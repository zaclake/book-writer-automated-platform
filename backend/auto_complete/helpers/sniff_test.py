#!/usr/bin/env python3
"""Path A+ P2.4 — Bounded literary sniff-test pass.

After a chapter is drafted and stitched, this module runs ONE editor-tier
critique call (no rubric, no scoring) and then ONE targeted-rewrite pass that
addresses ONLY the flagged paragraphs (capped at 5). This is the anti-rubric-
gaming check — it catches the AI-isms a numeric scorecard won't, without
opening an iterative editorial loop.

Design notes:
- Two LLM calls per chapter, both routed through the editor tier. Drafter
  tier is intentionally not used here because the whole point is a stronger
  reader-of-prose model.
- The rewrite call processes flagged paragraphs in a single call to limit
  cost and preserve cross-paragraph coherence. The model is told to leave
  every other paragraph untouched.
- If anything fails (parse error, LLM error, no flagged paragraphs, paragraph
  not found in chapter text) the function returns the original chapter
  unchanged. Sniff test is opt-out, never destructive.
- Gated by env var ENABLE_SNIFF_TEST (default true). Set to "false" to bypass
  in test/dev runs that should be cheap and deterministic.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple


log = logging.getLogger(__name__)


# ─── Configuration ──────────────────────────────────────────────────────────

# Hard cap on rewrites per chapter. Higher than this and we're back to a
# whole-chapter editorial loop — which the plan explicitly rejects.
MAX_REWRITES_PER_CHAPTER = 5

# Word-count floor below which the sniff test is skipped — short chapters
# don't have enough surface area for the critique to be useful.
MIN_WORDS_FOR_SNIFF_TEST = 600


def is_sniff_test_enabled() -> bool:
    """Honor ENABLE_SNIFF_TEST env var (default true)."""
    return os.getenv("ENABLE_SNIFF_TEST", "true").strip().lower() not in {"false", "0", "no"}


# ─── Step 1: Run the critique ───────────────────────────────────────────────

_CRITIQUE_SYSTEM = (
    "You are a senior literary editor reading a draft chapter. Do NOT score "
    "categories. Do NOT give a numeric rating. Do NOT praise to soften the "
    "critique. You are looking for AI-prose tells and unearned emotional "
    "beats — the things rubric scoring misses.\n\n"
    "Output STRICT JSON only. No commentary, no code fences."
)


def _build_critique_user_prompt(
    chapter_text: str,
    chapter_number: int,
    book_bible_excerpt: str = "",
) -> str:
    bible_block = (
        f"\nBOOK CONTEXT (excerpt — use only for understanding tone/register):\n"
        f"{book_bible_excerpt[:1500]}\n"
    ) if book_bible_excerpt else ""

    # The chapter is included in full; if the model truncates we'll see it in
    # the rewrite step and skip. We don't pre-truncate here because the editor
    # tier model has plenty of context.
    return (
        f"Read this draft of Chapter {chapter_number} as a senior literary "
        f"editor. Don't score, don't praise to soften. In ≤ 200 words, name:\n"
        f"  - The 3 things that most make this read like AI prose.\n"
        f"  - The 1 emotional beat that is unearned or saccharine.\n"
        f"  - The 1 sentence/paragraph that is the strongest.\n\n"
        f"Then output a list of targeted_rewrites. Each entry MUST quote the "
        f"problem paragraph EXACTLY (so we can find it). Be ruthless: only "
        f"flag what genuinely needs fixing. Cap your list at "
        f"{MAX_REWRITES_PER_CHAPTER} paragraphs. If the chapter is already "
        f"strong, return an empty list.\n\n"
        f"Return JSON in this shape (no other top-level keys):\n"
        '{\n'
        '  "critique_summary": "≤ 200 words of plain-English critique. No bullet headers, no hedging.",\n'
        '  "strongest_paragraph": "the quoted strongest paragraph",\n'
        '  "unearned_beat": "the quoted or paraphrased unearned beat",\n'
        '  "targeted_rewrites": [\n'
        '    {\n'
        '      "paragraph_quote": "the EXACT paragraph from the chapter, character-for-character",\n'
        '      "problem": "1-2 sentences naming the AI-prose tell or unearned beat",\n'
        '      "rewrite_directive": "1-3 sentences of concrete craft direction for the rewrite — what to do, not just what to avoid"\n'
        '    }\n'
        '  ]\n'
        '}\n'
        f"{bible_block}\n"
        f"CHAPTER TEXT:\n{chapter_text}\n"
    )


async def run_sniff_test(
    orchestrator,
    chapter_text: str,
    chapter_number: int,
    book_bible_excerpt: str = "",
) -> Dict[str, Any]:
    """Run the bounded literary critique. Returns a dict with the critique
    and a targeted_rewrites list (possibly empty).

    On any failure (env disabled, short chapter, LLM error, parse error)
    returns ``{"skipped": True, "reason": "<why>"}`` — the caller treats
    this as a no-op.
    """
    if not is_sniff_test_enabled():
        return {"skipped": True, "reason": "disabled_by_env"}

    if not chapter_text or len(chapter_text.split()) < MIN_WORDS_FOR_SNIFF_TEST:
        return {"skipped": True, "reason": "chapter_too_short"}

    user_prompt = _build_critique_user_prompt(
        chapter_text=chapter_text,
        chapter_number=chapter_number,
        book_bible_excerpt=book_bible_excerpt,
    )

    try:
        response = await orchestrator._make_api_call(
            messages=[
                {"role": "system", "content": _CRITIQUE_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.5,
            max_tokens=4000,
            response_format={"type": "json_object"},
            model_role="editor",
        )
    except Exception as e:
        log.warning(f"Chapter {chapter_number}: sniff-test critique LLM call failed: {e}")
        return {"skipped": True, "reason": f"llm_error:{type(e).__name__}"}

    content = ""
    if hasattr(response, "output_text"):
        content = response.output_text
    elif response and hasattr(response, "choices") and response.choices:
        content = response.choices[0].message.content
    if not content:
        return {"skipped": True, "reason": "empty_response"}

    try:
        parsed = json.loads(content)
    except Exception as e:
        log.warning(f"Chapter {chapter_number}: sniff-test JSON parse failed: {e}")
        return {"skipped": True, "reason": "json_parse_error"}

    if not isinstance(parsed, dict):
        return {"skipped": True, "reason": "json_not_object"}

    # Normalize and cap.
    rewrites_raw = parsed.get("targeted_rewrites", [])
    rewrites: List[Dict[str, str]] = []
    if isinstance(rewrites_raw, list):
        for item in rewrites_raw:
            if not isinstance(item, dict):
                continue
            quote = (item.get("paragraph_quote") or "").strip()
            problem = (item.get("problem") or "").strip()
            directive = (item.get("rewrite_directive") or "").strip()
            if not quote or not directive:
                continue
            rewrites.append({
                "paragraph_quote": quote,
                "problem": problem,
                "rewrite_directive": directive,
            })
            if len(rewrites) >= MAX_REWRITES_PER_CHAPTER:
                break

    return {
        "skipped": False,
        "critique_summary": (parsed.get("critique_summary") or "").strip(),
        "strongest_paragraph": (parsed.get("strongest_paragraph") or "").strip(),
        "unearned_beat": (parsed.get("unearned_beat") or "").strip(),
        "targeted_rewrites": rewrites,
    }


# ─── Step 2: Apply the rewrites ─────────────────────────────────────────────

_REWRITE_SYSTEM = (
    "You are a senior literary editor performing TARGETED rewrites on a draft "
    "chapter. You are given the full chapter and a list of paragraphs that "
    "need fixing, each with a problem statement and a craft directive.\n\n"
    "RULES (every rule is hard):\n"
    "1. Rewrite ONLY the listed paragraphs. Every other paragraph in the "
    "chapter must be returned VERBATIM, character-for-character.\n"
    "2. A 'paragraph' is a block of text separated by a blank line. Replace "
    "the matching paragraph in place; do NOT add new paragraphs around it.\n"
    "3. Your rewrite must address the named problem AND follow the craft "
    "directive. Don't soften, don't add filler, don't introduce new plot.\n"
    "4. Preserve continuity: same characters, same scene state, same dialogue "
    "facts. You may change phrasing, sentence shape, gesture choices, "
    "interiority — not events.\n"
    "5. Do not add preamble, commentary, code fences, or markdown headers. "
    "Output ONLY the full revised chapter prose.\n"
)


def _normalize_for_match(text: str) -> str:
    """Whitespace-normalized form for fuzzy paragraph matching."""
    return re.sub(r"\s+", " ", text).strip()


def _find_paragraph_in_chapter(
    chapter_text: str,
    paragraph_quote: str,
) -> Optional[str]:
    """Return the actual chapter paragraph that matches ``paragraph_quote``.

    Tries (1) exact substring, (2) whitespace-normalized exact match against
    each split paragraph, (3) prefix match on the first ~80 chars of the
    quote (the model sometimes truncates with '...'). Returns None when
    nothing usable is found — caller skips the rewrite for that quote.
    """
    if not chapter_text or not paragraph_quote:
        return None

    paragraphs = [p for p in chapter_text.split("\n\n") if p.strip()]

    # 1. Direct substring match.
    if paragraph_quote in chapter_text:
        for p in paragraphs:
            if paragraph_quote in p:
                return p

    # 2. Normalized full-paragraph match.
    needle = _normalize_for_match(paragraph_quote)
    if not needle:
        return None
    for p in paragraphs:
        if _normalize_for_match(p) == needle:
            return p

    # 3. Prefix match on first 80 chars (handles '...' truncation in the quote).
    prefix = needle[:80]
    if len(prefix) >= 30:
        for p in paragraphs:
            if _normalize_for_match(p).startswith(prefix):
                return p

    return None


def _build_rewrite_user_prompt(
    chapter_text: str,
    matched_rewrites: List[Tuple[str, str, str]],
) -> str:
    """matched_rewrites is a list of (matched_paragraph, problem, directive)."""
    lines = [
        f"Apply the following {len(matched_rewrites)} targeted rewrites to the "
        f"draft chapter. Return the FULL revised chapter — every unflagged "
        f"paragraph must be returned verbatim.",
        "",
        "TARGETED REWRITES:",
    ]
    for i, (para, problem, directive) in enumerate(matched_rewrites, start=1):
        lines.append(f"\n--- Rewrite {i} ---")
        lines.append(f"PARAGRAPH (rewrite this in place):\n{para}")
        if problem:
            lines.append(f"\nPROBLEM: {problem}")
        lines.append(f"\nDIRECTIVE: {directive}")

    lines.append("\n" + ("=" * 50))
    lines.append("FULL CHAPTER (apply rewrites in place; everything else verbatim):")
    lines.append(chapter_text)
    return "\n".join(lines)


async def apply_targeted_rewrites(
    orchestrator,
    chapter_text: str,
    rewrites: List[Dict[str, str]],
    chapter_number: int,
) -> Tuple[str, Dict[str, Any]]:
    """Apply at most MAX_REWRITES_PER_CHAPTER targeted rewrites.

    Returns ``(possibly_rewritten_text, info_dict)``. ``info_dict`` includes
    the count of rewrites attempted, matched, and a list of rewrites that
    couldn't be matched against the chapter (so they can be logged but not
    silently lost).

    On any LLM failure or implausible output (e.g. shrunk to <50% of input),
    returns the original ``chapter_text``.
    """
    info: Dict[str, Any] = {
        "attempted": 0,
        "matched": 0,
        "unmatched_quotes": [],
        "applied": False,
        "skipped_reason": None,
    }

    if not rewrites:
        info["skipped_reason"] = "no_rewrites"
        return chapter_text, info

    if not chapter_text:
        info["skipped_reason"] = "empty_chapter"
        return chapter_text, info

    capped = rewrites[:MAX_REWRITES_PER_CHAPTER]
    info["attempted"] = len(capped)

    matched: List[Tuple[str, str, str]] = []
    for r in capped:
        quote = r.get("paragraph_quote", "")
        match = _find_paragraph_in_chapter(chapter_text, quote)
        if not match:
            info["unmatched_quotes"].append(quote[:100])
            continue
        matched.append((match, r.get("problem", ""), r.get("rewrite_directive", "")))

    info["matched"] = len(matched)

    if not matched:
        info["skipped_reason"] = "no_matched_paragraphs"
        return chapter_text, info

    user_prompt = _build_rewrite_user_prompt(chapter_text, matched)

    try:
        response = await orchestrator._make_api_call(
            messages=[
                {"role": "system", "content": _REWRITE_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.6,
            # Output is full chapter; size for the worst case.
            max_tokens=max(8000, len(chapter_text.split()) * 2),
            model_role="editor",
        )
    except Exception as e:
        log.warning(f"Chapter {chapter_number}: targeted-rewrite LLM call failed: {e}")
        info["skipped_reason"] = f"llm_error:{type(e).__name__}"
        return chapter_text, info

    new_text = ""
    if hasattr(response, "output_text"):
        new_text = response.output_text
    elif response and hasattr(response, "choices") and response.choices:
        new_text = response.choices[0].message.content
    if not new_text:
        info["skipped_reason"] = "empty_response"
        return chapter_text, info

    new_text = new_text.strip()

    # Sanity guard: if the rewrite shrunk the chapter dramatically, the model
    # ignored "return the full chapter" — keep the original.
    original_words = len(chapter_text.split())
    new_words = len(new_text.split())
    if original_words and new_words < int(original_words * 0.6):
        log.warning(
            f"Chapter {chapter_number}: targeted-rewrite output is only "
            f"{new_words} words (orig {original_words}); discarding rewrite."
        )
        info["skipped_reason"] = "rewrite_too_short"
        return chapter_text, info

    info["applied"] = True
    return new_text, info


# ─── Convenience: critique + rewrite in one call ────────────────────────────


async def run_sniff_test_and_rewrite(
    orchestrator,
    chapter_text: str,
    chapter_number: int,
    book_bible_excerpt: str = "",
) -> Tuple[str, Dict[str, Any]]:
    """End-to-end helper: critique + targeted rewrite. Caller integrates this
    after deterministic cleanup. Returns ``(final_text, debug_info)``.
    """
    critique = await run_sniff_test(
        orchestrator=orchestrator,
        chapter_text=chapter_text,
        chapter_number=chapter_number,
        book_bible_excerpt=book_bible_excerpt,
    )
    if critique.get("skipped"):
        return chapter_text, {"critique": critique, "rewrite": {"applied": False}}

    rewrites = critique.get("targeted_rewrites", []) or []
    if not rewrites:
        return chapter_text, {"critique": critique, "rewrite": {"applied": False, "skipped_reason": "no_rewrites"}}

    new_text, rewrite_info = await apply_targeted_rewrites(
        orchestrator=orchestrator,
        chapter_text=chapter_text,
        rewrites=rewrites,
        chapter_number=chapter_number,
    )
    return new_text, {"critique": critique, "rewrite": rewrite_info}
