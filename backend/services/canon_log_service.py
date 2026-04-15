#!/usr/bin/env python3
"""
Canon Log Service
Builds and updates a canonical fact/timeline ledger after chapter generation.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.database_integration import create_reference_file, update_reference_file, get_project_reference_files
from backend.services.vector_store_service import VectorStoreService
from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig

logger = logging.getLogger(__name__)

_PROPER_NOUN_RE = re.compile(r"\b[A-Z][a-z]{2,}\b")
_PROPER_NOUN_STOP = {
    "Chapter", "Canon", "Log", "Summary", "Timeline", "Events", "Event",
    "Facts", "Character", "Updates", "World", "Unresolved", "Threads",
}

CANON_LOG_TRIM_SIZE = int(os.getenv("CANON_LOG_TRIM_SIZE", "2000"))
CANON_LOG_MAX_CHAPTER_SECTIONS = int(os.getenv("CANON_LOG_MAX_CHAPTER_SECTIONS", "60"))


def _approved_terms_set(orchestrator: LLMOrchestrator, book_bible: str, ref_excerpt: str) -> set[str]:
    try:
        getter = getattr(orchestrator, "_get_approved_terms", None)
        if callable(getter):
            terms = getter(book_bible or "", ref_excerpt or "", "")
            if isinstance(terms, list):
                return {str(t).strip().lower() for t in terms if str(t).strip()}
    except Exception:
        pass
    raw = "\n".join([book_bible or "", ref_excerpt or ""])
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


def _validate_and_sanitize_canon_entry(entry: Dict[str, Any], approved_terms: set[str]) -> Dict[str, Any]:
    if not isinstance(entry, dict):
        raise ValueError("canon_entry_not_object")

    def _coerce_list(value: Any, *, max_items: int = 12, max_item_chars: int = 200) -> list[str]:
        items: list[str] = []
        if isinstance(value, list):
            for item in value:
                text = _sanitize_text(item)
                if text:
                    items.append(text[:max_item_chars])
        return items[:max_items]

    summary = _sanitize_text(entry.get("summary", ""))[:900]
    canon_facts = _coerce_list(entry.get("canon_facts", []), max_items=12)
    world_updates = _coerce_list(entry.get("world_updates", []), max_items=10)
    unresolved_threads = _coerce_list(entry.get("unresolved_threads", []), max_items=12)

    timeline_events_raw = entry.get("timeline_events", []) or []
    timeline_events: list[Dict[str, str]] = []
    if isinstance(timeline_events_raw, list):
        for item in timeline_events_raw[:12]:
            if isinstance(item, dict):
                time_label = _sanitize_text(item.get("time") or item.get("timestamp") or "")[:60]
                event_text = _sanitize_text(item.get("event") or item.get("detail") or "")[:220]
                if time_label or event_text:
                    timeline_events.append({"time": time_label or "Event", "event": event_text})
            else:
                text = _sanitize_text(item)[:220]
                if text:
                    timeline_events.append({"time": "Event", "event": text})

    character_updates_raw = entry.get("character_updates", []) or []
    character_updates: list[Dict[str, str]] = []
    if isinstance(character_updates_raw, list):
        for item in character_updates_raw[:12]:
            if isinstance(item, dict):
                name = _sanitize_text(item.get("character") or item.get("name") or "")[:80]
                update = _sanitize_text(item.get("update") or item.get("change") or "")[:240]
                if name or update:
                    character_updates.append({"character": name or "Character", "update": update})
            else:
                text = _sanitize_text(item)[:240]
                if text:
                    character_updates.append({"character": "Character", "update": text})

    # Proper noun guard: too many unknown proper nouns = reject (prevents context poisoning).
    unknown: list[str] = []
    blobs = [summary] + canon_facts + world_updates + unresolved_threads
    blobs += [e.get("event", "") for e in timeline_events] + [u.get("update", "") for u in character_updates]
    for blob in blobs:
        unknown.extend(_unknown_proper_nouns(blob, approved_terms))
        if len(unknown) >= 20:
            break
    unknown = list(dict.fromkeys(unknown))
    if len(unknown) >= 30:
        try:
            logger.warning(
                "Canon entry rejected: too many unapproved proper nouns "
                f"(count={len(unknown)}). Skipping canon update for this chapter."
            )
        except Exception:
            pass
        return {
            "summary": "Canon update skipped: too many unapproved proper nouns detected in the extracted canon.",
            "timeline_events": [],
            "canon_facts": [],
            "character_updates": [],
            "world_updates": [],
            "unresolved_threads": [],
        }
    elif len(unknown) >= 12:
        try:
            logger.info(
                f"Canon entry has {len(unknown)} unapproved proper nouns; proceeding with caution."
            )
        except Exception:
            pass

    return {
        "summary": summary,
        "timeline_events": timeline_events,
        "canon_facts": canon_facts,
        "character_updates": character_updates,
        "world_updates": world_updates,
        "unresolved_threads": unresolved_threads,
    }


def _prune_markdown_chapter_sections(text: str, *, keep_last: int, header_prefix: str) -> str:
    """
    Keep only the last N markdown sections matching '## Chapter X', preserving the header_prefix.
    """
    if not text or keep_last <= 0:
        return (header_prefix.strip() + "\n") if header_prefix else ""

    t = text.strip()
    # Normalize header at top.
    if header_prefix and not t.startswith(header_prefix.strip()):
        # If missing header, prepend later.
        pass

    sections = re.split(r"(?m)^(?=##\s+Chapter\s+\d+\s*$)", t)
    kept = [s for s in sections if s.strip()]
    chapter_sections = [s for s in kept if re.match(r"(?m)^##\s+Chapter\s+\d+\s*$", s)]
    # If split didn't isolate headers correctly, fall back to original.
    if not chapter_sections:
        body = t
    else:
        body = "\n\n".join(chapter_sections[-keep_last:]).strip()

    if header_prefix:
        header = header_prefix.strip()
        if not header.endswith("\n"):
            header += "\n"
        # Ensure a single blank line between header and first section.
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


def _render_canon_markdown(entry: Dict[str, Any], chapter_number: int) -> str:
    summary = entry.get("summary", "")
    timeline_events = entry.get("timeline_events", []) or []
    canon_facts = entry.get("canon_facts", []) or []
    character_updates = entry.get("character_updates", []) or []
    world_updates = entry.get("world_updates", []) or []
    unresolved_threads = entry.get("unresolved_threads", []) or []

    lines: List[str] = []
    lines.append(f"## Chapter {chapter_number}")
    if summary:
        lines.append("")
        lines.append("### Summary")
        lines.append(summary.strip())
    if timeline_events:
        lines.append("")
        lines.append("### Timeline Events")
        for event in timeline_events:
            if isinstance(event, dict):
                label = event.get("time") or event.get("timestamp") or "Event"
                detail = event.get("event") or event.get("detail") or ""
                lines.append(f"- {label}: {detail}".strip())
            else:
                lines.append(f"- {str(event).strip()}")
    if canon_facts:
        lines.append("")
        lines.append("### Canon Facts")
        for fact in canon_facts:
            lines.append(f"- {str(fact).strip()}")
    if character_updates:
        lines.append("")
        lines.append("### Character Updates")
        for update in character_updates:
            if isinstance(update, dict):
                name = update.get("character") or update.get("name") or "Character"
                change = update.get("update") or update.get("change") or ""
                lines.append(f"- {name}: {change}".strip())
            else:
                lines.append(f"- {str(update).strip()}")
    if world_updates:
        lines.append("")
        lines.append("### World Updates")
        for update in world_updates:
            lines.append(f"- {str(update).strip()}")
    if unresolved_threads:
        lines.append("")
        lines.append("### Unresolved Threads")
        for thread in unresolved_threads:
            lines.append(f"- {str(thread).strip()}")

    return "\n".join(lines).strip() + "\n"


async def _generate_canon_entry(
    chapter_number: int,
    chapter_content: str,
    book_bible: str,
    references: Dict[str, str],
    prior_canon: str,
    vector_store_ids: Optional[List[str]] = None,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
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

    system_prompt = (
        "You are a canon librarian for a novel. Extract canon updates for one chapter.\n"
        "Use only the supplied chapter content and references. Do not invent facts.\n"
        "Return STRICT JSON only with keys: summary, timeline_events, canon_facts, "
        "character_updates, world_updates, unresolved_threads.\n"
        "timeline_events should be an array of objects with keys: time, event.\n"
        "character_updates should be an array of objects with keys: character, update.\n"
        "Keep each field concise and precise.\n"
    )

    user_prompt = (
        f"BOOK BIBLE:\n{book_bible[:2000]}\n\n"
        f"REFERENCE EXCERPTS:\n{ref_excerpt or 'None'}\n"
        f"PRIOR CANON LOG:\n{prior_canon[-CANON_LOG_TRIM_SIZE:] if prior_canon else 'None'}\n\n"
        f"CHAPTER {chapter_number} CONTENT:\n{chapter_content[:8000]}\n\n"
        "Extract canon updates now."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    response = await orchestrator._make_api_call(
        messages=messages,
        temperature=0.2,
        max_tokens=1000,
        response_format={"type": "json_object"},
        vector_store_ids=vector_store_ids or [],
        use_file_search=bool(vector_store_ids)
    )
    content, _usage = orchestrator._extract_content_and_usage(response)
    parsed = _extract_json_block(content)
    if not parsed:
        raise ValueError("Canon extraction failed to return valid JSON")
    approved = _approved_terms_set(orchestrator, book_bible[:2500] if book_bible else "", ref_excerpt)
    return _validate_and_sanitize_canon_entry(parsed, approved)


async def update_canon_log(
    project_id: str,
    user_id: str,
    chapter_number: int,
    chapter_content: str,
    book_bible: str,
    references: Dict[str, str],
    vector_store_ids: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Update canon log reference file and vector memory after a chapter."""
    try:
        existing_refs = await get_project_reference_files(project_id)
        canon_filename = "canon-log.md"
        prior_canon = ""
        for ref in existing_refs:
            if (ref.get("filename") or "").lower() == canon_filename:
                prior_canon = ref.get("content", "")
                break

        entry = await _generate_canon_entry(
            chapter_number=chapter_number,
            chapter_content=chapter_content,
            book_bible=book_bible,
            references=references,
            prior_canon=prior_canon,
            vector_store_ids=vector_store_ids,
            user_id=user_id
        )

        header = "# Canon Log\n\n"
        timestamp = datetime.now(timezone.utc).isoformat()
        new_section = _render_canon_markdown(entry, chapter_number)
        combined = prior_canon.strip()
        if not combined:
            combined = header + f"_Last updated: {timestamp}_\n\n" + new_section
        else:
            combined = combined.rstrip() + "\n\n" + new_section

        # Prune to last N chapter sections to prevent unbounded growth.
        combined = _prune_markdown_chapter_sections(
            combined,
            keep_last=CANON_LOG_MAX_CHAPTER_SECTIONS,
            header_prefix="# Canon Log\n",
        )

        updated = await update_reference_file(project_id, canon_filename, combined, user_id)
        if not updated:
            await create_reference_file(project_id, canon_filename, combined, user_id)

        try:
            vector_service = VectorStoreService()
            await vector_service.upsert_reference_file(
                project_id=project_id,
                user_id=user_id,
                filename=canon_filename,
                content=combined,
                file_type="canon_log"
            )
        except Exception as vector_err:
            logger.warning(f"Failed to update canon log vector memory: {vector_err}")

        return {"success": True, "entry": entry, "content": combined}
    except Exception as e:
        logger.error(f"Canon log update failed for project {project_id}: {e}")
        return {"success": False, "error": str(e)}


