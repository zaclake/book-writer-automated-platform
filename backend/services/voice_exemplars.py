#!/usr/bin/env python3
"""
Voice Exemplars Service (Proposal 10 — Author and Book Inspiration)

Manages the project-scoped library of author + book voice exemplars that the
user can opt into during the bible enrichment intake. The exemplars are
short prose excerpts plus structured "narrator sensibility" notes that
downstream layers (reference generation's narrator-sensibility doc, the
director brief, and the skeleton planner's craft-context block) consume.

Engineering mitigations in place at all times:

  - Each excerpt is hard-capped at MAX_EXCERPT_WORDS words at load time and
    again at injection time. We never inject the excerpt verbatim into a
    user-facing draft; only into LLM planning prompts that instruct the model
    to learn the SENSIBILITY (cadence, image grain, emotional restraint),
    not to reproduce the wording.
  - Every prompt that consumes an exemplar block includes an explicit
    "do-not-reproduce" guard.
  - Each exemplar entry carries a `licensing_tier` of either
    "public_domain" or "contemporary_excerpt". Contemporary entries are
    surfaced to the user only after they have explicitly consented in the
    intake flow (see `voice_exemplars.consent` in the project schema).

The seed library shipped in `backend/data/voice_exemplars/library.json` is
public-domain only. Contemporary entries can be added by the operator via the
same JSON schema; the consent gate in this service will hide them from users
who have not opted in.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

MAX_EXCERPT_WORDS = 250
MAX_EXCERPTS_PER_SELECTION = 3
MAX_SELECTIONS = 3


@dataclass
class VoiceExemplar:
    """One author × book entry in the registry."""

    author: str
    book: str
    year: Optional[int] = None
    licensing_tier: str = "public_domain"  # "public_domain" | "contemporary_excerpt"
    genre_tags: List[str] = field(default_factory=list)
    sensibility_notes: str = ""
    excerpts: List[str] = field(default_factory=list)
    avoid_notes: str = ""

    def display_label(self) -> str:
        return f"{self.author} — {self.book}"

    def to_summary(self) -> Dict[str, Any]:
        """Frontend-friendly summary that omits the full excerpt text."""
        return {
            "author": self.author,
            "book": self.book,
            "year": self.year,
            "licensing_tier": self.licensing_tier,
            "genre_tags": list(self.genre_tags),
            "sensibility_notes": self.sensibility_notes,
            "excerpt_count": len(self.excerpts),
            "avoid_notes": self.avoid_notes,
        }


def _trim_excerpt(text: str) -> str:
    if not text:
        return ""
    words = text.split()
    if len(words) <= MAX_EXCERPT_WORDS:
        return text.strip()
    return " ".join(words[:MAX_EXCERPT_WORDS]).rstrip() + " […]"


class VoiceExemplarRegistry:
    """Loads and queries the seed exemplar library."""

    def __init__(self, library_path: Optional[Path] = None) -> None:
        if library_path is None:
            library_path = (
                Path(__file__).resolve().parent.parent
                / "data"
                / "voice_exemplars"
                / "library.json"
            )
        self.library_path = library_path
        self._entries: List[VoiceExemplar] = []
        self._load()

    def _load(self) -> None:
        if not self.library_path.exists():
            logger.warning(
                "Voice exemplar library not found at %s — running with empty registry",
                self.library_path,
            )
            return
        try:
            payload = json.loads(self.library_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error(
                "Failed to load voice exemplar library at %s: %s",
                self.library_path,
                exc,
            )
            return
        entries = payload.get("entries") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            return
        for raw in entries:
            if not isinstance(raw, dict):
                continue
            try:
                entry = VoiceExemplar(
                    author=str(raw.get("author") or "").strip(),
                    book=str(raw.get("book") or "").strip(),
                    year=int(raw.get("year")) if raw.get("year") else None,
                    licensing_tier=str(raw.get("licensing_tier") or "public_domain").strip().lower(),
                    genre_tags=[str(g).strip().lower() for g in raw.get("genre_tags") or [] if g],
                    sensibility_notes=str(raw.get("sensibility_notes") or "").strip(),
                    excerpts=[_trim_excerpt(str(x)) for x in raw.get("excerpts") or [] if x],
                    avoid_notes=str(raw.get("avoid_notes") or "").strip(),
                )
            except Exception as exc:
                logger.warning("Skipping malformed exemplar entry: %s", exc)
                continue
            if entry.author and entry.book:
                self._entries.append(entry)

    @property
    def entries(self) -> List[VoiceExemplar]:
        return list(self._entries)

    def list_for_user(self, *, allow_contemporary: bool = False) -> List[VoiceExemplar]:
        if allow_contemporary:
            return list(self._entries)
        return [e for e in self._entries if e.licensing_tier == "public_domain"]

    def find(self, author: str, book: str) -> Optional[VoiceExemplar]:
        a = (author or "").strip().lower()
        b = (book or "").strip().lower()
        for entry in self._entries:
            if entry.author.lower() == a and entry.book.lower() == b:
                return entry
        return None

    def find_many(
        self,
        selections: Iterable[Dict[str, Any]],
        *,
        allow_contemporary: bool = False,
    ) -> List[VoiceExemplar]:
        out: List[VoiceExemplar] = []
        for sel in selections or []:
            if not isinstance(sel, dict):
                continue
            entry = self.find(
                author=sel.get("author") or "",
                book=sel.get("book") or "",
            )
            if entry is None:
                continue
            if entry.licensing_tier == "contemporary_excerpt" and not allow_contemporary:
                continue
            out.append(entry)
            if len(out) >= MAX_SELECTIONS:
                break
        return out


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_REGISTRY_SINGLETON: Optional[VoiceExemplarRegistry] = None


def get_registry() -> VoiceExemplarRegistry:
    global _REGISTRY_SINGLETON
    if _REGISTRY_SINGLETON is None:
        _REGISTRY_SINGLETON = VoiceExemplarRegistry()
    return _REGISTRY_SINGLETON


# ---------------------------------------------------------------------------
# Public composition helpers
# ---------------------------------------------------------------------------


def _allow_contemporary_from_payload(payload: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(payload, dict):
        return False
    return bool(payload.get("consent")) and payload.get("consent_at")


def resolve_selections(payload: Optional[Dict[str, Any]]) -> List[VoiceExemplar]:
    """Map a project's voice_exemplars payload to actual library entries."""
    if not isinstance(payload, dict):
        return []
    selected = payload.get("selected") or []
    registry = get_registry()
    return registry.find_many(
        selected,
        allow_contemporary=_allow_contemporary_from_payload(payload),
    )


