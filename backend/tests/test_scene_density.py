"""Tests for scene-density discipline (Proposal 7)."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from backend.auto_complete.helpers.skeleton_expand import (
    validate_scene_density,
    validate_skeleton_variety,
)


def _beat(
    *,
    n: int,
    scene_id: int,
    transition: str = "scene_continue",
    characters: List[str] | None = None,
    time_of_day: str = "morning",
    scene_shape: str = "dialogue_pressure",
    interiority_mode: str = "free_indirect",
) -> Dict[str, Any]:
    return {
        "beat_number": n,
        "scene_id": scene_id,
        "scene_transition": transition,
        "characters_present": characters or ["A", "B"],
        "time_of_day": time_of_day,
        "scene_shape": scene_shape,
        "interiority_mode": interiority_mode,
    }


def test_clean_skeleton_passes_density_check():
    beats = [
        _beat(n=1, scene_id=1, transition="scene_open", time_of_day="morning"),
        _beat(n=2, scene_id=1, time_of_day="morning"),
        _beat(n=3, scene_id=1, transition="scene_close", time_of_day="morning"),
        _beat(n=4, scene_id=2, transition="scene_open", time_of_day="afternoon"),
        _beat(n=5, scene_id=2, time_of_day="afternoon"),
        _beat(n=6, scene_id=2, transition="scene_close", time_of_day="afternoon"),
        _beat(n=7, scene_id=3, transition="scene_open", time_of_day="evening"),
        _beat(n=8, scene_id=3, transition="scene_close", time_of_day="evening"),
    ]
    report = validate_scene_density(beats)
    assert report["ok"], report
    assert report["distinct_scenes"] == [1, 2, 3]
    assert report["missing_scene_id_count"] == 0


def test_montage_chapter_is_flagged():
    beats = [
        _beat(n=i, scene_id=i, transition="scene_open" if i == 1 else "scene_open")
        for i in range(1, 9)
    ]
    report = validate_scene_density(beats)
    assert not report["ok"]
    assert any("montage" in issue for issue in report["issues"])


def test_recursive_entries_flagged():
    """Sam enters scene 1 → leaves → returns → leaves → returns. Two re-entries."""
    beats = [
        _beat(n=1, scene_id=1, transition="scene_open", characters=["A", "Sam"]),
        _beat(n=2, scene_id=1, characters=["A"]),  # Sam leaves
        _beat(n=3, scene_id=1, characters=["A", "Sam"]),  # Sam returns (entry 1)
        _beat(n=4, scene_id=1, characters=["A"]),  # Sam leaves again
        _beat(n=5, scene_id=1, characters=["A", "Sam"]),  # Sam returns (entry 2)
        _beat(n=6, scene_id=1, transition="scene_close", characters=["A", "Sam"]),
    ]
    report = validate_scene_density(beats)
    assert not report["ok"]
    assert any("Sam" in issue and "enters" in issue for issue in report["issues"])


def test_single_re_entry_is_allowed():
    """Sam enters → leaves → returns once. That's allowed."""
    beats = [
        _beat(n=1, scene_id=1, transition="scene_open", characters=["A", "Sam"]),
        _beat(n=2, scene_id=1, characters=["A"]),
        _beat(n=3, scene_id=1, characters=["A", "Sam"]),  # one re-entry
        _beat(n=4, scene_id=1, transition="scene_close", characters=["A", "Sam"]),
    ]
    report = validate_scene_density(beats)
    # No "Sam enters" issue should be raised for a single re-entry.
    assert not any("Sam" in issue and "enters" in issue for issue in report["issues"])


def test_time_jump_within_scene_is_flagged():
    beats = [
        _beat(n=1, scene_id=1, transition="scene_open", time_of_day="morning"),
        _beat(n=2, scene_id=1, time_of_day="evening"),  # bad — time jumped within scene
        _beat(n=3, scene_id=1, transition="scene_close", time_of_day="evening"),
    ]
    report = validate_scene_density(beats)
    assert any("time_of_day shifts" in issue for issue in report["issues"])


def test_time_jump_across_scenes_is_fine():
    beats = [
        _beat(n=1, scene_id=1, transition="scene_open", time_of_day="morning"),
        _beat(n=2, scene_id=1, transition="scene_close", time_of_day="morning"),
        _beat(n=3, scene_id=2, transition="scene_open", time_of_day="evening"),
        _beat(n=4, scene_id=2, transition="scene_close", time_of_day="evening"),
    ]
    report = validate_scene_density(beats)
    assert report["ok"], report["issues"]


def test_missing_scene_id_is_reported():
    beats = [
        {"beat_number": 1, "scene_transition": "scene_open", "characters_present": ["A"], "time_of_day": "morning"},
        {"beat_number": 2, "scene_transition": "scene_close", "characters_present": ["A"], "time_of_day": "morning"},
    ]
    report = validate_scene_density(beats)
    assert report["missing_scene_id_count"] == 2
    assert any("scene_id missing" in issue for issue in report["issues"])


def test_first_beat_should_open_a_scene():
    beats = [
        _beat(n=1, scene_id=1, transition="scene_continue"),
        _beat(n=2, scene_id=1, transition="scene_close"),
    ]
    report = validate_scene_density(beats)
    assert any("first beat" in issue for issue in report["issues"])


def test_validate_skeleton_variety_includes_density():
    """The umbrella validator should expose the scene_density sub-report."""
    beats = [
        _beat(
            n=i,
            scene_id=1,
            transition="scene_open" if i == 1 else "scene_continue" if i < 8 else "scene_close",
            scene_shape=("dialogue_pressure" if i % 3 == 0 else "interior_pressure" if i % 3 == 1 else "kinetic_action"),
            interiority_mode=("free_indirect" if i % 3 == 0 else "direct_thought" if i % 3 == 1 else "observed_external"),
        )
        for i in range(1, 9)
    ]
    report = validate_skeleton_variety(beats)
    assert "scene_density" in report
    assert isinstance(report["scene_density"], dict)
