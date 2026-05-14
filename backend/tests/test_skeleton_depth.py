#!/usr/bin/env python3
"""Tests for the Path A+ P1.1 deeper-skeleton schema and its consumption.

Verifies:
  - _default_skeleton populates pov_want / pov_obstacle / interiority_mode etc.
  - The skeleton system prompt teaches the model the new fields.
  - The skeleton user-prompt JSON example and rules reference the new fields.
  - expand_beat injects INTERIOR ARCHITECTURE block into the user prompt.
  - expand_beat injects an INTERIORITY MODE block into the system prompt.
  - Legacy beats (without the new fields) still produce valid prompts.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List
from unittest.mock import MagicMock

from backend.auto_complete.helpers.skeleton_expand import (
    SKELETON_SYSTEM,
    _default_skeleton,
    expand_beat,
)
from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig


def _make_orchestrator(monkeypatch) -> LLMOrchestrator:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    return LLMOrchestrator(
        model="gpt-4.1",
        retry_config=RetryConfig(max_retries=0),
        user_id="test-user",
        enable_billing=False,
    )


# ───── Schema-shape tests (no LLM calls) ─────


def test_default_skeleton_populates_new_fields_for_every_beat():
    plan = {
        "summary": "Detective interviews suspect.",
        "objectives": ["Get the alibi", "Push them off-balance"],
        "focal_characters": ["Detective Reyes", "Mr. Halsey"],
        "pov_character": "Detective Reyes",
        "required_plot_points": ["Halsey lies about Tuesday night"],
    }
    beats = _default_skeleton("standard", chapter_plan=plan)
    assert len(beats) >= 8
    new_fields = {"pov_want", "pov_obstacle", "pov_concession", "subtext", "interiority_mode"}
    for b in beats:
        missing = new_fields - set(b.keys())
        assert not missing, f"beat {b.get('beat_number')} missing P1.1 fields: {missing}"
        # pov_want and pov_obstacle must always be non-empty.
        assert b["pov_want"], f"beat {b.get('beat_number')} has empty pov_want"
        assert b["pov_obstacle"], f"beat {b.get('beat_number')} has empty pov_obstacle"


def test_default_skeleton_uses_at_least_3_interiority_modes():
    plan = {"focal_characters": ["A", "B"], "pov_character": "A"}
    beats = _default_skeleton("standard", chapter_plan=plan)
    modes = {b["interiority_mode"] for b in beats}
    assert len(modes) >= 3, f"default skeleton should rotate interiority modes, saw only: {modes}"


def test_default_skeleton_has_at_least_2_concrete_concessions():
    plan = {"focal_characters": ["A", "B"], "pov_character": "A"}
    beats = _default_skeleton("standard", chapter_plan=plan)
    concrete = [b for b in beats if (b.get("pov_concession") or "").lower() not in {"nothing", "none", "n/a", ""}]
    assert len(concrete) >= 2, f"default skeleton must seed at least 2 concrete concessions, saw {len(concrete)}"


def test_skeleton_system_prompt_teaches_new_fields():
    """The model needs the rule book — every new field must be defined in SKELETON_SYSTEM."""
    for token in (
        "pov_want",
        "pov_obstacle",
        "pov_concession",
        "subtext",
        "interiority_mode",
        "observed_external",
        "free_indirect",
        "direct_thought",
        "suppressed",
    ):
        assert token in SKELETON_SYSTEM, f"SKELETON_SYSTEM missing {token!r}"


# ───── expand_beat injection tests ─────


def _capture_chat(orch: LLMOrchestrator, captured: Dict[str, Any]) -> None:
    def fake_create(**kwargs):
        captured.update(kwargs)
        choice = MagicMock()
        # Return ~enough words to pass the >= 0.5 * expected_words threshold for a beat.
        choice.message.content = " ".join(["word"] * 200)
        choice.finish_reason = "stop"
        resp = MagicMock()
        resp.choices = [choice]
        resp.usage = MagicMock(prompt_tokens=1, completion_tokens=1, total_tokens=2)
        return resp

    orch.client.chat.completions.create = fake_create  # type: ignore[assignment]


def test_expand_beat_injects_interior_architecture(monkeypatch):
    orch = _make_orchestrator(monkeypatch)
    captured: Dict[str, Any] = {}
    _capture_chat(orch, captured)

    beat = {
        "beat_number": 3,
        "action": "Reyes presses Halsey on Tuesday night.",
        "pov_want": "get the truth without tipping his hand",
        "pov_obstacle": "Halsey is a defense lawyer who knows the rules",
        "pov_concession": "admits he found the receipt before reading him his rights",
        "subtext": "he doesn't actually have a warrant for the second receipt",
        "interiority_mode": "free_indirect",
        "info_type": "confrontation",
        "characters_present": ["Detective Reyes", "Halsey"],
        "prose_register": "plain",
        "emotional_temperature": "high",
        "notes": "",
    }

    asyncio.run(expand_beat(
        orchestrator=orch,
        beat=beat,
        chapter_number=4,
        book_bible_excerpt="Police procedural set in Cleveland.",
        character_reference="",
        previous_beats_text="",
        pov_character="Detective Reyes",
    ))

    messages = captured.get("messages", [])
    assert messages, "expand_beat must call the LLM"
    user_prompt = next(m["content"] for m in messages if m["role"] == "user")
    system_prompt = next(m["content"] for m in messages if m["role"] == "system")

    assert "INTERIOR ARCHITECTURE FOR THIS BEAT" in user_prompt
    assert "POV WANT" in user_prompt and "get the truth without tipping his hand" in user_prompt
    assert "POV OBSTACLE" in user_prompt and "defense lawyer" in user_prompt
    assert "POV CONCESSION" in user_prompt and "found the receipt" in user_prompt
    assert "SUBTEXT" in user_prompt and "warrant for the second receipt" in user_prompt
    # Free-indirect interiority instruction must reach the system prompt.
    assert "FREE_INDIRECT" in system_prompt or "free_indirect" in system_prompt.lower()


def test_expand_beat_skips_concession_when_nothing(monkeypatch):
    orch = _make_orchestrator(monkeypatch)
    captured: Dict[str, Any] = {}
    _capture_chat(orch, captured)

    beat = {
        "beat_number": 1,
        "action": "Reyes drives to the scene.",
        "pov_want": "stay focused",
        "pov_obstacle": "the night before is still in his head",
        "pov_concession": "nothing",
        "subtext": "",
        "interiority_mode": "observed_external",
        "info_type": "action",
        "characters_present": ["Detective Reyes"],
        "prose_register": "plain",
        "emotional_temperature": "low",
    }

    asyncio.run(expand_beat(
        orchestrator=orch,
        beat=beat,
        chapter_number=1,
        book_bible_excerpt="",
        character_reference="",
        previous_beats_text="",
        pov_character="Detective Reyes",
        is_first_beat=True,
    ))

    user_prompt = next(m["content"] for m in captured["messages"] if m["role"] == "user")
    system_prompt = next(m["content"] for m in captured["messages"] if m["role"] == "system")

    # Want/obstacle still injected; concession + subtext suppressed (they're "nothing"/"").
    assert "POV WANT" in user_prompt
    assert "POV OBSTACLE" in user_prompt
    assert "POV CONCESSION" not in user_prompt
    assert "SUBTEXT" not in user_prompt
    assert "OBSERVED_EXTERNAL" in system_prompt or "observed_external" in system_prompt.lower()


def test_expand_beat_legacy_beat_no_interior_block(monkeypatch):
    """A beat from a cached pre-P1.1 skeleton must still produce a valid prompt."""
    orch = _make_orchestrator(monkeypatch)
    captured: Dict[str, Any] = {}
    _capture_chat(orch, captured)

    legacy_beat = {
        "beat_number": 1,
        "action": "Old action without new fields.",
        "info_type": "deepening",
        "characters_present": ["Old POV"],
        "prose_register": "plain",
        "emotional_temperature": "medium",
        "notes": "",
    }

    asyncio.run(expand_beat(
        orchestrator=orch,
        beat=legacy_beat,
        chapter_number=1,
        book_bible_excerpt="",
        character_reference="",
        previous_beats_text="",
        pov_character="Old POV",
    ))

    user_prompt = next(m["content"] for m in captured["messages"] if m["role"] == "user")
    # No interior block when no fields supplied — graceful degradation.
    assert "INTERIOR ARCHITECTURE FOR THIS BEAT" not in user_prompt
    # But the basic beat structure is still there.
    assert "BEAT TO WRITE" in user_prompt
    assert "Old action without new fields" in user_prompt