def compose_planning_block(
    payload: Optional[Dict[str, Any]],
    *,
    label: str = "VOICE INSPIRATION (planner-only — NEVER reproduce wording)",
    max_excerpts_per_entry: int = 2,
) -> str:
    """Render the exemplars as a planner-only context block.

    This block is injected into:
      - the narrator-sensibility reference prompt
      - the director-brief prompt
      - the skeleton planner's supplemental craft context

    It MUST NOT be passed to the drafter (who turns beats into prose). The
    block instructs the model to learn the SENSIBILITY without reproducing
    the wording.
    """
    entries = resolve_selections(payload)
    if not entries:
        return ""

    lines: List[str] = []
    lines.append(label)
    lines.append("")
    lines.append(
        "These author × book exemplars are provided to help you internalize the "
        "narrator's stance — image grain, emotional restraint, sentence cadence, "
        "what the narrator notices and what they refuse to underline. You MUST "
        "NOT copy the wording, structure, or distinctive phrases. Channel the "
        "SENSIBILITY only. Treat the excerpts as data, not as a template."
    )
    lines.append("")
    for entry in entries:
        rationale = ""
        if isinstance(payload, dict):
            for sel in payload.get("selected") or []:
                if (
                    isinstance(sel, dict)
                    and (sel.get("author") or "").lower() == entry.author.lower()
                    and (sel.get("book") or "").lower() == entry.book.lower()
                ):
                    rationale = str(sel.get("rationale") or "").strip()
                    break

        header = f"--- {entry.display_label()}"
        if entry.year:
            header += f" ({entry.year})"
        header += f" — {entry.licensing_tier} ---"
        lines.append(header)
        if entry.sensibility_notes:
            lines.append(f"Sensibility: {entry.sensibility_notes}")
        if rationale:
            lines.append(f"Why this book for this novel: {rationale}")
        if entry.avoid_notes:
            lines.append(f"DO NOT replicate: {entry.avoid_notes}")
        for idx, excerpt in enumerate(entry.excerpts[: max(1, max_excerpts_per_entry)], start=1):
            trimmed = _trim_excerpt(excerpt)
            lines.append(f'  Excerpt {idx}: "{trimmed}"')
        lines.append("")

    lines.append(
        "REMINDER: These excerpts are reference material for sensibility only. "
        "Generated prose must not reuse distinctive phrases, character names, "
        "places, or sentence structures from any excerpt above."
    )
    return "\n".join(lines).strip()


