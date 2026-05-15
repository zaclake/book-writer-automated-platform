"""Tests for the promises ledger lifecycle (Proposal 4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.auto_complete.helpers.promises_ledger import (
    PromisesLedger,
    apply_chapter_to_ledger,
    audit_unpaid_promises,
    compose_outstanding_block,
)


def _seed_ledger(tmp_path: Path) -> PromisesLedger:
    payload = {
        "version": 1,
        "promises": [
            {
                "promise_id": "p1",
                "label": "knock at the door",
                "description": "the knock at the door in chapter 2 must be paid off",
                "planted_chapter": 2,
                "expected_payoff_window": [4, 6],
                "promise_type": "threat",
                "weight": "major",
                "status": "open",
                "history": [],
            },
            {
                "promise_id": "p2",
                "label": "the locked study",
                "description": "the locked study door reader was shown",
                "planted_chapter": 3,
                "expected_payoff_window": [8, 10],
                "promise_type": "place",
                "weight": "central",
                "status": "open",
                "history": [],
            },
            {
                "promise_id": "p3",
                "label": "minor: cigarette case",
                "description": "object of mild curiosity",
                "planted_chapter": 1,
                "expected_payoff_window": [3, 4],
                "promise_type": "object",
                "weight": "minor",
                "status": "open",
                "history": [],
            },
        ],
    }
    path = tmp_path / "book-promises.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return PromisesLedger.load(path)


def test_load_returns_empty_ledger_when_file_missing(tmp_path):
    ledger = PromisesLedger.load(tmp_path / "nope.json")
    assert ledger.promises == []
    assert ledger.data["version"] == 1


def test_compose_block_lists_must_pay_in_window(tmp_path):
    ledger = _seed_ledger(tmp_path)
    block = compose_outstanding_block(ledger, chapter_number=5)
    assert "OUTSTANDING PROMISES" in block
    assert "p1" in block
    assert "Promises whose payoff window INCLUDES this chapter" in block


def test_compose_block_flags_overdue(tmp_path):
    ledger = _seed_ledger(tmp_path)
    block = compose_outstanding_block(ledger, chapter_number=7)
    # p3 was due ch3-4, now overdue at ch7.
    assert "p3" in block
    assert "OVERDUE" in block


def test_compose_block_returns_empty_when_no_open_promises(tmp_path):
    ledger = _seed_ledger(tmp_path)
    for promise in ledger.promises:
        promise["status"] = "paid"
    assert compose_outstanding_block(ledger, chapter_number=5) == ""


def test_apply_chapter_marks_paid(tmp_path):
    ledger = _seed_ledger(tmp_path)
    paid, planted = apply_chapter_to_ledger(
        ledger,
        chapter_plan={"promises_paid": ["p1"], "promises_planted": []},
        chapter_number=5,
    )
    assert paid == ["p1"]
    assert planted == []
    p1 = ledger.find("p1")
    assert p1["status"] == "paid"
    assert any(h["event"] == "paid" for h in p1["history"])
    # Persisted to disk.
    reloaded = PromisesLedger.load(ledger.path)
    assert reloaded.find("p1")["status"] == "paid"


def test_apply_chapter_creates_new_promise_when_planted(tmp_path):
    ledger = _seed_ledger(tmp_path)
    paid, planted = apply_chapter_to_ledger(
        ledger,
        chapter_plan={"promises_paid": [], "promises_planted": ["p4"]},
        chapter_number=5,
        new_promise_descriptions={"p4": "a face seen in the crowd"},
    )
    assert planted == ["p4"]
    p4 = ledger.find("p4")
    assert p4 is not None
    assert p4["planted_chapter"] == 5
    assert p4["status"] == "open"
    assert p4["description"] == "a face seen in the crowd"


def test_audit_unpaid_promises_returns_only_overdue(tmp_path):
    ledger = _seed_ledger(tmp_path)
    overdue = audit_unpaid_promises(ledger, total_chapters=12)
    overdue_ids = {p["promise_id"] for p in overdue}
    # All open promises whose window upper bound < 12 should appear.
    assert overdue_ids == {"p1", "p2", "p3"}
    # Once we mark p2 paid, it should drop off.
    ledger.find("p2")["status"] = "paid"
    overdue_after = audit_unpaid_promises(ledger, total_chapters=12)
    assert {p["promise_id"] for p in overdue_after} == {"p1", "p3"}


def test_apply_chapter_paying_unknown_id_creates_stub(tmp_path):
    ledger = _seed_ledger(tmp_path)
    paid, _ = apply_chapter_to_ledger(
        ledger,
        chapter_plan={"promises_paid": ["pX"], "promises_planted": []},
        chapter_number=5,
        new_promise_descriptions={"pX": "ad-hoc payoff"},
    )
    assert paid == ["pX"]
    pX = ledger.find("pX")
    assert pX is not None
    assert pX["status"] == "paid"
    assert pX["description"] == "ad-hoc payoff"
