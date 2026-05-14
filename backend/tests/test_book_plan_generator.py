#!/usr/bin/env python3
"""Tests for book_plan_generator: reasoning-aware budget sizing,
empty-content retry, and diagnostic logging.

The production failure these tests guard against:

- Planner tier was upgraded from gpt-4.1 (legacy chat) to gpt-5.5 (reasoning).
- gpt-5.5 spends a large chunk of `max_completion_tokens` on hidden reasoning
  before producing visible JSON output.
- The book-plan call sized its budget for legacy chat models (~12K for a
  25-chapter book), which the reasoning model exhausted entirely on internal
  reasoning, returning an empty `content` string.
- The orchestrator returned the empty response cleanly; the book-plan
  generator failed with "Book plan generation returned empty content"; the
  whole 25-chapter autocomplete job aborted with 0 chapters generated.

These tests cover the three fixes:
  1. `_planner_budget` inflates the cap for reasoning planners.
  2. Empty content triggers a single retry with double the budget.
  3. Diagnostic logging includes finish_reason / usage / budget when the
     final response is still empty.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from backend.auto_complete.helpers import book_plan_generator as bpg
from backend.auto_complete.helpers.book_plan_generator import (
    BookPlanGenerator,
    _extract_response_diagnostics,
    _is_reasoning_planner,
    _planner_budget,
)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _fake_orchestrator(planner_model: str, model_cap: int = 32768):
    """Build a MagicMock orchestrator that quacks like LLMOrchestrator
    enough for the budget / diagnostic helpers."""
    orch = MagicMock()
    orch.model_planner = planner_model
    orch.model = "gpt-4.1"
    orch._resolve_model = MagicMock(return_value=planner_model)
    orch._get_model_max_output_tokens = MagicMock(return_value=model_cap)
    return orch


def _chat_response(content: str, finish_reason: str = "stop", **usage_attrs):
    """Build a MagicMock that mimics an OpenAI chat-completions response."""
    choice = MagicMock()
    choice.message = MagicMock()
    choice.message.content = content
    choice.finish_reason = finish_reason
    usage = SimpleNamespace(**usage_attrs) if usage_attrs else None
    resp = MagicMock(spec=["choices", "usage"])
    resp.choices = [choice]
    resp.usage = usage
    return resp


# ---------------------------------------------------------------------------
# _is_reasoning_planner
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model,expected",
    [
        ("gpt-5.5", True),
        ("gpt-5.5-pro", True),
        ("gpt-5.2-pro", True),
        ("gpt-5", True),
        ("o1-preview", True),
        ("o3-mini", True),
        ("o4-mini", True),
        ("gpt-4.1", False),
        ("gpt-4o", False),
        ("gpt-4o-mini", False),
        ("", False),
    ],
)
def test_is_reasoning_planner_classifies_models(model: str, expected: bool):
    orch = _fake_orchestrator(model)
    assert _is_reasoning_planner(orch) is expected


def test_is_reasoning_planner_uses_resolve_model_first():
    orch = MagicMock()
    orch._resolve_model = MagicMock(return_value="gpt-5.5")
    orch.model_planner = "gpt-4.1"  # would lie if it were used
    assert _is_reasoning_planner(orch) is True


def test_is_reasoning_planner_falls_back_when_resolve_raises():
    orch = MagicMock()
    orch._resolve_model = MagicMock(side_effect=RuntimeError("boom"))
    orch.model_planner = "gpt-5.5"
    assert _is_reasoning_planner(orch) is True


# ---------------------------------------------------------------------------
# _planner_budget
# ---------------------------------------------------------------------------


def test_planner_budget_legacy_model_keeps_old_cap():
    """For gpt-4.1 the budget formula must match the historical behavior
    (clamp to legacy_ceiling, floor at base)."""
    orch = _fake_orchestrator("gpt-4.1")
    budget = _planner_budget(orch, base=12000, legacy_ceiling=16000)
    assert budget == 12000


def test_planner_budget_legacy_model_clamps_to_ceiling():
    orch = _fake_orchestrator("gpt-4.1")
    budget = _planner_budget(orch, base=99000, legacy_ceiling=16000)
    assert budget == 16000


def test_planner_budget_reasoning_model_inflates_for_25_chapters():
    """The exact regression: 25-chapter plan with gpt-5.5 must give the
    model enough headroom for reasoning + visible JSON."""
    orch = _fake_orchestrator("gpt-5.5", model_cap=32768)
    base = 2000 + 25 * 400  # 12000 (the failing prod value)
    budget = _planner_budget(orch, base=base, legacy_ceiling=16000)
    # 2.5 * 12000 = 30000; ceiling*2 = 32000; clamp to model cap 32768.
    assert budget == 32000
    assert budget > base, "reasoning planner must get more than the legacy budget"


def test_planner_budget_reasoning_model_clamps_to_model_cap():
    orch = _fake_orchestrator("gpt-5.5", model_cap=20000)
    budget = _planner_budget(orch, base=12000, legacy_ceiling=16000)
    assert budget == 20000


def test_planner_budget_reasoning_model_small_request_still_inflates():
    orch = _fake_orchestrator("gpt-5.5", model_cap=32768)
    # A small fix-count call: base=2500 ceiling=2500 → ceiling*2 = 5000.
    budget = _planner_budget(orch, base=2500, legacy_ceiling=2500)
    assert budget == 6250  # 2500 * 2.5; max(6250, 5000) = 6250


def test_planner_budget_reasoning_model_handles_resolve_failure():
    """If model resolution blows up, fall back to a sensible default cap."""
    orch = MagicMock()
    orch._resolve_model = MagicMock(return_value="gpt-5.5")
    orch.model_planner = "gpt-5.5"
    orch._get_model_max_output_tokens = MagicMock(side_effect=RuntimeError)
    budget = _planner_budget(orch, base=12000, legacy_ceiling=16000)
    assert budget > 12000
    assert budget <= 32000


# ---------------------------------------------------------------------------
# _extract_response_diagnostics
# ---------------------------------------------------------------------------


def test_diagnostics_chat_completions_happy_path():
    resp = _chat_response(
        "hello world",
        finish_reason="stop",
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
    )
    diag = _extract_response_diagnostics(resp)
    assert diag["content"] == "hello world"
    assert diag["finish_reason"] == "stop"
    assert diag["usage"]["prompt_tokens"] == 10
    assert diag["usage"]["completion_tokens"] == 20
    assert diag["usage"]["total_tokens"] == 30


def test_diagnostics_chat_completions_empty_with_length_finish():
    """The exact production failure shape: empty content + finish=length."""
    resp = _chat_response(
        "",
        finish_reason="length",
        prompt_tokens=2500,
        completion_tokens=12000,
        total_tokens=14500,
    )
    diag = _extract_response_diagnostics(resp)
    assert diag["content"] == ""
    assert diag["finish_reason"] == "length"
    assert diag["usage"]["completion_tokens"] == 12000


def test_diagnostics_extracts_reasoning_tokens_when_present():
    """gpt-5.5 surfaces reasoning_tokens via completion_tokens_details."""
    details = SimpleNamespace(reasoning_tokens=11500)
    usage = SimpleNamespace(
        prompt_tokens=2500,
        completion_tokens=12000,
        total_tokens=14500,
        completion_tokens_details=details,
    )
    choice = MagicMock()
    choice.message = MagicMock()
    choice.message.content = ""
    choice.finish_reason = "length"
    resp = MagicMock(spec=["choices", "usage"])
    resp.choices = [choice]
    resp.usage = usage
    diag = _extract_response_diagnostics(resp)
    assert diag["usage"]["reasoning_tokens"] == 11500


def test_diagnostics_responses_api_shape():
    resp = MagicMock(spec=["output_text", "usage", "finish_reason"])
    resp.output_text = "json output"
    resp.finish_reason = "completed"
    resp.usage = SimpleNamespace(input_tokens=100, output_tokens=200, total_tokens=300)
    diag = _extract_response_diagnostics(resp)
    assert diag["content"] == "json output"
    assert diag["finish_reason"] == "completed"
    assert diag["usage"]["input_tokens"] == 100
    assert diag["usage"]["output_tokens"] == 200


def test_diagnostics_handles_none_response():
    diag = _extract_response_diagnostics(None)
    assert diag == {"content": "", "finish_reason": None, "usage": {}}


def test_diagnostics_handles_choice_attribute_errors():
    """Defensive: a choice that throws on .message.content must yield empty."""
    bad_choice = MagicMock()

    class _Boom:
        @property
        def content(self):
            raise RuntimeError("nope")

    bad_choice.message = _Boom()
    bad_choice.finish_reason = "stop"
    resp = MagicMock(spec=["choices", "usage"])
    resp.choices = [bad_choice]
    resp.usage = None
    diag = _extract_response_diagnostics(resp)
    assert diag["content"] == ""
    assert diag["finish_reason"] == "stop"


# ---------------------------------------------------------------------------
# generate_plan: empty-content retry path
# ---------------------------------------------------------------------------


def _minimal_book_bible() -> str:
    return (
        "A small-town teacher faces the closure of her school. "
        * 12
    )


def _minimal_references() -> Dict[str, str]:
    return {
        "outline": "Chapter 1: Inciting incident. Chapter 2: First confrontation.",
        "characters": "Ruth: 31-year teacher, late fifties.",
        "world_building": "Rural town, autumn 2026.",
        "style_guide": "Close third, present tense, plain prose.",
    }


class _FakeOrchestrator:
    """Minimal LLMOrchestrator stand-in used for generate_plan tests.

    Captures every _make_api_call invocation and returns canned responses
    in order. Implements the small surface generate_plan touches:
      - _make_api_call(messages, **kwargs)  (async)
      - _resolve_model(role)
      - _get_model_max_output_tokens(model)
    """

    def __init__(self, responses: List[Any], planner_model: str = "gpt-5.5"):
        self._responses = list(responses)
        self.calls: List[Dict[str, Any]] = []
        self._planner_model = planner_model

    def _resolve_model(self, role: str) -> str:
        if role == "planner":
            return self._planner_model
        return "gpt-4.1"

    def _get_model_max_output_tokens(self, model: str) -> int:
        return 32768

    async def _make_api_call(self, *, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        if not self._responses:
            raise RuntimeError("No more canned responses")
        return self._responses.pop(0)


def _patch_orchestrator(monkeypatch, fake: _FakeOrchestrator) -> None:
    """Replace the LLMOrchestrator constructor used inside generate_plan."""

    def _factory(*args, **kwargs):
        return fake

    monkeypatch.setattr(bpg, "__name__", bpg.__name__)  # touch to ensure import
    # generate_plan does an inner import; patch both possible names.
    import backend.auto_complete.llm_orchestrator as llm_mod

    monkeypatch.setattr(llm_mod, "LLMOrchestrator", _factory)


def _run(coro):
    return asyncio.run(coro)


def test_generate_plan_retries_once_when_first_call_returns_empty(monkeypatch, caplog):
    """First call returns empty (length-truncated reasoning); the second call
    with double budget returns a complete plan. Result must be success."""
    target_chapters = 3
    valid_plan = {
        "metadata": {"created_at": "2026-05-14T00:00:00", "target_chapters": target_chapters},
        "global_constraints": {},
        "story_arcs": {"primary": "x", "secondary": [], "themes": []},
        "chapters": [
            {"chapter_number": i, "title": f"C{i}", "summary": "s", "objectives": []}
            for i in range(1, target_chapters + 1)
        ],
    }
    import json as _json
    fake = _FakeOrchestrator(
        responses=[
            _chat_response(
                "",
                finish_reason="length",
                prompt_tokens=2500,
                completion_tokens=4400,
                total_tokens=6900,
            ),
            _chat_response(
                _json.dumps(valid_plan),
                finish_reason="stop",
                prompt_tokens=2500,
                completion_tokens=900,
                total_tokens=3400,
            ),
        ]
    )
    _patch_orchestrator(monkeypatch, fake)

    with tempfile.TemporaryDirectory() as tmp:
        gen = BookPlanGenerator(project_path=tmp)
        with caplog.at_level(logging.WARNING, logger=bpg.__name__):
            result = _run(gen.generate_plan(
                book_bible=_minimal_book_bible(),
                references=_minimal_references(),
                target_chapters=target_chapters,
                model="gpt-4.1",
            ))

    assert result.success is True, f"expected success, got: {result.error}"
    assert result.plan is not None
    assert len(result.plan["chapters"]) == target_chapters

    assert len(fake.calls) == 2, "must retry exactly once on empty content"
    first_budget = fake.calls[0]["max_tokens"]
    second_budget = fake.calls[1]["max_tokens"]
    assert second_budget > first_budget, "retry must use a larger budget"
    assert second_budget <= 32768, "retry must clamp to model output cap"

    assert any(
        "empty content" in rec.getMessage() and "retrying" in rec.getMessage()
        for rec in caplog.records
    ), "must log a warning before retrying"


def test_generate_plan_does_not_retry_on_legacy_model_when_first_succeeds(monkeypatch):
    """Sanity check: the happy path still works on the first call."""
    target_chapters = 2
    valid_plan = {
        "chapters": [
            {"chapter_number": 1, "title": "C1", "summary": "s"},
            {"chapter_number": 2, "title": "C2", "summary": "s"},
        ],
    }
    import json as _json
    fake = _FakeOrchestrator(
        responses=[_chat_response(_json.dumps(valid_plan), finish_reason="stop")],
        planner_model="gpt-4.1",  # legacy planner
    )
    _patch_orchestrator(monkeypatch, fake)

    with tempfile.TemporaryDirectory() as tmp:
        gen = BookPlanGenerator(project_path=tmp)
        result = _run(gen.generate_plan(
            book_bible=_minimal_book_bible(),
            references=_minimal_references(),
            target_chapters=target_chapters,
            model="gpt-4.1",
        ))

    assert result.success is True
    assert len(fake.calls) == 1, "must not retry on a successful first call"
    # Legacy planner: budget should follow the old formula (no inflation).
    assert fake.calls[0]["max_tokens"] <= 16000


def test_generate_plan_logs_diagnostics_when_retry_also_returns_empty(monkeypatch, caplog):
    """Both calls return empty: result is a failure with diagnostics in the
    error string and a warning log emitted."""
    fake = _FakeOrchestrator(
        responses=[
            _chat_response("", finish_reason="length", completion_tokens=10000),
            _chat_response("", finish_reason="length", completion_tokens=20000),
        ]
    )
    _patch_orchestrator(monkeypatch, fake)

    with tempfile.TemporaryDirectory() as tmp:
        gen = BookPlanGenerator(project_path=tmp)
        with caplog.at_level(logging.WARNING, logger=bpg.__name__):
            result = _run(gen.generate_plan(
                book_bible=_minimal_book_bible(),
                references=_minimal_references(),
                target_chapters=3,
                model="gpt-4.1",
            ))

    assert result.success is False
    assert result.error is not None
    # Error message must surface enough to debug from a log line alone.
    assert "finish_reason" in result.error
    assert "budget" in result.error
    # And we must have warned before failing.
    assert any("empty content" in rec.getMessage() for rec in caplog.records)


def test_generate_plan_uses_inflated_budget_for_reasoning_planner(monkeypatch):
    """Regression guard: the very first call's max_tokens for a 25-chapter
    plan with gpt-5.5 must be larger than the old hardcoded 12000."""
    target_chapters = 25
    fake = _FakeOrchestrator(
        responses=[_chat_response("", finish_reason="length"),
                   _chat_response("", finish_reason="length")],
        planner_model="gpt-5.5",
    )
    _patch_orchestrator(monkeypatch, fake)

    with tempfile.TemporaryDirectory() as tmp:
        gen = BookPlanGenerator(project_path=tmp)
        _run(gen.generate_plan(
            book_bible=_minimal_book_bible(),
            references=_minimal_references(),
            target_chapters=target_chapters,
            model="gpt-4.1",
        ))

    first_budget = fake.calls[0]["max_tokens"]
    assert first_budget > 12000, (
        f"reasoning planner with 25 chapters must exceed the old failing budget "
        f"of 12000, got {first_budget}"
    )
