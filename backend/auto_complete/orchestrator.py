#!/usr/bin/env python3
"""
Auto-Complete Book Orchestrator - FastAPI Backend Version
Manages sequential chapter generation with quality gates and context continuity.
"""

import json
import sys
import importlib.util
import logging
import uuid
import asyncio
import re
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)

# Optional run correlation + summaries
try:
    from backend.utils.logging_config import run_id_contextvar
except Exception:  # pragma: no cover
    try:
        from ..utils.logging_config import run_id_contextvar  # type: ignore
    except Exception:
        run_id_contextvar = None  # type: ignore

try:
    from backend.utils.run_summaries import emit_summary, text_stats
except Exception:  # pragma: no cover
    from ..utils.run_summaries import emit_summary, text_stats  # type: ignore

# Ensure backend/system imports work in production
try:
    backend_dir = Path(__file__).resolve().parents[1]
    repo_root = Path(__file__).resolve().parents[2]
    for path in (str(backend_dir), str(repo_root)):
        if path not in sys.path:
            sys.path.insert(0, path)
except Exception:
    pass

class AutoCompletionStatus(Enum):
    """Status states for auto-completion jobs."""
    NOT_STARTED = "not_started"
    INITIALIZING = "initializing"
    GENERATING = "generating"
    QUALITY_CHECKING = "quality_checking"
    RETRYING = "retrying"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class ChapterGenerationJob:
    """Represents a single chapter generation job."""
    chapter_number: int
    status: str
    start_time: Optional[datetime] = None
    completion_time: Optional[datetime] = None
    retry_count: int = 0
    quality_score: Optional[float] = None
    failure_reason: Optional[str] = None
    context_data: Optional[Dict[str, Any]] = None
    word_count: int = 0

@dataclass
class AutoCompletionConfig:
    """Configuration for auto-completion behavior."""
    target_word_count: int = 80000
    target_chapter_count: int = 20
    minimum_quality_score: float = 5.0
    max_retries_per_chapter: int = 3
    auto_pause_on_failure: bool = True
    context_improvement_enabled: bool = True
    quality_gates_enabled: bool = True
    user_review_required: bool = False
    words_per_chapter: int = 3800
    user_id: Optional[str] = None
    project_id: Optional[str] = None
    scene_by_scene: bool = False
    final_polish: bool = False
    final_audit_rewrite: bool = False
    candidate_generations: int = 1
    enable_reader_surrogate: bool = False
    reader_surrogate_auto_revise: bool = False
    final_gate_lock: bool = False
    max_repair_passes: int = 2


def _env_bool(name: str, default: bool) -> bool:
    """Parse a boolean-ish environment variable safely."""
    try:
        raw = os.getenv(name)
        if raw is None:
            return default
        raw = raw.strip().lower()
        if raw == "":
            return default
        return raw in ("1", "true", "yes", "y", "on")
    except Exception:
        return default

