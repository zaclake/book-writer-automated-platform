#!/usr/bin/env python3
"""Tests for the Path A+ P1.3 model-tiering plumbing.

Verifies that:
  - LLMOrchestrator picks up MODEL_PLANNER / MODEL_EDITOR env vars
  - _resolve_model maps roles to the right tier
  - _make_api_call routes a `model_role` kwarg through to the underlying
    OpenAI call without leaking the tier-routing kwargs into SDK kwargs

These tests use a stubbed OpenAI client so no network calls fire.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict
from unittest.mock import MagicMock

from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig


def _make_orchestrator(
    monkeypatch,
    *,
    planner: str = "gpt-5.2-pro",
    editor: str = "gpt-5.2-pro",
    drafter: str = "gpt-4.1",
) -> LLMOrchestrator:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_PLANNER", planner)
    monkeypatch.setenv("MODEL_EDITOR", editor)
    # Pass model explicitly: the constructor's default-arg "gpt-4.1" shadows
    # DEFAULT_AI_MODEL via short-circuit in `model or os.getenv(...)`. Tests
    # set the drafter via the explicit kwarg so the env path is irrelevant.
    return LLMOrchestrator(
        model=drafter,
        retry_config=RetryConfig(max_retries=0),
        user_id="test-user",
        enable_billing=False,
    )


def _stub_chat_completions(orch: LLMOrchestrator, captured: Dict[str, Any]) -> None:
    """Replace the orchestrator's chat completions endpoint with a capturing stub."""

    def fake_create(**kwargs):
        captured.update(kwargs)
        choice = MagicMock()
        choice.message.content = "ok"
        choice.finish_reason = "stop"
        resp = MagicMock()
        resp.choices = [choice]
        resp.usage = MagicMock(prompt_tokens=1, completion_tokens=1, total_tokens=2)
        return resp

    orch.client.chat.completions.create = fake_create  # type: ignore[assignment]


def test_init_reads_tier_env_vars(monkeypatch):
    orch = _make_orchestrator(
        monkeypatch,
        planner="gpt-5.2-pro",
        editor="gpt-5.2-pro",
        drafter="gpt-4.1",
    )
    assert orch.model == "gpt-4.1"
    assert orch.model_drafter == "gpt-4.1"
    assert orch.model_planner == "gpt-5.2-pro"
    assert orch.model_editor == "gpt-5.2-pro"


def test_init_defaults_when_env_unset(monkeypatch):
    monkeypatch.delenv("MODEL_PLANNER", raising=False)
    monkeypatch.delenv("MODEL_EDITOR", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    orch = LLMOrchestrator(
        model="gpt-4.1",
        retry_config=RetryConfig(max_retries=0),
        user_id="test-user",
        enable_billing=False,
    )
    assert orch.model == "gpt-4.1"
    assert orch.model_planner == "gpt-5.2-pro"
    assert orch.model_editor == "gpt-5.2-pro"


def test_resolve_model_role_routing(monkeypatch):
    orch = _make_orchestrator(
        monkeypatch,
        planner="planner-model",
        editor="editor-model",
        drafter="drafter-model",
    )
    assert orch._resolve_model("planner") == "planner-model"
    assert orch._resolve_model("editor") == "editor-model"
    assert orch._resolve_model("drafter") == "drafter-model"
    assert orch._resolve_model(None) == "drafter-model"
    assert orch._resolve_model("garbage") == "drafter-model"  # safe fallback


def test_get_model_max_output_tokens_handles_gpt5(monkeypatch):
    orch = _make_orchestrator(monkeypatch)
    assert orch._get_model_max_output_tokens("gpt-5.2-pro") == 65536
    assert orch._get_model_max_output_tokens("gpt-5.2") == 32768
    assert orch._get_model_max_output_tokens("gpt-5-something") == 32768
    assert orch._get_model_max_output_tokens("gpt-4.1") == 32768
    assert orch._get_model_max_output_tokens("gpt-4o") == 16384
    assert orch._get_model_max_output_tokens("totally-unknown-model") == 16384


def test_make_api_call_routes_role_to_planner(monkeypatch):
    orch = _make_orchestrator(
        monkeypatch,
        planner="planner-model",
        editor="editor-model",
        drafter="drafter-model",
    )
    captured: Dict[str, Any] = {}
    _stub_chat_completions(orch, captured)

    asyncio.run(orch._make_api_call(
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.1,
        max_tokens=200,
        model_role="planner",
        use_file_search=False,
    ))

    assert captured.get("model") == "planner-model", "planner role must route to MODEL_PLANNER"
    # Routing kwargs must NOT leak into the SDK call (would 400 on OpenAI side).
    assert "model_role" not in captured
    assert "model_override" not in captured


def test_make_api_call_routes_role_to_editor(monkeypatch):
    orch = _make_orchestrator(
        monkeypatch,
        planner="planner-model",
        editor="editor-model",
        drafter="drafter-model",
    )
    captured: Dict[str, Any] = {}
    _stub_chat_completions(orch, captured)

    asyncio.run(orch._make_api_call(
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.1,
        max_tokens=200,
        model_role="editor",
        use_file_search=False,
    ))

    assert captured.get("model") == "editor-model"
    assert "model_role" not in captured


def test_make_api_call_default_uses_drafter(monkeypatch):
    orch = _make_orchestrator(
        monkeypatch,
        planner="planner-model",
        editor="editor-model",
        drafter="drafter-model",
    )
    captured: Dict[str, Any] = {}
    _stub_chat_completions(orch, captured)

    asyncio.run(orch._make_api_call(
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.1,
        max_tokens=200,
        use_file_search=False,
    ))

    assert captured.get("model") == "drafter-model", "no role must default to drafter (self.model)"


def test_make_api_call_explicit_model_override_wins(monkeypatch):
    orch = _make_orchestrator(monkeypatch)
    captured: Dict[str, Any] = {}
    _stub_chat_completions(orch, captured)

    asyncio.run(orch._make_api_call(
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.1,
        max_tokens=200,
        model_role="planner",
        model_override="explicit-special-model",
        use_file_search=False,
    ))

    assert captured.get("model") == "explicit-special-model"


def test_max_tokens_clamping_uses_effective_model(monkeypatch):
    """Clamping must use the effective tier model, not self.model.

    A 60k max_tokens request routed to planner=gpt-5.2-pro (cap 65536) should
    NOT be clamped, even though self.model=gpt-4.1 would clamp at 32768.
    """
    orch = _make_orchestrator(
        monkeypatch,
        planner="gpt-5.2-pro",
        editor="gpt-5.2-pro",
        drafter="gpt-4.1",
    )
    captured: Dict[str, Any] = {}
    _stub_chat_completions(orch, captured)

    asyncio.run(orch._make_api_call(
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.1,
        max_tokens=60000,
        model_role="planner",
        use_file_search=False,
    ))

    assert captured.get("max_tokens") == 60000, (
        f"60k under planner-tier cap (65536) should NOT clamp; got {captured.get('max_tokens')}"
    )


def test_max_tokens_clamping_to_drafter_cap(monkeypatch):
    """Drafter (gpt-4.1) cap is 32768 — a 60k request should clamp."""
    orch = _make_orchestrator(monkeypatch, drafter="gpt-4.1")
    captured: Dict[str, Any] = {}
    _stub_chat_completions(orch, captured)

    asyncio.run(orch._make_api_call(
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.1,
        max_tokens=60000,
        use_file_search=False,
    ))

    assert captured.get("max_tokens") == 32768, (
        f"60k under drafter cap should clamp to 32768; got {captured.get('max_tokens')}"
    )
