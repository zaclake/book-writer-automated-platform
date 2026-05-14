#!/usr/bin/env python3
"""
Chapter Blueprint Generator & Pattern Tracker

Two components that work together:
1. ChapterPatternTracker: extracts structural signals from completed chapters
2. ChapterBlueprintGenerator: creates a structural blueprint before each chapter is written

The blueprint ensures each chapter has a different shape, opening, ending, and
prose register — preventing the structural monotony that makes AI novels feel
like the same chapter written 26 times.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


# ─── Pattern Tracker (runs AFTER each chapter) ──────────────────────────────

@dataclass
class ChapterSignals:
    """Structural signals extracted from a completed chapter."""
    chapter_number: int
    opening_type: str = "unknown"
    ending_type: str = "unknown"
    has_timer: bool = False
    new_developments: int = 0
    characters_present: List[str] = field(default_factory=list)
    word_count: int = 0
    avg_sentence_length: float = 0.0
    dialogue_percentage: float = 0.0
    chapter_shape: str = "unknown"
    first_sentence: str = ""
    last_sentence: str = ""
    # Path A+ P2.3 — Lexical-syntactic opening template (POS-ish family) and
    # verb-stem families overused in this chapter. Both are surfaced in the
    # next chapter's anti-pattern context so the model bans the FAMILY, not
    # the surface trigram.
    opening_template: str = "unknown"
    verb_stem_families: List[Dict[str, Any]] = field(default_factory=list)


# ─── P2.3: Opening-template + verb-stem family detectors ────────────────────
#
# These run on completed chapters and surface in the NEXT chapter's anti-pattern
# context. They catch the failure mode trigram detection misses: the model
# substitutes a synonym ("kept his eyes" → "kept his voice" → "kept his hands")
# and the underlying habit persists. The fix is to ban the FAMILY, not the
# surface phrase.

# Coarse opening-template families. We don't ship a POS tagger, but each
# template is a tight regex over the first sentence's lexical+syntactic shape.
# The names are referenced later by build_anti_pattern_context to issue hard
# bans when the same template recurs across recent chapters.
OPENING_TEMPLATES: List[str] = [
    "sensory_anchor_as_action",   # "[NN] [VBD] ... as [PRP] [VBG]"  ← Ponce/Daze offender
    "name_then_past_action",      # "Reyes pulled the door open."
    "pronoun_then_past_action",   # "He pulled the door open."
    "dialogue_first",             # opens with a quoted line
    "interior_monologue_first",   # opens with a thought, not a body
    "setting_description_first",  # "The morning was already hot."
    "time_reference_first",       # "By dawn, ..." / "Three hours later, ..."
    "adverbial_phrase_first",     # "Slowly, she ..." / "In the kitchen, ..."
    "subordinate_clause_first",   # "When she opened the door, ..."
    "in_medias_res_action",       # already-in-progress, no setup
    "other",
]


# Past-tense / past-participle suffixes used to recognize verbs WITHOUT a real
# POS tagger. Imperfect by design — false positives are fine because the
# downstream consumer is a soft prompt-time constraint, not a hard reject.
_PAST_VERB_SUFFIX = (
    r"(?:ed|d|t|ck|wn|nk|pt|nt|nd|ng|ung|ang|own|ade|ode|aw|aid|ent|ept|"
    r"old|olt|ank|unk|ied|ked|sed|red|ned|led|ged|ted|rew|une|aught|"
    r"me|ame|ought|ound)"
)
# Subject pronouns that should NOT be treated as a "concrete noun" opener.
_OPENING_PRONOUNS = frozenset({
    "he", "she", "they", "i", "you", "we", "it", "the", "a", "an",
    "this", "that", "these", "those", "there", "here",
})


def _classify_opening_template(first_sentence: str) -> str:
    """Classify the first sentence into a coarse lexical-syntactic template.

    The point isn't linguistic precision — it's catching the literal pattern
    the user flagged in farm-daze and ponce: a sensory noun phrase + past
    verb in the first clause, joined by "as <character> <verb>" in the
    second. We approximate this with regex; false positives are fine, since
    the downstream consumer (anti-pattern context) only triggers a ban when
    the same template recurs across multiple recent chapters.

    Returns one of OPENING_TEMPLATES.
    """
    if not first_sentence:
        return "unknown"

    s = first_sentence.strip()
    if not s:
        return "unknown"

    s_lower = s.lower()

    # Dialogue first — quoted line.
    if s.lstrip().startswith(('"', "\u201c", "'")):
        return "dialogue_first"

    # Subordinate clause first — "When/While/Before/After/Once <subj> <verb>, ..."
    # NOTE: we do NOT include "as" here — "as" is the joining conjunction in
    # the sensory-anchor pattern, not a true subordinator at sentence start.
    if re.match(
        r"^(when|while|before|after|once|since|because|until|though|although)\s+\w+",
        s_lower,
    ):
        return "subordinate_clause_first"

    # Time reference first — opens with a temporal anchor.
    if re.match(
        r"^(by|on)\s+(dawn|dusk|morning|evening|night|noon|midnight|sunrise|sunset|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        s_lower,
    ) or re.match(
        r"^(three|two|four|five|six|seven|eight|nine|ten|a few|several|many)\s+"
        r"(seconds?|minutes?|hours?|days?|weeks?|months?|years?)\s+(later|after|before|earlier|ago)\b",
        s_lower,
    ) or re.match(r"^(later|earlier|afterward|tomorrow|tonight|yesterday)\b", s_lower):
        return "time_reference_first"

    # Adverbial phrase first — "Slowly, she ..." / "In the kitchen, Mitch ..."
    if re.match(r"^[a-z]+ly,\s+\w+", s_lower):
        return "adverbial_phrase_first"
    if re.match(
        r"^(in|on|at|under|above|behind|beside|between|beneath|across|near|outside|inside)\s+"
        r"(the|a|an|her|his|their)\s+\w+(?:\s+\w+){0,3},\s+\w+",
        s_lower,
    ):
        return "adverbial_phrase_first"

    # Interior monologue first — opens with a thought / belief verb.
    # Checked BEFORE pronoun_then_past_action so "She knew ..." is interior,
    # not generic past-action.
    if re.match(
        r"^(he|she|they|i)\s+(thought|wondered|knew|believed|hoped|feared|imagined|"
        r"remembered|wanted|needed|understood|realized|sensed|suspected|doubted)\b",
        s_lower,
    ):
        return "interior_monologue_first"
    if re.match(r"^the\s+(thought|idea|memory|sound|smell|feeling)\s+of\b", s_lower):
        return "interior_monologue_first"

    # In-medias-res — sentence already in motion (gerund opener, very short
    # sound effect, etc.). Checked before sensory_anchor so a one-word opener
    # doesn't get misclassified.
    if re.match(r"^[A-Z][a-z]+ing\b", s):
        return "in_medias_res_action"
    if len(s.split()) <= 4 and re.match(r"^[A-Z][a-z]+[.!?]", s):
        return "in_medias_res_action"

    # Sensory-anchor-as-action — THE dominant Ponce / Farm Daze offender.
    # Pattern: a sensory noun phrase (capitalized common noun, optionally with
    # 1-3 modifiers) + past-tense verb, then
    #   "as [the|a]? <pronoun-or-Name> <verb>"
    # Checked before setting_description_first / name_then_past_action so the
    # actual culprit wins.
    first_word_match = re.match(r"^([A-Z][a-z']+)\b", s)
    first_word = first_word_match.group(1).lower() if first_word_match else ""
    if first_word and first_word not in _OPENING_PRONOUNS:
        head_tokens = s.split()[:6]
        head = " ".join(head_tokens)
        head_has_past_verb = bool(
            re.search(rf"\b[a-z]+{_PAST_VERB_SUFFIX}\b", head, re.IGNORECASE)
        )
        # Joining clause: " as <subject> <verb>". <subject> may be a pronoun,
        # a proper noun (1-2 words), or "the/a/an + (Adj )*ProperNoun(s)".
        as_clause = re.search(
            r"\bas\s+(?:"
            r"he|she|they"
            r"|(?:the|a|an)\s+(?:[A-Za-z]+\s+){0,3}[A-Za-z]+"
            r"|[A-Z][a-z']+(?:\s+[A-Z][a-z']+){0,2}"
            r")\s+[a-z]{3,}\b",
            s,
        )
        if head_has_past_verb and as_clause:
            return "sensory_anchor_as_action"

    # Setting description — "The morning was hot." / "The room smelled of bleach."
    # Comes before name_then_past_action so "The X was Y" doesn't get
    # misclassified (since "morning" looks like a verb to the past-suffix
    # heuristic).
    if re.match(
        r"^(the|a|an)\s+\w+\s+(was|were|smelled|sounded|felt|tasted|looked|seemed|hung|sat|stood|lay)\b",
        s_lower,
    ):
        return "setting_description_first"

    # Name then past action — "Reyes pulled ..." / "Halsey set ..."
    # Excludes opener articles to keep "The morning was ..." out.
    name_action = re.match(
        rf"^([A-Z][a-z]{{2,}})\s+[a-z]+{_PAST_VERB_SUFFIX}\b",
        s,
    )
    if name_action and name_action.group(1).lower() not in {"the", "a", "an"}:
        return "name_then_past_action"

    # Pronoun then past action — "He pulled ..." / "She set ..."
    if re.match(
        rf"^(he|she|they|i)\s+[a-z]+{_PAST_VERB_SUFFIX}\b",
        s_lower,
    ):
        return "pronoun_then_past_action"

    return "other"


# Anchors used by verb-stem-family detection.
#
# Two flavors:
#   • "framing-verb" anchors: VERB + possessive collocation. The model varies
#     the *object* ("kept his voice", "kept his eyes", "kept his hands").
#   • "body-part" anchors: BODY-PART noun appears with many different verbs
#     ("his jaw set", "his jaw tightened", "her jaw worked").
#
# Lists are intentionally short and anchored to the failure modes we observed
# in farm-daze/ponce — they are NOT a phrase blacklist (that would violate
# QUALITY_ITERATION_PROMPT.md). They name the *anchors* whose families to
# COUNT; the trigger is a per-chapter occurrence threshold.
_FRAMING_VERB_ANCHORS: List[str] = [
    "kept", "held", "let", "made", "pulled", "pushed", "set", "watched", "felt",
]
_FRAMING_PARTNER_NOUNS: List[str] = [
    # Body / posture nouns the model defaults to when a framing verb wants an
    # object. These rotate to make the family.
    "voice", "eyes", "gaze", "hands", "face", "jaw", "head", "mouth",
    "shoulders", "expression", "breath", "arms", "fingers", "back",
    "tone", "posture", "weight",
]
_BODY_PART_ANCHORS: List[str] = [
    "jaw", "eyes", "gaze", "hands", "voice", "chest", "shoulder", "shoulders",
    "face", "mouth", "throat", "breath", "fingers", "head", "arms",
]


def _extract_verb_stem_families(text: str) -> List[Dict[str, Any]]:
    """Identify verb-stem families overused in this chapter.

    A "family" is an anchor token that recurs with multiple different
    partners — e.g., `kept his __` filled by voice/eyes/hands/face. The
    model substitutes synonyms within the family, defeating trigram bans;
    so we ban the family by name in the next chapter's prompt.

    Returns a list of {"family": "kept his _", "count": n,
    "examples": ["kept his voice", "kept his eyes"]}.
    Only families with >= 3 occurrences AND >= 2 distinct partners are
    returned.
    """
    if not text or len(text.split()) < 200:
        return []

    text_lower = text.lower()

    families: List[Dict[str, Any]] = []

    # Framing-verb families — VERB + (his|her|their) + PARTNER_NOUN
    # We require the possessive in the middle so a generic "kept it short"
    # doesn't trip the family ban for "kept his voice".
    for verb in _FRAMING_VERB_ANCHORS:
        pattern = re.compile(
            rf"\b{verb}\s+(?:his|her|their)\s+([a-z]+)\b",
            re.IGNORECASE,
        )
        partners = [m.group(1).lower() for m in pattern.finditer(text_lower)]
        if not partners:
            continue
        # Only count partners that are recognizable body / register nouns —
        # otherwise we'd flag "kept his job" / "kept his promise" which are
        # legitimate.
        partners = [p for p in partners if p in _FRAMING_PARTNER_NOUNS]
        if len(partners) < 3:
            continue
        distinct = len(set(partners))
        if distinct < 2:
            continue
        examples = []
        seen = set()
        for p in partners:
            phrase = f"{verb} his/her/their {p}"
            if phrase not in seen:
                examples.append(phrase)
                seen.add(phrase)
            if len(examples) >= 4:
                break
        families.append({
            "family": f"{verb} his/her/their <body/register>",
            "count": len(partners),
            "examples": examples,
        })

    # Body-part anchor families — (his|her|their) + BODY_PART + VERB
    for noun in _BODY_PART_ANCHORS:
        pattern = re.compile(
            rf"\b(?:his|her|their)\s+{noun}\s+([a-z]+(?:ed|d|t|s)?)\b",
            re.IGNORECASE,
        )
        verbs = []
        for m in pattern.finditer(text_lower):
            v = m.group(1).lower()
            # Skip pure stopwords and copular fillers — we want action verbs.
            if v in {"and", "or", "but", "the", "a", "an", "to", "of", "in", "on", "for", "with"}:
                continue
            verbs.append(v)
        if len(verbs) < 3:
            continue
        if len(set(verbs)) < 2:
            continue
        examples = []
        seen = set()
        for v in verbs:
            phrase = f"his/her/their {noun} {v}"
            if phrase not in seen:
                examples.append(phrase)
                seen.add(phrase)
            if len(examples) >= 4:
                break
        families.append({
            "family": f"his/her/their {noun} <verb>",
            "count": len(verbs),
            "examples": examples,
        })

    # Sort by count desc, keep the worst 6 — that's plenty for one chapter.
    families.sort(key=lambda f: f["count"], reverse=True)
    return families[:6]


class ChapterPatternTracker:
    """Extracts and stores structural signals from completed chapters."""

    def __init__(self, project_path: str = "."):
        self.state_dir = Path(project_path) / ".project-state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.tracker_path = self.state_dir / "chapter-patterns.json"

    def load_patterns(self) -> List[Dict[str, Any]]:
        if not self.tracker_path.exists():
            return []
        try:
            return json.loads(self.tracker_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def save_patterns(self, patterns: List[Dict[str, Any]]) -> None:
        self.tracker_path.write_text(
            json.dumps(patterns, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def extract_signals(self, chapter_number: int, text: str, known_characters: List[str] = None) -> ChapterSignals:
        """Extract structural signals from a completed chapter."""
        if not text or not text.strip():
            return ChapterSignals(chapter_number=chapter_number)

        words = text.split()
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

        signals = ChapterSignals(
            chapter_number=chapter_number,
            word_count=len(words),
            avg_sentence_length=len(words) / max(len(sentences), 1),
            first_sentence=sentences[0][:200] if sentences else "",
            last_sentence=sentences[-1][:200] if sentences else "",
        )

        # Opening type detection
        first_para = paragraphs[0] if paragraphs else ""
        first_lower = first_para.lower()
        if first_para.startswith('"') or first_para.startswith('\u201c'):
            signals.opening_type = "dialogue"
        elif re.match(r'^(the|a|an)\s+(sun|moon|sky|rain|wind|morning|evening|night|dawn|dusk)', first_lower):
            signals.opening_type = "setting"
        elif re.search(r'^(he|she|they|i)\s+(sat|stood|waited|watched|listened|lay)', first_lower):
            signals.opening_type = "character_observation"
        elif re.search(r'^(he|she|they|i)\s+(grabbed|slammed|ran|hit|jerked|pressed|pushed|pulled)', first_lower):
            signals.opening_type = "physical_action"
        elif re.search(r'^\w+\s+(felt|heard|smelled|tasted|touched)', first_lower):
            signals.opening_type = "sensory"
        elif re.search(r'(years|months|weeks|days|hours|later|ago|before|after|since)', first_lower[:100]):
            signals.opening_type = "time_reference"
        else:
            signals.opening_type = "narration"

        # Ending type detection
        last_para = paragraphs[-1] if paragraphs else ""
        last_lower = last_para.lower()
        if re.search(r'(whatever came|into the unknown|only way forward|he was ready|she was ready|they were ready)', last_lower):
            signals.ending_type = "generic_cliffhanger"
        elif last_para.rstrip().endswith('?'):
            signals.ending_type = "question"
        elif re.search(r'(slammed|crashed|exploded|screamed|ran|darkness|black)', last_lower):
            signals.ending_type = "action_cliffhanger"
        elif re.search(r'(quiet|silence|still|peace|calm|breath|exhale|sigh)', last_lower):
            signals.ending_type = "quiet_resolution"
        elif last_para.rstrip().endswith('"') or last_para.rstrip().endswith('\u201d'):
            signals.ending_type = "dialogue"
        elif re.search(r'(decided|chose|knew what|made up)', last_lower):
            signals.ending_type = "decision"
        else:
            signals.ending_type = "narrative_close"

        # Timer/countdown detection
        timer_patterns = [
            r'\d+\s*(seconds?|minutes?|hours?)\s*(left|remaining|until|before)',
            r'countdown|timer|ticking|clock\s*(was|showed|read)',
            r'(deadline|time.?s up|running out of time)',
            r'\d{1,2}:\d{2}',
        ]
        timer_hits = sum(1 for p in timer_patterns if re.search(p, text, re.IGNORECASE))
        signals.has_timer = timer_hits >= 2

        # New developments count (genre-agnostic)
        development_markers = [
            'discovered', 'realized', 'revealed', 'learned', 'uncovered',
            'confessed', 'admitted', 'arrived', 'appeared', 'returned',
            'changed', 'transformed', 'decided', 'chose', 'broke',
        ]
        dev_hits = sum(1 for w in development_markers if re.search(rf'\b{w}\b', text.lower()))
        signals.new_developments = min(dev_hits // 4, 5)

        # Dialogue percentage
        in_quote = False
        dialogue_chars = 0
        for ch in text:
            if ch in ('"', '\u201c', '\u201d'):
                in_quote = not in_quote
            elif in_quote:
                dialogue_chars += 1
        signals.dialogue_percentage = round((dialogue_chars / max(len(text), 1)) * 100, 1)

        # Chapter shape classification (genre-agnostic)
        if signals.dialogue_percentage > 50:
            signals.chapter_shape = "dialogue_heavy"
        elif signals.has_timer:
            signals.chapter_shape = "urgency_driven"
        elif signals.new_developments >= 3:
            signals.chapter_shape = "revelation_heavy"
        elif signals.dialogue_percentage > 30 and signals.new_developments >= 1:
            signals.chapter_shape = "balanced"
        elif signals.dialogue_percentage < 20:
            signals.chapter_shape = "introspective"
        else:
            signals.chapter_shape = "character_focused"

        # Characters present (match known names)
        if known_characters:
            for name in known_characters:
                if name.lower() in text.lower():
                    signals.characters_present.append(name)

        # P2.3 — Lexical-syntactic opening template (catches the 7-of-12
        # "[NN] [VBD] ... as [PRP] [VBG]" pattern from Ponce/Daze) and
        # verb-stem family overuse (catches the kept_*/jaw_*/hands_* family
        # that defeats trigram bans).
        signals.opening_template = _classify_opening_template(signals.first_sentence)
        try:
            signals.verb_stem_families = _extract_verb_stem_families(text)
        except Exception:
            signals.verb_stem_families = []

        return signals

    def record_chapter(self, signals: ChapterSignals) -> None:
        """Record a chapter's signals to the persistent tracker."""
        patterns = self.load_patterns()
        patterns = [p for p in patterns if p.get("chapter_number") != signals.chapter_number]
        patterns.append(asdict(signals))
        patterns.sort(key=lambda p: p.get("chapter_number", 0))
        self.save_patterns(patterns)

    def get_recent_patterns(self, current_chapter: int, lookback: int = 4) -> List[Dict[str, Any]]:
        """Get patterns from recent chapters for anti-repetition."""
        patterns = self.load_patterns()
        return [p for p in patterns if p.get("chapter_number", 0) >= current_chapter - lookback
                and p.get("chapter_number", 0) < current_chapter]

    def build_anti_pattern_context(self, current_chapter: int) -> str:
        """Build anti-pattern context using ALL chapters for cumulative tracking."""
        all_patterns = self.load_patterns()
        all_before = [p for p in all_patterns if p.get("chapter_number", 0) < current_chapter]
        recent = self.get_recent_patterns(current_chapter)
        if not all_before and not recent:
            return ""

        lines = ["PATTERNS ALREADY USED (do NOT repeat these):"]
        total_chapters = len(all_before)

        # Cumulative opening type counts with hard constraints
        if all_before:
            opening_counts = Counter(p.get("opening_type", "unknown") for p in all_before)
            for otype, count in opening_counts.most_common():
                if count > max(2, total_chapters * 0.4):
                    lines.append(
                        f"- HARD CONSTRAINT: '{otype}' opening used {count}/{total_chapters} times "
                        f"({100 * count // max(total_chapters, 1)}%). "
                        f"This chapter MUST NOT use this opening type. "
                        f"The first word of the chapter MUST NOT be the protagonist's name."
                    )
            underused_openings = [o for o in OPENING_TYPES if opening_counts.get(o, 0) < 2]
            if underused_openings:
                lines.append(
                    f"- REQUIRED: Choose from these UNUSED or UNDERUSED openings: "
                    f"{json.dumps(underused_openings)}"
                )

            # Cumulative ending type counts
            ending_counts = Counter(p.get("ending_type", "unknown") for p in all_before)
            for etype, count in ending_counts.most_common():
                if count > max(2, total_chapters * 0.4):
                    lines.append(
                        f"- HARD CONSTRAINT: '{etype}' ending used {count}/{total_chapters} times. "
                        f"This chapter MUST use a DIFFERENT ending type."
                    )

            # Cumulative chapter shape counts
            shape_counts = Counter(p.get("chapter_shape", "unknown") for p in all_before)
            for shape, count in shape_counts.most_common():
                if count > max(2, total_chapters * 0.3):
                    lines.append(
                        f"- '{shape}' chapter structure used {count} times. "
                        f"This chapter MUST use a DIFFERENT structure. "
                        f"Choose from: {json.dumps(CHAPTER_SHAPES)}"
                    )

        # Recent patterns (last 4 chapters) for fine-grained avoidance
        if recent:
            opening_types = [p.get("opening_type", "unknown") for p in recent]
            ending_types = [p.get("ending_type", "unknown") for p in recent]
            shapes = [p.get("chapter_shape", "unknown") for p in recent]
            timer_chapters = [p.get("chapter_number") for p in recent if p.get("has_timer")]

            lines.append(f"- Recent opening types: {', '.join(opening_types)}. Choose a DIFFERENT opening type.")
            lines.append(f"- Recent ending types: {', '.join(ending_types)}. Choose a DIFFERENT ending type.")
            lines.append(f"- Recent chapter shapes: {', '.join(shapes)}. Choose a DIFFERENT shape.")

            if timer_chapters:
                lines.append(f"- Chapters with timers/countdowns: {timer_chapters}. Do NOT use a timer in this chapter.")

            dev_counts = [p.get("new_developments", 0) for p in recent]
            if sum(dev_counts) > 6:
                lines.append("- Recent chapters introduced many new developments. This chapter should deepen EXISTING threads instead of introducing new ones.")

            recent_openings = [p.get("first_sentence", "")[:80] for p in recent if p.get("first_sentence")]
            if recent_openings:
                lines.append("- Recent first sentences (avoid similar patterns):")
                for s in recent_openings[-3:]:
                    lines.append(f"  '{s}'")

            recent_endings = [p.get("last_sentence", "")[:80] for p in recent if p.get("last_sentence")]
            if recent_endings:
                lines.append("- Recent last sentences (avoid similar ending patterns):")
                for s in recent_endings[-3:]:
                    lines.append(f"  '{s}'")

        # P2.3 — Opening-template ban. If the same lexical-syntactic template
        # appears 2+ times in the most recent 3 chapters, force a different
        # template for this chapter. This catches the
        # "[NN] [VBD] ... as [PRP] [VBG]" sensory-anchor pattern that the
        # coarse opening_type tag classifies as 7 different things while the
        # underlying syntax is identical.
        try:
            tail = recent[-3:] if recent else []
            template_counts = Counter(
                (p.get("opening_template") or "unknown") for p in tail
                if (p.get("opening_template") or "unknown") not in {"unknown", "other"}
            )
            for template, count in template_counts.most_common():
                if count >= 2:
                    alternatives = [
                        t for t in OPENING_TEMPLATES
                        if t not in {template, "unknown", "other"}
                    ]
                    lines.append(
                        f"- HARD CONSTRAINT (opening template): '{template}' was used in "
                        f"{count} of the last {len(tail)} chapters. The opening sentence of "
                        f"THIS chapter MUST NOT match that template. Specifically forbidden: "
                        f"opening with a sensory noun + past verb + 'as <pronoun> <verb-ing>' "
                        f"(e.g., 'Wet grass pressed cold as he crossed.'). "
                        f"Use one of these instead: {json.dumps(alternatives[:5])}."
                    )
                    break  # one ban is enough; don't repeat
            # Also, if the cumulative offender is the sensory_anchor_as_action
            # template across the whole book, escalate.
            if all_before:
                book_template_counts = Counter(
                    (p.get("opening_template") or "unknown") for p in all_before
                )
                anchor_count = book_template_counts.get("sensory_anchor_as_action", 0)
                if anchor_count >= 3 and not any(
                    "sensory_anchor_as_action" in ln for ln in lines
                ):
                    lines.append(
                        f"- HARD CONSTRAINT (book-level opening): the "
                        f"sensory_anchor_as_action template "
                        f"('[NN] [VBD] ... as [PRP] [VBD/VBG]') has been used "
                        f"{anchor_count} times in this book. ABSOLUTELY do not open "
                        f"with that template again in this chapter."
                    )
        except Exception:
            pass

        # P2.3 — Verb-stem family ban. Aggregate families overused in any of
        # the 3 most recent chapters and ban the FAMILY (not the trigram).
        # This is what defeats the "model substitutes a synonym within the
        # family" failure ('kept his eyes' → 'kept his voice' → 'kept his
        # hands').
        try:
            family_history: Counter = Counter()
            family_examples: Dict[str, List[str]] = {}
            for p in (recent[-3:] if recent else []):
                for fam in (p.get("verb_stem_families") or []):
                    if not isinstance(fam, dict):
                        continue
                    name = fam.get("family")
                    if not name:
                        continue
                    family_history[name] += int(fam.get("count") or 0)
                    examples = fam.get("examples") or []
                    if name not in family_examples:
                        family_examples[name] = []
                    for ex in examples:
                        if ex not in family_examples[name]:
                            family_examples[name].append(ex)
            offenders = [name for name, total in family_history.most_common(5) if total >= 3]
            if offenders:
                lines.append(
                    "- HARD CONSTRAINT (verb-stem families banned for THIS chapter — "
                    "do NOT use any phrasing that fits these shapes; substituting a "
                    "synonym within the same family also counts as a violation):"
                )
                for name in offenders:
                    examples = family_examples.get(name, [])[:3]
                    if examples:
                        lines.append(
                            f"  • '{name}'  (e.g., {', '.join(examples)})"
                        )
                    else:
                        lines.append(f"  • '{name}'")
                lines.append(
                    "  Find a different syntactic frame entirely — different verb, "
                    "different anchor noun, or restructure the sentence so it doesn't "
                    "rest on a body-part / framing-verb crutch."
                )
        except Exception:
            pass

        return "\n".join(lines)


