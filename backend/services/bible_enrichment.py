#!/usr/bin/env python3
"""
Bible Enrichment Service

Powers the optional "deepen your book bible" intake flow. The user is offered
five strongly-encouraged questions; for each one they may either:

  1. Answer in their own words.
  2. Skip and let the system auto-fill, using the bible (and any already-
     generated reference docs) plus a genre-anchored exemplar pack to ground
     the answer in this specific book.

Every auto-fill answer is then run through an anti-cliché evaluator. If the
evaluator returns GENERIC, the question is regenerated ONCE with the sharper
instruction the evaluator produced. The final result is persisted with full
provenance (source: 'user' | 'auto'; attempts; reasons; timestamps).

The enriched answers are written into:

  - The serialized result returned by ``EnrichmentRunner.run`` — caller stores
    in Firestore under ``project.bible_enrichment``.
  - An "Author Intent" appendix that downstream reference generation, the book
    plan, and the director brief read as part of the bible payload (via
    ``EnrichmentRunner.compose_appendix``).

The service is deliberately framework-light: callers wire it into FastAPI
routes (production) or invoke it directly from local test harnesses.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Question registry
# ---------------------------------------------------------------------------

QUESTION_IDS: Tuple[str, ...] = (
    "reader_feeling",
    "central_question",
    "protagonist_lie",
    "worldview_change",
    "clear_scenes",
)

QUESTION_ORDER: Dict[str, int] = {qid: idx for idx, qid in enumerate(QUESTION_IDS)}


@dataclass
class QuestionDefinition:
    """Loaded from each ``backend/prompts/bible-enrichment/{qid}.yaml``."""

    question_id: str
    question_text: str
    short_label: str
    system_prompt: str
    user_prompt_template: str
    model: str
    temperature: float
    max_tokens: int


@dataclass
class EnrichmentAnswer:
    """One persisted answer, with provenance."""

    question_id: str
    question_text: str
    short_label: str
    answer: str
    source: str  # "user" | "auto"
    attempts: int  # 1 = first try; 2 = anti-cliché regenerate
    anti_cliche_verdict: Optional[str] = None  # "SPECIFIC" | "GENERIC" | None
    anti_cliche_reason: Optional[str] = None
    anti_cliche_sharper_instruction: Optional[str] = None
    model: Optional[str] = None
    elapsed_ms: int = 0
    generated_at: Optional[str] = None
    user_edited: bool = False  # True if the user later edited an auto-filled answer

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EnrichmentResult:
    """Full output of an enrichment run for one project."""

    project_id: str
    genre: str
    answers: Dict[str, EnrichmentAnswer] = field(default_factory=dict)
    completed_at: Optional[str] = None
    schema_version: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "genre": self.genre,
            "schema_version": self.schema_version,
            "completed_at": self.completed_at,
            "answers": {qid: ans.to_dict() for qid, ans in self.answers.items()},
        }


# ---------------------------------------------------------------------------
# Exemplar registry
# ---------------------------------------------------------------------------


@dataclass
class ExemplarPack:
    """Loaded from each ``backend/prompts/bible-enrichment/exemplars/{slug}.yaml``."""

    slug: str
    matches: List[str]
    per_question: Dict[str, Dict[str, Any]]

    def for_question(self, question_id: str) -> Dict[str, Any]:
        return self.per_question.get(question_id, {})


def _normalize_genre(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip().lower())


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


class EnrichmentPromptRegistry:
    """Loads question prompts, the anti-cliché evaluator, and exemplar packs."""

    def __init__(self, prompts_dir: Optional[Path] = None) -> None:
        if prompts_dir is None:
            prompts_dir = Path(__file__).resolve().parent.parent / "prompts" / "bible-enrichment"
        self.prompts_dir = prompts_dir
        self._questions: Dict[str, QuestionDefinition] = {}
        self._anti_cliche: Optional[QuestionDefinition] = None
        self._exemplars: List[ExemplarPack] = []
        self._default_exemplar: Optional[ExemplarPack] = None
        self._load()

    def _load(self) -> None:
        for qid in QUESTION_IDS:
            path = self.prompts_dir / f"{qid}.yaml"
            if not path.exists():
                raise FileNotFoundError(
                    f"Bible enrichment prompt missing: {path}. "
                    "Did the prompt YAML get committed?"
                )
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            mc = data.get("model_config") or {}
            self._questions[qid] = QuestionDefinition(
                question_id=qid,
                question_text=str(data.get("question_text") or "").strip(),
                short_label=str(data.get("short_label") or "").strip(),
                system_prompt=str(data.get("system_prompt") or "").strip(),
                user_prompt_template=str(data.get("user_prompt_template") or "").strip(),
                model=str(mc.get("model") or "gpt-5.5"),
                temperature=float(mc.get("temperature", 0.7)),
                max_tokens=int(mc.get("max_tokens", 600)),
            )

        anti_path = self.prompts_dir / "anti_cliche.yaml"
        if not anti_path.exists():
            raise FileNotFoundError(
                f"Bible enrichment anti-cliché evaluator missing: {anti_path}"
            )
        anti_data = yaml.safe_load(anti_path.read_text(encoding="utf-8")) or {}
        anti_mc = anti_data.get("model_config") or {}
        self._anti_cliche = QuestionDefinition(
            question_id="anti_cliche",
            question_text="",
            short_label="",
            system_prompt=str(anti_data.get("system_prompt") or "").strip(),
            user_prompt_template=str(anti_data.get("user_prompt_template") or "").strip(),
            model=str(anti_mc.get("model") or "gpt-5.5"),
            temperature=float(anti_mc.get("temperature", 0.1)),
            max_tokens=int(anti_mc.get("max_tokens", 400)),
        )

        exemplars_dir = self.prompts_dir / "exemplars"
        if not exemplars_dir.exists():
            raise FileNotFoundError(
                f"Bible enrichment exemplars dir missing: {exemplars_dir}"
            )
        for path in sorted(exemplars_dir.glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            slug = str(data.get("genre") or path.stem).strip().lower()
            matches = [
                _normalize_genre(m) for m in (data.get("matches") or []) if m
            ]
            per_question = {
                qid: {
                    "generic_examples": data.get(qid, {}).get("generic_examples", []) or [],
                    "specific_examples": data.get(qid, {}).get("specific_examples", []) or [],
                    "sharper_instructions": data.get(qid, {}).get("sharper_instructions", []) or [],
                }
                for qid in QUESTION_IDS
            }
            pack = ExemplarPack(slug=slug, matches=matches, per_question=per_question)
            self._exemplars.append(pack)
            if slug == "default":
                self._default_exemplar = pack

        if self._default_exemplar is None:
            raise FileNotFoundError(
                "Bible enrichment exemplars must include a default.yaml fallback pack."
            )

    @property
    def questions(self) -> Dict[str, QuestionDefinition]:
        return dict(self._questions)

    def get_question(self, question_id: str) -> QuestionDefinition:
        if question_id not in self._questions:
            raise KeyError(f"Unknown bible-enrichment question id: {question_id}")
        return self._questions[question_id]

    @property
    def anti_cliche(self) -> QuestionDefinition:
        assert self._anti_cliche is not None
        return self._anti_cliche

    def resolve_exemplar(self, genre: str) -> ExemplarPack:
        norm = _normalize_genre(genre)
        if not norm:
            return self._default_exemplar  # type: ignore[return-value]
        # Exact match first (slug or any of the `matches` aliases).
        for pack in self._exemplars:
            if pack.slug == norm or norm in pack.matches:
                return pack
        # Substring match — handles "literary fiction" → "literary".
        for pack in self._exemplars:
            for alias in [pack.slug, *pack.matches]:
                if alias and (alias in norm or norm in alias):
                    return pack
        return self._default_exemplar  # type: ignore[return-value]


def _format_exemplars_for_question(pack: ExemplarPack, question_id: str) -> str:
    """Render the genre's worked examples as a single text block for the prompt."""
    block = pack.for_question(question_id)
    generic = block.get("generic_examples") or []
    specific = block.get("specific_examples") or []
    parts: List[str] = []
    if generic:
        parts.append("GENERIC (do not produce this style):")
        for ex in generic:
            parts.append(f"- {ex}")
    if specific:
        parts.append("")
        parts.append("SPECIFIC (this is the bar to hit):")
        for ex in specific:
            parts.append(f"- {ex}")
    return "\n".join(parts) if parts else "(no exemplars available)"


