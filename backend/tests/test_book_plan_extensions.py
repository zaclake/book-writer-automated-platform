"""Tests for the book plan extensions (Proposals 2, 4, 5).

Covers ``_backfill_plan_extensions`` and ``save_promises_ledger`` on
``BookPlanGenerator``. We exercise the helpers directly without making any
LLM calls so the test suite stays fast and deterministic.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.auto_complete.helpers.book_plan_generator import BookPlanGenerator


def _make_plan(thematic_moves=None, tiers=None, num=4):
    chapters = []
    for i in range(num):
        chapters.append({
            "chapter_number": i + 1,
            "title": f"Chapter {i + 1}",
            "summary": "summary",
            "objectives": [],
            "chapter_tier": (tiers[i] if tiers else None),
            "thematic_move": (thematic_moves[i] if thematic_moves else None),
        })
    return {"chapters": chapters}


def test_backfill_assigns_defaults_for_missing_fields(tmp_path):
    gen = BookPlanGenerator(project_path=str(tmp_path))
    plan = _make_plan()
    out = gen._backfill_plan_extensions(plan)
    for chapter in out["chapters"]:
        assert chapter["chapter_tier"] in BookPlanGenerator._ALLOWED_CHAPTER_TIERS
        assert chapter["thematic_move"] in BookPlanGenerator._ALLOWED_THEMATIC_MOVES
        assert isinstance(chapter["promises_planted"], list)
        assert isinstance(chapter["promises_paid"], list)
        assert isinstance(chapter["thematic_move_note"], str)
    assert isinstance(out["promises_ledger"], list)


def test_backfill_normalizes_invalid_tier_and_move(tmp_path):
    gen = BookPlanGenerator(project_path=str(tmp_path))
    plan = _make_plan(thematic_moves=["bogus"] * 4, tiers=["nonsense"] * 4)
    out = gen._backfill_plan_extensions(plan)
    for chapter in out["chapters"]:
        assert chapter["chapter_tier"] == "development"
        assert chapter["thematic_move"] in BookPlanGenerator._ALLOWED_THEMATIC_MOVES


def test_backfill_breaks_adjacent_duplicate_thematic_moves(tmp_path):
    gen = BookPlanGenerator(project_path=str(tmp_path))
    plan = _make_plan(thematic_moves=["deepen"] * 4)
    out = gen._backfill_plan_extensions(plan)
    moves = [c["thematic_move"] for c in out["chapters"]]
    for i in range(1, len(moves)):
        assert moves[i] != moves[i - 1], (
            f"Adjacent thematic_move duplicate after backfill: {moves}"
        )


def test_save_promises_ledger_creates_canonical_file(tmp_path):
    gen = BookPlanGenerator(project_path=str(tmp_path))
    plan = {
        "promises_ledger": [
            {
                "promise_id": "p1",
                "label": "knock at door",
                "description": "the knock at the door",
                "planted_chapter": 2,
                "expected_payoff_window": [4, 6],
                "promise_type": "threat",
                "weight": "major",
            },
            {
                # Missing promise_id — should be auto-assigned.
                "label": "second promise",
                "description": "without explicit id",
                "planted_chapter": 1,
                "expected_payoff_window": [3, 5],
                "weight": "minor",
            },
        ],
    }
    gen.save_promises_ledger(plan)
    payload = json.loads(gen.promises_ledger_path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert len(payload["promises"]) == 2
    ids = [p["promise_id"] for p in payload["promises"]]
    assert ids == ["p1", "p2"]
    for p in payload["promises"]:
        assert p["status"] == "open"
        assert p["history"] == []


def test_save_promises_ledger_handles_empty_ledger(tmp_path):
    gen = BookPlanGenerator(project_path=str(tmp_path))
    gen.save_promises_ledger({"promises_ledger": []})
    payload = json.loads(gen.promises_ledger_path.read_text(encoding="utf-8"))
    assert payload["promises"] == []


def test_compact_plan_for_fix_preserves_new_fields(tmp_path):
    gen = BookPlanGenerator(project_path=str(tmp_path))
    plan = {
        "promises_ledger": [{"promise_id": "p1", "label": "x"}],
        "chapters": [{
            "chapter_number": 1,
            "title": "T",
            "summary": "S",
            "objectives": ["a"],
            "chapter_tier": "setpiece",
            "thematic_move": "complicate",
            "thematic_move_note": "note here",
            "promises_planted": ["p1"],
            "promises_paid": [],
        }],
    }
    compact = gen._compact_plan_for_fix(plan)
    chapter = compact["chapters"][0]
    assert chapter["chapter_tier"] == "setpiece"
    assert chapter["thematic_move"] == "complicate"
    assert chapter["thematic_move_note"] == "note here"
    assert chapter["promises_planted"] == ["p1"]
    assert compact["promises_ledger"] == [{"promise_id": "p1", "label": "x"}]