# ─── Blueprint Generator (runs BEFORE each chapter) ─────────────────────────

OPENING_TYPES = [
    "dialogue_mid_conversation",
    "quiet_observation",
    "setting_atmosphere",
    "character_routine",
    "time_skip_transition",
    "aftermath_of_event",
    "sensory_immersion",
    "another_character_perspective",
]

ENDING_TYPES = [
    "quiet_resolution",
    "decision_made",
    "question_unanswered",
    "dialogue_trailing_off",
    "character_alone_reflecting",
    "scene_completed_cleanly",
    "subtle_reveal",
    "shift_in_understanding",
]

CHAPTER_SHAPES = [
    "quiet_character_focus",
    "investigation_procedural",
    "confrontation_dialogue",
    "aftermath_processing",
    "relationship_deepening",
    "world_building_routine",
    "tension_escalation",
    "revelation_and_fallout",
]


async def generate_chapter_blueprint(
    orchestrator,
    chapter_number: int,
    total_chapters: int,
    chapter_plan: Dict[str, Any],
    book_bible: str,
    anti_pattern_context: str,
    style_guide: str = "",
) -> Dict[str, Any]:
    """
    Generate a structural blueprint for a chapter before it is written.

    Returns a dict with: opening_approach, chapter_shape, scenes, ending_approach,
    prose_register, timer_allowed, max_new_evidence, and specific_instructions.
    """

    plan_summary = chapter_plan.get("summary", "")
    plan_objectives = chapter_plan.get("objectives", [])
    plan_opening = chapter_plan.get("opening_type", "")
    plan_ending = chapter_plan.get("ending_type", "")
    plan_emotional_arc = chapter_plan.get("emotional_arc", "")
    plan_characters = chapter_plan.get("focal_characters", [])
    plan_pov = chapter_plan.get("pov_character", "")
    plan_transition = chapter_plan.get("transition_note", "")
    # Structural fields from enhanced book plan
    plan_chapter_shape = chapter_plan.get("chapter_shape", "")
    plan_prose_register = chapter_plan.get("prose_register", "")
    plan_tension_level = chapter_plan.get("tension_level", "")
    plan_new_developments = chapter_plan.get("new_developments", "")

    system_prompt = (
        "You are a novel architect. Create a structural blueprint for a single chapter.\n"
        "Output STRICT JSON only. No commentary, no code fences.\n"
        "Your job is to ensure THIS chapter feels completely different from recent chapters.\n"
        "Use the plan's suggested chapter_shape, prose_register, and tension_level as starting points, but OVERRIDE them if anti-pattern data shows they would repeat recent chapters.\n"
    )

    structural_guidance = ""
    if plan_chapter_shape or plan_prose_register or plan_tension_level:
        structural_guidance = "PLAN STRUCTURAL SUGGESTIONS (use as starting point, override if needed to avoid repetition):\n"
        if plan_chapter_shape:
            structural_guidance += f"- Suggested chapter shape: {plan_chapter_shape}\n"
        if plan_prose_register:
            structural_guidance += f"- Suggested prose register: {plan_prose_register}\n"
        if plan_tension_level:
            structural_guidance += f"- Suggested tension level: {plan_tension_level}\n"
        if plan_new_developments:
            structural_guidance += f"- Suggested new developments: {plan_new_developments}\n"
        structural_guidance += "\n"

    user_prompt = (
        f"Create a structural blueprint for Chapter {chapter_number} of {total_chapters}.\n\n"
        f"CHAPTER PLAN:\n"
        f"- Summary: {plan_summary}\n"
        f"- Objectives: {json.dumps(plan_objectives)}\n"
        f"- Opening type: {plan_opening}\n"
        f"- Ending type: {plan_ending}\n"
        f"- Emotional arc: {plan_emotional_arc}\n"
        f"- Focal characters: {json.dumps(plan_characters)}\n"
        f"- POV: {plan_pov}\n"
    )
    if plan_transition:
        user_prompt += f"- Transition from previous chapter: {plan_transition}\n"
    user_prompt += f"\n{structural_guidance}"
    user_prompt += f"BOOK BIBLE (excerpt):\n{book_bible[:3000]}\n\n"
    if style_guide:
        user_prompt += f"STYLE GUIDE:\n{style_guide[:1500]}\n\n"
    if anti_pattern_context:
        user_prompt += f"{anti_pattern_context}\n\n"

    user_prompt += (
        "Create a blueprint with this JSON schema:\n"
        "{\n"
        '  "opening_approach": "Specific description of how the chapter opens — first 2-3 paragraphs",\n'
        '  "chapter_shape": "The overall structure/rhythm of the chapter",\n'
        '  "scenes": [\n'
        '    {"scene_number": 1, "description": "What happens", "tone": "quiet/tense/warm/etc", "word_budget": 1000},\n'
        '    ...\n'
        '  ],\n'
        '  "ending_approach": "Specific description of how the chapter ends — last 2-3 paragraphs",\n'
        '  "prose_register": "How intense the prose should be: plain/moderate/lyrical",\n'
        '  "tension_level": "low/moderate/high — must vary from recent chapters",\n'
        '  "new_developments": 1,\n'
        '  "specific_instructions": "Any chapter-specific craft notes"\n'
        "}\n\n"
        "Rules:\n"
        "- The opening_approach must be SPECIFIC and DIFFERENT from recent chapters.\n"
        "- Plan 2-4 scenes that fill the word budget naturally.\n"
        "- At least one scene should be quiet/character-focused.\n"
        "- prose_register should vary: if recent chapters were intense, make this one mostly plain.\n"
        "- tension_level must alternate: do not have 3 high-tension chapters in a row.\n"
        "- new_developments should be 0-2. Some chapters should deepen existing threads, not introduce new ones.\n"
        f"- Vary the opening: choose from {json.dumps(OPENING_TYPES)}\n"
        f"- Vary the ending: choose from {json.dumps(ENDING_TYPES)}\n"
        f"- Vary the chapter structure: choose from {json.dumps(CHAPTER_SHAPES)}\n"
    )

    try:
        response = await orchestrator._make_api_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=1500,
            response_format={"type": "json_object"},
            model_role="planner",
        )
    except Exception:
        return _default_blueprint(chapter_number, total_chapters)

    content = ""
    if hasattr(response, "output_text"):
        content = response.output_text
    elif response and hasattr(response, "choices"):
        content = response.choices[0].message.content

    if not content:
        return _default_blueprint(chapter_number, total_chapters)

    try:
        blueprint = json.loads(content)
    except Exception:
        return _default_blueprint(chapter_number, total_chapters)

    blueprint.setdefault("opening_approach", "Start in media res")
    blueprint.setdefault("chapter_shape", "balanced")
    blueprint.setdefault("scenes", [])
    blueprint.setdefault("ending_approach", "End on a quiet note")
    blueprint.setdefault("prose_register", "moderate")
    blueprint.setdefault("tension_level", "moderate")
    blueprint.setdefault("new_developments", 1)
    blueprint.setdefault("specific_instructions", "")

    return blueprint