def _format_prior_references(prior_references: Optional[Dict[str, str]]) -> str:
    """Format already-generated reference markdown into a trimmed block."""
    if not prior_references:
        return "(no reference documents have been generated yet)"
    parts: List[str] = []
    # Limit to the most useful references for enrichment — skip director-guide
    # and entity-registry which are mechanical.
    preferred_order = (
        "characters",
        "world-building",
        "outline",
        "themes-and-motifs",
        "style-guide",
        "plot-timeline",
        "relationship-map",
        "target-audience-profile",
    )
    seen = set()
    for key in preferred_order:
        content = prior_references.get(key)
        if content and isinstance(content, str):
            seen.add(key)
            trimmed = content[:1500]
            label = key.replace("-", " ").title()
            parts.append(f"--- {label} ---\n{trimmed}")
    if not parts:
        return "(no reference documents have been generated yet)"
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class EnrichmentRunner:
    """Orchestrates auto-fill + anti-cliché evaluation for one project."""

    def __init__(
        self,
        registry: Optional[EnrichmentPromptRegistry] = None,
        llm_orchestrator: Optional[Any] = None,
    ) -> None:
        self.registry = registry or EnrichmentPromptRegistry()
        self.llm_orchestrator = llm_orchestrator

    def _get_orchestrator(self):
        if self.llm_orchestrator is not None:
            return self.llm_orchestrator
        # Lazy-import to avoid circulars and let local test harnesses skip
        # unless they actually need a real LLM.
        try:
            from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig
        except Exception:
            from ..auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig  # type: ignore
        self.llm_orchestrator = LLMOrchestrator(retry_config=RetryConfig(max_retries=2))
        return self.llm_orchestrator

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _extract_text(response: Any) -> str:
        if response is None:
            return ""
        if hasattr(response, "output_text"):
            t = getattr(response, "output_text", "") or ""
            if t:
                return t
        try:
            choices = getattr(response, "choices", None)
            if choices:
                msg = getattr(choices[0], "message", None)
                if msg is not None:
                    return getattr(msg, "content", "") or ""
        except Exception:
            return ""
        return ""

    async def _call_question(
        self,
        question: QuestionDefinition,
        bible: str,
        prior_references_block: str,
        exemplar_block: str,
        genre: str,
        extra_instruction: str = "",
    ) -> str:
        orchestrator = self._get_orchestrator()
        user_prompt = question.user_prompt_template.format(
            genre=genre or "Fiction",
            exemplars=exemplar_block,
            prior_references=prior_references_block,
            bible=(bible or "")[:12000],
        )
        if extra_instruction:
            user_prompt += "\n\n" + (
                "RETRY INSTRUCTION FROM EDITOR:\n"
                f"{extra_instruction}\n"
                "Apply this instruction. Do not explain it. Just produce a more "
                "specific answer."
            )

        messages = [
            {"role": "system", "content": question.system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            response = await orchestrator._make_api_call(  # noqa: SLF001
                messages=messages,
                temperature=question.temperature,
                max_tokens=question.max_tokens,
                model_override=question.model,
                reasoning_effort="low",
            )
        except Exception as exc:
            logger.error(
                "Bible enrichment LLM call failed for %s: %s",
                question.question_id,
                exc,
            )
            raise
        text = self._extract_text(response).strip()
        if not text:
            logger.warning(
                "Bible enrichment LLM returned EMPTY content for %s (model=%s, "
                "max_tokens=%s). Likely cause: reasoning model consumed entire "
                "token budget on internal reasoning.",
                question.question_id, question.model, question.max_tokens,
            )
        return text

    async def _evaluate_anti_cliche(
        self,
        question: QuestionDefinition,
        generated_answer: str,
        bible: str,
    ) -> Dict[str, str]:
        evaluator = self.registry.anti_cliche
        orchestrator = self._get_orchestrator()
        user_prompt = evaluator.user_prompt_template.format(
            question_text=question.question_text,
            generated_answer=generated_answer,
            bible=(bible or "")[:6000],
        )
        messages = [
            {"role": "system", "content": evaluator.system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            response = await orchestrator._make_api_call(  # noqa: SLF001
                messages=messages,
                temperature=evaluator.temperature,
                max_tokens=evaluator.max_tokens,
                model_override=evaluator.model,
                response_format={"type": "json_object"},
                reasoning_effort="low",
            )
        except Exception as exc:
            logger.warning(
                "Bible enrichment anti-cliché evaluator failed for %s: %s. "
                "Treating answer as SPECIFIC to avoid blocking the user.",
                question.question_id,
                exc,
            )
            return {
                "verdict": "SPECIFIC",
                "reason": f"evaluator_unavailable: {exc}",
                "sharper_instruction": "",
            }

        raw = self._extract_text(response).strip()
        if not raw:
            logger.warning(
                "Anti-cliché evaluator returned EMPTY content for %s (model=%s, "
                "max_tokens=%s). Treating answer as SPECIFIC. Likely cause: "
                "reasoning model consumed entire token budget on internal reasoning.",
                question.question_id, evaluator.model, evaluator.max_tokens,
            )
            return {
                "verdict": "SPECIFIC",
                "reason": "evaluator_empty_response",
                "sharper_instruction": "",
            }
        parse_recovered = True
        try:
            data = json.loads(raw)
        except Exception:
            parse_recovered = False
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    data = json.loads(raw[start : end + 1])
                    parse_recovered = True
                except Exception:
                    data = {}
            else:
                data = {}
        if not parse_recovered:
            snippet = (raw or "")[:300].replace("\n", " ")
            logger.warning(
                "Anti-cliché evaluator returned non-JSON for %s. Defaulting to "
                "SPECIFIC. Snippet: %r",
                question.question_id, snippet,
            )
        if not isinstance(data, dict):
            logger.warning(
                "Anti-cliché evaluator returned JSON of type %s for %s (expected "
                "object). Defaulting to SPECIFIC.",
                type(data).__name__, question.question_id,
            )
            data = {}
        verdict = str(data.get("verdict") or "").upper()
        if verdict not in ("SPECIFIC", "GENERIC"):
            if verdict:
                logger.warning(
                    "Anti-cliché evaluator returned unexpected verdict '%s' for %s "
                    "(expected SPECIFIC or GENERIC). Defaulting to SPECIFIC.",
                    verdict, question.question_id,
                )
            verdict = "SPECIFIC"
        return {
            "verdict": verdict,
            "reason": str(data.get("reason") or "")[:500],
            "sharper_instruction": str(data.get("sharper_instruction") or "")[:500],
        }

    async def autofill_question(
        self,
        question_id: str,
        bible: str,
        genre: str,
        prior_references: Optional[Dict[str, str]] = None,
    ) -> EnrichmentAnswer:
        """Generate a single auto-filled answer with one anti-cliché regeneration loop."""
        question = self.registry.get_question(question_id)
        pack = self.registry.resolve_exemplar(genre)
        exemplar_block = _format_exemplars_for_question(pack, question_id)
        prior_block = _format_prior_references(prior_references)

        started = time.time()
        attempt = 1
        first = await self._call_question(
            question=question,
            bible=bible,
            prior_references_block=prior_block,
            exemplar_block=exemplar_block,
            genre=genre,
        )
        verdict_payload = await self._evaluate_anti_cliche(question, first, bible)
        chosen_answer = first
        if verdict_payload["verdict"] == "GENERIC":
            sharper = verdict_payload.get("sharper_instruction") or ""
            if not sharper:
                # If the evaluator did not produce a sharper instruction, fall
                # back to the genre's pre-canned sharper guidance.
                generic_specifics = pack.for_question(question_id)
                instructions = generic_specifics.get("sharper_instructions") or []
                sharper = instructions[0] if instructions else (
                    "Be more concrete: cite at least one specific name, place, "
                    "or event from the bible."
                )
            attempt = 2
            try:
                second = await self._call_question(
                    question=question,
                    bible=bible,
                    prior_references_block=prior_block,
                    exemplar_block=exemplar_block,
                    genre=genre,
                    extra_instruction=sharper,
                )
                if second:
                    chosen_answer = second
            except Exception as exc:
                logger.warning(
                    "Bible enrichment regeneration failed for %s: %s. "
                    "Keeping first answer.",
                    question_id,
                    exc,
                )

        elapsed_ms = int((time.time() - started) * 1000)
        return EnrichmentAnswer(
            question_id=question_id,
            question_text=question.question_text,
            short_label=question.short_label,
            answer=chosen_answer.strip(),
            source="auto",
            attempts=attempt,
            anti_cliche_verdict=verdict_payload.get("verdict"),
            anti_cliche_reason=verdict_payload.get("reason"),
            anti_cliche_sharper_instruction=verdict_payload.get("sharper_instruction") or None,
            model=question.model,
            elapsed_ms=elapsed_ms,
            generated_at=self._now_iso(),
        )

    async def run(
        self,
        project_id: str,
        bible: str,
        genre: str,
        user_answers: Optional[Dict[str, str]] = None,
        skipped: Optional[List[str]] = None,
        prior_references: Optional[Dict[str, str]] = None,
    ) -> EnrichmentResult:
        """Produce a full enrichment result.

        Args:
            project_id: opaque project id (not validated here).
            bible: full book bible markdown.
            genre: free-form genre string from the bible / project metadata.
            user_answers: question_id → user-provided answer text. Trumps auto-fill.
            skipped: list of question_ids the user explicitly skipped (treated as auto).
            prior_references: dict of already-generated reference markdown
                keyed by reference type (e.g. "characters", "themes-and-motifs").
        """
        user_answers = user_answers or {}
        skipped_set = set(skipped or [])
        auto_targets: List[str] = []
        result = EnrichmentResult(project_id=project_id, genre=genre)

        for qid in QUESTION_IDS:
            question = self.registry.get_question(qid)
            user_text = (user_answers.get(qid) or "").strip()
            if user_text:
                result.answers[qid] = EnrichmentAnswer(
                    question_id=qid,
                    question_text=question.question_text,
                    short_label=question.short_label,
                    answer=user_text,
                    source="user",
                    attempts=0,
                    generated_at=self._now_iso(),
                )
                continue
            if qid in skipped_set or not user_text:
                auto_targets.append(qid)

        if auto_targets:
            tasks = [
                self.autofill_question(
                    question_id=qid,
                    bible=bible,
                    genre=genre,
                    prior_references=prior_references,
                )
                for qid in auto_targets
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for qid, value in zip(auto_targets, results):
                if isinstance(value, Exception):
                    question = self.registry.get_question(qid)
                    logger.error(
                        "Bible enrichment auto-fill failed for %s: %s",
                        qid,
                        value,
                    )
                    result.answers[qid] = EnrichmentAnswer(
                        question_id=qid,
                        question_text=question.question_text,
                        short_label=question.short_label,
                        answer="",
                        source="auto",
                        attempts=0,
                        anti_cliche_reason=f"autofill_failed: {value}",
                        generated_at=self._now_iso(),
                    )
                else:
                    result.answers[qid] = value

        result.completed_at = self._now_iso()
        return result

    @staticmethod
    def compose_appendix(result: EnrichmentResult) -> str:
        """Render the enriched answers as an "Author Intent" appendix.

        This appendix is appended to the book bible content that downstream
        layers (reference generation, book plan, director brief) consume.
        It is voiced as if the author wrote it, and notes provenance only in
        a small footer.
        """
        if not result.answers:
            return ""

        lines: List[str] = []
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("# Author Intent (Bible Enrichment)")
        lines.append("")
        lines.append(
            "The author has answered the following questions about the book. "
            "Treat these answers as load-bearing intent — the reference layer, "
            "book plan, and chapter planning must honor them."
        )
        lines.append("")

        ordered = sorted(
            result.answers.values(),
            key=lambda a: QUESTION_ORDER.get(a.question_id, 99),
        )
        for ans in ordered:
            if not ans.answer:
                continue
            heading = ans.short_label or ans.question_text or ans.question_id
            lines.append(f"## {heading}")
            lines.append("")
            lines.append(ans.answer.strip())
            lines.append("")

        provenance = {
            ans.question_id: {
                "source": ans.source,
                "attempts": ans.attempts,
                "anti_cliche_verdict": ans.anti_cliche_verdict,
                "user_edited": ans.user_edited,
            }
            for ans in ordered
        }
        lines.append("---")
        lines.append("")
        lines.append(
            "_Bible enrichment provenance (machine-readable; for editorial review):_"
        )
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(provenance, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
        return "\n".join(lines)


def merge_bible_with_enrichment(bible: str, result: Optional[EnrichmentResult]) -> str:
    """Append the Author Intent appendix to a book bible if enrichment exists.

    Idempotent: if the appendix is already present in the bible, the original
    bible is returned unchanged. This lets callers eagerly merge without
    worrying about double-stamping.
    """
    if not result or not result.answers:
        return bible or ""
    appendix = EnrichmentRunner.compose_appendix(result)
    if not appendix.strip():
        return bible or ""
    body = bible or ""
    marker = "# Author Intent (Bible Enrichment)"
    if marker in body:
        return body
    return f"{body.rstrip()}\n\n{appendix}".strip() + "\n"


def enrichment_result_from_dict(payload: Dict[str, Any]) -> EnrichmentResult:
    """Hydrate an EnrichmentResult from a serialized dict (e.g., Firestore)."""
    if not isinstance(payload, dict):
        raise ValueError("enrichment payload must be a dict")
    answers_payload = payload.get("answers") or {}
    answers: Dict[str, EnrichmentAnswer] = {}
    for qid, raw in answers_payload.items():
        if not isinstance(raw, dict):
            continue
        answers[qid] = EnrichmentAnswer(
            question_id=str(raw.get("question_id") or qid),
            question_text=str(raw.get("question_text") or ""),
            short_label=str(raw.get("short_label") or ""),
            answer=str(raw.get("answer") or ""),
            source=str(raw.get("source") or "auto"),
            attempts=int(raw.get("attempts") or 0),
            anti_cliche_verdict=raw.get("anti_cliche_verdict"),
            anti_cliche_reason=raw.get("anti_cliche_reason"),
            anti_cliche_sharper_instruction=raw.get("anti_cliche_sharper_instruction"),
            model=raw.get("model"),
            elapsed_ms=int(raw.get("elapsed_ms") or 0),
            generated_at=raw.get("generated_at"),
            user_edited=bool(raw.get("user_edited", False)),
        )
    return EnrichmentResult(
        project_id=str(payload.get("project_id") or ""),
        genre=str(payload.get("genre") or ""),
        answers=answers,
        completed_at=payload.get("completed_at"),
        schema_version=int(payload.get("schema_version", 1)),
    )
