"""Tests for the best-of-N runner (Proposal 9)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from backend.auto_complete.helpers.best_of_n import (
    BEST_OF_N_TIERS,
    BestOfNResult,
    CandidateResult,
    _select_winner,
    persist_best_of_n_artifacts,
    run_best_of_n,
    should_run_best_of_n,
)


def test_should_run_best_of_n_only_for_setpiece():
    assert should_run_best_of_n({"chapter_tier": "setpiece"}) is True
    assert should_run_best_of_n({"chapter_tier": "SETPIECE"}) is True
    assert should_run_best_of_n({"chapter_tier": "development"}) is False
    assert should_run_best_of_n({"chapter_tier": "connective"}) is False
    assert should_run_best_of_n({}) is False
    assert should_run_best_of_n(None) is False  # type: ignore[arg-type]


def test_best_of_n_tiers_is_immutable_set():
    assert "setpiece" in BEST_OF_N_TIERS
    with pytest.raises(AttributeError):
        BEST_OF_N_TIERS.add("development")  # type: ignore[attr-defined]


def test_select_winner_picks_highest_score():
    candidates = [
        CandidateResult(index=0, content="aaa bbb ccc", critique={"score": 0.6}, word_count=3),
        CandidateResult(index=1, content="aaa bbb ccc ddd", critique={"score": 0.9}, word_count=4),
        CandidateResult(index=2, content="aaa", critique={"score": 0.7}, word_count=1),
    ]
    winner = _select_winner(candidates)
    assert winner.index == 1


def test_select_winner_skips_empty_and_errored():
    candidates = [
        CandidateResult(index=0, content="", error="boom"),
        CandidateResult(index=1, content="aaa bbb", critique={"score": 0.5}, word_count=2),
        CandidateResult(index=2, content="", error="empty_content"),
    ]
    winner = _select_winner(candidates)
    assert winner.index == 1


def test_select_winner_falls_back_to_first_non_empty_when_all_errored():
    candidates = [
        CandidateResult(index=0, content="", error="x"),
        CandidateResult(index=1, content="some prose", error="critique_failed"),
    ]
    winner = _select_winner(candidates)
    assert winner.index == 1


def test_select_winner_tiebreaks_on_severity_then_word_count():
    candidates = [
        CandidateResult(
            index=0, content="x" * 100,
            critique={"score": 0.8, "findings": [{"severity": "high"}]},
            word_count=100,
        ),
        CandidateResult(
            index=1, content="x" * 200,
            critique={"score": 0.8, "findings": []},
            word_count=200,
        ),
        CandidateResult(
            index=2, content="x" * 150,
            critique={"score": 0.8, "findings": [{"severity": "medium"}]},
            word_count=150,
        ),
    ]
    winner = _select_winner(candidates)
    assert winner.index == 1


def test_select_winner_word_count_breaks_score_tie():
    candidates = [
        CandidateResult(index=0, content="x" * 100, critique={"score": 0.8}, word_count=100),
        CandidateResult(index=1, content="x" * 250, critique={"score": 0.8}, word_count=250),
    ]
    winner = _select_winner(candidates)
    # Setpieces deserve room; longer wins on score tie.
    assert winner.index == 1


@pytest.mark.asyncio
async def test_run_best_of_n_runs_n_attempts_in_parallel():
    counter = {"n": 0}

    async def gen():
        counter["n"] += 1
        await asyncio.sleep(0.01)
        return "prose " * 50

    async def crit(text: str) -> Dict[str, Any]:
        return {"score": 0.9, "summary": "", "findings": []}

    result = await run_best_of_n(n=3, generate=gen, critique=crit)
    assert counter["n"] == 3
    assert len(result.candidates) == 3
    assert result.winner.score == 0.9
    assert len(result.decision_log["scores"]) == 3


@pytest.mark.asyncio
async def test_run_best_of_n_picks_winner_by_score():
    scores_iter = iter([0.5, 0.95, 0.8])
    contents_iter = iter(["a a a", "b b b b b", "c c c c"])

    async def gen():
        return next(contents_iter)

    async def crit(text: str) -> Dict[str, Any]:
        return {"score": next(scores_iter), "summary": "", "findings": []}

    result = await run_best_of_n(n=3, generate=gen, critique=crit)
    assert result.winner.index == 1
    assert result.winner.content == "b b b b b"
    assert result.decision_log["selected_index"] == 1


@pytest.mark.asyncio
async def test_run_best_of_n_handles_one_attempt_failing():
    call_count = {"n": 0}

    async def gen():
        i = call_count["n"]
        call_count["n"] += 1
        if i == 0:
            raise RuntimeError("first attempt blew up")
        return "good prose " * 100

    async def crit(text: str) -> Dict[str, Any]:
        return {"score": 0.85, "summary": "", "findings": []}

    result = await run_best_of_n(n=2, generate=gen, critique=crit)
    assert result.winner.error is None
    assert "good prose" in result.winner.content
    # First candidate should have an error recorded.
    errors = [c.error for c in result.candidates]
    assert any(e is not None for e in errors)


@pytest.mark.asyncio
async def test_run_best_of_n_works_without_critic():
    async def gen():
        return "x" * 80

    result = await run_best_of_n(n=2, generate=gen)
    assert result.winner.content
    # No critic → all scores default to 1.0.
    assert all(c.score == 1.0 for c in result.candidates)


@pytest.mark.asyncio
async def test_run_best_of_n_rejects_n_below_one():
    async def gen():
        return "x"

    with pytest.raises(ValueError):
        await run_best_of_n(n=0, generate=gen)


def test_persist_best_of_n_artifacts_writes_files(tmp_path):
    candidates = [
        CandidateResult(index=0, content="alt prose", critique={"score": 0.7}, word_count=2),
        CandidateResult(index=1, content="winner prose", critique={"score": 0.95}, word_count=2),
    ]
    result = BestOfNResult(
        winner=candidates[1],
        candidates=candidates,
        decision_log={
            "n": 2,
            "selected_index": 1,
            "scores": [0.7, 0.95],
            "word_counts": [2, 2],
            "errors": [None, None],
        },
    )
    out_dir = persist_best_of_n_artifacts(tmp_path, chapter_number=7, result=result)
    assert out_dir.exists()
    files = sorted(p.name for p in out_dir.iterdir())
    assert "candidate-0-alt.md" in files
    assert "candidate-0-alt.critique.json" in files
    assert "candidate-1-winner.md" in files
    assert "candidate-1-winner.critique.json" in files
    assert "decision.json" in files
    decision = json.loads((out_dir / "decision.json").read_text(encoding="utf-8"))
    assert decision["selected_index"] == 1
    assert decision["scores"] == [0.7, 0.95]
