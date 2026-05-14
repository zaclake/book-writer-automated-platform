#!/usr/bin/env python3
"""Tests for the Path A+ P1.4 per-scene continuity guard."""

from __future__ import annotations

import asyncio
from typing import Any, Dict
from unittest.mock import MagicMock

from backend.auto_complete.helpers.scene_state_ledger import (
    CharacterState,
    SceneStateLedger,
    _classify_species,
)
from backend.auto_complete.helpers.skeleton_expand import expand_beat
from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig


# ───── Species classifier ─────


def test_classify_species_humans_default():
    assert _classify_species("Detective Reyes", "") == "human"
    assert _classify_species("Halsey", "Halsey is a defense attorney.") == "human"


def test_classify_species_detects_animal_in_profile_section():
    char_ref = (
        "## Sasha\n"
        "Sasha is an orange tabby cat who follows Reyes around the precinct.\n"
        "Always purring, never far from a sunbeam.\n"
    )
    assert _classify_species("Sasha", char_ref) == "animal"


def test_classify_species_detects_object_in_profile():
    char_ref = (
        "## ARIA\n"
        "ARIA is the AI assistant aboard the ship — a computer with a calm female voice.\n"
    )
    assert _classify_species("ARIA", char_ref) == "object"


def test_classify_species_proximity_fallback():
    """Even with no proper section, a sentence linking name + animal noun should classify."""
    char_ref = "The dog Wolfgang stayed by the door, watchful."
    assert _classify_species("Wolfgang", char_ref) == "animal"


# ───── Ledger seeding ─────


def test_from_chapter_plan_seeds_focal_and_pov():
    plan = {
        "focal_characters": ["Reyes", "Halsey", "Sasha"],
        "pov_character": "Reyes",
    }
    char_ref = "## Sasha\nSasha is the precinct cat, all tabby and indignation.\n"
    ledger = SceneStateLedger.from_chapter_plan(plan, character_reference=char_ref)
    names = set(ledger.known_names())
    assert names == {"Reyes", "Halsey", "Sasha"}
    assert ledger.get("Sasha").species == "animal"
    assert ledger.get("Reyes").species == "human"


def test_chapter_starts_with_no_one_on_stage():
    plan = {"focal_characters": ["A", "B"], "pov_character": "A"}
    ledger = SceneStateLedger.from_chapter_plan(plan)
    assert ledger.on_stage_names() == []


# ───── State guard prompt ─────


def test_build_state_guard_lists_target_on_stage_and_animals():
    plan = {"focal_characters": ["Reyes", "Halsey", "Sasha"], "pov_character": "Reyes"}
    char_ref = "## Sasha\nSasha is a black cat, the precinct mascot.\n"
    ledger = SceneStateLedger.from_chapter_plan(plan, character_reference=char_ref)

    beat = {
        "beat_number": 1,
        "characters_present": ["Reyes", "Halsey"],
        "action": "Reyes opens the interrogation.",
    }
    guard = ledger.build_state_guard(beat)
    assert "SCENE STATE GUARD" in guard
    assert "TARGET ON STAGE" in guard
    assert "Reyes" in guard and "Halsey" in guard
    assert "ANIMALS / OBJECTS" in guard
    assert "Sasha" in guard
    assert "NEVER produce dialogue" in guard


def test_build_state_guard_flags_leaving_characters():
    plan = {"focal_characters": ["A", "B", "C"], "pov_character": "A"}
    ledger = SceneStateLedger.from_chapter_plan(plan)
    # Mark A and B on stage from a previous beat.
    ledger.update_from_beat({"beat_number": 1, "characters_present": ["A", "B"]}, beat_text="A and B talked.")
    # Next beat: only A is on stage.
    next_beat = {"beat_number": 2, "characters_present": ["A"]}
    guard = ledger.build_state_guard(next_beat)
    assert "LEAVING the scene" in guard
    assert "B" in guard


# ───── update_from_beat ─────


def test_update_marks_characters_on_and_off_stage():
    plan = {"focal_characters": ["A", "B", "C"], "pov_character": "A"}
    ledger = SceneStateLedger.from_chapter_plan(plan)
    ledger.update_from_beat(
        {"beat_number": 1, "characters_present": ["A", "B"]},
        beat_text="A walked into the room. B was already there.",
    )
    assert ledger.get("A").on_stage is True
    assert ledger.get("B").on_stage is True
    assert ledger.get("C").on_stage is False
    # Move forward: A leaves, C enters.
    ledger.update_from_beat(
        {"beat_number": 2, "characters_present": ["B", "C"]},
        beat_text="C arrived and sat near B.",
    )
    assert ledger.get("A").on_stage is False
    assert ledger.get("A").last_seen_beat == 1
    assert ledger.get("B").on_stage is True
    assert ledger.get("C").on_stage is True


# ───── validate_beat_speakers ─────


