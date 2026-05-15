#!/usr/bin/env python3
"""
Book Plan Generator
Creates a master beat map and chapter objectives from book bible + references.
"""

from __future__ import annotations

import json
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token-budget helpers for reasoning-class planner models (gpt-5*, o1/o3/o4*).
#
# Reasoning models charge their hidden chain-of-thought against
# `max_completion_tokens`, but the SDK only exposes the visible output via
# `output_text` / `choices[0].message.content`. If the budget is sized for
# legacy chat models (where every token is visible), the planner can spend the
# entire allowance on internal reasoning and return an empty content string —
# which is exactly how the production book-plan call started failing once the
# planner was upgraded to gpt-5.5. These helpers inflate the budget for
# reasoning planners (clamped to the model's actual output cap) and surface
# diagnostics when an empty response slips through anyway.
# ---------------------------------------------------------------------------

_REASONING_MODEL_PREFIXES: tuple[str, ...] = ("gpt-5", "o1", "o3", "o4")


def _is_reasoning_planner(orchestrator) -> bool:
    """True if the planner tier resolves to a reasoning-class model.

    Reasoning models (gpt-5*, o-series) burn invisible reasoning tokens
    against the same ``max_completion_tokens`` budget as the visible output.
    """
    try:
        model = orchestrator._resolve_model("planner")
    except Exception:
        model = (
            getattr(orchestrator, "model_planner", None)
            or getattr(orchestrator, "model", None)
            or ""
        )
    name = (model or "").lower()
    return any(name.startswith(prefix) for prefix in _REASONING_MODEL_PREFIXES)


def _planner_budget(
    orchestrator,
    *,
    base: int,
    legacy_ceiling: int,
    reasoning_multiplier: float = 2.5,
) -> int:
    """Compute ``max_tokens`` for a planner LLM call.

    For legacy chat models (e.g. gpt-4.1) the budget is just
    ``min(legacy_ceiling, base)``. For reasoning planners we inflate the
    budget by ``reasoning_multiplier`` (and bump the ceiling by 2x) so that
    visible output still fits after the model's hidden reasoning is paid for,
    then clamp to the model's actual max output cap.
    """
    base = max(int(base), 0)
    legacy_ceiling = max(int(legacy_ceiling), 1)
    if not _is_reasoning_planner(orchestrator):
        return min(legacy_ceiling, base) if base > 0 else legacy_ceiling
    try:
        model_cap = orchestrator._get_model_max_output_tokens(
            orchestrator._resolve_model("planner")
        )
    except Exception:
        model_cap = 32000
    inflated_base = int(base * reasoning_multiplier)
    inflated_ceiling = int(legacy_ceiling * 2)
    return max(1, min(max(inflated_base, inflated_ceiling), model_cap))


def _extract_response_diagnostics(response) -> Dict[str, Any]:
    """Normalize content + finish_reason + usage from chat / responses APIs.

    Returns a dict with keys ``content`` (str), ``finish_reason``
    (``Optional[str]``), and ``usage`` (``Dict[str, Any]`` containing any of
    ``prompt_tokens``, ``completion_tokens``, ``total_tokens``,
    ``input_tokens``, ``output_tokens``, ``reasoning_tokens``).
    """
    if response is None:
        return {"content": "", "finish_reason": None, "usage": {}}

    content = ""
    if hasattr(response, "output_text"):
        content = getattr(response, "output_text", "") or ""
    elif hasattr(response, "choices"):
        try:
            content = response.choices[0].message.content or ""
        except Exception:
            content = ""

    finish_reason: Optional[str] = None
    try:
        choices = getattr(response, "choices", None)
        if choices:
            fr = getattr(choices[0], "finish_reason", None)
            if fr:
                finish_reason = str(fr)
    except Exception:
        pass
    if finish_reason is None:
        fr = getattr(response, "finish_reason", None)
        if fr:
            finish_reason = str(fr)

    usage: Dict[str, Any] = {}
    usage_obj = getattr(response, "usage", None)
    if usage_obj is not None:
        for attr in (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "input_tokens",
            "output_tokens",
        ):
            try:
                v = getattr(usage_obj, attr, None)
                if v is not None:
                    usage[attr] = v
            except Exception:
                pass
        try:
            details = getattr(usage_obj, "completion_tokens_details", None)
            if details is not None:
                rt = getattr(details, "reasoning_tokens", None)
                if rt is not None:
                    usage["reasoning_tokens"] = rt
        except Exception:
            pass

    return {
        "content": content,
        "finish_reason": finish_reason,
        "usage": usage,
    }


