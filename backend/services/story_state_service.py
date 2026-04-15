#!/usr/bin/env python3
"""
Story State Service
Builds a unified continuity snapshot and POV bridge guidance.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


def _extract_chapter_sections(ledger_text: str) -> List[Tuple[int, str]]:
    """Return list of (chapter_number, section_text) for ledger markdown."""
    if not ledger_text:
        return []
    matches = list(re.finditer(r"^##\s+Chapter\s+(\d+)\s*$", ledger_text, flags=re.MULTILINE))
    sections: List[Tuple[int, str]] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(ledger_text)
        chapter_num = int(match.group(1))
        sections.append((chapter_num, ledger_text[start:end].strip()))
    return sections


def parse_latest_ledger_entry(ledger_text: str) -> Dict[str, Any]:
    """Extract key fields from the latest ledger section."""
    sections = _extract_chapter_sections(ledger_text or "")
    if not sections:
        return {}
    _, section = sections[-1]
    data: Dict[str, Any] = {
        "summary": "",
        "carry_forward": [],
        "unresolved_threads": [],
        "changes": [],
        "relationship_shifts": [],
        "time_markers": [],
        "location_updates": [],
        "pov": {}
    }

    def _extract_list(header: str) -> List[str]:
        pattern = rf"^###\s+{re.escape(header)}\s*$"
        match = re.search(pattern, section, flags=re.MULTILINE)
        if not match:
            return []
        start = match.end()
        next_header = re.search(r"^###\s+", section[start:], flags=re.MULTILINE)
        end = start + next_header.start() if next_header else len(section)
        block = section[start:end]
        items = []
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("- "):
                items.append(line[2:].strip())
        return items

    data["summary"] = _extract_paragraph(section, "Summary")
    data["carry_forward"] = _extract_list("Carry Forward")
    data["unresolved_threads"] = _extract_list("Unresolved Threads")
    data["changes"] = _extract_list("New Facts or Changes")
    data["relationship_shifts"] = _extract_list("Relationship Shifts")
    data["time_markers"] = _extract_list("Time Markers")
    data["location_updates"] = _extract_list("Location Updates")
    data["pov"] = _extract_pov(section)
    return data


def _extract_paragraph(section: str, header: str) -> str:
    pattern = rf"^###\s+{re.escape(header)}\s*$"
    match = re.search(pattern, section, flags=re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    next_header = re.search(r"^###\s+", section[start:], flags=re.MULTILINE)
    end = start + next_header.start() if next_header else len(section)
    block = section[start:end].strip()
    lines = [line.strip() for line in block.splitlines() if line.strip() and not line.strip().startswith("- ")]
    return " ".join(lines).strip()


def _extract_pov(section: str) -> Dict[str, str]:
    match = re.search(r"^###\s+POV\s*$", section, flags=re.MULTILINE)
    if not match:
        return {}
    start = match.end()
    next_header = re.search(r"^###\s+", section[start:], flags=re.MULTILINE)
    end = start + next_header.start() if next_header else len(section)
    block = section[start:end]
    pov: Dict[str, str] = {}
    for line in block.splitlines():
        line = line.strip()
        if line.startswith("- Character:"):
            pov["character"] = line.split(":", 1)[1].strip()
        if line.startswith("- Type:"):
            pov["type"] = line.split(":", 1)[1].strip()
        if line.startswith("- Notes:"):
            pov["notes"] = line.split(":", 1)[1].strip()
    return pov


def build_pov_context(
    current_plan: Optional[Dict[str, Any]],
    previous_plan: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    current_plan = current_plan or {}
    previous_plan = previous_plan or {}

    current_pov = {
        "pov_character": current_plan.get("pov_character", ""),
        "pov_type": current_plan.get("pov_type", ""),
        "pov_notes": current_plan.get("pov_notes", "")
    }
    prev_character = previous_plan.get("pov_character", "")
    prev_type = previous_plan.get("pov_type", "")
    shift = False
    if current_pov.get("pov_character") and prev_character:
        shift = current_pov["pov_character"].strip().lower() != prev_character.strip().lower()
    elif current_pov.get("pov_type") and prev_type:
        shift = current_pov["pov_type"].strip().lower() != prev_type.strip().lower()

    current_pov["pov_shift"] = shift
    current_pov["previous_pov_character"] = prev_character
    current_pov["previous_pov_type"] = prev_type
    return current_pov


def build_bridge_requirements(
    ledger_entry: Dict[str, Any],
    pov_context: Dict[str, Any]
) -> List[str]:
    requirements: List[str] = []
    for item in (ledger_entry.get("carry_forward") or [])[:6]:
        requirements.append(str(item))
    for item in (ledger_entry.get("unresolved_threads") or [])[:6]:
        if item not in requirements:
            requirements.append(str(item))
    if pov_context.get("pov_shift"):
        requirements.append("Open in a new POV while anchoring in the immediate consequences of the prior chapter.")
    return requirements[:8]


def build_story_state_context(
    chapter_number: int,
    chapter_plan: Optional[Dict[str, Any]],
    previous_plan: Optional[Dict[str, Any]],
    ledger_text: str,
    continuity_snapshot: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    ledger_entry = parse_latest_ledger_entry(ledger_text)
    pov_context = build_pov_context(chapter_plan, previous_plan)
    bridge_requirements = build_bridge_requirements(ledger_entry, pov_context)

    story_state = {
        "chapter_number": chapter_number,
        "chapter_ledger_summary": ledger_entry.get("summary", ""),
        "chapter_ledger_carry_forward": ledger_entry.get("carry_forward", []),
        "chapter_ledger_unresolved": ledger_entry.get("unresolved_threads", []),
        "bridge_requirements": bridge_requirements,
        **pov_context
    }

    if continuity_snapshot:
        story_state["continuity_story_so_far"] = continuity_snapshot.get("story_so_far", "")
        story_state["continuity_unresolved_questions"] = continuity_snapshot.get("unresolved_questions", [])
        story_state["continuity_requirements"] = continuity_snapshot.get("continuity_requirements", [])
        story_state["continuity_character_needs"] = continuity_snapshot.get("character_development_needs", {})
        story_state["continuity_themes_to_continue"] = continuity_snapshot.get("themes_to_continue", [])
        story_state["pacing_guidance"] = continuity_snapshot.get("pacing_guidance", {})
        story_state["timeline_state"] = continuity_snapshot.get("timeline_state", {})
        story_state["timeline_constraints"] = continuity_snapshot.get("timeline_constraints", [])
        story_state["arc_diagnostics"] = continuity_snapshot.get("arc_diagnostics", {})

    return story_state