def test_validate_flags_animal_speaking():
    plan = {"focal_characters": ["Reyes", "Sasha"], "pov_character": "Reyes"}
    char_ref = "## Sasha\nSasha is a cat. She purrs constantly.\n"
    ledger = SceneStateLedger.from_chapter_plan(plan, character_reference=char_ref)
    ledger.update_from_beat({"beat_number": 1, "characters_present": ["Reyes", "Sasha"]}, "")

    beat = {"beat_number": 2, "characters_present": ["Reyes", "Sasha"]}
    text = '"You should have closed the door," Sasha said, jumping onto the desk.'
    warnings = ledger.validate_beat_speakers(text, beat)
    assert any("Sasha" in w and "animal" in w.lower() for w in warnings), warnings


def test_validate_flags_off_stage_speaker():
    plan = {"focal_characters": ["A", "B"], "pov_character": "A"}
    ledger = SceneStateLedger.from_chapter_plan(plan)
    # B was on stage in beat 1, off stage now.
    ledger.update_from_beat({"beat_number": 1, "characters_present": ["A", "B"]}, "")
    ledger.update_from_beat({"beat_number": 2, "characters_present": ["A"]}, "")

    beat = {"beat_number": 3, "characters_present": ["A"]}
    text = '"Don\'t do it," B said from somewhere unseen.'
    warnings = ledger.validate_beat_speakers(text, beat)
    assert any("B" in w and ("off-stage" in w.lower() or "ghost" in w.lower() or "off stage" in w.lower()) for w in warnings), warnings


def test_validate_clean_human_dialogue_no_warnings():
    plan = {"focal_characters": ["A", "B"], "pov_character": "A"}
    ledger = SceneStateLedger.from_chapter_plan(plan)
    ledger.update_from_beat({"beat_number": 1, "characters_present": ["A", "B"]}, "")

    beat = {"beat_number": 2, "characters_present": ["A", "B"]}
    text = '"Where were you?" A asked.\n"At home," B replied.'
    warnings = ledger.validate_beat_speakers(text, beat)
    assert warnings == [], warnings


def test_validate_handles_animal_sound_verbs_silently():
    """Sasha 'meowed' is fine — only human speech verbs trigger the warning."""
    plan = {"focal_characters": ["Reyes", "Sasha"], "pov_character": "Reyes"}
    char_ref = "## Sasha\nSasha is the office cat.\n"
    ledger = SceneStateLedger.from_chapter_plan(plan, character_reference=char_ref)
    ledger.update_from_beat({"beat_number": 1, "characters_present": ["Reyes", "Sasha"]}, "")

    beat = {"beat_number": 2, "characters_present": ["Reyes", "Sasha"]}
    # Sasha meows or purrs — this is sound, not dialogue, no warning.
    text = "Sasha meowed and arched against the chair leg."
    warnings = ledger.validate_beat_speakers(text, beat)
    assert warnings == [], warnings


def test_validate_ignores_narration_without_quotes():
    """Naked narration like 'Air hissed' must NOT be flagged as fabricated speaker.

    Regression: prior regex made the quoted span optional and used IGNORECASE,
    which caused noun-phrase + speech-verb constructions in pure narration
    ('Air hissed', 'the wind answered', 'cooling fans whined') to fire as
    ghost-speaker warnings. The validator now requires a real quoted span in
    the same paragraph before considering any attribution.
    """
    plan = {"focal_characters": ["Maya"], "pov_character": "Maya"}
    ledger = SceneStateLedger.from_chapter_plan(plan)
    ledger.update_from_beat({"beat_number": 1, "characters_present": ["Maya"]}, "")

    beat = {"beat_number": 2, "characters_present": ["Maya"]}
    text = (
        "Air hissed into the hush of Galileo Station. "
        "The wind answered with its own thin music, and Maya kept walking. "
        "Cooling fans whined behind the bulkhead, then settled. "
        "Steam drifted off the clarifier."
    )
    warnings = ledger.validate_beat_speakers(text, beat)
    assert warnings == [], warnings


def test_validate_still_flags_real_fabricated_speaker():
    """Even with the false-positive fix, a quoted line attributed to an unknown
    character name must still produce a warning."""
    plan = {"focal_characters": ["Ruth"], "pov_character": "Ruth"}
    ledger = SceneStateLedger.from_chapter_plan(plan)
    ledger.update_from_beat({"beat_number": 1, "characters_present": ["Ruth"]}, "")

    beat = {"beat_number": 2, "characters_present": ["Ruth"]}
    # 'Vernon' is not in the ledger and not in beat_chars — should warn.
    text = '"Stop where you are," Vernon said from the doorway.'
    warnings = ledger.validate_beat_speakers(text, beat)
    assert any("Vernon" in w and "fabricated" in w.lower() for w in warnings), warnings


def test_validate_handles_reverse_attribution_with_quote():
    """`"Stop," said Maya.` must still be parseable when Maya is on stage
    (no warning), and `"Stop," said Vernon.` (Vernon unknown) must warn."""
    plan = {"focal_characters": ["Maya"], "pov_character": "Maya"}
    ledger = SceneStateLedger.from_chapter_plan(plan)
    ledger.update_from_beat({"beat_number": 1, "characters_present": ["Maya"]}, "")

    beat = {"beat_number": 2, "characters_present": ["Maya"]}
    clean = '"I will check the logs," said Maya, hands steady on the console.'
    assert ledger.validate_beat_speakers(clean, beat) == []

    dirty = '"You should not be here," said Vernon, voice flat.'
    warnings = ledger.validate_beat_speakers(dirty, beat)
    assert any("Vernon" in w for w in warnings), warnings