@dataclass
class BookPlanResult:
    success: bool
    plan: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class BookPlanGenerator:
    """Generates a master book plan (beat map + chapter objectives)."""

    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.state_dir = self.project_path / ".project-state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.plan_path = self.state_dir / "book-plan.json"
        self.promises_ledger_path = self.state_dir / "book-promises.json"

    def load_existing_plan(self) -> Optional[Dict[str, Any]]:
        if not self.plan_path.exists():
            return None
        try:
            return json.loads(self.plan_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def save_plan(self, plan: Dict[str, Any]) -> None:
        self.plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")

    # ------------------------------------------------------------------
    # Plan extension backfills (Proposals 2, 4, 5)
    #
    # The planner is instructed to emit chapter_tier / thematic_move /
    # promises_ledger, but we never want a missing field to crash the chapter
    # pipeline. These helpers normalize the plan in-place with conservative
    # defaults so downstream consumers can rely on the fields being present.
    # ------------------------------------------------------------------

    _ALLOWED_CHAPTER_TIERS = {"setpiece", "development", "connective"}
    _ALLOWED_THEMATIC_MOVES = {
        "introduce", "complicate", "invert", "deepen", "stake",
        "foreclose", "reaffirm", "answer", "coda",
    }

    # Cycle of safe non-repeating moves used when we have to break an adjacent
    # duplicate. Order chosen to be the gentlest possible nudge while still
    # representing a meaningfully different thematic move from any neighbor.
    _MOVE_ROTATION_CYCLE: tuple[str, ...] = (
        "deepen", "complicate", "stake", "reaffirm", "invert", "foreclose"
    )

    def _backfill_plan_extensions(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure chapter_tier / thematic_move / promises arrays are present.

        Defaults err on the safe side: an unspecified chapter is tagged as a
        ``development`` chapter (the most common tier) with a ``deepen``
        thematic move (the least disruptive to the per-chapter-move-variety
        rule). The promises ledger defaults to an empty list. Adjacent
        duplicate thematic moves are corrected by walking the rotation cycle
        until a non-conflicting move is found.
        """
        chapters = plan.get("chapters")
        if isinstance(chapters, list):
            prev_move: Optional[str] = None
            for chapter in chapters:
                if not isinstance(chapter, dict):
                    continue
                tier = str(chapter.get("chapter_tier") or "").strip().lower()
                if tier not in self._ALLOWED_CHAPTER_TIERS:
                    chapter["chapter_tier"] = "development"
                else:
                    chapter["chapter_tier"] = tier

                move = str(chapter.get("thematic_move") or "").strip().lower()
                if move not in self._ALLOWED_THEMATIC_MOVES:
                    move = "deepen"
                if prev_move is not None and move == prev_move:
                    for candidate in self._MOVE_ROTATION_CYCLE:
                        if candidate != prev_move:
                            move = candidate
                            break
                chapter["thematic_move"] = move
                prev_move = move

                if not isinstance(chapter.get("thematic_move_note"), str):
                    chapter["thematic_move_note"] = ""

                if not isinstance(chapter.get("promises_planted"), list):
                    chapter["promises_planted"] = []
                if not isinstance(chapter.get("promises_paid"), list):
                    chapter["promises_paid"] = []

        if not isinstance(plan.get("promises_ledger"), list):
            plan["promises_ledger"] = []
        return plan

    def save_promises_ledger(self, plan: Dict[str, Any]) -> None:
        """Persist the initial promises ledger alongside the plan.

        The ledger lives in its own file so the lifecycle service can update it
        chapter-by-chapter without touching ``book-plan.json``. This is the
        canonical artifact the chapter pipeline reads to inject outstanding
        promises.
        """
        promises = plan.get("promises_ledger") or []
        if not isinstance(promises, list):
            promises = []
        ledger = {
            "version": 1,
            "created_at": datetime.utcnow().isoformat(),
            "promises": [
                {
                    "promise_id": str(p.get("promise_id") or f"p{idx + 1}"),
                    "label": str(p.get("label") or "").strip(),
                    "description": str(p.get("description") or "").strip(),
                    "planted_chapter": p.get("planted_chapter"),
                    "expected_payoff_window": p.get("expected_payoff_window") or [],
                    "promise_type": str(p.get("promise_type") or "").strip().lower() or "obligation",
                    "weight": str(p.get("weight") or "minor").strip().lower() or "minor",
                    "status": "open",
                    "history": [],
                }
                for idx, p in enumerate(promises)
                if isinstance(p, dict)
            ],
        }
        self.promises_ledger_path.write_text(
            json.dumps(ledger, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def compute_source_hashes(self, book_bible: str, references: Dict[str, str]) -> Dict[str, str]:
        """
        Compute stable hashes for plan invalidation.
        These are intentionally content-based (not timestamps) so we can safely reuse plans.
        """
        def _sha(text: str) -> str:
            return hashlib.sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()

        # Hash the full book bible text (can be large; still fine).
        bb_hash = _sha((book_bible or "").strip())

        # Hash references deterministically by sorting keys; include content.
        parts: list[str] = []
        if isinstance(references, dict):
            for key in sorted(references.keys()):
                val = references.get(key)
                if not isinstance(val, str):
                    continue
                parts.append(f"{key}\n{val}\n")
        refs_hash = _sha("\n---\n".join(parts))

        return {"book_bible_sha256": bb_hash, "references_sha256": refs_hash}

    def _extract_json_payload(self, content: str) -> Optional[str]:
        """Attempt to extract the first JSON object from model output."""
        if not content:
            return None
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}")
        if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
            return None
        return cleaned[start_idx:end_idx + 1]

    def _repair_json_payload(self, payload: str) -> Optional[str]:
        """Best-effort cleanup for common JSON formatting issues."""
        if not payload:
            return None
        cleaned = payload.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        # Remove trailing commas
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
        # Insert commas between adjacent JSON values and keys on new lines
        cleaned = re.sub(
            r'(".*?"|\btrue\b|\bfalse\b|\bnull\b|\d|\]|\})\s*\n(\s*")',
            r"\1,\n\2",
            cleaned,
            flags=re.IGNORECASE
        )
        # Insert commas between adjacent objects/arrays
        cleaned = re.sub(r"}\s*{", r"},{", cleaned)
        cleaned = re.sub(r"]\s*{", r"],{", cleaned)
        cleaned = re.sub(r"}\s*\[", r"},[", cleaned)
        cleaned = re.sub(r"]\s*\[", r"],[", cleaned)
        return cleaned

    def _compact_plan_for_fix(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        compact = {"metadata": plan.get("metadata", {}), "story_arcs": plan.get("story_arcs", {}), "chapters": []}
        chapters = plan.get("chapters", [])
        for chapter in chapters if isinstance(chapters, list) else []:
            compact["chapters"].append({
                "chapter_number": chapter.get("chapter_number"),
                "title": str(chapter.get("title", ""))[:80],
                "summary": str(chapter.get("summary", ""))[:160],
                "objectives": [str(o)[:120] for o in (chapter.get("objectives") or [])][:3],
                "required_plot_points": [str(p)[:120] for p in (chapter.get("required_plot_points") or [])][:3],
                "opening_type": str(chapter.get("opening_type", ""))[:80],
                "ending_type": str(chapter.get("ending_type", ""))[:80],
                "emotional_arc": str(chapter.get("emotional_arc", ""))[:120],
                "focal_characters": [str(c)[:80] for c in (chapter.get("focal_characters") or [])][:4],
                "continuity_requirements": [str(c)[:120] for c in (chapter.get("continuity_requirements") or [])][:3],
                "pov_character": str(chapter.get("pov_character", ""))[:80],
                "pov_type": str(chapter.get("pov_type", ""))[:80],
                "pov_notes": str(chapter.get("pov_notes", ""))[:120],
                "transition_note": str(chapter.get("transition_note", ""))[:160],
                "chapter_shape": str(chapter.get("chapter_shape", ""))[:80],
                "prose_register": str(chapter.get("prose_register", ""))[:40],
                "tension_level": str(chapter.get("tension_level", ""))[:40],
                "new_developments": chapter.get("new_developments", ""),
                "chapter_tier": str(chapter.get("chapter_tier", ""))[:40],
                "thematic_move": str(chapter.get("thematic_move", ""))[:40],
                "thematic_move_note": str(chapter.get("thematic_move_note", ""))[:200],
                "promises_planted": [str(p)[:40] for p in (chapter.get("promises_planted") or [])][:6],
                "promises_paid": [str(p)[:40] for p in (chapter.get("promises_paid") or [])][:6],
                "character_arc_beats": chapter.get("character_arc_beats", []),
            })
        # Preserve the top-level promises ledger across fix-passes so we don't
        # silently drop the book's setups/payoffs map during chapter-count repair.
        if isinstance(plan.get("promises_ledger"), list):
            compact["promises_ledger"] = plan["promises_ledger"]
        return compact

    def _normalize_chapter_count_local(
        self,
        plan: Dict[str, Any],
        target_chapters: int
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(plan, dict):
            return None
        chapters = plan.get("chapters")
        if not isinstance(chapters, list) or not chapters:
            return None
        normalized = [dict(chapter) for chapter in chapters]
        while len(normalized) > target_chapters:
            if len(normalized) < 2:
                break
            last = normalized.pop()
            prev = normalized.pop()
            merged = dict(prev)
            for key in ("summary", "transition_note"):
                merged[key] = " ".join([str(prev.get(key, "")).strip(), str(last.get(key, "")).strip()]).strip()
            for key in ("objectives", "required_plot_points", "continuity_requirements", "focal_characters"):
                merged[key] = list(prev.get(key, []) or []) + list(last.get(key, []) or [])
            normalized.append(merged)
        if len(normalized) < target_chapters:
            idx = 0
            while len(normalized) < target_chapters and idx < len(normalized):
                chapter = normalized[idx]
                objectives = list(chapter.get("objectives", []) or [])
                plot_points = list(chapter.get("required_plot_points", []) or [])
                if len(objectives) > 1 or len(plot_points) > 1:
                    split = dict(chapter)
                    split_obj = objectives[len(objectives) // 2:]
                    split_pts = plot_points[len(plot_points) // 2:]
                    chapter["objectives"] = objectives[:len(objectives) // 2] or objectives[:1]
                    chapter["required_plot_points"] = plot_points[:len(plot_points) // 2] or plot_points[:1]
                    split["objectives"] = split_obj or objectives[-1:]
                    split["required_plot_points"] = split_pts or plot_points[-1:]
                    normalized.insert(idx + 1, split)
                idx += 1
            while len(normalized) < target_chapters:
                normalized.append(dict(normalized[-1]))
        if len(normalized) != target_chapters:
            return None
        for i, chapter in enumerate(normalized, start=1):
            chapter["chapter_number"] = i
        plan["chapters"] = normalized
        return plan

    async def _fix_plan_chapter_count(
        self,
        orchestrator,
        plan: Dict[str, Any],
        target_chapters: int
    ) -> Optional[Dict[str, Any]]:
        compact_plan = self._compact_plan_for_fix(plan)
        system_prompt = (
            "You are a JSON-only editor. Return a single valid JSON object.\n"
            "Adjust the chapters array to the exact target length.\n"
            "Do not add new characters or plot points; only split or merge existing items.\n"
            "No commentary, no code fences, no trailing text.\n"
        )
        user_prompt = (
            f"Fix the plan to have exactly {target_chapters} chapters.\n"
            "If too many chapters, merge adjacent chapters by combining objectives and plot points.\n"
            "If too few chapters, split chapters by distributing existing objectives/plot points.\n"
            "Keep chapter_number sequential starting at 1.\n"
            "Return only JSON.\n\n"
            "PLAN TO FIX:\n"
            f"{json.dumps(compact_plan, ensure_ascii=False)}\n"
        )
        budget = _planner_budget(orchestrator, base=2500, legacy_ceiling=2500)
        try:
            response = await orchestrator._make_api_call(
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0.1,
                max_tokens=budget,
                response_format={"type": "json_object"},
                model_role="planner",
            )
        except Exception:
            return None
        diag = _extract_response_diagnostics(response)
        content = diag["content"]
        if not content:
            logger.warning(
                "_fix_plan_chapter_count returned empty content. "
                "budget=%s finish_reason=%s usage=%s",
                budget,
                diag["finish_reason"],
                diag["usage"],
            )
            return None
        try:
            return json.loads(content)
        except Exception:
            extracted = self._extract_json_payload(content)
            if not extracted:
                return None
            try:
                return json.loads(extracted)
            except Exception:
                return None

    async def _repair_json_with_llm(
        self,
        orchestrator,
        raw_payload: str,
        target_chapters: int
    ) -> Optional[Dict[str, Any]]:
        if not raw_payload:
            return None
        system_prompt = (
            "You are a JSON repair tool. Return ONLY valid JSON.\n"
            "Fix syntax errors, missing commas, or invalid formatting.\n"
            "Do not add commentary or code fences.\n"
        )
        user_prompt = (
            "Repair the JSON below to be valid and complete.\n"
            f"- Must include exactly {target_chapters} chapters in the 'chapters' array.\n"
            "Return only JSON.\n\n"
            "BROKEN JSON:\n"
            f"{raw_payload}\n"
        )
        # Needs enough budget to output a full corrected plan, plus reasoning
        # headroom when the planner is gpt-5*/o-series.
        base_budget = max(2500, 900 + int(target_chapters) * 260)
        budget = _planner_budget(orchestrator, base=base_budget, legacy_ceiling=9000)
        try:
            response = await orchestrator._make_api_call(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=budget,
                response_format={"type": "json_object"},
                model_role="planner",
            )
        except Exception:
            return None
        diag = _extract_response_diagnostics(response)
        content = diag["content"]
        if not content:
            logger.warning(
                "_repair_json_with_llm returned empty content. "
                "budget=%s finish_reason=%s usage=%s",
                budget,
                diag["finish_reason"],
                diag["usage"],
            )
            return None
        try:
            return json.loads(content)
        except Exception:
            extracted = self._extract_json_payload(content)
            if not extracted:
                return None
            try:
                return json.loads(extracted)
            except Exception:
                return None

    async def _retry_generate_plan_strict(
        self,
        orchestrator,
        book_bible: str,
        references: Dict[str, str],
        target_chapters: int
    ) -> Optional[Dict[str, Any]]:
        def _trim(text: str, limit: int = 2000) -> str:
            if not text:
                return ""
            if len(text) <= limit:
                return text
            return text[:limit] + "..."

        def _ref_retry(key: str, *alt_keys: str) -> str:
            for k in (key, *alt_keys):
                val = references.get(k, "")
                if val:
                    return val
            return ""

        outline = _trim(_ref_retry("outline", "outline_reference"))
        plot_timeline = _trim(_ref_retry("plot_timeline", "plot-timeline", "plot_timeline_reference"))
        characters = _trim(_ref_retry("characters", "characters_reference"))
        world_building = _trim(_ref_retry("world_building", "world-building", "world_building_reference"))
        style_guide = _trim(_ref_retry("style_guide", "style-guide", "style_guide_reference"))
        entity_registry = _trim(_ref_retry("entity_registry", "entity-registry", "entity_registry_reference"))
        relationship_map = _trim(_ref_retry("relationship_map", "relationship-map", "relationship_map_reference"))
        book_bible_trimmed = _trim(book_bible, 4000)
        system_prompt = (
            "You are a JSON-only planner. Return a single valid JSON object.\n"
            "No commentary, no code fences, no trailing text.\n"
            "Strictly follow the schema. Ensure all commas are present.\n"
        )
        user_prompt = (
            "Regenerate the book plan as valid JSON only.\n"
            f"TARGET CHAPTER COUNT: {target_chapters}\n\n"
            "BOOK BIBLE:\n"
            f"{book_bible_trimmed}\n\n"
            "OUTLINE (if provided):\n"
            f"{outline}\n\n"
            "PLOT TIMELINE (if provided):\n"
            f"{plot_timeline}\n\n"
            "CHARACTERS (if provided):\n"
            f"{characters}\n\n"
            "WORLD BUILDING (if provided):\n"
            f"{world_building}\n\n"
            "STYLE GUIDE (if provided):\n"
            f"{style_guide}\n\n"
            "ENTITY REGISTRY (if provided):\n"
            f"{entity_registry}\n\n"
            "RELATIONSHIP MAP (if provided):\n"
            f"{relationship_map}\n\n"
            "JSON SCHEMA REQUIRED:\n"
            "{\n"
            '  "metadata": {\n'
            '    "created_at": "ISO8601",\n'
            '    "target_chapters": number,\n'
            '    "planning_principles": [string]\n'
            "  },\n"
            '  "global_constraints": {\n'
            '    "opening_rotation_rules": [string],\n'
            '    "ending_rotation_rules": [string],\n'
            '    "emotional_arc_rotation_rules": [string],\n'
            '    "pov_rotation_rules": [string]\n'
            "  },\n"
            '  "story_arcs": {\n'
            '    "primary": string,\n'
            '    "secondary": [string],\n'
            '    "themes": [string]\n'
            "  },\n"
            '  "chapters": [\n'
            "    {\n"
            '      "chapter_number": number,\n'
            '      "title": string,\n'
            '      "summary": string,\n'
            '      "objectives": [string],\n'
            '      "required_plot_points": [string],\n'
            '      "opening_type": string,\n'
            '      "ending_type": string,\n'
            '      "emotional_arc": string,\n'
            '      "focal_characters": [string],\n'
            '      "continuity_requirements": [string],\n'
            '      "pov_character": string,\n'
            '      "pov_type": string,\n'
            '      "pov_notes": string,\n'
            '      "transition_note": string,\n'
            '      "chapter_shape": "quiet_character_focus | confrontation_dialogue | aftermath_processing | relationship_deepening | world_building_routine | tension_escalation | revelation_and_fallout | journey_transition",\n'
            '      "prose_register": "plain | moderate | lyrical",\n'
            '      "new_developments": number (0-2),\n'
            '      "tension_level": "low | moderate | high"\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "Output constraints:\n"
            "- Keep summaries <= 140 characters.\n"
            "- Titles <= 80 characters.\n"
            "- Objectives: max 3 items, each <= 120 characters.\n"
            "- Required plot points: max 3 items, each <= 120 characters.\n"
            "- Continuity requirements: max 3 items.\n"
        )
        base_budget = max(2800, 1100 + int(target_chapters) * 260)
        budget = _planner_budget(orchestrator, base=base_budget, legacy_ceiling=9000)
        try:
            response = await orchestrator._make_api_call(
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0.1,
                max_tokens=budget,
                response_format={"type": "json_object"},
                model_role="planner",
            )
        except Exception:
            return None
        diag = _extract_response_diagnostics(response)
        content = diag["content"]
        if not content:
            logger.warning(
                "_retry_generate_plan_strict returned empty content. "
                "budget=%s finish_reason=%s usage=%s",
                budget,
                diag["finish_reason"],
                diag["usage"],
            )
            return None
        try:
            return json.loads(content)
        except Exception:
            extracted = self._extract_json_payload(content)
            if not extracted:
                return None
            try:
                return json.loads(extracted)
            except Exception:
                return None

    async def generate_plan(
        self,
        book_bible: str,
        references: Dict[str, str],
        target_chapters: int,
        model: str = "gpt-4.1"
    ) -> BookPlanResult:
        """Generate and save a master book plan using the LLM."""
        if not book_bible or len(book_bible.strip()) < 200:
            return BookPlanResult(success=False, error="Book bible is missing or too short to plan a full book.")
        if target_chapters <= 0:
            return BookPlanResult(success=False, error="Target chapters must be greater than zero.")

        try:
            from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig
        except Exception:
            from ..llm_orchestrator import LLMOrchestrator, RetryConfig

        orchestrator = LLMOrchestrator(model=model, retry_config=RetryConfig(max_retries=2))

        def _trim(text: str, limit: int) -> str:
            if not text:
                return ""
            if len(text) <= limit:
                return text
            return text[:limit] + "..."

        def _ref(key: str, *alt_keys: str) -> str:
            for k in (key, *alt_keys):
                val = references.get(k, "")
                if val:
                    return val
            return ""

        book_bible_trimmed = _trim(book_bible, 15000)
        outline = _trim(_ref("outline", "outline_reference"), 5000)
        plot_timeline = _trim(_ref("plot_timeline", "plot-timeline", "plot_timeline_reference"), 5000)
        characters = _trim(_ref("characters", "characters_reference"), 5000)
        world_building = _trim(_ref("world_building", "world-building", "world_building_reference"), 5000)
        style_guide = _trim(_ref("style_guide", "style-guide", "style_guide_reference"), 5000)
        themes = _trim(_ref("themes_and_motifs", "themes-and-motifs", "themes_and_motifs_reference"), 3000)
        target_audience = _trim(_ref("target_audience", "target-audience-profile", "target_audience_reference"), 2000)
        research_notes = _trim(_ref("research_notes", "research-notes", "research_notes_reference"), 3000)
        entity_registry = _trim(_ref("entity_registry", "entity-registry", "entity_registry_reference"), 3000)
        relationship_map = _trim(_ref("relationship_map", "relationship-map", "relationship_map_reference"), 3000)

        system_prompt = (
            "You are a senior story architect. Produce a master beat map for an entire novel.\n"
            "Output STRICT JSON only. No commentary, no code fences.\n"
            "Use ONLY the provided book bible and references; do not invent missing facts.\n"
            "Keep outputs compact to avoid truncation.\n"
        )

        user_prompt = (
            "Create a complete book plan for the novel described below.\n\n"
            f"TARGET CHAPTER COUNT: {target_chapters}\n\n"
            "BOOK BIBLE:\n"
            f"{book_bible_trimmed}\n\n"
            "OUTLINE (if provided):\n"
            f"{outline}\n\n"
            "PLOT TIMELINE (if provided):\n"
            f"{plot_timeline}\n\n"
            "CHARACTERS (if provided):\n"
            f"{characters}\n\n"
            "WORLD BUILDING (if provided):\n"
            f"{world_building}\n\n"
            "STYLE GUIDE (if provided):\n"
            f"{style_guide}\n\n"
            "THEMES AND MOTIFS (if provided):\n"
            f"{themes}\n\n"
            "TARGET AUDIENCE (if provided):\n"
            f"{target_audience}\n\n"
            "RESEARCH NOTES (if provided):\n"
            f"{research_notes}\n\n"
            "ENTITY REGISTRY (if provided):\n"
            f"{entity_registry}\n\n"
            "RELATIONSHIP MAP (if provided):\n"
            f"{relationship_map}\n\n"
            "JSON SCHEMA REQUIRED:\n"
            "{\n"
            '  "metadata": {\n'
            '    "created_at": "ISO8601",\n'
            '    "target_chapters": number,\n'
            '    "planning_principles": [string]\n'
            "  },\n"
            '  "global_constraints": {\n'
            '    "opening_rotation_rules": [string],\n'
            '    "ending_rotation_rules": [string],\n'
            '    "emotional_arc_rotation_rules": [string],\n'
            '    "pov_rotation_rules": [string]\n'
            "  },\n"
            '  "story_arcs": {\n'
            '    "primary": string,\n'
            '    "secondary": [string],\n'
            '    "themes": [string]\n'
            "  },\n"
            '  "chapters": [\n'
            "    {\n"
            '      "chapter_number": number,\n'
            '      "title": string,\n'
            '      "summary": string,\n'
            '      "objectives": [string],\n'
            '      "required_plot_points": [string],\n'
            '      "opening_type": string,\n'
            '      "ending_type": string,\n'
            '      "emotional_arc": string,\n'
            '      "focal_characters": [string],\n'
            '      "continuity_requirements": [string],\n'
            '      "pov_character": string,\n'
            '      "pov_type": string,\n'
            '      "pov_notes": string,\n'
            '      "transition_note": string,\n'
            '      "chapter_shape": "quiet_character_focus | confrontation_dialogue | aftermath_processing | relationship_deepening | world_building_routine | tension_escalation | revelation_and_fallout | journey_transition",\n'
            '      "prose_register": "plain | moderate | lyrical",\n'
            '      "new_developments": number (0-2),\n'
            '      "tension_level": "low | moderate | high",\n'
            '      "chapter_tier": "setpiece | development | connective",\n'
            '      "thematic_move": "introduce | complicate | invert | deepen | stake | foreclose | reaffirm | answer | coda",\n'
            '      "thematic_move_note": "one-sentence operational description of what this chapter is doing TO the central question",\n'
            '      "promises_planted": [string],\n'
            '      "promises_paid": [string],\n'
            '      "character_arc_beats": [{"character": "Name", "arc_position": "initial | shift | deepening | crisis | resolution", "emotional_register": "description of emotional state", "motivation": "why this shift happens now"}]\n'
            "    }\n"
            "  ],\n"
            '  "promises_ledger": [\n'
            "    {\n"
            '      "promise_id": "p1",\n'
            '      "label": "short human-readable label",\n'
            '      "description": "what was set up and what kind of payoff the reader is owed",\n'
            '      "planted_chapter": number,\n'
            '      "expected_payoff_window": [number, number],\n'
            '      "promise_type": "object | place | relationship | mystery | obligation | threat | rule",\n'
            '      "weight": "minor | major | central"\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "Rules:\n"
            "- Provide exactly the target number of chapters.\n"
            "- Objectives must be concrete and non-repeating.\n"
            "- Opening and ending types must rotate; NEVER repeat the same type in adjacent chapters.\n"
            "- Emotional arcs must vary across the book.\n"
            "- POV should be specified per chapter (character + type) and transition notes included.\n"
            "- STRUCTURAL VARIETY IS CRITICAL: plan different chapter shapes. Include quiet character-focused chapters between intense ones.\n"
            "- At least 1 in 3 chapters should be a 'quiet' chapter (character relationships, processing events, world-building, reflection).\n"
            "- Tension must rise and fall: do not plan 3+ high-tension chapters in a row.\n"
            "- Plan prose_register per chapter: alternate between 'plain' (simple functional prose), 'moderate' (balanced), and 'lyrical' (rich imagery).\n"
            "- Plan new_developments per chapter: most chapters should have 0-1 major new developments. Let existing threads deepen.\n"
            "- CHARACTER ARC TRACKING: For each focal character in each chapter, specify their arc_position "
            "and emotional_register. Characters MUST NOT shift emotional register between chapters without "
            "explicit narrative motivation. If a character is vulnerable in one chapter, they cannot be "
            "threatening in the next without a scene showing why they reverted.\n"
            "- FINAL CHAPTER RULES:\n"
            "  - The final chapter MUST be at least 50% interpersonal (protagonist interacting with other characters).\n"
            "  - Maximum 2 paragraphs of solo reflection. The rest must be action or dialogue.\n"
            "  - End on forward motion or human connection, NOT on a character alone thinking.\n"
            "  - Plan 2-3 chapters of resolution after the climax.\n"
            "- POST-CLIMAX BUDGET: After the climax chapter, plan 2-3 chapters of resolution. "
            "These should be full-length chapters, action/dialogue-heavy, and must NOT recap the climax events. "
            "Resolution chapters deserve the same depth as the rest of the book — the reader has "
            "invested time, so give them a satisfying landing with enough room for emotional payoff.\n"
            "  - The final chapter's ending_type should be 'scene_completed_cleanly' or 'dialogue_trailing_off', NOT 'character_alone_reflecting'.\n"
            "\n"
            "CHAPTER-TIER RULES (Proposal 2 — Setpiece Tiering):\n"
            "- Every chapter MUST be tagged `chapter_tier` as one of:\n"
            "  * setpiece — climax, major reveal, decisive confrontation, emotional turning point, \n"
            "    or other moment the entire book has been building toward. Setpieces are non-negotiable\n"
            "    must-execute scenes that deserve maximum craft attention. Most books have 3-6 setpieces.\n"
            "  * development — the engine chapters that escalate, complicate, deepen relationships,\n"
            "    or introduce significant new pressure. The book's middle is mostly developments.\n"
            "  * connective — quieter chapters that bridge developments, process events, give the\n"
            "    reader time to breathe, or move characters into position. Connectives are the\n"
            "    valleys that make the peaks visible.\n"
            "- Distribution: A book of N chapters should typically have ~15-25% setpieces, ~50-65%\n"
            "  developments, ~15-30% connectives. Two consecutive setpiece chapters is a structural\n"
            "  red flag (the second will read as anticlimax).\n"
            "- The opening chapter is rarely a setpiece (the reader is still buying in). The climax\n"
            "  chapter MUST be a setpiece. The final chapter may be setpiece OR connective depending\n"
            "  on whether the climax happens in it or before it.\n"
            "\n"
            "THEMATIC-MOVE RULES (Proposal 5 — Per-Chapter Thematic Move):\n"
            "- Every chapter MUST be tagged `thematic_move` from the allowed vocabulary above. The\n"
            "  thematic_move names what the chapter is DOING to the book's central question — not\n"
            "  what the chapter is about, but the chapter's MOVE in the larger thematic argument.\n"
            "- No two adjacent chapters may share the same thematic_move.\n"
            "- Most chapters should NOT be `answer` — that move is reserved for 1-2 chapters near\n"
            "  the end where the book's position lands. `coda` is for the final 1-2 chapters of\n"
            "  resonance after the answer.\n"
            "- `thematic_move_note` is a one-sentence operational description (e.g., 'Complicates\n"
            "  the question by showing that David's silence at the funeral cost him his sons'\n"
            "  willingness to stay in touch this winter.'). Generic notes ('explores the theme of\n"
            "  loss') are not acceptable.\n"
            "\n"
            "PROMISES-LEDGER RULES (Proposal 4 — Promises and Payoffs):\n"
            "- Every setup the book makes (an object the protagonist notices, a question someone\n"
            "  asks, a debt referenced, a knock at a door, a location seen but not entered, a rule\n"
            "  established about the world, a character introduced who carries weight) creates a\n"
            "  PROMISE the reader expects to see paid off. Unpaid promises rot the ending.\n"
            "- Use the per-chapter `promises_planted` and `promises_paid` arrays plus the top-level\n"
            "  `promises_ledger` to track these. Each promise gets a unique `promise_id` (\"p1\",\n"
            "  \"p2\", \"p3\", ...) used as the reference in both planted/paid arrays.\n"
            "- Every promise that is `weight: major` or `weight: central` MUST be paid by the\n"
            "  expected_payoff_window or earlier. Minor promises may be left unpaid only if their\n"
            "  irrelevance is itself meaningful (e.g., a small thing the protagonist learns to let go).\n"
            "- 8-15 promises across the book is a healthy range. Fewer means the book under-promises\n"
            "  and feels slack. More means the book is over-promising and will feel busy.\n"
            "Output constraints:\n"
            "- Keep summaries <= 200 characters.\n"
            "- Titles <= 80 characters.\n"
            "- Objectives: max 4 items, each <= 150 characters.\n"
            "- Required plot points: max 3 items, each <= 120 characters.\n"
            "- Continuity requirements: max 3 items.\n"
            "- thematic_move_note: <= 200 characters.\n"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # Plan size grows ~linearly with target chapters. Reasoning planners
        # (gpt-5*) eat into the same budget for invisible reasoning tokens, so
        # _planner_budget inflates the cap when the planner is reasoning-class.
        base_budget = max(5000, 2000 + int(target_chapters) * 400)
        budget = _planner_budget(orchestrator, base=base_budget, legacy_ceiling=16000)
        try:
            response = await orchestrator._make_api_call(
                messages=messages,
                temperature=0.2,
                max_tokens=budget,
                response_format={"type": "json_object"},
                model_role="planner",
            )
        except Exception as e:
            return BookPlanResult(success=False, error=f"Book plan generation failed: {e}")

        diag = _extract_response_diagnostics(response)
        content = diag["content"]
        retry_budget: Optional[int] = None
        if not content:
            try:
                planner_model = orchestrator._resolve_model("planner")
                model_cap = orchestrator._get_model_max_output_tokens(planner_model)
            except Exception:
                planner_model = "<unknown>"
                model_cap = 32000
            logger.warning(
                "Book plan call returned empty content; retrying once with "
                "doubled budget. model=%s budget=%s finish_reason=%s usage=%s",
                planner_model,
                budget,
                diag["finish_reason"],
                diag["usage"],
            )
            retry_budget = min(budget * 2, model_cap)
            if retry_budget > budget:
                try:
                    response = await orchestrator._make_api_call(
                        messages=messages,
                        temperature=0.2,
                        max_tokens=retry_budget,
                        response_format={"type": "json_object"},
                        model_role="planner",
                    )
                    diag = _extract_response_diagnostics(response)
                    content = diag["content"]
                    if content:
                        logger.info(
                            "Book plan retry succeeded with budget=%s "
                            "(usage=%s).",
                            retry_budget,
                            diag["usage"],
                        )
                except Exception as e:
                    return BookPlanResult(
                        success=False,
                        error=f"Book plan generation retry failed: {e}",
                    )
        if not content:
            return BookPlanResult(
                success=False,
                error=(
                    "Book plan generation returned empty content "
                    f"(model={planner_model if 'planner_model' in locals() else '<unknown>'}, "
                    f"finish_reason={diag['finish_reason']}, usage={diag['usage']}, "
                    f"budget={budget}, retry_budget={retry_budget})."
                ),
            )

        try:
            plan = json.loads(content)
        except Exception:
            extracted = self._extract_json_payload(content)
            if not extracted:
                return BookPlanResult(success=False, error="Failed to parse book plan JSON: no JSON object found.")
            try:
                plan = json.loads(extracted)
            except Exception:
                repaired = self._repair_json_payload(extracted)
                if not repaired:
                    return BookPlanResult(success=False, error="Failed to parse book plan JSON after repair attempt.")
                try:
                    plan = json.loads(repaired)
                except Exception as e:
                    repaired_plan = await self._repair_json_with_llm(orchestrator, extracted, target_chapters)
                    if repaired_plan:
                        plan = repaired_plan
                    else:
                        retry_plan = await self._retry_generate_plan_strict(
                            orchestrator=orchestrator,
                            book_bible=book_bible,
                            references=references,
                            target_chapters=target_chapters
                        )
                        if retry_plan:
                            plan = retry_plan
                        else:
                            return BookPlanResult(success=False, error=f"Failed to parse book plan JSON: {e}")

        # Basic validation
        chapters = plan.get("chapters", [])
        if not isinstance(chapters, list) or len(chapters) != target_chapters:
            fixed_plan = await self._fix_plan_chapter_count(orchestrator, plan, target_chapters)
            if fixed_plan and isinstance(fixed_plan.get("chapters"), list) and len(fixed_plan["chapters"]) == target_chapters:
                plan = fixed_plan
            else:
                normalized = self._normalize_chapter_count_local(plan, target_chapters)
                if normalized and isinstance(normalized.get("chapters"), list) and len(normalized["chapters"]) == target_chapters:
                    plan = normalized
                else:
                    return BookPlanResult(success=False, error="Book plan does not include the required number of chapters.")

        plan.setdefault("metadata", {})
        plan["metadata"]["created_at"] = datetime.utcnow().isoformat()
        plan["metadata"]["target_chapters"] = target_chapters
        try:
            plan["metadata"]["source_hashes"] = self.compute_source_hashes(book_bible, references)
        except Exception:
            pass

        # Proposals 2, 4, 5 — make sure the new fields exist and persist the
        # initial promises ledger so the chapter pipeline can read it.
        try:
            plan = self._backfill_plan_extensions(plan)
        except Exception as backfill_err:  # pragma: no cover - defensive
            logger.warning("Failed to backfill plan extensions: %s", backfill_err)

        self.save_plan(plan)
        try:
            self.save_promises_ledger(plan)
        except Exception as ledger_err:  # pragma: no cover - defensive
            logger.warning("Failed to persist initial promises ledger: %s", ledger_err)

        return BookPlanResult(success=True, plan=plan)
