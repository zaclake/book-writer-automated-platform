#!/usr/bin/env python3
"""Tests for the Path A+ P2.1 per-shape expand_beat system prompts."""

from __future__ import annotations

import asyncio
from typing import Any, Dict
from unittest.mock import MagicMock

from backend.auto_complete.helpers.skeleton_expand import (
    SCENE_SHAPES,
    SHAPE_SYSTEM_PRELUDES,
    expand_beat,
)
from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig


def test_every_scene_shape_has_a_prelude():
    """If a scene_shape exists in SCENE_SHAPES it must have a SYSTEM_PRELUDE."""
    missing = set(SCENE_SHAPES) - set(SHAPE_SYSTEM_PRELUDES.keys())
    assert not missing, f"shapes without preludes: {missing}"


def test_preludes_are_substantial_and_distinct():
    """Each prelude must be substantial (not a stub) and distinct from the others."""
    seen = []
    for shape, prelude in SHAPE_SYSTEM_PRELUDES.items():
        assert len(prelude) > 200, f"prelude for {shape!r} is too short ({len(prelude)} chars)"
        assert "BEAT FRAME" in prelude, f"{shape} prelude missing BEAT FRAME header"
        for other in seen:
            assert prelude != other, f"prelude for {shape!r} duplicates another shape's prelude"
        seen.append(prelude)


def test_preludes_explicitly_override_universal_defaults():
    """Each prelude must mention overriding/replacing universal defaults so the
    drafter doesn't blindly apply the 'open with sensory anchor' boilerplate."""
    for shape, prelude in SHAPE_SYSTEM_PRELUDES.items():
        assert "override" in prelude.lower(), (
            f"prelude for {shape!r} should explicitly state it overrides universal defaults"
        )


def _make_orchestrator(monkeypatch) -> LLMOrchestrator:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    return LLMOrchestrator(
        model="gpt-4.1",
        retry_config=RetryConfig(max_retries=0),
        user_id="test-user",
        enable_billing=False,
    )


def _capture_chat(orch: LLMOrchestrator, captured: Dict[str, Any]) -> None:
    def fake_create(**kwargs):
        captured.update(kwargs)
        choice = MagicMock()
        choice.message.content = " ".join(["word"] * 200)
        choice.finish_reason = "stop"
        resp = MagicMock()
        resp.choices = [choice]
        resp.usage = MagicMock(prompt_tokens=1, completion_tokens=1, total_tokens=2)
        return resp

    orch.client.chat.completions.create = fake_create  # type: ignore[assignment]


def _system_prompt_for_shape(monkeypatch, shape: str) -> str:
    orch = _make_orchestrator(monkeypatch)
    captured: Dict[str, Any] = {}
    _capture_chat(orch, captured)
    beat = {
        "beat_number": 3,
        "action": "Generic action.",
        "scene_shape": shape,
        "characters_present": ["A", "B"],
        "info_type": "deepening",
        "prose_register": "plain",
        "emotional_temperature": "medium",
    }
    asyncio.run(expand_beat(
        orchestrator=orch,
        beat=beat,
        chapter_number=1,
        book_bible_excerpt="",
        character_reference="",
        previous_beats_text="",
        pov_character="A",
    ))
    return next(m["content"] for m in captured["messages"] if m["role"] == "system")


def test_dialogue_pressure_prelude_appears_in_system_prompt(monkeypatch):
    sp = _system_prompt_for_shape(monkeypatch, "dialogue_pressure")
    assert "DIALOGUE PRESSURE" in sp
    assert "OPEN inside a line of dialogue" in sp


def test_kinetic_action_prelude_appears_in_system_prompt(monkeypatch):
    sp = _system_prompt_for_shape(monkeypatch, "kinetic_action")
    assert "KINETIC ACTION" in sp
    assert "physical action verb" in sp.lower()


def test_interior_pressure_prelude_appears_in_system_prompt(monkeypatch):
    sp = _system_prompt_for_shape(monkeypatch, "interior_pressure")
    assert "INTERIOR PRESSURE" in sp
    assert "alone" in sp.lower()


def test_decision_crystallizes_prelude_blocks_narrated_decisions(monkeypatch):
    sp = _system_prompt_for_shape(monkeypatch, "decision_crystallizes")
    assert "DECISION CRYSTALLIZES" in sp
    # The good/bad examples should make it through to teach the drafter.
    assert "decided to" in sp.lower()


def test_revelation_exchange_prelude_demands_reaction(monkeypatch):
    sp = _system_prompt_for_shape(monkeypatch, "revelation_exchange")
    assert "REVELATION EXCHANGE" in sp
    assert "reaction" in sp.lower()


def test_transitional_prelude_keeps_things_short(monkeypatch):
    sp = _system_prompt_for_shape(monkeypatch, "transitional")
    assert "TRANSITIONAL" in sp
    assert "short paragraphs" in sp.lower() or "1-2 short" in sp.lower()


def test_observed_setpiece_prelude_leads_with_what_is_seen(monkeypatch):
    sp = _system_prompt_for_shape(monkeypatch, "observed_setpiece")
    assert "OBSERVED SETPIECE" in sp
    assert "thing being witnessed" in sp.lower() or "lead with" in sp.lower()


def test_unknown_shape_does_not_inject_prelude(monkeypatch):
    sp = _system_prompt_for_shape(monkeypatch, "")
    # No prelude for empty/unknown shape — universal craft block only.
    assert "BEAT FRAME" not in sp


def test_user_prompt_has_concise_shape_marker(monkeypatch):
    """User prompt should carry a one-line SCENE SHAPE marker, not the long hint."""
    orch = _make_orchestrator(monkeypatch)
    captured: Dict[str, Any] = {}
    _capture_chat(orch, captured)
    beat = {
        "beat_number": 1,
        "action": "Generic.",
        "scene_shape": "dialogue_pressure",
        "characters_present": ["A"],
    }
    asyncio.run(expand_beat(
        orchestrator=orch,
        beat=beat,
        chapter_number=1,
        book_bible_excerpt="",
        character_reference="",
        previous_beats_text="",
        pov_character="A",
    ))
    up = next(m["content"] for m in captured["messages"] if m["role"] == "user")
    assert "SCENE SHAPE: dialogue_pressure" in up
    # The old long hint string ("Stay in dialogue. Movement is incidental.") must
    # NOT appear in the user prompt — the system prelude carries it now.
    assert "Movement is incidental" not in up
