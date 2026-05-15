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

# How many tic-driven rewrites we'll inject into the editor's targeted
# rewrites list. The total still respects MAX_REWRITES_PER_CHAPTER.
MAX_TIC_REWRITES = 3


def is_sniff_test_enabled() -> bool:
    """Honor ENABLE_SNIFF_TEST env var (default true)."""
    return os.getenv("ENABLE_SNIFF_TEST", "true").strip().lower() not in {"false", "0", "no"}


# ─── Intra-chapter tic detector ─────────────────────────────────────────────

# Stopwords used to filter phrase candidates. A 3-word phrase made entirely
# of stopwords is noise (e.g., "and the way", "in the next"). We require at
# least one content word.
_TIC_STOPWORDS = {
    "the", "a", "an", "and", "but", "or", "if", "so", "yet", "for", "nor",
    "to", "of", "in", "on", "at", "by", "from", "with", "as", "into", "onto",
    "is", "was", "were", "are", "be", "been", "being", "had", "has", "have",
    "do", "does", "did", "doing", "done", "would", "could", "should", "may",
    "might", "must", "can", "shall", "will", "ought",
    "i", "me", "my", "mine", "we", "us", "our", "ours",
    "you", "your", "yours", "he", "him", "his", "she", "her", "hers",
    "it", "its", "they", "them", "their", "theirs", "this", "that",
    "these", "those", "there", "here",
    "not", "no", "yes", "very", "just", "only", "also", "too",
    "then", "than", "though", "while", "when", "where", "why", "how",
    "what", "which", "who", "whom", "whose",
    "one", "two", "three", "four", "five", "first", "last", "next",
}


def _is_meaningful_tic_phrase(tokens: List[str]) -> bool:
    """A phrase qualifies as a possible tic only if it has ≥ 2 content words
    AND isn't pure dialogue scaffolding ('he said', 'she said' is too noisy)."""
    if not tokens:
        return False
    content = [t for t in tokens if t not in _TIC_STOPWORDS]
    if len(content) < 2:
        return False
    # Pure dialogue scaffolding pattern: "he said" / "she said" / "X said Y".
    if len(content) == 2 and content[1] in {"said", "asked", "answered", "replied"}:
        return False
    return True


