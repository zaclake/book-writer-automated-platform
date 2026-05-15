"""Tests for the plan-compliance critic (Proposal 1).

We exercise the critic's normalization and side-effect helpers directly. The
LLM call itself is wrapped in a thin async function (``critique_chapter``)
that is exercised only via mocks.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.auto_complete.helpers.plan_compliance_critic import (
    _coerce_critique,
    _coerce_finding,
    _serialize_blueprint_for_critic,
    critique_chapter,
    format_critique_for_next_chapter,
    persist_critique,
    reconcile_promises_with_critique,
)
from backend.auto_complete.helpers.promises_ledger import PromisesLedger


def test_serialize_blueprint_keeps_only_relevant_fields():
    blueprint = {
        "opening_approach": "open with knock at the door",
        "chapter_tier": "setpiece",
        "thematic_move": "complicate",
        "scenes": [{"scene_number": 1, "description": "x"}],
        "promises_paid": ["p1"],
        "promises_planted": [],
        "junk_field": "should be dropped",
        "another_junk": 99,
    }
    out = _serialize_blueprint_for_critic(blueprint)
    assert "opening_approach" in out
    assert "chapter_tier" in out
    assert "junk_field" not in out
    assert "another_junk" not in out


def test_coerce_finding_drops_invalid_categories():
    assert _coerce_finding({"category": "made_up_category"}) is None
    assert _coerce_finding(None) is None
    assert _coerce_finding({"category": "promise_unpaid", "severity": "low"}) == {
        "category": "promise_unpaid",
        "severity": "low",
        "evidence": "",
        "fix_hint": "",
    }


def test_coerce_finding_normalizes_severity():
    out = _coerce_finding({
        "category": "scene_omitted",
        "severity": "MEDIUM ",
        "evidence": "scene 3 missing",
        "fix_hint": "include the diner scene",
    })
    assert out["severity"] == "medium"


def test_coerce_critique_clamps_score_and_normalizes_findings():
    raw = {
        "score": 1.7,
        "summary": "drifty",
        "findings": [
            {"category": "promise_unpaid", "severity": "high",
             "evidence": "p1 never paid", "fix_hint": "pay p1 next chapter"},
            {"category": "bogus", "severity": "high"},
            "not even a dict",
        ],
    }
    out = _coerce_critique(raw)
    assert out["score"] == 1.0
    assert out["summary"] == "drifty"
    assert len(out["findings"]) == 1
    assert out["findings"][0]["category"] == "promise_unpaid"


def test_coerce_critique_clamps_low_score():
    out = _coerce_critique({"score": -0.5})
    assert out["score"] == 0.0


@pytest.mark.asyncio
async def test_critique_chapter_returns_default_when_blueprint_empty():
    out = await critique_chapter(
        orchestrator=MagicMock(),
        chapter_number=1,
        chapter_text="some text",
        blueprint={},
    )
    assert out == {"score": 1.0, "summary": "", "findings": []}


@pytest.mark.asyncio
async def test_critique_chapter_returns_default_when_text_empty():
    out = await critique_chapter(
        orchestrator=MagicMock(),
        chapter_number=1,
        chapter_text="",
        blueprint={"chapter_tier": "setpiece"},
    )
    assert out == {"score": 1.0, "summary": "", "findings": []}


@pytest.mark.asyncio
async def test_critique_chapter_handles_orchestrator_failure():
    orchestrator = MagicMock()
    orchestrator._make_api_call = AsyncMock(side_effect=RuntimeError("boom"))
    out = await critique_chapter(
        orchestrator=orchestrator,
        chapter_number=2,
        chapter_text="prose",
        blueprint={"chapter_tier": "setpiece", "thematic_move": "complicate"},
    )
    assert out == {"score": 1.0, "summary": "", "findings": []}


@pytest.mark.asyncio
async def test_critique_chapter_parses_valid_response():
    fake_response = MagicMock()
    fake_response.output_text = json.dumps({
        "score": 0.7,
        "summary": "missing payoff",
        "findings": [
            {
                "category": "promise_unpaid",
                "severity": "high",
                "evidence": "p1 was supposed to pay",
                "fix_hint": "deliver p1 next chapter",
            }
        ],
    })
    orchestrator = MagicMock()
    orchestrator._make_api_call = AsyncMock(return_value=fake_response)
    out = await critique_chapter(
        orchestrator=orchestrator,
        chapter_number=3,
        chapter_text="some prose",
        blueprint={"chapter_tier": "setpiece", "thematic_move": "complicate"},
    )
    assert out["score"] == 0.7
    assert len(out["findings"]) == 1
    assert out["findings"][0]["category"] == "promise_unpaid"


def test_persist_critique_writes_chapter_json(tmp_path):
    critique = {
        "score": 0.85,
        "summary": "minor drift",
        "findings": [{"category": "register_drift", "severity": "low",
                      "evidence": "lyrical not plain", "fix_hint": "tone down"}],
    }
    path = persist_critique(tmp_path, chapter_number=4, critique=critique)
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["chapter_number"] == 4
    assert payload["score"] == 0.85
    assert payload["findings"][0]["category"] == "register_drift"


def test_format_critique_for_next_chapter_skips_low_severity():
    critique = {
        "score": 0.85,
        "summary": "x",
        "findings": [
            {"category": "register_drift", "severity": "low", "evidence": "", "fix_hint": "tone down"},
        ],
    }
    assert format_critique_for_next_chapter(critique, chapter_number=1) == ""


def test_format_critique_for_next_chapter_includes_high_severity():
    critique = {
        "score": 0.4,
        "summary": "bad",
        "findings": [
            {"category": "promise_unpaid", "severity": "high", "evidence": "p1", "fix_hint": "pay p1"},
            {"category": "register_drift", "severity": "low", "evidence": "", "fix_hint": "x"},
        ],
    }
    out = format_critique_for_next_chapter(critique, chapter_number=2)
    assert "promise_unpaid" in out
    assert "pay p1" in out
    assert "register_drift" not in out


def test_reconcile_promises_reverts_explicit_id_match(tmp_path):
    payload = {
        "version": 1,
        "promises": [
            {
                "promise_id": "p1",
                "label": "knock at door",
                "description": "the knock",
                "planted_chapter": 1,
                "expected_payoff_window": [3, 5],
                "promise_type": "threat",
                "weight": "major",
                "status": "paid",
                "history": [{"ts": "x", "chapter": 4, "event": "paid"}],
            }
        ],
    }
    path = tmp_path / "book-promises.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    ledger = PromisesLedger.load(path)

    critique = {
        "score": 0.5,
        "findings": [
            {
                "category": "promise_unpaid",
                "severity": "high",
                "evidence": "p1 was claimed paid but never delivered on-page",
                "fix_hint": "deliver p1 next chapter",
            }
        ],
    }
    reverted = reconcile_promises_with_critique(
        promises_ledger=ledger,
        critique=critique,
        chapter_number=4,
    )
    assert reverted == ["p1"]
    assert ledger.find("p1")["status"] == "open"
    history = ledger.find("p1")["history"]
    assert any(h.get("event") == "reverted_by_critic" for h in history)


def test_reconcile_promises_falls_back_to_label_match(tmp_path):
    payload = {
        "version": 1,
        "promises": [
            {
                "promise_id": "p7",
                "label": "the locked study",
                "description": "the door reader was shown",
                "planted_chapter": 1,
                "expected_payoff_window": [3, 5],
                "promise_type": "place",
                "weight": "central",
                "status": "paid",
                "history": [],
            }
        ],
    }
    path = tmp_path / "book-promises.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    ledger = PromisesLedger.load(path)

    critique = {
        "findings": [
            {
                "category": "promise_unpaid",
                "severity": "medium",
                "evidence": "the locked study was not opened on-page",
                "fix_hint": "open the locked study",
            }
        ],
    }
    reverted = reconcile_promises_with_critique(
        promises_ledger=ledger,
        critique=critique,
        chapter_number=4,
    )
    assert reverted == ["p7"]
    assert ledger.find("p7")["status"] == "open"


def test_reconcile_promises_skips_low_severity(tmp_path):
    payload = {
        "version": 1,
        "promises": [
            {
                "promise_id": "p1",
                "label": "x",
                "description": "x",
                "planted_chapter": 1,
                "expected_payoff_window": [3, 5],
                "promise_type": "object",
                "weight": "minor",
                "status": "paid",
                "history": [],
            }
        ],
    }
    path = tmp_path / "book-promises.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    ledger = PromisesLedger.load(path)

    critique = {
        "findings": [
            {
                "category": "promise_unpaid",
                "severity": "low",
                "evidence": "p1 was kind of paid",
                "fix_hint": "fully deliver p1",
            }
        ],
    }
    reverted = reconcile_promises_with_critique(
        promises_ledger=ledger,
        critique=critique,
        chapter_number=4,
    )
    assert reverted == []
    assert ledger.find("p1")["status"] == "paid"
