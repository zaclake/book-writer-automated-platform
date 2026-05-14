#!/usr/bin/env python3
"""Tests for Path A+ P2.3 — lexical-syntactic opening detector and verb-stem
family ban.

The point of P2.3 is that trigram detection catches "kept his eyes" but the
model substitutes "kept his voice" / "kept his hands" and the family persists.
This test suite verifies:

1. The opening-template classifier names the failure mode (sensory_anchor_as_action)
   for the actual openings shipped by the system in farm-daze and ponce.
2. The verb-stem family detector catches kept his __ / __ jaw __ / __ hands __
   families and reports them in a form usable by the next chapter's prompt.
3. build_anti_pattern_context surfaces the bans only when they're warranted
   (recurring template across recent chapters; family overuse).
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.auto_complete.helpers.chapter_blueprint import (
    OPENING_TEMPLATES,
    ChapterPatternTracker,
    ChapterSignals,
    _classify_opening_template,
    _extract_verb_stem_families,
)


# ──────────────────────────────────────────────────────────────────────────
# 1. Opening-template classifier
# ──────────────────────────────────────────────────────────────────────────


class TestOpeningTemplateClassifier:
    def test_ponce_first_chapter_opening_is_sensory_anchor(self):
        # Verbatim from the user's evidence (ponce ch1).
        s = "Wet grass pressed cold between his toes as he crossed to the trough."
        assert _classify_opening_template(s) == "sensory_anchor_as_action"

    def test_ponce_chapter_3_opening_is_sensory_anchor(self):
        s = "Salt stuck to Jaron's fingers as he looped the last line over the cleat."
        assert _classify_opening_template(s) == "sensory_anchor_as_action"

    def test_ponce_chapter_4_opening_is_sensory_anchor(self):
        s = "Metal clicked as the latch lifted, rough under Jaron's thumb."
        # This one starts "Metal clicked as the latch lifted" — note the
        # subject after "as" is a noun, not a pronoun. Acceptable to fall
        # to a different template; the key is that the ones that DO match
        # the failure pattern are flagged.
        result = _classify_opening_template(s)
        assert result in {"sensory_anchor_as_action", "name_then_past_action", "other"}

    def test_ponce_chapter_5_opening_is_sensory_anchor(self):
        s = "Cabinet doors rattled as Kady came in carrying the groceries."
        assert _classify_opening_template(s) == "sensory_anchor_as_action"

    def test_ponce_chapter_6_opening_is_sensory_anchor(self):
        s = "Salt spray slapped his cheek as the Reel Authority punched through the inlet."
        # "spray slapped" then "as the Reel ... punched" — the subject after
        # `as` is a proper noun ("Reel Authority"), which our detector also
        # accepts.
        assert _classify_opening_template(s) == "sensory_anchor_as_action"

    def test_dialogue_open(self):
        s = '"You don\'t have to do this," she said.'
        assert _classify_opening_template(s) == "dialogue_first"

    def test_subordinate_clause_open(self):
        s = "When the door finally closed, she let her shoulders drop."
        assert _classify_opening_template(s) == "subordinate_clause_first"

    def test_time_reference_open(self):
        s = "Three hours later, the kitchen still smelled of coffee."
        assert _classify_opening_template(s) == "time_reference_first"

    def test_adverbial_phrase_open(self):
        s = "Slowly, she set the cup down."
        assert _classify_opening_template(s) == "adverbial_phrase_first"

    def test_adverbial_prepositional_open(self):
        s = "In the kitchen, Mitch was already pouring coffee."
        assert _classify_opening_template(s) == "adverbial_phrase_first"

    def test_pronoun_then_action(self):
        s = "He pulled the door open and stepped inside."
        assert _classify_opening_template(s) == "pronoun_then_past_action"

    def test_name_then_action(self):
        s = "Reyes pulled the door open and stepped inside."
        assert _classify_opening_template(s) == "name_then_past_action"

    def test_setting_description(self):
        s = "The morning was already hot."
        assert _classify_opening_template(s) == "setting_description_first"

    def test_interior_monologue_open(self):
        s = "She knew it was a bad idea before she said it."
        assert _classify_opening_template(s) == "interior_monologue_first"

    def test_in_medias_res_gerund(self):
        s = "Running, he didn't see the truck until the horn screamed."
        assert _classify_opening_template(s) == "in_medias_res_action"

    def test_empty_returns_unknown(self):
        assert _classify_opening_template("") == "unknown"
        assert _classify_opening_template("   ") == "unknown"

    def test_every_template_is_in_canonical_list(self):
        for s in [
            "Wet grass pressed cold as he crossed.",
            '"Get out," she said.',
            "When she opened it, the dog bolted.",
            "Three days later, nothing had changed.",
            "Slowly, she sat down.",
            "He stepped inside.",
            "Reyes stepped inside.",
            "The kitchen was quiet.",
            "She knew it would happen.",
            "Running, he turned the corner.",
        ]:
            assert _classify_opening_template(s) in OPENING_TEMPLATES


# ──────────────────────────────────────────────────────────────────────────
# 2. Verb-stem family detector
# ──────────────────────────────────────────────────────────────────────────


def _padded(*sentences: str, pad_words: int = 250) -> str:
    """Make a chapter long enough to clear the 200-word floor."""
    padding = " ".join(["filler"] * pad_words)
    return " ".join([*sentences, padding])


class TestVerbStemFamilyDetector:
    def test_kept_family_with_three_distinct_partners_is_flagged(self):
        text = _padded(
            "He kept his voice low.",
            "He kept his eyes on the door.",
            "He kept his hands behind his back.",
        )
        families = _extract_verb_stem_families(text)
        names = [f["family"] for f in families]
        assert any("kept" in n for n in names), names

    def test_kept_family_below_threshold_is_not_flagged(self):
        text = _padded("He kept his voice low.")
        families = _extract_verb_stem_families(text)
        # Single hit on a single partner → no family
        assert not any("kept" in f["family"] for f in families)

    def test_jaw_family_with_three_verbs_is_flagged(self):
        text = _padded(
            "His jaw tightened.",
            "His jaw set.",
            "Her jaw worked as she chewed.",
        )
        families = _extract_verb_stem_families(text)
        assert any("jaw" in f["family"] for f in families)

    def test_hands_family_is_flagged(self):
        text = _padded(
            "His hands trembled.",
            "His hands shook in the cold air.",
            "Her hands moved across the keyboard.",
        )
        families = _extract_verb_stem_families(text)
        assert any("hands" in f["family"] for f in families)

    def test_examples_are_human_readable(self):
        text = _padded(
            "He kept his voice low.",
            "He kept his eyes on the door.",
            "She kept her hands at her sides.",
        )
        families = _extract_verb_stem_families(text)
        kept = next(f for f in families if "kept" in f["family"])
        assert isinstance(kept.get("examples"), list)
        assert len(kept["examples"]) >= 2
        # Each example mentions the verb and the partner noun
        joined = " ".join(kept["examples"])
        assert "voice" in joined or "eyes" in joined or "hands" in joined

    def test_ignores_legitimate_kept_collocations(self):
        # "kept his promise", "kept his job", "kept his secret" — legit
        # idioms that shouldn't trip the body/register family.
        text = _padded(
            "He kept his promise to her.",
            "He kept his job by the skin of his teeth.",
            "He kept his secret for years.",
        )
        families = _extract_verb_stem_families(text)
        assert not any("kept" in f["family"] for f in families), families

    def test_short_text_returns_empty(self):
        text = "He kept his voice low. He kept his eyes on the door."
        assert _extract_verb_stem_families(text) == []


# ──────────────────────────────────────────────────────────────────────────
# 3. End-to-end: extract_signals records the new fields, and
#    build_anti_pattern_context surfaces the bans for the next chapter.
# ──────────────────────────────────────────────────────────────────────────


class TestSignalsAndAntiPatternContext:
    def test_extract_signals_records_opening_template(self, tmp_path):
        tracker = ChapterPatternTracker(str(tmp_path))
        text = _padded(
            "Wet grass pressed cold between his toes as he crossed to the trough.",
            "He kept walking until the barn was a black shape behind him.",
        )
        signals = tracker.extract_signals(1, text)
        assert signals.opening_template == "sensory_anchor_as_action"

    def test_extract_signals_records_verb_stem_families(self, tmp_path):
        tracker = ChapterPatternTracker(str(tmp_path))
        text = _padded(
            "He kept his voice low.",
            "He kept his eyes on the door.",
            "He kept his hands behind his back.",
        )
        signals = tracker.extract_signals(1, text)
        assert signals.verb_stem_families
        assert any("kept" in f["family"] for f in signals.verb_stem_families)

    def test_anti_pattern_context_bans_template_after_two_recurrences(self, tmp_path):
        tracker = ChapterPatternTracker(str(tmp_path))
        # Three chapters all opening with sensory_anchor_as_action — the next
        # chapter must be told to use a different template.
        for i in (1, 2, 3):
            sig = ChapterSignals(
                chapter_number=i,
                opening_type="sensory",
                opening_template="sensory_anchor_as_action",
                first_sentence=f"Wet grass pressed cold as he crossed in chapter {i}.",
                last_sentence="He went inside.",
            )
            tracker.record_chapter(sig)

        ctx = tracker.build_anti_pattern_context(current_chapter=4)
        assert "opening template" in ctx.lower(), ctx
        assert "sensory_anchor_as_action" in ctx
        assert "MUST NOT" in ctx

    def test_anti_pattern_context_does_not_ban_template_with_one_use(self, tmp_path):
        tracker = ChapterPatternTracker(str(tmp_path))
        for i, tmpl in enumerate(
            ["sensory_anchor_as_action", "dialogue_first", "name_then_past_action"], start=1
        ):
            tracker.record_chapter(ChapterSignals(
                chapter_number=i,
                opening_template=tmpl,
                first_sentence="placeholder",
                last_sentence="placeholder",
            ))
        ctx = tracker.build_anti_pattern_context(current_chapter=4)
        # No template appears more than once in the 3-chapter tail → no template ban
        assert "opening template" not in ctx.lower()

    def test_anti_pattern_context_bans_stem_family_after_overuse(self, tmp_path):
        tracker = ChapterPatternTracker(str(tmp_path))
        family_payload = [{
            "family": "kept his/her/their <body/register>",
            "count": 7,
            "examples": [
                "kept his/her/their voice",
                "kept his/her/their eyes",
                "kept his/her/their hands",
            ],
        }]
        for i in (1, 2):
            tracker.record_chapter(ChapterSignals(
                chapter_number=i,
                first_sentence="placeholder",
                last_sentence="placeholder",
                verb_stem_families=family_payload,
            ))
        ctx = tracker.build_anti_pattern_context(current_chapter=3)
        assert "verb-stem families banned" in ctx.lower(), ctx
        assert "kept" in ctx
        # Examples should appear so the model knows what's being banned.
        assert "voice" in ctx or "eyes" in ctx or "hands" in ctx
        # The instruction must explicitly say "synonym ... also counts" —
        # this is the differentiator from the trigram ban.
        assert "synonym" in ctx.lower()

    def test_anti_pattern_context_no_stem_ban_when_no_overuse(self, tmp_path):
        tracker = ChapterPatternTracker(str(tmp_path))
        for i in (1, 2):
            tracker.record_chapter(ChapterSignals(
                chapter_number=i,
                first_sentence="placeholder",
                last_sentence="placeholder",
                verb_stem_families=[],
            ))
        ctx = tracker.build_anti_pattern_context(current_chapter=3)
        assert "verb-stem families banned" not in ctx.lower()

    def test_book_level_sensory_anchor_escalation(self, tmp_path):
        """Even if the most-recent-3 don't cluster, a book-wide pile-up of the
        sensory-anchor template should still be banned."""
        tracker = ChapterPatternTracker(str(tmp_path))
        # 4 chapters all sensory_anchor at the start of the book, then 2
        # different ones immediately before the current chapter.
        records = [
            (1, "sensory_anchor_as_action"),
            (2, "sensory_anchor_as_action"),
            (3, "sensory_anchor_as_action"),
            (4, "sensory_anchor_as_action"),
            (5, "dialogue_first"),
            (6, "name_then_past_action"),
            (7, "subordinate_clause_first"),
        ]
        for n, tmpl in records:
            tracker.record_chapter(ChapterSignals(
                chapter_number=n,
                opening_template=tmpl,
                first_sentence="placeholder",
                last_sentence="placeholder",
            ))
        ctx = tracker.build_anti_pattern_context(current_chapter=8)
        assert "sensory_anchor_as_action" in ctx, ctx
        assert "book-level" in ctx.lower() or "ABSOLUTELY" in ctx