def _extract_intra_chapter_tics(
    chapter_text: str,
    min_phrase_len: int = 3,
    max_phrase_len: int = 5,
    min_count: int = 2,
    char_name_allowlist: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Find phrases that appear ≥ min_count times within a single chapter.

    Returns a list of dicts sorted by descending count, then descending phrase
    length:
        [{"phrase": "let the silence", "count": 3, "tokens": [...]}, ...]

    A phrase qualifies as a tic only if it:
      - has ≥ 2 content (non-stopword) words
      - does not consist entirely of dialogue scaffolding ("he said")
      - does not contain a known character name from char_name_allowlist
        (recurring character references are legitimate, not tics)

    The detector is intentionally conservative — false positives here force
    rewrites the model has to do, which is expensive and can hurt good prose.
    """
    if not chapter_text:
        return []

    # Lowercase and strip non-letters; keep apostrophes inside words by
    # converting them to a single character then stripping.
    normalized = re.sub(r"[\u2018\u2019']", "", chapter_text.lower())
    words = re.findall(r"[a-z]+", normalized)
    if len(words) < 200:
        return []

    name_set = {n.lower() for n in (char_name_allowlist or []) if isinstance(n, str)}

    counts: Dict[str, int] = {}
    for n in range(min_phrase_len, max_phrase_len + 1):
        for i in range(len(words) - n + 1):
            tokens = words[i:i + n]
            if not _is_meaningful_tic_phrase(tokens):
                continue
            if name_set and any(t in name_set for t in tokens):
                continue
            phrase = " ".join(tokens)
            counts[phrase] = counts.get(phrase, 0) + 1

    results: List[Dict[str, Any]] = []
    for phrase, count in counts.items():
        if count < min_count:
            continue
        results.append({
            "phrase": phrase,
            "count": count,
            "tokens": phrase.split(),
        })
    # Sort: highest count first; tie-break on longer phrases (more specific).
    results.sort(key=lambda d: (-d["count"], -len(d["tokens"])))
    return results


def _normalize_for_phrase_match(text: str) -> str:
    """Lowercase, strip apostrophes and punctuation, collapse all whitespace.

    Used to compare a phrase like 'well now' against a paragraph like
    `\u201cWell, now,\u201d he said` — without this, the comma or curly
    quote breaks the substring match.
    """
    text = re.sub(r"[\u2018\u2019']", "", text.lower())
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _find_paragraph_containing(chapter_text: str, phrase: str) -> Optional[str]:
    """Return the first paragraph that contains the phrase (case-insensitive,
    punctuation-and-whitespace-insensitive). None if not found."""
    if not chapter_text or not phrase:
        return None
    paragraphs = [p for p in chapter_text.split("\n\n") if p.strip()]
    needle = _normalize_for_phrase_match(phrase)
    if not needle:
        return None
    for p in paragraphs:
        flat = _normalize_for_phrase_match(p)
        if needle in flat:
            return p
    return None


def build_tic_rewrites(
    chapter_text: str,
    max_tic_rewrites: int = MAX_TIC_REWRITES,
    char_name_allowlist: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """Convert detected intra-chapter tics into targeted_rewrite entries.

    Each entry rewrites the FIRST paragraph containing the tic and instructs
    the editor to break the pattern across the whole chapter. Capped at
    max_tic_rewrites so we don't crowd out the LLM critic's own rewrites.
    """
    tics = _extract_intra_chapter_tics(
        chapter_text=chapter_text,
        char_name_allowlist=char_name_allowlist,
    )
    if not tics:
        return []

    rewrites: List[Dict[str, str]] = []
    seen_paragraphs: set[str] = set()
    for tic in tics:
        if len(rewrites) >= max_tic_rewrites:
            break
        phrase = tic["phrase"]
        count = tic["count"]
        para = _find_paragraph_containing(chapter_text, phrase)
        if not para:
            continue
        # Don't queue two tic-rewrites against the same paragraph.
        para_key = para[:80]
        if para_key in seen_paragraphs:
            continue
        seen_paragraphs.add(para_key)
        rewrites.append({
            "paragraph_quote": para,
            "problem": (
                f"intra-chapter phrase tic: \"{phrase}\" appears {count} "
                f"times in this chapter, becoming a verbal habit rather than "
                f"a deliberate refrain."
            ),
            "rewrite_directive": (
                f"Rewrite this paragraph so it does NOT contain the phrase "
                f"\"{phrase}\". Then, in your rewrite, break the same pattern "
                f"across the rest of the chapter by varying the rendering: "
                f"different verb, different sensory anchor, or restructure "
                f"the action so the phrase isn't reachable. The phrase should "
                f"appear at most ONCE in the final chapter."
            ),
        })
    return rewrites


def build_banned_phrase_rewrites(
    chapter_text: str,
    banned_phrases: List[str],
    max_rewrites: int = 2,
) -> List[Dict[str, str]]:
    """Force a rewrite for any phrase already on the cross-chapter banned
    list that still appears in the current chapter — even ONCE.

    This is the catchphrase-leak guard. The drafter and stitch passes are
    told these phrases are banned, but the model sometimes lands on them
    anyway (literary-cycle1: "Well, now" leaked into 5/5 chapters). The
    sniff-test pass is the last gate; if a banned phrase survives to here,
    rewrite the first occurrence and instruct the editor to remove the rest.

    `banned_phrases` is a list of normalized lowercase phrases (typically
    coming from cross-chapter overused_phrases entries with chapter_count
    >= 2 — phrases that have ALREADY become recurring habits).
    """
    if not chapter_text or not banned_phrases:
        return []
    rewrites: List[Dict[str, str]] = []
    seen_paragraphs: set[str] = set()
    flat_chapter = _normalize_for_phrase_match(chapter_text)
    for phrase in banned_phrases:
        if len(rewrites) >= max_rewrites:
            break
        if not phrase:
            continue
        needle = _normalize_for_phrase_match(phrase)
        if not needle or needle not in flat_chapter:
            continue
        para = _find_paragraph_containing(chapter_text, needle)
        if not para:
            continue
        para_key = para[:80]
        if para_key in seen_paragraphs:
            continue
        seen_paragraphs.add(para_key)
        rewrites.append({
            "paragraph_quote": para,
            "problem": (
                f"cross-chapter catchphrase leak: \"{phrase}\" is on the "
                f"banned list (it became a recurring habit across prior "
                f"chapters) but appears here anyway."
            ),
            "rewrite_directive": (
                f"Rewrite this paragraph so it does NOT contain the phrase "
                f"\"{phrase}\". If a character is using it as a verbal tic, "
                f"replace with silence, action, or a different turn of "
                f"phrase. Then, scan the rest of the chapter and remove "
                f"any other occurrence of \"{phrase}\" the same way. The "
                f"phrase MUST not appear in the final chapter at all."
            ),
        })
    return rewrites


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
    char_name_allowlist: Optional[List[str]] = None,
    banned_phrases: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Run the bounded literary critique. Returns a dict with the critique
    and a targeted_rewrites list (possibly empty).

    On any failure (env disabled, short chapter, LLM error, parse error)
    returns ``{"skipped": True, "reason": "<why>"}`` — the caller treats
    this as a no-op.

    The targeted_rewrites list is the union of:
      - The LLM critic's own rewrite suggestions (capped)
      - Cross-chapter banned-phrase rewrites (any phrase from banned_phrases
        that still appears in this chapter, capped at 2)
      - Deterministic intra-chapter tic rewrites (capped at MAX_TIC_REWRITES)
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
            max_tokens=12000,
            response_format={"type": "json_object"},
            model_role="editor",
            reasoning_effort="low",
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
        log.warning(
            f"Chapter {chapter_number}: sniff-test critique returned EMPTY content — "
            "no rewrites will be applied. Likely cause: reasoning model consumed entire "
            "token budget on internal reasoning."
        )
        return {"skipped": True, "reason": "empty_response"}

    try:
        parsed = json.loads(content)
    except Exception as e:
        snippet = (content or "")[:300].replace("\n", " ")
        log.warning(
            f"Chapter {chapter_number}: sniff-test JSON parse failed ({type(e).__name__}: {e}). "
            f"Snippet: {snippet!r}"
        )
        return {"skipped": True, "reason": "json_parse_error"}

    if not isinstance(parsed, dict):
        log.warning(
            f"Chapter {chapter_number}: sniff-test critique returned JSON of type "
            f"{type(parsed).__name__} (expected object). Skipping."
        )
        return {"skipped": True, "reason": "json_not_object"}

    # Normalize and cap LLM-critic rewrites.
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
            # Reserve room for tic rewrites — leave at least MAX_TIC_REWRITES
            # slots so the deterministic detector always has space to act.
            if len(rewrites) >= MAX_REWRITES_PER_CHAPTER - MAX_TIC_REWRITES:
                break

    # FIRST priority for deterministic add-ons: cross-chapter banned-phrase
    # rewrites. If a phrase like "Well, now" was already on the cross-chapter
    # avoid list, the model was supposed to drop it; if it survived to here,
    # we force the editor to remove it before the chapter ships.
    banned_rewrites: List[Dict[str, str]] = []
    if banned_phrases:
        try:
            banned_rewrites = build_banned_phrase_rewrites(
                chapter_text=chapter_text,
                banned_phrases=banned_phrases,
                max_rewrites=2,
            )
        except Exception as e:
            log.warning(
                f"Chapter {chapter_number}: banned-phrase detector failed "
                f"(non-fatal): {e}"
            )
    existing_para_keys = {r.get("paragraph_quote", "")[:80] for r in rewrites}
    for br in banned_rewrites:
        if len(rewrites) >= MAX_REWRITES_PER_CHAPTER:
            break
        para_key = br.get("paragraph_quote", "")[:80]
        if para_key in existing_para_keys:
            continue
        rewrites.append(br)
        existing_para_keys.add(para_key)

    # Then deterministic intra-chapter tic rewrites. These catch phrases
    # like "let the silence" / "wanted to ask" appearing 2-3× per chapter
    # that the LLM critic often misses (they look like author voice if you
    # only read the chapter once).
    tic_rewrites: List[Dict[str, str]] = []
    try:
        tic_rewrites = build_tic_rewrites(
            chapter_text=chapter_text,
            max_tic_rewrites=MAX_TIC_REWRITES,
            char_name_allowlist=char_name_allowlist,
        )
    except Exception as e:
        log.warning(f"Chapter {chapter_number}: tic detector failed (non-fatal): {e}")

    for tic_r in tic_rewrites:
        if len(rewrites) >= MAX_REWRITES_PER_CHAPTER:
            break
        para_key = tic_r.get("paragraph_quote", "")[:80]
        if para_key in existing_para_keys:
            continue
        rewrites.append(tic_r)
        existing_para_keys.add(para_key)

    return {
        "skipped": False,
        "critique_summary": (parsed.get("critique_summary") or "").strip(),
        "strongest_paragraph": (parsed.get("strongest_paragraph") or "").strip(),
        "unearned_beat": (parsed.get("unearned_beat") or "").strip(),
        "targeted_rewrites": rewrites,
        "tic_rewrites_added": len(tic_rewrites),
        "banned_phrase_rewrites_added": len(banned_rewrites),
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


def _rewrite_preserves_quote_balance(original: str, rewritten: str) -> bool:
    """Reject rewrites that introduce a quote imbalance the original didn't
    have. Covers straight (`"`) and curly (`\u201c`/`\u201d`) pairs.

    Real defect: thriller-round-2 ch3 line 143 lost a curly quote and the
    paragraph rendered as a sentence-fragment merged into the next speaker
    attribution.
    """
    s_in_unpaired = original.count('"') % 2
    s_out_unpaired = rewritten.count('"') % 2
    if s_in_unpaired == 0 and s_out_unpaired == 1:
        return False
    co_in = original.count("\u201c")
    cc_in = original.count("\u201d")
    co_out = rewritten.count("\u201c")
    cc_out = rewritten.count("\u201d")
    in_delta = co_in - cc_in
    out_delta = co_out - cc_out
    if abs(out_delta) > abs(in_delta):
        return False
    return True


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
            reasoning_effort="low",
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
        log.warning(
            f"Chapter {chapter_number}: targeted-rewrite returned EMPTY content "
            f"({len(matched)} matched paragraphs were skipped). Likely cause: "
            "reasoning model consumed entire token budget on internal reasoning."
        )
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

    # Quote-balance guard. Reject rewrites that introduce a quote imbalance
    # the input didn't have — straight OR curly. Real defect: thriller
    # round-2 ch3 line 143 lost a curly quote boundary mid-paragraph.
    try:
        if not _rewrite_preserves_quote_balance(chapter_text, new_text):
            log.warning(
                f"Chapter {chapter_number}: targeted-rewrite produced "
                f"unbalanced quotes; discarding."
            )
            info["skipped_reason"] = "quote_imbalance"
            return chapter_text, info
    except Exception:
        pass

    info["applied"] = True
    return new_text, info


# ─── Convenience: critique + rewrite in one call ────────────────────────────


async def run_sniff_test_and_rewrite(
    orchestrator,
    chapter_text: str,
    chapter_number: int,
    book_bible_excerpt: str = "",
    char_name_allowlist: Optional[List[str]] = None,
    banned_phrases: Optional[List[str]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """End-to-end helper: critique + targeted rewrite. Caller integrates this
    after deterministic cleanup. Returns ``(final_text, debug_info)``.

    char_name_allowlist is forwarded to the intra-chapter tic detector so
    that phrases containing a recurring character name aren't flagged.

    banned_phrases is forwarded to the cross-chapter catchphrase guard;
    any phrase from this list that still appears in the current chapter
    forces a targeted rewrite (catches drafter/stitch failures to honor
    the avoid_phrases instruction).
    """
    critique = await run_sniff_test(
        orchestrator=orchestrator,
        chapter_text=chapter_text,
        chapter_number=chapter_number,
        book_bible_excerpt=book_bible_excerpt,
        char_name_allowlist=char_name_allowlist,
        banned_phrases=banned_phrases,
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
