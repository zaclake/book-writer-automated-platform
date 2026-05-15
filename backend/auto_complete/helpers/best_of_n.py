#!/usr/bin/env python3
"""Best-of-N at setpiece chapters (Proposal 9).

For chapters tagged ``chapter_tier: setpiece`` (the climactic / decisive
chapters the entire book builds toward), it pays to spend extra compute and
generate N candidate drafts in parallel, then pick the strongest.

Selection is based on the plan-compliance critic (Proposal 1) score, with
specific tiebreakers chosen to favor candidates that actually deliver the
weight a setpiece demands. The non-winning candidates are persisted to
``.project-state/best-of-n/chapter-NN/`` so a human can inspect alternatives
later.

This module is deliberately small: it is a runner around a generate-chapter
callable plus the critic. It does NOT modify the generation pipeline itself.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple


logger = logging.getLogger(__name__)


# Chapter tiers that should opt into best-of-N. Today only "setpiece"; kept
# as a frozenset so callers can reason about it programmatically.
BEST_OF_N_TIERS: frozenset[str] = frozenset({"setpiece"})


@dataclass
class CandidateResult:
    """One attempt's output and critique."""
    index: int
    content: str
    critique: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    word_count: int = 0

    @property
    def score(self) -> float:
        try:
            return float(self.critique.get("score", 0.0))
        except Exception:
            return 0.0

    @property
    def finding_severity_count(self) -> Tuple[int, int, int]:
        """Counts of (high, medium, low) severity findings."""
        high = medium = low = 0
        for finding in self.critique.get("findings") or []:
            sev = str(finding.get("severity") or "").lower()
            if sev == "high":
                high += 1
            elif sev == "medium":
                medium += 1
            elif sev == "low":
                low += 1
        return (high, medium, low)


@dataclass
class BestOfNResult:
    """Outcome of a best-of-N generation pass."""
    winner: CandidateResult
    candidates: List[CandidateResult]
    decision_log: Dict[str, Any] = field(default_factory=dict)


def should_run_best_of_n(blueprint: Dict[str, Any]) -> bool:
    """Return True if the blueprint's chapter_tier is one we BoN on."""
    if not isinstance(blueprint, dict):
        return False
    tier = str(blueprint.get("chapter_tier") or "").strip().lower()
    return tier in BEST_OF_N_TIERS


def _select_winner(candidates: List[CandidateResult]) -> CandidateResult:
    """Pick the strongest candidate.

    Selection rules, applied in order:
      1. Drop candidates with empty content or any error.
      2. Highest critic score wins.
      3. Tiebreak by FEWER high-severity findings.
      4. Tiebreak by FEWER medium-severity findings.
      5. Tiebreak by HIGHER word_count (setpieces deserve room to breathe;
         under-written setpieces are the failure mode we're guarding against).
      6. Tiebreak by lowest index (deterministic).
    """
    usable = [
        c for c in candidates
        if c.content and len(c.content.strip()) > 0 and not c.error
    ]
    if not usable:
        # Fall back to the first non-empty candidate even if it errored, so
        # the caller has SOMETHING to ship.
        for candidate in candidates:
            if candidate.content and candidate.content.strip():
                return candidate
        # Truly nothing usable; return the first.
        return candidates[0]

    def sort_key(c: CandidateResult):
        high, medium, _ = c.finding_severity_count
        return (
            -c.score,        # higher score first
            high,            # fewer high-severity findings first
            medium,          # fewer medium-severity findings first
            -c.word_count,   # longer (more breathing room) first
            c.index,         # deterministic tiebreaker
        )

    return sorted(usable, key=sort_key)[0]


async def _run_single_attempt(
    *,
    index: int,
    generate: Callable[[], Awaitable[str]],
    critique: Optional[Callable[[str], Awaitable[Dict[str, Any]]]],
) -> CandidateResult:
    try:
        content = await generate()
    except Exception as err:
        logger.warning("Best-of-N candidate %d failed during generation: %s", index, err)
        return CandidateResult(index=index, content="", error=str(err))
    if not content or not content.strip():
        return CandidateResult(index=index, content="", error="empty_content")
    word_count = len(content.split())
    critique_payload: Dict[str, Any] = {"score": 1.0, "summary": "", "findings": []}
    if critique is not None:
        try:
            critique_payload = await critique(content)
        except Exception as err:
            logger.warning("Best-of-N candidate %d failed during critique: %s", index, err)
            critique_payload = {"score": 1.0, "summary": "", "findings": []}
    return CandidateResult(
        index=index,
        content=content,
        critique=critique_payload,
        word_count=word_count,
    )


async def run_best_of_n(
    *,
    n: int,
    generate: Callable[[], Awaitable[str]],
    critique: Optional[Callable[[str], Awaitable[Dict[str, Any]]]] = None,
) -> BestOfNResult:
    """Run ``n`` candidate generations in parallel and pick the winner.

    ``generate`` is an awaitable that produces one candidate's content. It is
    called ``n`` times concurrently — callers must ensure the function is
    safe to call in parallel (no shared mutable state across attempts beyond
    the orchestrator's own retry-safe primitives).

    ``critique`` is an optional awaitable that scores one candidate's content;
    when omitted, all non-empty candidates score equally and the longest one
    wins on word_count.

    Returns a :class:`BestOfNResult` with the winning candidate, all
    candidates (for diagnostics / persistence), and a decision log.
    """
    if n < 1:
        raise ValueError("n must be >= 1")

    tasks = [
        _run_single_attempt(index=i, generate=generate, critique=critique)
        for i in range(n)
    ]
    candidates = await asyncio.gather(*tasks)

    winner = _select_winner(list(candidates))
    decision_log = {
        "n": n,
        "selected_index": winner.index,
        "scores": [c.score for c in candidates],
        "word_counts": [c.word_count for c in candidates],
        "errors": [c.error for c in candidates],
    }
    return BestOfNResult(
        winner=winner,
        candidates=list(candidates),
        decision_log=decision_log,
    )


def persist_best_of_n_artifacts(
    project_path: Path,
    chapter_number: int,
    result: BestOfNResult,
) -> Path:
    """Save all candidates + decision log under ``.project-state/best-of-n/``.

    Returns the directory created. Errors are logged and swallowed.
    """
    try:
        run_dir = project_path / ".project-state" / "best-of-n" / f"chapter-{chapter_number:02d}"
        run_dir.mkdir(parents=True, exist_ok=True)
        for candidate in result.candidates:
            tag = "winner" if candidate.index == result.winner.index else "alt"
            stem = f"candidate-{candidate.index}-{tag}"
            (run_dir / f"{stem}.md").write_text(
                candidate.content or "", encoding="utf-8"
            )
            (run_dir / f"{stem}.critique.json").write_text(
                json.dumps(candidate.critique, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        log_payload = dict(result.decision_log)
        log_payload["created_at"] = datetime.utcnow().isoformat()
        (run_dir / "decision.json").write_text(
            json.dumps(log_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return run_dir
    except Exception as err:
        logger.warning(
            "Failed to persist best-of-n artifacts for Chapter %s: %s",
            chapter_number, err,
        )
        return project_path
