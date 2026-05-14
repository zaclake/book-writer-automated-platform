#!/usr/bin/env python3
"""Tests for Path A+ P2.4 — bounded literary sniff-test pass.

The sniff test is "one critique call + one targeted-rewrite call, capped at 5
paragraph rewrites, opt-out via ENABLE_SNIFF_TEST=false". These tests verify:

1. Both LLM calls route through the editor tier (not drafter, not planner).
2. The critique JSON is parsed safely; bad JSON / unrelated payloads
   produce ``{skipped: True, reason: ...}`` rather than blowing up.
3. The rewrite cap (MAX_REWRITES_PER_CHAPTER) is enforced.
4. apply_targeted_rewrites only invokes the LLM if at least one quoted
   paragraph can be located in the chapter; unmatched quotes are reported
   in info, not silently lost.
5. The wrapper accepts the rewritten chapter only when it's plausibly the
   full chapter (>= 60% of original word count).
6. ENABLE_SNIFF_TEST=false short-circuits the critique cleanly.
7. Short chapters (< MIN_WORDS_FOR_SNIFF_TEST) are skipped without an LLM call.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

from backend.auto_complete.helpers import sniff_test as sniff_mod
from backend.auto_complete.helpers.sniff_test import (
    MAX_REWRITES_PER_CHAPTER,
    MIN_WORDS_FOR_SNIFF_TEST,
    apply_targeted_rewrites,
    is_sniff_test_enabled,
    run_sniff_test,
    run_sniff_test_and_rewrite,
    _find_paragraph_in_chapter,
)
from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig


def _make_orchestrator(monkeypatch) -> LLMOrchestrator:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    return LLMOrchestrator(
        model="gpt-4.1",
        retry_config=RetryConfig(max_retries=0),
        user_id="sniff-test-user",
        enable_billing=False,
    )


class _Resp:
    """Minimal fake OpenAI response — has .choices[0].message.content but
    NOT .output_text (which would route content extraction down the wrong
    code path in the orchestrator)."""

    def __init__(self, content: str) -> None:
        class _Msg:
            def __init__(self, c: str) -> None:
                self.content = c

        class _Choice:
            def __init__(self, c: str) -> None:
                self.message = _Msg(c)
                self.finish_reason = "stop"

        class _Usage:
            prompt_tokens = 1
            completion_tokens = 1
            total_tokens = 2

        self.choices = [_Choice(content)]
        self.usage = _Usage()


def _set_chat_response(orch: LLMOrchestrator, capture: List[Dict[str, Any]], payloads: List[str]) -> None:
    """Wire orchestrator to return ``payloads`` in order; record kwargs to capture."""
    iter_payloads = iter(payloads)

    def fake_create(**kwargs):
        capture.append(kwargs)
        try:
            body = next(iter_payloads)
        except StopIteration:
            body = ""
        return _Resp(body)

    orch.client.chat.completions.create = fake_create  # type: ignore[assignment]


def _make_chapter(extra: str = "", min_words: int = MIN_WORDS_FOR_SNIFF_TEST + 50) -> str:
    """Build a chapter long enough to clear the MIN_WORDS_FOR_SNIFF_TEST floor."""
    base = (
        "Mitch parked the truck at the edge of the lane.\n\n"
        "Ruth stepped onto the porch, hands tight at her sides. She did not look at him.\n\n"
        "The dog sat in the back of the truck and did not bark.\n\n"
    )
    while len(base.split()) < min_words:
        base += "He waited and so did she and the wind moved through the corn. " * 4
        base += "\n\n"
    if extra:
        base = base + "\n\n" + extra
    return base


# ──────────────────────────────────────────────────────────────────────────
# 1. Env gate
# ──────────────────────────────────────────────────────────────────────────


class TestEnvGate:
    def test_enabled_by_default(self, monkeypatch):
        monkeypatch.delenv("ENABLE_SNIFF_TEST", raising=False)
        assert is_sniff_test_enabled() is True

    def test_explicit_false_disables(self, monkeypatch):
        for v in ("false", "FALSE", "0", "no", "No"):
            monkeypatch.setenv("ENABLE_SNIFF_TEST", v)
            assert is_sniff_test_enabled() is False, v

    def test_explicit_true_enables(self, monkeypatch):
        monkeypatch.setenv("ENABLE_SNIFF_TEST", "true")
        assert is_sniff_test_enabled() is True

    def test_run_sniff_test_skipped_when_disabled(self, monkeypatch):
        monkeypatch.setenv("ENABLE_SNIFF_TEST", "false")
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        _set_chat_response(orch, captured, ["{}"])
        chapter = _make_chapter()
        result = asyncio.run(run_sniff_test(orch, chapter, 1))
        assert result.get("skipped") is True
        assert result.get("reason") == "disabled_by_env"
        assert len(captured) == 0, "Disabled gate must NOT call the LLM"


# ──────────────────────────────────────────────────────────────────────────
# 2. Critique LLM call
# ──────────────────────────────────────────────────────────────────────────


class TestRunSniffTest:
    def test_short_chapter_is_skipped_without_llm_call(self, monkeypatch):
        monkeypatch.setenv("ENABLE_SNIFF_TEST", "true")
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        _set_chat_response(orch, captured, ["{}"])
        # Below the floor.
        result = asyncio.run(run_sniff_test(orch, "He waited.", 1))
        assert result.get("skipped") is True
        assert result.get("reason") == "chapter_too_short"
        assert len(captured) == 0

    def test_critique_call_uses_editor_tier(self, monkeypatch):
        monkeypatch.setenv("ENABLE_SNIFF_TEST", "true")
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        payload = json.dumps({
            "critique_summary": "Reads like the model's default sensory mode.",
            "strongest_paragraph": "Ruth stepped onto the porch ...",
            "unearned_beat": "The reconciliation lands too easily.",
            "targeted_rewrites": [],
        })
        _set_chat_response(orch, captured, [payload])
        asyncio.run(run_sniff_test(orch, _make_chapter(), 1))
        assert len(captured) == 1
        assert captured[0]["model"] == "gpt-5.2-pro", "must use editor tier"

    def test_critique_returns_normalized_rewrites(self, monkeypatch):
        monkeypatch.setenv("ENABLE_SNIFF_TEST", "true")
        orch = _make_orchestrator(monkeypatch)
        payload = json.dumps({
            "critique_summary": "Three AI tells: gesture clutter, sensory anchor, tidy ending.",
            "strongest_paragraph": "Ruth stepped ...",
            "unearned_beat": "He forgives without payment.",
            "targeted_rewrites": [
                {
                    "paragraph_quote": "Ruth stepped onto the porch, hands tight at her sides. She did not look at him.",
                    "problem": "Reflex gesture combo.",
                    "rewrite_directive": "Cut the gesture; render her stillness through delay only.",
                },
                {
                    # Missing rewrite_directive → must be dropped.
                    "paragraph_quote": "The dog sat in the back of the truck and did not bark.",
                    "problem": "Filler beat.",
                },
            ],
        })
        _set_chat_response(orch, [], [payload])
        result = asyncio.run(run_sniff_test(orch, _make_chapter(), 1))
        assert result["skipped"] is False
        assert len(result["targeted_rewrites"]) == 1
        kept = result["targeted_rewrites"][0]
        assert "stepped onto the porch" in kept["paragraph_quote"]
        assert kept["rewrite_directive"]

    def test_critique_caps_at_max_rewrites(self, monkeypatch):
        monkeypatch.setenv("ENABLE_SNIFF_TEST", "true")
        orch = _make_orchestrator(monkeypatch)
        many = [
            {
                "paragraph_quote": f"Para {i}",
                "problem": "x",
                "rewrite_directive": "y",
            }
            for i in range(MAX_REWRITES_PER_CHAPTER + 5)
        ]
        payload = json.dumps({"critique_summary": "x", "targeted_rewrites": many})
        _set_chat_response(orch, [], [payload])
        result = asyncio.run(run_sniff_test(orch, _make_chapter(), 1))
        assert len(result["targeted_rewrites"]) == MAX_REWRITES_PER_CHAPTER

    def test_critique_handles_bad_json(self, monkeypatch):
        monkeypatch.setenv("ENABLE_SNIFF_TEST", "true")
        orch = _make_orchestrator(monkeypatch)
        _set_chat_response(orch, [], ["this is not JSON {{"])
        result = asyncio.run(run_sniff_test(orch, _make_chapter(), 1))
        assert result.get("skipped") is True
        assert result.get("reason") == "json_parse_error"

    def test_critique_handles_llm_error(self, monkeypatch):
        monkeypatch.setenv("ENABLE_SNIFF_TEST", "true")
        orch = _make_orchestrator(monkeypatch)

        def boom(**kwargs):
            raise RuntimeError("openai blew up")

        orch.client.chat.completions.create = boom  # type: ignore[assignment]
        result = asyncio.run(run_sniff_test(orch, _make_chapter(), 1))
        assert result.get("skipped") is True
        assert "llm_error" in result.get("reason", "")


# ──────────────────────────────────────────────────────────────────────────
# 3. Paragraph matching + targeted rewrite
# ──────────────────────────────────────────────────────────────────────────


class TestParagraphMatching:
    def test_exact_substring_match(self):
        chapter = "Para A.\n\nPara B that is longer than the others.\n\nPara C."
        assert _find_paragraph_in_chapter(chapter, "Para B that is longer than the others.") == "Para B that is longer than the others."

    def test_whitespace_normalized_match(self):
        chapter = "Para B  spans    multiple   spaces."
        # Quote uses single spaces; chapter has multi-space runs
        assert _find_paragraph_in_chapter(chapter, "Para B spans multiple spaces.") == chapter

    def test_prefix_match_for_truncated_quote(self):
        para = "Ruth stepped onto the porch, hands tight at her sides. She did not look at him. The wind moved through the corn."
        chapter = f"Mitch parked the truck.\n\n{para}\n\nThe dog sat in the back."
        # Quote is truncated mid-paragraph (model often does this)
        truncated = "Ruth stepped onto the porch, hands tight at her sides. She did not"
        assert _find_paragraph_in_chapter(chapter, truncated) == para

    def test_returns_none_when_no_match(self):
        chapter = "Para A.\n\nPara B.\n\nPara C."
        assert _find_paragraph_in_chapter(chapter, "Completely unrelated content here.") is None


class TestApplyTargetedRewrites:
    def test_no_rewrites_returns_input(self, monkeypatch):
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        _set_chat_response(orch, captured, [""])
        text = _make_chapter()
        out, info = asyncio.run(apply_targeted_rewrites(orch, text, [], 1))
        assert out == text
        assert info["applied"] is False
        assert info["skipped_reason"] == "no_rewrites"
        assert len(captured) == 0

    def test_unmatched_quotes_skip_llm_call(self, monkeypatch):
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        _set_chat_response(orch, captured, ["should not be called"])
        text = _make_chapter()
        rewrites = [{
            "paragraph_quote": "This paragraph does not exist in the chapter at all.",
            "problem": "x",
            "rewrite_directive": "y",
        }]
        out, info = asyncio.run(apply_targeted_rewrites(orch, text, rewrites, 1))
        assert out == text
        assert info["matched"] == 0
        assert info["applied"] is False
        assert info["skipped_reason"] == "no_matched_paragraphs"
        assert len(info["unmatched_quotes"]) == 1
        assert len(captured) == 0, "must not call LLM if nothing matched"

    def test_applies_rewrite_when_paragraph_matches(self, monkeypatch):
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        text = _make_chapter()
        # Rewrite returns chapter with one paragraph swapped — same length range.
        rewritten_text = text.replace(
            "Ruth stepped onto the porch, hands tight at her sides. She did not look at him.",
            "Ruth waited on the porch. She let the silence be the answer.",
        )
        _set_chat_response(orch, captured, [rewritten_text])

        rewrites = [{
            "paragraph_quote": "Ruth stepped onto the porch, hands tight at her sides. She did not look at him.",
            "problem": "Gesture clutter.",
            "rewrite_directive": "Cut the gesture; render stillness only.",
        }]
        out, info = asyncio.run(apply_targeted_rewrites(orch, text, rewrites, 1))
        assert info["matched"] == 1
        assert info["applied"] is True
        assert "Ruth waited on the porch" in out
        assert "hands tight at her sides" not in out

    def test_rewrite_call_uses_editor_tier(self, monkeypatch):
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        text = _make_chapter()
        _set_chat_response(orch, captured, [text])  # echo back
        rewrites = [{
            "paragraph_quote": "Ruth stepped onto the porch, hands tight at her sides. She did not look at him.",
            "problem": "p",
            "rewrite_directive": "d",
        }]
        asyncio.run(apply_targeted_rewrites(orch, text, rewrites, 1))
        assert captured, "rewrite call should have happened"
        assert captured[0]["model"] == "gpt-5.2-pro"

    def test_caps_rewrites_at_max(self, monkeypatch):
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        text = _make_chapter()
        _set_chat_response(orch, captured, [text])
        many = [
            {
                "paragraph_quote": "Ruth stepped onto the porch, hands tight at her sides. She did not look at him.",
                "problem": "p",
                "rewrite_directive": "d",
            }
            for _ in range(MAX_REWRITES_PER_CHAPTER + 3)
        ]
        _, info = asyncio.run(apply_targeted_rewrites(orch, text, many, 1))
        assert info["attempted"] == MAX_REWRITES_PER_CHAPTER

    def test_rejects_rewrite_that_shrinks_chapter(self, monkeypatch):
        """If the rewrite call returns only ~half the chapter, the model
        ignored 'return the full chapter' — keep the original."""
        orch = _make_orchestrator(monkeypatch)
        text = _make_chapter()
        # Output is way too short — fewer than 60% of the original word count.
        truncated = " ".join(text.split()[: int(len(text.split()) * 0.4)])
        _set_chat_response(orch, [], [truncated])
        rewrites = [{
            "paragraph_quote": "Ruth stepped onto the porch, hands tight at her sides. She did not look at him.",
            "problem": "p",
            "rewrite_directive": "d",
        }]
        out, info = asyncio.run(apply_targeted_rewrites(orch, text, rewrites, 1))
        assert out == text  # original preserved
        assert info["applied"] is False
        assert info["skipped_reason"] == "rewrite_too_short"


# ──────────────────────────────────────────────────────────────────────────
# 4. End-to-end wrapper
# ──────────────────────────────────────────────────────────────────────────


class TestRunSniffTestAndRewrite:
    def test_no_rewrites_means_no_rewrite_call(self, monkeypatch):
        monkeypatch.setenv("ENABLE_SNIFF_TEST", "true")
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        _set_chat_response(orch, captured, [json.dumps({
            "critique_summary": "clean",
            "targeted_rewrites": [],
        })])
        text = _make_chapter()
        out, info = asyncio.run(run_sniff_test_and_rewrite(orch, text, 1))
        assert out == text
        assert info["rewrite"]["applied"] is False
        # Only the critique call should have happened.
        assert len(captured) == 1

    def test_critique_then_rewrite_path(self, monkeypatch):
        monkeypatch.setenv("ENABLE_SNIFF_TEST", "true")
        orch = _make_orchestrator(monkeypatch)
        text = _make_chapter()
        rewritten = text.replace(
            "Ruth stepped onto the porch, hands tight at her sides. She did not look at him.",
            "Ruth waited on the porch. She let the silence be the answer.",
        )
        critique_payload = json.dumps({
            "critique_summary": "AI gestures.",
            "targeted_rewrites": [{
                "paragraph_quote": "Ruth stepped onto the porch, hands tight at her sides. She did not look at him.",
                "problem": "p",
                "rewrite_directive": "d",
            }],
        })
        captured: List[Dict[str, Any]] = []
        _set_chat_response(orch, captured, [critique_payload, rewritten])
        out, info = asyncio.run(run_sniff_test_and_rewrite(orch, text, 1))
        assert info["critique"]["skipped"] is False
        assert info["rewrite"]["applied"] is True
        assert "Ruth waited on the porch" in out
        # Both calls used editor tier.
        assert all(c["model"] == "gpt-5.2-pro" for c in captured)
        assert len(captured) == 2

    def test_disabled_short_circuits_at_wrapper(self, monkeypatch):
        monkeypatch.setenv("ENABLE_SNIFF_TEST", "false")
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        _set_chat_response(orch, captured, ["{}"])
        text = _make_chapter()
        out, info = asyncio.run(run_sniff_test_and_rewrite(orch, text, 1))
        assert out == text
        assert info["critique"]["skipped"] is True
        assert info["critique"]["reason"] == "disabled_by_env"
        assert info["rewrite"]["applied"] is False
        assert len(captured) == 0
