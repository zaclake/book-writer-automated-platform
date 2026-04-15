#!/usr/bin/env python3
"""
Chapter Ledger Service
Builds and updates a concise chapter delta ledger after generation.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.database_integration import create_reference_file, update_reference_file, get_project_reference_files
from backend.services.vector_store_service import VectorStoreService
from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig

logger = logging.getLogger(__name__)

LEDGER_FILENAME = "chapter-ledger.md"

LEDGER_TRIM_SIZE = int(os.getenv("LEDGER_TRIM_SIZE", "2000"))
LEDGER_MAX_CHAPTER_SECTIONS = int(os.getenv("LEDGER_MAX_CHAPTER_SECTIONS", "80"))

_PROPER_NOUN_RE = re.compile(r"\b[A-Z][a-z]{2,}\b")
_PROPER_NOUN_STOP = {
    "Chapter", "POV", "Summary", "Carry", "Forward", "Unresolved", "Threads",
    "New", "Facts", "Changes", "Relationship", "Shifts", "Time", "Markers",
    "Location", "Updates", "Event", "Character", "Type", "Notes",
}


def _approved_terms_set(orchestrator: LLMOrchestrator, book_bible: str, ref_excerpt: str, director_notes: str) -> set[str]:
    """Return a lowercase set of approved proper terms."""
    try:
        getter = getattr(orchestrator, "_get_approved_terms", None)
        if callable(getter):
            terms = getter(book_bible or "", ref_excerpt or "", director_notes or "")
            if isinstance(terms, list):
                return {str(t).strip().lower() for t in terms if str(t).strip()}
    except Exception:
        pass
    # Fallback: extract capitalized tokens from inputs.
    raw = "\n".join([book_bible or "", ref_excerpt or "", director_notes or ""])
    return {m.group(0).strip().lower() for m in _PROPER_NOUN_RE.finditer(raw) if m.group(0)}


def _sanitize_text(text: str) -> str:
    if not text:
        return ""
    t = str(text).replace("\r\n", "\n").replace("\r", "\n")
    for dash in ("—", "–", "―", "‒", "‑"):
        t = t.replace(dash, ", ")
    return t.strip()


def _unknown_proper_nouns(text: str, approved: set[str]) -> list[str]:
    if not text:
        return []
    unknown: list[str] = []
    for match in _PROPER_NOUN_RE.finditer(text):
        token = match.group(0)
        if not token or token in _PROPER_NOUN_STOP:
            continue
        low = token.lower()
        if low not in approved and low not in unknown:
            unknown.append(low)
    return unknown


def _validate_and_sanitize_ledger_entry(entry: Dict[str, Any], approved_terms: set[str]) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Deterministically validate + sanitize a ledger entry.
    Returns (sanitized_entry, validation_report).
    Raises ValueError on severe invalid shapes.
    """
    if not isinstance(entry, dict):
        raise ValueError("ledger_entry_not_object")

    report: Dict[str, Any] = {"passed": True, "warnings": [], "unknown_proper_nouns": []}

    def _coerce_list(value: Any, *, max_items: int = 10, max_item_chars: int = 180) -> list[str]:
        items: list[str] = []
        if isinstance(value, list):
            for item in value:
                text = _sanitize_text(item)
                if text:
                    items.append(_sanitize_text(text)[:max_item_chars])
        return items[:max_items]

    summary = _sanitize_text(entry.get("summary", ""))[:900]
    carry_forward = _coerce_list(entry.get("carry_forward", []), max_items=10)
    unresolved_threads = _coerce_list(entry.get("unresolved_threads", []), max_items=10)
    changes = _coerce_list(entry.get("changes", []), max_items=10)
    relationship_shifts = _coerce_list(entry.get("relationship_shifts", []), max_items=10)
    time_markers = _coerce_list(entry.get("time_markers", []), max_items=8)
    location_updates = _coerce_list(entry.get("location_updates", []), max_items=8)

    pov_raw = entry.get("pov", {}) or {}
    pov: Dict[str, str] = {}
    if isinstance(pov_raw, dict):
        pov["character"] = _sanitize_text(pov_raw.get("character") or pov_raw.get("name") or "")[:80]
        pov["type"] = _sanitize_text(pov_raw.get("type") or pov_raw.get("pov_type") or "")[:40]
        pov["notes"] = _sanitize_text(pov_raw.get("notes") or "")[:240]

    # Proper noun guard: if we see too many unknown proper nouns, refuse to write.
    unknown = []
    blobs = [summary] + carry_forward + unresolved_threads + changes + relationship_shifts + time_markers + location_updates
    for blob in blobs:
        unknown.extend(_unknown_proper_nouns(blob, approved_terms))
        if len(unknown) >= 20:
            break
    unknown = list(dict.fromkeys(unknown))
    if len(unknown) >= 30:
        report["passed"] = False
        report["unknown_proper_nouns"] = unknown[:30]
        raise ValueError("ledger_unknown_proper_nouns")
    elif len(unknown) >= 12:
        report["warnings"].append(f"high_unknown_proper_noun_count ({len(unknown)})")
        report["unknown_proper_nouns"] = unknown[:20]

    sanitized = {
        "summary": summary,
        "carry_forward": carry_forward,
        "unresolved_threads": unresolved_threads,
        "changes": changes,
        "relationship_shifts": relationship_shifts,
        "time_markers": time_markers,
        "location_updates": location_updates,
        "pov": {k: v for k, v in pov.items() if v},
    }
    return sanitized, report


