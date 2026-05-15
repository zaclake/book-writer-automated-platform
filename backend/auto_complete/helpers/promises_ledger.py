#!/usr/bin/env python3
"""Promises Ledger lifecycle (Proposal 4 — Promises and Payoffs).

The book plan generator emits an initial set of "promises" — setups the book
makes that the reader expects to see paid off (an object the protagonist
notices, a debt referenced, a knock at a door, a question someone asks). This
module is the chapter-side counterpart: it loads, queries, and updates that
ledger as chapters are generated.

Lifecycle:

  1. ``BookPlanGenerator.save_promises_ledger(...)`` writes the initial
     ``book-promises.json`` during planning.
  2. Before generating chapter N, the chapter pipeline calls
     ``compose_outstanding_block(ledger, chapter_number=N, ...)`` and injects
     the resulting text block into the planner / drafter prompt so the model
     is reminded of (a) promises it MUST pay off in this chapter window, and
     (b) promises it has been carrying for too long.
  3. After chapter N is finalized, the chapter pipeline calls
     ``apply_chapter_to_ledger(ledger, chapter_plan, chapter_number=N)`` to
     mark planted/paid promises and persist the updated ledger.
  4. At any time, ``audit_unpaid_promises(ledger, total_chapters)`` returns
     promises that are past their payoff window — surfaced for review.

The ledger is deliberately conservative: it never deletes promises or
silently rewrites them. It only flips ``status`` and appends to ``history``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


logger = logging.getLogger(__name__)


_VALID_STATUSES = {"open", "paid", "abandoned", "carried"}
_VALID_WEIGHTS = {"minor", "major", "central"}


@dataclass
class PromisesLedger:
    """In-memory view of ``book-promises.json``.

    The ledger is kept as a thin wrapper around the JSON dict so the chapter
    pipeline can mutate it incrementally and write it back without recreating
    structure. ``promises`` is a list of dicts, each with at minimum:
        promise_id, label, description, planted_chapter,
        expected_payoff_window, promise_type, weight, status, history
    """

    path: Path
    data: Dict[str, Any]

    @property
    def promises(self) -> List[Dict[str, Any]]:
        return self.data.setdefault("promises", [])

    @classmethod
    def load(cls, path: Path) -> "PromisesLedger":
        if not path.exists():
            return cls(
                path=path,
                data={
                    "version": 1,
                    "created_at": datetime.utcnow().isoformat(),
                    "promises": [],
                },
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as err:
            logger.warning("Failed to load promises ledger %s: %s", path, err)
            data = {"version": 1, "promises": []}
        if not isinstance(data, dict):
            data = {"version": 1, "promises": []}
        if not isinstance(data.get("promises"), list):
            data["promises"] = []
        return cls(path=path, data=data)

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self.data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as err:
            logger.warning("Failed to save promises ledger %s: %s", self.path, err)

    def find(self, promise_id: str) -> Optional[Dict[str, Any]]:
        promise_id = str(promise_id or "").strip()
        if not promise_id:
            return None
        for promise in self.promises:
            if str(promise.get("promise_id") or "").strip() == promise_id:
                return promise
        return None


def _normalize_promise_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    candidate = str(value).strip()
    return candidate or None


def _promise_in_window(
    promise: Dict[str, Any],
    chapter_number: int,
) -> bool:
    """True if the chapter falls inside the promise's expected payoff window."""
    window = promise.get("expected_payoff_window") or []
    if not isinstance(window, (list, tuple)) or len(window) < 1:
        return False
    try:
        lo = int(window[0])
        hi = int(window[1]) if len(window) >= 2 else lo
    except Exception:
        return False
    return lo <= chapter_number <= hi


def _promise_overdue(promise: Dict[str, Any], chapter_number: int) -> bool:
    """True if the chapter is past the promise's expected payoff window."""
    window = promise.get("expected_payoff_window") or []
    if not isinstance(window, (list, tuple)) or len(window) < 2:
        return False
    try:
        hi = int(window[1])
    except Exception:
        return False
    return chapter_number > hi and str(promise.get("status") or "open").lower() == "open"


def _format_window(window: Any) -> str:
    if not isinstance(window, (list, tuple)) or not window:
        return "TBD"
    try:
        if len(window) == 1:
            return f"ch {int(window[0])}"
        return f"ch {int(window[0])}-{int(window[1])}"
    except Exception:
        return "TBD"