def _default_blueprint(chapter_number: int, total_chapters: int) -> Dict[str, Any]:
    """Fallback blueprint when LLM call fails."""
    position = chapter_number / max(total_chapters, 1)
    if position <= 0.15:
        shape = "world_building_routine"
        register = "moderate"
        tension = "low"
    elif position >= 0.85:
        shape = "revelation_and_fallout"
        register = "moderate"
        tension = "high"
    elif chapter_number % 3 == 0:
        shape = "quiet_character_focus"
        register = "plain"
        tension = "low"
    else:
        shape = "balanced"
        register = "moderate"
        tension = "moderate"

    return {
        "opening_approach": OPENING_TYPES[chapter_number % len(OPENING_TYPES)],
        "chapter_shape": shape,
        "scenes": [],
        "ending_approach": ENDING_TYPES[chapter_number % len(ENDING_TYPES)],
        "prose_register": register,
        "tension_level": tension,
        "new_developments": 1,
        "specific_instructions": "",
    }


def format_blueprint_for_prompt(blueprint: Dict[str, Any]) -> str:
    """Format a blueprint as a prompt section for chapter generation."""
    lines = ["CHAPTER BLUEPRINT (follow this structural plan):"]
    lines.append(f"- OPENING: {blueprint.get('opening_approach', 'Start naturally')}")
    lines.append(f"- CHAPTER SHAPE: {blueprint.get('chapter_shape', 'balanced')}")
    lines.append(f"- ENDING: {blueprint.get('ending_approach', 'End cleanly')}")
    register = blueprint.get('prose_register', 'moderate')
    if register == 'plain':
        register_desc = (
            "PLAIN — Most sentences should be short, direct, and invisible. "
            "Example: 'She sat down. The coffee was cold. She drank it anyway.' "
            "NOT: 'She lowered herself into the chair, the ceramic mug radiating a chill that matched the emptiness pooling in her chest.' "
            "Save ONE moment of vivid imagery for the chapter's emotional peak."
        )
    elif register == 'lyrical':
        register_desc = (
            "LYRICAL — Allow richer imagery and longer sentences, but still vary. "
            "Follow every lyrical sentence with a plain one. "
            "Even in lyrical mode, at least 30% of paragraphs should be functional and unadorned."
        )
    else:
        register_desc = (
            "MODERATE — Mix plain and vivid. Most paragraphs functional, with 3-4 moments of stronger imagery. "
            "Vary sentence length: short declaratives between longer descriptive sentences."
        )
    lines.append(f"- PROSE REGISTER: {register_desc}")
    lines.append(f"- TENSION LEVEL: {blueprint.get('tension_level', 'moderate')}")
    lines.append(f"- NEW DEVELOPMENTS: Max {blueprint.get('new_developments', 1)} significant new plot developments. Deepen existing threads where possible.")

    scenes = blueprint.get("scenes", [])
    if scenes:
        lines.append("- SCENE PLAN:")
        for scene in scenes:
            desc = scene.get("description", "")
            tone = scene.get("tone", "")
            budget = scene.get("word_budget", "")
            lines.append(f"  Scene {scene.get('scene_number', '?')}: {desc} (tone: {tone}, ~{budget} words)")

    instructions = blueprint.get("specific_instructions", "")
    if instructions:
        lines.append(f"- CRAFT NOTES: {instructions}")

    return "\n".join(lines)
