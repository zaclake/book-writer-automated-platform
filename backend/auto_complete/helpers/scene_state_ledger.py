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

        Detection rule: only flag a token as a "speaker" when it is the
        attribution for an actual quoted dialogue span in the same paragraph.
        Naked narration like ``Air hissed into the hush`` or ``the wind
        answered`` does NOT count as dialogue and never triggers the warning.
        """
        if not beat_text:
            return []

        warnings: List[str] = []
        beat_chars = {
            (c or "").strip().lower()
            for c in (beat.get("characters_present") or [])
            if isinstance(c, str)
        }

        # Speech verbs that legitimately tag a quoted line. Animal-coded
        # verbs ('barked', 'hissed', etc.) are kept here because we still
        # want to flag them when paired with an actual quote, but they're
        # NEVER triggered by narration like "Air hissed".
        _SPEECH_VERBS = (
            "said|asked|answered|replied|murmured|whispered|shouted|"
            "growled|barked|hissed|snarled|whined|meowed|purred|yelped|"
            "whinnied|neighed"
        )

        # CASE-SENSITIVE speaker pattern: must start with a capital letter.
        # The speaker token itself is matched without IGNORECASE so that
        # "the wind answered" is rejected at parse time. Verb list is then
        # matched separately so its alternatives still match in any case.
        speaker_token_re = re.compile(
            r"\b([A-Z][a-zA-Z\-']{0,30}(?:\s+[A-Z][a-zA-Z\-']{0,30})?)\s+"
            r"(" + _SPEECH_VERBS + r")\b",
            re.IGNORECASE,  # kept for the verb half; speaker still requires
                            # an explicit capital due to the literal [A-Z].
        )
        # Reverse form: said + Speaker (e.g. `"Stop," said Maya.`)
        reverse_speaker_re = re.compile(
            r"\b(" + _SPEECH_VERBS + r")\s+([A-Z][a-zA-Z\-']{0,30}(?:\s+[A-Z][a-zA-Z\-']{0,30})?)\b",
            re.IGNORECASE,
        )

        # Pronoun-shaped tokens that accidentally satisfy the [A-Z]...
        # pattern when they appear at sentence start (e.g. "She said").
        # Common stop words that the model sometimes leads paragraphs with
        # (and which would be capitalized after a period).
        _PRONOUN_TOKENS = {
            "i", "he", "she", "they", "we", "you", "it",
            "his", "her", "him", "them", "their", "our", "my", "your",
            "the", "a", "an", "this", "that", "these", "those",
            "and", "but", "or", "if", "then", "when", "where", "why",
            "what", "which", "who", "whom", "whose",
            # Multi-word determiner-led noun phrases caught by the two-word
            # speaker pattern (e.g., "No one answered", "The fryer hissed",
            # "Lou always said" where the second token is an adverb, not a
            # proper continuation of the speaker name).
            "no one", "no body", "anyone", "someone", "everyone",
            "nobody", "somebody", "everybody",
        }
        # First-word stop set — when the speaker phrase's FIRST token is one
        # of these, the whole phrase is determiner-led (a noun phrase like
        # "The fryer", "No one", "Some kid") rather than a proper name. We
        # skip the speaker check rather than try to match the full phrase
        # against _PRONOUN_TOKENS (the second word can be anything).
        _DETERMINER_FIRST_WORDS = {
            "the", "a", "an", "no", "any", "some", "every",
            "this", "that", "these", "those",
        }
        # Second-word stop set — when the speaker phrase's SECOND token is
        # an adverb/pronoun, the model has misattributed dialogue to "Lou
        # always" / "Lou I" / "Mary suddenly" rather than to the speaker.
        _ADVERB_SECOND_WORDS = {
            "i", "he", "she", "they", "we", "you", "it",
            "always", "never", "sometimes", "often", "just", "only",
            "still", "already", "finally", "suddenly", "almost",
            "barely", "nearly", "quickly", "slowly", "quietly",
        }
        # Common nouns that are capitalized in English but never speakers —
        # months, weekdays, seasons, holidays. The regex finds patterns like
        # `October said` where the model wrote "October said its quiet, dry
        # word" as personification narration. These are not speakers.
        _COMMON_NOUN_NAMES = {
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
            "monday", "tuesday", "wednesday", "thursday", "friday",
            "saturday", "sunday",
            "spring", "summer", "fall", "autumn", "winter",
            "christmas", "easter", "thanksgiving", "halloween",
            "god", "heaven", "hell", "earth", "moon", "sun",
            "north", "south", "east", "west",
        }
        # Quoted-dialogue detector — straight or curly quotes, ≥2 chars.
        _QUOTE_RE = re.compile(r"[\"\u201c][^\"\u201d\u201c]{2,}[\"\u201d]")
        seen: Set[str] = set()

        # Split into paragraphs so each attribution is bounded by a real
        # dialogue span in its own paragraph. This is the core fix for
        # false positives like `Steam hissed.` (no quote → no flag).
        paragraphs = re.split(r"\n\s*\n", beat_text)
        for para in paragraphs:
            if not _QUOTE_RE.search(para):
                continue  # no quoted dialogue here → no attribution to check

            # Collect (speaker_raw, verb) candidates from both directions.
            candidates: List[tuple] = []
            for m in speaker_token_re.finditer(para):
                candidates.append((m.group(1).strip(), m.group(2).lower()))
            for m in reverse_speaker_re.finditer(para):
                candidates.append((m.group(2).strip(), m.group(1).lower()))

            for speaker_raw, verb in candidates:
                speaker_key = speaker_raw.lower()
                if speaker_key in _PRONOUN_TOKENS:
                    continue
                # First word of the speaker phrase must literally start with
                # a capital — protects against lowercased noun phrases that
                # snuck through because IGNORECASE applies to the verb half.
                tokens = speaker_raw.split()
                first_word = tokens[0]
                if not first_word or not first_word[0].isupper():
                    continue
                # Determiner-led noun phrases ("The fryer", "No one", "Some kid")
                # are not speakers — they're narrative subjects that happen to
                # precede a speech verb. Skip the whole phrase.
                if first_word.lower() in _DETERMINER_FIRST_WORDS:
                    continue
                # Two-word speaker where the SECOND token is an adverb or
                # pronoun ("Lou always", "Lou I", "Mary suddenly") is the
                # model misparsing — the actual speaker is just "Lou" / "Mary"
                # and the regex caught a continuation. Skip.
                if len(tokens) >= 2 and tokens[1].lower() in _ADVERB_SECOND_WORDS:
                    continue
                # Single-word speakers that are actually months/weekdays/
                # seasons/holidays — these are common-noun calendar terms
                # the model uses in personification ("October said") rather
                # than dialogue attributions. Skip.
                if (
                    len(tokens) == 1
                    and first_word.lower() in _COMMON_NOUN_NAMES
                ):
                    continue
                if speaker_key in seen:
                    continue
                seen.add(speaker_key)

                state = self._states.get(speaker_key)
                if state and state.species in ("animal", "object"):
                    # Animal-coded verbs (barked, meowed, purred, growled when
                    # paired with 'said' is fine for humans; but pure speech
                    # verbs for an animal/object character are a problem).
                    if verb in {"said", "asked", "answered", "replied", "murmured", "whispered", "shouted"}:
                        warnings.append(
                            f"animal/object character '{state.name}' spoke human dialogue ('{verb}') — "
                            f"render through sound or physical reaction instead."
                        )
                    continue

                # Ghost speaker: someone speaks who isn't in this beat's
                # planned cast AND isn't a known character at all.
                if not state and speaker_key not in beat_chars:
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