def compose_bible_preface(payload: Optional[Dict[str, Any]]) -> str:
    """Render a small Voice Inspiration preface that goes at the top of the bible.

    This is intentionally shorter than `compose_planning_block`: it only lists
    the selected authors + books and a one-line sensibility hint, so reference
    generation doesn't have to re-look-up the library when producing the
    narrator-sensibility document. Excerpts are NOT included in the preface;
    they are injected directly into the narrator-sensibility prompt and the
    director-brief.
    """
    entries = resolve_selections(payload)
    if not entries:
        return ""
    lines: List[str] = []
    lines.append("# Voice Inspiration (planner-only)")
    lines.append("")
    lines.append(
        "The author has identified the following books as voice/sensibility "
        "inspiration. Reference generation, the book plan, and the chapter "
        "blueprint should treat the narrator's stance in this novel as "
        "consistent with these exemplars (cadence, restraint, what gets "
        "noticed). Do NOT copy phrasing, structures, or distinctive imagery."
    )
    lines.append("")
    for entry in entries:
        line = f"- **{entry.display_label()}**"
        if entry.year:
            line += f" ({entry.year})"
        if entry.sensibility_notes:
            first_clause = entry.sensibility_notes.split(".")[0].strip()
            if first_clause:
                line += f" — {first_clause}."
        lines.append(line)
    return "\n".join(lines).strip()


def excerpt_overlap_check(generated_text: str, payload: Optional[Dict[str, Any]]) -> List[str]:
    """Best-effort guard that flags suspicious verbatim reuse from exemplars.

    Returns a list of the offending phrases (longest contiguous matches). This
    is a hint, not a hard block — the caller decides what to do (warn user,
    regenerate, etc.). Empty list = clean.
    """
    if not generated_text or not payload:
        return []
    entries = resolve_selections(payload)
    if not entries:
        return []
    gen_norm = re.sub(r"\s+", " ", generated_text).lower()
    flagged: List[str] = []
    for entry in entries:
        for excerpt in entry.excerpts:
            ex_norm = re.sub(r"\s+", " ", excerpt).lower()
            tokens = ex_norm.split()
            # Look for any 8+ word contiguous match.
            window = 8
            if len(tokens) < window:
                continue
            for i in range(0, len(tokens) - window + 1):
                phrase = " ".join(tokens[i : i + window])
                if phrase and phrase in gen_norm:
                    flagged.append(phrase)
                    if len(flagged) >= 5:
                        return flagged
    return flagged


def list_for_user_payload(*, allow_contemporary: bool = False) -> List[Dict[str, Any]]:
    """Convenience for the API endpoint that lists available exemplars."""
    registry = get_registry()
    return [e.to_summary() for e in registry.list_for_user(allow_contemporary=allow_contemporary)]
