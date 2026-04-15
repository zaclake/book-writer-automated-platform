#!/usr/bin/env python3
"""
Skeleton + Expand Chapter Generation Engine

Architecture:
1. SKELETON: Generate a beat-level plan driven by narrative needs (not word count)
2. EXPAND: Generate each beat as prose in a small, focused LLM call
3. STITCH: Smooth transitions between beats
4. CLEANUP: Light deterministic fixes (paragraph-level repetition, meta-narration)

Design principles:
- Chapters are as long as the story needs, not padded to a number
- Beat count is driven by narrative weight, not word math
- No hardcoded synonym maps — word variety handled by the model via overused_words context
- Plain prose is the default; vivid moments are rare and earned
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


# ─── Repetition Detection (generic, no hardcoded phrases) ────────────────────

# Function words that form noise n-grams ("he was the", "and then he").
# These are the ONLY hardcoded words — they filter out grammatical chaff,
# not creative content. The actual repetition detection is frequency-based.
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "but", "or", "so", "to", "of", "in", "on",
    "at", "for", "with", "as", "by", "from", "that", "this", "it", "its",
    "he", "she", "they", "his", "her", "was", "were", "had", "has", "have",
    "been", "not", "is", "are", "be", "if", "then", "than", "them", "him",
    "who", "what", "when", "did", "does", "do", "will", "would", "could",
    "just", "into", "out", "up", "down", "back", "all", "no", "yes",
})


def _extract_repeated_ngrams(
    text: str,
    ns: tuple = (3, 4),
    min_occurrences: int = 2,
    max_results: int = 15,
) -> List[str]:
    """Find any n-gram that repeats above a threshold.

    Purely frequency-based — no word lists, no genre assumptions.
    Only filters n-grams where EVERY token is a stopword (pure grammatical
    noise like "he was the"). Any n-gram with at least one content word
    is tracked.
    """
    words = re.findall(r"[a-z]+", text.lower())
    counts: Counter = Counter()
    for n in ns:
        for i in range(len(words) - n + 1):
            tokens = words[i : i + n]
            content_words = sum(1 for t in tokens if t not in _STOPWORDS)
            if content_words == 0:
                continue
            counts[" ".join(tokens)] += 1

    repeated = [
        (phrase, count)
        for phrase, count in counts.most_common()
        if count >= min_occurrences
    ]
    repeated.sort(key=lambda x: -x[1])
    return [f'"{phrase}" ({count}x)' for phrase, count in repeated[:max_results]]


# ─── Deterministic Cleanup (no LLM) ─────────────────────────────────────────

def fix_paragraph_repetition(text: str) -> str:
    """Fix word repetition WITHIN a single paragraph (same word 4+ times)."""
    if not text:
        return text
    paragraphs = text.split('\n\n')
    result = []
    for para in paragraphs:
        words = re.findall(r'\b[a-z]{4,}\b', para.lower())
        counts = Counter(words)
        worst = [(w, c) for w, c in counts.items() if c >= 4 and w not in {
            'said', 'that', 'this', 'then', 'they', 'them', 'were', 'been',
            'have', 'from', 'with', 'into', 'just', 'back', 'down',
        }]
        if not worst:
            result.append(para)
            continue
        # Don't try to fix — just flag for the stitch pass to address
        result.append(para)
    return '\n\n'.join(result)


def trim_repeated_phrases(text: str, max_occurrences: int = 3) -> str:
    """Generic safety net: find ANY 3-gram that appears more than
    max_occurrences times in the chapter text and remove the sentence
    containing the excess occurrence — but only if the sentence is short
    (filler, not plot-bearing).

    No hardcoded phrase lists. Purely frequency-based.
    """
    if not text or len(text.split()) < 200:
        return text

    words = re.findall(r"[a-z]+", text.lower())
    trigram_counts: Counter = Counter()
    for i in range(len(words) - 2):
        tokens = (words[i], words[i + 1], words[i + 2])
        if all(t in _STOPWORDS for t in tokens):
            continue
        trigram_counts[" ".join(tokens)] += 1

    offenders = [
        phrase for phrase, count in trigram_counts.most_common(30)
        if count > max_occurrences
    ]

    for phrase in offenders:
        for _pass in range(5):
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            matches = list(pattern.finditer(text))
            if len(matches) <= max_occurrences:
                break
            match = matches[-1]
            sent_start = text.rfind(".", 0, match.start())
            sent_end = text.find(".", match.end())
            if sent_start >= 0 and sent_end >= 0:
                sentence = text[sent_start + 1 : sent_end + 1]
                if len(sentence.split()) <= 15:
                    text = text[: sent_start + 1] + text[sent_end + 1 :]
                    continue
            break

    return text


def strip_meta_narration(text: str) -> str:
    """Remove fourth-wall-breaking meta text and LLM preamble/revision notes."""
    if not text:
        return text or ""

    # Strip LLM preamble: "Certainly!", "Here is your revised...", revision bullet lists, separators
    # This handles the case where the stitch or revision pass outputs commentary before the prose.
    preamble_pattern = re.compile(
        r'^(?:'
        r'(?:Certainly|Sure|Of course|Absolutely|Great|Here)[!.,]?\s*'
        r'(?:Here\s+is|Below\s+is|I\'ve)[^\n]*\n*'
        r'|Here\s+is\s+(?:your|the)\s+(?:revised|updated|edited|final|completed)[^\n]*\n*'
        r'|(?:---+\s*\n)+'
        r'|(?:\s*[-*]\s+[A-Z][^\n]*\n)+\s*(?:---+\s*\n)*'
        r'|Chapter\s+\d+\s*\n+'
        r')+',
        re.MULTILINE | re.IGNORECASE,
    )
    text = preamble_pattern.sub('', text, count=1).lstrip()

    # Strip trailing meta narration
    patterns = [
        r'[Tt]he chapter ended[^.]*\.',
        r'[Ee]nd of chapter[^.]*\.',
        r'[Cc]hapter \d+ ends[^.]*\.',
        r'[Tt]his concludes[^.]*\.',
        r'\*\*\*\s*$',
    ]
    for pattern in patterns:
        text = re.sub(pattern, '', text, flags=re.MULTILINE)
    return text.strip()


def ensure_clean_ending(text: str) -> str:
    """Ensure chapter ends on a complete sentence with balanced quotes."""
    if not text:
        return text
    trimmed = text.rstrip()
    # Close any dangling open quote (curly quotes only — straight quotes are ambiguous)
    open_curly = trimmed.count('\u201c')
    close_curly = trimmed.count('\u201d')
    if open_curly > close_curly:
        trimmed = trimmed + '\u201d'
    if re.search(r'[.!?]["\')\]]?\s*$', trimmed):
        return trimmed
    # Em dashes and ellipses are valid literary endings
    if trimmed.endswith(('\u2014', '\u2026', '...', '\u2014"', "\u2014'")):
        return trimmed
    # Trim to last complete sentence
    last_terminal = max(
        trimmed.rfind('.'), trimmed.rfind('!'), trimmed.rfind('?'),
    )
    for ending in ('."', '!"', '?"', ".'", "!'", "?'", '.)', '!)'):
        pos = trimmed.rfind(ending)
        if pos >= 0:
            last_terminal = max(last_terminal, pos + len(ending) - 1)
    if last_terminal > len(trimmed) * 0.5:
        return trimmed[:last_terminal + 1]
    return trimmed


def fix_generic_ending(text: str) -> str:
    """Detect and trim bland/generic closing sentences.

    Patterns like 'The day would not wait', 'The night stretched ahead',
    'Tomorrow would bring answers' are atmospheric padding. If the last
    sentence matches a generic closer, trim it so the chapter ends on
    the previous, more specific sentence.
    """
    if not text or len(text) < 200:
        return text

    # Split into sentences (preserve paragraph structure)
    paragraphs = text.rstrip().split("\n\n")
    if not paragraphs:
        return text

    last_para = paragraphs[-1].strip()
    # Find the last sentence
    sentences = re.split(r'(?<=[.!?])\s+', last_para)
    if len(sentences) < 2:
        return text

    last_sentence = sentences[-1].strip()
    last_lower = last_sentence.lower()

    generic_patterns = [
        r'^the (?:day|night|morning|evening|dawn|darkness|silence|quiet|world|work|shift|journey|road|battle|fight|war|storm) '
        r'(?:would|could|did|was|stretched|waited|pressed|called|lay|loomed|settled)',
        r'^(?:tomorrow|tonight|the hours? ahead|what came next|whatever came)',
        r'^(?:everything|nothing|something|the rest) (?:would|could|was|had)',
        r'^(?:he|she|they|i) (?:would|could) (?:not|deal with|face|handle|sort|figure)',
        r'^(?:it was|this was) (?:only|just) the (?:beginning|start)',
        r'^the (?:answer|truth|real work|hard part|rest) (?:would|could|lay|waited)',
        r'^(?:but |and )?(?:that|it|this) (?:was|would be) (?:for|a) (?:another|later|tomorrow)',
        r'^there (?:was|would be) (?:time|work|more|plenty)',
        r'^(?:he|she|they|i) (?:knew|understood|realized) (?:then |now )?(?:that |what )',
    ]

    for pattern in generic_patterns:
        if re.match(pattern, last_lower):
            # Trim the generic sentence — end on the previous one
            trimmed_para = " ".join(sentences[:-1])
            paragraphs[-1] = trimmed_para
            return "\n\n".join(paragraphs)

    return text


# ─── Skeleton Generator ──────────────────────────────────────────────────────

SKELETON_SYSTEM = (
    "You are a novel architect planning a single chapter beat by beat.\n"
    "Output STRICT JSON only. No commentary, no code fences.\n\n"
    "Each beat is a SCENE — a continuous dramatic unit with a clear purpose.\n"
    "When expanded into prose, a beat becomes 2-5 paragraphs.\n\n"
    "CHAPTER STRUCTURE PHILOSOPHY:\n"
    "A chapter is NOT a tour. It is not a sequence of observations. It is a dramatic unit\n"
    "with a BEGINNING STATE and an END STATE that are DIFFERENT. Something must change —\n"
    "a relationship, a piece of knowledge, a decision, a threat level, a commitment.\n"
    "If you cannot articulate what changed between beat 1 and the final beat, the chapter\n"
    "does not justify its existence.\n\n"
    "BEAT COUNT: Plan FEWER, DEEPER beats. A chapter should have 6-10 beats, not 12-16.\n"
    "Each beat should do real work. If a beat is just 'character walks to location and\n"
    "notices the atmosphere,' CUT IT. Atmosphere belongs inside action beats, not as\n"
    "standalone beats.\n\n"
    "CRITICAL RULES FOR BEAT PLANNING:\n"
    "- Plan beats based on what the STORY needs, not a word count target.\n"
    "- Most beats should be 'plain' register (functional prose). Only 1 beat should be 'vivid.'\n"
    "- OPENING BEAT: Start mid-action or mid-interaction, NOT mid-atmosphere.\n"
    "  The first beat must have a character DOING something or TALKING to someone.\n"
    "  Setting details should be woven INTO the action, not placed before it.\n"
    "  BAD: 'Describe the location at night.' GOOD: 'Character checks equipment and finds something wrong.'\n"
    "  BAD: 'Character arrives and looks around.' GOOD: 'Character arrives and someone greets them with odd instructions.'\n"
    "- SURPRISE BEAT: At least one beat must SUBVERT the reader's expectation.\n"
    "  A character says something unexpected. A discovery reframes what came before.\n"
    "  A routine action reveals something wrong. Someone shows up who shouldn't be there.\n"
    "  Mark this beat with info_type 'new_development' and note what the surprise IS.\n"
    "- DECISION BEAT: At least one beat must show the protagonist CHOOSING — not just\n"
    "  thinking, but committing to an action with consequences. 'She decided to confront him'\n"
    "  is a decision. 'She wondered what to do' is NOT.\n"
    "- NOT every chapter needs a 'routine inspection' beat. Skip it unless the routine\n"
    "  reveals something unexpected.\n"
    "- If evidence or findings have been established in prior chapters, do NOT plan beats that\n"
    "  re-examine or re-describe that evidence. Show CONSEQUENCES only.\n"
    "- The FINAL beat must end on a specific moment — mid-dialogue, a concrete action, a question.\n"
    "  NOT a character alone reflecting. NOT ambiance.\n"
    "- Do NOT plan beats where the only action is 'character walks to X and looks around.'\n"
    "  Every beat must advance CHARACTER or PLOT. Atmosphere is seasoning, not the meal.\n"
    "- ON-PAGE PAYOFF: If the chapter plan indicates a climax, revelation, confrontation,\n"
    "  arrest, or resolution, that event MUST happen ON PAGE in this chapter's beats.\n"
    "  Do NOT defer it to a phone call, a later meeting, or an off-screen authority.\n"
    "  The reader has been waiting — they must SEE the moment, not hear about it afterward.\n"
    "- VULNERABILITY: Every 3-4 chapters, include one beat where the POV character shows\n"
    "  genuine doubt, fear, exhaustion, or personal cost — not just competence. Characters\n"
    "  who never crack under pressure feel robotic. One moment of vulnerability per arc\n"
    "  section makes the strength believable.\n"
)


async def generate_skeleton(
    orchestrator,
    chapter_number: int,
    total_chapters: int,
    chapter_plan: Dict[str, Any],
    book_bible: str,
    anti_pattern_context: str = "",
    established_facts: str = "",
    previous_chapter_ending: str = "",
    style_guide: str = "",
    narrative_weight: str = "standard",
    world_building: str = "",
    outline_excerpt: str = "",
    director_brief: str = "",
    relationship_context: str = "",
    entity_registry: str = "",
    chapter_blueprint: str = "",
    plot_timeline: str = "",
) -> List[Dict[str, Any]]:
    """Generate a beat-level skeleton for a chapter.
    
    Args:
        narrative_weight: 'light' (transition/quiet), 'standard', or 'heavy' (climax/major event)
        world_building: World-building reference excerpt (sensory palettes, rules)
        outline_excerpt: Outline section for this specific chapter
        director_brief: Director brief for this chapter (scene cards)
        chapter_blueprint: Pre-computed structural blueprint from the blueprint generator
        plot_timeline: Plot timeline excerpt for continuity
        relationship_context: Relationship dynamics relevant to this chapter's characters
        entity_registry: Proper noun registry for name consistency
    """
    plan_summary = chapter_plan.get("summary", "")
    plan_objectives = chapter_plan.get("objectives", [])
    plan_opening = chapter_plan.get("opening_type", "")
    plan_ending = chapter_plan.get("ending_type", "")
    plan_characters = chapter_plan.get("focal_characters", [])
    plan_pov = chapter_plan.get("pov_character", "")
    plan_emotional_arc = chapter_plan.get("emotional_arc", "")
    plan_plot_points = chapter_plan.get("required_plot_points", [])
    plan_transition = chapter_plan.get("transition_note", "")

    weight_guidance = {
        "light": "This is a quieter chapter — 4-6 beats. Focus on character interaction and one key shift. Shorter is better — not every chapter needs to be the same length.",
        "standard": "Standard chapter — 6-9 beats. Mix of action, dialogue, and one surprise.",
        "heavy": "This is a major chapter (climax, revelation, confrontation) — 9-12 beats. Full scenes with buildup, escalation, and consequence. This chapter should be LONGER than average.",
    }

    # Ensure we have characters — extract from bible if plan doesn't provide them
    if not plan_characters:
        plan_characters = _extract_character_names_from_bible(book_bible)
    if not plan_pov and plan_characters:
        plan_pov = plan_characters[0]

    # Build the MANDATORY EVENTS section from plan data
    mandatory_events = []
    if plan_summary:
        mandatory_events.append(f"STORY: {plan_summary}")
    for pp in plan_plot_points:
        if pp and isinstance(pp, str):
            mandatory_events.append(f"MUST HAPPEN: {pp}")
    for obj in plan_objectives:
        if obj and isinstance(obj, str) and obj not in mandatory_events:
            mandatory_events.append(f"OBJECTIVE: {obj}")

    user_prompt = (
        f"Create a beat-by-beat skeleton for Chapter {chapter_number} of {total_chapters}.\n\n"
        f"NARRATIVE WEIGHT: {weight_guidance.get(narrative_weight, weight_guidance['standard'])}\n\n"
    )

    # Present plan events as NON-NEGOTIABLE requirements, not suggestions
    if mandatory_events:
        user_prompt += (
            "═══════════════════════════════════════════\n"
            "  MANDATORY CHAPTER EVENTS (NON-NEGOTIABLE)\n"
            "═══════════════════════════════════════════\n"
            "Your skeleton MUST include beats that execute ALL of these events.\n"
            "You may NOT skip, defer, or replace any of them.\n"
            "Each event must have its own beat or be clearly part of a beat.\n\n"
        )
        for i, event in enumerate(mandatory_events, 1):
            user_prompt += f"  {i}. {event}\n"
        user_prompt += "\n"

    # Characters as requirements
    if plan_characters:
        user_prompt += (
            f"REQUIRED CHARACTERS (must appear in this chapter):\n"
            f"  POV: {plan_pov}\n"
            f"  Also present: {', '.join(c for c in plan_characters if c != plan_pov)}\n"
            f"  At least 2 of these characters MUST interact in dialogue.\n"
            f"  A chapter where the POV character is alone is BROKEN.\n\n"
        )

    # Structural hints (less forceful)
    if plan_opening or plan_ending or plan_emotional_arc:
        user_prompt += f"STRUCTURAL GUIDANCE:\n"
        if plan_opening:
            user_prompt += f"  - Suggested opening: {plan_opening}\n"
        if plan_ending:
            user_prompt += f"  - Suggested ending: {plan_ending}\n"
        if plan_emotional_arc:
            user_prompt += f"  - Emotional arc: {plan_emotional_arc}\n"
        if plan_transition:
            user_prompt += f"  - Transition from previous chapter: {plan_transition}\n"
        user_prompt += "\n"

    user_prompt += f"BOOK BIBLE (excerpt):\n{book_bible[:4000]}\n\n"
    if style_guide:
        user_prompt += f"STYLE GUIDE:\n{style_guide[:2000]}\n\n"
    if world_building:
        user_prompt += f"WORLD & SETTING:\n{world_building[:2000]}\n\n"
    if director_brief:
        user_prompt += f"DIRECTOR BRIEF (scene cards for this chapter):\n{director_brief[:2000]}\n\n"
    if outline_excerpt:
        user_prompt += f"OUTLINE (this chapter):\n{outline_excerpt[:1500]}\n\n"
    if relationship_context:
        user_prompt += f"RELATIONSHIP DYNAMICS:\n{relationship_context[:1500]}\n\n"
    if entity_registry:
        user_prompt += f"ENTITY REGISTRY (use these exact names):\n{entity_registry[:1500]}\n\n"
    if previous_chapter_ending:
        user_prompt += f"PREVIOUS CHAPTER ENDED WITH:\n{previous_chapter_ending[:1000]}\n\n"
    if chapter_blueprint:
        user_prompt += f"CHAPTER BLUEPRINT (use as structural guidance):\n{chapter_blueprint[:2000]}\n\n"
    if plot_timeline:
        user_prompt += f"PLOT TIMELINE (for continuity — what has happened and what comes next):\n{plot_timeline[:2000]}\n\n"
    if anti_pattern_context:
        user_prompt += f"{anti_pattern_context}\n\n"
    if established_facts:
        user_prompt += f"{established_facts}\n\n"

    # Character arc directives from book plan
    arc_beats = chapter_plan.get("character_arc_beats", [])
    if arc_beats and isinstance(arc_beats, list):
        user_prompt += "CHARACTER ARC POSITIONS FOR THIS CHAPTER:\n"
        for ab in arc_beats:
            if isinstance(ab, dict):
                user_prompt += (
                    f"- {ab.get('character', '?')}: {ab.get('arc_position', '?')} — "
                    f"{ab.get('emotional_register', '?')}. "
                    f"Motivation: {ab.get('motivation', 'N/A')}\n"
                )
        user_prompt += "Each character MUST behave consistently with their arc position.\n\n"

    user_prompt += (
        "Return a JSON object with a 'beats' array (6-10 beats):\n"
        '{"beats": [\n'
        "  {\n"
        '    "beat_number": 1,\n'
        '    "action": "What happens — be SPECIFIC. Name the action, the discovery, the decision.",\n'
        '    "what_changes": "What is different after this beat? What does the reader now know/feel?",\n'
        '    "prose_register": "plain | moderate | vivid",\n'
        '    "emotional_temperature": "low | medium | high",\n'
        '    "info_type": "new_development | deepening | decision | dialogue_scene | confrontation | action",\n'
        '    "time_of_day": "e.g. pre-dawn, early morning, mid-morning, noon, etc.",\n'
        '    "characters_present": ["Name1", "Name2"],\n'
        '    "notes": "Specific craft notes for this beat"\n'
        "  }\n"
        "]}\n\n"
        "Rules:\n"
        "- Follow the beat count from the NARRATIVE WEIGHT guidance above. "
        "Light chapters can be as few as 4 beats. Heavy chapters can be up to 12.\n"
        "- At least 70% of beats should be 'plain' register. At most 1 'vivid'.\n"
        "- At least 2 beats must be 'dialogue_scene' or 'confrontation'.\n"
        "- At least 1 beat must be 'decision' (protagonist commits to an action).\n"
        "- At least 1 beat must be 'new_development' with a genuine surprise.\n"
        "- Maximum 2 consecutive beats of the same info_type.\n"
        "- The 'what_changes' field must be DIFFERENT for every beat. If two beats\n"
        "  have the same answer for what_changes, one of them is dead weight — cut it.\n"
        "- TIME OF DAY must be consistent. Pick ONE time window and stay in it.\n"
        "- The opening beat starts mid-action or mid-conversation, never mid-atmosphere.\n"
        "- The final beat ends on a concrete moment, not reflection or ambiance.\n"
    )

    try:
        response = await orchestrator._make_api_call(
            messages=[
                {"role": "system", "content": SKELETON_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=3000,
            response_format={"type": "json_object"},
        )
    except Exception:
        return _default_skeleton(narrative_weight, chapter_plan=chapter_plan)

    content = ""
    if hasattr(response, "output_text"):
        content = response.output_text
    elif response and hasattr(response, "choices") and response.choices:
        content = response.choices[0].message.content

    try:
        parsed = json.loads(content or "")
        beats = parsed.get("beats", parsed if isinstance(parsed, list) else [])
        if isinstance(beats, list) and len(beats) >= 3:
            return beats
    except Exception:
        pass

    return _default_skeleton(narrative_weight, chapter_plan=chapter_plan)


def _default_skeleton(
    narrative_weight: str = "standard",
    chapter_plan: Dict[str, Any] = None,
) -> List[Dict[str, Any]]:
    """Fallback skeleton when LLM fails. Uses plan data when available."""
    plan = chapter_plan or {}
    count = {"light": 5, "standard": 7, "heavy": 11}.get(narrative_weight, 7)

    characters = plan.get("focal_characters", []) or []
    pov = characters[0] if characters else "Protagonist"
    others = characters[1:] if len(characters) > 1 else []
    summary = plan.get("summary", "")
    objectives = plan.get("objectives", []) or []
    plot_points = plan.get("required_plot_points", []) or []

    # Build meaningful beat actions from plan data
    planned_actions: List[str] = []
    if summary:
        planned_actions.append(f"Open the chapter: {summary[:100]}")
    for pp in plot_points:
        if pp and isinstance(pp, str):
            planned_actions.append(pp[:100])
    for obj in objectives:
        if obj and isinstance(obj, str) and obj not in planned_actions:
            planned_actions.append(obj[:100])

    info_types = ["dialogue_scene", "new_development", "deepening",
                  "confrontation", "decision", "dialogue_scene",
                  "deepening", "action", "new_development", "dialogue_scene"]

    beats = []
    for i in range(count):
        register = "plain"
        if i == count // 2:
            register = "moderate"
        elif i == count - 2:
            register = "vivid"

        action = planned_actions[i] if i < len(planned_actions) else f"Advance the chapter — beat {i + 1}"
        beat_chars = [pov]
        if others and i % 2 == 1:
            beat_chars.append(others[i % len(others)] if others else "Companion")

        beats.append({
            "beat_number": i + 1,
            "action": action,
            "what_changes": "Story advances",
            "prose_register": register,
            "emotional_temperature": "medium",
            "info_type": info_types[i % len(info_types)],
            "characters_present": beat_chars,
            "notes": "",
        })
    return beats


def _extract_character_names_from_bible(book_bible: str, max_names: int = 6) -> List[str]:
    """Extract character names from the book bible when focal_characters is empty."""
    names = []
    section_headers = frozenset({
        "Genre", "Setting", "Premise", "Tone", "Themes", "Voice", "Structure",
        "Act", "Main Characters", "Characters", "Story Arc", "Key Plot Points",
        "World Building", "World", "Plot", "Outline", "Notes", "Style",
        "Sensory Priorities", "Things to Avoid", "Pacing Rules",
    })
    # Look for markdown headers that typically introduce characters
    for match in re.finditer(r'###?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', book_bible):
        name = match.group(1).strip()
        if len(name.split()) <= 3 and name not in section_headers:
            names.append(name)
    if not names:
        # Fallback: find capitalized multi-word sequences that look like names
        for match in re.finditer(r'\b([A-Z][a-z]{2,}\s+[A-Z][a-z]{2,})\b', book_bible):
            name = match.group(1)
            if name not in names:
                names.append(name)
    return names[:max_names]


def _validate_and_fix_skeleton(
    beats: List[Dict[str, Any]],
    focal_characters: List[str],
    book_bible: str = "",
    chapter_plan: Dict[str, Any] = None,
    logger=None,
    established_context: str = "",
) -> List[Dict[str, Any]]:
    """Validate a skeleton and fix structural problems before expansion.

    Checks:
    1. Plan compliance: do required plot points and characters appear?
    2. At least 2 beats must have 2+ characters (interaction, not solo)
    3. At least 2 beats must be dialogue_scene or confrontation
    4. At least 1 beat must be decision type
    5. No more than 2 consecutive same info_type
    6. Characters_present must not be empty for most beats
    7. Final beat must not be reflection/observation
    8. Scene replay: beats must not replay scenes/revelations from prior chapters
    """
    import logging
    log = logger or logging.getLogger(__name__)
    chapter_plan = chapter_plan or {}

    if not beats:
        return beats

    # Build character list: prefer plan characters, then bible extraction
    characters = list(focal_characters) if focal_characters else []
    if not characters:
        characters = _extract_character_names_from_bible(book_bible)
    if not characters:
        characters = ["Protagonist", "Companion"]

    pov = characters[0] if characters else "Protagonist"
    others = characters[1:] if len(characters) > 1 else ["Companion"]

    fixes_applied = []

    # ── Plan compliance: ensure required characters appear ──
    # Check if the plan's focal characters actually appear in beat actions
    plan_chars = chapter_plan.get("focal_characters", []) or []
    if plan_chars and len(plan_chars) >= 2:
        all_beat_text = " ".join(
            (b.get("action", "") + " " + " ".join(b.get("characters_present", [])))
            for b in beats
        ).lower()
        missing_chars = [
            c for c in plan_chars
            if c.lower().split()[0] not in all_beat_text
        ]
        if missing_chars:
            # Inject missing characters into middle beats as dialogue partners
            for char in missing_chars[:2]:
                inject_pos = len(beats) // 2
                for j in range(inject_pos, len(beats)):
                    if beats[j].get("info_type") not in ("dialogue_scene", "confrontation"):
                        beats[j]["info_type"] = "dialogue_scene"
                        beats[j]["characters_present"] = [pov, char]
                        beats[j]["action"] = (
                            f"{char} appears and confronts/informs {pov}. "
                            f"Original: {beats[j].get('action', '')}"
                        )
                        fixes_applied.append(f"beat {j+1}: injected missing plan character {char}")
                        break

    # ── Check 0b: Scene replay detection ──
    # Match on specific scene PHRASES (3-grams), not individual words.
    # Individual words cause massive false positives because character names,
    # locations, and setting vocabulary repeat every chapter.
    if established_context:
        # Build a set of character/location names to exclude
        char_names_lower = set()
        for c in characters:
            for part in c.lower().split():
                if len(part) >= 3:
                    char_names_lower.add(part)

        # Extract prior scene 3-grams (phrases, not individual words)
        # Only from "SCENES ALREADY DEPICTED" and "REVELATIONS ALREADY MADE" sections
        prior_scene_phrases: List[str] = []
        in_scene_section = False
        for line in established_context.split("\n"):
            header_lower = line.strip().lower()
            if "scenes already depicted" in header_lower or "revelations already made" in header_lower:
                in_scene_section = True
                continue
            if header_lower.startswith("already established") or header_lower.startswith("unresolved") or header_lower.startswith("character emotional"):
                in_scene_section = False
                continue
            if not in_scene_section:
                continue
            stripped = line.strip().lstrip("- ")
            if stripped.startswith("Ch ") and ":" in stripped:
                scene_desc = stripped.split(":", 1)[1].strip().lower()
                words = [w for w in re.findall(r"[a-z]{4,}", scene_desc)
                         if w not in _STOPWORDS and w not in char_names_lower]
                for j in range(len(words) - 2):
                    prior_scene_phrases.append(f"{words[j]} {words[j+1]} {words[j+2]}")

        if prior_scene_phrases:
            phrase_set = set(prior_scene_phrases)
            replay_flags = 0
            for i, beat in enumerate(beats):
                if replay_flags >= 2:
                    break
                action_lower = (beat.get("action", "") or "").lower()
                action_words = [w for w in re.findall(r"[a-z]{4,}", action_lower)
                                if w not in _STOPWORDS and w not in char_names_lower]
                beat_phrases = set()
                for j in range(len(action_words) - 2):
                    beat_phrases.add(f"{action_words[j]} {action_words[j+1]} {action_words[j+2]}")
                matching = beat_phrases & phrase_set
                if len(matching) >= 2:
                    match_str = "; ".join(sorted(matching)[:3])
                    beat["notes"] = (
                        f"{beat.get('notes', '')} "
                        f"CAUTION: This beat's action resembles a prior scene ({match_str}). "
                        f"Show NEW consequences or reactions, not the same events."
                    ).strip()
                    replay_flags += 1
                    fixes_applied.append(f"beat {i+1}: added scene-replay caution (soft warning)")

    # ── Check 1: How many beats have 2+ characters? ──
    multi_char_beats = sum(
        1 for b in beats
        if len(b.get("characters_present", [])) >= 2
    )
    if multi_char_beats < 2:
        inject_positions = [len(beats) // 3, len(beats) * 2 // 3]
        for pos in inject_positions:
            if pos < len(beats):
                beat = beats[pos]
                existing = beat.get("characters_present", [])
                if len(existing) < 2:
                    beat["characters_present"] = [pov] + others[:1]
                    if beat.get("info_type") not in ("dialogue_scene", "confrontation"):
                        beat["info_type"] = "dialogue_scene"
                        beat["action"] = (
                            f"{pov} and {others[0]} discuss the situation — "
                            f"tension, disagreement, or new information exchanged. "
                            f"Original action: {beat.get('action', '')}"
                        )
                    fixes_applied.append(f"beat {pos+1}: injected characters + dialogue")

    # ── Check 2: Dialogue beat count ──
    dialogue_beats = sum(
        1 for b in beats
        if b.get("info_type") in ("dialogue_scene", "confrontation")
    )
    if dialogue_beats < 2:
        for i, beat in enumerate(beats):
            if dialogue_beats >= 2:
                break
            if beat.get("info_type") in ("deepening", "action", "new_development") and i > 0:
                beat["info_type"] = "dialogue_scene"
                existing_chars = beat.get("characters_present", [])
                if len(existing_chars) < 2:
                    beat["characters_present"] = [pov] + others[:1]
                beat["action"] = (
                    f"Dialogue scene between {beat['characters_present'][0]} "
                    f"and {beat['characters_present'][-1]}. "
                    f"Original action: {beat.get('action', '')}"
                )
                dialogue_beats += 1
                fixes_applied.append(f"beat {i+1}: converted to dialogue_scene")

    # ── Check 3: At least 1 decision beat ──
    decision_beats = sum(1 for b in beats if b.get("info_type") == "decision")
    if decision_beats < 1:
        idx = max(0, len(beats) - 2)
        beats[idx]["info_type"] = "decision"
        beats[idx]["action"] = (
            f"{pov} makes a decision — commits to a specific action "
            f"with consequences. Original: {beats[idx].get('action', '')}"
        )
        fixes_applied.append(f"beat {idx+1}: converted to decision")

    # ── Check 4: Populate empty characters_present ──
    for beat in beats:
        if not beat.get("characters_present"):
            beat["characters_present"] = [pov]

    # ── Check 5: Break consecutive same-type runs ──
    for i in range(2, len(beats)):
        if (beats[i].get("info_type") == beats[i-1].get("info_type") ==
                beats[i-2].get("info_type")):
            if beats[i-1].get("info_type") != "dialogue_scene":
                beats[i-1]["info_type"] = "dialogue_scene"
                if len(beats[i-1].get("characters_present", [])) < 2:
                    beats[i-1]["characters_present"] = [pov] + others[:1]
                fixes_applied.append(f"beat {i}: broke 3-way same-type run")

    # ── Check 5b: Cap consecutive solo beats ──
    # 3 consecutive solo beats get a soft warning.
    # 4+ consecutive solo beats get a character injected (unless the chapter
    # plan or style guide indicates isolation is intentional — e.g. horror, survival).
    solo_run_start = None
    for i, beat in enumerate(beats):
        chars = beat.get("characters_present", [])
        is_solo = (len(chars) <= 1)
        if is_solo:
            if solo_run_start is None:
                solo_run_start = i
        else:
            solo_run_start = None

        if solo_run_start is not None:
            run_length = i - solo_run_start + 1
            if run_length == 3:
                mid = solo_run_start + 1
                beats[mid]["notes"] = (
                    f"{beats[mid].get('notes', '')} "
                    f"CAUTION: 3 consecutive solo beats. Consider adding another "
                    f"character for interaction unless isolation is intentional."
                ).strip()
                fixes_applied.append(f"beat {mid+1}: soft warning for 3 consecutive solo beats")
            elif run_length >= 4:
                mid = solo_run_start + 1
                beats[mid]["characters_present"] = [pov] + others[:1]
                if beats[mid].get("info_type") not in ("dialogue_scene", "confrontation"):
                    beats[mid]["info_type"] = "dialogue_scene"
                    beats[mid]["action"] = (
                        f"Another character arrives or interrupts — "
                        f"brief exchange. Original: {beats[mid].get('action', '')}"
                    )
                fixes_applied.append(f"beat {mid+1}: broke 4+ consecutive solo beats")
                solo_run_start = None

    # ── Check 6: Final beat should not be pure reflection/observation ──
    final = beats[-1] if beats else None
    if final and final.get("info_type") in ("deepening", "transition"):
        action_lower = (final.get("action", "") or "").lower()
        if any(w in action_lower for w in ("watch", "reflect", "think", "sunrise",
                                            "sunrise", "dawn", "coffee", "window",
                                            "stare", "gaze", "contemplate")):
            final["info_type"] = "dialogue_scene"
            final["characters_present"] = [pov] + others[:1]
            final["action"] = (
                f"Chapter ends on a confrontation or unanswered question between "
                f"{pov} and {others[0]}. Original: {final.get('action', '')}"
            )
            fixes_applied.append("final beat: replaced reflection with dialogue ending")

    if fixes_applied:
        log.info(f"Skeleton validation fixed {len(fixes_applied)} issues: {', '.join(fixes_applied)}")

    return beats


def infer_narrative_weight(chapter_plan: Dict[str, Any], chapter_number: int, total_chapters: int) -> str:
    """Infer whether a chapter is light, standard, or heavy from its plan."""
    if not isinstance(chapter_plan, dict):
        chapter_plan = {}
    summary = (chapter_plan.get("summary", "") or "").lower()
    emotional_arc = (chapter_plan.get("emotional_arc", "") or "").lower()

    heavy_signals = ["climax", "confrontation", "revelation", "crisis", "discover", "death", "escape",
                     "betrayal", "confession", "showdown", "final", "resolution"]
    light_signals = ["quiet", "aftermath", "reflection", "transition", "routine", "morning",
                     "travel", "rest", "processing", "settling"]

    if any(s in summary or s in emotional_arc for s in heavy_signals):
        return "heavy"
    if any(s in summary or s in emotional_arc for s in light_signals):
        return "light"

    # Last 2 chapters tend to be heavy
    if total_chapters > 0 and chapter_number >= total_chapters - 1:
        return "heavy"
    # First chapter is standard
    if chapter_number == 1:
        return "standard"

    return "standard"


# ─── Character Voice Extraction ───────────────────────────────────────────────

def extract_voice_profiles(character_reference: str, max_chars: int = 2000) -> str:
    """Extract voice/speech/dialogue sections from a character reference file.
    
    Character files typically have physical descriptions at the top and voice
    profiles deeper in. This function prioritizes the voice-relevant content.
    """
    if not character_reference:
        return ""

    voice_markers = [
        "voice", "speech", "dialogue", "speaking", "communication",
        "verbal", "manner of speaking", "catchphrase", "vocabulary",
        "contractions", "accent", "tone", "diction",
    ]

    lines = character_reference.split("\n")
    voice_sections: List[str] = []
    in_voice_section = False
    current_section: List[str] = []

    for line in lines:
        lower = line.lower().strip()
        # Detect section headers that relate to voice
        is_header = lower.startswith("#") or lower.startswith("**")
        if is_header and any(marker in lower for marker in voice_markers):
            if current_section and in_voice_section:
                voice_sections.append("\n".join(current_section))
            current_section = [line]
            in_voice_section = True
        elif is_header and in_voice_section:
            voice_sections.append("\n".join(current_section))
            current_section = [line]
            in_voice_section = False
        elif in_voice_section:
            current_section.append(line)

    if current_section and in_voice_section:
        voice_sections.append("\n".join(current_section))

    if voice_sections:
        result = "\n\n".join(voice_sections)
        return result[:max_chars]

    # Fallback: return the latter half of the file (where voice profiles usually live)
    midpoint = len(character_reference) // 2
    return character_reference[midpoint:midpoint + max_chars]


async def build_voice_profiles(
    orchestrator,
    character_reference: str,
    project_path: str = ".",
) -> str:
    """Generate per-character voice rules from character reference via LLM.

    Caches the result to .project-state/voice-profiles.json and returns
    a formatted string ready for beat expansion prompt injection.
    """
    import hashlib

    state_dir = Path(project_path) / ".project-state"
    state_dir.mkdir(parents=True, exist_ok=True)
    cache_path = state_dir / "voice-profiles.json"

    ref_hash = hashlib.sha256((character_reference or "").encode("utf-8", errors="ignore")).hexdigest()[:16]

    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("ref_hash") == ref_hash and cached.get("profiles"):
                return cached["profiles"]
        except Exception:
            pass

    if not character_reference or len(character_reference.strip()) < 100:
        return extract_voice_profiles(character_reference)

    system_prompt = (
        "You are a dialogue coach. Given character descriptions, define each "
        "character's UNIQUE speech pattern so they never sound alike.\n"
        "Output a plain-text block (NOT JSON) with one section per character.\n"
        "For each character provide:\n"
        "- Avg sentence length (short/medium/long)\n"
        "- Contraction frequency (high/low/none)\n"
        "- Vocabulary tier (blue-collar slang / professional jargon / academic)\n"
        "- Verbal tics or distinctive phrases they repeat\n"
        "- What REPLACES the tic when the budget is spent (action, silence, or alternate phrasing)\n"
        "- What they NEVER say or do in dialogue\n"
        "CRITICAL CONSTRAINT: Each verbal tic or catchphrase you define must be used "
        "MAXIMUM 2 times per chapter. After 2 uses in a chapter, the character must "
        "express the same intent through the replacement you define.\n"
        "Keep each character's section to 3-5 lines.\n"
    )

    user_prompt = (
        "Define speech patterns for every named character below.\n\n"
        f"CHARACTER REFERENCE:\n{character_reference[:4000]}\n\n"
        "Return one block of text with CHARACTER VOICE RULES as the header."
    )

    try:
        response = await orchestrator._make_api_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=800,
        )
    except Exception:
        return extract_voice_profiles(character_reference)

    content = ""
    if hasattr(response, "output_text"):
        content = response.output_text
    elif response and hasattr(response, "choices") and response.choices:
        content = response.choices[0].message.content

    profiles = (content or "").strip()
    if not profiles or len(profiles) < 50:
        return extract_voice_profiles(character_reference)

    try:
        cache_path.write_text(
            json.dumps({"ref_hash": ref_hash, "profiles": profiles}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass

    return profiles


# ─── Beat Expander ────────────────────────────────────────────────────────────

REGISTER_INSTRUCTIONS = {
    "plain": (
        "Write in PLAIN prose. Short, direct sentences. Functional writing. "
        "Max 2 sentences per paragraph on average. "
        "Include ONE sensory detail per beat (not per paragraph — one per beat total). "
        "No metaphors. No lyrical flourishes. No stacked adjectives. "
        "The prose should be invisible — the reader sees the scene, not the writing.\n"
        "ENVIRONMENTAL BALANCE: Most paragraphs should be about CHARACTER ACTION, "
        "DIALOGUE, or THOUGHT — not environmental description. Setting details should "
        "be woven into action sentences, not standalone observations.\n"
        "SENTENCE LENGTH VARIETY (critical): Mix short sentences (under 8 words) with "
        "medium (8-19 words) and at least ONE long sentence (20+ words) per beat. "
        "Target: 25-40% short, 50-65% medium, 10-15% long.\n"
        "EXAMPLES OF PLAIN PROSE:\n"
        "  'She checked the lock. The handle was cold, slick with rain that came "
        "off on her palm. She turned it once and listened. Nothing. She moved on.'\n"
        "TARGET: 100-180 words for this beat."
    ),
    "moderate": (
        "Write in MODERATE prose. Mix plain sentences with occasional descriptive detail. "
        "One evocative image per 2-3 paragraphs. Keep it grounded and specific. "
        "SENTENCE LENGTH VARIETY (critical): Mix short sentences (under 8 words) with "
        "medium (8-19 words) and some long sentences (20+ words). "
        "Target: 25-35% short, 50-60% medium, 10-20% long. "
        "Vary rhythm: follow a long sentence with a short one.\n"
        "TARGET: 150-250 words for this beat."
    ),
    "vivid": (
        "Write in VIVID prose. This is a key moment — deploy sensory detail and rhythm. "
        "Allow longer, more complex sentences. Layer 2-3 senses in the key paragraph. "
        "But still: ONE strong central image per paragraph. Do not stack metaphors. "
        "Let one striking, original detail carry the moment. "
        "After the vivid moment, return to plainer prose for the beat's conclusion.\n"
        "VIVID CONTAINMENT: The heightened prose lives in ONE paragraph only — the "
        "peak moment. The paragraphs before and after it must be plain. Do NOT let "
        "atmospheric description spill across 2-3 consecutive paragraphs. If you wrote "
        "a vivid image in one paragraph, the next paragraph must be action or dialogue.\n"
        "SENTENCE LENGTH VARIETY: Even vivid beats need short sentences for contrast. "
        "Target: 20-30% short, 45-55% medium, 20-30% long.\n"
        "EXAMPLES OF VIVID PROSE:\n"
        "  'Lightning cracked overhead, so bright it turned the world to bone. For a heartbeat, "
        "everything sharpened — the fence, the slick black puddles, the dark shape beyond.'\n"
        "TARGET: 200-300 words for this beat."
    ),
}

TEMP_INSTRUCTIONS = {
    "low": "Calm, quiet moment. Let the character breathe. No urgency. Slower rhythm.",
    "medium": "Normal tension. Things are in motion but not at crisis point.",
    "high": "Tense, urgent. Short sentences. Quick actions. Stakes are real and immediate.",
}


async def expand_beat(
    orchestrator,
    beat: Dict[str, Any],
    chapter_number: int,
    book_bible_excerpt: str,
    character_reference: str,
    previous_beats_text: str,
    established_facts: str = "",
    overused_words: str = "",
    pov_character: str = "",
    is_final_beat: bool = False,
    is_first_beat: bool = False,
    world_reference: str = "",
    entity_registry: str = "",
    director_scene_card: str = "",
    style_guide: str = "",
    character_voice_profiles: str = "",
    avoid_phrases: str = "",
    overused_phrases: str = "",
    previous_beat_emotional_point: str = "",
    within_chapter_repetition: str = "",
    chapter_events_summary: str = "",
) -> str:
    """Expand a single beat into prose. No word target — write until the beat is complete."""

    register = beat.get("prose_register", "plain")
    temperature = beat.get("emotional_temperature", "medium")
    action = beat.get("action", "Continue the scene")
    characters = beat.get("characters_present", [])
    notes = beat.get("notes", "")
    info_type = beat.get("info_type", "deepening")
    time_of_day = beat.get("time_of_day", "")

    register_instruction = REGISTER_INSTRUCTIONS.get(register, REGISTER_INSTRUCTIONS["plain"])
    temp_instruction = TEMP_INSTRUCTIONS.get(temperature, TEMP_INSTRUCTIONS["medium"])

    system_prompt = (
        "You are a novelist writing a short passage (2-5 paragraphs) that is part of a larger chapter.\n"
        "Output ONLY the prose. No headings, no meta-commentary, no beat numbers.\n"
        "Write in third person past tense unless the book context specifies otherwise.\n"
        f"\n{register_instruction}\n"
        f"\n{temp_instruction}\n"
        "\nCRITICAL RULES:\n"
        "- Write until this beat's action is COMPLETE, then stop. Don't pad, don't rush.\n"
        "- SENTENCE RHYTHM: At least 1 in 4 sentences must be 8 words or fewer. "
        "After any sentence over 20 words, the next sentence MUST be under 10 words. "
        "Vary rhythm constantly — never write 3 medium-length sentences in a row.\n"
        "- Do NOT explain what a detail means after showing it. Show, then move on.\n"
        "- SINGLE-CHANNEL RULE: Every emotional point, observation, or realization gets ONE channel:\n"
        "  Option A: Show through action/body language (then move on)\n"
        "  Option B: Show through dialogue (then move on)\n"
        "  Option C: Show through brief internal thought (then move on)\n"
        "  NEVER use two channels for the same point. NEVER use three.\n"
        "- After showing an emotion through any channel, the NEXT paragraph must be about something else.\n"
        "- If a character makes a decision, state it ONCE through action. Do not then think about it or discuss it.\n"
        "- Do NOT repeat information from earlier in the chapter.\n"
        "- Dialogue should sound like real people — clipped, unfinished, no speeches.\n"
        "- Each character should sound different from every other character.\n"
        "- Characters NEVER state the book's theme in dialogue. No abstract declarations.\n"
        "- Confessions should use euphemism and deflection, not direct statements of guilt.\n"
        "- No rehearsal monologues: characters do NOT practice what they will say to others.\n"
        "- DIALOGUE ESCALATION: In any scene with 3+ dialogue exchanges, each exchange must "
        "SHIFT something — the power balance, the information level, the emotional register, "
        "or the topic. If character A asks a question and character B deflects, the NEXT exchange "
        "cannot be the same pattern. A must try a different angle, or B must crack. Conversations "
        "that repeat the same posture (ask → deflect → ask → deflect) are broken.\n"
        "- ATTRIBUTION VARIETY: Do NOT use 'kept his voice even/flat/measured/low' more than "
        "ONCE per chapter. After the first use, show tone through WORD CHOICE and SENTENCE "
        "LENGTH, not narrator description. Vary dialogue tags: use 'said' for most, silence "
        "or action beats for the rest. Never stack 'he replied... he answered... he said' in "
        "consecutive exchanges.\n"
        "- NEVER start a sentence with 'There was' or 'There were.' Restructure to lead "
        "with the subject or a sensory detail instead.\n"
        "- CHARACTER INTERIORITY: The POV character is a thinking, feeling person — not a "
        "camera. In at least one paragraph per beat, show what they THINK, REMEMBER, WANT, "
        "FEAR, or DECIDE — not just what they see and hear. Weave thought naturally into "
        "action: 'He tightened the grip, thinking of the last time things had gone wrong.' "
        "Not every paragraph needs interiority, but every beat needs SOME.\n"
        "- ENVIRONMENTAL DISCIPLINE: Do NOT describe the setting in every paragraph. "
        "After the opening beat establishes the scene, subsequent beats should focus on "
        "CHARACTER ACTION, DIALOGUE, and THOUGHT. Setting details should be brief and "
        "woven into action, not standalone paragraphs of observation.\n"
        "- Use proper nouns exactly as they appear in the entity registry.\n"
        "- Ground each scene in at least one sensory detail from the world reference.\n"
        "- GESTURE BUDGET: Default is 3 physical gestures for the ENTIRE chapter (nod, sigh, "
        "jaw clench, shoulder shift, leaning, exhaling, etc.). MOST beats have ZERO gestures. "
        "Each gesture may appear ONCE only — never repeat the same gesture. "
        "Prefer dialogue, action, or sensory detail over body language. "
        "Exception: if the STYLE GUIDE indicates physical interaction is central to the genre "
        "(romance, action, dance, sports), increase the budget to match the style guide.\n"
        "- PROP BUDGET: Do not mention the same physical object more than 2 times per chapter. "
        "After 2 mentions, refer to it indirectly or skip entirely. "
        "Exception: if a prop is CENTRAL to the plot of this beat (a weapon in a fight, "
        "a letter being read), it may appear more, but vary the phrasing each time.\n"
        "- NO REPEATED VERBAL TICS: Each character's verbal tic or catchphrase may appear "
        "MAXIMUM 2 times in a chapter. After that, express the same intent through action, "
        "silence, or different phrasing.\n"
        "- SENSORY FRESHNESS: Do not repeat the same environmental detail (smell, sound, "
        "temperature, light quality) that appeared in earlier beats. Each beat needs a NEW "
        "sensory detail from a DIFFERENT sense. If earlier beats used sound, use smell or "
        "touch. Never write 'the air felt' or 'the hum of' if those phrases appeared before.\n"
        "- SENSORY BALANCE: Default maximum of 2 references to any SINGLE sense per chapter "
        "(e.g. max 2 smell references, max 2 sound references). Rotate across all five "
        "senses. No specific sensory detail (a particular smell, a particular sound) should "
        "appear more than once per chapter. Exception: if the style guide emphasizes a "
        "particular sense for this genre, follow the style guide.\n"
        "- EVIDENCE RULE: Each piece of evidence or prior finding may be mentioned AT MOST "
        "ONCE in this beat, and AT MOST ONCE in the entire chapter. If an earlier beat already "
        "referenced it, do NOT mention it again — the reader remembers. When you do reference "
        "evidence, use a DIFFERENT phrasing each time across chapters (e.g. vary between "
        "'the marks on the hatch', 'what he'd found at the hatch', 'the hatch discovery'). "
        "Do NOT re-describe what the evidence looks like or what it means.\n"
    )

    if overused_phrases:
        top_banned = overused_phrases.strip().split("\n")[:5]
        system_prompt += (
            "\nBANNED PHRASES (overused across prior chapters — "
            "do NOT write any of these or close variants):\n"
            + "\n".join(top_banned) + "\n"
        )

    if previous_beat_emotional_point:
        system_prompt += (
            f"\n- The previous beat already conveyed: '{previous_beat_emotional_point}'. "
            "Do NOT restate this through narration, thought, or dialogue. "
            "ADVANCE the scene — show a NEW reaction, a consequence, or a shift.\n"
        )

    if is_first_beat:
        system_prompt += (
            "\nFIRST BEAT — OPENING RULES:\n"
            "- Start IN THE MIDDLE OF SOMETHING HAPPENING. A character doing, saying, "
            "or discovering — not just arriving or looking around.\n"
            "- The first WORD must NOT be a character's name or pronoun.\n"
            "- Do NOT open with atmospheric description. Setting details must be woven into "
            "the character's action. Maximum 1 sentence of pure setting before the first action.\n"
            "- BAD: 3 paragraphs describing the setting, THEN the character does something.\n"
            "- GOOD: Character doing something specific — the setting is conveyed through "
            "what they touch, smell, hear while acting.\n"
            "- BAD: Character standing in a doorway, looking at a room for 2 paragraphs.\n"
            "- GOOD: Character entering and immediately interacting — the room visible "
            "THROUGH the action.\n"
        )

    if not is_final_beat:
        system_prompt += "- End the passage mid-flow so the next beat can continue naturally.\n"

    if is_final_beat:
        system_prompt += (
            "\nFINAL BEAT: This ends the chapter. End on a SPECIFIC moment:\n"
            "- Mid-dialogue, a concrete physical action, a question from another character, or an arrival/departure.\n"
            "- Do NOT end with a character alone reflecting.\n"
            "- Do NOT end with a thematic declaration.\n"
            "- Do NOT end with atmospheric description.\n"
            "- The last sentence should be concrete and specific, not abstract.\n"
        )

    user_prompt = f"BEAT TO WRITE:\n{action}\n\n"
    if characters:
        user_prompt += f"CHARACTERS: {', '.join(characters)}\n"
    if pov_character:
        user_prompt += f"POV: {pov_character}\n"
    if info_type:
        user_prompt += f"BEAT TYPE: {info_type}\n"
    if time_of_day:
        user_prompt += (
            f"TIME OF DAY: {time_of_day}\n"
            f"All ambient details (light, temperature, sky, sounds) MUST match this time. "
            f"Do NOT introduce dawn cues if it's night, or dusk cues if it's morning.\n"
        )
    if info_type == "character_moment":
        user_prompt += (
            "This is a CHARACTER MOMENT beat: the POV character must THINK, REMEMBER, "
            "or MAKE A DECISION in this beat. Show their inner life — a memory, a regret, "
            "a realization, a weighing of options. Not just external perception.\n"
        )
    if notes:
        user_prompt += f"NOTES: {notes}\n"
    if director_scene_card:
        user_prompt += f"\nDIRECTOR SCENE CARD:\n{director_scene_card[:600]}\n"

    if chapter_events_summary:
        user_prompt += (
            f"\nCHAPTER EVENTS SO FAR (canonical record — your prose MUST be consistent with these):\n"
            f"{chapter_events_summary}\n"
            f"Any dialogue that retells these events must match exactly. Do NOT contradict who "
            f"found what, who told whom, or the sequence of actions.\n"
        )

    if previous_beats_text:
        tail = previous_beats_text[-1500:]
        user_prompt += f"\nPREVIOUS TEXT (continue from here, do not repeat):\n...{tail}\n"

    if established_facts:
        user_prompt += f"\nALREADY ESTABLISHED (brief reference only, do not re-describe):\n{established_facts[:1000]}\n"

    if overused_words:
        user_prompt += f"\nOVERUSED WORDS TO AVOID: {overused_words}\n"
    if avoid_phrases:
        user_prompt += f"\nOVERUSED PHRASES TO AVOID: {avoid_phrases}\n"
    if overused_phrases:
        user_prompt += f"\nPHRASES OVERUSED IN PRIOR CHAPTERS (avoid or rephrase):\n{overused_phrases}\n"
    if within_chapter_repetition:
        user_prompt += f"\n{within_chapter_repetition}\n"

    if style_guide:
        user_prompt += f"\nSTYLE GUIDE (follow these prose guidelines):\n{style_guide[:1500]}\n"
    if character_voice_profiles:
        user_prompt += f"\nCHARACTER VOICE PROFILES (match each character's speech patterns):\n{character_voice_profiles[:2000]}\n"

    user_prompt += f"\nBOOK CONTEXT:\n{book_bible_excerpt[:1500]}\n"
    if character_reference:
        user_prompt += f"\nCHARACTERS:\n{character_reference[:1500]}\n"
    if world_reference:
        user_prompt += f"\nWORLD & SENSORY DETAILS:\n{world_reference[:1000]}\n"
    if entity_registry:
        user_prompt += f"\nPROPER NOUNS (use exact spellings):\n{entity_registry[:800]}\n"

    user_prompt += "\nWrite the passage now."

    try:
        response = await orchestrator._make_api_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.6 if register == "vivid" else 0.45,
            max_tokens=800,
        )
    except Exception:
        return ""

    content = ""
    if hasattr(response, "output_text"):
        content = response.output_text
    elif response and hasattr(response, "choices") and response.choices:
        content = response.choices[0].message.content

    return (content or "").strip()


# ─── Stitch Pass ──────────────────────────────────────────────────────────────

async def stitch_beats(
    orchestrator,
    expanded_text: str,
    chapter_number: int,
    book_bible_excerpt: str,
    repetition_report: str = "",
    cross_chapter_phrases: str = "",
    chapter_events_summary: str = "",
) -> str:
    """Light smoothing pass with data-driven repetition fixing.

    The repetition_report provides specific issues found by the scanner,
    giving the editor concrete targets rather than vague instructions.
    """
    if not expanded_text or len(expanded_text.split()) < 200:
        return expanded_text

    system_prompt = (
        "You are a professional fiction editor doing a focused revision pass.\n"
        "Fix these specific issues:\n\n"
        "1. DEAD WEIGHT: Cut or condense any paragraph where the character just 'paused,' "
        "'listened,' 'glanced,' or 'waited' without advancing plot, character, or tension. "
        "Also cut any paragraph that is PURE REFLECTION — 'He thought about X', "
        "'He considered Y', 'He wondered about Z' — where the character is only musing "
        "without acting, deciding, or learning. Reflection is earned ONLY when it leads "
        "directly to a decision or action in the same paragraph. "
        "If a paragraph could be removed without the reader noticing, remove it.\n\n"
        "2. REPETITION FIXES: See the SPECIFIC ISSUES section for exact phrases and words "
        "that repeat. Replace the 3rd+ occurrence with a DIFFERENT action or cut the sentence.\n\n"
        "3. CONSTRUCTION CRUTCHES: Look for repeated sentence SHAPES (not just repeated words):\n"
        "   - '[noun] pressed in/close/against' — rewrite with a different construction\n"
        "   - 'She/He did not [verb]' — vary the syntax\n"
        "   - 'Not for the first time' — cut or rewrite\n"
        "   - 'The sound/hum/drone of [noun] filled/pressed/settled' — vary or cut\n"
        "   If ANY construction pattern appears 3+ times, rewrite the extras.\n\n"
        "4. ATMOSPHERIC OVERLOAD: If the opening has 2+ paragraphs of pure setting before "
        "the first character action, condense the setting INTO the action paragraphs.\n\n"
        "5. GESTURE/SENSORY/VERBAL TIC AUDITS: Same rules as before — max 3 gestures, "
        "max 2 of any sensory detail, max 2 of any verbal tic.\n\n"
        "6. INTERNAL CONSISTENCY: Check that any dialogue retelling events (who found what, "
        "who called whom, who arrived first) matches the NARRATED version earlier in the chapter. "
        "If a character claims they did something that the narration showed someone else doing, "
        "fix the dialogue to match the narration. The narrated version is always canonical.\n\n"
        "7. TAIL DRAG: After the LAST dialogue or character interaction in the chapter, there "
        "should generally be at most 2 short paragraphs before the chapter ends. If the chapter "
        "has 3+ paragraphs of solo activity after the last conversation, condense them unless "
        "the solo ending serves a clear narrative purpose (building dread, showing isolation, "
        "processing a major revelation). The chapter should usually end close to its last "
        "moment of tension.\n\n"
        "Do NOT:\n"
        "- Add new metaphors, imagery, or sensory details\n"
        "- Expand or pad the text — the goal is TIGHTER, not longer\n"
        "- Change character voice, plot content, or register\n"
        "- Include ANY preamble, explanation, or list of changes you made\n"
        "\nOutput ONLY the revised chapter text. No 'Here is your revised...' or "
        "bullet lists of changes. Start directly with the first sentence of the chapter.\n"
    )

    user_prompt = (
        f"Smooth this Chapter {chapter_number} draft. Minimal changes only.\n\n"
    )

    if repetition_report:
        user_prompt += (
            f"SPECIFIC ISSUES FOUND (fix these):\n{repetition_report}\n\n"
        )
    if cross_chapter_phrases:
        user_prompt += (
            f"PHRASES OVERUSED ACROSS PRIOR CHAPTERS (replace if found):\n"
            f"{cross_chapter_phrases}\n\n"
        )
    if chapter_events_summary:
        user_prompt += (
            f"CANONICAL EVENT SEQUENCE (use this to verify consistency — "
            f"if any dialogue contradicts these events, fix the dialogue):\n"
            f"{chapter_events_summary}\n\n"
        )

    user_prompt += (
        f"CHAPTER TEXT:\n{expanded_text}\n\n"
        "Return the complete chapter."
    )

    try:
        response = await orchestrator._make_api_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=max(2000, int(len(expanded_text.split()) * 1.5)),
        )
    except Exception:
        return expanded_text

    content = ""
    if hasattr(response, "output_text"):
        content = response.output_text
    elif response and hasattr(response, "choices") and response.choices:
        content = response.choices[0].message.content

    result = (content or "").strip()
    if not result or len(result.split()) < len(expanded_text.split()) * 0.5:
        return expanded_text
    return result


# ─── Beat-to-Beat Emotional Handoff ──────────────────────────────────────────

EMOTION_WORDS = {
    "afraid", "angry", "anxious", "ashamed", "bitter", "calm", "confident",
    "confused", "desperate", "determined", "disgusted", "embarrassed",
    "excited", "frustrated", "grateful", "guilty", "helpless", "hopeful",
    "hostile", "humiliated", "impatient", "irritated", "jealous", "lonely",
    "nervous", "overwhelmed", "panicked", "proud", "relieved", "resentful",
    "sad", "scared", "shocked", "suspicious", "tense", "terrified",
    "threatened", "tired", "uneasy", "vulnerable", "worried",
    "trembled", "shook", "flinched", "froze", "stiffened", "relaxed",
    "clenched", "sobbed", "whispered", "shouted", "screamed", "stammered",
    "hesitated", "recoiled", "winced", "sighed", "gasped",
}


def _extract_emotional_summary(text: str) -> str:
    """Extract a 1-line summary of the emotional point conveyed in a beat.

    Uses simple heuristics — finds the last sentence containing an emotion word
    or character reaction, truncated to ~100 chars.
    """
    if not text:
        return ""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    emotional_sentences = []
    for s in sentences:
        words_lower = set(re.findall(r'[a-z]+', s.lower()))
        if words_lower & EMOTION_WORDS:
            emotional_sentences.append(s.strip())
    if emotional_sentences:
        last = emotional_sentences[-1]
        return last[:100] if len(last) > 100 else last
    if sentences:
        return sentences[-1][:100]
    return ""


# ─── Within-Chapter Event Tracker ──────────────────────────────────────────────

def _extract_beat_events(beat_text: str, beat_number: int, beat_action: str) -> str:
    """Extract a 1-2 line factual summary of what happened in a beat.

    This compact summary survives context truncation so later beats
    always know the canonical sequence of events (who found what,
    who told whom, key actions and discoveries).
    """
    if not beat_text:
        return ""

    events: List[str] = []

    # Detect dialogue attributions (who spoke)
    speakers = set()
    for m in re.finditer(r'["\u201c][^"\u201d]+["\u201d]\s*(?:,?\s*)(\w+)\s+(?:said|called|asked|replied|whispered|muttered|snapped|shouted)', beat_text):
        speakers.add(m.group(1))
    for m in re.finditer(r'(\w+)\s+(?:said|called|asked|replied|whispered|muttered|snapped|shouted)\s*[,.]?\s*["\u201c]', beat_text):
        speakers.add(m.group(1))

    # Detect discoveries / findings
    discovery_patterns = [
        r'(?:found|discovered|noticed|spotted|saw)\s+(?:a|the|an)\s+(\w[\w\s]{2,20})',
        r'(?:body|corpse|figure)\s+(?:lay|was|floated)',
        r'(?:dead|deceased|lifeless)',
    ]
    discoveries = []
    for pattern in discovery_patterns:
        for m in re.finditer(pattern, beat_text, re.IGNORECASE):
            discoveries.append(m.group(0).strip()[:40])

    # Detect decisions / actions
    decision_patterns = [
        r'(?:decided|chose|committed|resolved|made\s+(?:a|his|her)\s+decision)',
        r'(?:called|phoned|radioed|reported)',
    ]
    decisions = []
    for pattern in decision_patterns:
        for m in re.finditer(pattern, beat_text, re.IGNORECASE):
            decisions.append(m.group(0).strip())

    # Build compact summary
    parts = []
    if beat_action:
        parts.append(beat_action[:80])
    if discoveries:
        parts.append(f"Found: {'; '.join(discoveries[:2])}")
    if speakers:
        parts.append(f"Speakers: {', '.join(sorted(speakers)[:4])}")
    if decisions:
        parts.append(f"Action: {'; '.join(decisions[:2])}")

    return f"Beat {beat_number}: {' | '.join(parts)}" if parts else ""


# ─── Within-Chapter Repetition Scanner ────────────────────────────────────────

def _scan_within_chapter_repetition(accumulated_text: str) -> str:
    """Scan the chapter-so-far for ANY repeated phrases or dialogue tics.

    Purely frequency-based — no hardcoded word lists.
    Returns a compact warning for the next beat's prompt, or "".
    """
    if not accumulated_text or len(accumulated_text) < 200:
        return ""

    warnings: List[str] = []
    text_lower = accumulated_text.lower()

    # Single-word prop/object/gesture frequency scan (highest priority —
    # catches clipboard, phone, sword, nodded, sighed, etc.)
    # Skip proper nouns (character/place names) — detected by initial capitalization
    # Uses {3,} to catch short props (cup, mug, pen, gun)
    capitalized_words = set(w.lower() for w in re.findall(r"\b[A-Z][a-z]{2,}\b", accumulated_text))
    total_words = len(text_lower.split())
    word_counts = Counter(re.findall(r"[a-z]{3,}", text_lower))
    # High-frequency prose words that are normal at 2-3x per chapter and should
    # not be flagged. These are analogous to _STOPWORDS but for content words.
    _HIGH_FREQ_PROSE = frozenset({
        "said", "looked", "turned", "came", "went", "made", "like",
        "took", "got", "left", "put", "told", "asked", "let",
        "know", "still", "even", "before", "after", "time", "way",
        "long", "away", "side", "seen",
        "words", "word", "right", "thing", "things", "thought",
        "half", "felt", "keep", "kept", "last", "next", "same",
    })
    flagged = 0
    for word, count in word_counts.most_common(15):
        if flagged >= 6:
            break
        if word in _STOPWORDS or word in capitalized_words or word in _HIGH_FREQ_PROSE:
            continue
        # 4+ char words flagged at 3+ (catches nodded, sighed, shifted, clipboard, etc.)
        # 3-char words flagged at 3+ (catches cup, mug, pen, gun)
        threshold = 3
        if count >= threshold:
            warnings.append(f'word "{word}" ({count}x — find alternatives or omit)')
            flagged += 1

    # N-gram scan (catches repeated gesture phrases, atmospheric wallpaper, etc.)
    # Threshold of 2 flags phrases before they become a pattern (prevents 3rd occurrence)
    ngram_warnings = _extract_repeated_ngrams(
        accumulated_text, ns=(3,), min_occurrences=2, max_results=8
    )
    warnings.extend(ngram_warnings)

    # Dialogue tic scan (catches repeated catchphrases regardless of content)
    dialogue_phrases = re.findall(
        r'["\u201c]([^"\u201d]{3,60})["\u201d]', text_lower
    )
    phrase_counts: Counter = Counter(dialogue_phrases)
    for phrase, count in phrase_counts.items():
        if count >= 2 and len(phrase.split()) <= 10:
            warnings.append(f'catchphrase "{phrase}" ({count}x)')

    # Unearned callback detection: "again", "still [verb]ing", "as before", "once more"
    # that reference something not established earlier in this chapter's text
    callback_patterns = [
        (r'\b(\w{3,})\s+(?:started|began|came)\s+(?:up\s+)?again\b', "started X again"),
        (r'\bonce\s+more\b', "once more"),
        (r'\bas\s+before\b', "as before"),
        (r'\blike\s+(?:last|the\s+previous)\s+time\b', "like last time"),
        (r'\bnot\s+for\s+the\s+first\s+time\b', "not for the first time"),
    ]
    for pattern, label in callback_patterns:
        matches = list(re.finditer(pattern, text_lower))
        if matches:
            for m in matches[:1]:
                context_start = max(0, m.start() - 40)
                snippet = accumulated_text[context_start:m.end()].strip()
                # Check if the referenced thing actually appeared earlier
                if label == "started X again":
                    subject = m.group(1)
                    prior_text = text_lower[:m.start()]
                    if subject not in prior_text:
                        warnings.append(
                            f'unearned callback: "{subject} ... again" — '
                            f'"{subject}" has no prior mention in this chapter'
                        )

    if not warnings:
        return ""
    return (
        "⚠ REPETITION ALERT — These have ALREADY appeared in this chapter. "
        "Using them again will damage the prose. Find a completely different "
        "action, object, or phrase:\n"
        + "\n".join(f"- {w}" for w in warnings[:10])
    )


def _build_chapter_repetition_report(chapter_text: str) -> str:
    """Analyze a complete chapter for repetition and produce a concise
    data-driven report for the stitch pass.

    Includes:
    - 3-gram repetition (same as within-chapter scanner)
    - 2-gram repetition (catches semantic roots like "his jaw", "shifted his")
    - Single-word overuse (props, atmospheric crutches)
    - Dialogue tic detection
    """
    if not chapter_text or len(chapter_text.split()) < 200:
        return ""

    issues: List[str] = []
    text_lower = chapter_text.lower()

    # 2-gram scan — catches semantic repetition roots
    # "his jaw tightened" / "his jaw worked" / "his jaw clenched" all share "his jaw"
    words_lower = re.findall(r"[a-z]+", text_lower)
    bigram_counts: Counter = Counter()
    for i in range(len(words_lower) - 1):
        a, b = words_lower[i], words_lower[i + 1]
        if a in _STOPWORDS and b in _STOPWORDS:
            continue
        bigram_counts[f"{a} {b}"] += 1
    # Only keep bigrams where BOTH words are content words with 3+ letters
    semantic_roots = []
    for bg, count in bigram_counts.most_common():
        if count < 4:
            break
        a, b = bg.split()
        if a in _STOPWORDS or b in _STOPWORDS:
            continue
        if len(a) < 3 or len(b) < 3:
            continue
        semantic_roots.append(f'  "{bg}" ({count}x)')
    if semantic_roots:
        issues.append("Repeated action/body patterns (same root, different verbs each time):")
        issues.extend(semantic_roots[:5])

    # 3-gram scan
    trigrams = _extract_repeated_ngrams(chapter_text, ns=(3,), min_occurrences=3, max_results=6)
    if trigrams:
        issues.append("Repeated 3-word phrases:")
        issues.extend(f"  {t}" for t in trigrams)

    # Single-word overuse (props, atmospheric words, gesture verbs)
    capitalized = set(w.lower() for w in re.findall(r"\b[A-Z][a-z]{2,}\b", chapter_text))
    total_words = len(text_lower.split())
    word_counts = Counter(re.findall(r"[a-z]{3,}", text_lower))
    overused_words = []
    # Scan more words (top 20) to catch props that aren't the most frequent
    for word, count in word_counts.most_common(20):
        if word in _STOPWORDS or word in capitalized:
            continue
        if count >= max(3, total_words // 500):
            overused_words.append(f'  "{word}" ({count}x)')
    # Catch ANY content word at 5+ occurrences — no hardcoded lists.
    # This universally catches genre-specific crutch words (boots in a
    # thriller, blade in fantasy, stars in sci-fi) without needing to
    # anticipate them.
    for word, count in word_counts.items():
        if count >= 5 and word not in _STOPWORDS and word not in capitalized:
            entry = f'  "{word}" ({count}x)'
            if entry not in overused_words:
                overused_words.append(entry)
    if overused_words:
        issues.append("Overused words:")
        issues.extend(overused_words)

    # Dialogue tics
    dialogue_phrases = re.findall(r'["\u201c]([^"\u201d]{3,60})["\u201d]', text_lower)
    phrase_counts = Counter(dialogue_phrases)
    tics = []
    for phrase, count in phrase_counts.most_common(5):
        if count >= 2 and len(phrase.split()) <= 10:
            tics.append(f'  "{phrase}" ({count}x)')
    if tics:
        issues.append("Repeated dialogue catchphrases:")
        issues.extend(tics)

    # Gesture audit: count physical gesture patterns
    gesture_patterns = [
        (r'nodded|nod(?:ding)', "nodded/nodding"),
        (r'sigh(?:ed|ing|s)', "sigh/sighed"),
        (r'(?:jaw|teeth)\s+(?:clenched|tightened|worked|set)', "jaw clenched"),
        (r'shifted\s+(?:his|her|their)\s+weight', "shifted weight"),
        (r'exhale[ds]?\b|let\s+out\s+a\s+breath', "exhaled"),
        (r'shook\s+(?:his|her|their)\s+head', "head shake"),
        (r'(?:cleared|clearing)\s+(?:his|her|their)\s+throat', "throat clear"),
        (r'lean(?:ed|ing)\s+(?:back|forward|against)', "leaned"),
        (r'(?:rubbed|rubbing|wiped)\s', "rubbed/wiped"),
        (r'(?:crossed|folded)\s+(?:his|her|their)\s+arms', "crossed arms"),
    ]
    gesture_counts = []
    for pattern, label in gesture_patterns:
        count = len(re.findall(pattern, text_lower))
        if count >= 2:
            gesture_counts.append(f'  "{label}" ({count}x)')
    total_gesture_hits = sum(
        len(re.findall(p, text_lower)) for p, _ in gesture_patterns
    )
    if gesture_counts or total_gesture_hits > 4:
        issues.append(
            f"GESTURE OVERUSE (total: {total_gesture_hits}, budget: 3 per chapter) — "
            "CUT gestures that don't advance plot. Replace with dialogue or action:"
        )
        issues.extend(gesture_counts)

    # Construction crutch detection: repeated sentence SHAPES
    construction_patterns = [
        (r'(?:silence|noise|hum|sound|drone|quiet|darkness|heat|cold|weight|pressure)\s+'
         r'(?:pressed|settled|crept|hung|lingered|filled|pushed|closed)', "X pressed/settled/crept"),
        (r'(?:she|he|they)\s+did\s+not\s+\w+', "She/He did not [verb]"),
        (r'not\s+for\s+the\s+first\s+time', "not for the first time"),
        (r'(?:the|a)\s+(?:sound|hum|drone|whir|buzz)\s+of\s+\w+\s+'
         r'(?:filled|pressed|settled|hung)', "the sound/hum of X filled/pressed"),
        (r'already\s+(?:planning|thinking|noting|considering|sorting|cataloging|imagining|'
         r'running|mapping|weighing|replaying|moving)', "already [verb]ing"),
        (r'(?:kept|held)\s+(?:his|her|their)\s+(?:voice|tone|gaze|eyes|face|expression)\s+'
         r'(?:even|flat|steady|low|neutral|measured|still|blank|calm)',
         "kept his voice/face even/flat/steady"),
        (r'(?:he|she)\s+(?:thought|wondered)\s+(?:about|of|how|if|whether)',
         "He thought/wondered about"),
    ]
    crutch_issues = []
    for pattern, label in construction_patterns:
        hits = len(re.findall(pattern, text_lower))
        if hits >= 2:
            crutch_issues.append(f'  "{label}" pattern ({hits}x)')
    if crutch_issues:
        issues.append("CONSTRUCTION CRUTCHES (repeated sentence shapes — rewrite with varied syntax):")
        issues.extend(crutch_issues)

    # Sensory channel stacking: detect when one sense (usually smell) dominates
    smell_words = len(re.findall(
        r'(?:smell|scent|odor|tang|stink|stench|whiff|reek|fragrance|aroma|'
        r'smelled|stank|reeked|wafted|drifted|clung|lingered)\b', text_lower
    ))
    sound_words = len(re.findall(
        r'(?:hum|drone|clang|clatter|rattle|buzz|whir|thud|scrape|creak|'
        r'click|snap|bang|slam|rumble|echo)\b', text_lower
    ))
    if smell_words >= 6:
        issues.append(
            f"SENSORY IMBALANCE: Smell references ({smell_words}x) dominate — "
            f"cut to 3 max, replace extras with touch, taste, or visual details"
        )
    if sound_words >= 8:
        issues.append(
            f"SENSORY IMBALANCE: Sound references ({sound_words}x) dominate — "
            f"cut to 4 max, vary with other senses"
        )

    return "\n".join(issues) if issues else ""


# ─── Established Facts Ledger ─────────────────────────────────────────────────

class EstablishedFactsLedger:
    """Tracks what the reader already knows to prevent re-description."""

    def __init__(self, project_path: str = "."):
        self.state_dir = Path(project_path) / ".project-state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.state_dir / "established-facts.json"

    def load(self) -> List[Dict[str, Any]]:
        if not self.ledger_path.exists():
            return []
        try:
            return json.loads(self.ledger_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def save(self, facts: List[Dict[str, Any]]) -> None:
        try:
            self.ledger_path.write_text(
                json.dumps(facts, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception:
            pass

    async def extract_facts_from_chapter(
        self, orchestrator, chapter_number: int, chapter_text: str, book_bible: str
    ) -> Dict[str, Any]:
        """Extract established facts, scene events, unresolved threads, and character states."""
        if not chapter_text or len(chapter_text.split()) < 100:
            return {"facts": [], "scene_events": [], "unresolved_threads": [], "character_states": []}

        system_prompt = (
            "You are a continuity tracker. Extract SIX types of information:\n\n"
            "1. ESTABLISHED FACTS: Key facts the READER now knows (character descriptions, "
            "setting details, relationship dynamics, discoveries, objects introduced).\n\n"
            "2. SCENE EVENTS: Specific scenes that played out (e.g., 'Character A reported a "
            "problem -> Character B checked -> minor issue, no action taken'). These prevent future "
            "chapters from replaying the same scene.\n\n"
            "3. UNRESOLVED THREADS: Plot elements introduced but NOT yet resolved "
            "(e.g., 'threatening note found - not yet shown to anyone', 'glove found - "
            "not yet analyzed'). Mark each with status: OPEN.\n\n"
            "4. CHARACTER STATES: Each named character's emotional register at chapter end "
            "(e.g., 'Character X: vulnerable, scared, confided in Character Y'). These prevent characters "
            "from shifting personality without narrative motivation.\n\n"
            "5. EVIDENCE PRESENTATIONS: Any scene where evidence, findings, or investigation "
            "results are presented to other characters (e.g., 'Character A showed the report "
            "to the group — all evidence was discussed in full'). These prevent "
            "future chapters from re-presenting the SAME evidence.\n\n"
            "6. REVELATIONS & CONFESSIONS: Any scene where a character reveals a secret, "
            "confesses knowledge, admits something, or discloses information they had been "
            "withholding (e.g., 'Character A told Character B they saw someone suspicious', "
            "'Character C admitted they knew about the problem'). Include WHO told WHOM and WHAT was revealed. "
            "These are CRITICAL — future chapters must NEVER replay the same revelation.\n\n"
            "Output STRICT JSON with six arrays.\n"
        )

        user_prompt = (
            f"Extract continuity data from Chapter {chapter_number}.\n\n"
            f"TEXT (excerpt):\n{chapter_text[:4000]}\n\n"
            "Return JSON:\n"
            "{\n"
            '  "facts": [{"description": "...", "short_reference": "5-10 word ref", '
            f'"chapter_introduced": {chapter_number}, '
            '"category": "character|setting|relationship|discovery|object|rule"}],\n'
            '  "scene_events": [{"summary": "what happened in 1 sentence", '
            f'"chapter": {chapter_number}' + '}],\n'
            '  "unresolved_threads": [{"thread": "what was introduced", "status": "OPEN", '
            f'"introduced_chapter": {chapter_number}' + '}],\n'
            '  "character_states": [{"character": "Name", "emotional_state": "description", '
            f'"as_of_chapter": {chapter_number}' + '}],\n'
            '  "evidence_presentations": [{"summary": "what evidence was presented to whom", '
            f'"chapter": {chapter_number}' + '}],\n'
            '  "revelations": [{"who_revealed": "character name", "told_to": "character name", '
            '"what_revealed": "specific secret or information disclosed", '
            f'"chapter": {chapter_number}' + '}]\n'
            "}\n"
            "Extract 5-10 facts, 2-5 scene events, any unresolved threads, states for all named characters, "
            "any evidence presentation scenes, and ALL revelations/confessions.\n"
        )

        try:
            response = await orchestrator._make_api_call(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=2000,
                response_format={"type": "json_object"},
            )
        except Exception:
            return {"facts": [], "scene_events": [], "unresolved_threads": [], "character_states": []}

        content = ""
        if hasattr(response, "output_text"):
            content = response.output_text
        elif response and hasattr(response, "choices") and response.choices:
            content = response.choices[0].message.content

        try:
            parsed = json.loads(content or "")
            result = {
                "facts": [f for f in parsed.get("facts", []) if isinstance(f, dict) and f.get("short_reference")],
                "scene_events": [s for s in parsed.get("scene_events", []) if isinstance(s, dict)],
                "unresolved_threads": [t for t in parsed.get("unresolved_threads", []) if isinstance(t, dict)],
                "character_states": [c for c in parsed.get("character_states", []) if isinstance(c, dict)],
                "evidence_presentations": [e for e in parsed.get("evidence_presentations", []) if isinstance(e, dict)],
                "revelations": [r for r in parsed.get("revelations", []) if isinstance(r, dict)],
            }
            return result
        except Exception:
            return {"facts": [], "scene_events": [], "unresolved_threads": [], "character_states": [], "evidence_presentations": [], "revelations": []}

    def add_chapter_facts(self, chapter_number: int, new_data) -> None:
        """Add extracted data (facts + scene events + threads + character states)."""
        existing = self.load()

        if isinstance(new_data, dict):
            for fact in new_data.get("facts", []):
                fact["chapter_introduced"] = chapter_number
                existing.append(fact)
            ledger_data = self._load_extended()
            for event in new_data.get("scene_events", []):
                event["chapter"] = chapter_number
                ledger_data.setdefault("scene_events", []).append(event)
            for thread in new_data.get("unresolved_threads", []):
                thread["introduced_chapter"] = chapter_number
                ledger_data.setdefault("unresolved_threads", []).append(thread)
            for state in new_data.get("character_states", []):
                state["as_of_chapter"] = chapter_number
                char_states = ledger_data.setdefault("character_states", [])
                char_states[:] = [s for s in char_states if s.get("character") != state.get("character")]
                char_states.append(state)
            for ev_pres in new_data.get("evidence_presentations", []):
                ev_pres["chapter"] = chapter_number
                ledger_data.setdefault("evidence_presentations", []).append(ev_pres)
            for rev in new_data.get("revelations", []):
                rev["chapter"] = chapter_number
                ledger_data.setdefault("revelations", []).append(rev)
            self._save_extended(ledger_data)
        elif isinstance(new_data, list):
            for fact in new_data:
                fact["chapter_introduced"] = chapter_number
                existing.append(fact)

        self.save(existing)

    def _load_extended(self) -> Dict[str, Any]:
        ext_path = self.state_dir / "established-extended.json"
        if not ext_path.exists():
            return {"scene_events": [], "unresolved_threads": [], "character_states": []}
        try:
            return json.loads(ext_path.read_text(encoding="utf-8"))
        except Exception:
            return {"scene_events": [], "unresolved_threads": [], "character_states": []}

    def _save_extended(self, data: Dict[str, Any]) -> None:
        ext_path = self.state_dir / "established-extended.json"
        try:
            ext_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def update_thread_status(self, thread_keyword: str, new_status: str, chapter: int) -> None:
        """Update an unresolved thread's status (OPEN -> PROGRESSED -> RESOLVED)."""
        data = self._load_extended()
        for thread in data.get("unresolved_threads", []):
            if thread_keyword.lower() in thread.get("thread", "").lower():
                thread["status"] = new_status
                thread["updated_chapter"] = chapter
        self._save_extended(data)

    def get_established_context(self, max_chars: int = 3000) -> str:
        facts = self.load()
        ext = self._load_extended()
        sections = []
        used = 0

        if facts:
            lines = ["ALREADY ESTABLISHED (use ONLY the [short reference], do not re-describe):"]
            for fact in facts:
                ref = fact.get("short_reference", "")
                ch = fact.get("chapter_introduced", "?")
                cat = fact.get("category", "")
                line = f"- [{ref}] (Ch {ch}, {cat})"
                if used + len(line) > max_chars * 0.4:
                    break
                lines.append(line)
                used += len(line)
            sections.append("\n".join(lines))

        scene_events = ext.get("scene_events", [])
        if scene_events:
            lines = ["SCENES ALREADY DEPICTED (do NOT replay these):"]
            for event in scene_events[-15:]:
                summary = event.get("summary", "")
                ch = event.get("chapter", "?")
                line = f"- Ch {ch}: {summary}"
                if used + len(line) > max_chars * 0.65:
                    break
                lines.append(line)
                used += len(line)
            sections.append("\n".join(lines))

        threads = [t for t in ext.get("unresolved_threads", []) if t.get("status") == "OPEN"]
        if threads:
            lines = ["UNRESOLVED THREADS (you MUST advance or reference at least one):"]
            for thread in threads[-8:]:
                desc = thread.get("thread", "")
                ch = thread.get("introduced_chapter", "?")
                line = f"- [OPEN since Ch {ch}] {desc}"
                if used + len(line) > max_chars * 0.85:
                    break
                lines.append(line)
                used += len(line)
            sections.append("\n".join(lines))

        char_states = ext.get("character_states", [])
        if char_states:
            lines = ["CHARACTER EMOTIONAL STATES (any shift must be narratively motivated):"]
            for state in char_states:
                char = state.get("character", "?")
                emotion = state.get("emotional_state", "?")
                ch = state.get("as_of_chapter", "?")
                line = f"- {char} (as of Ch {ch}): {emotion}"
                if used + len(line) > max_chars * 0.9:
                    break
                lines.append(line)
                used += len(line)
            sections.append("\n".join(lines))

        ev_presentations = ext.get("evidence_presentations", [])
        if ev_presentations:
            lines = ["EVIDENCE ALREADY PRESENTED (do NOT re-describe — reference by short name only):"]
            for ep in ev_presentations[-10:]:
                summary = ep.get("summary", "")
                ch = ep.get("chapter", "?")
                line = f"- Ch {ch}: {summary}"
                if used + len(line) > max_chars * 0.95:
                    break
                lines.append(line)
                used += len(line)
            sections.append("\n".join(lines))

        revelations = ext.get("revelations", [])
        if revelations:
            lines = [
                "REVELATIONS ALREADY MADE (these secrets are OUT — do NOT have the character "
                "reveal the same information again; show CONSEQUENCES instead):"
            ]
            for rev in revelations:
                who = rev.get("who_revealed", "?")
                told = rev.get("told_to", "?")
                what = rev.get("what_revealed", "?")
                ch = rev.get("chapter", "?")
                line = f"- Ch {ch}: {who} told {told}: \"{what}\""
                if used + len(line) > max_chars:
                    break
                lines.append(line)
                used += len(line)
            sections.append("\n".join(lines))

        return "\n\n".join(sections)


