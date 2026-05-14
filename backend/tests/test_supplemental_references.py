#!/usr/bin/env python3
"""Tests for Path A+ P3.3 — themes-and-motifs, research-notes,
target-audience-profile, and series-bible are CONSUMED by the skeleton planner.

Background: prior to P3.3, all four references were generated and silently
dropped — `themes_ref` was loaded into a variable in skeleton_expand and
never read; the others weren't loaded at all. This test pins the new
behavior so the references actually inform planning.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

from backend.auto_complete.helpers.skeleton_expand import generate_skeleton
from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig


def _make_orchestrator(monkeypatch) -> LLMOrchestrator:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    return LLMOrchestrator(
        model="gpt-4.1",
        retry_config=RetryConfig(max_retries=0),
        user_id="ref-audit-user",
        enable_billing=False,
    )


class _Resp:
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


def _capture_chat(orch: LLMOrchestrator, captured: List[Dict[str, Any]]) -> None:
    """Skeleton call returns a minimal valid JSON object so the function
    completes; what we actually test is the user prompt that went IN."""
    body = json.dumps({
        "beats": [
            {
                "beat_number": 1,
                "action": "test action",
                "what_changes": "test change",
                "scene_shape": "interior_pressure",
                "interiority_mode": "free_indirect",
                "characters_present": ["A"],
            }
        ]
    })

    def fake_create(**kwargs):
        captured.append(kwargs)
        return _Resp(body)

    orch.client.chat.completions.create = fake_create  # type: ignore[assignment]


def _basic_chapter_plan() -> Dict[str, Any]:
    return {
        "summary": "Chapter focuses on character A's internal struggle.",
        "objectives": ["Reveal A's secret"],
        "focal_characters": ["A"],
        "pov_character": "A",
        "chapter_shape": "introspective",
    }


# ──────────────────────────────────────────────────────────────────────────
# 1. Each supplemental reference appears in the planner's user prompt
# ──────────────────────────────────────────────────────────────────────────


class TestSupplementalRefsInPrompt:
    def test_themes_and_motifs_is_injected(self, monkeypatch):
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        _capture_chat(orch, captured)

        themes = (
            "## Imagery System\n- Cold water as memory\n- Doors as choices\n"
            "## Thematic Question\nCan a person outrun the place that made them?"
        )

        asyncio.run(generate_skeleton(
            orchestrator=orch,
            chapter_number=3,
            total_chapters=20,
            chapter_plan=_basic_chapter_plan(),
            book_bible="Some bible content here.",
            themes_and_motifs=themes,
        ))

        user_prompt = next(m["content"] for m in captured[0]["messages"] if m["role"] == "user")
        assert "THEMES & MOTIFS" in user_prompt
        assert "Cold water as memory" in user_prompt
        assert "Doors as choices" in user_prompt
        assert "outrun the place that made them" in user_prompt

    def test_research_notes_is_injected(self, monkeypatch):
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        _capture_chat(orch, captured)

        research = (
            "## Sailing & rigging\n- A halyard runs through a sheave at the mast head.\n"
            "- A jib sheet is the line that controls the foresail."
        )
        asyncio.run(generate_skeleton(
            orchestrator=orch,
            chapter_number=3,
            total_chapters=20,
            chapter_plan=_basic_chapter_plan(),
            book_bible="Some bible.",
            research_notes=research,
        ))

        user_prompt = next(m["content"] for m in captured[0]["messages"] if m["role"] == "user")
        assert "RESEARCH NOTES" in user_prompt
        assert "halyard" in user_prompt or "jib sheet" in user_prompt

    def test_target_audience_is_injected(self, monkeypatch):
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        _capture_chat(orch, captured)

        audience = (
            "Adult literary readers, age 35-65, comfortable with slow openings, "
            "low-action high-character novels in the vein of Marilynne Robinson."
        )
        asyncio.run(generate_skeleton(
            orchestrator=orch,
            chapter_number=3,
            total_chapters=20,
            chapter_plan=_basic_chapter_plan(),
            book_bible="Some bible.",
            target_audience_profile=audience,
        ))

        user_prompt = next(m["content"] for m in captured[0]["messages"] if m["role"] == "user")
        assert "TARGET AUDIENCE" in user_prompt
        assert "Marilynne Robinson" in user_prompt

    def test_series_bible_is_injected(self, monkeypatch):
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        _capture_chat(orch, captured)

        series = "Book 1 ended with Reyes being demoted to night shift. Reyes carries a scar over the left eye since Book 1 ch 18."
        asyncio.run(generate_skeleton(
            orchestrator=orch,
            chapter_number=3,
            total_chapters=20,
            chapter_plan=_basic_chapter_plan(),
            book_bible="Some bible.",
            series_bible=series,
        ))

        user_prompt = next(m["content"] for m in captured[0]["messages"] if m["role"] == "user")
        assert "SERIES BIBLE" in user_prompt
        assert "scar over the left eye" in user_prompt or "demoted to night shift" in user_prompt


# ──────────────────────────────────────────────────────────────────────────
# 2. Empty inputs do NOT add a noisy header
# ──────────────────────────────────────────────────────────────────────────


class TestSupplementalRefsAreOptional:
    def test_no_supplemental_block_when_all_empty(self, monkeypatch):
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        _capture_chat(orch, captured)

        asyncio.run(generate_skeleton(
            orchestrator=orch,
            chapter_number=1,
            total_chapters=20,
            chapter_plan=_basic_chapter_plan(),
            book_bible="Bible content.",
            # All four supplemental refs left at empty defaults.
        ))

        user_prompt = next(m["content"] for m in captured[0]["messages"] if m["role"] == "user")
        assert "SUPPLEMENTAL CRAFT CONTEXT" not in user_prompt
        assert "THEMES & MOTIFS" not in user_prompt
        assert "RESEARCH NOTES" not in user_prompt
        assert "TARGET AUDIENCE" not in user_prompt
        assert "SERIES BIBLE" not in user_prompt

    def test_partial_supplemental_only_includes_present_refs(self, monkeypatch):
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        _capture_chat(orch, captured)

        asyncio.run(generate_skeleton(
            orchestrator=orch,
            chapter_number=1,
            total_chapters=20,
            chapter_plan=_basic_chapter_plan(),
            book_bible="Bible content.",
            themes_and_motifs="just themes here",
            research_notes="",
            target_audience_profile="",
            series_bible="",
        ))

        user_prompt = next(m["content"] for m in captured[0]["messages"] if m["role"] == "user")
        assert "SUPPLEMENTAL CRAFT CONTEXT" in user_prompt
        assert "THEMES & MOTIFS" in user_prompt
        assert "RESEARCH NOTES" not in user_prompt
        assert "TARGET AUDIENCE" not in user_prompt
        assert "SERIES BIBLE" not in user_prompt

    def test_whitespace_only_ref_is_treated_as_empty(self, monkeypatch):
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        _capture_chat(orch, captured)

        asyncio.run(generate_skeleton(
            orchestrator=orch,
            chapter_number=1,
            total_chapters=20,
            chapter_plan=_basic_chapter_plan(),
            book_bible="Bible content.",
            themes_and_motifs="   \n\n   ",  # whitespace only
        ))

        user_prompt = next(m["content"] for m in captured[0]["messages"] if m["role"] == "user")
        assert "THEMES & MOTIFS" not in user_prompt


# ──────────────────────────────────────────────────────────────────────────
# 3. Truncation is applied (defense against giant references blowing prompts)
# ──────────────────────────────────────────────────────────────────────────


class TestSupplementalRefsAreTruncated:
    def test_themes_truncated_to_1500_chars(self, monkeypatch):
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        _capture_chat(orch, captured)

        # 5000 characters of unique tagged content so we can detect truncation.
        themes = "X" * 1490 + "BEFORE_BOUNDARY" + "Y" * 4000 + "AFTER_BOUNDARY"
        asyncio.run(generate_skeleton(
            orchestrator=orch,
            chapter_number=1,
            total_chapters=20,
            chapter_plan=_basic_chapter_plan(),
            book_bible="Bible.",
            themes_and_motifs=themes,
        ))

        user_prompt = next(m["content"] for m in captured[0]["messages"] if m["role"] == "user")
        # First boundary marker should be missing (we only ship the first 1500c)
        assert "BEFORE_BOUNDARY" not in user_prompt
        assert "AFTER_BOUNDARY" not in user_prompt

    def test_target_audience_truncated_to_800_chars(self, monkeypatch):
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        _capture_chat(orch, captured)

        audience = "Z" * 790 + "BOUNDARY_MARKER" + "Z" * 1000
        asyncio.run(generate_skeleton(
            orchestrator=orch,
            chapter_number=1,
            total_chapters=20,
            chapter_plan=_basic_chapter_plan(),
            book_bible="Bible.",
            target_audience_profile=audience,
        ))

        user_prompt = next(m["content"] for m in captured[0]["messages"] if m["role"] == "user")
        assert "BOUNDARY_MARKER" not in user_prompt
