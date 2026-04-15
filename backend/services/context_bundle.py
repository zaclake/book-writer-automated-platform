"""
Context bundle utilities.

Purpose:
- Unify context packaging across workflows (auto-complete and over-time chapter generation).
- Apply hard caps to reduce token bloat and latency.
- Encode a canonical hierarchy of truth in the context fields:
  book_bible > canon_log > chapter_ledger > plan > vector_hints

This module does NOT generate prompts; it standardizes the context dict that prompt builders consume.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

try:
    from backend.services.chapter_context_builder import normalize_references, get_canon_log
except Exception:  # pragma: no cover
    from .chapter_context_builder import normalize_references, get_canon_log  # type: ignore

try:
    from backend.utils.run_summaries import text_stats
except Exception:  # pragma: no cover
    from ..utils.run_summaries import text_stats  # type: ignore


def _trim(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _canonical_ref_key(key: str) -> str:
    """Reduce a reference key to its canonical form for dedup."""
    k = key.lower().replace("-", "_")
    if k.endswith(".md"):
        k = k[:-3]
    return k


def _trim_references(
    references: Dict[str, str],
    *,
    per_ref_limit: int = 8000,
    max_total_chars: int = 80_000,
) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """
    Trim each reference file and the overall combined reference payload.

    Uses canonical dedup so that alias keys (e.g. ``characters`` and
    ``characters.md``) don't cause the same content to appear twice.
    """
    normalized = normalize_references(references or {})

    # Preferred keys control ordering.  Only one key per canonical form
    # is kept; the first match wins.
    preferred_order = [
        "characters",
        "outline",
        "plot_timeline",
        "world_building",
        "style_guide",
        "entity_registry",
        "relationship_map",
        "chapter-ledger",
        "canon-log",
    ]

    items: list[tuple[str, str]] = []
    seen_canonical: set[str] = set()

    for key in preferred_order:
        canonical = _canonical_ref_key(key)
        if canonical in seen_canonical:
            continue
        value = normalized.get(key) or ""
        if not value:
            # Try common alias forms (both dash-to-underscore and underscore-to-dash)
            for alt in (
                key.replace("_", "-"),
                key.replace("-", "_"),
                f"{key}.md",
                key.replace("_", "-") + ".md",
                key.replace("-", "_") + ".md",
            ):
                value = normalized.get(alt) or ""
                if value:
                    break
        if not value:
            continue
        seen_canonical.add(canonical)
        items.append((key, value))

    for key, value in normalized.items():
        canonical = _canonical_ref_key(key)
        if canonical in seen_canonical:
            continue
        if not value:
            continue
        seen_canonical.add(canonical)
        items.append((key, value))

    trimmed: Dict[str, str] = {}
    used = 0
    for key, value in items:
        if used >= max_total_chars:
            break
        chunk = _trim(value, per_ref_limit)
        remaining = max_total_chars - used
        if remaining <= 0:
            break
        if len(chunk) > remaining:
            chunk = _trim(chunk, remaining)
        trimmed[key] = chunk
        used += len(chunk)

    stats = {
        "total_chars": used,
        "file_count": len(trimmed),
    }
    return trimmed, stats


def normalize_generation_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a normalized, size-bounded generation context dict.

    This function is safe to call multiple times.
    """
    ctx = dict(context or {})

    # Primary truth sources (bounded).
    book_bible = _trim(str(ctx.get("book_bible") or ""), 80_000)
    ctx["book_bible"] = book_bible

    # Canon + ledger fields are expected across flows. Keep as concise snapshots.
    ctx["canon_log_reference"] = _trim(str(ctx.get("canon_log_reference") or ""), 20_000)
    ctx["chapter_ledger_summary"] = _trim(str(ctx.get("chapter_ledger_summary") or ""), 8_000)

    # Plan fields (bounded).
    ctx["chapter_plan_summary"] = _trim(str(ctx.get("chapter_plan_summary") or ""), 4_000)
    ctx["chapter_contract"] = _trim(str(ctx.get("chapter_contract") or ""), 6_000)

    # Vector hints are explicitly untrusted: clamp and label.
    ctx["vector_context"] = _trim(str(ctx.get("vector_context") or ctx.get("vector_memory_context") or ""), 4_000)
    ctx["vector_guidelines"] = _trim(str(ctx.get("vector_guidelines") or ctx.get("vector_memory_guidelines") or ""), 2_800)

    # References dictionary (bounded + normalized).
    refs = ctx.get("references")
    if isinstance(refs, dict):
        trimmed_refs, ref_stats = _trim_references(refs)
        ctx["references"] = trimmed_refs
        # Keep canon/ledger convenience fields aligned with references when missing.
        if not ctx.get("canon_log_reference"):
            ctx["canon_log_reference"] = _trim(get_canon_log(trimmed_refs), 20_000)
        if not ctx.get("chapter_ledger_summary"):
            # Ledger is a full reference file; keep only latest summary if caller already provides it.
            ledger = (
                trimmed_refs.get("chapter-ledger.md")
                or trimmed_refs.get("chapter_ledger.md")
                or trimmed_refs.get("chapter-ledger")
                or trimmed_refs.get("chapter_ledger")
                or ""
            )
            ctx["chapter_ledger_summary"] = _trim(ledger, 8_000)
        ctx.setdefault("context_digests", {})
        ctx["context_digests"]["references"] = ref_stats

    # Add digests (no content) for run summaries / debugging.
    ctx.setdefault("context_digests", {})
    ctx["context_digests"].update(
        {
            "book_bible": text_stats(book_bible),
            "canon_log": text_stats(str(ctx.get("canon_log_reference") or "")),
            "chapter_ledger": text_stats(str(ctx.get("chapter_ledger_summary") or "")),
            "vector_context": text_stats(str(ctx.get("vector_context") or "")),
        }
    )

    # Make hierarchy explicit for downstream prompt builders.
    ctx["context_hierarchy"] = [
        "book_bible",
        "canon_log_reference",
        "chapter_ledger_summary",
        "chapter_plan_summary",
        "vector_context",
    ]

    return ctx

