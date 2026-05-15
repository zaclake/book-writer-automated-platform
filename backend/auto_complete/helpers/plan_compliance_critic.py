#!/usr/bin/env python3
"""Plan-Compliance Critic (Proposal 1).

After a chapter is generated, the critic compares the chapter blueprint
(chapter_tier, thematic_move, promises_paid, promises_planted, scenes,
opening_approach, ending_approach, prose_register) against the prose itself
and returns a structured drift report:

  {
    "score": 0.0-1.0,
    "summary": "<one-line summary>",
    "findings": [
      {
        "category": "promise_unpaid | thematic_move_unrealized | scene_omitted |
                     opening_drift | ending_drift | tier_underwritten | ...",
        "severity": "low | medium | high",
        "evidence": "<short quote or excerpt>",
        "fix_hint": "<concrete instruction for the next pass>"
      }
    ]
  }

This is a SIGNAL, not a rewrite trigger. The user explicitly opted out of
whole-chapter editorial loops. The findings are:

  1. Persisted to ``.project-state/chapter-critiques/chapter-NN.json`` for
     a human reviewer.
  2. Used to AUTO-CORRECT the promises ledger when the critic determines a
     promise the chapter claims to have paid was not actually delivered
     on-page (the chapter blueprint says ``promises_paid: ["p3"]`` but the
     prose never delivers the payoff). When that happens, the ledger keeps
     p3 as ``open`` so the next chapter is reminded of it.
  3. Surfaced to the next chapter's planner via the orchestrator's
     ``recent_drift_findings`` context bag so persistent drift can be
     remediated upstream rather than ignored.

The critic itself is a small JSON-only LLM call. It is intentionally
conservative: when in doubt it SHOULD return ``severity: low`` rather than
fabricate findings, and its score MUST default to 1.0 if the blueprint is
empty. We never let critic failure block chapter generation.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


logger = logging.getLogger(__name__)


CRITIC_SYSTEM_PROMPT = (
    "You are a STRICT plan-compliance critic for a single chapter of a novel.\n"
    "Your job is to read the chapter's blueprint and the chapter prose, and\n"
    "report where the prose drifted from the plan.\n"
    "\n"
    "Output STRICT JSON only. No commentary, no code fences.\n"
    "\n"
    "Findings to look for:\n"
    "  * promise_unpaid — the blueprint says a promise_id is paid this chapter\n"
    "    but the prose never delivers the payoff on-page (the payoff was\n"
    "    summarized, glossed over, or absent).\n"
    "  * thematic_move_unrealized — the chapter's thematic_move (e.g.,\n"
    "    'complicate') is not visible in the prose. The chapter just exists;\n"
    "    it does not DO anything to the central question.\n"
    "  * tier_underwritten — the chapter is tagged 'setpiece' but reads like\n"
    "    a development chapter: too few scenes, too little weight, climactic\n"
    "    moment is glossed.\n"
    "  * tier_overwritten — the chapter is tagged 'connective' but reads like\n"
    "    a setpiece: manufactured tension, too many new developments, the\n"
    "    quiet earned by being a connective is wasted.\n"
    "  * scene_omitted — a scene from the blueprint was skipped.\n"
    "  * scene_added — a scene appears in prose that the blueprint did not plan.\n"
    "  * opening_drift — the actual opening does not match the blueprint's\n"
    "    opening_approach (e.g., blueprint says dialogue_first but prose opens\n"
    "    with setting description).\n"
    "  * ending_drift — the actual ending does not match the blueprint's\n"
    "    ending_approach.\n"
    "  * register_drift — the prose register is out of family with the\n"
    "    blueprint (e.g., 'plain' planned, lyrical delivered).\n"
    "  * pov_drift — POV character or POV type does not match the plan.\n"
    "\n"
    "Severity guidance:\n"
    "  - high   = a setpiece's core moment is missing/glossed, OR a major/central\n"
    "             promise the blueprint claimed paid is not actually delivered.\n"
    "  - medium = a planned scene was clearly omitted, OR thematic_move is\n"
    "             absent on a setpiece, OR ending_drift on the final chapter.\n"
    "  - low    = surface drift (a scene was reordered, a minor promise was\n"
    "             carried instead of paid, register slightly off).\n"
    "\n"
    "Be conservative. If the prose plausibly delivers the planned beat — even\n"
    "if it does so differently than the blueprint imagined — do NOT flag it.\n"
    "Only flag drift you can quote evidence for.\n"
)


CRITIC_USER_TEMPLATE = (
    "BLUEPRINT (the plan the chapter was supposed to execute):\n"
    "{blueprint_json}\n"
    "\n"
    "CHAPTER PROSE (full text of the generated chapter):\n"
    "{chapter_text}\n"
    "\n"
    "Return JSON of the form:\n"
    "{{\n"
    '  "score": 0.0-1.0,\n'
    '  "summary": "<one short sentence>",\n'
    '  "findings": [\n'
    "    {{\n"
    '      "category": "<one of the categories above>",\n'
    '      "severity": "low | medium | high",\n'
    '      "evidence": "<short quote from the prose, or the planned element that is missing>",\n'
    '      "fix_hint": "<one concrete instruction for a future revision>"\n'
    "    }}\n"
    "  ]\n"
    "}}\n"
    "\n"
    "Score rubric:\n"
    "  1.00 = no drift; the prose executes the blueprint cleanly.\n"
    "  0.85 = minor drift only (low severity).\n"
    "  0.70 = at least one medium-severity finding.\n"
    "  0.50 = a setpiece is underwritten OR a major promise is unpaid.\n"
    "  0.30 = multiple high-severity findings.\n"
    "Use the integer scale; pick the lowest score that fits.\n"
)


_VALID_SEVERITIES = {"low", "medium", "high"}
_VALID_CATEGORIES = {
    "promise_unpaid",
    "thematic_move_unrealized",
    "tier_underwritten",
    "tier_overwritten",
    "scene_omitted",
    "scene_added",
    "opening_drift",
    "ending_drift",
    "register_drift",
    "pov_drift",
}


def _serialize_blueprint_for_critic(blueprint: Dict[str, Any]) -> Dict[str, Any]:
    """Strip the blueprint down to the fields the critic actually needs."""
    if not isinstance(blueprint, dict):
        return {}
    keep = (
        "opening_approach",
        "chapter_shape",
        "ending_approach",
        "prose_register",
        "tension_level",
        "new_developments",
        "chapter_tier",
        "thematic_move",
        "thematic_move_note",
        "scenes",
        "promises_planted",
        "promises_paid",
        "specific_instructions",
    )
    return {k: blueprint.get(k) for k in keep if k in blueprint}


def _coerce_finding(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    category = str(raw.get("category") or "").strip().lower()
    if category not in _VALID_CATEGORIES:
        return None
    severity = str(raw.get("severity") or "").strip().lower()
    if severity not in _VALID_SEVERITIES:
        severity = "low"
    evidence = str(raw.get("evidence") or "").strip()
    fix_hint = str(raw.get("fix_hint") or "").strip()
    return {
        "category": category,
        "severity": severity,
        "evidence": evidence[:500],
        "fix_hint": fix_hint[:500],
    }


def _coerce_critique(raw: Any) -> Dict[str, Any]:
    """Normalize the critic's raw JSON into a stable shape."""
    if not isinstance(raw, dict):
        return {"score": 1.0, "summary": "", "findings": []}
    try:
        score = float(raw.get("score", 1.0))
    except Exception:
        score = 1.0
    score = max(0.0, min(1.0, score))
    summary = str(raw.get("summary") or "").strip()
    findings_raw = raw.get("findings") or []
    findings: List[Dict[str, Any]] = []
    if isinstance(findings_raw, list):
        for entry in findings_raw:
            normalized = _coerce_finding(entry)
            if normalized:
                findings.append(normalized)
    return {"score": score, "summary": summary[:300], "findings": findings}


