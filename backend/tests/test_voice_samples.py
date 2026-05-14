#!/usr/bin/env python3
"""Tests for the Path A+ P2.2 character voice-sample replacement."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock

from backend.auto_complete.helpers.skeleton_expand import (
    build_character_voice_samples,
    expand_beat,
    format_voice_samples_for_beat,
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


# ───── format_voice_samples_for_beat ─────


def test_format_returns_only_speakers_in_beat():
    samples = {
        "Detective Reyes": "Reyes shrugged. " + ("Voice that is recognizably Reyes. " * 4),
        "Halsey": "Halsey lowered his glasses. " + ("Halsey saying things in his way. " * 4),
        "Sasha": "Sasha said something." + (" content. " * 4),
    }
    out = format_voice_samples_for_beat(samples, ["Reyes", "Halsey"])
    assert "Detective Reyes" in out
    assert "Halsey" in out
    assert "Sasha" not in out


def test_format_token_overlap_matches_partial_names():
    """Reyes in the beat list should match 'Detective Reyes' in the samples dict."""
    samples = {"Detective Reyes": "Reyes leaned back. " + ("padding paragraph that explains how he sounds. " * 3)}
    out = format_voice_samples_for_beat(samples, ["Reyes"])
    assert "Detective Reyes" in out


def test_format_returns_empty_when_no_match():
    samples = {"Reyes": "Reyes content here that is long enough to count as a sample paragraph at all."}
    assert format_voice_samples_for_beat(samples, ["Halsey"]) == ""


def test_format_returns_empty_when_no_speakers_in_beat():
    samples = {"Reyes": "Sample content that is plenty long enough."}
    assert format_voice_samples_for_beat(samples, []) == ""


def test_format_caps_at_max_chars():
    big = "X" * 800
    samples = {f"C{i}": big for i in range(5)}
    out = format_voice_samples_for_beat(samples, [f"C{i}" for i in range(5)], max_chars=1500)
    # Should pick first ~2 samples and stop before 5*800.
    assert len(out) <= 2200  # header + 2 samples + spacing
    assert "C0" in out


# ───── build_character_voice_samples (mocked LLM) ─────


def _fake_chat_response(content_str: str):
    """Build a fake response with .choices but no .output_text.

    The orchestrator first checks `hasattr(response, "output_text")`; a bare
    MagicMock would auto-create that attribute, making the orchestrator pull a
    MagicMock as the content. We use a real object instead to keep both code
    paths honest.
    """

    class _Msg:
        def __init__(self, content: str) -> None:
            self.content = content

    class _Choice:
        def __init__(self, content: str) -> None:
            self.message = _Msg(content)
            self.finish_reason = "stop"

    class _Usage:
        prompt_tokens = 1
        completion_tokens = 1
        total_tokens = 2

    class _Resp:
        def __init__(self, content: str) -> None:
            self.choices = [_Choice(content)]
            self.usage = _Usage()

    return _Resp(content_str)


def test_build_voice_samples_parses_json_and_caches(monkeypatch, tmp_path):
    orch = _make_orchestrator(monkeypatch)

    fake_json = {
        "samples": {
            "Reyes": "Reyes leaned back, hands behind his head. \"Let me ask you something simpler.\"",
            "Halsey": "\"You'll need a warrant for that,\" Halsey said. He didn't look up.",
        }
    }

    def fake_create(**kwargs):
        return _fake_chat_response(json.dumps(fake_json))

    orch.client.chat.completions.create = fake_create  # type: ignore[assignment]

    char_ref = "## Reyes\nDetective.\n## Halsey\nDefense lawyer.\n" + ("padding text " * 30)

    samples = asyncio.run(build_character_voice_samples(orch, char_ref, project_path=str(tmp_path)))
    assert set(samples.keys()) == {"Reyes", "Halsey"}
    assert "warrant" in samples["Halsey"]

    # Cache should be written and version-tagged.
    cache = json.loads((tmp_path / ".project-state" / "voice-profiles.json").read_text())
    assert cache["version"] == 2
    assert isinstance(cache["samples"], dict)
    assert cache["samples"] == samples


def test_build_voice_samples_uses_planner_tier(monkeypatch, tmp_path):
    """Sample building is craft-heavy work — must route through planner tier."""
    orch = _make_orchestrator(monkeypatch)
    captured: Dict[str, Any] = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        body = json.dumps({"samples": {"A": "A speaks like this. " + ("Plenty here. " * 4)}})
        return _fake_chat_response(body)

    orch.client.chat.completions.create = fake_create  # type: ignore[assignment]

    char_ref = "## A\nCharacter A is a thoughtful person.\n" + ("padding " * 30)
    asyncio.run(build_character_voice_samples(orch, char_ref, project_path=str(tmp_path)))
    assert captured.get("model") == "gpt-5.2-pro", "voice sample call must use planner model"


def test_build_voice_samples_invalidates_old_v1_cache(monkeypatch, tmp_path):
    """A v1 (text-block) cache should NOT short-circuit the v2 fetch."""
    orch = _make_orchestrator(monkeypatch)

    state = tmp_path / ".project-state"
    state.mkdir(parents=True)
    (state / "voice-profiles.json").write_text(json.dumps({
        "ref_hash": "deadbeefdeadbeef",
        "profiles": "OLD V1 RULES TEXT",  # v1 schema
    }))

    fake_json = {"samples": {"A": "A speaks. " + ("Plenty of demonstration here for the test. " * 3)}}

    called = {"n": 0}

    def fake_create(**kwargs):
        called["n"] += 1
        return _fake_chat_response(json.dumps(fake_json))

    orch.client.chat.completions.create = fake_create  # type: ignore[assignment]

    samples = asyncio.run(build_character_voice_samples(orch, "deadbeefdeadbeef" * 20, project_path=str(tmp_path)))
    assert called["n"] == 1, "old v1 cache must be ignored and a fresh build triggered"
    assert "A" in samples


# ───── expand_beat consumes samples ─────


def _capture_chat(orch: LLMOrchestrator, captured: Dict[str, Any]) -> None:
    def fake_create(**kwargs):
        captured.update(kwargs)
        return _fake_chat_response(" ".join(["word"] * 200))

    orch.client.chat.completions.create = fake_create  # type: ignore[assignment]


def test_expand_beat_injects_only_speaking_characters_voice(monkeypatch):
    orch = _make_orchestrator(monkeypatch)
    captured: Dict[str, Any] = {}
    _capture_chat(orch, captured)

    samples = {
        "Reyes": "Reyes leaned back, hands behind his head. \"Let me ask you something simpler.\" He waited.",
        "Halsey": "\"You'll need a warrant,\" Halsey said. He didn't look up. The cuff of his shirt was perfect.",
        "Sasha (cat)": "Sasha purred and pushed her head against his hand.",
    }

    beat = {
        "beat_number": 5,
        "action": "Reyes presses Halsey.",
        "characters_present": ["Reyes", "Halsey"],
        "scene_shape": "dialogue_pressure",
    }

    asyncio.run(expand_beat(
        orchestrator=orch,
        beat=beat,
        chapter_number=1,
        book_bible_excerpt="",
        character_reference="",
        previous_beats_text="",
        pov_character="Reyes",
        voice_samples_by_character=samples,
    ))

    user_prompt = next(m["content"] for m in captured["messages"] if m["role"] == "user")
    # Speakers in this beat get their samples.
    assert "Reyes — voice sample" in user_prompt
    assert "Halsey — voice sample" in user_prompt
    # Non-speakers (Sasha) do NOT get their sample injected — and certainly not
    # the cat's "voice".
    assert "Sasha" not in user_prompt
    # No legacy rule block when samples are present.
    assert "CHARACTER VOICE PROFILES" not in user_prompt


def test_expand_beat_falls_back_to_legacy_when_no_samples(monkeypatch):
    orch = _make_orchestrator(monkeypatch)
    captured: Dict[str, Any] = {}
    _capture_chat(orch, captured)

    beat = {
        "beat_number": 1,
        "action": "Generic.",
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
        character_voice_profiles="LEGACY VOICE RULE TEXT",
        voice_samples_by_character=None,
    ))

    user_prompt = next(m["content"] for m in captured["messages"] if m["role"] == "user")
    # Legacy block lands when samples are unavailable.
    assert "CHARACTER VOICE PROFILES" in user_prompt
    assert "LEGACY VOICE RULE TEXT" in user_prompt


def test_expand_beat_prefers_samples_over_legacy_when_both_passed(monkeypatch):
    orch = _make_orchestrator(monkeypatch)
    captured: Dict[str, Any] = {}
    _capture_chat(orch, captured)

    samples = {"A": "A speaks like this in their own way. " * 5}
    beat = {
        "beat_number": 1,
        "action": "Generic.",
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
        character_voice_profiles="LEGACY RULES",
        voice_samples_by_character=samples,
    ))

    user_prompt = next(m["content"] for m in captured["messages"] if m["role"] == "user")
    # Samples win; legacy rule text must NOT also be injected.
    assert "voice sample" in user_prompt
    assert "LEGACY RULES" not in user_prompt