async def append_manual_canon_update(
    project_id: str,
    user_id: str,
    source_type: str,
    source_label: str,
    source_content: str,
    instructions: str = ""
) -> Dict[str, Any]:
    """Append a manual canon update entry to canon-log.md and reindex."""
    try:
        existing_refs = await get_project_reference_files(project_id)
        canon_filename = "canon-log.md"
        prior_canon = ""
        for ref in existing_refs:
            if (ref.get("filename") or "").lower() == canon_filename:
                prior_canon = ref.get("content", "")
                break

        timestamp = datetime.now(timezone.utc).isoformat()
        safe_label = (source_label or source_type or "canon-update").strip()[:120]
        excerpt = (source_content or "").strip().replace("\n", " ")[:800]
        note = (instructions or "").strip()

        section_lines = [
            f"## Canon Update: {safe_label}",
            f"_Timestamp: {timestamp}_",
            f"Source Type: {source_type or 'unknown'}",
        ]
        if note:
            section_lines.append("")
            section_lines.append("### Instructions")
            section_lines.append(note)
        if excerpt:
            section_lines.append("")
            section_lines.append("### Source Excerpt")
            section_lines.append(excerpt)

        section = "\n".join(section_lines).strip() + "\n"

        header = "# Canon Log\n\n"
        combined = prior_canon.strip()
        if not combined:
            combined = header + section
        else:
            combined = combined.rstrip() + "\n\n" + section

        updated = await update_reference_file(project_id, canon_filename, combined, user_id)
        if not updated:
            await create_reference_file(project_id, canon_filename, combined, user_id)

        try:
            vector_service = VectorStoreService()
            await vector_service.upsert_reference_file(
                project_id=project_id,
                user_id=user_id,
                filename=canon_filename,
                content=combined,
                file_type="canon_log"
            )
        except Exception as vector_err:
            logger.warning(f"Failed to update canon log vector memory: {vector_err}")

        return {"success": True, "content": combined}
    except Exception as e:
        logger.error(f"Canon log append failed for project {project_id}: {e}")
        return {"success": False, "error": str(e)}