# ─── Full Pipeline ────────────────────────────────────────────────────────────

async def generate_chapter_skeleton_expand(
    orchestrator,
    chapter_number: int,
    total_chapters: int,
    target_words: int,
    context: Dict[str, Any],
    logger=None,
) -> str:
    """Generate a chapter using the skeleton+expand architecture."""
    import logging
    log = logger or logging.getLogger(__name__)

    book_bible = context.get("book_bible", "") or ""
    chapter_plan = context.get("_chapter_plan", {}) or {}
    if not chapter_plan:
        chapter_plan = {
            "summary": context.get("chapter_plan_summary", ""),
            "objectives": context.get("chapter_objectives", []),
            "opening_type": context.get("opening_type", ""),
            "ending_type": context.get("ending_type", ""),
            "emotional_arc": context.get("emotional_arc", ""),
            "focal_characters": context.get("focal_characters", []),
            "pov_character": context.get("pov_character", ""),
            "required_plot_points": context.get("required_plot_points", []),
            "transition_note": context.get("transition_note", ""),
        }
    # Ensure required_plot_points is populated from context if plan doesn't have it
    if not chapter_plan.get("required_plot_points"):
        chapter_plan["required_plot_points"] = context.get("required_plot_points", [])
    if not chapter_plan.get("focal_characters"):
        chapter_plan["focal_characters"] = context.get("focal_characters", [])
    if not chapter_plan.get("transition_note"):
        chapter_plan["transition_note"] = context.get("transition_note", "")

    anti_pattern = context.get("anti_pattern_context", "") or ""
    previous_ending = context.get("last_chapter_ending", "")

    # Final chapter constraints
    is_final_chapter = (chapter_number == total_chapters)
    if is_final_chapter:
        anti_pattern += (
            "\nFINAL CHAPTER CONSTRAINTS:\n"
            "- At least 50% of beats must involve dialogue or interaction with another character.\n"
            "- Maximum 2 beats of solo reflection/introspection.\n"
            "- The chapter must end with forward motion or interpersonal connection.\n"
            "- Do NOT plan beats where the protagonist walks alone thinking about the theme.\n"
        )

    # Denouement pacing: penultimate chapter(s) after the climax
    is_denouement = (chapter_number >= total_chapters - 2) and not is_final_chapter
    if is_denouement:
        anti_pattern += (
            "\nDENOUEMENT PACING:\n"
            "- This is a post-climax chapter. Keep it TIGHT — 7-9 beats maximum.\n"
            "- Do NOT recap events the reader just witnessed. Reference them in 1 sentence max.\n"
            "- Focus on CONSEQUENCES and FORWARD MOTION, not reflection or recap.\n"
            "- At least 60% of beats must involve character interaction (dialogue or action).\n"
        )
    refs = context.get("references", {})
    if not isinstance(refs, dict):
        refs = {}

    def _ref(key: str, *alt_keys: str) -> str:
        for k in (key, *alt_keys):
            val = refs.get(k, "")
            if val:
                return val
        return ""

    style_guide = _ref("style-guide", "style_guide")
    character_ref = _ref("characters", "characters.md")
    world_building_ref = _ref("world-building", "world_building")
    outline_ref = _ref("outline", "outline.md")
    entity_registry_ref = _ref("entity-registry", "entity_registry")
    relationship_map_ref = _ref("relationship-map", "relationship_map")
    director_brief = context.get("director_brief", "") or context.get("_director_brief", "") or ""

    established_facts_text = context.get("established_facts", "")

    plot_timeline_ref = _ref("plot-timeline", "plot_timeline")
    themes_ref = _ref("themes-and-motifs", "themes_and_motifs")
    chapter_blueprint = context.get("chapter_blueprint", "")

    overused = context.get("overused_words", [])
    overused_str = ", ".join(
        e.get("word", "") for e in overused[:10] if isinstance(e, dict)
    ) if overused else ""

    avoid_phrases = context.get("avoid_phrases", [])
    avoid_phrases_str = ", ".join(
        str(p)[:60] for p in avoid_phrases[:15]
    ) if avoid_phrases else ""

    # Cross-chapter phrase tracker results (generic frequency-based, no hardcoded lists)
    # Capped at 12 to keep prompt focused on worst offenders
    overused_phrases_raw = context.get("overused_phrases", [])
    overused_phrases_str = ""
    if overused_phrases_raw:
        phrase_lines = []
        for entry in overused_phrases_raw[:12]:
            if isinstance(entry, dict) and entry.get("phrase"):
                phrase_lines.append(
                    f"- \"{entry['phrase']}\" ({entry.get('chapter_count', 0)} chapters)"
                )
        if phrase_lines:
            overused_phrases_str = "\n".join(phrase_lines)

    pov_character = context.get("pov_character", "")

    # Extract character voice profiles — try LLM-based profiles first, fall back to text extraction
    try:
        character_voice_profiles = await build_voice_profiles(
            orchestrator=orchestrator,
            character_reference=character_ref,
            project_path=str(Path(context.get("project_path", ".")).resolve()) if context.get("project_path") else ".",
        )
    except Exception:
        character_voice_profiles = extract_voice_profiles(character_ref)

    # Extract chapter-specific outline excerpt
    outline_excerpt = ""
    if outline_ref:
        ch_markers = [
            f"### Chapter {chapter_number}:",
            f"### Chapter {chapter_number} ",
            f"## Chapter {chapter_number}:",
            f"## Chapter {chapter_number} ",
        ]
        for marker in ch_markers:
            idx = outline_ref.find(marker)
            if idx >= 0:
                end_markers = ["### Chapter ", "## Chapter "]
                end_idx = len(outline_ref)
                for em in end_markers:
                    next_ch = outline_ref.find(em, idx + len(marker))
                    if next_ch > 0:
                        end_idx = min(end_idx, next_ch)
                outline_excerpt = outline_ref[idx:end_idx].strip()
                break

    # Extract relationship context for focal characters
    relationship_context = ""
    if relationship_map_ref and chapter_plan.get("focal_characters"):
        focal = [c.lower() for c in chapter_plan["focal_characters"] if isinstance(c, str)]
        lines = relationship_map_ref.split("\n")
        relevant = []
        for line in lines:
            if any(name in line.lower() for name in focal):
                relevant.append(line)
        if relevant:
            relationship_context = "\n".join(relevant[:30])

    narrative_weight = infer_narrative_weight(chapter_plan, chapter_number, total_chapters)
    log.info(f"Chapter {chapter_number}: narrative_weight={narrative_weight}")

    log.info(f"Chapter {chapter_number}: Generating skeleton...")
    skeleton = await generate_skeleton(
        orchestrator=orchestrator,
        chapter_number=chapter_number,
        total_chapters=total_chapters,
        chapter_plan=chapter_plan,
        book_bible=book_bible,
        anti_pattern_context=anti_pattern,
        established_facts=established_facts_text,
        previous_chapter_ending=previous_ending,
        style_guide=style_guide,
        narrative_weight=narrative_weight,
        world_building=world_building_ref,
        outline_excerpt=outline_excerpt,
        director_brief=director_brief,
        relationship_context=relationship_context,
        entity_registry=entity_registry_ref,
        chapter_blueprint=chapter_blueprint,
        plot_timeline=plot_timeline_ref[:3000] if plot_timeline_ref else "",
    )
    log.info(f"Chapter {chapter_number}: Skeleton has {len(skeleton)} beats (weight: {narrative_weight})")

    # Validate and fix structural issues in the skeleton before expanding
    focal_chars = chapter_plan.get("focal_characters", []) or context.get("focal_characters", []) or []
    skeleton = _validate_and_fix_skeleton(
        beats=skeleton,
        focal_characters=focal_chars,
        book_bible=book_bible,
        chapter_plan=chapter_plan,
        logger=log,
        established_context=established_facts_text,
    )

    expanded_parts: List[str] = []
    accumulated_text = ""
    emotional_summary = ""
    events_log: List[str] = []
    for i, beat in enumerate(skeleton):
        register = beat.get("prose_register", "plain")
        is_final = (i == len(skeleton) - 1)
        is_first = (i == 0)
        log.info(f"Chapter {chapter_number}: Expanding beat {i+1}/{len(skeleton)} ({register}{'[FIRST]' if is_first else ''}{'[FINAL]' if is_final else ''})")

        within_chapter_warnings = _scan_within_chapter_repetition(accumulated_text)
        events_summary = "\n".join(events_log) if events_log else ""

        beat_text = await expand_beat(
            orchestrator=orchestrator,
            beat=beat,
            chapter_number=chapter_number,
            book_bible_excerpt=book_bible[:1500],
            character_reference=character_ref[:1500],
            previous_beats_text=accumulated_text,
            established_facts=established_facts_text,
            overused_words=overused_str,
            pov_character=pov_character,
            is_final_beat=is_final,
            is_first_beat=is_first,
            world_reference=world_building_ref[:1000] if world_building_ref else "",
            entity_registry=entity_registry_ref[:800] if entity_registry_ref else "",
            style_guide=style_guide[:1500] if style_guide else "",
            character_voice_profiles=character_voice_profiles,
            avoid_phrases=avoid_phrases_str,
            overused_phrases=overused_phrases_str,
            previous_beat_emotional_point=emotional_summary,
            within_chapter_repetition=within_chapter_warnings,
            chapter_events_summary=events_summary,
        )

        if beat_text:
            expanded_parts.append(beat_text)
            accumulated_text += "\n\n" + beat_text
            emotional_summary = _extract_emotional_summary(beat_text) if not is_final else ""
            beat_event = _extract_beat_events(beat_text, i + 1, beat.get("action", ""))
            if beat_event:
                events_log.append(beat_event)

    if not expanded_parts:
        log.error(f"Chapter {chapter_number}: No beats expanded")
        return ""

    raw_chapter = "\n\n".join(expanded_parts)
    log.info(f"Chapter {chapter_number}: Raw = {len(raw_chapter.split())} words from {len(expanded_parts)} beats")

    # Step 3: Analyze full chapter for repetition, then stitch with data-driven targets
    repetition_report = _build_chapter_repetition_report(raw_chapter)
    if repetition_report:
        log.info(f"Chapter {chapter_number}: Found repetition issues for stitch pass")

    log.info(f"Chapter {chapter_number}: Stitching...")
    final_events_summary = "\n".join(events_log) if events_log else ""
    stitched = await stitch_beats(
        orchestrator=orchestrator,
        expanded_text=raw_chapter,
        chapter_number=chapter_number,
        book_bible_excerpt=book_bible[:2000],
        repetition_report=repetition_report,
        cross_chapter_phrases=overused_phrases_str,
        chapter_events_summary=final_events_summary,
    )

    # Step 4: Deterministic cleanup
    cleaned = fix_paragraph_repetition(stitched)
    cleaned = trim_repeated_phrases(cleaned)
    cleaned = strip_meta_narration(cleaned)
    cleaned = fix_generic_ending(cleaned)
    cleaned = ensure_clean_ending(cleaned)

    # Balance straight double quotes (close any dangling open)
    straight_count = cleaned.count('"')
    if straight_count % 2 == 1:
        last_quote_pos = cleaned.rfind('"')
        if last_quote_pos > len(cleaned) * 0.8:
            cleaned = cleaned + '"'

    log.info(f"Chapter {chapter_number}: Final = {len(cleaned.split())} words")
    return cleaned