async def critique_chapter(
    *,
    orchestrator,
    chapter_number: int,
    chapter_text: str,
    blueprint: Dict[str, Any],
    chapter_text_char_limit: int = 24000,
) -> Dict[str, Any]:
    """Run the plan-compliance critic against a generated chapter.

    Returns the normalized critique dict ``{score, summary, findings}``. On
    any error, returns ``{"score": 1.0, "summary": "", "findings": []}`` —
    the critic NEVER blocks chapter generation.
    """
    if not chapter_text or not blueprint:
        return {"score": 1.0, "summary": "", "findings": []}

    blueprint_for_critic = _serialize_blueprint_for_critic(blueprint)
    if not blueprint_for_critic:
        return {"score": 1.0, "summary": "", "findings": []}

    prose_for_critic = chapter_text
    if len(prose_for_critic) > chapter_text_char_limit:
        # Keep the head and tail — those are where opening/ending drift is
        # easiest to spot, and where the critic is most useful.
        head = prose_for_critic[: chapter_text_char_limit // 2]
        tail = prose_for_critic[-chapter_text_char_limit // 2:]
        prose_for_critic = (
            f"{head}\n\n[... middle of chapter elided for critic budget ...]\n\n{tail}"
        )

    user_prompt = CRITIC_USER_TEMPLATE.format(
        blueprint_json=json.dumps(blueprint_for_critic, ensure_ascii=False, indent=2),
        chapter_text=prose_for_critic,
    )

    try:
        response = await orchestrator._make_api_call(
            messages=[
                {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=12000,
            response_format={"type": "json_object"},
            model_role="editor",
            reasoning_effort="low",
        )
    except Exception as err:
        logger.warning(
            "Plan-compliance critic call failed for Chapter %s: %s",
            chapter_number, err,
        )
        return {"score": 1.0, "summary": "", "findings": []}

    content = ""
    try:
        if hasattr(response, "output_text") and response.output_text:
            content = response.output_text
        elif response and hasattr(response, "choices"):
            content = response.choices[0].message.content or ""
    except Exception:
        content = ""

    if not content:
        logger.warning(
            "Plan-compliance critic returned EMPTY content for Chapter %s — "
            "no drift findings will be emitted. Likely cause: reasoning model "
            "consumed entire token budget on internal reasoning.",
            chapter_number,
        )
        return {"score": 1.0, "summary": "", "findings": []}

    try:
        raw = json.loads(content)
    except Exception as exc:
        snippet = (content or "")[:300].replace("\n", " ")
        logger.warning(
            "Plan-compliance critic returned non-JSON for Chapter %s (%s: %s) — "
            "ignoring. Snippet: %r",
            chapter_number, type(exc).__name__, exc, snippet,
        )
        return {"score": 1.0, "summary": "", "findings": []}

    return _coerce_critique(raw)


def persist_critique(
    project_path: Path,
    chapter_number: int,
    critique: Dict[str, Any],
) -> Path:
    """Write the critique JSON to ``.project-state/chapter-critiques/chapter-NN.json``.

    Returns the path written. Errors are swallowed so the critic never blocks
    chapter generation.
    """
    try:
        critiques_dir = project_path / ".project-state" / "chapter-critiques"
        critiques_dir.mkdir(parents=True, exist_ok=True)
        path = critiques_dir / f"chapter-{chapter_number:02d}.json"
        payload = dict(critique)
        payload["chapter_number"] = chapter_number
        payload["created_at"] = datetime.utcnow().isoformat()
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path
    except Exception as err:
        logger.warning(
            "Failed to persist plan-compliance critique for Chapter %s: %s",
            chapter_number, err,
        )
        return Path()


def reconcile_promises_with_critique(
    *,
    promises_ledger,
    critique: Dict[str, Any],
    chapter_number: int,
) -> List[str]:
    """Roll back ``promises_paid`` claims that the critic found unpaid.

    For each ``promise_unpaid`` finding (severity medium/high) the critic
    raised, find the most recent paid history entry for that chapter and
    revert it to ``open``. Returns the list of promise_ids reverted.

    The critic's evidence string usually contains the promise_id; if not, we
    fall back to reverting the most recent ``paid`` history entry from
    ``chapter_number`` whose label appears in the evidence.
    """
    reverted: List[str] = []
    for finding in critique.get("findings") or []:
        if finding.get("category") != "promise_unpaid":
            continue
        if finding.get("severity") not in {"medium", "high"}:
            continue
        evidence = (finding.get("evidence") or "") + " " + (finding.get("fix_hint") or "")
        evidence_lower = evidence.lower()
        # Prefer explicit ID match (p1, p2, ...).
        target_promise = None
        for promise in promises_ledger.promises:
            pid = str(promise.get("promise_id") or "").lower()
            if pid and pid in evidence_lower:
                target_promise = promise
                break
        if target_promise is None:
            # Fall back to label match.
            for promise in promises_ledger.promises:
                label = str(promise.get("label") or "").strip().lower()
                if not label or len(label) < 3:
                    continue
                if label in evidence_lower:
                    target_promise = promise
                    break
        if target_promise is None:
            continue
        if str(target_promise.get("status") or "").lower() != "paid":
            continue
        target_promise["status"] = "open"
        history = target_promise.setdefault("history", [])
        history.append({
            "ts": datetime.utcnow().isoformat(),
            "chapter": chapter_number,
            "event": "reverted_by_critic",
            "evidence": (finding.get("evidence") or "")[:200],
        })
        reverted.append(str(target_promise.get("promise_id")))
    if reverted:
        promises_ledger.save()
    return reverted


def format_critique_for_next_chapter(
    critique: Dict[str, Any],
    *,
    chapter_number: int,
    max_findings: int = 4,
) -> str:
    """Render a short hint block for the NEXT chapter's planner.

    Surfaces only medium/high severity findings (low-severity surface drift
    isn't worth burning planner tokens on). Returns an empty string if there
    is nothing actionable to report.
    """
    findings = [
        f for f in (critique.get("findings") or [])
        if f.get("severity") in {"medium", "high"}
    ]
    if not findings:
        return ""
    lines = [
        f"PRIOR-CHAPTER DRIFT (from Chapter {chapter_number} plan-compliance critique):",
    ]
    for finding in findings[:max_findings]:
        lines.append(
            f"  - [{finding.get('severity')}] {finding.get('category')}: "
            f"{finding.get('fix_hint') or finding.get('evidence') or ''}"
        )
    lines.append(
        "  When the prior chapter dropped a beat, the next chapter MUST acknowledge "
        "or recover from that drift on-page (don't pretend it didn't happen)."
    )
    return "\n".join(lines)
