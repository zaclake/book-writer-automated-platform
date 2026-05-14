#!/usr/bin/env python3
"""Tests for Path A+ P2.4 — bounded literary sniff-test pass.

The sniff test is "one critique call + one targeted-rewrite call, capped at 5
paragraph rewrites, opt-out via ENABLE_SNIFF_TEST=false". These tests verify:

1. Both LLM calls route through the editor tier (not drafter, not planner).
2. The critique JSON is parsed safely; bad JSON / unrelated payloads
   produce ``{skipped: True, reason: ...}`` rather than blowing up.
3. The rewrite cap (MAX_REWRITES_PER_CHAPTER) is enforced.
4. apply_targeted_rewrites only invokes the LLM if at least one quoted
   paragraph can be located in the chapter; unmatched quotes are reported
   in info, not silently lost.
5. The wrapper accepts the rewritten chapter only when it's plausibly the
   full chapter (>= 60% of original word count).
6. ENABLE_SNIFF_TEST=false short-circuits the critique cleanly.
7. Short chapters (< MIN_WORDS_FOR_SNIFF_TEST) are skipped without an LLM call.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

from backend.auto_complete.helpers import sniff_test as sniff_mod
from backend.auto_complete.helpers.sniff_test import (
    MAX_REWRITES_PER_CHAPTER,
    MAX_TIC_REWRITES,
    MIN_WORDS_FOR_SNIFF_TEST,
    apply_targeted_rewrites,
    is_sniff_test_enabled,
    run_sniff_test,
    run_sniff_test_and_rewrite,
    _extract_intra_chapter_tics,
    _find_paragraph_in_chapter,
    build_tic_rewrites,
    build_banned_phrase_rewrites,
)
from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig


def _make_orchestrator(monkeypatch) -> LLMOrchestrator:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    return LLMOrchestrator(
        model="gpt-4.1",
        retry_config=RetryConfig(max_retries=0),
        user_id="sniff-test-user",
        enable_billing=False,
    )


class _Resp:
    """Minimal fake OpenAI response — has .choices[0].message.content but
    NOT .output_text (which would route content extraction down the wrong
    code path in the orchestrator)."""

    def __init__(self, content: str) -> None:
        class _Msg:
            def __init__(self, c: str) -> None:
                self.content = c

        class _Choice:
            def __init__(self, c: str) -> None:
                self.message = _Msg(c)
                self.finish_reason = "stop"

        class _Usage:
            prompt_tokens = 1
            completion_tokens = 1
            total_tokens = 2

        self.choices = [_Choice(content)]
        self.usage = _Usage()


def _set_chat_response(orch: LLMOrchestrator, capture: List[Dict[str, Any]], payloads: List[str]) -> None:
    """Wire orchestrator to return ``payloads`` in order; record kwargs to capture."""
    iter_payloads = iter(payloads)

    def fake_create(**kwargs):
        capture.append(kwargs)
        try:
            body = next(iter_payloads)
        except StopIteration:
            body = ""
        return _Resp(body)

    orch.client.chat.completions.create = fake_create  # type: ignore[assignment]


_FILLER_LINES = [
    "A magpie cracked something against the gravel and flapped away again.",
    "Cottonwood seed drifted across the porch boards in long, lazy curls.",
    "Heat trembled over the asphalt where the lane met the highway.",
    "Far off, a tractor coughed twice and settled into a steady rasp.",
    "Inside, the refrigerator clicked, hummed, and went quiet again.",
    "Behind the barn, swallows traced loose figure-eights through dust.",
    "A single bell ratcheted across two pastures and was answered by a dog.",
    "Sunlight pooled at the porch step, sliced thin by spring hinges.",
    "Wheat moved in slow, separate gusts, like a crowd that couldn't agree.",
    "The yard had a smell of cut diesel and last night's rain on warm stone.",
    "Mitch listened to wires above the road tick in their slow tension.",
    "Ruth let her hand rest on the railing, then drew it back, considering.",
    "Out past the fence, a black calf turned its head and lost interest.",
    "The mailbox flag was still up; she'd told him about it twice already.",
    "An old combine sat out in the lot like something a museum forgot.",
    "Steam rose off a coffee mug somebody had abandoned by the back step.",
    "A box of matches sat half-empty on the windowsill above the basin.",
    "The radio in the kitchen was tuned to weather and turned down low.",
    "Two cats were arguing under the back porch in some private dialect.",
    "A pickup with one headlight idled at the corner stop sign for too long.",
    "Wires crossed overhead to a transformer somebody had spray-painted blue.",
    "The fields beyond looked seasick in the heat, leaning every direction.",
    "A windsock hung limp at the edge of the airstrip, faded and patched.",
    "Children somewhere laughed and then suddenly didn't; nobody asked why.",
    "The coffee was thin enough to read a phone number through, no matter.",
    "An ice cream truck went down the back road playing a single broken note.",
    "Hay bales sat in the south paddock like loaves nobody wanted to eat.",
    "The handle of the kitchen drawer had been wrapped in electrical tape twice.",
    "A scoured saucepan dried upside down on a folded dishrag near the sink.",
    "Frost from yesterday's milk had gathered along the lip of the steel can.",
    "A plastic bag caught itself on a fence post and fluttered like an apology.",
    "The driveway gravel held an oily stripe where his transmission used to leak.",
    "A clothespin with somebody's old initials sat on the stoop for no reason.",
    "Out by the silo a generator coughed itself awake and then settled in.",
    "The neighbor's flag was at half-mast for a reason she had forgotten.",
    "An empty feed sack rolled across the lot, lazily, on a current of breeze.",
    "Somewhere a screen door slapped shut and whoever it was didn't come back.",
    "A pheasant tracked past the woodpile, eyeing the dog without committing.",
    "The thermometer on the porch post read three degrees above honest.",
    "Bees worked the lavender along the foundation in their slow, exact way.",
    "Down at the pond, a heron stood like punctuation somebody had penciled in.",
    "Light bent around the cistern lid and pooled in the long grass.",
    "Hummingbirds buzzed the feeder twice and dispersed, unimpressed.",
    "The wind chimes she'd hung last spring had finally stopped clattering.",
    "A laundry line ran from the porch to the garage and held nothing today.",
    "An aluminum can rattled across the road and was hit by nothing in particular.",
    "Above them, contrails crossed and uncrossed in absent geometry.",
    "The kitchen radio was working through somebody else's local obituary.",
    "A barred owl muttered from the tree line, clearly insulted by morning.",
    "Crows held a brief conference on the power line and adjourned by twos.",
    "Smoke drifted up from a brush pile two miles off and smelled like fall.",
    "The barn cat rolled itself across a patch of warm concrete, satisfied.",
    "A garbage truck downshifted on the rise and groaned through its turn.",
    "Cumulus had gathered in the west like wadded receipts somebody saved.",
]


def _make_chapter(extra: str = "", min_words: int = MIN_WORDS_FOR_SNIFF_TEST + 50) -> str:
    """Build a chapter long enough to clear the MIN_WORDS_FOR_SNIFF_TEST floor.

    Uses a rotating bank of filler lines (no repeats) so the intra-chapter
    tic detector doesn't pick anything up by default. Tests that want the
    tic detector to fire build their own chapter with intentional repetition.
    """
    base = (
        "Mitch parked the truck at the edge of the lane.\n\n"
        "Ruth stepped onto the porch, hands tight at her sides. She did not look at him.\n\n"
        "The dog sat in the back of the truck and did not bark.\n\n"
    )
    i = 0
    while len(base.split()) < min_words:
        base += _FILLER_LINES[i % len(_FILLER_LINES)] + "\n\n"
        i += 1
    if extra:
        base = base + "\n\n" + extra
    return base


# ──────────────────────────────────────────────────────────────────────────
# 1. Env gate
# ──────────────────────────────────────────────────────────────────────────


class TestEnvGate:
    def test_enabled_by_default(self, monkeypatch):
        monkeypatch.delenv("ENABLE_SNIFF_TEST", raising=False)
        assert is_sniff_test_enabled() is True

    def test_explicit_false_disables(self, monkeypatch):
        for v in ("false", "FALSE", "0", "no", "No"):
            monkeypatch.setenv("ENABLE_SNIFF_TEST", v)
            assert is_sniff_test_enabled() is False, v

    def test_explicit_true_enables(self, monkeypatch):
        monkeypatch.setenv("ENABLE_SNIFF_TEST", "true")
        assert is_sniff_test_enabled() is True

    def test_run_sniff_test_skipped_when_disabled(self, monkeypatch):
        monkeypatch.setenv("ENABLE_SNIFF_TEST", "false")
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        _set_chat_response(orch, captured, ["{}"])
        chapter = _make_chapter()
        result = asyncio.run(run_sniff_test(orch, chapter, 1))
        assert result.get("skipped") is True
        assert result.get("reason") == "disabled_by_env"
        assert len(captured) == 0, "Disabled gate must NOT call the LLM"


# ──────────────────────────────────────────────────────────────────────────
# 2. Critique LLM call
# ──────────────────────────────────────────────────────────────────────────


class TestRunSniffTest:
    def test_short_chapter_is_skipped_without_llm_call(self, monkeypatch):
        monkeypatch.setenv("ENABLE_SNIFF_TEST", "true")
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        _set_chat_response(orch, captured, ["{}"])
        # Below the floor.
        result = asyncio.run(run_sniff_test(orch, "He waited.", 1))
        assert result.get("skipped") is True
        assert result.get("reason") == "chapter_too_short"
        assert len(captured) == 0

    def test_critique_call_uses_editor_tier(self, monkeypatch):
        monkeypatch.setenv("ENABLE_SNIFF_TEST", "true")
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        payload = json.dumps({
            "critique_summary": "Reads like the model's default sensory mode.",
            "strongest_paragraph": "Ruth stepped onto the porch ...",
            "unearned_beat": "The reconciliation lands too easily.",
            "targeted_rewrites": [],
        })
        _set_chat_response(orch, captured, [payload])
        asyncio.run(run_sniff_test(orch, _make_chapter(), 1))
        assert len(captured) == 1
        assert captured[0]["model"] == "gpt-5.5", "must use editor tier"

    def test_critique_returns_normalized_rewrites(self, monkeypatch):
        monkeypatch.setenv("ENABLE_SNIFF_TEST", "true")
        orch = _make_orchestrator(monkeypatch)
        payload = json.dumps({
            "critique_summary": "Three AI tells: gesture clutter, sensory anchor, tidy ending.",
            "strongest_paragraph": "Ruth stepped ...",
            "unearned_beat": "He forgives without payment.",
            "targeted_rewrites": [
                {
                    "paragraph_quote": "Ruth stepped onto the porch, hands tight at her sides. She did not look at him.",
                    "problem": "Reflex gesture combo.",
                    "rewrite_directive": "Cut the gesture; render her stillness through delay only.",
                },
                {
                    # Missing rewrite_directive → must be dropped.
                    "paragraph_quote": "The dog sat in the back of the truck and did not bark.",
                    "problem": "Filler beat.",
                },
            ],
        })
        _set_chat_response(orch, [], [payload])
        result = asyncio.run(run_sniff_test(orch, _make_chapter(), 1))
        assert result["skipped"] is False
        # Tic detector adds entries deterministically, but the LLM-derived
        # rewrite (stepped-onto-the-porch) must be present and the bad one
        # (no rewrite_directive) must be dropped.
        quotes = [r["paragraph_quote"] for r in result["targeted_rewrites"]]
        kept = [q for q in quotes if "stepped onto the porch" in q]
        dropped = [q for q in quotes if "did not bark" in q]
        assert len(kept) == 1
        assert len(dropped) == 0
        for r in result["targeted_rewrites"]:
            assert r["rewrite_directive"]

    def test_critique_caps_at_max_rewrites(self, monkeypatch):
        monkeypatch.setenv("ENABLE_SNIFF_TEST", "true")
        orch = _make_orchestrator(monkeypatch)
        many = [
            {
                "paragraph_quote": f"Para {i}",
                "problem": "x",
                "rewrite_directive": "y",
            }
            for i in range(MAX_REWRITES_PER_CHAPTER + 5)
        ]
        payload = json.dumps({"critique_summary": "x", "targeted_rewrites": many})
        _set_chat_response(orch, [], [payload])
        result = asyncio.run(run_sniff_test(orch, _make_chapter(), 1))
        # Total list (LLM + tic) must never exceed the hard cap.
        assert len(result["targeted_rewrites"]) <= MAX_REWRITES_PER_CHAPTER

    def test_critique_handles_bad_json(self, monkeypatch):
        monkeypatch.setenv("ENABLE_SNIFF_TEST", "true")
        orch = _make_orchestrator(monkeypatch)
        _set_chat_response(orch, [], ["this is not JSON {{"])
        result = asyncio.run(run_sniff_test(orch, _make_chapter(), 1))
        assert result.get("skipped") is True
        assert result.get("reason") == "json_parse_error"

    def test_critique_handles_llm_error(self, monkeypatch):
        monkeypatch.setenv("ENABLE_SNIFF_TEST", "true")
        orch = _make_orchestrator(monkeypatch)

        def boom(**kwargs):
            raise RuntimeError("openai blew up")

        orch.client.chat.completions.create = boom  # type: ignore[assignment]
        result = asyncio.run(run_sniff_test(orch, _make_chapter(), 1))
        assert result.get("skipped") is True
        assert "llm_error" in result.get("reason", "")


# ──────────────────────────────────────────────────────────────────────────
# 3. Paragraph matching + targeted rewrite
# ──────────────────────────────────────────────────────────────────────────


class TestParagraphMatching:
    def test_exact_substring_match(self):
        chapter = "Para A.\n\nPara B that is longer than the others.\n\nPara C."
        assert _find_paragraph_in_chapter(chapter, "Para B that is longer than the others.") == "Para B that is longer than the others."

    def test_whitespace_normalized_match(self):
        chapter = "Para B  spans    multiple   spaces."
        # Quote uses single spaces; chapter has multi-space runs
        assert _find_paragraph_in_chapter(chapter, "Para B spans multiple spaces.") == chapter

    def test_prefix_match_for_truncated_quote(self):
        para = "Ruth stepped onto the porch, hands tight at her sides. She did not look at him. The wind moved through the corn."
        chapter = f"Mitch parked the truck.\n\n{para}\n\nThe dog sat in the back."
        # Quote is truncated mid-paragraph (model often does this)
        truncated = "Ruth stepped onto the porch, hands tight at her sides. She did not"
        assert _find_paragraph_in_chapter(chapter, truncated) == para

    def test_returns_none_when_no_match(self):
        chapter = "Para A.\n\nPara B.\n\nPara C."
        assert _find_paragraph_in_chapter(chapter, "Completely unrelated content here.") is None


class TestApplyTargetedRewrites:
    def test_no_rewrites_returns_input(self, monkeypatch):
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        _set_chat_response(orch, captured, [""])
        text = _make_chapter()
        out, info = asyncio.run(apply_targeted_rewrites(orch, text, [], 1))
        assert out == text
        assert info["applied"] is False
        assert info["skipped_reason"] == "no_rewrites"
        assert len(captured) == 0

    def test_unmatched_quotes_skip_llm_call(self, monkeypatch):
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        _set_chat_response(orch, captured, ["should not be called"])
        text = _make_chapter()
        rewrites = [{
            "paragraph_quote": "This paragraph does not exist in the chapter at all.",
            "problem": "x",
            "rewrite_directive": "y",
        }]
        out, info = asyncio.run(apply_targeted_rewrites(orch, text, rewrites, 1))
        assert out == text
        assert info["matched"] == 0
        assert info["applied"] is False
        assert info["skipped_reason"] == "no_matched_paragraphs"
        assert len(info["unmatched_quotes"]) == 1
        assert len(captured) == 0, "must not call LLM if nothing matched"

    def test_applies_rewrite_when_paragraph_matches(self, monkeypatch):
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        text = _make_chapter()
        # Rewrite returns chapter with one paragraph swapped — same length range.
        rewritten_text = text.replace(
            "Ruth stepped onto the porch, hands tight at her sides. She did not look at him.",
            "Ruth waited on the porch. She let the silence be the answer.",
        )
        _set_chat_response(orch, captured, [rewritten_text])

        rewrites = [{
            "paragraph_quote": "Ruth stepped onto the porch, hands tight at her sides. She did not look at him.",
            "problem": "Gesture clutter.",
            "rewrite_directive": "Cut the gesture; render stillness only.",
        }]
        out, info = asyncio.run(apply_targeted_rewrites(orch, text, rewrites, 1))
        assert info["matched"] == 1
        assert info["applied"] is True
        assert "Ruth waited on the porch" in out
        assert "hands tight at her sides" not in out

    def test_rewrite_call_uses_editor_tier(self, monkeypatch):
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        text = _make_chapter()
        _set_chat_response(orch, captured, [text])  # echo back
        rewrites = [{
            "paragraph_quote": "Ruth stepped onto the porch, hands tight at her sides. She did not look at him.",
            "problem": "p",
            "rewrite_directive": "d",
        }]
        asyncio.run(apply_targeted_rewrites(orch, text, rewrites, 1))
        assert captured, "rewrite call should have happened"
        assert captured[0]["model"] == "gpt-5.5"

    def test_caps_rewrites_at_max(self, monkeypatch):
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        text = _make_chapter()
        _set_chat_response(orch, captured, [text])
        many = [
            {
                "paragraph_quote": "Ruth stepped onto the porch, hands tight at her sides. She did not look at him.",
                "problem": "p",
                "rewrite_directive": "d",
            }
            for _ in range(MAX_REWRITES_PER_CHAPTER + 3)
        ]
        _, info = asyncio.run(apply_targeted_rewrites(orch, text, many, 1))
        assert info["attempted"] == MAX_REWRITES_PER_CHAPTER

    def test_rejects_rewrite_that_shrinks_chapter(self, monkeypatch):
        """If the rewrite call returns only ~half the chapter, the model
        ignored 'return the full chapter' — keep the original."""
        orch = _make_orchestrator(monkeypatch)
        text = _make_chapter()
        # Output is way too short — fewer than 60% of the original word count.
        truncated = " ".join(text.split()[: int(len(text.split()) * 0.4)])
        _set_chat_response(orch, [], [truncated])
        rewrites = [{
            "paragraph_quote": "Ruth stepped onto the porch, hands tight at her sides. She did not look at him.",
            "problem": "p",
            "rewrite_directive": "d",
        }]
        out, info = asyncio.run(apply_targeted_rewrites(orch, text, rewrites, 1))
        assert out == text  # original preserved
        assert info["applied"] is False
        assert info["skipped_reason"] == "rewrite_too_short"


# ──────────────────────────────────────────────────────────────────────────
# 4. End-to-end wrapper
# ──────────────────────────────────────────────────────────────────────────


class TestRunSniffTestAndRewrite:
    def test_no_rewrites_means_no_rewrite_call(self, monkeypatch):
        monkeypatch.setenv("ENABLE_SNIFF_TEST", "true")
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        _set_chat_response(orch, captured, [json.dumps({
            "critique_summary": "clean",
            "targeted_rewrites": [],
        })])
        text = _make_chapter()
        out, info = asyncio.run(run_sniff_test_and_rewrite(orch, text, 1))
        assert out == text
        assert info["rewrite"]["applied"] is False
        # Only the critique call should have happened.
        assert len(captured) == 1

    def test_critique_then_rewrite_path(self, monkeypatch):
        monkeypatch.setenv("ENABLE_SNIFF_TEST", "true")
        orch = _make_orchestrator(monkeypatch)
        text = _make_chapter()
        rewritten = text.replace(
            "Ruth stepped onto the porch, hands tight at her sides. She did not look at him.",
            "Ruth waited on the porch. She let the silence be the answer.",
        )
        critique_payload = json.dumps({
            "critique_summary": "AI gestures.",
            "targeted_rewrites": [{
                "paragraph_quote": "Ruth stepped onto the porch, hands tight at her sides. She did not look at him.",
                "problem": "p",
                "rewrite_directive": "d",
            }],
        })
        captured: List[Dict[str, Any]] = []
        _set_chat_response(orch, captured, [critique_payload, rewritten])
        out, info = asyncio.run(run_sniff_test_and_rewrite(orch, text, 1))
        assert info["critique"]["skipped"] is False
        assert info["rewrite"]["applied"] is True
        assert "Ruth waited on the porch" in out
        # Both calls used editor tier.
        assert all(c["model"] == "gpt-5.5" for c in captured)
        assert len(captured) == 2

    def test_disabled_short_circuits_at_wrapper(self, monkeypatch):
        monkeypatch.setenv("ENABLE_SNIFF_TEST", "false")
        orch = _make_orchestrator(monkeypatch)
        captured: List[Dict[str, Any]] = []
        _set_chat_response(orch, captured, ["{}"])
        text = _make_chapter()
        out, info = asyncio.run(run_sniff_test_and_rewrite(orch, text, 1))
        assert out == text
        assert info["critique"]["skipped"] is True
        assert info["critique"]["reason"] == "disabled_by_env"
        assert info["rewrite"]["applied"] is False
        assert len(captured) == 0


# ──────────────────────────────────────────────────────────────────────────
# 5. Intra-chapter tic detector (P2.4 follow-up)
# ──────────────────────────────────────────────────────────────────────────


def _ticky_chapter() -> str:
    """A chapter that intentionally trips the tic detector with two distinct
    3-word phrases ('let the silence' and 'wanted to ask') appearing 3× each.
    Surrounded by enough varied filler to clear the word-count floor."""
    body = (
        "Ruth took a long breath and let the silence carry the room.\n\n"
        "Mitch waited near the door. He wanted to ask what had happened.\n\n"
        "Outside, a magpie cracked something against the gravel and flapped away.\n\n"
        "She watched the curtain move and let the silence stretch a little longer.\n\n"
        "He wanted to ask about the dog, but the question felt small.\n\n"
        "The kettle ticked on the burner; she did not look at it.\n\n"
        "Cottonwood seed drifted across the porch in long, lazy curls.\n\n"
        "Ruth let the silence be the only answer she had to offer.\n\n"
        "Mitch wanted to ask one more thing and didn't.\n\n"
        "Far off, a tractor coughed twice and settled into a steady rasp.\n\n"
    )
    while len(body.split()) < MIN_WORDS_FOR_SNIFF_TEST + 50:
        body += "Sunlight pooled at the screen door, sliced thin by the spring's hinges.\n\n"
    return body


class TestIntraChapterTicDetector:
    def test_extracts_repeating_three_word_phrase(self):
        tics = _extract_intra_chapter_tics(_ticky_chapter())
        phrases = {t["phrase"] for t in tics}
        # Both intentional tics must surface.
        assert "let the silence" in phrases
        assert "wanted to ask" in phrases

    def test_ignores_pure_stopword_phrases(self):
        chapter = (
            "Ruth and the way she walked. The way she walked again. "
            "Mitch and the way she walked. " * 30
        )
        # "and the way" is mostly stopwords + 'way' as the single content
        # word — the detector requires ≥ 2 content words, so it must skip.
        tics = _extract_intra_chapter_tics(chapter)
        assert all("and the way" != t["phrase"] for t in tics)

    def test_ignores_dialogue_scaffolding(self):
        chapter = (
            "He said one thing. She said the other. He said it again. "
            "She said no. He said yes. She said maybe. " * 20
        )
        # "he said" / "she said" / "she said the" etc. are scaffolding —
        # the 2-content-word filter drops "X said".
        tics = _extract_intra_chapter_tics(chapter)
        for t in tics:
            tokens = t["tokens"]
            # If two-content-word phrase ends in 'said', we must have rejected it.
            content = [tok for tok in tokens if tok not in sniff_mod._TIC_STOPWORDS]
            if len(content) == 2:
                assert content[1] not in {"said", "asked", "answered", "replied"}

    def test_respects_character_name_allowlist(self):
        # "Nero kept his" reads like a tic but is a legitimate recurring
        # reference to the POV character; the allowlist must suppress it.
        chapter = (
            "Nero kept his eyes on the panel.\n\n"
            "Nero kept his hand near the radio.\n\n"
            "Nero kept his back to the door.\n\n"
            "Nero kept his answer brief.\n\n"
        ) + ("Sunlight moved across the floor in small even squares.\n\n" * 30)
        tics = _extract_intra_chapter_tics(chapter, char_name_allowlist=["Nero"])
        for t in tics:
            assert "nero" not in t["tokens"]

    def test_build_tic_rewrites_caps_at_max(self):
        rewrites = build_tic_rewrites(_ticky_chapter(), max_tic_rewrites=MAX_TIC_REWRITES)
        assert len(rewrites) <= MAX_TIC_REWRITES
        assert len(rewrites) >= 1
        for r in rewrites:
            assert r["paragraph_quote"]
            assert r["rewrite_directive"]
            # Directive must name the offending phrase explicitly.
            assert "\"" in r["rewrite_directive"]

    def test_build_tic_rewrites_returns_empty_for_clean_text(self):
        # Each filler line is unique; no 3-word phrase repeats.
        clean = "\n\n".join(_FILLER_LINES)
        assert build_tic_rewrites(clean) == []

    def test_critique_appends_tic_rewrites_under_cap(self, monkeypatch):
        monkeypatch.setenv("ENABLE_SNIFF_TEST", "true")
        orch = _make_orchestrator(monkeypatch)
        # Critic returns no rewrites — tic detector should still add some.
        payload = json.dumps({"critique_summary": "x", "targeted_rewrites": []})
        _set_chat_response(orch, [], [payload])
        result = asyncio.run(run_sniff_test(orch, _ticky_chapter(), 1))
        assert result["skipped"] is False
        assert result["tic_rewrites_added"] >= 1
        assert len(result["targeted_rewrites"]) == result["tic_rewrites_added"]
        # Each must be a valid rewrite payload.
        for r in result["targeted_rewrites"]:
            assert r["paragraph_quote"]
            assert r["rewrite_directive"]

    def test_banned_phrase_rewrite_fires_for_single_occurrence(self):
        """Cross-chapter catchphrase guard: even ONE occurrence of a phrase
        on the banned list forces a rewrite. This catches the literary-
        cycle1 defect where 'Well, now' leaked into 5/5 chapters despite
        being on the avoid list since chapter 3."""
        chapter = (
            "Mitch tipped his cap. \u201cWell, now,\u201d he said, "
            "\u201cdidn't expect to find you here at this hour.\u201d\n\n"
            "Ruth waited. She did not answer right away.\n\n"
        ) + ("\n\n".join(_FILLER_LINES))
        rewrites = build_banned_phrase_rewrites(
            chapter_text=chapter,
            banned_phrases=["well now"],
            max_rewrites=2,
        )
        assert len(rewrites) == 1
        r = rewrites[0]
        assert "Well, now" in r["paragraph_quote"]
        assert "well now" in r["rewrite_directive"].lower()
        assert "MUST not appear" in r["rewrite_directive"]

    def test_banned_phrase_rewrite_returns_empty_when_phrase_absent(self):
        chapter = "\n\n".join(_FILLER_LINES)
        assert build_banned_phrase_rewrites(
            chapter_text=chapter,
            banned_phrases=["well now", "wanted to ask"],
        ) == []

    def test_banned_phrase_rewrite_caps_at_max(self):
        chapter = (
            "He said, \u201cwell now indeed.\u201d\n\n"
            "She said, \u201cwell now what?\u201d\n\n"
            "They wanted to ask the question, but didn't.\n\n"
            "She wanted to ask why, then thought better.\n\n"
            "Let the silence speak for them. He would let the silence settle.\n\n"
        ) + ("\n\n".join(_FILLER_LINES))
        rewrites = build_banned_phrase_rewrites(
            chapter_text=chapter,
            banned_phrases=["well now", "wanted to ask", "let the silence"],
            max_rewrites=2,
        )
        assert len(rewrites) == 2

    def test_run_sniff_test_appends_banned_phrase_rewrites(self, monkeypatch):
        monkeypatch.setenv("ENABLE_SNIFF_TEST", "true")
        orch = _make_orchestrator(monkeypatch)
        chapter = (
            "Mitch tipped his cap. \u201cWell, now,\u201d he said, "
            "\u201cdidn't expect to find you here at this hour.\u201d\n\n"
            "Ruth waited. She did not answer right away.\n\n"
        ) + ("\n\n".join(_FILLER_LINES))
        payload = json.dumps({"critique_summary": "x", "targeted_rewrites": []})
        _set_chat_response(orch, [], [payload])
        result = asyncio.run(run_sniff_test(
            orch,
            chapter,
            1,
            banned_phrases=["well now"],
        ))
        assert result["skipped"] is False
        assert result["banned_phrase_rewrites_added"] == 1
        # The banned-phrase entry must be present.
        assert any(
            "Well, now" in r.get("paragraph_quote", "")
            for r in result["targeted_rewrites"]
        )

    def test_critique_dedupes_against_llm_paragraph_choices(self, monkeypatch):
        """If the LLM critic already picked a paragraph, the tic detector
        must NOT queue a second rewrite against the same paragraph."""
        monkeypatch.setenv("ENABLE_SNIFF_TEST", "true")
        orch = _make_orchestrator(monkeypatch)
        chapter = _ticky_chapter()
        # Pick the first 'let the silence' paragraph as the LLM's quote.
        target_para = next(
            p for p in chapter.split("\n\n")
            if "let the silence carry the room" in p
        )
        payload = json.dumps({
            "critique_summary": "x",
            "targeted_rewrites": [{
                "paragraph_quote": target_para,
                "problem": "anything",
                "rewrite_directive": "anything",
            }],
        })
        _set_chat_response(orch, [], [payload])
        result = asyncio.run(run_sniff_test(orch, chapter, 1))
        # Count distinct paragraph_quote prefixes — no duplicates allowed.
        prefixes = [r["paragraph_quote"][:80] for r in result["targeted_rewrites"]]
        assert len(prefixes) == len(set(prefixes))