def test_validate_skips_determiner_led_noun_phrases():
    """`"Hello?" No one answered.` and `"Cut it," The fryer hissed.` must not
    flag 'No one' or 'The fryer' as speakers — these are narration with the
    speech verb attached to a determiner-led noun phrase, not real attributions.
    """
    plan = {"focal_characters": ["Nero"], "pov_character": "Nero"}
    ledger = SceneStateLedger.from_chapter_plan(plan)
    ledger.update_from_beat({"beat_number": 1, "characters_present": ["Nero"]}, "")

    beat = {"beat_number": 2, "characters_present": ["Nero"]}
    text = (
        '"Hello?" Nero called into the dark of the plant. No one answered. '
        '"Cut it," he muttered. The fryer hissed back from the corner kitchen, '
        'angry and indifferent, before the breaker tripped and the room went dim.'
    )
    warnings = ledger.validate_beat_speakers(text, beat)
    # "Nero called" is fine (Nero on stage). "No one answered" and "The fryer
    # hissed" must NOT be flagged.
    assert not any("No one" in w for w in warnings), warnings
    assert not any("fryer" in w.lower() for w in warnings), warnings


def test_validate_skips_adverb_second_word_misparses():
    """`"X," Lou always said` and `"X," Mary suddenly added` must not flag
    'Lou always' / 'Mary suddenly' as fabricated speakers — these are real
    speakers (Lou / Mary) where the regex captured an adverb continuation."""
    plan = {"focal_characters": ["Lou", "Mary"], "pov_character": "Lou"}
    ledger = SceneStateLedger.from_chapter_plan(plan)
    ledger.update_from_beat({"beat_number": 1, "characters_present": ["Lou", "Mary"]}, "")

    beat = {"beat_number": 2, "characters_present": ["Lou", "Mary"]}
    text = (
        '"You stay close to the truck," Lou always said when the headlights came on. '
        '"Not tonight," Mary suddenly answered, the words sharp.'
    )
    warnings = ledger.validate_beat_speakers(text, beat)
    assert not any("Lou always" in w for w in warnings), warnings
    assert not any("Mary suddenly" in w for w in warnings), warnings


def test_validate_skips_calendar_personification():
    """Months, weekdays, seasons, and similar capitalized-but-not-name common
    nouns ('"X," October said' as personification) must NOT be flagged as
    fabricated speakers. Real defect: literary-cycle1 ch2 beat 4 flagged
    'October' because the model wrote `"...the harvest is late," October
    said in its quiet, dry voice.`"""
    plan = {"focal_characters": ["Ruth", "Mitch"], "pov_character": "Ruth"}
    ledger = SceneStateLedger.from_chapter_plan(plan)
    ledger.update_from_beat(
        {"beat_number": 1, "characters_present": ["Ruth"]}, ""
    )

    beat = {"beat_number": 2, "characters_present": ["Ruth"]}
    text = (
        '"That\u2019s how it is," October said, in its quiet, dry voice.\n\n'
        '"Slower than usual," Tuesday murmured, the wind agreeing.\n\n'
        '"Wait for the rain," Autumn answered.\n\n'
    )
    warnings = ledger.validate_beat_speakers(text, beat)
    for nope in ("October", "Tuesday", "Autumn"):
        assert not any(nope in w for w in warnings), (
            f"calendar/season name {nope} must not be flagged: {warnings}"
        )


# ───── expand_beat plumbing ─────


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


def test_expand_beat_injects_scene_state_guard(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    orch = LLMOrchestrator(
        model="gpt-4.1",
        retry_config=RetryConfig(max_retries=0),
        user_id="test-user",
        enable_billing=False,
    )
    captured: Dict[str, Any] = {}
    _capture_chat(orch, captured)

    plan = {"focal_characters": ["Reyes", "Sasha"], "pov_character": "Reyes"}
    char_ref = "## Sasha\nSasha is a cat.\n"
    ledger = SceneStateLedger.from_chapter_plan(plan, character_reference=char_ref)
    beat = {"beat_number": 1, "action": "Reyes enters", "characters_present": ["Reyes"]}
    guard = ledger.build_state_guard(beat)

    asyncio.run(expand_beat(
        orchestrator=orch,
        beat=beat,
        chapter_number=1,
        book_bible_excerpt="",
        character_reference=char_ref,
        previous_beats_text="",
        pov_character="Reyes",
        scene_state_guard=guard,
    ))

    user_prompt = next(m["content"] for m in captured["messages"] if m["role"] == "user")
    assert "SCENE STATE GUARD" in user_prompt
    assert "Sasha" in user_prompt
    assert "NEVER produce dialogue" in user_prompt