def compose_outstanding_block(
    ledger: PromisesLedger,
    *,
    chapter_number: int,
    max_promises: int = 12,
) -> str:
    """Build a compact text block of outstanding promises for a chapter prompt.

    Promises are surfaced in this order:
      1. Open promises whose expected payoff window includes ``chapter_number``
         (these MUST be paid this chapter).
      2. Open promises that are overdue (past the upper bound of the window).
      3. Other open promises whose payoff window starts BEFORE ``chapter_number``
         (the drafter should at least be aware of them).
      4. Open central / major promises planted in earlier chapters that still
         have headroom (lowest priority).

    Returns an empty string if there are no relevant promises.
    """
    promises = ledger.promises
    if not promises:
        return ""

    open_promises = [
        p for p in promises
        if str(p.get("status") or "open").lower() == "open"
    ]
    if not open_promises:
        return ""

    must_pay: List[Dict[str, Any]] = []
    overdue: List[Dict[str, Any]] = []
    upcoming: List[Dict[str, Any]] = []
    background: List[Dict[str, Any]] = []

    for promise in open_promises:
        if _promise_in_window(promise, chapter_number):
            must_pay.append(promise)
        elif _promise_overdue(promise, chapter_number):
            overdue.append(promise)
        else:
            window = promise.get("expected_payoff_window") or []
            try:
                lo = int(window[0]) if window else None
            except Exception:
                lo = None
            if lo is not None and lo <= chapter_number:
                upcoming.append(promise)
            elif str(promise.get("weight") or "minor").lower() in {"major", "central"}:
                background.append(promise)

    def _line(p: Dict[str, Any]) -> str:
        pid = p.get("promise_id") or ""
        label = (p.get("label") or "").strip() or (p.get("description") or "").strip()[:80]
        weight = (p.get("weight") or "minor").lower()
        planted = p.get("planted_chapter")
        window_str = _format_window(p.get("expected_payoff_window"))
        return f"  - [{pid} | {weight} | planted ch {planted} | window {window_str}] {label}"

    lines: List[str] = ["OUTSTANDING PROMISES (Proposal 4 — Promises Ledger):"]
    if must_pay:
        lines.append("  Promises whose payoff window INCLUDES this chapter — pay these now if at all possible:")
        lines.extend(_line(p) for p in must_pay[:max_promises])
    if overdue:
        lines.append("  Promises that are OVERDUE — the reader is already wondering. Pay or explicitly retire:")
        lines.extend(_line(p) for p in overdue[:max_promises])
    if upcoming and (len(must_pay) + len(overdue)) < max_promises:
        budget = max_promises - len(must_pay) - len(overdue)
        if budget > 0:
            lines.append("  Promises in flight — keep alive in subtext where natural:")
            lines.extend(_line(p) for p in upcoming[:budget])
    if (
        background
        and (len(must_pay) + len(overdue) + min(len(upcoming), max_promises)) < max_promises
    ):
        budget = max_promises - len(must_pay) - len(overdue) - min(len(upcoming), max_promises)
        if budget > 0:
            lines.append("  Background major/central promises — do not let these go cold:")
            lines.extend(_line(p) for p in background[:budget])

    if len(lines) == 1:
        return ""
    lines.append(
        "  Rules: When you pay a promise, the chapter plan's `promises_paid` array MUST list its "
        "promise_id. When the chapter plants a NEW promise that didn't exist in the ledger, add it "
        "to `promises_planted` with a freshly invented `pX` id and brief description."
    )
    return "\n".join(lines)


def apply_chapter_to_ledger(
    ledger: PromisesLedger,
    *,
    chapter_plan: Dict[str, Any],
    chapter_number: int,
    new_promise_descriptions: Optional[Dict[str, str]] = None,
) -> Tuple[List[str], List[str]]:
    """Update the ledger after a chapter is finalized.

    ``chapter_plan`` should be the chapter's entry in ``book-plan.json`` (or
    the live chapter blueprint). It must carry ``promises_planted`` and
    ``promises_paid`` arrays of promise IDs.

    ``new_promise_descriptions`` optionally maps newly-introduced promise IDs
    to descriptions, so the drafter can plant a promise mid-book without the
    upstream planner having anticipated it.

    Returns ``(paid_ids, planted_ids)`` for diagnostics.
    """
    if not isinstance(chapter_plan, dict):
        return ([], [])
    new_promise_descriptions = new_promise_descriptions or {}

    paid_ids: List[str] = []
    planted_ids: List[str] = []
    timestamp = datetime.utcnow().isoformat()

    # Mark paid.
    for raw_pid in chapter_plan.get("promises_paid") or []:
        pid = _normalize_promise_id(raw_pid)
        if not pid:
            continue
        promise = ledger.find(pid)
        if not promise:
            # Unknown ID; create a stub so the chapter's claim is preserved.
            promise = {
                "promise_id": pid,
                "label": new_promise_descriptions.get(pid, "")[:80],
                "description": new_promise_descriptions.get(pid, ""),
                "planted_chapter": None,
                "expected_payoff_window": [],
                "promise_type": "obligation",
                "weight": "minor",
                "status": "open",
                "history": [],
            }
            ledger.promises.append(promise)
        promise["status"] = "paid"
        history = promise.setdefault("history", [])
        history.append({
            "ts": timestamp,
            "chapter": chapter_number,
            "event": "paid",
        })
        paid_ids.append(pid)

    # Mark planted (new promises).
    for raw_pid in chapter_plan.get("promises_planted") or []:
        pid = _normalize_promise_id(raw_pid)
        if not pid:
            continue
        promise = ledger.find(pid)
        if promise is None:
            promise = {
                "promise_id": pid,
                "label": new_promise_descriptions.get(pid, "")[:80],
                "description": new_promise_descriptions.get(pid, ""),
                "planted_chapter": chapter_number,
                "expected_payoff_window": [],
                "promise_type": "obligation",
                "weight": "minor",
                "status": "open",
                "history": [{
                    "ts": timestamp,
                    "chapter": chapter_number,
                    "event": "planted",
                }],
            }
            ledger.promises.append(promise)
        else:
            history = promise.setdefault("history", [])
            history.append({
                "ts": timestamp,
                "chapter": chapter_number,
                "event": "re-planted",
            })
        planted_ids.append(pid)

    ledger.save()
    return (paid_ids, planted_ids)


def audit_unpaid_promises(
    ledger: PromisesLedger,
    *,
    total_chapters: int,
) -> List[Dict[str, Any]]:
    """Return the list of promises that are still open past their window.

    Useful for a final pre-publish report so a human can decide whether each
    open promise should be paid in a revision pass or explicitly abandoned.
    """
    overdue: List[Dict[str, Any]] = []
    for promise in ledger.promises:
        if str(promise.get("status") or "open").lower() != "open":
            continue
        if _promise_overdue(promise, total_chapters):
            overdue.append(promise)
    return overdue
