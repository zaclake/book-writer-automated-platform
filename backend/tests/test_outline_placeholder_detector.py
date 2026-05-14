#!/usr/bin/env python3
"""Tests for Path A+ P3.1 — fail-closed continuation-placeholder detector.

The outline reference must contain ONE chapter block per chapter, not "[Continue
with detailed chapter breakdown for each subsequent chapter...]" as literal
output. These tests verify:

1. The literal placeholder shipped in production (line 116 of
   ref_gen_1776112980/rich/outline.md) is detected.
2. A diverse family of equivalent placeholders is detected (same intent,
   different phrasing).
3. The detector does NOT false-positive on legitimate filled-in chapter
   blocks or bracketed schema-template guidance in the prompt.
4. The detector is scoped to the 'outline' reference type — other references
   (where bracketed examples are common) are not affected.
5. The detector can find multiple distinct placeholder hits and caps at 5.
"""

from __future__ import annotations

from backend.utils.reference_content_generator import ReferenceContentGenerator


def _make_generator(monkeypatch) -> ReferenceContentGenerator:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    # Constructor needs a key but we never make a real call here.
    return ReferenceContentGenerator()


# ──────────────────────────────────────────────────────────────────────────
# 1. The exact production-shipped placeholder
# ──────────────────────────────────────────────────────────────────────────


class TestProductionPlaceholder:
    def test_exact_string_from_ref_gen_output_is_detected(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        content = (
            "### Chapter 1: Return to Dunmore\n"
            "- Stuff happens\n\n"
            "[Continue with detailed chapter breakdown for each subsequent chapter, "
            "maintaining the same level of detail and consistency with the story's "
            "themes and structure.]\n\n"
            "## Information Reveals Schedule\n"
        )
        hits = gen._detect_continuation_placeholders(content, "outline")
        assert hits, "Production-shipped placeholder must be detected"
        assert any("continue" in h.lower() for h in hits)


# ──────────────────────────────────────────────────────────────────────────
# 2. Family of equivalent placeholders
# ──────────────────────────────────────────────────────────────────────────


class TestPlaceholderFamily:
    def test_repeat_format_for_each_remaining(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        content = (
            "### Chapter 1: Foo\n- Stuff\n\n"
            "[Repeat the above format for each remaining chapter.]"
        )
        assert gen._detect_continuation_placeholders(content, "outline")

    def test_each_remaining_chapter_follows_pattern(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        content = (
            "### Chapter 1: Foo\n- Stuff\n\n"
            "[Each remaining chapter follows this pattern.]"
        )
        assert gen._detect_continuation_placeholders(content, "outline")

    def test_for_brevity_remaining_omitted(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        content = "[For brevity, remaining chapters omitted.]"
        assert gen._detect_continuation_placeholders(content, "outline")

    def test_remaining_chapters_abbreviated(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        content = "[Remaining chapters abbreviated.]"
        assert gen._detect_continuation_placeholders(content, "outline")

    def test_continue_similarly(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        content = "[Continue similarly for chapters 4 through 26.]"
        assert gen._detect_continuation_placeholders(content, "outline")

    def test_chapters_n_to_m_omitted(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        content = "[Chapters 12-26 omitted for brevity.]"
        assert gen._detect_continuation_placeholders(content, "outline")

    def test_parenthesized_continuation(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        content = "(Continue with detailed chapter breakdown for chapters 8-25.)"
        assert gen._detect_continuation_placeholders(content, "outline")

    def test_subsequent_chapters_follow_same_pattern(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        content = "[Subsequent chapters follow the same pattern.]"
        assert gen._detect_continuation_placeholders(content, "outline")


# ──────────────────────────────────────────────────────────────────────────
# 3. NOT false-positive on legitimate content
# ──────────────────────────────────────────────────────────────────────────


class TestNoFalsePositives:
    def test_filled_chapter_block_is_clean(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        content = (
            "### Chapter 5: The Cottage\n"
            "- **Act Position:** Act I, 18%\n"
            "- **Word Count Target:** 3000\n"
            "- **Primary Purpose:** Nora finds her father's locked drawer.\n"
            "- **POV Focus:** Nora\n"
            "- **Emotional Arc:** Resignation → Suspicion\n"
            "- **Plot Advancement:** The drawer reveals coded notes.\n"
            "- **Scenes:**\n"
            "  - **Scene 1:** Cottage study — Nora alone — She forces the drawer.\n"
        )
        assert gen._detect_continuation_placeholders(content, "outline") == []

    def test_bracketed_schema_guidance_not_a_placeholder(self, monkeypatch):
        """The outline prompt itself contains brackets like [Specific opening
        scene that establishes tone and character]. If the model EXTRACTS
        those (rather than filling them in) we'd want to flag it — but the
        test guards that we don't false-positive on legitimate filled-in
        bracketed metadata in the body of a chapter block."""
        gen = _make_generator(monkeypatch)
        content = (
            "### Chapter 1: Return to Dunmore\n"
            "- **Word Count Target:** [3000-3500 words]\n"  # legitimate range bracket
            "- **POV Focus:** Nora\n"
            "- **Bridge to Next:** Leads into her decision to investigate.\n"
        )
        assert gen._detect_continuation_placeholders(content, "outline") == []

    def test_running_text_with_continue_is_not_a_placeholder(self, monkeypatch):
        """A chapter description that uses the word "continue" in prose must
        not trip the detector."""
        gen = _make_generator(monkeypatch)
        content = (
            "### Chapter 5: The Search\n"
            "Nora must continue searching the cottage, even when she suspects "
            "what she will find. The chapter ends as she lifts the floorboard.\n"
        )
        assert gen._detect_continuation_placeholders(content, "outline") == []

    def test_empty_content_is_clean(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        assert gen._detect_continuation_placeholders("", "outline") == []
        assert gen._detect_continuation_placeholders(None, "outline") == []  # type: ignore[arg-type]


# ──────────────────────────────────────────────────────────────────────────
# 4. Scoped to outline only
# ──────────────────────────────────────────────────────────────────────────


class TestScopedToOutline:
    def test_non_outline_reference_skips_detection(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        offending = (
            "### Style example\n"
            "[Continue with detailed chapter breakdown for each subsequent chapter.]"
        )
        # In a style guide, bracketed examples may be intentional. Detector
        # only fires for outline.
        assert gen._detect_continuation_placeholders(offending, "style-guide") == []
        assert gen._detect_continuation_placeholders(offending, "characters") == []
        assert gen._detect_continuation_placeholders(offending, "outline") != []


# ──────────────────────────────────────────────────────────────────────────
# 5. Multi-hit + cap
# ──────────────────────────────────────────────────────────────────────────


class TestMultiHit:
    def test_finds_multiple_distinct_placeholders(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        content = (
            "[Continue with detailed chapter breakdown for chapters 4-10.]\n\n"
            "[For brevity, remaining chapters omitted.]\n\n"
            "[Each remaining chapter follows this pattern.]\n\n"
            "[Subsequent chapters follow the same pattern.]\n\n"
            "[Continue similarly for chapters 20-26.]\n\n"
        )
        hits = gen._detect_continuation_placeholders(content, "outline")
        assert len(hits) >= 3

    def test_caps_at_five_hits(self, monkeypatch):
        gen = _make_generator(monkeypatch)
        # Build a content string that would otherwise yield far more than 5 hits.
        many = "\n\n".join(
            "[Continue with detailed chapter breakdown for chapters X.]" for _ in range(20)
        )
        hits = gen._detect_continuation_placeholders(many, "outline")
        assert len(hits) <= 5
