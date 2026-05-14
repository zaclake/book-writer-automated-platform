#!/usr/bin/env python3
"""Tests for the Path A+ P1.2 scene-shape and chapter-shape variety budgets."""

from __future__ import annotations

from backend.auto_complete.helpers.skeleton_expand import (
    SCENE_SHAPES,
    SKELETON_SYSTEM,
    CHAPTER_SHAPE_TO_SCENE_MIX,
    _default_skeleton,
    validate_skeleton_variety,
)


# ───── Vocabulary / mapping ─────


def test_scene_shapes_are_canonical_set():
    expected = {
        "dialogue_pressure",
        "kinetic_action",
        "interior_pressure",
        "observed_setpiece",
        "decision_crystallizes",
        "revelation_exchange",
        "transitional",
    }
    assert set(SCENE_SHAPES) == expected


def test_every_chapter_shape_has_scene_mix():
    """Every chapter_shape that the book-plan generator emits must have a scene_shape palette."""
    book_plan_chapter_shapes = {
        "quiet_character_focus",
        "confrontation_dialogue",
        "aftermath_processing",
        "relationship_deepening",
        "world_building_routine",
        "tension_escalation",
        "revelation_and_fallout",
        "journey_transition",
    }
    missing = book_plan_chapter_shapes - set(CHAPTER_SHAPE_TO_SCENE_MIX.keys())
    assert not missing, f"chapter_shape values missing scene_shape palette: {missing}"


def test_skeleton_system_prompt_teaches_scene_shape_rules():
    for token in (
        "scene_shape",
        "dialogue_pressure",
        "kinetic_action",
        "interior_pressure",
        "observed_setpiece",
        "decision_crystallizes",
        "revelation_exchange",
        "transitional",
        "at least 3 distinct scene_shapes",
    ):
        assert token in SKELETON_SYSTEM, f"SKELETON_SYSTEM missing {token!r}"


# ───── _default_skeleton: scene_shape population ─────


def test_default_skeleton_populates_scene_shape_for_every_beat():
    plan = {
        "focal_characters": ["A", "B"],
        "pov_character": "A",
        "chapter_shape": "confrontation_dialogue",
    }
    beats = _default_skeleton("standard", chapter_plan=plan)
    for b in beats:
        assert "scene_shape" in b, f"beat {b.get('beat_number')} missing scene_shape"
        assert b["scene_shape"] in SCENE_SHAPES, (
            f"beat {b.get('beat_number')} has unknown scene_shape {b['scene_shape']!r}"
        )


def test_default_skeleton_uses_chapter_shape_palette():
    plan = {"focal_characters": ["A"], "pov_character": "A", "chapter_shape": "tension_escalation"}
    beats = _default_skeleton("standard", chapter_plan=plan)
    palette = set(CHAPTER_SHAPE_TO_SCENE_MIX["tension_escalation"])
    used = {b["scene_shape"] for b in beats}
    # Most beats should land inside the palette (allow drift via the dedup rule).
    in_palette = used & palette
    assert in_palette, f"default skeleton ignored chapter_shape palette: used={used}, palette={palette}"


def test_default_skeleton_avoids_two_consecutive_same_scene_shape():
    plan = {"focal_characters": ["A"], "pov_character": "A", "chapter_shape": "quiet_character_focus"}
    beats = _default_skeleton("standard", chapter_plan=plan)
    for prev, curr in zip(beats, beats[1:]):
        assert prev["scene_shape"] != curr["scene_shape"], (
            f"default skeleton placed same scene_shape {prev['scene_shape']!r} on consecutive beats "
            f"{prev['beat_number']} and {curr['beat_number']}"
        )


def test_default_skeleton_uses_at_least_3_scene_shapes():
    plan = {"focal_characters": ["A"], "pov_character": "A", "chapter_shape": "balanced"}
    beats = _default_skeleton("standard", chapter_plan=plan)
    distinct = {b["scene_shape"] for b in beats}
    assert len(distinct) >= 3, f"default skeleton too monotone: {distinct}"


# ───── validate_skeleton_variety ─────


def test_validate_flags_monotone_scene_shape():
    beats = [{"beat_number": i, "scene_shape": "interior_pressure", "interiority_mode": "free_indirect"} for i in range(8)]
    report = validate_skeleton_variety(beats)
    assert not report["ok"]
    issues = " ".join(report["issues"])
    assert "scene_shape" in issues


def test_validate_flags_consecutive_scene_shape_run():
    # 3 in a row of dialogue_pressure should trip the consecutive-run check.
    beats = [
        {"beat_number": 1, "scene_shape": "kinetic_action", "interiority_mode": "observed_external"},
        {"beat_number": 2, "scene_shape": "dialogue_pressure", "interiority_mode": "free_indirect"},
        {"beat_number": 3, "scene_shape": "dialogue_pressure", "interiority_mode": "direct_thought"},
        {"beat_number": 4, "scene_shape": "dialogue_pressure", "interiority_mode": "free_indirect"},
        {"beat_number": 5, "scene_shape": "interior_pressure", "interiority_mode": "suppressed"},
        {"beat_number": 6, "scene_shape": "decision_crystallizes", "interiority_mode": "direct_thought"},
        {"beat_number": 7, "scene_shape": "revelation_exchange", "interiority_mode": "observed_external"},
    ]
    report = validate_skeleton_variety(beats)
    assert not report["ok"]
    assert any("dialogue_pressure" in issue for issue in report["issues"])


def test_validate_passes_for_well_balanced_skeleton():
    beats = [
        {"beat_number": 1, "scene_shape": "kinetic_action", "interiority_mode": "observed_external"},
        {"beat_number": 2, "scene_shape": "dialogue_pressure", "interiority_mode": "free_indirect"},
        {"beat_number": 3, "scene_shape": "interior_pressure", "interiority_mode": "direct_thought"},
        {"beat_number": 4, "scene_shape": "revelation_exchange", "interiority_mode": "observed_external"},
        {"beat_number": 5, "scene_shape": "dialogue_pressure", "interiority_mode": "suppressed"},
        {"beat_number": 6, "scene_shape": "decision_crystallizes", "interiority_mode": "direct_thought"},
        {"beat_number": 7, "scene_shape": "interior_pressure", "interiority_mode": "free_indirect"},
        {"beat_number": 8, "scene_shape": "dialogue_pressure", "interiority_mode": "observed_external"},
    ]
    report = validate_skeleton_variety(beats)
    assert report["ok"], f"expected balanced skeleton to pass, got issues: {report['issues']}"
    assert len(report["distinct_shapes"]) >= 3
    assert len(report["distinct_interiority"]) >= 3


def test_validate_handles_empty_skeleton():
    report = validate_skeleton_variety([])
    assert not report["ok"]
    assert "empty" in report["issues"][0].lower()
