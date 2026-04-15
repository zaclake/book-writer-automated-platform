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
            response_format={"type": "json_object"}
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