class AutoCompleteBookOrchestrator:
    """
    Orchestrates the auto-completion of an entire book through sequential chapter generation.
    Simplified version for FastAPI backend.
    """
    
    def __init__(self, project_path: str = ".", config: Optional[AutoCompletionConfig] = None):
        self.project_path = Path(project_path)
        self.chapters_dir = self.project_path / "chapters"
        self.state_dir = self.project_path / ".project-state"
        
        # Configuration
        self.config = config or AutoCompletionConfig()
        # Allow ops/testing to toggle heavier passes via env without changing defaults.
        self.config.scene_by_scene = _env_bool("AUTO_COMPLETE_SCENE_BY_SCENE", self.config.scene_by_scene)
        self.config.final_polish = _env_bool("AUTO_COMPLETE_FINAL_POLISH", self.config.final_polish)
        self.config.final_audit_rewrite = _env_bool("AUTO_COMPLETE_FINAL_AUDIT_REWRITE", self.config.final_audit_rewrite)
        
        # State management
        self.job_id: Optional[str] = None
        self.current_status = AutoCompletionStatus.NOT_STARTED
        self.chapter_jobs: List[ChapterGenerationJob] = []
        self.start_time: Optional[datetime] = None
        self.completion_data: Dict[str, Any] = {}
        
        # Create necessary directories
        self.chapters_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup logging
        self.logger = logger

        # Initialize chapter context manager for continuity and state
        try:
            from .helpers.chapter_context_manager import ChapterContextManager
            self.context_manager = ChapterContextManager(self.project_path)
        except Exception as e:
            self.logger.warning(f"Context manager unavailable, proceeding without continuity manager: {e}")
            self.context_manager = None

        # Initialize book plan generator (master beat map)
        try:
            from .helpers.book_plan_generator import BookPlanGenerator
            self.book_plan_generator = BookPlanGenerator(str(self.project_path))
        except Exception as e:
            self.logger.warning(f"Book plan generator unavailable: {e}")
            self.book_plan_generator = None
        self.book_plan_cache: Optional[Dict[str, Any]] = None

        # Initialize chapter pattern tracker and blueprint generator
        self.pattern_tracker = None
        try:
            from .helpers.chapter_blueprint import ChapterPatternTracker
            self.pattern_tracker = ChapterPatternTracker(str(self.project_path))
        except Exception as e:
            self.logger.warning(f"Chapter pattern tracker unavailable: {e}")

        # Initialize cadence analyzer for rhythm fingerprinting
        self.cadence_analyzer = None
        try:
            from .helpers.cadence_analyzer import CadenceAnalyzer
            self.cadence_analyzer = CadenceAnalyzer(str(self.project_path))
        except Exception as e:
            self.logger.warning(f"Cadence analyzer unavailable: {e}")

        # Initialize voice fingerprint manager for character voice distinctiveness
        self.voice_fingerprint_manager = None
        try:
            from .helpers.voice_fingerprint_manager import VoiceFingerprintManager
            self.voice_fingerprint_manager = VoiceFingerprintManager(str(self.project_path))
        except Exception as e:
            self.logger.warning(f"Voice fingerprint manager unavailable: {e}")
        
        # Initialize pattern database for repetition tracking
        self.pattern_db = None
        try:
            from backend.system.pattern_database_engine import PatternDatabase
            self.pattern_db = PatternDatabase(str(self.project_path))
        except Exception as backend_err:
            try:
                from ..system.pattern_database_engine import PatternDatabase
                self.pattern_db = PatternDatabase(str(self.project_path))
            except Exception as system_err:
                try:
                    backend_dir = Path(__file__).resolve().parents[1]
                    repo_root = Path(__file__).resolve().parents[2]
                    module_candidates = [
                        backend_dir / "system" / "pattern_database_engine.py",
                        backend_dir / "system" / "pattern-database-engine.py",
                        repo_root / "backend" / "system" / "pattern_database_engine.py",
                        repo_root / "backend" / "pattern_database_engine.py",
                        repo_root / "backend" / "system" / "pattern-database-engine.py",
                        repo_root / "backend" / "backend" / "system" / "pattern_database_engine.py",
                        repo_root / "backend" / "backend" / "system" / "pattern-database-engine.py",
                        repo_root / "system" / "pattern_database_engine.py",
                        repo_root / "system" / "pattern-database-engine.py",
                    ]
                    module_path = next((path for path in module_candidates if path.exists()), None)
                    if not module_path:
                        searched = ", ".join(str(path) for path in module_candidates)
                        raise Exception(
                            "backend.system import failed: "
                            f"{backend_err}; system import failed: {system_err}; "
                            f"pattern database file not found under {searched}"
                        )
                    spec = importlib.util.spec_from_file_location("pattern_database_engine", module_path)
                    if not spec or not spec.loader:
                        raise Exception(f"Pattern database module spec unavailable: {module_path}")
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    self.pattern_db = getattr(module, "PatternDatabase")(str(self.project_path))
                except Exception as e:
                    self.logger.warning(f"Pattern database unavailable, repetition tracking disabled: {e}")

        # Initialize completion detector to recognize natural end-of-book
        self.completion_detector = None
        try:
            # Prefer system completion detection which analyzes story semantics
            from backend.system.completion_detection_system import CompletionDetectionSystem, CompletionStatus as _CompletionStatus
            self.completion_detector = CompletionDetectionSystem(str(self.project_path))
            self._CompletionStatusClass = _CompletionStatus
        except Exception:
            try:
                # Fallback import path when running within backend/system as top-level
                from system.completion_detection_system import CompletionDetectionSystem, CompletionStatus as _CompletionStatus
                self.completion_detector = CompletionDetectionSystem(str(self.project_path))
                self._CompletionStatusClass = _CompletionStatus
            except Exception as e:
                self.logger.warning(f"Completion detection unavailable; will generate to target count only: {e}")
                self._CompletionStatusClass = None

        if self.completion_detector:
            try:
                self.completion_detector.criteria.target_word_count = int(self.config.target_word_count)
                self.completion_detector.criteria.target_chapter_count = int(self.config.target_chapter_count)
                self.completion_detector.criteria.minimum_word_count = int(self.config.target_word_count * 0.85)
                self.completion_detector.criteria.maximum_word_count = int(self.config.target_word_count * 1.2)
                self.completion_detector.criteria.minimum_chapter_count = max(1, int(self.config.target_chapter_count * 0.8))
                self.completion_detector.criteria.maximum_chapter_count = int(self.config.target_chapter_count * 1.2)
            except Exception as criteria_err:
                self.logger.warning(f"Failed to override completion criteria: {criteria_err}")
        
    def start_auto_completion(self, request_data: Dict[str, Any]) -> str:
        """
        Start the auto-completion process.
        
        Args:
            request_data: Request data containing book_bible, project_id, etc.
            
        Returns:
            Job ID for tracking the completion process
        """
        if self.current_status != AutoCompletionStatus.NOT_STARTED:
            raise ValueError(f"Auto-completion already started (status: {self.current_status.value})")
        
        # Generate unique job ID
        self.job_id = str(uuid.uuid4())
        self.current_status = AutoCompletionStatus.INITIALIZING
        self.start_time = datetime.utcnow()
        
        # Update configuration from request (support both legacy + config keys)
        target_chapters = request_data.get('target_chapters', request_data.get('target_chapter_count'))
        words_per_chapter = request_data.get('words_per_chapter')
        quality_threshold = request_data.get('quality_threshold', request_data.get('minimum_quality_score'))

        if target_chapters is not None:
            self.config.target_chapter_count = int(target_chapters)
        if words_per_chapter is not None:
            self.config.words_per_chapter = int(words_per_chapter)
        if quality_threshold is not None:
            self.config.minimum_quality_score = float(quality_threshold)
        
        # Initialize completion data
        self.completion_data = {
            'job_id': self.job_id,
            'project_id': request_data.get('project_id'),
            'book_bible': request_data.get('book_bible'),
            'config': asdict(self.config),
            'start_time': self.start_time.isoformat(),
            'status': self.current_status.value,
            'progress': {
                'current_chapter': 0,
                'total_chapters': self.config.target_chapter_count,
                'chapters_completed': 0,
                'total_words': 0
            },
            'quality_scores': [],
            'error_message': None
        }
        
        # Save book bible for reference
        if request_data.get('book_bible'):
            book_bible_file = self.project_path / "book-bible.md"
            with open(book_bible_file, 'w', encoding='utf-8') as f:
                f.write(request_data['book_bible'])
        
        # Initialize chapter generation queue
        self._initialize_chapter_queue(request_data.get('starting_chapter', 1))
        
        # Log start
        self.logger.info(f"Auto-completion started - Job ID: {self.job_id}")
        
        return self.job_id
    
    def _initialize_chapter_queue(self, starting_chapter: int = 1):
        """Initialize the chapter generation queue."""
        self.chapter_jobs = []
        
        # Create jobs for chapters
        for chapter_num in range(starting_chapter, self.config.target_chapter_count + 1):
            job = ChapterGenerationJob(
                chapter_number=chapter_num,
                status='pending'
            )
            self.chapter_jobs.append(job)
        
        self.logger.info(f"Initialized chapter queue: {len(self.chapter_jobs)} chapters to generate")
    
    async def run_auto_completion(self, progress_callback=None) -> Dict[str, Any]:
        """
        Run the complete auto-completion process.
        
        Args:
            progress_callback: Optional callback for progress updates
            
        Returns:
            Completion results and statistics
        """
        if self.current_status == AutoCompletionStatus.NOT_STARTED:
            raise ValueError("Auto-completion not started. Call start_auto_completion() first.")
        
        self.current_status = AutoCompletionStatus.GENERATING
        
        try:
            # Ensure master book plan exists before generating chapters
            await self._ensure_book_plan()

            # Generate chapters sequentially
            for job in self.chapter_jobs:
                if job.status != 'pending':
                    continue
                
                # Pause handling: wait until resumed or cancelled
                while self.current_status == AutoCompletionStatus.PAUSED:
                    self.completion_data['status'] = "paused"
                    if progress_callback:
                        await progress_callback(self.get_progress_status())
                    await asyncio.sleep(1)
                    if self.current_status == AutoCompletionStatus.CANCELLED:
                        break

                # Check if job was cancelled
                if self.current_status == AutoCompletionStatus.CANCELLED:
                    break

                # Check for natural completion based on story analysis and targets
                try:
                    if self.completion_detector:
                        analysis = self.completion_detector.analyze_completion_status()
                        # Stop if completed or exceeded target envelope
                        if (
                            (self._CompletionStatusClass and analysis.status in [
                                self._CompletionStatusClass.COMPLETED,
                                self._CompletionStatusClass.OVER_TARGET
                            ])
                            or (not self._CompletionStatusClass and str(getattr(analysis, 'status', '')).lower() in ['completed', 'over_target'])
                        ):
                            self.logger.info("Book completion detected by completion detector - stopping further generation")
                            self.completion_data['status'] = 'completed'
                            self.completion_data['completion_reason'] = 'story_completed'
                            break
                except Exception as completion_check_err:
                    # Non-fatal; continue generation if detector fails
                    self.logger.warning(f"Completion detection check failed, continuing generation: {completion_check_err}")
                
                # Generate chapter
                chapter_result = await self._generate_chapter(job)
                
                # Update progress
                self.completion_data['progress']['current_chapter'] = job.chapter_number
                if chapter_result['success']:
                    self.completion_data['progress']['chapters_completed'] += 1
                    self.completion_data['progress']['total_words'] += chapter_result.get('word_count', 0)
                    
                    self.completion_data['quality_scores'].append({
                        'chapter': job.chapter_number,
                        'score': chapter_result.get('quality_score', 0),
                        'timestamp': datetime.utcnow().isoformat()
                    })
                
                # Call progress callback if provided
                if progress_callback:
                    await progress_callback(self.get_progress_status())
                
            # Brief pause between chapters (yield control so other requests aren't starved)
            await asyncio.sleep(0)
            
            # Determine completion status
            if self.current_status == AutoCompletionStatus.PAUSED:
                self.completion_data['status'] = "paused"
            elif self.current_status == AutoCompletionStatus.CANCELLED:
                self.completion_data['status'] = "cancelled"
            else:
                self.current_status = AutoCompletionStatus.COMPLETED
                self.completion_data['status'] = "completed"
                self.completion_data['end_time'] = datetime.utcnow().isoformat()

            # Final polish pass across the entire book
            if self.current_status == AutoCompletionStatus.COMPLETED and self.config.final_polish:
                try:
                    await self._final_polish_book()
                except Exception as polish_err:
                    self.logger.warning(f"Final polish pass failed: {polish_err}")
            
        except Exception as e:
            self.logger.error(f"Auto-completion failed: {e}")
            self.current_status = AutoCompletionStatus.FAILED
            self.completion_data['status'] = "failed"
            self.completion_data['error_message'] = str(e)
            self.completion_data['end_time'] = datetime.utcnow().isoformat()
        
        return self.completion_data

    async def _ensure_book_plan(self) -> None:
        """Ensure a master book plan exists (beat map + chapter objectives)."""
        if not self.book_plan_generator:
            raise RuntimeError("Book plan generator is unavailable; cannot generate coherent full book.")

        existing_plan = self.book_plan_generator.load_existing_plan()
        if existing_plan:
            self.book_plan_cache = existing_plan
            return

        # Load book bible and references for planning
        book_bible_file = self.project_path / "book-bible.md"
        if not book_bible_file.exists():
            raise RuntimeError("Book bible not found; cannot generate master book plan.")

        book_bible = book_bible_file.read_text(encoding="utf-8")

        references = {}
        references_dir = self.project_path / "references"
        if references_dir.exists():
            reference_files = {
                'characters': 'characters.md',
                'outline': 'outline.md',
                'plot_timeline': 'plot-timeline.md',
                'world_building': 'world-building.md',
                'style_guide': 'style-guide.md',
                'entity_registry': 'entity-registry.md',
                'relationship_map': 'relationship-map.md',
                'themes_and_motifs': 'themes-and-motifs.md',
                'target_audience': 'target-audience-profile.md',
                'research_notes': 'research-notes.md',
            }
            for ref_type, filename in reference_files.items():
                ref_file = references_dir / filename
                if ref_file.exists():
                    references[ref_type] = ref_file.read_text(encoding="utf-8")

        result = await self.book_plan_generator.generate_plan(
            book_bible=book_bible,
            references=references,
            target_chapters=self.config.target_chapter_count
        )

        if not result.success or not result.plan:
            raise RuntimeError(result.error or "Failed to generate master book plan.")

        self.book_plan_cache = result.plan
    
    async def _generate_chapter(self, job: ChapterGenerationJob) -> Dict[str, Any]:
        """
        Generate a single chapter with quality assessment.
        
        Args:
            job: Chapter generation job
            
        Returns:
            Generation result with quality assessment
        """
        chapter_run_id = str(uuid.uuid4())
        try:
            if run_id_contextvar is not None:
                run_id_contextvar.set(chapter_run_id[:12])
        except Exception:
            pass
        job.status = 'generating'
        job.start_time = datetime.utcnow()
        
        self.logger.info(f"Generating Chapter {job.chapter_number}")

        # Early cancellation check
        if self.current_status == AutoCompletionStatus.CANCELLED:
            job.status = 'failed'
            job.failure_reason = 'Cancelled'
            return {'success': False, 'chapter_number': job.chapter_number, 'error': 'Cancelled'}

        try:
            # Build context for this chapter
            context = self._build_chapter_context(job.chapter_number)
            context["chapter_run_id"] = chapter_run_id
            # Shared post-draft LLM budget (caps churn after initial draft exists)
            try:
                postdraft_total = max(0, int(os.getenv("CHAPTER_POSTDRAFT_LLM_BUDGET", "3")))
                context["postdraft_budget"] = {
                    "total": postdraft_total,
                    "used": 0,
                    "remaining": postdraft_total,
                    "actions": [],
                }
            except Exception:
                pass
            try:
                vector_payload = await self._build_vector_memory_context(job.chapter_number, context)
                context.update(vector_payload)
            except Exception as e:
                self.logger.warning(f"Vector memory unavailable for Chapter {job.chapter_number}: {e}")
            
            # Generate chapter using LLM with reference files
            try:
                from backend.services.chapter_context_builder import references_from_context
                context["references"] = references_from_context(context)
            except Exception:
                context["references"] = {
                    k.replace("_reference", ""): v
                    for k, v in (context or {}).items()
                    if isinstance(v, str) and k.endswith("_reference")
                }
            candidate_count = max(1, int(os.getenv("CHAPTER_CANDIDATE_COUNT", self.config.candidate_generations)))
            max_regen_rounds = max(0, int(os.getenv("CHAPTER_MAX_REGEN_ROUNDS", "0")))
            candidates: List[Dict[str, Any]] = []
            early_stop_score = float(os.getenv("CHAPTER_EARLY_STOP_SCORE", "9.0"))
            for idx in range(candidate_count):
                draft = await self._generate_chapter_with_references(job.chapter_number, context)
                draft_metadata = context.pop("_last_llm_metadata", {}) if isinstance(context, dict) else {}
                if not isinstance(draft_metadata, dict):
                    draft_metadata = {}
                evaluation = await self.evaluate_candidate(draft, job.chapter_number, context)
                candidates.append({"content": draft, "llm_metadata": draft_metadata, **evaluation})
                self.logger.info(f"Candidate {idx + 1}/{candidate_count} scored {evaluation.get('score', 0):.2f}")
                try:
                    if self._passes_quality_gates(evaluation.get("quality_result", {})) and float(evaluation.get("score", 0.0)) >= early_stop_score:
                        self.logger.info(
                            f"Early-stopping candidate search: candidate {idx + 1} cleared gates with score {evaluation.get('score', 0):.2f}."
                        )
                        break
                except Exception:
                    pass

            # Cancellation check after generation
            if self.current_status == AutoCompletionStatus.CANCELLED:
                job.status = 'failed'
                job.failure_reason = 'Cancelled'
                return {'success': False, 'chapter_number': job.chapter_number, 'error': 'Cancelled'}

            # Choose best candidate (prefer those passing quality gates)
            passing = [c for c in candidates if self._passes_quality_gates(c.get("quality_result", {}))]
            pool = passing if passing else candidates
            best = max(pool, key=lambda c: c.get("score", 0))
            chapter_content = best["content"]
            quality_result = best.get("quality_result", {})

            # If gates fail, try mechanical repairs first (avoid polishing).
            if (
                self.config.quality_gates_enabled
                and not self._passes_quality_gates(quality_result)
                and not self._has_fail_fast_failures(quality_result)
            ):
                chapter_content = await self._apply_targeted_repairs(
                    chapter_content,
                    job.chapter_number,
                    quality_result,
                    context
                )
                quality_result = await self._assess_chapter_quality(chapter_content, job.chapter_number, context)

            # If gates still fail, prefer regeneration rounds over editing.
            regen_round = 0
            while (
                self.config.quality_gates_enabled
                and not self._passes_quality_gates(quality_result)
                and regen_round < max_regen_rounds
            ):
                # Enforce post-draft LLM budget (regen is churn after draft exists).
                budget = context.get("postdraft_budget") if isinstance(context, dict) else None
                remaining = int((budget or {}).get("remaining", 0) or 0) if isinstance(budget, dict) else 0
                if remaining <= 0:
                    self.logger.info("Post-draft LLM budget exhausted; skipping further regeneration rounds.")
                    break
                try:
                    budget["remaining"] = max(0, remaining - 1)
                    budget["used"] = int(budget.get("used", 0) or 0) + 1
                    (budget.get("actions") if isinstance(budget.get("actions"), list) else []).append("regen_round")
                except Exception:
                    pass

                regen_round += 1
                self.logger.info(
                    f"Chapter {job.chapter_number} failed quality gates; regenerating candidate (round {regen_round}/{max_regen_rounds})"
                )
                try:
                    context["regen_feedback"] = self._build_regen_feedback(quality_result)
                except Exception:
                    context["regen_feedback"] = ""
                draft = await self._generate_chapter_with_references(job.chapter_number, context)
                draft_metadata = context.pop("_last_llm_metadata", {}) if isinstance(context, dict) else {}
                if not isinstance(draft_metadata, dict):
                    draft_metadata = {}
                evaluation = await self.evaluate_candidate(draft, job.chapter_number, context)
                candidates.append({"content": draft, "llm_metadata": draft_metadata, **evaluation})

                passing = [c for c in candidates if self._passes_quality_gates(c.get("quality_result", {}))]
                pool = passing if passing else candidates
                best = max(pool, key=lambda c: c.get("score", 0))
                chapter_content = best["content"]
                quality_result = best.get("quality_result", {})
            selected_llm_metadata = best.get("llm_metadata", {}) if isinstance(best, dict) else {}
            if isinstance(selected_llm_metadata, dict) and selected_llm_metadata:
                # Make best-effort tokens/cost/time available for persistence and summaries.
                context["tokens_used"] = selected_llm_metadata.get("tokens_used", context.get("tokens_used", {}))
                context["cost_breakdown"] = selected_llm_metadata.get("cost_breakdown", context.get("cost_breakdown", {}))
                context["generation_time"] = selected_llm_metadata.get("generation_time", context.get("generation_time", 0.0))
                context["retry_attempts"] = selected_llm_metadata.get("retry_attempts", context.get("retry_attempts", 0))
                context["model_used"] = selected_llm_metadata.get("model", context.get("model_used", "gpt-4o"))

            # Attach plan and bridge compliance to quality result
            plan_compliance = best.get("plan_compliance")
            if plan_compliance:
                quality_result.setdefault("category_results", {})
                quality_result["category_results"]["plan_compliance"] = plan_compliance
            bridge_compliance = best.get("bridge_compliance")
            if bridge_compliance:
                quality_result.setdefault("category_results", {})
                quality_result["category_results"]["bridge_compliance"] = bridge_compliance
            pov_compliance = best.get("pov_compliance")
            if pov_compliance:
                quality_result.setdefault("category_results", {})
                quality_result["category_results"]["pov_compliance"] = pov_compliance
            director_validation = context.get("director_brief_validation")
            if isinstance(director_validation, dict) and director_validation:
                quality_result.setdefault("category_results", {})
                quality_result["category_results"]["director_brief_validation"] = {
                    "score": 1.0 if director_validation.get("passed") else 0.0,
                    "minimum_required": 1.0,
                    "passed": bool(director_validation.get("passed")),
                    "details": {"missing_sections": director_validation.get("missing_sections", [])}
                }

            # Optional last-resort revision pass (off by default).
            if (
                self.config.quality_gates_enabled
                and not self._passes_quality_gates(quality_result)
                and self._enable_llm_revision()
                and not self._has_fail_fast_failures(quality_result)
            ):
                self.logger.info(f"Chapter {job.chapter_number} failed quality gates; attempting targeted revision")
                chapter_content = await self._revise_chapter(chapter_content, job.chapter_number, quality_result, context)
                # Re-assess after revision before applying targeted repairs
                quality_result = await self._assess_chapter_quality(chapter_content, job.chapter_number, context)
                # Intelligent targeted repairs based on failed checks
                chapter_content = await self._apply_targeted_repairs(
                    chapter_content,
                    job.chapter_number,
                    quality_result,
                    context
                )
                # Re-assess after revision
                quality_result = await self._assess_chapter_quality(chapter_content, job.chapter_number, context)
                # Recompute plan compliance after revision
                plan_compliance = self._evaluate_plan_compliance(
                    chapter_content,
                    objectives=context.get("chapter_objectives", []),
                    required_plot_points=context.get("required_plot_points", [])
                )
                if plan_compliance:
                    quality_result.setdefault("category_results", {})
                    quality_result["category_results"]["plan_compliance"] = plan_compliance

                bridge_compliance = self._evaluate_bridge_compliance(
                    chapter_content,
                    bridge_requirements=context.get("bridge_requirements", [])
                )
                if bridge_compliance:
                    quality_result.setdefault("category_results", {})
                    quality_result["category_results"]["bridge_compliance"] = bridge_compliance

                pov_compliance = self._evaluate_pov_compliance(
                    chapter_content,
                    pov_character=context.get("pov_character", ""),
                    pov_type=context.get("pov_type", "")
                )
                if pov_compliance:
                    quality_result.setdefault("category_results", {})
                    quality_result["category_results"]["pov_compliance"] = pov_compliance

            # Consistency check against canon log and references (budgeted)
            if os.getenv("ENABLE_CONSISTENCY_CHECK", "false").lower() == "true":
                try:
                    from backend.services.consistency_check_service import check_chapter_consistency
                    try:
                        from backend.services.chapter_context_builder import references_from_context, get_canon_log
                        references = references_from_context(context)
                        canon_log = get_canon_log(references) or context.get("canon_log_reference", "")
                    except Exception:
                        canon_log = context.get("canon_log_reference", "")
                        references = context.get("references", {}) or {
                            k.replace("_reference", ""): v
                            for k, v in (context or {}).items()
                            if isinstance(v, str) and k.endswith("_reference")
                        }
                    budget = context.get("postdraft_budget") if isinstance(context, dict) else None
                    remaining = int((budget or {}).get("remaining", 0) or 0) if isinstance(budget, dict) else 0
                    if remaining <= 0:
                        check_result = {"severity": "unknown", "skipped": True, "reason": "postdraft_budget_cap"}
                    else:
                        try:
                            budget["remaining"] = max(0, remaining - 1)
                            budget["used"] = int(budget.get("used", 0) or 0) + 1
                            (budget.get("actions") if isinstance(budget.get("actions"), list) else []).append("consistency_check")
                        except Exception:
                            pass
                        check_result = await check_chapter_consistency(
                            chapter_number=job.chapter_number,
                            chapter_content=chapter_content,
                            book_bible=context.get("book_bible", ""),
                            references=references,
                            canon_log=canon_log,
                            vector_store_ids=context.get("vector_store_ids", []),
                            user_id=context.get("user_id")
                        )

                    if check_result.get("severity") == "high" and check_result.get("rewrite_instruction"):
                        budget = context.get("postdraft_budget") if isinstance(context, dict) else None
                        remaining = int((budget or {}).get("remaining", 0) or 0) if isinstance(budget, dict) else 0
                        if remaining > 0:
                            try:
                                budget["remaining"] = max(0, remaining - 1)
                                budget["used"] = int(budget.get("used", 0) or 0) + 1
                                (budget.get("actions") if isinstance(budget.get("actions"), list) else []).append("canon_rewrite")
                            except Exception:
                                pass
                            chapter_content = await self._rewrite_with_canon(
                                chapter_content,
                                check_result["rewrite_instruction"],
                                context
                            )
                            quality_result = await self._assess_chapter_quality(chapter_content, job.chapter_number, context)
                except Exception as consistency_err:
                    self.logger.warning(f"Consistency check failed for Chapter {job.chapter_number}: {consistency_err}")

            # Hard gate review — disabled by default; enable via ENABLE_HARD_GATE_CHECK=true
            hard_gate_result = {"passed": True, "details": {"skipped": True, "reason": "disabled_by_default"}}
            try:
                budget = context.get("postdraft_budget") if isinstance(context, dict) else None
                remaining = int((budget or {}).get("remaining", 0) or 0) if isinstance(budget, dict) else 0
            except Exception:
                remaining = 0
            if remaining > 0 and os.getenv("ENABLE_HARD_GATE_CHECK", "false").lower() == "true":
                try:
                    budget["remaining"] = max(0, remaining - 1)  # type: ignore[index]
                    budget["used"] = int(budget.get("used", 0) or 0) + 1  # type: ignore[union-attr]
                    (budget.get("actions") if isinstance(budget.get("actions"), list) else []).append("hard_gate_check")  # type: ignore[union-attr]
                except Exception:
                    pass
                hard_gate_result = await self._evaluate_hard_gates(chapter_content, job.chapter_number, context)
            quality_result.setdefault("category_results", {})["hard_gates"] = {
                "score": 1.0 if hard_gate_result.get("passed") else 0.0,
                "minimum_required": 1.0,
                "passed": hard_gate_result.get("passed", False),
                "details": hard_gate_result.get("details", {})
            }
            if not hard_gate_result.get("passed"):
                budget = context.get("postdraft_budget") if isinstance(context, dict) else None
                remaining = int((budget or {}).get("remaining", 0) or 0) if isinstance(budget, dict) else 0
                if remaining <= 0:
                    self.logger.info("Post-draft LLM budget exhausted; skipping hard-gate revision.")
                    # Mark as non-fatal when budget-capped; rely on fail-fast deterministic gates.
                    try:
                        quality_result.setdefault("category_results", {})["hard_gates"]["passed"] = True
                    except Exception:
                        pass
                else:
                    try:
                        budget["remaining"] = max(0, remaining - 1)
                        budget["used"] = int(budget.get("used", 0) or 0) + 1
                        (budget.get("actions") if isinstance(budget.get("actions"), list) else []).append("hard_gate_revise")
                    except Exception:
                        pass
                    chapter_content = await self._revise_for_hard_gates(
                        chapter_content,
                        job.chapter_number,
                        hard_gate_result,
                        context
                    )
                    quality_result = await self._assess_chapter_quality(chapter_content, job.chapter_number, context)

            # Reader surrogate diagnostic pass
            surrogate_report = {}
            if self.config.enable_reader_surrogate:
                try:
                    budget = context.get("postdraft_budget") if isinstance(context, dict) else None
                    remaining = int((budget or {}).get("remaining", 0) or 0) if isinstance(budget, dict) else 0
                    if remaining <= 0:
                        self.logger.info("Post-draft LLM budget exhausted; skipping reader surrogate check.")
                        surrogate_report = {"severity": "unknown", "skipped": True, "reason": "postdraft_budget_cap"}
                        quality_result.setdefault("category_results", {})["reader_surrogate"] = {
                            "score": 1.0,
                            "minimum_required": 1.0,
                            "passed": True,
                            "details": surrogate_report
                        }
                        severity = "unknown"
                    else:
                        try:
                            budget["remaining"] = max(0, remaining - 1)
                            budget["used"] = int(budget.get("used", 0) or 0) + 1
                            (budget.get("actions") if isinstance(budget.get("actions"), list) else []).append("reader_surrogate_check")
                        except Exception:
                            pass
                        surrogate_report = await self._run_reader_surrogate(chapter_content, job.chapter_number, context)
                        severity = str(surrogate_report.get("severity", "low")).lower()
                        quality_result.setdefault("category_results", {})["reader_surrogate"] = {
                            "score": 1.0 if severity in {"low", "medium"} else 0.0,
                            "minimum_required": 1.0,
                            "passed": severity in {"low", "medium"},
                            "details": surrogate_report
                        }
                    if severity == "high" and self.config.reader_surrogate_auto_revise:
                        # Prefer regeneration before any LLM editing.
                        max_surrogate_regen = max(0, int(os.getenv("CHAPTER_MAX_SURROGATE_REGEN_ROUNDS", "2")))
                        for r in range(max_surrogate_regen):
                            budget = context.get("postdraft_budget") if isinstance(context, dict) else None
                            remaining = int((budget or {}).get("remaining", 0) or 0) if isinstance(budget, dict) else 0
                            if remaining <= 0:
                                self.logger.info("Post-draft LLM budget exhausted; skipping surrogate regeneration.")
                                break
                            try:
                                budget["remaining"] = max(0, remaining - 1)
                                budget["used"] = int(budget.get("used", 0) or 0) + 1
                                (budget.get("actions") if isinstance(budget.get("actions"), list) else []).append("surrogate_regen_round")
                            except Exception:
                                pass
                            self.logger.info(
                                f"Reader surrogate severity high; regenerating candidate (round {r + 1}/{max_surrogate_regen})"
                            )
                            try:
                                context["regen_feedback"] = "Reader surrogate reported high confusion/boredom; regenerate with clearer stakes, clearer causal links, and more concrete scene actions."
                            except Exception:
                                context["regen_feedback"] = ""
                            draft = await self._generate_chapter_with_references(job.chapter_number, context)
                            draft_metadata = context.pop("_last_llm_metadata", {}) if isinstance(context, dict) else {}
                            if not isinstance(draft_metadata, dict):
                                draft_metadata = {}
                            evaluation = await self.evaluate_candidate(draft, job.chapter_number, context)
                            candidates.append({"content": draft, "llm_metadata": draft_metadata, **evaluation})
                            passing = [c for c in candidates if self._passes_quality_gates(c.get("quality_result", {}))]
                            pool = passing if passing else candidates
                            best = max(pool, key=lambda c: c.get("score", 0))
                            chapter_content = best["content"]
                            quality_result = best.get("quality_result", {})

                        # Re-run surrogate once after regeneration to avoid repeated costly checks.
                        budget = context.get("postdraft_budget") if isinstance(context, dict) else None
                        remaining = int((budget or {}).get("remaining", 0) or 0) if isinstance(budget, dict) else 0
                        if remaining > 0:
                            try:
                                budget["remaining"] = max(0, remaining - 1)
                                budget["used"] = int(budget.get("used", 0) or 0) + 1
                                (budget.get("actions") if isinstance(budget.get("actions"), list) else []).append("reader_surrogate_recheck")
                            except Exception:
                                pass
                            surrogate_report = await self._run_reader_surrogate(chapter_content, job.chapter_number, context)
                        severity = str(surrogate_report.get("severity", "low")).lower()
                        quality_result.setdefault("category_results", {})["reader_surrogate"] = {
                            "score": 1.0 if severity in {"low", "medium"} else 0.0,
                            "minimum_required": 1.0,
                            "passed": severity in {"low", "medium"},
                            "details": surrogate_report
                        }

                        # Optional last-resort edit pass (off by default).
                        if severity == "high" and self._enable_llm_revision() and not self._has_fail_fast_failures(quality_result):
                            chapter_content = await self._revise_for_reader_surrogate(
                                chapter_content,
                                job.chapter_number,
                                surrogate_report,
                                context
                            )
                            quality_result = await self._assess_chapter_quality(chapter_content, job.chapter_number, context)

                        hard_gate_result = await self._evaluate_hard_gates(chapter_content, job.chapter_number, context)
                        quality_result.setdefault("category_results", {})["hard_gates"] = {
                            "score": 1.0 if hard_gate_result.get("passed") else 0.0,
                            "minimum_required": 1.0,
                            "passed": hard_gate_result.get("passed", False),
                            "details": hard_gate_result.get("details", {})
                        }
                except Exception as surrogate_err:
                    self.logger.warning(f"Reader surrogate check failed for Chapter {job.chapter_number}: {surrogate_err}")

            # Final gate lock to prevent post-gate drift
            if self.config.final_gate_lock:
                chapter_content, quality_result, hard_gate_result = await self._final_gate_lock(
                    chapter_content,
                    job.chapter_number,
                    context,
                    quality_result
                )
            
            # Capture final quality result for persistence
            # Recompute plan/bridge/POV compliance after final lock
            plan_compliance = self._evaluate_plan_compliance(
                chapter_content,
                objectives=context.get("chapter_objectives", []),
                required_plot_points=context.get("required_plot_points", [])
            )
            if plan_compliance:
                quality_result.setdefault("category_results", {})
                quality_result["category_results"]["plan_compliance"] = plan_compliance

            bridge_compliance = self._evaluate_bridge_compliance(
                chapter_content,
                bridge_requirements=context.get("bridge_requirements", [])
            )
            if bridge_compliance:
                quality_result.setdefault("category_results", {})
                quality_result["category_results"]["bridge_compliance"] = bridge_compliance

            pov_compliance = self._evaluate_pov_compliance(
                chapter_content,
                pov_character=context.get("pov_character", ""),
                pov_type=context.get("pov_type", "")
            )
            if pov_compliance:
                quality_result.setdefault("category_results", {})
                quality_result["category_results"]["pov_compliance"] = pov_compliance

            context["quality_result"] = quality_result
            context["quality_score"] = quality_result.get("overall_score", 0)
            context["stage"] = "draft"

            # Cancellation check before persistence
            if self.current_status == AutoCompletionStatus.CANCELLED:
                job.status = 'failed'
                job.failure_reason = 'Cancelled'
                return {'success': False, 'chapter_number': job.chapter_number, 'error': 'Cancelled'}

            # Persist final content and continuity artifacts
            try:
                chapter_file = self.chapters_dir / f"chapter-{job.chapter_number:02d}.md"
                with open(chapter_file, 'w', encoding='utf-8') as f:
                    f.write(chapter_content)
            except Exception as file_err:
                self.logger.warning(f"Failed to save chapter file for Chapter {job.chapter_number}: {file_err}")

            chapter_context = None
            if self.context_manager:
                try:
                    chapter_context = self.context_manager.analyze_chapter_content(job.chapter_number, chapter_content)
                except Exception as e:
                    self.logger.warning(f"Failed to analyze continuity for Chapter {job.chapter_number}: {e}")

            # Record chapter structural signals for anti-pattern tracking
            if self.pattern_tracker:
                try:
                    known_chars = context.get("focal_characters", [])
                    signals = self.pattern_tracker.extract_signals(
                        job.chapter_number, chapter_content, known_characters=known_chars
                    )
                    self.pattern_tracker.record_chapter(signals)
                    self.logger.info(
                        f"Chapter {job.chapter_number} patterns: shape={signals.chapter_shape}, "
                        f"opening={signals.opening_type}, ending={signals.ending_type}, "
                        f"timer={signals.has_timer}, developments={signals.new_developments}"
                    )
                except Exception as e:
                    self.logger.warning(f"Failed to record chapter patterns for Chapter {job.chapter_number}: {e}")

            if self.pattern_db:
                try:
                    characters = chapter_context.characters_present if chapter_context else []
                    self.pattern_db.add_chapter_patterns(job.chapter_number, chapter_content, characters=characters)
                except Exception as e:
                    self.logger.warning(f"Failed to update pattern database for Chapter {job.chapter_number}: {e}")

            if self.cadence_analyzer:
                try:
                    fingerprint = self.cadence_analyzer.analyze(job.chapter_number, chapter_content)
                    self.cadence_analyzer.store(fingerprint)
                except Exception as e:
                    self.logger.warning(f"Failed to update cadence fingerprints for Chapter {job.chapter_number}: {e}")

            if self.voice_fingerprint_manager:
                try:
                    self.voice_fingerprint_manager.analyze_chapter(job.chapter_number, chapter_content)
                except Exception as e:
                    self.logger.warning(f"Failed to update voice fingerprints for Chapter {job.chapter_number}: {e}")

            # Update chapter ledger (delta summary + continuity obligations)
            try:
                from backend.services.chapter_ledger_service import update_chapter_ledger, update_local_chapter_ledger
                references = context.get("references", {}) if isinstance(context.get("references"), dict) else {}
                pov_context = {
                    "pov_character": context.get("pov_character", ""),
                    "pov_type": context.get("pov_type", ""),
                    "pov_notes": context.get("pov_notes", "")
                }
                project_id = context.get("project_id") or self.config.project_id
                user_id = context.get("user_id") or self.config.user_id
                if project_id and user_id:
                    ledger_result = await update_chapter_ledger(
                        project_id=project_id,
                        user_id=user_id,
                        chapter_number=job.chapter_number,
                        chapter_content=chapter_content,
                        book_bible=context.get("book_bible", ""),
                        references=references,
                        pov_context=pov_context,
                        vector_store_ids=context.get("vector_store_ids", [])
                    )
                    if ledger_result.get("success") and ledger_result.get("entry"):
                        update_local_chapter_ledger(str(self.project_path), ledger_result["entry"], job.chapter_number)
            except Exception as e:
                self.logger.warning(f"Failed to update chapter ledger for Chapter {job.chapter_number}: {e}")

            chapter_doc_id = await self._save_chapter_to_database(job.chapter_number, chapter_content, context)

            # Emit single structured chapter run summary (log + persisted in chapter metadata).
            try:
                category_results = quality_result.get("category_results", {}) if isinstance(quality_result, dict) else {}
                failed_categories = [
                    name for name, result in (category_results or {}).items()
                    if isinstance(result, dict) and result.get("passed") is False
                ]
                hard_gate_details = {}
                try:
                    hard_gate_details = (category_results.get("hard_gates") or {}).get("details", {})  # type: ignore[union-attr]
                except Exception:
                    hard_gate_details = {}
                reader_surrogate_severity = None
                try:
                    reader_surrogate_severity = ((category_results.get("reader_surrogate") or {}).get("details") or {}).get("severity")
                except Exception:
                    reader_surrogate_severity = None

                canon_text = ""
                try:
                    canon_text = context.get("canon_log_reference", "") or ""
                except Exception:
                    canon_text = ""
                ledger_text_value = ""
                try:
                    ledger_text_value = context.get("chapter_ledger_summary", "") or ""
                except Exception:
                    ledger_text_value = ""

                chapter_run_summary = {
                    "event": "CHAPTER_RUN_SUMMARY",
                    "status": "success" if self._passes_quality_gates(quality_result) else "failed_gates",
                    "mode": "auto_complete",
                    "run_id": chapter_run_id,
                    "job_id": self.job_id,
                    "project_id": context.get("project_id") or self.config.project_id,
                    "user_id": context.get("user_id") or self.config.user_id,
                    "chapter_id": chapter_doc_id,
                    "chapter_number": job.chapter_number,
                    "candidate_count": int(len(candidates)),
                    "regen_rounds": int(regen_round),
                    "selected_candidate_score": float(best.get("score", 0.0)) if isinstance(best, dict) else 0.0,
                    "postdraft_budget": context.get("postdraft_budget", {}),
                    "gates": {
                        "passed": bool(self._passes_quality_gates(quality_result)),
                        "fail_fast_hit": bool(self._has_fail_fast_failures(quality_result)),
                        "failed_categories": failed_categories[:16],
                        "reader_surrogate_severity": reader_surrogate_severity,
                        "hard_gates": hard_gate_details,
                    },
                    "tokens": context.get("tokens_used", {}),
                    "cost_breakdown": context.get("cost_breakdown", {}),
                    "output": {
                        "word_count": len((chapter_content or "").split()),
                        "em_dash_count": int((chapter_content or "").count("—") + (chapter_content or "").count("–")),
                        "ended_cleanly": bool(chapter_content and chapter_content.rstrip()[-1:] in {".", "!", "?", "\"", "”", "’"}),
                    },
                    "continuity_inputs": {
                        "book_bible": text_stats(context.get("book_bible", "") or ""),
                        "canon_log": text_stats(canon_text),
                        "chapter_ledger": text_stats(ledger_text_value),
                    },
                    "llm_perf": selected_llm_metadata.get("perf_summary") if isinstance(selected_llm_metadata, dict) else {},
                    "style_signals": (quality_result.get("style_signals") if isinstance(quality_result, dict) else {}),
                }
                emit_summary(self.logger, chapter_run_summary)
                # Persist summary onto chapter doc (best-effort; does not affect generation success).
                try:
                    if chapter_doc_id and (context.get("project_id") or self.config.project_id):
                        from backend.database_integration import get_database_adapter
                        db = get_database_adapter()
                        await db.update_chapter(
                            chapter_doc_id,
                            {
                                "metadata.run_id": chapter_run_id,
                                "metadata.run_summary": chapter_run_summary,
                            },
                            context.get("user_id") or self.config.user_id,
                            context.get("project_id") or self.config.project_id,
                        )
                except Exception:
                    pass
            except Exception:
                pass

            # Check quality gates
            if self._passes_quality_gates(quality_result):
                job.status = 'completed'
                job.completion_time = datetime.utcnow()
                job.quality_score = quality_result.get('overall_score', 0)
                job.word_count = len(chapter_content.split())
                
                self.logger.info(f"Chapter {job.chapter_number} completed successfully (Quality: {job.quality_score})")
                
                return {
                    'success': True,
                    'chapter_number': job.chapter_number,
                    'word_count': job.word_count,
                    'quality_score': job.quality_score,
                    'generation_time': (job.completion_time - job.start_time).total_seconds()
                }
            else:
                job.status = 'failed'
                # Preserve more specific failure messages when available
                try:
                    llm_error = context.get("_last_llm_error") if isinstance(context, dict) else None
                except Exception:
                    llm_error = None
                if isinstance(llm_error, str) and llm_error.strip():
                    job.failure_reason = llm_error.strip()
                else:
                    try:
                        director_brief_validation = context.get("director_brief_validation") if isinstance(context, dict) else None
                    except Exception:
                        director_brief_validation = None
                    if isinstance(director_brief_validation, dict) and director_brief_validation.get("passed") is False:
                        job.failure_reason = f"Director brief validation failed: {director_brief_validation.get('missing_sections', [])}"
                    else:
                        job.failure_reason = "Failed quality gates"
                # Track word count even on failure when we have content
                try:
                    job.word_count = len((chapter_content or "").split())
                except Exception:
                    job.word_count = 0
                
                return {
                    'success': False,
                    'chapter_number': job.chapter_number,
                    'error': job.failure_reason,
                    'quality_score': quality_result.get('overall_score', 0)
                }
                
        except Exception as e:
            job.status = 'failed'
            job.failure_reason = str(e)
            try:
                # If we managed to generate any content before failure, keep a non-zero word count.
                if isinstance(locals().get("chapter_content"), str) and locals()["chapter_content"].strip():
                    job.word_count = len(locals()["chapter_content"].split())
            except Exception:
                pass
            
            self.logger.error(f"Chapter {job.chapter_number} generation failed: {e}")
            
            return {
                'success': False,
                'chapter_number': job.chapter_number,
                'error': str(e)
            }

    def _get_written_word_count(self) -> int:
        total = 0
        for job in self.chapter_jobs:
            if job.status == 'completed' and job.word_count:
                total += job.word_count
        if total > 0:
            return total
        try:
            total_words = int(self.completion_data.get('progress', {}).get('total_words', 0))
            if total_words > 0:
                return total_words
        except Exception:
            pass
        try:
            if self.chapters_dir.exists():
                for chapter_file in self.chapters_dir.glob("chapter-*.md"):
                    content = chapter_file.read_text(encoding="utf-8")
                    total += len(content.split())
        except Exception as e:
            self.logger.debug(f"Failed to compute written word count from files: {e}")
        return total

    def _infer_pacing_profile(self) -> str:
        avg = getattr(self.config, "words_per_chapter", 0) or 0
        if avg <= 2200:
            return "fast"
        if avg <= 3200:
            return "balanced"
        return "expansive"

    def _word_count_strictness(self) -> str:
        """Return word count enforcement mode: soft or strict."""
        value = os.getenv("WORD_COUNT_STRICTNESS", "soft").strip().lower()
        return value if value in {"soft", "strict"} else "soft"

    def _calculate_word_budget(self, chapter_number: int) -> Tuple[int, int, int, int, int]:
        total_written = self._get_written_word_count()
        remaining_words = max(1000, int(self.config.target_word_count) - total_written)
        remaining_chapters = max(1, int(self.config.target_chapter_count) - (chapter_number - 1))

        base_target = max(800, int(remaining_words / remaining_chapters))
        pacing_profile = self._infer_pacing_profile()

        if remaining_chapters <= 2:
            min_ratio, max_ratio = 0.9, 1.1
        elif pacing_profile == "fast":
            min_ratio, max_ratio = 0.7, 1.05
        elif pacing_profile == "expansive":
            min_ratio, max_ratio = 0.85, 1.3
        else:
            min_ratio, max_ratio = 0.75, 1.2

        target_min = max(600, int(base_target * min_ratio))
        target_max = max(target_min + 200, int(base_target * max_ratio))
        target_max = min(target_max, max(1200, remaining_words))
        target_words = int(min(max(base_target, target_min), target_max))

        return target_words, target_min, target_max, remaining_words, remaining_chapters
    
    def _build_chapter_context(self, chapter_number: int) -> Dict[str, Any]:
        """Build context for chapter generation."""
        target_words, target_min, target_max, remaining_words, remaining_chapters = self._calculate_word_budget(chapter_number)
        context = {
            'chapter_number': chapter_number,
            'total_chapters': self.config.target_chapter_count,
            'target_words': target_words,
            'target_words_min': target_min,
            'target_words_max': target_max,
            'remaining_word_budget': remaining_words,
            'remaining_chapters': remaining_chapters,
            'previous_chapters': self._get_previous_chapters_summary(chapter_number),
            'user_id': self.config.user_id,
            'project_id': self.config.project_id
        }
        
        # Add book bible content if available
        book_bible_file = self.project_path / "book-bible.md"
        if book_bible_file.exists():
            with open(book_bible_file, 'r', encoding='utf-8') as f:
                context['book_bible'] = f.read()
        
        # Add reference files if available
        references_dir = self.project_path / "references"
        if references_dir.exists():
            reference_files = {
                'characters': 'characters.md',
                'outline': 'outline.md',
                'plot_timeline': 'plot-timeline.md',
                'world_building': 'world-building.md',
                'style_guide': 'style-guide.md',
                'canon_log': 'canon-log.md',
                'themes_and_motifs': 'themes-and-motifs.md',
                'target_audience': 'target-audience-profile.md',
                'research_notes': 'research-notes.md',
                'series_bible': 'series-bible.md',
                'director_guide': 'director-guide.md',
                'entity_registry': 'entity-registry.md',
                'relationship_map': 'relationship-map.md',
            }
            
            for ref_type, filename in reference_files.items():
                ref_file = references_dir / filename
                if ref_file.exists():
                    with open(ref_file, 'r', encoding='utf-8') as f:
                        context[f'{ref_type}_reference'] = f.read()
                    self.logger.info(f"Loaded reference file: {filename}")

        # If a continuity manager is available, enrich context for next chapter
        if self.context_manager:
            try:
                next_ctx = self.context_manager.build_next_chapter_context(chapter_number)
                context['continuity'] = next_ctx
                # Provide a concise previous_chapters_summary string from contexts
                context['previous_chapters'] = next_ctx.get('story_so_far', context.get('previous_chapters', ''))
                context['memory_ledger'] = next_ctx.get('memory_ledger', '')
            except Exception as e:
                self.logger.warning(f"Failed to enrich continuity context for chapter {chapter_number}: {e}")

        # Attach chapter objectives from the master plan if available
        chapter_plan = self._get_chapter_plan(chapter_number)
        if chapter_plan:
            context['chapter_objectives'] = chapter_plan.get('objectives', [])
            context['required_plot_points'] = chapter_plan.get('required_plot_points', [])
            context['opening_type'] = chapter_plan.get('opening_type', '')
            context['ending_type'] = chapter_plan.get('ending_type', '')
            context['emotional_arc'] = chapter_plan.get('emotional_arc', '')
            context['focal_characters'] = chapter_plan.get('focal_characters', [])
            context['plan_continuity_requirements'] = chapter_plan.get('continuity_requirements', [])
            context['chapter_plan_summary'] = chapter_plan.get('summary', '')
            context['pov_character'] = chapter_plan.get('pov_character', '')
            context['pov_type'] = chapter_plan.get('pov_type', '')
            context['pov_notes'] = chapter_plan.get('pov_notes', '')
            context['chapter_title'] = chapter_plan.get('title', '')
            context['transition_note'] = chapter_plan.get('transition_note', '')
            # Structural variety fields from enhanced plan
            context['plan_chapter_shape'] = chapter_plan.get('chapter_shape', '')
            context['plan_prose_register'] = chapter_plan.get('prose_register', '')
            context['plan_tension_level'] = chapter_plan.get('tension_level', '')
            context['plan_new_developments'] = chapter_plan.get('new_developments', '')

        # Extract story arcs from book plan metadata
        if self.book_plan_cache:
            context['story_arcs'] = self.book_plan_cache.get('story_arcs', {})

        # Story state snapshot (ledger + continuity + POV bridge)
        try:
            from backend.services.story_state_service import build_story_state_context
            ledger_file = self.state_dir / "chapter-ledger.md"
            ledger_text = ledger_file.read_text(encoding="utf-8") if ledger_file.exists() else ""
            previous_plan = self._get_chapter_plan(max(1, chapter_number - 1)) if chapter_number > 1 else None
            continuity_snapshot = context.get("continuity") if isinstance(context.get("continuity"), dict) else {}
            story_state = build_story_state_context(
                chapter_number=chapter_number,
                chapter_plan=chapter_plan or {},
                previous_plan=previous_plan or {},
                ledger_text=ledger_text,
                continuity_snapshot=continuity_snapshot
            )
            context.update(story_state)
        except Exception as e:
            self.logger.warning(f"Failed to build story state context: {e}")
        
        # Add lightweight opening/ending continuity hints from previous chapters
        try:
            previous_openings: list[str] = []
            previous_endings: list[str] = []
            last_chapter_ending: str = ""

            # Collect first sentence of the last up-to-3 chapters
            for i in range(max(1, chapter_number - 3), chapter_number):
                chapter_file = self.chapters_dir / f"chapter-{i:02d}.md"
                if chapter_file.exists():
                    content = chapter_file.read_text(encoding='utf-8')
                    # First sentence heuristic: split first paragraph by period/question/exclamation
                    first_paragraph = (content.split('\n\n')[0] if content else "").strip()
                    first_sentence = first_paragraph.split('. ')[0].split('! ')[0].split('? ')[0].strip()
                    if first_sentence:
                        previous_openings.append(first_sentence[:200])

            # Get last paragraphs of immediate previous chapter as ending context
            if chapter_number > 1:
                prev_file = self.chapters_dir / f"chapter-{chapter_number-1:02d}.md"
                if prev_file.exists():
                    prev_content = prev_file.read_text(encoding='utf-8')
                    paragraphs = [p.strip() for p in prev_content.split('\n\n') if p.strip()]
                    if paragraphs:
                        # Include last 2-3 paragraphs for better continuity
                        ending_paragraphs = paragraphs[-3:] if len(paragraphs) >= 3 else paragraphs[-2:]
                        last_chapter_ending = "\n\n".join(ending_paragraphs)[-2000:]
            
            # Collect last sentence of the last up-to-3 chapters for ending variety
            for i in range(max(1, chapter_number - 3), chapter_number):
                chapter_file = self.chapters_dir / f"chapter-{i:02d}.md"
                if chapter_file.exists():
                    content = chapter_file.read_text(encoding='utf-8')
                    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
                    if paragraphs:
                        last_para = paragraphs[-1]
                        last_sentence = last_para.split('. ')[-1].split('! ')[-1].split('? ')[-1].strip()
                        if last_sentence:
                            previous_endings.append(last_sentence[:200])

            if previous_openings:
                context['previous_opening_lines'] = previous_openings[-3:]
            if previous_endings:
                context['previous_ending_lines'] = previous_endings[-3:]
            if last_chapter_ending:
                context['last_chapter_ending'] = last_chapter_ending
        except Exception as e:
            self.logger.warning(f"Failed to derive opening/ending continuity hints: {e}")

        # Add repetition risk summary from pattern database if available
        if self.pattern_db:
            try:
                summary = self.pattern_db.get_pattern_summary()
                recent_risks = summary.get("recent_risks", {})
                context["repetition_risks"] = recent_risks
                context["pattern_database_summary"] = self._format_pattern_summary(summary)
            except Exception as e:
                self.logger.warning(f"Failed to load pattern database summary: {e}")

        # Add avoid-phrases list from recent chapters to reduce lexical repetition
        try:
            repetition_allowlist = self._build_repetition_allowlist(context)
            context["repetition_allowlist"] = repetition_allowlist
            avoid_phrases = self._build_avoid_phrases(chapter_number, repetition_allowlist)
            if avoid_phrases:
                context["avoid_phrases"] = avoid_phrases
        except Exception as e:
            self.logger.warning(f"Failed to build avoid phrases list: {e}")

        # Book-wide vocabulary tracker — catches single-word fixation like "battered"
        try:
            overused_words = self._build_overused_words(chapter_number, self._build_repetition_allowlist(context))
            if overused_words:
                context["overused_words"] = overused_words
        except Exception as e:
            self.logger.warning(f"Failed to build overused words list: {e}")

        # Book-wide phrase/gesture tracker — catches multi-word repetition patterns
        try:
            overused_phrases = self._build_overused_phrases(chapter_number, self._build_repetition_allowlist(context))
            if overused_phrases:
                context["overused_phrases"] = overused_phrases
        except Exception as e:
            self.logger.warning(f"Failed to build overused phrases list: {e}")

        # Add cadence targets based on recent chapters
        if self.cadence_analyzer:
            try:
                cadence_targets = self._build_cadence_targets(chapter_number)
                if cadence_targets:
                    context["cadence_targets"] = cadence_targets
            except Exception as e:
                self.logger.warning(f"Failed to build cadence targets: {e}")

        # Add pacing targets based on book position
        try:
            pacing_targets = self._build_pacing_targets(chapter_number)
            if pacing_targets:
                context["pacing_targets"] = pacing_targets
        except Exception as e:
            self.logger.warning(f"Failed to build pacing targets: {e}")

        # Build chapter contract for non-negotiables
        try:
            context["chapter_contract"] = self._build_chapter_contract(context)
        except Exception as e:
            self.logger.warning(f"Failed to build chapter contract: {e}")

        # Add anti-pattern context from previous chapters
        if self.pattern_tracker:
            try:
                anti_pattern = self.pattern_tracker.build_anti_pattern_context(chapter_number)
                if anti_pattern:
                    context["anti_pattern_context"] = anti_pattern
            except Exception as e:
                self.logger.warning(f"Failed to build anti-pattern context: {e}")

        return context

    async def _build_vector_memory_context(self, chapter_number: int, context: Dict[str, Any]) -> Dict[str, Any]:
        """Retrieve vector memory context and store ids for retrieval-first generation."""
        user_id = context.get("user_id") or self.config.user_id
        project_id = context.get("project_id") or self.config.project_id
        if not user_id or not project_id:
            return {}

        try:
            from backend.services.vector_store_service import VectorStoreService
        except Exception:
            try:
                from services.vector_store_service import VectorStoreService
            except Exception:
                return {}

        vector_service = VectorStoreService()
        if not vector_service.available:
            return {}

        try:
            project_store_id = await vector_service.ensure_project_vector_store(project_id, user_id)
            user_store_id = await vector_service.ensure_user_vector_store(user_id)
        except Exception:
            project_store_id = None
            user_store_id = None

        vector_store_ids = [store_id for store_id in [project_store_id, user_store_id] if store_id]
        if not vector_store_ids:
            return {}

        objectives = context.get("chapter_objectives", [])
        focal_characters = context.get("focal_characters", [])
        required_plot_points = context.get("required_plot_points", [])
        query = (
            f"Chapter {chapter_number} context. Objectives: {objectives}. "
            f"Required plot points: {required_plot_points}. "
            f"Focal characters: {focal_characters}. "
            "Return continuity-critical facts, setting details, and character constraints."
        )

        vector_context = ""
        vector_guidelines = ""
        try:
            results = await vector_service.retrieve_chapter_context(project_id, user_id, query, max_results=10)
            vector_context = vector_service.format_results(results, max_chars=2200)
        except Exception:
            vector_context = ""

        try:
            vector_guidelines = await vector_service.retrieve_guidelines(project_id, user_id, max_results=6)
        except Exception:
            vector_guidelines = ""

        # Keep vector_context as a fallback when file_search isn't available

        return {
            "vector_store_ids": vector_store_ids,
            "vector_memory_context": vector_context,
            "vector_memory_guidelines": vector_guidelines,
            # Aliases consumed by LLMOrchestrator prompt builder
            "vector_context": vector_context,
            "vector_guidelines": vector_guidelines
        }

    async def _rewrite_with_canon(self, chapter_content: str, instruction: str, context: Dict[str, Any]) -> str:
        """Rewrite a chapter to align with canon log and references."""
        try:
            from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig
        except Exception:
            from .llm_orchestrator import LLMOrchestrator, RetryConfig

        enable_billing = os.getenv('ENABLE_CREDITS_BILLING', 'false').lower() == 'true'
        orchestrator = LLMOrchestrator(
            retry_config=RetryConfig(max_retries=2),
            user_id=context.get("user_id"),
            enable_billing=enable_billing
        )

        references = context.get("references", {}) or {
            k.replace("_reference", ""): v
            for k, v in (context or {}).items()
            if isinstance(v, str) and k.endswith("_reference")
        }
        canon_source = context.get("canon_log_reference", "")

        result = await orchestrator.rewrite_full_chapter(
            chapter_text=chapter_content,
            instruction=instruction,
            context={
                "book_bible": context.get("book_bible", ""),
                "references": references,
                "canon_source": canon_source,
                "canon_label": "Canon Log",
                "vector_store_ids": context.get("vector_store_ids", []),
                "use_file_search": True,
                "chapter_number": context.get("chapter_number", 0),
            },
            chapter_number=context.get("chapter_number", 0),
        )

        if result.success and result.content.strip():
            return result.content
        return chapter_content

    def _get_chapter_plan(self, chapter_number: int) -> Optional[Dict[str, Any]]:
        """Get chapter plan from cached master plan if available."""
        plan = self.book_plan_cache
        if not plan:
            try:
                if self.book_plan_generator:
                    plan = self.book_plan_generator.load_existing_plan()
                    self.book_plan_cache = plan
            except Exception:
                plan = None

        if not plan:
            return None

        chapters = plan.get("chapters", [])
        for chapter in chapters:
            if chapter.get("chapter_number") == chapter_number:
                return chapter

        return None

    async def _revise_chapter(self, original_content: str, chapter_number: int, quality_result: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Perform a single targeted revision pass based on quality feedback."""
        try:
            from .llm_orchestrator import LLMOrchestrator, RetryConfig
            retry_config = RetryConfig(max_retries=2)
            orchestrator = LLMOrchestrator(retry_config=retry_config)

            # Build a concise critique to feed into revision prompt
            issues = []
            try:
                category_results = quality_result.get('category_results', {})
                for cat, res in category_results.items():
                    if cat == "enhanced_system_compliance" and self._word_count_strictness() != "strict":
                        continue
                    if not res.get('passed', True):
                        issues.append(f"- Improve {cat} (score {res.get('score', 0):.1f} < min {res.get('minimum_required', 0):.1f})")
            except Exception:
                pass
            try:
                plan_res = quality_result.get('category_results', {}).get('plan_compliance', {})
                if plan_res and not plan_res.get('passed', True):
                    issues.append(f"- Plan compliance too low (score {plan_res.get('score', 0):.2f} < min {plan_res.get('minimum_required', 0):.2f})")
            except Exception:
                pass
            if 'brutal_assessment' in quality_result and not quality_result['brutal_assessment'].get('passed', True):
                issues.append("- Raise overall brutal assessment to pass threshold")
            criticals = quality_result.get('critical_failures', []) if isinstance(quality_result.get('critical_failures'), list) else []
            for c in criticals:
                issues.append(f"- Fix critical: {c}")

            critique = "\n".join(issues[:8]) if issues else "- Strengthen clarity, plot advancement, and prose polish"

            revision_system = (
                "You are a professional fiction editor revising a chapter to meet strict quality gates.\n"
                "Preserve story facts and voice. Apply targeted changes only.\n"
                "Eliminate repetition loops and list spirals. Do not repeat words or phrases.\n"
                "Output plain text only (no Markdown formatting: no headings, bullets, blockquotes, emphasis markers like *, **, _, or separators like ---).\n"
                "Use em dashes sparingly."
            )
            revision_user = (
                f"Revise Chapter {chapter_number} to address the issues.\n\n"
                f"CRITIQUE:\n{critique}\n\n"
                "REFERENCE CONTEXT (read-only, do not copy verbatim):\n"
                f"BOOK BIBLE (excerpt):\n{(context.get('book_bible') or '')[:6000]}\n\n"
                f"PREVIOUS CHAPTERS (summary):\n{(context.get('previous_chapters') or '')[:4000]}\n\n"
                f"CHAPTER OBJECTIVES:\n{context.get('chapter_objectives', [])}\n\n"
                f"REQUIRED PLOT POINTS:\n{context.get('required_plot_points', [])}\n\n"
                f"OPENING TYPE REQUIRED: {context.get('opening_type', '')}\n"
                f"ENDING TYPE REQUIRED: {context.get('ending_type', '')}\n"
                f"EMOTIONAL ARC REQUIRED: {context.get('emotional_arc', '')}\n"
                f"FOCAL CHARACTERS: {context.get('focal_characters', [])}\n\n"
                f"MEMORY LEDGER:\n{context.get('memory_ledger', '')}\n\n"
                f"VECTOR MEMORY CONTEXT:\n{context.get('vector_memory_context', '')}\n\n"
                f"VECTOR MEMORY GUIDELINES:\n{context.get('vector_memory_guidelines', '')}\n\n"
                "COMPOSITION TARGETS:\n"
                "- Dialogue: 30% to 70%\n"
                "- Action: 20% to 50%\n"
                "- Internal monologue: 15% to 40%\n"
                "- Description: 10% to 30%\n\n"
                "DIALOGUE TAG VARIETY: Use more than one dialogue tag; avoid dominance by a single tag.\n\n"
                "Draft to revise begins below the delimiter.\n"
                "--- DRAFT START ---\n"
                f"{original_content}\n"
                "--- DRAFT END ---\n\n"
                "Output the fully revised chapter."
            )

            messages = [
                {"role": "system", "content": revision_system},
                {"role": "user", "content": revision_user}
            ]

            response = await orchestrator._make_api_call(
                messages=messages,
                temperature=0.5,
                max_tokens=16000,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                vector_store_ids=context.get("vector_store_ids", [])
            )
            if hasattr(response, "output_text"):
                return response.output_text
            if hasattr(response, "choices"):
                return response.choices[0].message.content
            return original_content
        except Exception as e:
            self.logger.warning(f"Revision failed for Chapter {chapter_number}: {e}; keeping original")
            return original_content
    
    def _get_previous_chapters_summary(self, up_to_chapter: int) -> str:
        """Build a rich summary of previous chapters with opening, key content, and ending."""
        summary_parts = []
        total_chars = 0
        max_total_chars = 12000

        for i in range(1, up_to_chapter):
            chapter_file = self.chapters_dir / f"chapter-{i:02d}.md"
            if not chapter_file.exists():
                continue
            try:
                content = chapter_file.read_text(encoding='utf-8')
            except Exception:
                continue
            if not content.strip():
                continue

            paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
            word_count = len(content.split())

            # For the most recent 2 chapters, include more content
            is_recent = (up_to_chapter - i) <= 2
            if is_recent:
                per_chapter_budget = min(3000, max_total_chars - total_chars)
            else:
                per_chapter_budget = min(800, max_total_chars - total_chars)

            if per_chapter_budget <= 100:
                break

            # Opening (first 1-2 paragraphs)
            opening = "\n\n".join(paragraphs[:2]) if len(paragraphs) >= 2 else (paragraphs[0] if paragraphs else "")
            # Ending (last 1-2 paragraphs)
            ending = "\n\n".join(paragraphs[-2:]) if len(paragraphs) >= 4 else (paragraphs[-1] if paragraphs else "")

            if is_recent and len(paragraphs) > 4:
                # For recent chapters, include opening, middle sample, and ending
                mid_idx = len(paragraphs) // 2
                middle = paragraphs[mid_idx] if mid_idx < len(paragraphs) else ""
                chapter_summary = (
                    f"--- Chapter {i} ({word_count} words) ---\n"
                    f"[OPENING]\n{opening[:per_chapter_budget // 3]}\n"
                    f"[MIDDLE]\n{middle[:per_chapter_budget // 3]}\n"
                    f"[ENDING]\n{ending[:per_chapter_budget // 3]}"
                )
            else:
                chapter_summary = (
                    f"--- Chapter {i} ({word_count} words) ---\n"
                    f"{opening[:per_chapter_budget // 2]}\n...\n"
                    f"{ending[:per_chapter_budget // 2]}"
                )

            chapter_summary = chapter_summary[:per_chapter_budget]
            summary_parts.append(chapter_summary)
            total_chars += len(chapter_summary)

        return "\n\n".join(summary_parts)
    
    async def _generate_real_chapter_content(self, chapter_number: int, context: Dict[str, Any]) -> str:
        """Generate real chapter content using LLM orchestrator."""
        try:
            # Import the real LLM orchestrator
            import sys
            from pathlib import Path
            
            # Add system directory to path for importing
            parent_dir = Path(__file__).parent.parent
            system_dir = parent_dir / "system"
            
            if str(system_dir) not in sys.path:
                sys.path.insert(0, str(system_dir))
            
            from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig
            
            # Initialize LLM orchestrator
            retry_config = RetryConfig(max_retries=3)
            prompts_dir = parent_dir / "prompts"
            resolved_prompts_dir = str(prompts_dir) if prompts_dir.exists() else "prompts"
            
            orchestrator = LLMOrchestrator(
                retry_config=retry_config,
                prompts_dir=resolved_prompts_dir
            )
            
            target_words = context.get('target_words', 3800)
            
            # Add book bible content to context if available
            book_bible_content = context.get('book_bible', '')
            
            # Enhanced context for LLM generation
            enhanced_context = {
                **context,
                "book_bible": book_bible_content,
                "story_context": f"Chapter {chapter_number} of a novel based on the provided book bible",
                "genre": "fiction",
                "target_words": target_words,
                "chapter_number": chapter_number,
            }

            try:
                vector_payload = await self._build_vector_memory_context(chapter_number, context)
                enhanced_context.update(vector_payload)
            except Exception as e:
                self.logger.warning(f"Vector memory unavailable for Chapter {chapter_number}: {e}")
            
            self.logger.info(f"Generating real content for Chapter {chapter_number} using LLM orchestrator")
            
            # Generate chapter using the real LLM system
            result = await orchestrator.generate_chapter(
                chapter_number=chapter_number,
                target_words=target_words,
                stage="complete",
                context=enhanced_context
            )
            
            if result.success:
                self.logger.info(f"Successfully generated Chapter {chapter_number} with {len(result.content.split())} words")
                if result.metadata:
                    context["tokens_used"] = result.metadata.get("tokens_used", context.get("tokens_used", {'prompt': 0, 'completion': 0, 'total': 0}))
                    context["cost_breakdown"] = result.metadata.get("cost_breakdown", context.get("cost_breakdown", {'input_cost': 0.0, 'output_cost': 0.0, 'total_cost': 0.0}))
                    context["generation_time"] = result.metadata.get("generation_time", context.get("generation_time", 0.0))
                    context["retry_attempts"] = result.metadata.get("retry_attempts", context.get("retry_attempts", 0))
                    context["model_used"] = result.metadata.get("model", context.get("model_used", "gpt-4o"))
                return result.content
            else:
                self.logger.error(f"LLM generation failed for Chapter {chapter_number}: {result.error}")
                # Fallback to basic content generation if LLM fails
                return self._generate_fallback_content(chapter_number, context)
                
        except Exception as e:
            self.logger.error(f"Error in real chapter generation for Chapter {chapter_number}: {e}")
            # Fallback to basic content generation
            return self._generate_fallback_content(chapter_number, context)
    
    def _generate_fallback_content(self, chapter_number: int, context: Dict[str, Any]) -> str:
        """Generate fallback content if LLM generation fails."""
        raise RuntimeError(
            f"LLM generation failed for Chapter {chapter_number}. No fallback content will be created."
        )
    
    async def _generate_chapter_with_references(self, chapter_number: int, context: Dict[str, Any]) -> str:
        """Generate chapter using LLM orchestrator with reference files included."""
        try:
            # Import the LLM orchestrator
            import sys
            from pathlib import Path
            
            # Add system directory to path for importing
            parent_dir = Path(__file__).parent.parent
            system_dir = parent_dir / "system"
            
            if str(system_dir) not in sys.path:
                sys.path.insert(0, str(system_dir))
            
            from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig
            
            # Initialize LLM orchestrator
            retry_config = RetryConfig(max_retries=3)
            enable_billing = os.getenv('ENABLE_CREDITS_BILLING', 'false').lower() == 'true'
            prompts_dir = parent_dir / "prompts"
            resolved_prompts_dir = str(prompts_dir) if prompts_dir.exists() else "prompts"

            orchestrator = LLMOrchestrator(
                retry_config=retry_config,
                user_id=context.get("user_id"),
                enable_billing=enable_billing,
                prompts_dir=resolved_prompts_dir
            )
            
            target_words = context.get('target_words', 3800)
            
            self.logger.info(f"Generating Chapter {chapter_number} with reference files using LLM orchestrator")
            
            generation_context = {
                "project_path": str(self.project_path),
                "book_bible": context.get("book_bible", ""),
                "previous_chapters_summary": context.get("previous_chapters", ""),
                "references": context.get("references") or {
                    k.replace("_reference", ""): v
                    for k, v in context.items()
                    if isinstance(v, str) and k.endswith("_reference") and v.strip()
                },
                "target_words_min": context.get("target_words_min"),
                "target_words_max": context.get("target_words_max"),
                "remaining_word_budget": context.get("remaining_word_budget"),
                "remaining_chapters": context.get("remaining_chapters"),
                # Continuity snapshot if available
                "continuity_story_so_far": (context.get("continuity", {}) or {}).get("story_so_far", ""),
                "continuity_unresolved_questions": (context.get("continuity", {}) or {}).get("unresolved_questions", []),
                "continuity_requirements": (context.get("continuity", {}) or {}).get("continuity_requirements", []),
                "continuity_required_plot_advancement": (context.get("continuity", {}) or {}).get("required_plot_advancement", ""),
                "continuity_character_needs": (context.get("continuity", {}) or {}).get("character_development_needs", {}),
                "continuity_themes_to_continue": (context.get("continuity", {}) or {}).get("themes_to_continue", []),
                "pacing_guidance": (context.get("continuity", {}) or {}).get("pacing_guidance", {}),
                "memory_ledger": context.get("memory_ledger", ""),
                "timeline_state": context.get("timeline_state", {}),
                "timeline_constraints": context.get("timeline_constraints", []),
                "chapter_ledger_summary": context.get("chapter_ledger_summary", ""),
                "bridge_requirements": context.get("bridge_requirements", []),
                "pov_character": context.get("pov_character", ""),
                "pov_type": context.get("pov_type", ""),
                "pov_notes": context.get("pov_notes", ""),
                "pov_shift": context.get("pov_shift", False),
                # Opening/ending guardrails
                "previous_opening_lines": context.get("previous_opening_lines", []),
                "previous_ending_lines": context.get("previous_ending_lines", []),
                "last_chapter_ending": context.get("last_chapter_ending", ""),
                # Chapter plan constraints
                "chapter_objectives": context.get("chapter_objectives", []),
                "chapter_plan_summary": context.get("chapter_plan_summary", ""),
                "required_plot_points": context.get("required_plot_points", []),
                "opening_type": context.get("opening_type", ""),
                "ending_type": context.get("ending_type", ""),
                "emotional_arc": context.get("emotional_arc", ""),
                "focal_characters": context.get("focal_characters", []),
                "plan_continuity_requirements": context.get("plan_continuity_requirements", []),
                "chapter_contract": context.get("chapter_contract", ""),
                # Repetition guardrails
                "pattern_database_summary": context.get("pattern_database_summary", ""),
                "repetition_risks": context.get("repetition_risks", {}),
                "avoid_phrases": context.get("avoid_phrases", []),
                "overused_words": context.get("overused_words", []),
                "overused_phrases": context.get("overused_phrases", []),
                "cadence_targets": context.get("cadence_targets", {}),
                "pacing_targets": context.get("pacing_targets", {}),
                # Anti-repetition features
                "anti_pattern_context": context.get("anti_pattern_context", ""),
                "repetition_allowlist": context.get("repetition_allowlist", []),
                # Plan structural fields
                "chapter_title": context.get("chapter_title", ""),
                "transition_note": context.get("transition_note", ""),
                "story_arcs": context.get("story_arcs", {}),
                # Pacing awareness
                "remaining_word_budget": context.get("remaining_word_budget", 0),
                "remaining_chapters": context.get("remaining_chapters", 0),
                "total_chapters": context.get("total_chapters", 0),
            }

            try:
                vector_payload = await self._build_vector_memory_context(chapter_number, context)
                generation_context.update(vector_payload)
            except Exception as e:
                self.logger.warning(f"Vector memory unavailable for Chapter {chapter_number}: {e}")

            # Normalize + clamp context to keep long-run generation stable.
            try:
                from backend.services.context_bundle import normalize_generation_context
                generation_context = normalize_generation_context(generation_context)
            except Exception:
                try:
                    from ..services.context_bundle import normalize_generation_context  # type: ignore
                    generation_context = normalize_generation_context(generation_context)
                except Exception:
                    pass

            # Generate chapter blueprint for structural variety
            try:
                from backend.auto_complete.helpers.chapter_blueprint import (
                    generate_chapter_blueprint, format_blueprint_for_prompt
                )
                chapter_plan = self._get_chapter_plan(chapter_number) or {}
                anti_pattern = context.get("anti_pattern_context", "")
                style_guide = generation_context.get("references", {}).get("style-guide", "") or generation_context.get("references", {}).get("style_guide", "")
                blueprint = await generate_chapter_blueprint(
                    orchestrator=orchestrator,
                    chapter_number=chapter_number,
                    total_chapters=self.config.target_chapter_count,
                    chapter_plan=chapter_plan,
                    book_bible=generation_context.get("book_bible", ""),
                    anti_pattern_context=anti_pattern,
                    style_guide=style_guide,
                )
                generation_context["chapter_blueprint"] = format_blueprint_for_prompt(blueprint)
                generation_context["_blueprint_raw"] = blueprint
                self.logger.info(
                    f"Chapter {chapter_number} blueprint: shape={blueprint.get('chapter_shape')}, "
                    f"register={blueprint.get('prose_register')}, tension={blueprint.get('tension_level')}"
                )
            except Exception as e:
                self.logger.warning(f"Blueprint generation failed for Chapter {chapter_number}: {e}")

            # Director brief to guide first-draft naturalness (validated)
            try:
                brief, validation = await self._get_valid_director_brief(
                    orchestrator=orchestrator,
                    chapter_number=chapter_number,
                    target_words=target_words,
                    context=generation_context
                )
                generation_context["director_brief"] = brief
                generation_context["director_brief_validation"] = validation
                context["director_brief"] = brief
                context["director_brief_validation"] = validation
                if not validation.get("passed"):
                    # Soft-fail: do not block chapter generation on director brief schema issues.
                    # We still persist the validation result so the chapter can be marked as failed
                    # (and visible in the UI) if downstream gates fail.
                    try:
                        missing_sections = validation.get("missing_sections", [])
                        self.logger.warning(
                            f"Director brief validation failed for Chapter {chapter_number}; "
                            f"continuing without blocking. Missing: {missing_sections}"
                        )
                    except Exception:
                        pass
            except Exception as e:
                self.logger.error(f"Director brief generation failed for Chapter {chapter_number}: {e}")
                raise

            # Skeleton + Expand generation (preferred path)
            use_skeleton = os.getenv("USE_SKELETON_EXPAND", "true").lower() == "true"
            if use_skeleton:
                try:
                    from backend.auto_complete.helpers.skeleton_expand import (
                        generate_chapter_skeleton_expand,
                    )
                    # Build book-wide word counts for deterministic cleanup
                    book_word_counts: Dict[str, int] = {}
                    try:
                        for i in range(1, chapter_number):
                            ch_file = self.chapters_dir / f"chapter-{i:02d}.md"
                            if ch_file.exists():
                                ch_text = ch_file.read_text(encoding="utf-8").lower()
                                for w in re.findall(r'\b[a-z]{4,}\b', ch_text):
                                    book_word_counts[w] = book_word_counts.get(w, 0) + 1
                    except Exception:
                        pass
                    generation_context["_book_word_counts"] = book_word_counts
                    generation_context["_chapter_plan"] = self._get_chapter_plan(chapter_number) or {}

                    # Get established facts
                    try:
                        from backend.auto_complete.helpers.skeleton_expand import EstablishedFactsLedger
                        facts_ledger = EstablishedFactsLedger(str(self.project_path))
                        generation_context["established_facts"] = facts_ledger.get_established_context()
                    except Exception:
                        pass

                    chapter_content = await generate_chapter_skeleton_expand(
                        orchestrator=orchestrator,
                        chapter_number=chapter_number,
                        total_chapters=self.config.target_chapter_count,
                        target_words=target_words,
                        context=generation_context,
                        logger=self.logger,
                    )

                    if chapter_content and len(chapter_content.split()) > 200:
                        # Update established facts ledger after successful generation
                        try:
                            facts_ledger = EstablishedFactsLedger(str(self.project_path))
                            new_facts = await facts_ledger.extract_facts_from_chapter(
                                orchestrator, chapter_number, chapter_content,
                                generation_context.get("book_bible", "")
                            )
                            facts_ledger.add_chapter_facts(chapter_number, new_facts)
                        except Exception as facts_err:
                            self.logger.warning(f"Failed to update established facts for Chapter {chapter_number}: {facts_err}")

                        # Build a GenerationResult-like response for downstream compatibility
                        try:
                            context["_last_llm_metadata"] = {
                                "generation_time": 0,
                                "model": orchestrator.model,
                                "word_count": len(chapter_content.split()),
                                "generation_method": "skeleton_expand",
                            }
                        except Exception:
                            pass
                        return chapter_content

                    self.logger.warning(f"Skeleton+expand produced insufficient content for Chapter {chapter_number}; falling back to single-pass.")
                except Exception as skel_err:
                    self.logger.warning(f"Skeleton+expand failed for Chapter {chapter_number}: {skel_err}; falling back to single-pass.")

            # Scene-by-scene generation if enabled and plan exists.
            # If scene planning proves brittle (malformed JSON), we disable it for the remainder
            # of this chapter's attempts (regen rounds included) to avoid repeated failures/cost.
            if (
                self.config.scene_by_scene
                and generation_context.get("chapter_objectives")
                and not generation_context.get("_disable_scene_by_scene")
            ):
                result = await orchestrator.generate_chapter_scene_by_scene(
                    chapter_number=chapter_number,
                    target_words=target_words,
                    context=generation_context
                )
                # Robust fallback: scene-by-scene can fail when the scene plan JSON is malformed.
                # In that case, fall back to a single-pass chapter generation so auto-complete
                # doesn't stall out on a brittle intermediate format.
                if (not result) or (not getattr(result, "success", False)):
                    err = ""
                    try:
                        err = str(getattr(result, "error", "") or "")
                    except Exception:
                        err = ""
                    if "Scene plan JSON parse failed" in err or "scene plan json parse failed" in err:
                        self.logger.warning(
                            f"Scene-by-scene failed for Chapter {chapter_number} ({err}); "
                            "falling back to non-scene-by-scene generation."
                        )
                        try:
                            generation_context["_disable_scene_by_scene"] = True
                        except Exception:
                            pass
                        result = await orchestrator.generate_chapter(
                            chapter_number=chapter_number,
                            target_words=target_words,
                            stage="complete",
                            context=generation_context
                        )
            else:
                result = await orchestrator.generate_chapter(
                    chapter_number=chapter_number,
                    target_words=target_words,
                    stage="complete",
                    context=generation_context
                )
            
            if result.success:
                self.logger.info(f"Successfully generated Chapter {chapter_number} with {len(result.content.split())} words")
                try:
                    context["_last_llm_metadata"] = result.metadata or {}
                except Exception:
                    context["_last_llm_metadata"] = {}
                return result.content
            else:
                # Best-effort behavior:
                # Some generation failures (e.g. specificity gate) should return content (even if failed)
                # so we can persist a failed chapter artifact and surface it in the UI.
                try:
                    if getattr(result, "content", "") and str(getattr(result, "content", "")).strip():
                        self.logger.warning(
                            f"LLM generation reported failure for Chapter {chapter_number} "
                            f"but returned content; continuing with best-effort artifact. Error: {result.error}"
                        )
                        try:
                            context["_last_llm_metadata"] = result.metadata or {}
                        except Exception:
                            context["_last_llm_metadata"] = {}
                        try:
                            context["_last_llm_error"] = result.error
                        except Exception:
                            context["_last_llm_error"] = None
                        return result.content
                except Exception:
                    pass

                self.logger.error(f"LLM generation failed for Chapter {chapter_number}: {result.error}")
                raise RuntimeError(result.error or "LLM generation failed")
                
        except Exception as e:
            self.logger.error(f"Error in chapter generation for Chapter {chapter_number}: {e}")
            raise
    
    async def _assess_chapter_quality(self, chapter_content: str, chapter_number: int, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Assess chapter quality using quality gates and brutal assessment helpers."""
        try:
            # Run quick validation and scoring
            from .helpers.quality_gate_validator import QualityGateValidator
            from .helpers.brutal_assessment_scorer import BrutalAssessmentScorer

            config_candidates = [
                Path(__file__).resolve().parents[2] / "quality-gates.yml",
                Path(__file__).resolve().parents[1] / "quality-gates.yml",
                Path(__file__).resolve().parents[3] / "quality-gates.yml",
                Path("/app/quality-gates.yml"),
                Path("/app/backend/quality-gates.yml")
            ]
            config_path = next((p for p in config_candidates if p.exists()), config_candidates[0])
            validator = QualityGateValidator(str(config_path))
            scorer = BrutalAssessmentScorer()

            word_count = len(chapter_content.split())
            target_words, target_min, target_max, _, _ = self._calculate_word_budget(chapter_number)
            word_count_score = validator.validate_word_count(
                word_count,
                target_range=(target_min, target_max),
                target_words=target_words
            )

            # Build naive category scores seed and let brutal scorer compute weighted results
            category_scores_seed = {
                'enhanced_system_compliance': max(word_count_score.score / 1.0, 0.0),
                'story_function': 8.0,
                'character_authenticity': 8.0,
                'prose_quality': 8.0,
                'reader_engagement': 8.0,
                'emotional_impact': 8.0,
                'pattern_freshness': 8.0
            }

            assessment = scorer.assess_chapter(chapter_content, chapter_number, metadata={'genre': 'fiction'})

            # Build result structure aligned with orchestrator expectations
            result = {
                'overall_score': min(assessment.overall_score / 10.0, 10.0),  # convert 100 scale to ~10
                'word_count': word_count,
                'brutal_assessment': {
                    'score': assessment.overall_score,
                    'level': assessment.assessment_level,
                    'passed': assessment.passed
                },
                'critical_failures': assessment.critical_failures,
                'category_results': {
                    'enhanced_system_compliance': {
                        'score': word_count_score.score,
                        'minimum_required': word_count_score.minimum_required,
                        'passed': word_count_score.passed
                    }
                }
            }

            # Em-dash is a style choice; do not score/gate on it.

            # Content composition check (dialogue/action/internal/description)
            composition = self._evaluate_content_composition(chapter_content, validator.config)
            if composition:
                result['category_results']['content_composition'] = composition

            # Dialogue tag variety check
            dialogue_tag_variety = self._evaluate_dialogue_tag_variety(chapter_content, validator.config)
            if dialogue_tag_variety:
                result['category_results']['dialogue_tag_variety'] = dialogue_tag_variety

            # Trailer-voice / voiceover drift check (fail-fast)
            trailer_voice = self._evaluate_trailer_voice(chapter_content)
            if trailer_voice:
                result['category_results']['trailer_voice'] = trailer_voice
                if not trailer_voice.get("passed", True):
                    result.setdefault("critical_failures", [])
                    result["critical_failures"].append("Trailer-voice narration detected")

            # Summary/montage density check (fail-fast)
            summary_density = self._evaluate_summary_density(chapter_content)
            if summary_density:
                result['category_results']['summary_density'] = summary_density
                if not summary_density.get("passed", True):
                    result.setdefault("critical_failures", [])
                    result["critical_failures"].append("Excessive summary density detected")

            # Inference-chain density check (fail-fast)
            inference_chain = self._evaluate_inference_chain_density(chapter_content)
            if inference_chain:
                result["category_results"]["inference_chain_density"] = inference_chain
                if not inference_chain.get("passed", True):
                    result.setdefault("critical_failures", [])
                    result["critical_failures"].append("Excessive inference-chain narration detected")

            # Markdown artifact check (fail-fast)
            markdown_artifacts = self._evaluate_markdown_artifacts(chapter_content)
            if markdown_artifacts:
                result["category_results"]["markdown_artifacts"] = markdown_artifacts
                if not markdown_artifacts.get("passed", True):
                    result.setdefault("critical_failures", [])
                    result["critical_failures"].append("Markdown formatting artifacts detected")

            # Opening grounding check (fail-fast)
            opening_grounding = self._evaluate_opening_grounding(chapter_content)
            if opening_grounding:
                result["category_results"]["opening_grounding"] = opening_grounding
                if not opening_grounding.get("passed", True):
                    result.setdefault("critical_failures", [])
                    result["critical_failures"].append("Opening lacks concrete scene grounding")

            # Mid-chapter expository drift check (fail-fast)
            expository_drift = self._evaluate_expository_drift(chapter_content)
            if expository_drift:
                result["category_results"]["expository_drift"] = expository_drift
                if not expository_drift.get("passed", True):
                    result.setdefault("critical_failures", [])
                    result["critical_failures"].append("Mid-chapter expository drift detected")

            # Non-gating style signals (for feedback + correlation; do not create new churn)
            try:
                style_signals = {
                    "montage_zoomout": self._style_signal_montage_zoomout(chapter_content),
                    "named_constraint": self._style_signal_named_constraint(chapter_content),
                    "dialogue_leverage": self._style_signal_dialogue_leverage(chapter_content),
                    "tagline_ending": self._style_signal_tagline_ending(chapter_content),
                }
                result["style_signals"] = style_signals
            except Exception as sig_err:
                self.logger.debug(f"Style signals skipped: {sig_err}")

            # Non-gating continuity audits (surface big pitfalls without triggering regen loops)
            try:
                continuity_audits = self._continuity_audits(
                    chapter_content=chapter_content,
                    chapter_number=chapter_number,
                    context=context or {},
                )
                if continuity_audits:
                    result["continuity_audits"] = continuity_audits
            except Exception as cont_err:
                self.logger.debug(f"Continuity audits skipped: {cont_err}")

            # Runaway repetition guard (lexical loops and list spirals)
            repetition_guard = self._evaluate_runaway_repetition(
                chapter_content,
                allowlist=(context or {}).get("repetition_allowlist", [])
            )
            if repetition_guard:
                result['category_results']['runaway_repetition'] = repetition_guard
                if not repetition_guard.get('passed', True):
                    result.setdefault('critical_failures', [])
                    result['critical_failures'].append("Runaway repetition detected")
            
            # Pacing alignment check (based on targets)
            pacing_alignment = self._evaluate_pacing_alignment(chapter_content, chapter_number)
            if pacing_alignment:
                result['category_results']['pacing_alignment'] = pacing_alignment

            # Add repetition freshness score when pattern database is available
            if self.pattern_db:
                try:
                    freshness_score = self.pattern_db.check_freshness_score(chapter_content, chapter_number)
                    result['category_results']['pattern_freshness'] = {
                        'score': freshness_score,
                        'minimum_required': 7.0,
                        'passed': freshness_score >= 7.0
                    }
                except Exception as freshness_err:
                    self.logger.debug(f"Pattern freshness check skipped: {freshness_err}")

            # Repetition risk score from pattern database
            if self.pattern_db:
                try:
                    risk = self.pattern_db.analyze_repetition_risk(chapter_number)
                    risk_score = max(0.0, min(10.0, float(risk.get("score", 0))))
                    result['category_results']['pattern_repetition_risk'] = {
                        'score': risk_score / 10.0,
                        'minimum_required': 0.7,
                        'passed': (risk_score / 10.0) >= 0.7,
                        'details': {
                            'high_risk': risk.get('high_risk', []),
                            'medium_risk': risk.get('medium_risk', [])
                        }
                    }
                except Exception as risk_err:
                    self.logger.debug(f"Pattern repetition risk check skipped: {risk_err}")

            # Cadence similarity check
            if self.cadence_analyzer:
                try:
                    similarity = self.cadence_analyzer.cadence_similarity_score(chapter_number, chapter_content, lookback=3)
                    if similarity is not None:
                        result['category_results']['cadence_variation'] = {
                            'score': 1.0 - similarity,
                            'minimum_required': 0.3,  # require at least 0.3 variation
                            'passed': (1.0 - similarity) >= 0.3,
                            'details': {'similarity': round(similarity, 3)}
                        }
                except Exception as cad_err:
                    self.logger.debug(f"Cadence variation check skipped: {cad_err}")

            # Additional continuity check: opening variety vs. recent chapters
            try:
                # Extract first sentence of current chapter
                first_paragraph = (chapter_content.split('\n\n')[0] if chapter_content else '').strip()
                current_opening = ''
                if first_paragraph:
                    current_opening = first_paragraph.split('. ')[0].split('! ')[0].split('? ')[0].strip().lower()

                # Gather previous openings (last up to 3 chapters)
                previous_openings: list[str] = []
                for i in range(max(1, chapter_number - 3), chapter_number):
                    chapter_file = self.chapters_dir / f"chapter-{i:02d}.md"
                    if chapter_file.exists():
                        content_prev = chapter_file.read_text(encoding='utf-8')
                        prev_para = (content_prev.split('\n\n')[0] if content_prev else '').strip()
                        prev_open = ''
                        if prev_para:
                            prev_open = prev_para.split('. ')[0].split('! ')[0].split('? ')[0].strip().lower()
                        if prev_open:
                            previous_openings.append(prev_open)

                def _token_prefix(s: str, n: int = 7) -> str:
                    tokens = [t for t in s.replace(',', ' ').replace('"', ' ').split() if t]
                    return ' '.join(tokens[:n])

                is_repetitive_opening = False
                if current_opening and previous_openings:
                    cur_prefix = _token_prefix(current_opening)
                    for prev in previous_openings:
                        prev_prefix = _token_prefix(prev)
                        if cur_prefix and prev_prefix and cur_prefix == prev_prefix:
                            is_repetitive_opening = True
                            break

                # Record in category_results to enable targeted revision if needed
                result['category_results']['continuity_opening_variety'] = {
                    'score': 1.0 if not is_repetitive_opening else 0.0,
                    'minimum_required': 1.0,
                    'passed': not is_repetitive_opening
                }
            except Exception as cont_err:
                self.logger.debug(f"Continuity opening variety check skipped: {cont_err}")

            # Additional continuity check: ending variety vs. recent chapters
            try:
                # Extract last sentence of current chapter
                paragraphs_current = [p.strip() for p in chapter_content.split('\n\n') if p.strip()]
                current_ending = ''
                if paragraphs_current:
                    last_para = paragraphs_current[-1]
                    current_ending = last_para.split('. ')[-1].split('! ')[-1].split('? ')[-1].strip().lower()

                previous_endings: list[str] = []
                for i in range(max(1, chapter_number - 3), chapter_number):
                    chapter_file = self.chapters_dir / f"chapter-{i:02d}.md"
                    if chapter_file.exists():
                        content_prev = chapter_file.read_text(encoding='utf-8')
                        paragraphs_prev = [p.strip() for p in content_prev.split('\n\n') if p.strip()]
                        if paragraphs_prev:
                            last_para_prev = paragraphs_prev[-1]
                            prev_end = last_para_prev.split('. ')[-1].split('! ')[-1].split('? ')[-1].strip().lower()
                            if prev_end:
                                previous_endings.append(prev_end)

                def _token_suffix(s: str, n: int = 7) -> str:
                    tokens = [t for t in s.replace(',', ' ').replace('"', ' ').split() if t]
                    return ' '.join(tokens[-n:]) if tokens else ''

                is_repetitive_ending = False
                if current_ending and previous_endings:
                    cur_suffix = _token_suffix(current_ending)
                    for prev in previous_endings:
                        prev_suffix = _token_suffix(prev)
                        if cur_suffix and prev_suffix and cur_suffix == prev_suffix:
                            is_repetitive_ending = True
                            break

                result['category_results']['continuity_ending_variety'] = {
                    'score': 1.0 if not is_repetitive_ending else 0.0,
                    'minimum_required': 1.0,
                    'passed': not is_repetitive_ending
                }
            except Exception as cont_err:
                self.logger.debug(f"Continuity ending variety check skipped: {cont_err}")

            # Tone rotation check
            if self.context_manager:
                try:
                    current_tone = self.context_manager._analyze_emotional_tone(chapter_content)
                    recent_tones = []
                    for i in range(max(1, chapter_number - 3), chapter_number):
                        ctx = self.context_manager.chapter_contexts.get(i)
                        if ctx:
                            recent_tones.append(ctx.emotional_tone)
                    repetitive = current_tone in recent_tones and recent_tones.count(current_tone) >= 2
                    result['category_results']['tone_rotation'] = {
                        'score': 1.0 if not repetitive else 0.0,
                        'minimum_required': 1.0,
                        'passed': not repetitive,
                        'details': {'current_tone': current_tone, 'recent_tones': recent_tones}
                    }
                except Exception as tone_err:
                    self.logger.debug(f"Tone rotation check skipped: {tone_err}")

            # Timeline consistency check
            if self.context_manager:
                try:
                    markers = self.context_manager._extract_time_markers(chapter_content)
                    position = self.context_manager._determine_timeline_position(markers)
                    has_flashback_signal = any(m in ["flashback", "memory", "years ago", "earlier", "yesterday", "previous day"] for m in markers)
                    passed = True
                    if position == "backward" and not has_flashback_signal:
                        passed = False
                    # Enforce forward continuity when prior chapters moved forward
                    recent = self.context_manager.timeline_state.get("events", [])[-3:] if self.context_manager else []
                    last_position = recent[-1].get("relative_time") if recent else "unknown"
                    if last_position == "forward" and position == "unknown":
                        passed = False
                    if last_position == "forward" and position == "backward" and not has_flashback_signal:
                        passed = False
                    result['category_results']['timeline_consistency'] = {
                        'score': 1.0 if passed else 0.0,
                        'minimum_required': 1.0,
                        'passed': passed,
                        'details': {'markers': markers, 'timeline_position': position, 'last_position': last_position}
                    }
                except Exception as time_err:
                    self.logger.debug(f"Timeline consistency check skipped: {time_err}")

            # Scene-level timeline consistency
            if self.context_manager:
                try:
                    scene_markers = self.context_manager._extract_scene_markers(chapter_content)
                    scene_passed = True
                    for scene in scene_markers:
                        pos = scene.get("timeline_position")
                        markers = scene.get("markers", [])
                        has_flashback = any(m in ["flashback", "memory", "years ago", "earlier", "yesterday", "previous day"] for m in markers)
                        if pos == "backward" and not has_flashback:
                            scene_passed = False
                            break
                    result['category_results']['scene_timeline_consistency'] = {
                        'score': 1.0 if scene_passed else 0.0,
                        'minimum_required': 1.0,
                        'passed': scene_passed,
                        'details': {'scene_markers': scene_markers[:6]}
                    }
                except Exception as scene_time_err:
                    self.logger.debug(f"Scene timeline check skipped: {scene_time_err}")

            # Paragraph pattern repetition check
            if self.pattern_db:
                try:
                    patterns = self.pattern_db._extract_paragraph_patterns(chapter_content, chapter_number)
                    threshold = validator.config.get('pattern_tracking', {}).get('paragraph_pattern_frequency', {}).get('failure_threshold', 5)
                    most_common_count = 0
                    if patterns:
                        for pattern in set(patterns):
                            most_common_count = max(most_common_count, patterns.count(pattern))
                    passed = most_common_count < threshold
                    result['category_results']['paragraph_pattern_variety'] = {
                        'score': 1.0 if passed else 0.0,
                        'minimum_required': 1.0,
                        'passed': passed,
                        'details': {'max_pattern_repeats_in_chapter': most_common_count}
                    }
                except Exception as para_err:
                    self.logger.debug(f"Paragraph pattern check skipped: {para_err}")

            # Voice distinctiveness check
            if self.voice_fingerprint_manager:
                try:
                    fingerprints = self.voice_fingerprint_manager.fingerprints_from_text(chapter_number, chapter_content)
                    conflicts = self.voice_fingerprint_manager.chapter_voice_similarity(fingerprints)
                    passed = len(conflicts) == 0
                    result['category_results']['voice_distinctiveness'] = {
                        'score': 1.0 if passed else 0.0,
                        'minimum_required': 1.0,
                        'passed': passed,
                        'details': {'conflicts': conflicts}
                    }

                    # Global voice drift check
                    drift_passed = True
                    drift_details = []
                    for character, fp in fingerprints.items():
                        drift = self.voice_fingerprint_manager.global_character_drift(character, fp, lookback=10)
                        if drift is not None and drift < 0.5:
                            drift_passed = False
                            drift_details.append({"character": character, "similarity": drift})
                    result['category_results']['voice_drift'] = {
                        'score': 1.0 if drift_passed else 0.0,
                        'minimum_required': 1.0,
                        'passed': drift_passed,
                        'details': drift_details
                    }
                except Exception as voice_err:
                    self.logger.debug(f"Voice distinctiveness check skipped: {voice_err}")

            return result
        except Exception as e:
            self.logger.warning(f"Quality assessment helpers failed, using basic scoring: {e}")
            # Basic fallback
            word_count = len(chapter_content.split())
            base_score = 7.5
            target_words, target_min, target_max, _, _ = self._calculate_word_budget(chapter_number)
            if word_count >= target_min:
                base_score += 1.0
            if word_count <= target_max:
                base_score += 0.5
            return {
                'overall_score': min(base_score, 10.0),
                'word_count': word_count,
                'brutal_assessment': {'score': base_score * 10, 'passed': base_score >= self.config.minimum_quality_score},
                'quality_gates': {'passed': 8, 'total': 10}
            }
    
    def _passes_quality_gates(self, quality_result: Dict[str, Any]) -> bool:
        """Check if chapter passes quality gates.
        
        With regen disabled by default, this gate should only reject
        truly catastrophic output — not nitpick individual categories.
        Category results are logged for diagnostics but do not block.
        """
        overall_score = quality_result.get('overall_score', 0)
        if overall_score < self.config.minimum_quality_score:
            return False

        return True

    def _has_fail_fast_failures(self, quality_result: Dict[str, Any]) -> bool:
        """
        Return True when the chapter fails due to high-signal style failures that we prefer to fix by regeneration.
        """
        category_results = quality_result.get("category_results", {}) or {}
        fail_fast_keys = {
            "trailer_voice",
            "summary_density",
            "inference_chain_density",
            "expository_drift",
            "opening_grounding",
            "markdown_artifacts",
        }
        for key in fail_fast_keys:
            result = category_results.get(key)
            if isinstance(result, dict) and result.get("passed") is False:
                return True
        return False

    def _build_regen_feedback(self, quality_result: Dict[str, Any]) -> str:
        """Build short, high-signal feedback for regeneration prompts."""
        category_results = quality_result.get("category_results", {}) if isinstance(quality_result, dict) else {}
        failed = [
            name for name, result in (category_results or {}).items()
            if isinstance(result, dict) and result.get("passed") is False
        ]
        hints: list[str] = []
        if "trailer_voice" in failed:
            hints.append("Remove trailer-voice narration; stay in-scene with concrete actions and sensory anchors.")
        if "summary_density" in failed:
            hints.append("Reduce summary density; dramatize beats in lived time (goal → friction → choice → consequence).")
        if "inference_chain_density" in failed:
            hints.append("Cut inference chains ('which meant/therefore'); show outcomes through action and dialogue.")
        if "opening_grounding" in failed:
            hints.append("Start with physical interaction + sensory cue + immediate pressure; no warmup summary.")
        if "expository_drift" in failed:
            hints.append("Avoid mid-chapter explanatory essays; convert exposition into scenes and interactions.")
        if "markdown_artifacts" in failed:
            hints.append("Output plain text only; no Markdown artifacts.")
        if "runaway_repetition" in failed:
            hints.append("Avoid repeating phrases and list spirals; vary sentence openings and imagery.")

        # Non-gating style signal hints (only when present)
        try:
            style_signals = quality_result.get("style_signals", {}) if isinstance(quality_result, dict) else {}
            if (style_signals.get("montage_zoomout") or {}).get("flagged"):
                hints.append("Avoid montage/zoom-out runs. After any broad framing line, return to a concrete observable detail + a physical action.")
            if (style_signals.get("named_constraint") or {}).get("flagged"):
                hints.append("Do not stack named concepts as lore. When a named org/system appears, show its immediate constraint on the POV’s next action (timer, risk, lockout, demand).")
            if (style_signals.get("dialogue_leverage") or {}).get("flagged"):
                hints.append("Make dialogue carry leverage (ask/refuse/bargain/threat/conceal) rather than supportive/expository check-ins.")
            if (style_signals.get("tagline_ending") or {}).get("flagged"):
                hints.append("Replace tagline/button ending with irreversible action + immediate complication; end in concrete urgency (no ‘the hunt begins’ style lines).")
        except Exception:
            pass
        if not hints and failed:
            hints.append("Fix failed quality categories: " + ", ".join(failed[:8]) + ".")
        if not hints:
            hints.append("Regenerate with stricter scene grounding, specificity, and continuity compliance.")
        return " ".join(hints).strip()

    def _chapter_repair_mode(self) -> str:
        """
        Controls how aggressive post-generation repairs are.
        - mechanical: only fix objective/mechanical issues (default)
        - full: allow stylistic rewrites (legacy)
        """
        mode = str(os.getenv("CHAPTER_REPAIR_MODE", "mechanical")).strip().lower()
        if mode not in {"mechanical", "full"}:
            return "mechanical"
        return mode

    def _enable_llm_revision(self) -> bool:
        """
        If true, allow full-chapter LLM revision passes.
        Default is false to avoid polishing trailer-ish drafts.
        """
        return str(os.getenv("CHAPTER_ENABLE_LLM_REVISION", "false")).strip().lower() in {"1", "true", "yes", "y"}

    def _evaluate_plan_compliance(self, chapter_content: str, objectives: List[str], required_plot_points: List[str]) -> Optional[Dict[str, Any]]:
        """Evaluate whether the chapter complies with the chapter plan."""
        targets = []
        if isinstance(objectives, list):
            targets.extend(objectives)
        if isinstance(required_plot_points, list):
            targets.extend(required_plot_points)

        if not targets:
            return None

        content_lower = chapter_content.lower()
        hits = 0
        total = 0

        for item in targets:
            if not item or not isinstance(item, str):
                continue
            total += 1
            tokens = [t.lower() for t in item.split() if t.isalpha() and len(t) > 3]
            if not tokens:
                continue
            matched = sum(1 for token in tokens if token in content_lower)
            if matched >= max(1, int(len(tokens) * 0.6)):
                hits += 1

        if total == 0:
            return None

        score = hits / total
        return {
            "score": score,
            "minimum_required": 0.7,
            "passed": score >= 0.7
        }

    def _evaluate_bridge_compliance(self, chapter_content: str, bridge_requirements: List[str]) -> Optional[Dict[str, Any]]:
        """Check that bridge requirements are reflected in the chapter."""
        if not bridge_requirements:
            return None
        content_lower = chapter_content.lower()
        hits = 0
        total = 0
        for item in bridge_requirements:
            if not item or not isinstance(item, str):
                continue
            total += 1
            tokens = [t.lower() for t in item.split() if t.isalpha() and len(t) > 3]
            if not tokens:
                continue
            matched = sum(1 for token in tokens if token in content_lower)
            if matched >= max(1, int(len(tokens) * 0.5)):
                hits += 1
        if total == 0:
            return None
        score = hits / total
        return {
            "score": score,
            "minimum_required": 0.6,
            "passed": score >= 0.6
        }

    def _evaluate_pov_compliance(self, chapter_content: str, pov_character: str, pov_type: str) -> Optional[Dict[str, Any]]:
        """Lightweight POV compliance check."""
        if not pov_character and not pov_type:
            return None
        content_lower = chapter_content.lower()
        score = 1.0
        if pov_character and pov_character.strip().lower() not in content_lower:
            score = 0.6
        return {
            "score": score,
            "minimum_required": 0.6,
            "passed": score >= 0.6
        }

    def _build_chapter_contract(self, context: Dict[str, Any]) -> str:
        """Build a non-negotiable contract for the chapter."""
        lines: list[str] = ["NON-NEGOTIABLES:"]
        objectives = context.get("chapter_objectives", [])
        plot_points = context.get("required_plot_points", [])
        bridge_requirements = context.get("bridge_requirements", [])
        plan_requirements = context.get("plan_continuity_requirements", [])
        timeline_constraints = context.get("timeline_constraints", [])
        avoid_phrases = context.get("avoid_phrases", [])
        pov_character = context.get("pov_character", "")
        pov_type = context.get("pov_type", "")
        opening_type = context.get("opening_type", "")
        ending_type = context.get("ending_type", "")
        emotional_arc = context.get("emotional_arc", "")

        if objectives:
            lines.append("Objectives:")
            lines.extend([f"- {str(item).strip()}" for item in objectives[:8]])
        if plot_points:
            lines.append("Required plot points:")
            lines.extend([f"- {str(item).strip()}" for item in plot_points[:8]])
        if pov_character or pov_type:
            pov_line = pov_character.strip() if pov_character else ""
            if pov_type:
                pov_line = f"{pov_line} ({pov_type.strip()})" if pov_line else pov_type.strip()
            lines.append("POV must remain consistent:")
            lines.append(f"- {pov_line}")
        if opening_type:
            lines.append(f"Opening type required: {opening_type}")
        if ending_type:
            lines.append(f"Ending type required: {ending_type}")
        if emotional_arc:
            lines.append(f"Emotional arc required: {emotional_arc}")
        if bridge_requirements:
            lines.append("Bridge requirements:")
            lines.extend([f"- {str(item).strip()}" for item in bridge_requirements[:8]])
        if plan_requirements:
            lines.append("Continuity requirements:")
            lines.extend([f"- {str(item).strip()}" for item in plan_requirements[:8]])
        if timeline_constraints:
            lines.append("Timeline constraints:")
            lines.extend([f"- {str(item).strip()}" for item in timeline_constraints[:6]])
        if avoid_phrases:
            lines.append("Avoid phrases or near-variants:")
            lines.extend([f"- {str(item).strip()}" for item in avoid_phrases[:10]])

        return "\n".join(lines).strip()

    def _validate_director_brief(self, brief: str) -> Dict[str, Any]:
        """Validate the director brief structure."""
        required_sections = {
            "Chapter Intent": ["chapter intent"],
            "Opening Onramp Strategy": ["opening onramp", "onramp strategy"],
            "Scene Cards": ["scene cards"],
            "Freedom Levers": ["freedom levers"],
            "Avoid/Do-Not-Repeat": ["avoid/do-not-repeat", "avoid/do not repeat", "avoid", "do-not-repeat"],
            "Ending Hook": ["ending hook"]
        }
        if not brief or not brief.strip():
            return {"passed": False, "missing_sections": list(required_sections.keys())}

        lowered = brief.lower()
        missing = []
        for section, needles in required_sections.items():
            if not any(n in lowered for n in needles):
                missing.append(section)

        return {"passed": len(missing) == 0, "missing_sections": missing}

    async def _get_valid_director_brief(
        self,
        orchestrator,
        chapter_number: int,
        target_words: int,
        context: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        """Generate and validate a director brief, retrying once if needed."""
        brief = await orchestrator.generate_director_brief(
            chapter_number=chapter_number,
            target_words=target_words,
            context=context
        )
        validation = self._validate_director_brief(brief)
        if validation.get("passed"):
            return brief, validation

        missing = ", ".join(validation.get("missing_sections", []))
        notes = (context.get("director_notes") or "").strip()
        extra = f"Director brief must include: {missing}."
        context = {**context, "director_notes": (notes + "\n" + extra).strip()}

        brief = await orchestrator.generate_director_brief(
            chapter_number=chapter_number,
            target_words=target_words,
            context=context
        )
        validation = self._validate_director_brief(brief)
        return brief, validation

    async def _evaluate_hard_gates(
        self,
        chapter_content: str,
        chapter_number: int,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Evaluate hard gates using deterministic checks and LLM audit."""
        issues: list[Dict[str, Any]] = []
        details: Dict[str, Any] = {}

        # Em-dash is a style choice; do not gate on it.

        # LLM-based hard gate audit for semantic checks
        try:
            from .llm_orchestrator import LLMOrchestrator, RetryConfig
        except Exception:
            from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig

        enable_billing = os.getenv("ENABLE_CREDITS_BILLING", "false").lower() == "true"
        auditor = LLMOrchestrator(
            retry_config=RetryConfig(max_retries=2),
            user_id=context.get("user_id"),
            enable_billing=enable_billing
        )

        pov_character = context.get("pov_character", "")
        pov_type = context.get("pov_type", "")
        contract = context.get("chapter_contract", "")
        book_bible = context.get("book_bible", "")
        continuity_summary = context.get("previous_chapters", "") or context.get("previous_chapters_summary", "")
        required_plot_points = context.get("required_plot_points", [])

        system_prompt = (
            "You are a strict novel QA gatekeeper. Check hard gates only.\n"
            "Return STRICT JSON with keys: passed, gates.\n"
            "gates is an object with boolean fields:\n"
            "- pov_consistency\n"
            "- identity_consistency\n"
            "- ending_obligation\n"
            "- plot_advancement\n"
            "- show_vs_summary_balance\n"
            "- world_marker_presence\n"
            "- scene_function_variety\n"
            "- opening_promise (only required for chapter 1)\n"
            "Also include issues: array of {gate, severity, detail}.\n"
            "Use em dashes sparingly."
        )
        user_prompt = (
            f"CHAPTER NUMBER: {chapter_number}\n"
            f"POV REQUIRED: {pov_character} ({pov_type})\n"
            f"REQUIRED PLOT POINTS: {required_plot_points}\n"
            f"CHAPTER CONTRACT:\n{contract}\n\n"
            f"BOOK BIBLE (excerpt):\n{book_bible[:1800]}\n\n"
            f"PREVIOUS CONTINUITY (excerpt):\n{continuity_summary[:1200]}\n\n"
            f"CHAPTER CONTENT:\n{chapter_content[:8000]}\n\n"
            "Evaluate hard gate compliance."
        )

        def _extract_json(text: str) -> Optional[Dict[str, Any]]:
            if not text:
                return None
            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
                cleaned = re.sub(r"```$", "", cleaned).strip()
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return None
            try:
                return json.loads(cleaned[start:end + 1])
            except Exception:
                return None

        audit = {}
        try:
            response = await auditor._make_api_call(
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0.2,
                max_tokens=700,
                response_format={"type": "json_object"},
                vector_store_ids=context.get("vector_store_ids", []),
                use_file_search=bool(context.get("vector_store_ids"))
            )
            content, _ = auditor._extract_content_and_usage(response)
            audit = _extract_json(content) or {}
        except Exception as e:
            issues.append({"gate": "hard_gate_audit", "severity": "high", "detail": f"Hard gate audit failed: {e}"})

        gates = audit.get("gates") if isinstance(audit, dict) else None
        if isinstance(gates, dict):
            details["hard_gate_gates"] = gates
            for issue in audit.get("issues", []) or []:
                if isinstance(issue, dict):
                    issues.append(issue)

        # Determine overall pass
        passed = len(issues) == 0
        if isinstance(gates, dict):
            required = [
                "pov_consistency",
                "identity_consistency",
                "ending_obligation",
                "plot_advancement",
                "show_vs_summary_balance",
                "world_marker_presence",
                "scene_function_variety"
            ]
            if chapter_number == 1:
                required.append("opening_promise")

            def _normalize_gate(value: Any) -> Optional[bool]:
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    lowered = value.strip().lower()
                    if lowered in {"true", "yes", "y", "pass"}:
                        return True
                    if lowered in {"false", "no", "n", "fail"}:
                        return False
                return None

            for key in required:
                normalized = _normalize_gate(gates.get(key))
                if normalized is None:
                    issues.append({"gate": key, "severity": "high", "detail": "Gate value missing or invalid"})
                    passed = False
                elif normalized is False:
                    passed = False

        return {"passed": passed, "issues": issues, "details": details}

    async def _revise_for_hard_gates(
        self,
        chapter_content: str,
        chapter_number: int,
        hard_gate_result: Dict[str, Any],
        context: Dict[str, Any]
    ) -> str:
        """Targeted revision to address hard gate failures."""
        issues = hard_gate_result.get("issues", [])
        issue_lines = []
        for item in issues:
            if isinstance(item, dict):
                gate = item.get("gate", "issue")
                detail = item.get("detail", "")
                issue_lines.append(f"- {gate}: {detail}")
        if not issue_lines:
            return chapter_content

        try:
            from .llm_orchestrator import LLMOrchestrator, RetryConfig
        except Exception:
            from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig

        enable_billing = os.getenv("ENABLE_CREDITS_BILLING", "false").lower() == "true"
        editor = LLMOrchestrator(
            retry_config=RetryConfig(max_retries=2),
            user_id=context.get("user_id"),
            enable_billing=enable_billing
        )

        system_prompt = (
            "You are a senior fiction editor. Fix ONLY the hard gate failures listed.\n"
            "Preserve plot facts, voice, and outcomes. Use em dashes sparingly.\n"
            "Output plain text only (no Markdown formatting: no headings, bullets, blockquotes, emphasis markers like *, **, _, or separators like ---).\n"
            "Return the full revised chapter."
        )
        user_prompt = (
            f"Hard gate failures:\n{chr(10).join(issue_lines)}\n\n"
            f"CHAPTER CONTRACT:\n{context.get('chapter_contract', '')}\n\n"
            "CHAPTER TEXT:\n"
            "--- START ---\n"
            f"{chapter_content}\n"
            "--- END ---\n"
        )

        response = await editor._make_api_call(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.4,
            max_tokens=16000,
            vector_store_ids=context.get("vector_store_ids", [])
        )
        content, _ = editor._extract_content_and_usage(response)
        return content.strip() or chapter_content

    async def _run_reader_surrogate(
        self,
        chapter_content: str,
        chapter_number: int,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run a reader-surrogate diagnostic pass (no direct edits)."""
        try:
            from .llm_orchestrator import LLMOrchestrator, RetryConfig
        except Exception:
            from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig

        enable_billing = os.getenv("ENABLE_CREDITS_BILLING", "false").lower() == "true"
        analyst = LLMOrchestrator(
            retry_config=RetryConfig(max_retries=2),
            user_id=context.get("user_id"),
            enable_billing=enable_billing
        )

        system_prompt = (
            "You are a cold-reader surrogate evaluating a chapter for confusion, boredom, and stakes clarity.\n"
            "Return STRICT JSON with keys: severity (low|medium|high), confusion_points, boredom_points, stakes_clarity, recommendations.\n"
            "Do not propose new plot points. Use em dashes sparingly."
        )
        user_prompt = (
            f"CHAPTER NUMBER: {chapter_number}\n"
            f"BOOK BIBLE (excerpt):\n{(context.get('book_bible') or '')[:1800]}\n\n"
            f"CHAPTER TEXT:\n{chapter_content[:8000]}\n\n"
            "Evaluate reader experience."
        )

        response = await analyst._make_api_call(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.3,
            max_tokens=700,
            response_format={"type": "json_object"},
            vector_store_ids=context.get("vector_store_ids", []),
            use_file_search=bool(context.get("vector_store_ids"))
        )
        content, _ = analyst._extract_content_and_usage(response)

        def _extract_json(text: str) -> Dict[str, Any]:
            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
                cleaned = re.sub(r"```$", "", cleaned).strip()
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return {}
            try:
                return json.loads(cleaned[start:end + 1])
            except Exception:
                return {}

        return _extract_json(content)

    async def _revise_for_reader_surrogate(
        self,
        chapter_content: str,
        chapter_number: int,
        surrogate_report: Dict[str, Any],
        context: Dict[str, Any]
    ) -> str:
        """Targeted revision based on reader-surrogate diagnostics."""
        recommendations = surrogate_report.get("recommendations", [])
        confusion_points = surrogate_report.get("confusion_points", [])
        boredom_points = surrogate_report.get("boredom_points", [])
        if not recommendations and not confusion_points and not boredom_points:
            return chapter_content

        try:
            from .llm_orchestrator import LLMOrchestrator, RetryConfig
        except Exception:
            from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig

        enable_billing = os.getenv("ENABLE_CREDITS_BILLING", "false").lower() == "true"
        editor = LLMOrchestrator(
            retry_config=RetryConfig(max_retries=2),
            user_id=context.get("user_id"),
            enable_billing=enable_billing
        )

        system_prompt = (
            "You are a senior fiction editor. Improve clarity, momentum, and stakes without changing plot facts.\n"
            "Address confusion and boredom points. Preserve voice. Use em dashes sparingly.\n"
            "Output plain text only (no Markdown formatting: no headings, bullets, blockquotes, emphasis markers like *, **, _, or separators like ---).\n"
            "Return the full revised chapter."
        )
        user_prompt = (
            f"READER SURROGATE FINDINGS:\n"
            f"Confusion points: {confusion_points}\n"
            f"Boredom points: {boredom_points}\n"
            f"Recommendations: {recommendations}\n\n"
            f"CHAPTER CONTRACT:\n{context.get('chapter_contract', '')}\n\n"
            "CHAPTER TEXT:\n"
            "--- START ---\n"
            f"{chapter_content}\n"
            "--- END ---\n"
        )

        response = await editor._make_api_call(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.4,
            max_tokens=16000,
            vector_store_ids=context.get("vector_store_ids", [])
        )
        content, _ = editor._extract_content_and_usage(response)
        return content.strip() or chapter_content

    async def _final_gate_lock(
        self,
        chapter_content: str,
        chapter_number: int,
        context: Dict[str, Any],
        quality_result: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
        """Final gate lock to prevent post-gate drift."""
        max_passes = max(1, int(self.config.max_repair_passes))
        hard_gate_result: Dict[str, Any] = {}
        for _ in range(max_passes):
            hard_gate_result = await self._evaluate_hard_gates(chapter_content, chapter_number, context)
            quality_result = await self._assess_chapter_quality(chapter_content, chapter_number, context)
            quality_result.setdefault("category_results", {})["hard_gates"] = {
                "score": 1.0 if hard_gate_result.get("passed") else 0.0,
                "minimum_required": 1.0,
                "passed": hard_gate_result.get("passed", False),
                "details": hard_gate_result.get("details", {})
            }

            # Consistency/canon re-check
            if os.getenv("ENABLE_CONSISTENCY_CHECK", "false").lower() == "true":
                try:
                    from backend.services.consistency_check_service import check_chapter_consistency
                    try:
                        from backend.services.chapter_context_builder import references_from_context, get_canon_log
                        references = references_from_context(context)
                        canon_log = get_canon_log(references) or context.get("canon_log_reference", "")
                    except Exception:
                        canon_log = context.get("canon_log_reference", "")
                        references = context.get("references", {}) or {
                            k.replace("_reference", ""): v
                            for k, v in (context or {}).items()
                            if isinstance(v, str) and k.endswith("_reference")
                        }
                    consistency = await check_chapter_consistency(
                        chapter_number=chapter_number,
                        chapter_content=chapter_content,
                        book_bible=context.get("book_bible", ""),
                        references=references,
                        canon_log=canon_log,
                        vector_store_ids=context.get("vector_store_ids", []),
                        user_id=context.get("user_id")
                    )
                    quality_result.setdefault("category_results", {})["consistency_check"] = {
                        "score": 1.0 if consistency.get("severity") in {"low", "medium"} else 0.0,
                        "minimum_required": 1.0,
                        "passed": consistency.get("severity") in {"low", "medium"},
                        "details": consistency
                    }
                    if consistency.get("severity") == "high" and consistency.get("rewrite_instruction"):
                        chapter_content = await self._rewrite_with_canon(
                            chapter_content,
                            consistency["rewrite_instruction"],
                            context
                        )
                        continue
                except Exception as consistency_err:
                    quality_result.setdefault("category_results", {})["consistency_check"] = {
                        "score": 0.0,
                        "minimum_required": 1.0,
                        "passed": False,
                        "details": {"error": str(consistency_err)}
                    }

            if hard_gate_result.get("passed") and self._passes_quality_gates(quality_result):
                return chapter_content, quality_result, hard_gate_result

            if not hard_gate_result.get("passed"):
                chapter_content = await self._revise_for_hard_gates(chapter_content, chapter_number, hard_gate_result, context)
                continue

            if self.config.quality_gates_enabled and not self._passes_quality_gates(quality_result):
                # Do not try to "polish" fail-fast style failures here; those should be handled by regeneration upstream.
                if not self._has_fail_fast_failures(quality_result):
                    chapter_content = await self._apply_targeted_repairs(chapter_content, chapter_number, quality_result, context)
                continue

        return chapter_content, quality_result, hard_gate_result

    async def evaluate_candidate(
        self,
        chapter_content: str,
        chapter_number: int,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Evaluate a candidate chapter for selection and reranking."""
        quality_result = await self._assess_chapter_quality(chapter_content, chapter_number, context)
        plan_compliance = self._evaluate_plan_compliance(
            chapter_content,
            objectives=context.get("chapter_objectives", []),
            required_plot_points=context.get("required_plot_points", [])
        )
        bridge_compliance = self._evaluate_bridge_compliance(
            chapter_content,
            bridge_requirements=context.get("bridge_requirements", [])
        )
        pov_compliance = self._evaluate_pov_compliance(
            chapter_content,
            pov_character=context.get("pov_character", ""),
            pov_type=context.get("pov_type", "")
        )

        score = quality_result.get("overall_score", 0.0)
        if plan_compliance:
            score += plan_compliance.get("score", 0.0) * 2.0
        if bridge_compliance:
            score += bridge_compliance.get("score", 0.0) * 1.0
        if pov_compliance:
            score += pov_compliance.get("score", 0.0) * 0.5

        # Small, non-gating penalties to prefer candidates that avoid trailer-compression patterns.
        try:
            ss = quality_result.get("style_signals", {}) if isinstance(quality_result, dict) else {}
            if (ss.get("montage_zoomout") or {}).get("flagged"):
                score -= 0.25
            if (ss.get("named_constraint") or {}).get("flagged"):
                score -= 0.20
            if (ss.get("dialogue_leverage") or {}).get("flagged"):
                score -= 0.20
            if (ss.get("tagline_ending") or {}).get("flagged"):
                score -= 0.30
        except Exception:
            pass

        return {
            "score": score,
            "quality_result": quality_result,
            "plan_compliance": plan_compliance,
            "bridge_compliance": bridge_compliance,
            "pov_compliance": pov_compliance
        }

    def _evaluate_content_composition(self, chapter_content: str, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Evaluate dialogue/action/internal/description composition against targets."""
        composition_cfg = (config or {}).get('content_composition', {})
        if not composition_cfg:
            return None

        total_words = max(1, len(chapter_content.split()))

        dialogue_words = 0
        internal_words = 0
        action_words = 0
        description_words = 0

        action_keywords = {
            'ran', 'walked', 'moved', 'grabbed', 'pulled', 'pushed', 'opened', 'closed',
            'turned', 'looked', 'entered', 'left', 'hit', 'kicked', 'drove', 'rushed',
            'stopped', 'paused', 'stood', 'sat', 'jumped'
        }
        internal_keywords = {
            'thought', 'felt', 'wondered', 'realized', 'remembered', 'decided',
            'considered', 'feared', 'hoped', 'knew', 'understood'
        }

        paragraphs = [p for p in chapter_content.split('\n\n') if p.strip()]
        for paragraph in paragraphs:
            words = paragraph.split()
            word_count = len(words)
            if word_count == 0:
                continue

            is_dialogue = '"' in paragraph or '“' in paragraph or '”' in paragraph
            if is_dialogue:
                dialogue_words += word_count
                continue

            lower = paragraph.lower()
            if any(k in lower for k in internal_keywords):
                internal_words += word_count
                continue

            if any(k in lower for k in action_keywords):
                action_words += word_count
                continue

            description_words += word_count

        def pct(part: int) -> float:
            return (part / total_words) * 100.0

        dialogue_pct = pct(dialogue_words)
        action_pct = pct(action_words)
        internal_pct = pct(internal_words)
        description_pct = pct(description_words)

        def in_range(value: float, min_v: float, max_v: float) -> bool:
            return min_v <= value <= max_v

        requirements = {
            'dialogue': composition_cfg.get('dialogue_percentage', {}),
            'action': composition_cfg.get('action_percentage', {}),
            'internal': composition_cfg.get('internal_monologue_percentage', {}),
            'description': composition_cfg.get('description_percentage', {})
        }

        passed = True
        for key, req in requirements.items():
            if not req:
                continue
            value = {
                'dialogue': dialogue_pct,
                'action': action_pct,
                'internal': internal_pct,
                'description': description_pct
            }[key]
            if not in_range(value, req.get('minimum', 0), req.get('maximum', 100)):
                passed = False
                break

        score = 1.0 if passed else 0.0
        return {
            'score': score,
            'minimum_required': 1.0,
            'passed': passed,
            'details': {
                'dialogue_pct': round(dialogue_pct, 1),
                'action_pct': round(action_pct, 1),
                'internal_pct': round(internal_pct, 1),
                'description_pct': round(description_pct, 1)
            }
        }

    def _evaluate_dialogue_tag_variety(self, chapter_content: str, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Evaluate dialogue tag variety against thresholds."""
        tracking_cfg = (config or {}).get('pattern_tracking', {})
        variety_cfg = tracking_cfg.get('dialogue_tag_variety', {})
        if not variety_cfg:
            return None

        import re
        tag_patterns = [
            r'"[^"]*"\s*,?\s*(\w+\s+(?:said|asked|replied|answered|whispered|shouted|murmured|called|declared|stated|exclaimed|muttered|growled|sighed))',
            r'(\w+\s+(?:said|asked|replied|answered|whispered|shouted|murmured|called|declared|stated|exclaimed|muttered|growled|sighed))\s*,?\s*"[^"]*"'
        ]

        tags: list[str] = []
        for pattern in tag_patterns:
            tags.extend([m.strip().lower() for m in re.findall(pattern, chapter_content, re.IGNORECASE)])

        if not tags:
            return {
                'score': 1.0,
                'minimum_required': 1.0,
                'passed': True,
                'details': {'unique_tags': 0, 'single_tag_pct': 0.0, 'note': 'action_beats_preferred'}
            }

        unique_tags = len(set(tags))
        most_common = max(set(tags), key=tags.count)
        single_tag_pct = (tags.count(most_common) / len(tags)) * 100.0

        passed = (
            unique_tags >= variety_cfg.get('minimum_unique_tags', 0)
            and single_tag_pct <= variety_cfg.get('maximum_single_tag_percentage', 100)
        )
        return {
            'score': 1.0 if passed else 0.0,
            'minimum_required': 1.0,
            'passed': passed,
            'details': {
                'unique_tags': unique_tags,
                'single_tag_pct': round(single_tag_pct, 1)
            }
        }

    def _evaluate_trailer_voice(self, chapter_content: str) -> Optional[Dict[str, Any]]:
        """
        Deterministic check for trailer/voiceover narration patterns.

        This is intentionally cross-genre: it targets *voiceover framing* and *narrator-summary stingers*,
        not specific vocabulary that might be valid in some genres (fantasy, epic, etc.).
        """
        if not chapter_content or not chapter_content.strip():
            return None

        text_lower = chapter_content.lower()
        strong_phrases = [
            "in a world where",
            "nothing would ever be the same",
            "this was the moment",
            "little did",
            "no one could have",
            "everything changed",
            "against all odds",
            "now more than ever",
            "the stakes had never been higher",
            "marked the beginning",
        ]
        narrator_summary_phrases = [
            "this was more than",
            "this wasn't just",
            "it wasn't just",
            "it was more than",
            "would change everything",
            "would change it all",
        ]
        # Weaker patterns can appear naturally; require multiple hits before failing.
        weak_phrases = [
            "what happens when",
            "the kind of thing",
            "it was the kind of",
            "a day like any other",
        ]

        strong_hits = [p for p in strong_phrases if p in text_lower]
        summary_hits = [p for p in narrator_summary_phrases if p in text_lower]
        weak_hit_count = sum(text_lower.count(p) for p in weak_phrases)

        # Sentence-openers that indicate voiceover interpretation rather than scene-time.
        opener_hits = len(re.findall(
            r"(?m)^\s*(this meant|this was|that meant|that was)\b",
            chapter_content
        ))

        passed = (len(strong_hits) == 0 and len(summary_hits) <= 1 and weak_hit_count < 3 and opener_hits < 3)
        return {
            "score": 1.0 if passed else 0.0,
            "minimum_required": 1.0,
            "passed": passed,
            "details": {
                "strong_hits": strong_hits[:5],
                "summary_hits": summary_hits[:5],
                "weak_hit_count": weak_hit_count,
                "sentence_opener_hits": opener_hits
            }
        }

    def _evaluate_summary_density(self, chapter_content: str) -> Optional[Dict[str, Any]]:
        """
        Deterministic check for montage/summary drift (too many paragraphs that report/interpret vs dramatize).

        This is not trying to ban interiority; it flags runs of abstract recap paragraphs without action/dialogue/sensory anchors.
        """
        if not chapter_content or not chapter_content.strip():
            return None

        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", chapter_content) if p.strip()]
        if len(paragraphs) < 4:
            return {
                "score": 1.0,
                "minimum_required": 1.0,
                "passed": True,
                "details": {"paragraphs": len(paragraphs), "summary_like": 0, "ratio": 0.0}
            }

        summary_verbs = [
            "was", "were", "had been", "felt", "realized", "knew", "seemed",
            "understood", "remembered", "noticed", "thought", "decided",
        ]
        action_markers = [
            "open", "opened", "close", "closed", "grab", "grabbed", "pull", "pulled",
            "push", "pushed", "turn", "turned", "walk", "walked", "ran", "sat", "stood",
            "entered", "left", "said", "asked", "replied",
        ]
        sensory_markers = [
            "saw", "heard", "smelled", "taste", "tasted", "touch", "touched",
            "cold", "warm", "hot", "sharp", "rough", "slick", "wet", "dry",
        ]

        summary_like_idx: list[int] = []
        max_consecutive = 0
        current_consecutive = 0

        for idx, p in enumerate(paragraphs, start=1):
            pl = p.lower()
            has_dialogue = ('"' in p) or ("“" in p) or ("”" in p)
            if has_dialogue:
                current_consecutive = 0
                continue

            summary_hits = sum(pl.count(v) for v in summary_verbs)
            has_action = any(re.search(rf"\b{re.escape(a)}\b", pl) for a in action_markers)
            has_sensory = any(re.search(rf"\b{re.escape(s)}\b", pl) for s in sensory_markers)

            is_summary_like = (summary_hits >= 4 and not has_action and not has_sensory)
            if is_summary_like:
                summary_like_idx.append(idx)
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 0

        ratio = len(summary_like_idx) / max(1, len(paragraphs))
        passed = True
        # Fail if too many summary-like paragraphs, or if there's a long consecutive run.
        if len(paragraphs) >= 6 and ratio > 0.35:
            passed = False
        if max_consecutive >= 3:
            passed = False

        return {
            "score": 1.0 if passed else 0.0,
            "minimum_required": 1.0,
            "passed": passed,
            "details": {
                "paragraphs": len(paragraphs),
                "summary_like": len(summary_like_idx),
                "summary_like_ratio": round(ratio, 3),
                "max_consecutive_summary_like": max_consecutive,
                "flagged_paragraph_indices": summary_like_idx[:10],
            }
        }

    def _style_signal_montage_zoomout(self, chapter_content: str) -> Dict[str, Any]:
        """
        Non-gating, deterministic signal for montage-like escalation.
        Flags runs of consecutive “zoom-out” sentences (news/socials/everywhere/legend framing),
        which often reads as trailer compression across genres.
        """
        excerpt = " ".join(chapter_content.split()[:900])  # early window (~900 words)
        if not excerpt.strip():
            return {"flagged": False, "max_consecutive": 0, "hits": 0, "examples": []}

        # Lightweight sentence split (good enough for signal; avoid heavy NLP).
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", excerpt) if s.strip()]
        zoom_markers = [
            "the news", "news", "socials", "social media", "feeds", "timelines",
            "everywhere", "all over", "across the city", "the internet",
            "the legend", "the myth", "everyone", "no one", "people were",
            "went viral", "world", "everybody",
        ]
        examples: list[str] = []
        max_consecutive = 0
        current = 0
        hits = 0
        for s in sentences[:40]:
            sl = s.lower()
            is_zoom = any(m in sl for m in zoom_markers)
            if is_zoom:
                hits += 1
                current += 1
                max_consecutive = max(max_consecutive, current)
                if len(examples) < 3:
                    examples.append(s[:180])
            else:
                current = 0
        return {
            "flagged": bool(max_consecutive >= 2),
            "max_consecutive": int(max_consecutive),
            "hits": int(hits),
            "examples": examples,
        }

    def _style_signal_named_constraint(self, chapter_content: str) -> Dict[str, Any]:
        """
        Non-gating, deterministic signal for named-thing stacking without immediate constraint.
        Heuristic: clusters of capitalized tokens not followed by constraint language.
        """
        excerpt = " ".join(chapter_content.split()[:900])
        if not excerpt.strip():
            return {"flagged": False, "clusters": 0, "unconstrained": 0, "examples": []}

        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", excerpt) if s.strip()]
        stop = {
            "I", "The", "A", "An", "He", "She", "They", "We", "It", "His", "Her", "My", "Our", "And", "But", "In",
            "On", "At", "As", "If", "When", "After", "Before", "Because",
        }
        constraint_markers = [
            "must", "can't", "cannot", "won't", "need", "have to", "deadline", "due", "late", "timer", "minutes",
            "locked", "lockout", "alert", "flag", "blocked", "freeze", "ban", "audit", "tracked", "ping", "message",
            "call", "knock", "sirens", "police", "risk", "threat", "fine", "eviction", "rent",
        ]
        examples: list[str] = []
        clusters = 0
        unconstrained = 0

        def _named_tokens(sentence: str) -> list[str]:
            toks = re.findall(r"\b[A-Z][A-Za-z0-9]{2,}\b|\b[A-Z]{3,}\b", sentence)
            # drop first token (sentence-start capitalization noise) and stop words
            toks2: list[str] = []
            for i, t in enumerate(toks):
                if i == 0:
                    continue
                if t in stop:
                    continue
                toks2.append(t)
            return toks2

        for i, s in enumerate(sentences[:40]):
            named = _named_tokens(s)
            if len(named) >= 2:
                clusters += 1
                look = (s + " " + (sentences[i + 1] if i + 1 < len(sentences) else "")).lower()
                constrained = any(m in look for m in constraint_markers)
                if not constrained:
                    unconstrained += 1
                    if len(examples) < 3:
                        examples.append(s[:180])

        return {
            "flagged": bool(unconstrained >= 2),
            "clusters": int(clusters),
            "unconstrained": int(unconstrained),
            "examples": examples,
        }

    def _style_signal_dialogue_leverage(self, chapter_content: str) -> Dict[str, Any]:
        """
        Non-gating, deterministic signal for dialogue without leverage (supportive/expository exchange).
        Looks only at the early window.
        """
        excerpt = " ".join(chapter_content.split()[:650])
        if not excerpt.strip():
            return {"flagged": False, "dialogue_present": False, "leverage_hits": 0, "examples": []}

        dialogue_present = ('"' in excerpt) or ("“" in excerpt) or ("”" in excerpt)
        if not dialogue_present:
            return {"flagged": False, "dialogue_present": False, "leverage_hits": 0, "examples": []}

        leverage_markers = [
            "?", "if ", "unless", "or else", "need", "must", "can't", "cannot", "won't", "don't",
            "promise", "tell me", "give me", "stop", "leave", "pay", "offer", "trade", "deal",
            "why", "how", "when",
        ]
        lines = [l.strip() for l in excerpt.splitlines() if l.strip()]
        examples: list[str] = []
        hits = 0
        for l in lines[:40]:
            ll = l.lower()
            if ('"' in l) or ("“" in l) or ("”" in l):
                if any(m in ll for m in leverage_markers):
                    hits += 1
                if len(examples) < 3:
                    examples.append(l[:160])
        return {
            "flagged": bool(hits == 0),
            "dialogue_present": True,
            "leverage_hits": int(hits),
            "examples": examples,
        }

    def _style_signal_tagline_ending(self, chapter_content: str) -> Dict[str, Any]:
        """
        Non-gating, deterministic signal for tagline/button endings.
        """
        if not chapter_content or not chapter_content.strip():
            return {"flagged": False, "hits": [], "ending_excerpt": ""}

        tail = chapter_content.strip()[-800:]
        tail_lower = tail.lower()
        patterns = [
            "the hunt begins",
            "this was only the beginning",
            "only the beginning",
            "everything changed",
            "no turning back",
            "the journey begins",
            "it had begun",
            "the threshold",
            "odyssey",
        ]
        hits = [p for p in patterns if p in tail_lower]
        # Take last 3 non-empty lines as a human-readable excerpt.
        lines = [l.strip() for l in chapter_content.splitlines() if l.strip()]
        ending_excerpt = "\n".join(lines[-3:])[-300:]
        return {"flagged": bool(hits), "hits": hits[:4], "ending_excerpt": ending_excerpt}

    def _continuity_audits(self, chapter_content: str, chapter_number: int, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Non-gating continuity audits to surface common multi-chapter failures:
        - recap/restart openings
        - disconnected opening vs previous ending
        - basic timeline discontinuity signals

        These are advisory signals only (do NOT feed into category_results / gating).
        """
        if not chapter_content or not chapter_content.strip():
            return {}
        if int(chapter_number or 0) <= 1:
            return {}

        # Load recent previous chapter texts if available (for lexical overlap checks).
        prev_texts: list[str] = []
        try:
            for i in range(max(1, int(chapter_number) - 2), int(chapter_number)):
                p = self.chapters_dir / f"chapter-{i:02d}.md"
                if p.exists():
                    t = p.read_text(encoding="utf-8")
                    if t and t.strip():
                        prev_texts.append(t)
        except Exception:
            prev_texts = []

        # Best-effort previous ending (prefer context, fallback to file tail).
        previous_ending = (context or {}).get("last_chapter_ending", "") or ""
        if not previous_ending and prev_texts:
            try:
                paragraphs = [p.strip() for p in prev_texts[-1].split("\n\n") if p.strip()]
                previous_ending = paragraphs[-1] if paragraphs else ""
            except Exception:
                previous_ending = ""

        return {
            "recap_restart": self._continuity_audit_recap_restart(chapter_content, prev_texts),
            "opening_bridge": self._continuity_audit_opening_bridge(chapter_content, previous_ending),
            "timeline_hints": self._continuity_audit_timeline_hints(chapter_content),
        }

    def _continuity_audit_recap_restart(self, chapter_content: str, previous_texts: List[str]) -> Dict[str, Any]:
        """
        Detect likely recap/restart by measuring early lexical overlap with recent chapters and
        scanning for explicit recap phrases. Genre-agnostic.
        """
        if not previous_texts:
            return {"flagged": False, "reason": "no_previous_texts"}

        current_start = " ".join(chapter_content.split()[:550]).lower()
        previous_blob = " ".join(previous_texts[-2:]).lower()

        # Tokenize (skip short words to reduce false positives).
        current_words = set(re.findall(r"\b[a-z]{4,}\b", current_start))
        prev_words = set(re.findall(r"\b[a-z]{4,}\b", previous_blob))
        overlap_ratio = 0.0
        if current_words:
            overlap_ratio = len(current_words & prev_words) / max(1, len(current_words))

        recap_patterns = [
            r"\bas we (?:saw|learned|discovered|found out)\b",
            r"\b(?:last|previous|earlier) (?:chapter|time|day|week)\b",
            r"\bto (?:recap|summarize|review)\b",
            r"\b(?:remember|recall) that\b",
            r"\bas (?:mentioned|discussed|established) (?:before|earlier|previously)\b",
        ]
        recap_hits = sum(1 for pat in recap_patterns if re.search(pat, current_start, re.IGNORECASE))

        # Conservative thresholds; this is advisory, not a gate.
        flagged = bool(overlap_ratio >= 0.42 or recap_hits >= 2)
        return {
            "flagged": flagged,
            "overlap_ratio": round(overlap_ratio, 3),
            "recap_phrase_hits": int(recap_hits),
            "thresholds": {"overlap_ratio": 0.42, "recap_phrase_hits": 2},
        }

    def _continuity_audit_opening_bridge(self, chapter_content: str, previous_ending: str) -> Dict[str, Any]:
        """
        Detect likely disconnected opening: no shared entities with previous ending and no clear time-skip signal.
        """
        start = " ".join(chapter_content.split()[:320])
        if not start.strip():
            return {"flagged": False, "reason": "empty_opening"}
        if not previous_ending or not previous_ending.strip():
            return {"flagged": False, "reason": "no_previous_ending"}

        start_lower = start.lower()
        ending_text = " ".join(previous_ending.split()[-220:])

        # Named entity overlap (very lightweight): capitalized tokens (names/places/orgs).
        prev_entities = set(re.findall(r"\b[A-Z][a-z]{2,}\b", ending_text))
        cur_entities = set(re.findall(r"\b[A-Z][a-z]{2,}\b", start))
        entity_overlap = len(prev_entities & cur_entities)

        time_jump_patterns = [
            r"\b(?:hours|days|weeks|months|years)\s+(?:later|after)\b",
            r"\b(?:the next|following)\s+(?:day|morning|evening|night)\b",
            r"\bmeanwhile\b",
            r"\belsewhere\b",
        ]
        time_jump_signals = sum(1 for pat in time_jump_patterns if re.search(pat, start_lower, re.IGNORECASE))

        # If there are zero shared entities and no time-skip cues, the opening may have restarted.
        flagged = bool(entity_overlap == 0 and time_jump_signals == 0 and len(ending_text.split()) >= 40)
        return {
            "flagged": flagged,
            "entity_overlap": int(entity_overlap),
            "time_jump_signals": int(time_jump_signals),
        }

    def _continuity_audit_timeline_hints(self, chapter_content: str) -> Dict[str, Any]:
        """
        Basic timeline drift hints. Non-gating.
        """
        start = " ".join(chapter_content.split()[:650]).lower()
        if not start.strip():
            return {"flagged": False, "reason": "empty"}

        backward_markers = ["earlier", "before", "previously", "yesterday", "last week", "years ago"]
        flashback_signals = ["flashback", "memory", "remembered", "recalled"]
        forward_markers = ["later", "next", "following", "after", "then", "soon"]

        has_backward = any(m in start for m in backward_markers)
        has_flashback = any(m in start for m in flashback_signals)
        has_forward = any(m in start for m in forward_markers)

        flagged = bool(has_backward and not has_flashback and not has_forward)
        return {
            "flagged": flagged,
            "has_backward_marker": bool(has_backward),
            "has_flashback_signal": bool(has_flashback),
            "has_forward_marker": bool(has_forward),
        }

    def _evaluate_inference_chain_density(self, chapter_content: str) -> Optional[Dict[str, Any]]:
        """
        Deterministic check for over-explaining via explicit inference chains.
        This is cross-genre: it targets *explanatory linking phrases* that read like voiceover.
        """
        if not chapter_content or not chapter_content.strip():
            return None

        text_lower = chapter_content.lower()
        # Explicit inference-linkers that often create trailer/summary narration.
        phrases = [
            "which meant",
            "which suggests",
            "which suggested",
            "which implies",
            "which implied",
            "therefore",
            "as a result",
            "this meant",
            "that meant",
            "this was",
            "that was",
        ]
        hits = sum(text_lower.count(p) for p in phrases)
        words = max(1, len(chapter_content.split()))
        per_1k = (hits / words) * 1000.0

        # Also count repeated sentence-openers that are explanatory, not scene-time.
        opener_hits = len(re.findall(r"(?m)^\s*(this meant|this was|that meant|that was)\b", chapter_content))

        # Pass unless it becomes a dominant habit.
        passed = True
        if hits >= 6:
            passed = False
        if per_1k >= 1.6:
            passed = False
        if opener_hits >= 4:
            passed = False

        return {
            "score": 1.0 if passed else 0.0,
            "minimum_required": 1.0,
            "passed": passed,
            "details": {
                "hits": hits,
                "hits_per_1k_words": round(per_1k, 3),
                "sentence_opener_hits": opener_hits,
            }
        }

    def _evaluate_markdown_artifacts(self, chapter_content: str) -> Optional[Dict[str, Any]]:
        """
        Deterministic check for markdown formatting leaking into output.
        """
        if not chapter_content or not chapter_content.strip():
            return None

        # Flags: headings, bold/italic wrappers, blockquotes, list markers, separators.
        hits = 0
        examples: list[str] = []

        lines = chapter_content.splitlines()
        for line in lines[:400]:
            raw = line.rstrip("\n")
            stripped = raw.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                hits += 1
                if len(examples) < 4:
                    examples.append(stripped[:120])
            if stripped.startswith(">"):
                hits += 1
                if len(examples) < 4:
                    examples.append(stripped[:120])
            if re.match(r"^(- |\* |\d+\.)\s+\S+", stripped):
                hits += 1
                if len(examples) < 4:
                    examples.append(stripped[:120])
            if re.match(r"^-{3,}\s*$", stripped):
                hits += 1
                if len(examples) < 4:
                    examples.append(stripped[:120])

        # Inline emphasis markers anywhere in text (soft fail unless frequent).
        emphasis_hits = len(re.findall(r"\*\*.+?\*\*|__.+?__|(?<!\w)\*(?!\s).+?(?<!\s)\*(?!\w)", chapter_content))

        passed = True
        if hits > 5:
            passed = False
        if emphasis_hits >= 10:
            passed = False

        return {
            "score": 1.0 if passed else 0.0,
            "minimum_required": 1.0,
            "passed": passed,
            "details": {
                "line_markers": hits,
                "inline_emphasis_hits": emphasis_hits,
                "examples": examples,
            }
        }

    def _evaluate_opening_grounding(self, chapter_content: str) -> Optional[Dict[str, Any]]:
        """
        Fail-fast check that the opening starts in-scene (not abstract summary/backstory).

        Cross-genre: does not require dialogue or action-heavy openings; it requires
        concrete sensory/camera grounding and avoids opening with voiceover recap.
        """
        if not chapter_content or not chapter_content.strip():
            return None

        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", chapter_content) if p.strip()]
        if not paragraphs:
            return None

        opener = "\n\n".join(paragraphs[:2])
        opener_lower = opener.lower()

        # Simple sensory and physical markers.
        sensory = [
            "smell", "smelled", "scent", "reek", "stink",
            "hear", "heard", "sound", "hummed", "buzz", "ring",
            "taste", "tasted",
            "warm", "cold", "hot", "wet", "dry", "damp",
            "light", "dark", "shadow", "fog", "mist", "rain",
            "rough", "slick", "grit", "metal", "wood", "glass",
        ]
        physical = [
            "look", "looked", "squint", "squinted", "stare", "stared",
            "step", "stepped", "walk", "walked", "stand", "stood", "sat",
            "grab", "grabbed", "hold", "held", "reach", "reached",
            "open", "opened", "close", "closed", "click", "clicked",
            "turn", "turned", "lift", "lifted", "set", "set down",
        ]
        summary_verbs = ["was", "were", "had been", "felt", "realized", "knew", "seemed", "understood", "remembered"]

        sensory_hits = sum(1 for w in sensory if re.search(rf"\b{re.escape(w)}\b", opener_lower))
        physical_hits = sum(1 for w in physical if re.search(rf"\b{re.escape(w)}\b", opener_lower))
        summary_hits = sum(opener_lower.count(v) for v in summary_verbs)

        # Voiceover-y openers (hard fail if present right away).
        trailerish = [
            "in a world where",
            "nothing would ever be the same",
            "marked the beginning",
            "this was the moment",
            "it was a day like any other",
        ]
        trailer_hits = [p for p in trailerish if p in opener_lower]

        passed = True
        if trailer_hits:
            passed = False
        if summary_hits >= 8 and (sensory_hits + physical_hits) < 1:
            passed = False

        return {
            "score": 1.0 if passed else 0.0,
            "minimum_required": 1.0,
            "passed": passed,
            "details": {
                "sensory_hits": sensory_hits,
                "physical_hits": physical_hits,
                "summary_verb_hits": summary_hits,
                "trailer_hits": trailer_hits[:3],
            }
        }

    def _evaluate_expository_drift(self, chapter_content: str) -> Optional[Dict[str, Any]]:
        """
        Fail-fast check for mid-chapter drift into "explaining the story" instead of dramatizing it.

        This complements summary_density by catching explanatory runs that may include some sensory words
        but are primarily recap/context paragraphs chained by rationale markers.
        """
        if not chapter_content or not chapter_content.strip():
            return None

        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", chapter_content) if p.strip()]
        if len(paragraphs) < 8:
            return {
                "score": 1.0,
                "minimum_required": 1.0,
                "passed": True,
                "details": {"paragraphs": len(paragraphs), "expository_like": 0, "max_run": 0}
            }

        # Simple heuristics
        explain_markers = [
            "because",
            "therefore",
            "as a result",
            "which meant",
            "which suggested",
            "this meant",
            "that meant",
            "in order to",
            "so that",
            "it meant",
            "it was because",
        ]
        # "Aboutness" framing is a big offender
        aboutness = [
            "this was more than",
            "it wasn't just",
            "it was more than",
            "marked the beginning",
            "would change",
        ]
        action_markers = [
            "open", "opened", "close", "closed", "grab", "grabbed", "pull", "pulled",
            "push", "pushed", "turn", "turned", "walk", "walked", "ran", "sat", "stood",
            "entered", "left", "clicked", "tap", "tapped", "set", "set down",
            "said", "asked", "replied",
        ]
        sensory_markers = [
            "smell", "smelled", "scent", "reek", "stink",
            "hear", "heard", "sound", "hummed", "buzz", "ring",
            "warm", "cold", "hot", "wet", "dry", "damp",
            "light", "dark", "shadow", "fog", "mist", "rain",
            "rough", "slick", "grit", "metal", "wood", "glass",
        ]

        expository_idx: list[int] = []
        max_run = 0
        run = 0

        # Skip the first 2 paragraphs (handled by opening_grounding)
        for i, p in enumerate(paragraphs[2:], start=3):
            pl = p.lower()
            has_dialogue = ('"' in p) or ("“" in p) or ("”" in p)
            if has_dialogue:
                run = 0
                continue

            explain_hits = sum(pl.count(m) for m in explain_markers)
            about_hits = sum(pl.count(m) for m in aboutness)
            has_action = any(re.search(rf"\b{re.escape(a)}\b", pl) for a in action_markers)
            has_sensory = any(re.search(rf"\b{re.escape(s)}\b", pl) for s in sensory_markers)

            # Expository-like: lots of rationale/aboutness, and little/no action.
            is_expository = (explain_hits + about_hits) >= 2 and not has_action
            # Also count "all context" paragraphs that contain no action and no sensory.
            if not has_action and not has_sensory and len(p.split()) >= 60:
                is_expository = True

            if is_expository:
                expository_idx.append(i)
                run += 1
                max_run = max(max_run, run)
            else:
                run = 0

        ratio = len(expository_idx) / max(1, len(paragraphs))
        passed = True
        # Fail if we see a long run or too much overall drift.
        if max_run >= 3:
            passed = False
        if ratio >= 0.30:
            passed = False

        return {
            "score": 1.0 if passed else 0.0,
            "minimum_required": 1.0,
            "passed": passed,
            "details": {
                "paragraphs": len(paragraphs),
                "expository_like": len(expository_idx),
                "ratio": round(ratio, 3),
                "max_run": max_run,
                "flagged_paragraph_indices": expository_idx[:12],
            }
        }

    def _tokenize_for_repetition(self, text: str, allowlist: Optional[List[str]] = None) -> List[str]:
        """Tokenize text for repetition analysis."""
        allowlist = allowlist or []
        stopwords = {
            "the", "and", "but", "or", "a", "an", "to", "of", "in", "on", "at", "for",
            "with", "as", "by", "from", "that", "this", "these", "those", "it", "its",
            "he", "she", "they", "we", "you", "i", "his", "her", "their", "our", "my",
            "was", "were", "is", "are", "be", "been", "being", "had", "has", "have",
            "not", "no", "yes", "if", "then", "so", "because", "when", "while", "just"
        }
        tokens = [t.lower() for t in re.findall(r"[A-Za-z']+", text)]
        return [t for t in tokens if t not in allowlist and t not in stopwords]

    def _max_repeat_run(self, tokens: List[str]) -> int:
        """Find max consecutive repeat count for a token list."""
        if not tokens:
            return 0
        max_run = 1
        current_run = 1
        last = tokens[0]
        for tok in tokens[1:]:
            if tok == last:
                current_run += 1
                max_run = max(max_run, current_run)
            else:
                last = tok
                current_run = 1
        return max_run

    def _top_ngram_stats(self, tokens: List[str], n: int) -> Tuple[str, int, int]:
        """Return (top_ngram, top_count, total_ngrams)."""
        if len(tokens) < n:
            return ("", 0, 0)
        counts: Dict[str, int] = {}
        for i in range(len(tokens) - n + 1):
            ngram = " ".join(tokens[i:i + n])
            counts[ngram] = counts.get(ngram, 0) + 1
        if not counts:
            return ("", 0, 0)
        top_ngram = max(counts, key=counts.get)
        top_count = counts[top_ngram]
        total = len(tokens) - n + 1
        return (top_ngram, top_count, total)

    def _evaluate_runaway_repetition(self, chapter_content: str, allowlist: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """Detect runaway repetition (loops, list spirals, low lexical diversity)."""
        paragraphs = [p for p in chapter_content.split("\n\n") if p.strip()]
        if not paragraphs:
            return None

        issues = []
        for idx, paragraph in enumerate(paragraphs):
            tokens = self._tokenize_for_repetition(paragraph, allowlist=allowlist)
            token_count = len(tokens)
            if token_count < 80:
                continue

            unique_ratio = (len(set(tokens)) / token_count) if token_count else 1.0
            max_run = self._max_repeat_run(tokens)
            top_trigram, trigram_count, trigram_total = self._top_ngram_stats(tokens, 3)
            trigram_ratio = (trigram_count / trigram_total) if trigram_total else 0.0

            is_problem = False
            if max_run >= 6:
                is_problem = True
            if token_count >= 120 and unique_ratio < 0.4:
                is_problem = True
            if trigram_count >= 5 and trigram_ratio >= 0.08:
                is_problem = True

            if is_problem:
                issues.append({
                    "paragraph_index": idx,
                    "word_count": token_count,
                    "unique_ratio": round(unique_ratio, 3),
                    "max_repeat_run": max_run,
                    "top_trigram": top_trigram,
                    "top_trigram_ratio": round(trigram_ratio, 3)
                })

        passed = len(issues) == 0
        return {
            "score": 1.0 if passed else 0.0,
            "minimum_required": 1.0,
            "passed": passed,
            "details": {
                "issue_count": len(issues),
                "issues": issues[:5]
            }
        }

    def _evaluate_pacing_alignment(self, chapter_content: str, chapter_number: int) -> Optional[Dict[str, Any]]:
        """Evaluate pacing alignment vs pacing targets."""
        pacing_targets = self._build_pacing_targets(chapter_number)
        if not pacing_targets:
            return None

        pace_mode = pacing_targets.get("pace_mode")
        paragraphs = [p.strip() for p in chapter_content.split("\n\n") if p.strip()]
        if not paragraphs:
            return None

        avg_paragraph = sum(len(p.split()) for p in paragraphs) / max(1, len(paragraphs))
        passed = True
        if pace_mode == "high_tension" and avg_paragraph > 120:
            passed = False
        if pace_mode == "slow_build" and avg_paragraph < 60:
            passed = False

        return {
            "score": 1.0 if passed else 0.0,
            "minimum_required": 1.0,
            "passed": passed,
            "details": {"avg_paragraph_length": round(avg_paragraph, 1), "pace_mode": pace_mode}
        }

    def _infer_chapter_number(self, chapter_content: str) -> int:
        """Deprecated fallback chapter number inference; default to 1."""
        return 1

    async def _apply_targeted_repairs(
        self,
        chapter_content: str,
        chapter_number: int,
        quality_result: Dict[str, Any],
        context: Dict[str, Any]
    ) -> str:
        """Apply targeted repairs in priority order based on failed checks."""
        category_results = quality_result.get("category_results", {})
        mode = self._chapter_repair_mode()

        # Optional backstop: if we are already spending post-draft LLM budget in this run,
        # and the ending lands as a tagline/button, spend ONE budgeted paragraph rewrite to fix it.
        try:
            style_signals = quality_result.get("style_signals", {}) if isinstance(quality_result, dict) else {}
            tagline_flagged = bool((style_signals.get("tagline_ending") or {}).get("flagged"))
            budget = context.get("postdraft_budget", {}) if isinstance(context, dict) else {}
            used = int((budget or {}).get("used", 0) or 0) if isinstance(budget, dict) else 0
            remaining = int((budget or {}).get("remaining", 0) or 0) if isinstance(budget, dict) else 0
            if tagline_flagged and used > 0 and remaining > 0 and chapter_content and chapter_content.strip():
                # Consume one budget unit (best-effort bookkeeping).
                try:
                    budget["remaining"] = max(0, remaining - 1)
                    budget["used"] = used + 1
                    actions = budget.get("actions")
                    if not isinstance(actions, list):
                        actions = []
                        budget["actions"] = actions
                    actions.append("ending_backstop")
                except Exception:
                    pass

                paragraphs = [p for p in chapter_content.split("\n\n") if p.strip()]
                if paragraphs:
                    last_idx = len(paragraphs) - 1
                    paragraphs[last_idx] = await self._rewrite_paragraph(
                        paragraph=paragraphs[last_idx],
                        instruction=(
                            "Rewrite the ending paragraph to avoid tagline/button language. "
                            "End mid-action, mid-decision, or mid-consequence. "
                            "Include (1) an irreversible action and (2) an immediate complication or constraint. "
                            "Do not summarize, do not announce beginnings/odysseys. Use em dashes sparingly."
                        ),
                        context=context,
                    )
                    chapter_content = "\n\n".join(paragraphs)
        except Exception:
            pass

        # Mechanical repairs (safe): repetition -> timeline
        if category_results.get("runaway_repetition", {}).get("passed") is False:
            chapter_content = await self._repair_runaway_repetition(
                chapter_content,
                chapter_number,
                context,
                category_results.get("runaway_repetition", {})
            )

        if category_results.get("timeline_consistency", {}).get("passed") is False or \
           category_results.get("scene_timeline_consistency", {}).get("passed") is False:
            chapter_content = await self._repair_timeline_issues(chapter_content, chapter_number, context)

        if mode != "full":
            return chapter_content

        # Legacy stylistic repairs (can change voice; use sparingly)
        if category_results.get("voice_drift", {}).get("passed") is False or \
           category_results.get("voice_distinctiveness", {}).get("passed") is False:
            chapter_content = await self._repair_voice_drift(chapter_content, chapter_number, context)

        if category_results.get("pacing_alignment", {}).get("passed") is False:
            chapter_content = await self._repair_pacing_issues(chapter_content, chapter_number, context)

        if category_results.get("cadence_variation", {}).get("passed") is False:
            chapter_content = await self._repair_cadence_issues(chapter_content, chapter_number, context)

        if category_results.get("paragraph_pattern_variety", {}).get("passed") is False:
            chapter_content = await self._repair_paragraph_pattern_issues(chapter_content, chapter_number, context)

        if category_results.get("content_composition", {}).get("passed") is False:
            chapter_content = await self._repair_composition_issues(chapter_content, chapter_number, context)

        if category_results.get("dialogue_tag_variety", {}).get("passed") is False:
            chapter_content = await self._repair_dialogue_tag_variety(chapter_content, chapter_number, context)

        return chapter_content

    async def _repair_cadence_issues(self, chapter_content: str, chapter_number: int, context: Dict[str, Any]) -> str:
        """Repair cadence issues by rewriting paragraphs with repetitive rhythm."""
        if not self.cadence_analyzer:
            return chapter_content

        paragraphs = [p for p in chapter_content.split("\n\n") if p.strip()]
        if not paragraphs:
            return chapter_content

        # Identify paragraphs with very similar sentence lengths
        def paragraph_avg_sentence_length(p: str) -> float:
            sentences = [s.strip() for s in re.split(r'[.!?]+', p) if s.strip()]
            if not sentences:
                return 0.0
            lengths = [len(s.split()) for s in sentences]
            return sum(lengths) / max(1, len(lengths))

        avg_lengths = [paragraph_avg_sentence_length(p) for p in paragraphs]
        overall_avg = sum(avg_lengths) / max(1, len(avg_lengths))
        indices_to_fix = [i for i, val in enumerate(avg_lengths) if abs(val - overall_avg) < 1.0][:2]

        if not indices_to_fix:
            return chapter_content

        for idx in indices_to_fix:
            paragraphs[idx] = await self._rewrite_paragraph(
                paragraph=paragraphs[idx],
                instruction=(
                    "Vary cadence: adjust sentence lengths and structure to create a different rhythm. "
                    "Keep meaning and plot facts. Use em dashes sparingly."
                ),
                context=context
            )

        return "\n\n".join(paragraphs)

    async def _repair_paragraph_pattern_issues(self, chapter_content: str, chapter_number: int, context: Dict[str, Any]) -> str:
        """Repair overused paragraph patterns by rewriting offending paragraphs."""
        if not self.pattern_db:
            return chapter_content

        paragraphs = [p for p in chapter_content.split("\n\n") if p.strip()]
        if not paragraphs:
            return chapter_content

        indices_to_fix = []
        for idx, para in enumerate(paragraphs):
            patterns = self.pattern_db._extract_paragraph_patterns(para, chapter_number)
            if patterns and any(pat in ["thinking_pattern_contrast", "thinking_pattern_simple"] for pat in patterns):
                indices_to_fix.append(idx)
            if len(indices_to_fix) >= 2:
                break

        if not indices_to_fix:
            return chapter_content

        for idx in indices_to_fix:
            paragraphs[idx] = await self._rewrite_paragraph(
                paragraph=paragraphs[idx],
                instruction=(
                    "Rewrite this paragraph to a different structure. Avoid the same thinking/contrast pattern. "
                    "Keep meaning and plot facts. Use em dashes sparingly."
                ),
                context=context
            )

        return "\n\n".join(paragraphs)

    async def _repair_composition_issues(self, chapter_content: str, chapter_number: int, context: Dict[str, Any]) -> str:
        """Repair composition issues by adjusting a few paragraphs."""
        paragraphs = [p for p in chapter_content.split("\n\n") if p.strip()]
        if not paragraphs:
            return chapter_content

        # Add dialogue if dialogue is low, add action if action is low
        try:
            from .helpers.quality_gate_validator import QualityGateValidator
        except Exception:
            from backend.auto_complete.helpers.quality_gate_validator import QualityGateValidator
        comp = self._evaluate_content_composition(chapter_content, QualityGateValidator().config)
        if not comp:
            return chapter_content
        details = comp.get("details", {})

        indices_to_fix = []
        if details.get("dialogue_pct", 0) < 30:
            indices_to_fix = [i for i, p in enumerate(paragraphs) if '"' not in p][:2]
            instruction = "Introduce brief dialogue to balance composition. Keep plot facts. Use em dashes sparingly."
        elif details.get("action_pct", 0) < 20:
            indices_to_fix = list(range(min(2, len(paragraphs))))
            instruction = "Add concise physical action to improve pacing. Keep plot facts. Use em dashes sparingly."
        else:
            return chapter_content

        for idx in indices_to_fix:
            paragraphs[idx] = await self._rewrite_paragraph(
                paragraph=paragraphs[idx],
                instruction=instruction,
                context=context
            )
        return "\n\n".join(paragraphs)

    async def _repair_dialogue_tag_variety(self, chapter_content: str, chapter_number: int, context: Dict[str, Any]) -> str:
        """Repair dialogue tag variety by rewriting dialogue paragraphs."""
        paragraphs = [p for p in chapter_content.split("\n\n") if p.strip()]
        if not paragraphs:
            return chapter_content

        indices_to_fix = [i for i, p in enumerate(paragraphs) if '"' in p or '“' in p or '”' in p][:2]
        if not indices_to_fix:
            return chapter_content

        for idx in indices_to_fix:
            paragraphs[idx] = await self._rewrite_paragraph(
                paragraph=paragraphs[idx],
                instruction=(
                    "Vary dialogue tags and sentence rhythm. Avoid repeating the same tag. "
                    "Keep plot facts. Use em dashes sparingly."
                ),
                context=context
            )
        return "\n\n".join(paragraphs)

    async def _repair_runaway_repetition(
        self,
        chapter_content: str,
        chapter_number: int,
        context: Dict[str, Any],
        repetition_result: Dict[str, Any]
    ) -> str:
        """Repair runaway repetition by rewriting flagged paragraphs."""
        paragraphs = [p for p in chapter_content.split("\n\n") if p.strip()]
        if not paragraphs:
            return chapter_content

        issues = repetition_result.get("details", {}).get("issues", [])
        indices = [issue.get("paragraph_index") for issue in issues if isinstance(issue, dict)]
        indices = [i for i in indices if isinstance(i, int) and 0 <= i < len(paragraphs)]
        if not indices:
            return chapter_content

        for idx in indices[:3]:
            paragraphs[idx] = await self._rewrite_paragraph(
                paragraph=paragraphs[idx],
                instruction=(
                    "Remove repetition and list-like spirals. Replace repeated words with concise narrative. "
                    "Keep plot facts. Use em dashes sparingly."
                ),
                context=context
            )

        return "\n\n".join(paragraphs)

    async def _final_polish_book(self) -> None:
        """Final polish pass across the entire book for coherence and repetition control."""
        self.logger.info("Starting final polish pass across all chapters")

        chapter_files = sorted(self.chapters_dir.glob("chapter-*.md"))
        if not chapter_files:
            self.logger.warning("No chapters found for final polish")
            return

        for chapter_file in chapter_files:
            try:
                chapter_number = int(chapter_file.stem.split("-")[-1])
            except Exception:
                continue

            original = chapter_file.read_text(encoding="utf-8")
            if not original.strip():
                continue

            polished = await self._polish_chapter(chapter_number, original)
            if polished and polished.strip() and polished != original:
                if self.config.final_gate_lock:
                    try:
                        context = self._build_chapter_context(chapter_number)
                        quality_result = await self._assess_chapter_quality(polished, chapter_number, context)
                        polished, quality_result, _ = await self._final_gate_lock(
                            polished,
                            chapter_number,
                            context,
                            quality_result
                        )
                    except Exception as lock_err:
                        self.logger.warning(f"Final gate lock failed after polish for Chapter {chapter_number}: {lock_err}")
                chapter_file.write_text(polished, encoding="utf-8")
                await self._update_chapter_in_database(chapter_number, polished)

        # Global audit after polish
        try:
            issues = self._audit_book_cadence_and_tone()
            if issues and self.config.final_audit_rewrite:
                for issue in issues:
                    chapter_number = issue.get("chapter_number")
                    if not chapter_number:
                        continue
                    chapter_path = self.chapters_dir / f"chapter-{int(chapter_number):02d}.md"
                    if not chapter_path.exists():
                        continue
                    original = chapter_path.read_text(encoding="utf-8")
                    rewritten = await self._cadence_variation_rewrite(int(chapter_number), original, issue)
                    if rewritten and rewritten.strip() and rewritten != original:
                        if self.config.final_gate_lock:
                            try:
                                context = self._build_chapter_context(int(chapter_number))
                                quality_result = await self._assess_chapter_quality(rewritten, int(chapter_number), context)
                                rewritten, quality_result, _ = await self._final_gate_lock(
                                    rewritten,
                                    int(chapter_number),
                                    context,
                                    quality_result
                                )
                            except Exception as lock_err:
                                self.logger.warning(f"Final gate lock failed after cadence rewrite for Chapter {chapter_number}: {lock_err}")
                        chapter_path.write_text(rewritten, encoding="utf-8")
                        await self._update_chapter_in_database(int(chapter_number), rewritten)
        except Exception as audit_err:
            self.logger.warning(f"Global cadence/tone audit failed: {audit_err}")

        self.logger.info("Final polish pass complete")

    async def _polish_chapter(self, chapter_number: int, chapter_content: str) -> str:
        """Polish a chapter for coherence, variation, and plan compliance."""
        try:
            from .llm_orchestrator import LLMOrchestrator, RetryConfig
        except Exception:
            from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig

        orchestrator = LLMOrchestrator(retry_config=RetryConfig(max_retries=2))

        context = self._build_chapter_context(chapter_number)
        chapter_plan = self._get_chapter_plan(chapter_number) or {}
        try:
            vector_payload = await self._build_vector_memory_context(chapter_number, context)
            context.update(vector_payload)
        except Exception as e:
            self.logger.warning(f"Vector memory unavailable for polish pass: {e}")

        system_prompt = (
            "You are a senior fiction editor producing a final polish pass.\n"
            "Goals: improve coherence, reduce repetition, preserve facts and voice.\n"
            "Do not add new plot points. Do not change the story outcomes.\n"
            "Use em dashes sparingly.\n"
            "Output plain text only (no Markdown formatting: no headings, bullets, blockquotes, emphasis markers like *, **, _, or separators like ---).\n"
            "Maintain composition targets for dialogue, action, internal monologue, and description.\n"
            "Vary dialogue tags; avoid dominance by a single tag.\n"
            "Vary cadence and paragraph rhythm relative to adjacent chapters.\n"
        )

        user_prompt = (
            f"Polish Chapter {chapter_number} for publication readiness.\n\n"
            f"CHAPTER PLAN SUMMARY:\n{chapter_plan.get('summary', '')}\n\n"
            f"OBJECTIVES:\n{chapter_plan.get('objectives', [])}\n\n"
            f"REQUIRED PLOT POINTS:\n{chapter_plan.get('required_plot_points', [])}\n\n"
            f"OPENING TYPE: {chapter_plan.get('opening_type', '')}\n"
            f"ENDING TYPE: {chapter_plan.get('ending_type', '')}\n"
            f"EMOTIONAL ARC: {chapter_plan.get('emotional_arc', '')}\n"
            f"FOCAL CHARACTERS: {chapter_plan.get('focal_characters', [])}\n\n"
            f"MEMORY LEDGER:\n{context.get('memory_ledger', '')}\n\n"
            f"VECTOR MEMORY CONTEXT:\n{context.get('vector_memory_context', '')}\n\n"
            f"VECTOR MEMORY GUIDELINES:\n{context.get('vector_memory_guidelines', '')}\n\n"
            "CHAPTER TEXT:\n"
            "--- DRAFT START ---\n"
            f"{chapter_content}\n"
            "--- DRAFT END ---\n\n"
            "Return the fully polished chapter text."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        response = await orchestrator._make_api_call(
            messages=messages,
            temperature=0.3,
            max_tokens=16000,
            vector_store_ids=context.get("vector_store_ids", [])
        )
        if hasattr(response, "output_text"):
            return response.output_text
        if hasattr(response, "choices"):
            return response.choices[0].message.content
        return chapter_content

    def _audit_book_cadence_and_tone(self) -> List[Dict[str, Any]]:
        """Audit the full book for cadence and tone repetition."""
        issues: List[Dict[str, Any]] = []

        chapter_files = sorted(self.chapters_dir.glob("chapter-*.md"))
        if not chapter_files or not self.cadence_analyzer:
            return issues

        recent_fps: List[Any] = []
        recent_tones: List[str] = []

        for chapter_file in chapter_files:
            try:
                chapter_number = int(chapter_file.stem.split("-")[-1])
            except Exception:
                continue

            text = chapter_file.read_text(encoding="utf-8")
            if not text.strip():
                continue

            fp = self.cadence_analyzer.analyze(chapter_number, text)
            tone = self.context_manager._analyze_emotional_tone(text) if self.context_manager else "neutral"

            # Compare cadence to recent
            if recent_fps:
                similarities = [self.cadence_analyzer.similarity(fp, r) for r in recent_fps]
                max_sim = max(similarities) if similarities else 0.0
                if max_sim > 0.75:
                    issues.append({
                        "chapter_number": chapter_number,
                        "type": "cadence_similarity",
                        "details": {"similarity": round(max_sim, 3)}
                    })

            # Tone repetition (3 in a row)
            if recent_tones.count(tone) >= 2:
                issues.append({
                    "chapter_number": chapter_number,
                    "type": "tone_repetition",
                    "details": {"tone": tone, "recent_tones": recent_tones[-3:]}
                })

            recent_fps = (recent_fps + [fp])[-3:]
            recent_tones = (recent_tones + [tone])[-3:]

        return issues

    async def _cadence_variation_rewrite(self, chapter_number: int, chapter_content: str, issue: Dict[str, Any]) -> str:
        """Rewrite a chapter to vary cadence or tone without changing plot."""
        try:
            from .llm_orchestrator import LLMOrchestrator, RetryConfig
        except Exception:
            from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig

        orchestrator = LLMOrchestrator(retry_config=RetryConfig(max_retries=2))
        context = self._build_chapter_context(chapter_number)
        try:
            vector_payload = await self._build_vector_memory_context(chapter_number, context)
            context.update(vector_payload)
        except Exception as e:
            self.logger.warning(f"Vector memory unavailable for cadence rewrite: {e}")

        system_prompt = (
            "You are a senior fiction editor. Adjust cadence and tone to avoid repetition.\n"
            "Do not change plot facts or outcomes. Preserve character voice.\n"
            "Use em dashes sparingly.\n"
            "Output plain text only (no Markdown formatting: no headings, bullets, blockquotes, emphasis markers like *, **, _, or separators like ---).\n"
        )

        user_prompt = (
            f"Revise Chapter {chapter_number} to address this issue:\n{issue}\n\n"
            "Focus on sentence rhythm, paragraph structure, and tone variation. Do not alter plot events.\n\n"
            f"VECTOR MEMORY CONTEXT:\n{context.get('vector_memory_context', '')}\n\n"
            f"VECTOR MEMORY GUIDELINES:\n{context.get('vector_memory_guidelines', '')}\n\n"
            "--- DRAFT START ---\n"
            f"{chapter_content}\n"
            "--- DRAFT END ---\n\n"
            "Return the fully revised chapter text."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        response = await orchestrator._make_api_call(
            messages=messages,
            temperature=0.3,
            max_tokens=16000,
            vector_store_ids=context.get("vector_store_ids", [])
        )
        if hasattr(response, "output_text"):
            return response.output_text
        if hasattr(response, "choices"):
            return response.choices[0].message.content
        return chapter_content

    async def _repair_timeline_issues(self, chapter_content: str, chapter_number: int, context: Dict[str, Any]) -> str:
        """Repair timeline issues by clarifying time shifts."""
        try:
            if not self.context_manager:
                return chapter_content
            scene_markers = self.context_manager._extract_scene_markers(chapter_content)
            needs_fix = any(
                s.get("timeline_position") == "backward"
                and not any(m in ["flashback", "memory", "years ago", "earlier", "yesterday", "previous day"] for m in s.get("markers", []))
                for s in scene_markers
            )
            if not needs_fix:
                return chapter_content
        except Exception:
            return chapter_content

        try:
            from .llm_orchestrator import LLMOrchestrator, RetryConfig
        except Exception:
            from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig

        # Targeted paragraph rewrites: only paragraphs with time shifts
        paragraphs = [p for p in chapter_content.split("\n\n") if p.strip()]
        indices_to_fix = []
        for idx, para in enumerate(paragraphs):
            markers = self.context_manager._extract_time_markers(para)
            position = self.context_manager._determine_timeline_position(markers)
            has_flashback = any(m in ["flashback", "memory", "years ago", "earlier", "yesterday", "previous day"] for m in markers)
            if position == "backward" and not has_flashback:
                indices_to_fix.append(idx)

        if not indices_to_fix:
            return chapter_content

        for idx in indices_to_fix:
            paragraphs[idx] = await self._rewrite_paragraph(
                paragraph=paragraphs[idx],
                instruction=(
                    "Clarify timeline. If this moves backward, explicitly mark as flashback "
                    "with a clear cue. Do not change plot facts. Use em dashes sparingly."
                ),
                context=context
            )

        return "\n\n".join(paragraphs)

    async def _repair_voice_drift(self, chapter_content: str, chapter_number: int, context: Dict[str, Any]) -> str:
        """Repair character voice drift by aligning dialogue to established voices."""
        if not self.voice_fingerprint_manager:
            return chapter_content
        try:
            fingerprints = self.voice_fingerprint_manager.fingerprints_from_text(chapter_number, chapter_content)
            drifted = []
            for character, fp in fingerprints.items():
                drift = self.voice_fingerprint_manager.global_character_drift(character, fp, lookback=10)
                if drift is not None and drift < 0.5:
                    drifted.append(character)
            if not drifted:
                return chapter_content
        except Exception:
            return chapter_content

        # Targeted paragraph rewrites: only dialogue paragraphs for drifted characters
        paragraphs = [p for p in chapter_content.split("\n\n") if p.strip()]
        indices_to_fix = []
        for idx, para in enumerate(paragraphs):
            if '"' not in para and '“' not in para and '”' not in para:
                continue
            for character in drifted:
                if character.lower() in para.lower():
                    indices_to_fix.append(idx)
                    break

        if not indices_to_fix:
            return chapter_content

        for idx in indices_to_fix:
            paragraphs[idx] = await self._rewrite_paragraph(
                paragraph=paragraphs[idx],
                instruction=(
                    f"Adjust dialogue to match established voice for {', '.join(drifted)}. "
                    "Keep plot facts. Use em dashes sparingly."
                ),
                context=context
            )

        return "\n\n".join(paragraphs)

    async def _repair_pacing_issues(self, chapter_content: str, chapter_number: int, context: Dict[str, Any]) -> str:
        """Repair pacing issues based on pacing targets."""
        pacing_targets = context.get("pacing_targets", {})
        if not pacing_targets:
            return chapter_content

        # Targeted paragraph rewrites based on pacing envelope
        paragraphs = [p for p in chapter_content.split("\n\n") if p.strip()]
        indices_to_fix = []
        pace_mode = pacing_targets.get("pace_mode")
        for idx, para in enumerate(paragraphs):
            wc = len(para.split())
            if pace_mode == "high_tension" and wc > 180:
                indices_to_fix.append(idx)
            if pace_mode == "slow_build" and wc < 60:
                indices_to_fix.append(idx)

        if not indices_to_fix:
            return chapter_content

        for idx in indices_to_fix:
            paragraphs[idx] = await self._rewrite_paragraph(
                paragraph=paragraphs[idx],
                instruction=(
                    f"Adjust pacing for mode {pace_mode}. "
                    "Shorten or expand to fit flow. Keep plot facts. Use em dashes sparingly."
                ),
                context=context
            )

        return "\n\n".join(paragraphs)

    async def _rewrite_paragraph(self, paragraph: str, instruction: str, context: Dict[str, Any]) -> str:
        """Rewrite a single paragraph with strict constraints."""
        try:
            from .llm_orchestrator import LLMOrchestrator, RetryConfig
        except Exception:
            from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig

        orchestrator = LLMOrchestrator(retry_config=RetryConfig(max_retries=2))
        system_prompt = (
            "You are a fiction editor. Rewrite ONLY the given paragraph.\n"
            "Do not change plot facts or outcomes. Use em dashes sparingly.\n"
            "Preserve character voice and continuity.\n"
            "Eliminate repetition and avoid list-like spirals.\n"
            "Output plain text only (no Markdown formatting: no headings, bullets, blockquotes, emphasis markers like *, **, _, or separators like ---).\n"
        )
        user_prompt = (
            f"INSTRUCTION: {instruction}\n\n"
            f"MEMORY LEDGER:\n{context.get('memory_ledger', '')}\n\n"
            f"VECTOR MEMORY CONTEXT:\n{context.get('vector_memory_context', '')}\n\n"
            f"VECTOR MEMORY GUIDELINES:\n{context.get('vector_memory_guidelines', '')}\n\n"
            "--- PARAGRAPH START ---\n"
            f"{paragraph}\n"
            "--- PARAGRAPH END ---\n\n"
            "Return only the revised paragraph."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        response = await orchestrator._make_api_call(
            messages=messages,
            temperature=0.3,
            max_tokens=2000,
            frequency_penalty=0.0,
            presence_penalty=0.0,
            vector_store_ids=context.get("vector_store_ids", [])
        )
        if hasattr(response, "output_text"):
            return response.output_text.strip()
        if hasattr(response, "choices"):
            return response.choices[0].message.content.strip()
        return paragraph

    async def _update_chapter_in_database(self, chapter_number: int, content: str) -> None:
        """Update existing chapter in database with a new polished version."""
        try:
            from backend.database_integration import get_project_chapters, get_database_adapter
        except Exception:
            from database_integration import get_project_chapters, get_database_adapter

        project_id = self.config.project_id
        user_id = self.config.user_id or "unknown"

        if not project_id:
            return

        existing_chapters = await get_project_chapters(project_id)
        chapter_doc = next((ch for ch in existing_chapters if ch.get('chapter_number') == chapter_number), None)
        if not chapter_doc:
            return

        chapter_id = chapter_doc.get('id')
        if not chapter_id:
            return

        update_data = {
            'content': content,
            'metadata.word_count': len(content.split()),
            'metadata.updated_at': datetime.utcnow().isoformat(),
            'metadata.updated_by': user_id,
            'metadata.last_generation_reason': 'final_polish'
        }

        versions = chapter_doc.get('versions', []) or []
        new_version = {
            'version_number': len(versions) + 1,
            'content': content,
            'timestamp': datetime.utcnow(),
            'reason': 'final_polish',
            'user_id': user_id,
            'changes_summary': f'Final polish pass for Chapter {chapter_number}'
        }
        update_data['versions'] = versions + [new_version]

        db = get_database_adapter()
        if db.use_firestore:
            await db.firestore.update_chapter(chapter_id, update_data)

        try:
            from backend.services.vector_store_service import VectorStoreService
        except Exception:
            try:
                from services.vector_store_service import VectorStoreService
            except Exception:
                VectorStoreService = None

        if VectorStoreService:
            try:
                vector_service = VectorStoreService()
                if vector_service.available:
                    await vector_service.ensure_project_vector_store(project_id, user_id)
                    await vector_service.upsert_chapter(
                        project_id=project_id,
                        user_id=user_id,
                        chapter_id=chapter_id,
                        chapter_number=chapter_number,
                        title=chapter_doc.get('title') or f"Chapter {chapter_number}",
                        content=content
                    )
            except Exception as e:
                self.logger.warning(f"Vector store update failed for Chapter {chapter_number}: {e}")

    def _format_pattern_summary(self, summary: Dict[str, Any]) -> str:
        """Build a concise pattern database summary for prompts."""
        metadata = summary.get("metadata", {})
        risks = summary.get("recent_risks", {})

        lines = [
            f"Chapters tracked: {summary.get('chapters_tracked', 0)}",
            f"Total metaphors: {summary.get('total_metaphors', 0)}",
            f"Total similes: {summary.get('total_similes', 0)}",
            f"Sentence patterns: {summary.get('sentence_patterns', 0)}",
            f"Paragraph patterns: {summary.get('paragraph_patterns', 0)}",
            f"Dialogue tags: {summary.get('dialogue_tags', 0)}",
            f"Freshness score: {risks.get('score', 0)}/10"
        ]

        if metadata.get("last_updated"):
            lines.append(f"Last updated: {metadata.get('last_updated')}")

        return "\n".join(lines)

    def _build_repetition_allowlist(self, context: Dict[str, Any]) -> List[str]:
        """Build allowlist for expected repetition (names, terms, catchphrases)."""
        allowlist: List[str] = []
        focal_characters = context.get("focal_characters", []) or []
        for name in focal_characters:
            if isinstance(name, str) and name.strip():
                allowlist.append(name.strip().lower())

        # Extract candidate proper names from character references
        character_ref = context.get("characters_reference") or ""
        if character_ref:
            tokens = re.findall(r"\b[A-Z][a-z]{2,}\b", character_ref)
            for token in tokens:
                allowlist.append(token.strip().lower())

        # Allow explicit repetition notes in director notes
        director_notes = context.get("director_notes") or ""
        for line in director_notes.splitlines():
            if line.strip().lower().startswith("allow_repetition:"):
                phrase = line.split(":", 1)[1].strip().lower()
                if phrase:
                    allowlist.append(phrase)

        # Deduplicate
        return sorted({p for p in allowlist if p})

    def _build_overused_words(self, chapter_number: int, allowlist: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Extract the most overused single words across ALL completed chapters."""
        stopwords = {
            "the", "and", "but", "or", "a", "an", "to", "of", "in", "on", "at", "for",
            "with", "as", "by", "from", "that", "this", "these", "those", "it", "its",
            "he", "she", "they", "we", "you", "i", "his", "her", "their", "our", "my",
            "was", "were", "is", "are", "be", "been", "being", "had", "has", "have",
            "not", "no", "yes", "if", "then", "so", "because", "when", "while", "just",
            "all", "can", "could", "would", "should", "will", "do", "did", "does", "done",
            "got", "get", "been", "more", "some", "any", "each", "every", "much", "many",
            "too", "very", "also", "about", "into", "over", "after", "before", "between",
            "through", "under", "again", "there", "here", "where", "who", "what", "how",
            "than", "them", "him", "me", "us", "your", "out", "up", "down", "back",
            "said", "like", "one", "two", "even", "still", "now", "only", "other",
            "own", "most", "same", "new", "first", "last", "long", "way", "may",
            "come", "came", "make", "made", "know", "knew", "see", "saw", "go", "went",
            "take", "took", "tell", "told", "think", "thought", "look", "looked",
            "want", "turn", "turned", "say", "just", "well", "right", "let",
        }
        allowlist_lower = {w.lower() for w in (allowlist or [])}
        word_counts: Dict[str, int] = {}
        total_words = 0
        for i in range(1, chapter_number):
            chapter_file = self.chapters_dir / f"chapter-{i:02d}.md"
            if not chapter_file.exists():
                continue
            try:
                text = chapter_file.read_text(encoding="utf-8").lower()
                words = re.findall(r'\b[a-z]{4,}\b', text)
                total_words += len(words)
                for w in words:
                    if w not in stopwords and w not in allowlist_lower:
                        word_counts[w] = word_counts.get(w, 0) + 1
            except Exception:
                continue

        if not word_counts or total_words < 500:
            return []

        avg_per_word = total_words / max(len(word_counts), 1)
        threshold = max(15, int(avg_per_word * 3))

        overused = [
            {"word": w, "count": c}
            for w, c in word_counts.items()
            if c >= threshold
        ]
        overused.sort(key=lambda x: -x["count"])
        return overused[:15]

    def _build_overused_phrases(self, chapter_number: int, allowlist: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Extract ANY repeated multi-word phrase across ALL completed chapters.

        Purely frequency-based — no hardcoded verb lists or phrase seeds.
        Returns phrases that appear in 3+ chapters, sorted by cross-chapter
        frequency. Catches gestures, atmospheric wallpaper, dialogue tics,
        and any other pattern the model fixates on.
        """
        allowlist_lower = {w.lower() for w in (allowlist or [])}
        stopwords = {
            "the", "and", "but", "or", "a", "an", "to", "of", "in", "on",
            "at", "for", "with", "as", "by", "from", "that", "this", "it",
            "its", "he", "she", "they", "his", "her", "was", "were", "had",
            "has", "have", "been", "not", "is", "are", "be", "if", "then",
            "than", "them", "him", "who", "what", "did", "does", "do",
            "will", "would", "could", "just", "into", "out", "up", "down",
            "back", "all", "no", "yes",
        }

        from collections import defaultdict
        phrase_chapter_sets: Dict[str, set] = defaultdict(set)
        phrase_totals: Dict[str, int] = defaultdict(int)

        for i in range(1, chapter_number):
            chapter_file = self.chapters_dir / f"chapter-{i:02d}.md"
            if not chapter_file.exists():
                continue
            try:
                text = chapter_file.read_text(encoding="utf-8").lower()
            except Exception:
                continue

            words = re.findall(r"[a-z]+", text)
            for n in (3, 4):
                for j in range(len(words) - n + 1):
                    tokens = words[j : j + n]
                    if all(t in stopwords for t in tokens):
                        continue
                    if any(t in allowlist_lower for t in tokens):
                        continue
                    phrase = " ".join(tokens)
                    phrase_chapter_sets[phrase].add(i)
                    phrase_totals[phrase] += 1

        results = []
        total_chapters_written = max(1, chapter_number - 1)
        for phrase, ch_set in phrase_chapter_sets.items():
            ch_count = len(ch_set)
            total = phrase_totals[phrase]
            if ch_count < 3:
                continue
            avg_per_chapter = total / ch_count
            spread_ratio = ch_count / total_chapters_written
            # Flag if: heavy per-chapter use (avg 1.5+)
            # OR: wide spread across 40%+ of chapters (catches 1x-per-chapter tics)
            #     but only for 4+ word phrases (avoids flagging common 3-word patterns)
            is_heavy = avg_per_chapter >= 1.5
            is_widespread = spread_ratio >= 0.4 and len(phrase.split()) >= 4
            if not is_heavy and not is_widespread:
                continue
            results.append({
                "phrase": phrase,
                "chapter_count": ch_count,
                "total": total,
            })
        results.sort(key=lambda x: (-x["chapter_count"], -x["total"]))
        return results[:15]

    def _build_avoid_phrases(self, chapter_number: int, allowlist: Optional[List[str]] = None) -> List[str]:
        """Extract repeated phrases from recent chapters to avoid."""
        phrases: Dict[str, int] = {}
        allowlist = allowlist or []
        stopwords = {
            "the", "and", "but", "or", "a", "an", "to", "of", "in", "on", "at", "for",
            "with", "as", "by", "from", "that", "this", "these", "those", "it", "its",
            "he", "she", "they", "we", "you", "i", "his", "her", "their", "our", "my",
            "was", "were", "is", "are", "be", "been", "being", "had", "has", "have",
            "not", "no", "yes", "if", "then", "so", "because", "when", "while", "just"
        }
        window_files = []
        for i in range(max(1, chapter_number - 3), chapter_number):
            chapter_file = self.chapters_dir / f"chapter-{i:02d}.md"
            if chapter_file.exists():
                window_files.append(chapter_file)

        for chapter_file in window_files:
            text = chapter_file.read_text(encoding="utf-8").lower()
            words = [w for w in re.split(r'[^a-zA-Z]+', text) if len(w) > 2]
            for n in (3, 4):
                for i in range(0, len(words) - n + 1):
                    phrase = " ".join(words[i:i+n])
                    tokens = phrase.split()
                    if phrase in allowlist:
                        continue
                    if any(t in allowlist for t in tokens):
                        continue
                    stop_count = sum(1 for t in tokens if t in stopwords)
                    if stop_count >= len(tokens) - 1:
                        continue
                    phrases[phrase] = phrases.get(phrase, 0) + 1

        repeated = [p for p, count in phrases.items() if count >= 2]
        repeated.sort(key=lambda p: (-phrases[p], len(p)))

        # Also add single-word (unigram) offenders from ALL chapters
        unigram_counts: Dict[str, int] = {}
        for i in range(1, chapter_number):
            chapter_file = self.chapters_dir / f"chapter-{i:02d}.md"
            if not chapter_file.exists():
                continue
            try:
                text = chapter_file.read_text(encoding="utf-8").lower()
                for w in re.findall(r'\b[a-z]{5,}\b', text):
                    if w not in stopwords and w not in allowlist:
                        unigram_counts[w] = unigram_counts.get(w, 0) + 1
            except Exception:
                continue
        # Add words that appear excessively (20+ times across the book)
        unigram_offenders = [w for w, c in unigram_counts.items() if c >= 20]
        unigram_offenders.sort(key=lambda w: -unigram_counts[w])
        for w in unigram_offenders[:10]:
            entry = f"[word: {w}] (used {unigram_counts[w]} times)"
            if entry not in repeated:
                repeated.append(entry)

        return repeated[:40]

    def _build_cadence_targets(self, chapter_number: int) -> Dict[str, Any]:
        """Create cadence variation targets based on recent fingerprints."""
        if not self.cadence_analyzer:
            return {}
        recent = self.cadence_analyzer.get_recent(chapter_number, lookback=3)
        if not recent:
            return {}

        avg_sentence = sum(fp.avg_sentence_length for fp in recent) / len(recent)
        avg_paragraph = sum(fp.avg_paragraph_length for fp in recent) / len(recent)

        # Encourage variation away from recent averages
        return {
            "target_avg_sentence_length": round(avg_sentence + 3, 1),
            "target_avg_paragraph_length": round(avg_paragraph + 15, 1),
            "variation_hint": "Increase sentence length variance and vary paragraph sizes."
        }

    def _build_pacing_targets(self, chapter_number: int) -> Dict[str, Any]:
        """Generate pacing targets based on chapter position in the book."""
        total = self.config.target_chapter_count
        if total <= 0:
            return {}

        pct = chapter_number / max(1, total)
        if pct <= 0.2:
            pace = "slow_build"
            guidance = "Establish stakes and world; allow longer reflective beats."
            scene_count_target = "3-4 scenes"
        elif pct <= 0.5:
            pace = "rising_action"
            guidance = "Increase pace; tighten scene lengths and raise complications."
            scene_count_target = "4-5 scenes"
        elif pct <= 0.8:
            pace = "high_tension"
            guidance = "High momentum; shorter scenes, sharper transitions."
            scene_count_target = "5-6 scenes"
        else:
            pace = "climax_resolution"
            guidance = "Climax and resolution; strong reveals and decisive beats."
            scene_count_target = "4-5 scenes"

        return {
            "pace_mode": pace,
            "guidance": guidance,
            "scene_count_target": scene_count_target
        }
    
    async def _save_chapter_to_database(self, chapter_number: int, chapter_content: str, context: Dict[str, Any]):
        """Save chapter to database/Firestore."""
        try:
            from backend.database_integration import create_chapter
            from datetime import datetime, timezone
            
            # Get user_id from context or job data
            user_id = context.get('user_id') or self.config.user_id if hasattr(self.config, 'user_id') else None
            project_id = context.get('project_id') or self.config.project_id if hasattr(self.config, 'project_id') else None
            
            if not project_id:
                self.logger.error("No project_id available for chapter save")
                return
            
            if not user_id:
                self.logger.warning("No user_id available, trying to save chapter anyway")
                user_id = "unknown"
            
            quality_result = context.get("quality_result", {})
            quality_score = context.get("quality_score", 0.0)
            brutal_assessment = quality_result.get("brutal_assessment")
            critical_failures = quality_result.get("critical_failures", []) if isinstance(quality_result, dict) else []
            director_brief_validation = context.get("director_brief_validation")
            llm_metadata = context.get("_last_llm_metadata") if isinstance(context, dict) else None
            llm_error = context.get("_last_llm_error") if isinstance(context, dict) else None

            # Determine gate status/failure reason for persistence.
            gates_passed = False
            try:
                gates_passed = bool(self._passes_quality_gates(quality_result))
            except Exception:
                gates_passed = False

            failure_reason = None
            try:
                if gates_passed:
                    failure_reason = None
                else:
                    # Prefer explicit LLM error when present (e.g. specificity gate failure).
                    if isinstance(llm_error, str) and llm_error.strip():
                        failure_reason = llm_error.strip()
                    else:
                        try:
                            if isinstance(director_brief_validation, dict) and director_brief_validation.get("passed") is False:
                                failure_reason = f"Director brief validation failed: {director_brief_validation.get('missing_sections', [])}"
                            else:
                                failure_reason = "Failed quality gates"
                        except Exception:
                            failure_reason = "Failed quality gates"
            except Exception:
                failure_reason = None

            # Prepare chapter data in the format expected by the new database layer
            chapter_data = {
                'project_id': project_id,
                'chapter_number': chapter_number,
                'title': f"Chapter {chapter_number}",
                'content': chapter_content,
                'metadata': {
                    'run_id': context.get("chapter_run_id"),
                    'run_summary': context.get("chapter_run_summary"),
                    'gates_passed': gates_passed,
                    'failure_reason': failure_reason,
                    'director_brief_validation': director_brief_validation,
                    'word_count': len(chapter_content.split()),
                    'target_word_count': context.get('target_words', 3800),
                    'target_range_words': [context.get('target_words_min'), context.get('target_words_max')],
                    'created_by': user_id,
                    'stage': context.get('stage', 'draft'),
                    'generation_time': context.get('generation_time', 0.0),
                    'retry_attempts': context.get('retry_attempts', 0),
                    'model_used': context.get('model_used', 'gpt-4o'),
                    'tokens_used': context.get('tokens_used', {'prompt': 0, 'completion': 0, 'total': 0}),
                    'cost_breakdown': context.get('cost_breakdown', {'input_cost': 0.0, 'output_cost': 0.0, 'total_cost': 0.0}),
                    'generation_method': 'auto_complete_orchestrator',
                    'generated_at': datetime.now(timezone.utc).isoformat()
                },
                'quality_scores': {
                    'brutal_assessment': brutal_assessment,
                    'engagement_score': quality_score,
                    'overall_rating': quality_score,
                    'craft_scores': {
                        'prose': 0.0,
                        'character': 0.0,
                        'story': 0.0,
                        'emotion': 0.0,
                        'freshness': 0.0
                    },
                    'pattern_violations': critical_failures,
                    'improvement_suggestions': []
                },
                'versions': [{
                    'version_number': 1,
                    'content': chapter_content,
                    'timestamp': datetime.now(timezone.utc),
                    'reason': 'auto_generation',
                    'user_id': user_id,
                    'changes_summary': f'Auto-generated chapter {chapter_number}'
                }],
                'context_data': {
                    'character_states': context.get('character_states', {}),
                    'plot_threads': context.get('plot_threads', []),
                    'world_state': context.get('world_state', {}),
                    'timeline_position': context.get('timeline_position'),
                    'previous_chapter_summary': context.get('previous_chapter_summary', '')
                }
            }

            # Surface specificity failures (if any) from LLM metadata onto the chapter doc for UI/debugging.
            try:
                spec_failures = None
                if isinstance(llm_metadata, dict):
                    spec_failures = llm_metadata.get("specificity_failures")
                if spec_failures:
                    chapter_data['metadata']['specificity_failures'] = spec_failures
            except Exception:
                pass
            
            # Save using the database integration layer
            chapter_id = await create_chapter(chapter_data)
            if chapter_id:
                self.logger.info(f"Chapter {chapter_number} saved to database: {chapter_id}")
                try:
                    from backend.services.vector_store_service import VectorStoreService
                except Exception:
                    try:
                        from services.vector_store_service import VectorStoreService
                    except Exception:
                        VectorStoreService = None
                if VectorStoreService:
                    try:
                        vector_service = VectorStoreService()
                        if vector_service.available:
                            await vector_service.ensure_project_vector_store(project_id, user_id)
                            await vector_service.upsert_chapter(
                                project_id=project_id,
                                user_id=user_id,
                                chapter_id=chapter_id,
                                chapter_number=chapter_number,
                                title=f"Chapter {chapter_number}",
                                content=chapter_content
                            )
                    except Exception as e:
                        self.logger.warning(f"Vector store update failed for Chapter {chapter_number}: {e}")
                try:
                    from backend.services.canon_log_service import update_canon_log
                    references = context.get("references", {}) or {
                        k.replace("_reference", ""): v
                        for k, v in (context or {}).items()
                        if isinstance(v, str) and k.endswith("_reference")
                    }
                    await update_canon_log(
                        project_id=project_id,
                        user_id=user_id,
                        chapter_number=chapter_number,
                        chapter_content=chapter_content,
                        book_bible=context.get("book_bible", ""),
                        references=references,
                        vector_store_ids=context.get("vector_store_ids", [])
                    )
                except Exception as canon_err:
                    self.logger.warning(f"Canon log update failed after Chapter {chapter_number}: {canon_err}")
                return chapter_id
            else:
                self.logger.warning(f"Failed to save Chapter {chapter_number} to database")
                return None
                
        except Exception as e:
            self.logger.error(f"Error saving Chapter {chapter_number} to database: {e}")
            # Don't fail the chapter generation if database save fails
            return None
    
    def pause_auto_completion(self) -> bool:
        """Pause the auto-completion process."""
        if self.current_status == AutoCompletionStatus.GENERATING:
            self.current_status = AutoCompletionStatus.PAUSED
            self.completion_data['status'] = "paused"
            self.logger.info("Auto-completion paused")
            return True
        return False
    
    def resume_auto_completion(self) -> bool:
        """Resume the auto-completion process."""
        if self.current_status == AutoCompletionStatus.PAUSED:
            self.current_status = AutoCompletionStatus.GENERATING
            self.completion_data['status'] = "generating"
            self.logger.info("Auto-completion resumed")
            return True
        return False
    
    def cancel_auto_completion(self) -> bool:
        """Cancel the auto-completion process."""
        if self.current_status in [AutoCompletionStatus.GENERATING, AutoCompletionStatus.PAUSED]:
            self.current_status = AutoCompletionStatus.CANCELLED
            self.completion_data['status'] = "cancelled"
            self.completion_data['end_time'] = datetime.utcnow().isoformat()
            self.logger.info("Auto-completion cancelled")
            return True
        return False
    
    def get_progress_status(self) -> Dict[str, Any]:
        """Get current progress status."""
        progress = {
            'job_id': self.job_id,
            'status': self.current_status.value,
            'progress': self.completion_data.get('progress', {}),
            'quality_scores': self.completion_data.get('quality_scores', []),
            'error_message': self.completion_data.get('error_message'),
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'current_chapter': self.completion_data.get('progress', {}).get('current_chapter', 0),
            'total_chapters': self.config.target_chapter_count
        }
        
        # Add completion time if finished
        if 'end_time' in self.completion_data:
            progress['end_time'] = self.completion_data['end_time']
        
        return progress
    
    def get_chapter_jobs(self) -> List[Dict[str, Any]]:
        """Get list of chapter jobs with their status."""
        return [
            {
                'chapter_number': job.chapter_number,
                'status': job.status,
                'start_time': job.start_time.isoformat() if job.start_time else None,
                'completion_time': job.completion_time.isoformat() if job.completion_time else None,
                'quality_score': job.quality_score,
                'word_count': job.word_count,
                'failure_reason': job.failure_reason
            }
            for job in self.chapter_jobs
        ] 