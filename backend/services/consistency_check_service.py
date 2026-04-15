#!/usr/bin/env python3
"""
Consistency Check Service
Detects canon and continuity contradictions and proposes corrective guidance.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    payload = cleaned[start:end + 1]
    try:
        return json.loads(payload)
    except Exception:
        return None


async def check_chapter_consistency(
    chapter_number: int,
    chapter_content: str,
    book_bible: str,
    references: Dict[str, str],
    canon_log: str,
    vector_store_ids: Optional[List[str]] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """Return consistency issues and a rewrite instruction when needed."""
    enable_billing = os.getenv('ENABLE_CREDITS_BILLING', 'false').lower() == 'true'
    orchestrator = LLMOrchestrator(
        retry_config=RetryConfig(max_retries=2),
        user_id=user_id,
        enable_billing=enable_billing
    )

    def _focused_excerpt(content: str, limit: int = 2000) -> str:
        """Extract the most relevant portion of a reference."""
        if not content:
            return ""
        if len(content) <= limit:
            return content
        return content[:limit]

    def _canonical_key(key: str) -> str:
        """Normalize to a single canonical form for dedup (lowercase, underscores, no .md)."""
        k = key.lower().replace("-", "_")
        if k.endswith(".md"):
            k = k[:-3]
        return k

    # Priority order uses canonical forms for dedup; we look up both
    # dash and underscore variants in the references dict.
    priority_refs = [
        ("entity_registry", ["entity-registry", "entity_registry", "entity-registry.md", "entity_registry.md"]),
        ("characters", ["characters", "characters.md"]),
        ("world_building", ["world-building", "world_building", "world-building.md", "world_building.md"]),
        ("outline", ["outline", "outline.md"]),
        ("plot_timeline", ["plot-timeline", "plot_timeline", "plot-timeline.md", "plot_timeline.md"]),
        ("relationship_map", ["relationship-map", "relationship_map", "relationship-map.md", "relationship_map.md"]),
    ]

    ref_excerpt = ""
    used = 0
    budget = 6000
    seen_canonical = set()

    for canonical, lookup_keys in priority_refs:
        if used >= budget:
            break
        if canonical in seen_canonical:
            continue
        content = ""
        display_key = canonical
        for lk in lookup_keys:
            content = references.get(lk, "")
            if content:
                display_key = lk
                break
        if not content:
            continue
        seen_canonical.add(canonical)
        per_ref_limit = 2500 if "entity" in canonical or "character" in canonical else 1500
        excerpt = _focused_excerpt(content, per_ref_limit)
        header = f"\n--- {display_key} ---\n"
        ref_excerpt += f"{header}{excerpt}\n"
        used += len(excerpt) + len(header)

    for name, content in references.items():
        if used >= budget:
            break
        canonical = _canonical_key(name)
        if canonical in seen_canonical or not content:
            continue
        seen_canonical.add(canonical)
        excerpt = _focused_excerpt(content, 800)
        header = f"\n--- {name} ---\n"
        ref_excerpt += f"{header}{excerpt}\n"
        used += len(excerpt) + len(header)

    system_prompt = (
        "You are a continuity editor for a novel.\n"
        "Check the chapter for contradictions with canon, book bible, or references.\n"
        "Pay special attention to: proper noun spellings, character knowledge state "
        "(characters should not reference information they haven't learned yet), "
        "world rules violations, and timeline inconsistencies.\n"
        "Return STRICT JSON with keys: issues, severity, rewrite_instruction.\n"
        "issues: array of brief strings.\n"
        "severity: one of low|medium|high.\n"
        "rewrite_instruction: short, precise instruction to fix issues (empty if none).\n"
        "Do not invent facts.\n"
    )

    user_prompt = (
        f"BOOK BIBLE:\n{book_bible[:3000]}\n\n"
        f"REFERENCE EXCERPTS:\n{ref_excerpt or 'None'}\n"
        f"CANON LOG (recent):\n{canon_log[-2500:] if canon_log else 'None'}\n\n"
        f"CHAPTER {chapter_number} CONTENT:\n{chapter_content[:8000]}\n\n"
        "Identify contradictions or continuity breaks."
    )

    response = await orchestrator._make_api_call(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2,
        max_tokens=600,
        response_format={"type": "json_object"},
        vector_store_ids=vector_store_ids or [],
        use_file_search=bool(vector_store_ids)
    )
    content, _usage = orchestrator._extract_content_and_usage(response)
    parsed = _extract_json(content) or {}
    issues = parsed.get("issues") or []
    severity = (parsed.get("severity") or "low").lower()
    rewrite_instruction = (parsed.get("rewrite_instruction") or "").strip()
    if not isinstance(issues, list):
        issues = []
    if severity not in {"low", "medium", "high"}:
        severity = "low"

    return {
        "issues": issues,
        "severity": severity,
        "rewrite_instruction": rewrite_instruction
    }