def _prune_markdown_chapter_sections(text: str, *, keep_last: int, header_prefix: str) -> str:
    """
    Keep only the last N markdown sections matching '## Chapter X', preserving the header_prefix.
    """
    if not text or keep_last <= 0:
        return (header_prefix.strip() + "\n") if header_prefix else ""

    t = text.strip()
    sections = re.split(r"(?m)^(?=##\s+Chapter\s+\d+\s*$)", t)
    kept = [s for s in sections if s.strip()]
    chapter_sections = [s for s in kept if re.match(r"(?m)^##\s+Chapter\s+\d+\s*$", s)]
    if not chapter_sections:
        body = t
    else:
        body = "\n\n".join(chapter_sections[-keep_last:]).strip()

    if header_prefix:
        header = header_prefix.strip()
        if not header.endswith("\n"):
            header += "\n"
        return (header + "\n" + body.strip() + "\n").strip() + "\n"
    return body.strip() + "\n"


def _extract_json_block(text: str) -> Optional[Dict[str, Any]]:
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


def _render_chapter_ledger_markdown(entry: Dict[str, Any], chapter_number: int) -> str:
    summary = entry.get("summary", "")
    carry_forward = entry.get("carry_forward", []) or []
    unresolved_threads = entry.get("unresolved_threads", []) or []
    changes = entry.get("changes", []) or []
    relationship_shifts = entry.get("relationship_shifts", []) or []
    time_markers = entry.get("time_markers", []) or []
    location_updates = entry.get("location_updates", []) or []
    pov = entry.get("pov", {}) or {}

    lines: List[str] = []
    lines.append(f"## Chapter {chapter_number}")
    if summary:
        lines.append("")
        lines.append("### Summary")
        lines.append(summary.strip())
    if carry_forward:
        lines.append("")
        lines.append("### Carry Forward")
        for item in carry_forward:
            lines.append(f"- {str(item).strip()}")
    if unresolved_threads:
        lines.append("")
        lines.append("### Unresolved Threads")
        for item in unresolved_threads:
            lines.append(f"- {str(item).strip()}")
    if changes:
        lines.append("")
        lines.append("### New Facts or Changes")
        for item in changes:
            lines.append(f"- {str(item).strip()}")
    if relationship_shifts:
        lines.append("")
        lines.append("### Relationship Shifts")
        for item in relationship_shifts:
            lines.append(f"- {str(item).strip()}")
    if time_markers:
        lines.append("")
        lines.append("### Time Markers")
        for item in time_markers:
            lines.append(f"- {str(item).strip()}")
    if location_updates:
        lines.append("")
        lines.append("### Location Updates")
        for item in location_updates:
            lines.append(f"- {str(item).strip()}")
    if pov:
        lines.append("")
        lines.append("### POV")
        character = pov.get("character") or pov.get("name") or ""
        pov_type = pov.get("type") or pov.get("pov_type") or ""
        notes = pov.get("notes") or ""
        if character:
            lines.append(f"- Character: {character}")
        if pov_type:
            lines.append(f"- Type: {pov_type}")
        if notes:
            lines.append(f"- Notes: {notes}")

    return "\n".join(lines).strip() + "\n"


