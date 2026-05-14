#!/usr/bin/env python3
"""Per-scene continuity guard (Path A+ P1.4).

Tracks per-character state inside a single chapter so the drafter can't
silently teleport people from one beat to the next, or hand dialogue to
an animal/object. The ledger is intra-chapter only — cross-chapter state
lives in the EstablishedFactsLedger / character_states.

Wire-up:
  1. `SceneStateLedger.from_chapter_plan(...)` once per chapter, seeded with
     focal characters and (best-effort) species inferred from the character
     reference markdown.
  2. Before each beat call `ledger.build_state_guard(beat)` and pass the
     resulting string to `expand_beat(..., scene_state_guard=...)`.
  3. After each beat call `ledger.update_from_beat(beat, beat_text)` to
     advance on_stage state for the next iteration.
  4. After each beat call `ledger.validate_beat_speakers(beat_text, beat)` to
     catch animal-speak and ghost-speaker violations. Returns a list of
     warning strings; callers log and may inject as a rewrite hint.

The ledger is intentionally lightweight: it does NOT try to be a perfect
world model. It catches the violations that hurt the most in the shipped
ponce.epub (cats talking, characters appearing in scenes they weren't in).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


# Tokens in a character profile (or name) that strongly suggest the character
# is an animal/object/AI rather than a speaking human. Detection is heuristic;
# false positives (e.g., a character nicknamed "Wolf") are acceptable because
# the ledger only RECOMMENDS — it does not block generation.
_ANIMAL_TOKENS = re.compile(
    r"\b(cat|kitten|dog|puppy|horse|mare|stallion|cow|bull|pig|sheep|goat|"
    r"chicken|rooster|hen|duck|goose|sparrow|crow|raven|hawk|owl|falcon|"
    r"rabbit|hare|fox|wolf|bear|deer|elk|moose|buffalo|bison|lion|tiger|"
    r"leopard|cheetah|jaguar|panther|cougar|coyote|hyena|monkey|ape|gorilla|"
    r"chimpanzee|elephant|giraffe|zebra|hippo|rhino|whale|dolphin|shark|"
    r"fish|snake|serpent|lizard|turtle|tortoise|frog|toad|crocodile|"
    r"alligator|spider|insect|bug|bee|wasp|hornet|ant|beetle|"
    r"animal|beast|critter|creature\s+with\s+fur|pet)\b",
    re.IGNORECASE,
)

_OBJECT_TOKENS = re.compile(
    r"\b(robot|android|ai\b|computer|machine|drone|car|truck|ship|building|"
    r"house|tree|stone|statue|painting|the\s+building)\b",
    re.IGNORECASE,
)


def _strip_paren(name: str) -> str:
    """Strip parenthetical descriptions from a character name like 'Sasha (the cat)' → 'Sasha'."""
    return re.sub(r"\s*\(.*?\)\s*", "", name).strip()


def _classify_species(name: str, character_reference: str) -> str:
    """Return 'human' (default), 'animal', or 'object' based on best-effort detection."""
    bare = _strip_paren(name)
    if not bare:
        return "human"

    # Look for the character's section in the reference markdown. We accept
    # the section header line plus the next ~600 chars as their profile.
    if character_reference:
        # Match lines like '## Sasha', '### Sasha (the cat)', '- Sasha:' etc.
        pattern = re.compile(
            rf"(^|\n)(?:#+\s*|[*\-]\s*){re.escape(bare)}\b(?:[^\n]{{0,200}})\n([\s\S]{{0,600}})",
            re.IGNORECASE,
        )
        m = pattern.search(character_reference)
        if m:
            block = m.group(0)
            if _ANIMAL_TOKENS.search(block):
                return "animal"
            if _OBJECT_TOKENS.search(block):
                return "object"

        # Fall back: walk every sentence containing the name and check both
        # forward and backward neighbors. This catches "The dog Wolfgang…"
        # and "Wolfgang, a dog…" without requiring a profile section.
        name_re = re.compile(rf"\b{re.escape(bare)}\b", re.IGNORECASE)
        sentences = re.split(r"(?<=[.!?])\s+|\n+", character_reference)
        for sentence in sentences:
            if not name_re.search(sentence):
                continue
            if _ANIMAL_TOKENS.search(sentence):
                return "animal"
            if _OBJECT_TOKENS.search(sentence):
                return "object"

    # Heuristic: if the bare name itself is an animal noun (e.g., "Mr. Whiskers"
    # is too rare to catch; this picks up "Wolf the dog" called only "Wolf").
    if _ANIMAL_TOKENS.fullmatch(bare):
        return "animal"

    return "human"


@dataclass
class CharacterState:
    """State for a single character within the current chapter."""
    name: str
    species: str = "human"          # "human" | "animal" | "object"
    on_stage: bool = False          # currently in the active scene/beat
    last_seen_beat: int = 0         # 0 = not yet seen this chapter
    location_hint: str = ""         # free-form; "interrogation room", "the truck"
    holding: List[str] = field(default_factory=list)  # objects in hand
    condition: str = "ok"           # "ok" | "injured" | "unconscious" | "dead" | "absent"
    notes: str = ""                 # free-form recent intent

    def to_line(self) -> str:
        bits = [self.name]
        details = []
        if self.species != "human":
            details.append(self.species.upper())
        if self.condition != "ok":
            details.append(self.condition)
        if self.holding:
            details.append("holding " + ", ".join(self.holding[:2]))
        if self.location_hint:
            details.append(f"@{self.location_hint}")
        if details:
            bits.append(f"({'; '.join(details)})")
        return " ".join(bits)


class SceneStateLedger:
    """Per-chapter character ledger."""

    def __init__(self):
        self._states: Dict[str, CharacterState] = {}

    @classmethod
    def from_chapter_plan(
        cls,
        chapter_plan: Dict[str, Any],
        character_reference: str = "",
        previous_chapter_ending: str = "",
    ) -> "SceneStateLedger":
        """Seed the ledger from the chapter plan + character reference profiles."""
        ledger = cls()
        focal = chapter_plan.get("focal_characters") or []
        pov = (chapter_plan.get("pov_character") or "").strip()
        names: List[str] = []
        if pov:
            names.append(pov)
        for c in focal:
            if isinstance(c, str) and c.strip() and c not in names:
                names.append(c.strip())

        for name in names:
            species = _classify_species(name, character_reference)
            ledger._states[name.lower()] = CharacterState(
                name=name,
                species=species,
                on_stage=False,
                last_seen_beat=0,
            )

        # If the previous chapter ending mentions any seeded character,
        # we DON'T mark them on-stage — every chapter starts fresh and the
        # opening beat will declare characters_present.
        return ledger

    # ───── public API ─────

    def known_names(self) -> List[str]:
        return [s.name for s in self._states.values()]

    def add_character_if_missing(self, name: str, character_reference: str = "") -> None:
        key = (name or "").strip().lower()
        if not key or key in self._states:
            return
        self._states[key] = CharacterState(
            name=name.strip(),
            species=_classify_species(name, character_reference),
        )

    def get(self, name: str) -> Optional[CharacterState]:
        return self._states.get((name or "").strip().lower())

    def on_stage_names(self) -> List[str]:
        return [s.name for s in self._states.values() if s.on_stage]

    def off_stage_names(self) -> List[str]:
        return [s.name for s in self._states.values() if not s.on_stage]

    def animal_or_object_names(self) -> List[str]:
        return [s.name for s in self._states.values() if s.species in ("animal", "object")]

    def build_state_guard(self, beat: Dict[str, Any]) -> str:
        """Build the SCENE STATE GUARD prose block to inject into expand_beat.

        Reflects truth as of BEFORE the beat is written; the planner intent for
        this beat (characters_present) is included as the target on-stage set.
        """
        beat_chars = [c for c in (beat.get("characters_present") or []) if isinstance(c, str)]

        # Make sure all beat characters exist in the ledger (no profile match
        # → assume human; better to under-flag than miss them entirely).
        for c in beat_chars:
            self.add_character_if_missing(c)

        on_stage_lines = []
        for s in self._states.values():
            if s.on_stage:
                on_stage_lines.append(f"  - {s.to_line()}")

        target_set = {(c or "").strip().lower() for c in beat_chars}
        becoming_on_stage = []
        for c in beat_chars:
            key = (c or "").strip().lower()
            if not key:
                continue
            state = self._states.get(key)
            if state and not state.on_stage:
                becoming_on_stage.append(c)

        leaving = []
        for s in self._states.values():
            if s.on_stage and s.name.lower() not in target_set:
                leaving.append(s.name)

        off_stage_lines = []
        for s in self._states.values():
            if not s.on_stage and s.name.lower() not in target_set:
                bits = [s.name]
                if s.last_seen_beat:
                    bits.append(f"last seen beat {s.last_seen_beat}")
                if s.location_hint:
                    bits.append(f"location: {s.location_hint}")
                off_stage_lines.append("  - " + " — ".join(bits))

        animals = self.animal_or_object_names()

        block = ["SCENE STATE GUARD (current truth before this beat — obey or correct):"]
        if on_stage_lines:
            block.append("ON STAGE going into this beat:")
            block.extend(on_stage_lines)
        else:
            block.append("ON STAGE going into this beat: (none yet — this beat establishes the scene)")

        if becoming_on_stage:
            block.append(
                "TARGET ON STAGE for this beat (planner intent): "
                + ", ".join(becoming_on_stage)
                + " — if any of these were NOT on stage in the prior beat, the prose MUST show them entering, arriving, or being addressed for the first time."
            )

        if leaving:
            block.append(
                "LEAVING the scene by start of this beat (planner intent): "
                + ", ".join(leaving)
                + " — the prior beat must have shown them exit, OR you must establish their absence in 1 line."
            )

        if off_stage_lines:
            block.append("OFF STAGE this chapter (do NOT have them speak in this beat):")
            block.extend(off_stage_lines[:8])

        if animals:
            block.append(
                "ANIMALS / OBJECTS present in this story (these NEVER produce dialogue): "
                + ", ".join(animals)
                + ". Render them only through actions, sounds, and physical reactions."
            )

        block.append(
            "RULES:\n"
            "  - Only ON STAGE / TARGET ON STAGE characters may speak in this beat.\n"
            "  - A character cannot teleport: bringing them on stage requires entry/arrival on the page.\n"
            "  - Animals/objects never speak in quoted dialogue. They produce sounds and physical reactions only.\n"
            "  - Do not contradict prior on-stage facts (location, what they were holding) without explicit narrative cause."
        )
        return "\n".join(block)

    def update_from_beat(self, beat: Dict[str, Any], beat_text: str = "") -> None:
        """Advance ledger state after the beat has been generated.

        We rely on the skeleton's characters_present as the source of truth
        for on/off stage, with a light prose-based location hint extraction.
        We deliberately do NOT call the LLM here — it would double the cost
        of every chapter for marginal gain.
        """
        beat_number = int(beat.get("beat_number") or 0)
        on_stage_now: Set[str] = {
            (c or "").strip().lower()
            for c in (beat.get("characters_present") or [])
            if isinstance(c, str)
        }
        # Always include POV-by-implication: if the beat has dialogue from
        # the POV but the planner forgot to list them, treat them as on-stage.
        # (We don't know POV here, so just trust characters_present.)

        for state in self._states.values():
            key = state.name.lower()
            if key in on_stage_now:
                state.on_stage = True
                state.last_seen_beat = beat_number
                # Best-effort location hint from a few common patterns.
                if beat_text:
                    loc = self._extract_location_for(state.name, beat_text)
                    if loc:
                        state.location_hint = loc
            else:
                # If they were on stage and aren't named in this beat, mark
                # them off stage. The planner has signaled they exited.
                state.on_stage = False

    @staticmethod
    def _extract_location_for(name: str, beat_text: str) -> str:
        """Cheap location heuristic: 'Reyes was in the interrogation room' → 'interrogation room'."""
        if not name or not beat_text:
            return ""
        patterns = [
            rf"\b{re.escape(name)}\b[^.\n]{{0,40}}\b(in|inside|at|by|near|on)\s+(the\s+)?([a-zA-Z][\w\s\-']{{2,40}})",
            rf"\b{re.escape(name)}\b[^.\n]{{0,40}}\b(stood|sat|leaned|stopped|knelt)\s+(in|at|by|on|near)\s+(the\s+)?([a-zA-Z][\w\s\-']{{2,40}})",
        ]
        for pat in patterns:
            m = re.search(pat, beat_text, re.IGNORECASE)
            if m:
                # The captured location is the LAST captured group.
                loc = m.group(m.lastindex).strip()
                # Trim at first sentence-end punctuation.
                loc = re.split(r"[,.;:!?]", loc)[0].strip()
                if 2 <= len(loc) <= 60:
                    return loc.lower()
        return ""

    def validate_beat_speakers(self, beat_text: str, beat: Dict[str, Any]) -> List[str]:
        """Inspect the generated beat for animal-speak and ghost-speaker violations.

        Returns a list of human-readable warnings. Empty list = clean beat.
        """
        if not beat_text:
            return []

        warnings: List[str] = []
        beat_chars = {
            (c or "").strip().lower()
            for c in (beat.get("characters_present") or [])
            if isinstance(c, str)
        }

        # Find dialogue attributions: 'X said' / 'said X' / 'X asked' / etc.
        # Single-letter character names (e.g., 'B') must match too — pronouns
        # are filtered downstream by length checks and ledger membership.
        attribution_re = re.compile(
            r'(?:[\"\u201c][^\"\u201d]{2,}[\"\u201d]\s*[,.]?\s*)?'  # optional quoted span
            r'\b([A-Z][a-zA-Z\-\']{0,30}(?:\s+[A-Z][a-zA-Z\-\']{0,30})?)\b'
            r'\s+(said|asked|answered|replied|murmured|whispered|shouted|growled|barked|hissed|snarled|whined|meowed|purred|yelped|whinnied|neighed)\b',
            re.IGNORECASE,
        )
        # Pronoun-shaped tokens that accidentally satisfy the [A-Z]... pattern.
        # We can't catch case via regex alone (we use IGNORECASE for verbs), so
        # filter explicitly by lowercased value.
        _PRONOUN_TOKENS = {"i", "he", "she", "they", "we", "you", "it"}
        seen: Set[str] = set()
        for m in attribution_re.finditer(beat_text):
            speaker_raw = m.group(1).strip()
            verb = m.group(2).lower()
            speaker_key = speaker_raw.lower()
            if speaker_key in _PRONOUN_TOKENS:
                continue
            if speaker_key in seen:
                continue
            seen.add(speaker_key)

            state = self._states.get(speaker_key)
            if state and state.species in ("animal", "object"):
                # Animal-coded verbs (barked, meowed, purred, growled when
                # paired with 'said' is fine for humans; but pure speech verbs
                # for an animal/object character are a problem).
                if verb in {"said", "asked", "answered", "replied", "murmured", "whispered", "shouted"}:
                    warnings.append(
                        f"animal/object character '{state.name}' spoke human dialogue ('{verb}') — "
                        f"render through sound or physical reaction instead."
                    )
                continue

            # Ghost speaker: someone speaks who isn't in this beat's planned cast
            # AND isn't a known character at all (likely a fabricated name).
            if not state and speaker_key not in beat_chars:
                # Skip very short capitalized words and pronoun-shaped tokens.
                if len(speaker_raw) < 3:
                    continue
                warnings.append(
                    f"unknown speaker '{speaker_raw}' attributed dialogue ('{verb}') — "
                    f"this name doesn't match any chapter character. Possible fabricated character."
                )
            elif state and not state.on_stage and speaker_key not in beat_chars:
                warnings.append(
                    f"off-stage character '{state.name}' produced dialogue without entering the scene — "
                    f"add an entrance line or move dialogue to a character actually on stage."
                )

        return warnings

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for persistence at end of chapter."""
        return {
            "characters": [
                {
                    "name": s.name,
                    "species": s.species,
                    "on_stage": s.on_stage,
                    "last_seen_beat": s.last_seen_beat,
                    "location_hint": s.location_hint,
                    "holding": list(s.holding),
                    "condition": s.condition,
                    "notes": s.notes,
                }
                for s in self._states.values()
            ]
        }