async def _generate_ledger_entry(
    chapter_number: int,
    chapter_content: str,
    book_bible: str,
    references: Dict[str, str],
    prior_ledger: str,
    pov_context: Optional[Dict[str, Any]] = None,
    vector_store_ids: Optional[List[str]] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    if not isinstance(references, dict):
        logger.warning("Ledger references not dict; coercing to empty dict.")
        references = {}
    enable_billing = os.getenv('ENABLE_CREDITS_BILLING', 'false').lower() == 'true'
    orchestrator = LLMOrchestrator(
        retry_config=RetryConfig(max_retries=2),
        user_id=user_id,
        enable_billing=enable_billing
    )

    ref_excerpt = ""
    used = 0
    for name, content in references.items():
        if used >= 2000:
            break
        if not content:
            continue
        excerpt = content[:400].replace("\n", " ")
        ref_excerpt += f"{name}: {excerpt}\n"
        used += len(excerpt)

    pov_label = ""
    if pov_context:
        character = pov_context.get("pov_character", "")
        pov_type = pov_context.get("pov_type", "")
        if character or pov_type:
            pov_label = f"POV PLAN: {character} ({pov_type})"

    system_prompt = (
        "You are a continuity librarian for a novel. Extract a concise chapter delta ledger.\n"
        "Use only the supplied chapter content and references. Do not invent facts.\n"
        "Return STRICT JSON only with keys: summary, carry_forward, unresolved_threads, changes, "
        "relationship_shifts, time_markers, location_updates, pov.\n"
        "Keep items concise and specific.\n"
    )

    user_prompt = (
        f"{pov_label}\n"
        f"BOOK BIBLE:\n{book_bible[:2000]}\n\n"
        f"REFERENCE EXCERPTS:\n{ref_excerpt or 'None'}\n"
        f"PRIOR LEDGER:\n{prior_ledger[-LEDGER_TRIM_SIZE:] if prior_ledger else 'None'}\n\n"
        f"CHAPTER {chapter_number} CONTENT:\n{chapter_content[:8000]}\n\n"
        "Extract the chapter delta ledger now."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    response = await orchestrator._make_api_call(
        messages=messages,
        temperature=0.2,
        max_tokens=900,
        response_format={"type": "json_object"},
        vector_store_ids=vector_store_ids or [],
        use_file_search=bool(vector_store_ids)
    )
    content, _usage = orchestrator._extract_content_and_usage(response)
    parsed = _extract_json_block(content)
    if not parsed:
        raise ValueError("Chapter ledger extraction failed to return valid JSON")
    approved = _approved_terms_set(orchestrator, book_bible[:2500] if book_bible else "", ref_excerpt, pov_label)
    sanitized, _report = _validate_and_sanitize_ledger_entry(parsed, approved)
    return sanitized


async def update_chapter_ledger(
    project_id: str,
    user_id: str,
    chapter_number: int,
    chapter_content: str,
    book_bible: str,
    references: Dict[str, str],
    pov_context: Optional[Dict[str, Any]] = None,
    vector_store_ids: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Update chapter-ledger.md reference file and vector memory after a chapter."""
    try:
        if not isinstance(references, dict):
            logger.warning("Chapter ledger references not dict; skipping reference extract.")
            references = {}
        existing_refs = await get_project_reference_files(project_id)
        prior_ledger = ""
        for ref in existing_refs:
            if not isinstance(ref, dict):
                logger.warning("Chapter ledger reference entry not dict; skipping.")
                continue
            if (ref.get("filename") or "").lower() == LEDGER_FILENAME:
                prior_ledger = ref.get("content", "")
                break

        entry = await _generate_ledger_entry(
            chapter_number=chapter_number,
            chapter_content=chapter_content,
            book_bible=book_bible,
            references=references,
            prior_ledger=prior_ledger,
            pov_context=pov_context,
            vector_store_ids=vector_store_ids,
            user_id=user_id
        )

        header = "# Chapter Ledger\n\n"
        timestamp = datetime.now(timezone.utc).isoformat()
        new_section = _render_chapter_ledger_markdown(entry, chapter_number)
        combined = prior_ledger.strip()
        if not combined:
            combined = header + f"_Last updated: {timestamp}_\n\n" + new_section
        else:
            combined = combined.rstrip() + "\n\n" + new_section

        # Prune to last N chapter sections to prevent unbounded growth.
        combined = _prune_markdown_chapter_sections(
            combined,
            keep_last=LEDGER_MAX_CHAPTER_SECTIONS,
            header_prefix="# Chapter Ledger\n",
        )

        updated = await update_reference_file(project_id, LEDGER_FILENAME, combined, user_id)
        if not updated:
            await create_reference_file(project_id, LEDGER_FILENAME, combined, user_id)

        try:
            vector_service = VectorStoreService()
            await vector_service.upsert_reference_file(
                project_id=project_id,
                user_id=user_id,
                filename=LEDGER_FILENAME,
                content=combined,
                file_type="chapter_ledger"
            )
        except Exception as vector_err:
            logger.warning(f"Failed to update chapter ledger vector memory: {vector_err}")

        return {"success": True, "entry": entry, "content": combined}
    except Exception as e:
        logger.error(f"Chapter ledger update failed for project {project_id}: {e}")
        return {"success": False, "error": str(e)}


def update_local_chapter_ledger(project_path: str, entry: Dict[str, Any], chapter_number: int) -> None:
    """Persist chapter ledger to local project state for continuity tooling."""
    state_dir = Path(project_path) / ".project-state"
    state_dir.mkdir(parents=True, exist_ok=True)

    ledger_md_path = state_dir / LEDGER_FILENAME
    ledger_json_path = state_dir / "chapter-ledger.json"

    prior_md = ""
    if ledger_md_path.exists():
        try:
            prior_md = ledger_md_path.read_text(encoding="utf-8")
        except Exception:
            prior_md = ""

    header = "# Chapter Ledger\n\n"
    timestamp = datetime.now(timezone.utc).isoformat()
    new_section = _render_chapter_ledger_markdown(entry, chapter_number)
    combined = prior_md.strip()
    if not combined:
        combined = header + f"_Last updated: {timestamp}_\n\n" + new_section
    else:
        combined = combined.rstrip() + "\n\n" + new_section
    ledger_md_path.write_text(combined, encoding="utf-8")

    json_payload: Dict[str, Any] = {}
    if ledger_json_path.exists():
        try:
            json_payload = json.loads(ledger_json_path.read_text(encoding="utf-8"))
        except Exception:
            json_payload = {}
    json_payload.setdefault("entries", {})
    json_payload["entries"][str(chapter_number)] = entry
    json_payload["last_updated"] = datetime.now(timezone.utc).isoformat()
    ledger_json_path.write_text(json.dumps(json_payload, indent=2, ensure_ascii=False), encoding="utf-8")
