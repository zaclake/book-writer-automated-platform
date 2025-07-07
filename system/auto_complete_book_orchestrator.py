#!/usr/bin/env python3
"""
Auto-Complete Book Orchestrator
Manages sequential chapter generation with quality gates, context continuity, and failure recovery.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from llm_orchestrator import LLMOrchestrator, GenerationResult
from brutal_assessment_scorer import BrutalAssessmentScorer
from reader_engagement_scorer import ReaderEngagementScorer
from quality_gate_validator import QualityGateValidator
from chapter_context_manager import ChapterContextManager
from intelligent_retry_system import IntelligentRetrySystem, FailureType, RetryAttempt
from completion_detection_system import CompletionDetectionSystem, CompletionStatus
from failure_recovery_system import FailureRecoverySystem, RecoveryAction, FailureSeverity


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


@dataclass
class AutoCompletionConfig:
    """Configuration for auto-completion behavior."""
    target_word_count: int = 80000
    target_chapter_count: int = 20
    minimum_quality_score: float = 80.0
    max_retries_per_chapter: int = 3
    auto_pause_on_failure: bool = True
    context_improvement_enabled: bool = True
    quality_gates_enabled: bool = True
    user_review_required: bool = False


class AutoCompleteBookOrchestrator:
    """
    Orchestrates the auto-completion of an entire book through sequential chapter generation.
    
    Features:
    - Sequential chapter generation with quality gates
    - Context continuity management between chapters
    - Intelligent retry logic with context improvements
    - Real-time progress tracking
    - Failure recovery and rollback capabilities
    - User control (pause/resume/stop)
    """
    
    def __init__(self, project_path: str = ".", config: Optional[AutoCompletionConfig] = None):
        self.project_path = Path(project_path)
        self.state_dir = self.project_path / ".project-state"
        self.chapters_dir = self.project_path / "chapters"
        
        # Configuration
        self.config = config or AutoCompletionConfig()
        
        # Initialize components
        self.llm_orchestrator = LLMOrchestrator()
        self.brutal_scorer = BrutalAssessmentScorer()
        self.engagement_scorer = ReaderEngagementScorer()
        self.quality_validator = QualityGateValidator()
        self.context_manager = ChapterContextManager(project_path)
        self.completion_detector = CompletionDetectionSystem(project_path)
        self.recovery_system = FailureRecoverySystem(project_path)
        
        # State management
        self.job_id: Optional[str] = None
        self.current_status = AutoCompletionStatus.NOT_STARTED
        self.chapter_jobs: List[ChapterGenerationJob] = []
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        self._setup_logging()
        
        # Load state
        self._load_completion_state()
    
    def _setup_logging(self):
        """Set up logging for the orchestrator."""
        log_dir = self.project_path / "logs"
        log_dir.mkdir(exist_ok=True)
        
        handler = logging.FileHandler(log_dir / f"auto_completion_{datetime.now().strftime('%Y%m%d')}.log")
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
    
    def _load_completion_state(self):
        """Load existing completion state from file."""
        state_file = self.state_dir / "book-completion-state.json"
        if state_file.exists():
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    self.state_data = json.load(f)
                
                # Restore job state if exists
                job_data = self.state_data.get('book_completion_job', {})
                if job_data.get('job_id'):
                    self.job_id = job_data['job_id']
                    self.current_status = AutoCompletionStatus(job_data.get('status', 'not_started'))
                    self._restore_chapter_jobs()
                    
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                self.logger.warning(f"Failed to load completion state: {e}")
                self._initialize_default_state()
        else:
            self._initialize_default_state()
    
    def _initialize_default_state(self):
        """Initialize default completion state."""
        self.state_data = {
            "metadata": {
                "created": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "schema_version": "1.0",
                "auto_completion_enabled": True
            },
            "book_completion_job": {
                "job_id": None,
                "status": "not_started",
                "start_time": None,
                "estimated_completion_time": None,
                "current_chapter": 0,
                "total_chapters_planned": self.config.target_chapter_count,
                "chapters_completed": 0,
                "user_initiated": False,
                "max_retry_attempts": self.config.max_retries_per_chapter,
                "context_improvement_enabled": self.config.context_improvement_enabled
            },
            "chapter_generation_queue": {
                "pending_chapters": [],
                "current_chapter": None,
                "completed_chapters": [],
                "failed_chapters": [],
                "skipped_chapters": []
            },
            "quality_gate_configuration": {
                "enabled": self.config.quality_gates_enabled,
                "minimum_pass_score": self.config.minimum_quality_score,
                "auto_retry_on_failure": True,
                "max_retries_per_chapter": self.config.max_retries_per_chapter
            },
            "progress_tracking": {
                "overall_completion_percentage": 0.0,
                "current_phase": "not_started",
                "chapters_progress": {},
                "estimated_time_remaining": None,
                "velocity_metrics": {
                    "avg_chapter_generation_time": None,
                    "success_rate": 1.0
                }
            },
            "context_management": {
                "previous_chapters_summary": "",
                "character_development_continuity": {},
                "plot_advancement_tracking": {},
                "theme_consistency": {}
            },
            "auto_completion_log": {
                "session_logs": [],
                "chapter_generation_logs": [],
                "quality_assessment_logs": [],
                "error_logs": []
            }
        }
    
    def _save_completion_state(self):
        """Save current completion state to file."""
        self.state_data['metadata']['last_updated'] = datetime.now().isoformat()
        
        # Update job state
        job_data = self.state_data['book_completion_job']
        job_data['job_id'] = self.job_id
        job_data['status'] = self.current_status.value
        
        # Save chapter jobs
        queue_data = self.state_data['chapter_generation_queue']
        queue_data['pending_chapters'] = [job.chapter_number for job in self.chapter_jobs if job.status == 'pending']
        queue_data['completed_chapters'] = [job.chapter_number for job in self.chapter_jobs if job.status == 'completed']
        queue_data['failed_chapters'] = [job.chapter_number for job in self.chapter_jobs if job.status == 'failed']
        
        state_file = self.state_dir / "book-completion-state.json"
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(self.state_data, f, indent=2, ensure_ascii=False)
    
    def _restore_chapter_jobs(self):
        """Restore chapter jobs from state data."""
        self.chapter_jobs = []
        queue_data = self.state_data.get('chapter_generation_queue', {})
        
        # Restore from all chapter lists
        for status in ['pending', 'completed', 'failed']:
            chapters = queue_data.get(f'{status}_chapters', [])
            for chapter_num in chapters:
                job = ChapterGenerationJob(
                    chapter_number=chapter_num,
                    status=status
                )
                self.chapter_jobs.append(job)
    
    def start_auto_completion(self, user_initiated: bool = True) -> str:
        """
        Start the auto-completion process.
        
        Args:
            user_initiated: Whether this was initiated by a user action
            
        Returns:
            Job ID for tracking the completion process
        """
        if self.current_status != AutoCompletionStatus.NOT_STARTED:
            raise ValueError(f"Auto-completion already started (status: {self.current_status.value})")
        
        # Generate unique job ID
        self.job_id = str(uuid.uuid4())
        self.current_status = AutoCompletionStatus.INITIALIZING
        
        # Update state
        self.state_data['book_completion_job']['job_id'] = self.job_id
        self.state_data['book_completion_job']['user_initiated'] = user_initiated
        self.state_data['book_completion_job']['start_time'] = datetime.now().isoformat()
        
        # Initialize chapter generation queue
        self._initialize_chapter_queue()
        
        # Save state
        self._save_completion_state()
        
        # Log start
        self.logger.info(f"Auto-completion started - Job ID: {self.job_id}")
        self._log_session_event("auto_completion_started", {"job_id": self.job_id, "user_initiated": user_initiated})
        
        return self.job_id
    
    def _initialize_chapter_queue(self):
        """Initialize the chapter generation queue."""
        self.chapter_jobs = []
        
        # Determine starting chapter (skip existing completed chapters)
        existing_chapters = self._get_existing_chapters()
        start_chapter = len(existing_chapters) + 1
        
        # Create jobs for remaining chapters
        for chapter_num in range(start_chapter, self.config.target_chapter_count + 1):
            job = ChapterGenerationJob(
                chapter_number=chapter_num,
                status='pending'
            )
            self.chapter_jobs.append(job)
        
        self.logger.info(f"Initialized chapter queue: {len(self.chapter_jobs)} chapters to generate")
    
    def _get_existing_chapters(self) -> List[int]:
        """Get list of existing chapter numbers."""
        if not self.chapters_dir.exists():
            return []
        
        existing = []
        for file in self.chapters_dir.glob("chapter-*.md"):
            try:
                # Extract chapter number from filename
                chapter_num = int(file.stem.split('-')[1])
                existing.append(chapter_num)
            except (ValueError, IndexError):
                continue
        
        return sorted(existing)
    
    async def run_auto_completion(self) -> Dict[str, Any]:
        """
        Run the complete auto-completion process.
        
        Returns:
            Completion results and statistics
        """
        if self.current_status == AutoCompletionStatus.NOT_STARTED:
            raise ValueError("Auto-completion not started. Call start_auto_completion() first.")
        
        self.current_status = AutoCompletionStatus.GENERATING
        self._save_completion_state()
        
        completion_results = {
            "job_id": self.job_id,
            "start_time": datetime.now().isoformat(),
            "chapters_generated": [],
            "chapters_failed": [],
            "total_word_count": 0,
            "average_quality_score": 0.0,
            "completion_status": "in_progress"
        }
        
        try:
            # Generate chapters sequentially
            for job in self.chapter_jobs:
                if job.status != 'pending':
                    continue
                
                # Check for user control requests
                if self._check_user_control_requests():
                    break
                
                # Check completion status before generating next chapter
                if not self.completion_detector.should_continue_generation():
                    completion_analysis = self.completion_detector.analyze_completion_status()
                    
                    if completion_analysis.status == CompletionStatus.COMPLETED:
                        self.logger.info("Book completion detected - stopping generation")
                        completion_results['completion_reason'] = "Story naturally completed"
                        completion_results['completion_analysis'] = self.completion_detector.get_completion_summary()
                        break
                    elif completion_analysis.status == CompletionStatus.OVER_TARGET:
                        self.logger.info("Book over target length - stopping generation")
                        completion_results['completion_reason'] = "Exceeded target word count"
                        completion_results['completion_analysis'] = self.completion_detector.get_completion_summary()
                        break
                
                # Generate chapter
                chapter_result = await self._generate_chapter_with_quality_gates(job)
                
                if chapter_result['success']:
                    completion_results['chapters_generated'].append(chapter_result)
                    completion_results['total_word_count'] += chapter_result.get('word_count', 0)
                else:
                    completion_results['chapters_failed'].append({
                        'chapter_number': job.chapter_number,
                        'failure_reason': chapter_result.get('error', 'Unknown error')
                    })
                    
                    # Handle failure based on configuration
                    if self.config.auto_pause_on_failure:
                        self.logger.warning(f"Auto-pausing due to chapter {job.chapter_number} failure")
                        self.current_status = AutoCompletionStatus.PAUSED
                        break
            
            # Calculate final results
            if completion_results['chapters_generated']:
                total_quality = sum(ch.get('quality_score', 0) for ch in completion_results['chapters_generated'])
                completion_results['average_quality_score'] = total_quality / len(completion_results['chapters_generated'])
            
            # Determine completion status
            if self.current_status == AutoCompletionStatus.PAUSED:
                completion_results['completion_status'] = "paused"
            elif len(completion_results['chapters_failed']) == 0:
                completion_results['completion_status'] = "completed"
                self.current_status = AutoCompletionStatus.COMPLETED
            else:
                completion_results['completion_status'] = "completed_with_failures"
                self.current_status = AutoCompletionStatus.COMPLETED
            
            completion_results['end_time'] = datetime.now().isoformat()
            
        except Exception as e:
            self.logger.error(f"Auto-completion failed: {e}")
            completion_results['completion_status'] = "failed"
            completion_results['error'] = str(e)
            self.current_status = AutoCompletionStatus.FAILED
        
        finally:
            self._save_completion_state()
            self._log_session_event("auto_completion_finished", completion_results)
        
        return completion_results
    
    async def _generate_chapter_with_quality_gates(self, job: ChapterGenerationJob) -> Dict[str, Any]:
        """
        Generate a chapter with quality gates and retry logic.
        
        Args:
            job: Chapter generation job
            
        Returns:
            Generation result with quality assessment
        """
        job.status = 'generating'
        job.start_time = datetime.now()
        self._save_completion_state()
        
        self.logger.info(f"Starting generation for Chapter {job.chapter_number}")
        
        for attempt in range(self.config.max_retries_per_chapter + 1):
            try:
                # Build context for this chapter
                context = self._build_chapter_context(job.chapter_number, attempt)
                
                # Generate chapter using 5-stage process
                generation_results = self.llm_orchestrator.generate_chapter_5_stage(
                    chapter_number=job.chapter_number,
                    target_words=self.config.target_word_count // self.config.target_chapter_count,
                    context=context
                )
                
                # Get final chapter content
                if generation_results and generation_results[-1].success:
                    chapter_content = generation_results[-1].content
                    
                    # Save chapter to file
                    chapter_file = self.chapters_dir / f"chapter-{job.chapter_number:02d}.md"
                    self.chapters_dir.mkdir(exist_ok=True)
                    
                    with open(chapter_file, 'w', encoding='utf-8') as f:
                        f.write(chapter_content)
                    
                    # Run quality assessment
                    quality_result = await self._assess_chapter_quality(chapter_file, job.chapter_number)
                    
                    # Check quality gates
                    if self._passes_quality_gates(quality_result):
                        job.status = 'completed'
                        job.completion_time = datetime.now()
                        job.quality_score = quality_result.get('overall_score', 0)
                        
                        # Update context for next chapter
                        self._update_chapter_context(job.chapter_number, chapter_content, quality_result)
                        
                        # Create recovery point after successful chapter
                        self.recovery_system.create_recovery_point(
                            job.chapter_number, 
                            self._build_chapter_context(job.chapter_number)
                        )
                        
                        self.logger.info(f"Chapter {job.chapter_number} completed successfully (Quality: {job.quality_score})")
                        
                        return {
                            'success': True,
                            'chapter_number': job.chapter_number,
                            'word_count': len(chapter_content.split()),
                            'quality_score': job.quality_score,
                            'attempt': attempt + 1,
                            'generation_time': (job.completion_time - job.start_time).total_seconds()
                        }
                    else:
                        job.retry_count += 1
                        self.logger.warning(f"Chapter {job.chapter_number} failed quality gates (attempt {attempt + 1})")
                        
                        if attempt < self.config.max_retries_per_chapter:
                            # Improve context for retry
                            if self.config.context_improvement_enabled:
                                context = self._improve_context_for_retry(context, quality_result)
                        continue
                else:
                    self.logger.error(f"Chapter {job.chapter_number} generation failed")
                    continue
                    
            except Exception as e:
                self.logger.error(f"Chapter {job.chapter_number} generation error: {e}")
                continue
        
        # All attempts failed - analyze and attempt recovery
        job.status = 'failed'
        job.failure_reason = f"Failed after {self.config.max_retries_per_chapter} attempts"
        
        # Analyze failure and attempt recovery
        failure_event = self.recovery_system.analyze_failure(
            job.chapter_number, 
            job.failure_reason,
            self._build_chapter_context(job.chapter_number)
        )
        
        # Determine if recovery should be attempted
        if failure_event.severity in [FailureSeverity.HIGH, FailureSeverity.CRITICAL, FailureSeverity.CATASTROPHIC]:
            suggested_actions = self.recovery_system.suggest_recovery_actions(failure_event)
            
            self.logger.warning(f"Attempting recovery for critical failure in chapter {job.chapter_number}")
            recovery_success = self.recovery_system.execute_recovery(failure_event, suggested_actions)
            
            if recovery_success:
                self.logger.info(f"Recovery successful for chapter {job.chapter_number}")
                # Update job status to allow retry
                job.status = 'pending'
                job.retry_count = 0
                self._save_completion_state()
                
                return {
                    'success': True,
                    'chapter_number': job.chapter_number,
                    'recovery_applied': True,
                    'recovery_actions': [action.value for action in suggested_actions],
                    'message': 'Chapter recovered and ready for retry'
                }
        
        self._save_completion_state()
        
        return {
            'success': False,
            'chapter_number': job.chapter_number,
            'error': job.failure_reason,
            'attempts': self.config.max_retries_per_chapter + 1,
            'failure_severity': failure_event.severity.value
        }
    
    def _build_chapter_context(self, chapter_number: int, attempt: int = 0) -> Dict[str, Any]:
        """Build context for chapter generation using ChapterContextManager."""
        # Get comprehensive context from context manager
        context_data = self.context_manager.build_next_chapter_context(chapter_number)
        
        # Add generation-specific context
        context = {
            "chapter_number": chapter_number,
            "target_words": self.config.target_word_count // self.config.target_chapter_count,
            "attempt": attempt,
            "total_chapters_planned": self.config.target_chapter_count,
            "context_quality_score": context_data.get('context_quality_score', 8.0),
            
            # Story continuity context
            "story_so_far": context_data.get('story_so_far', ''),
            "previous_chapters_count": context_data.get('previous_chapters_count', 0),
            
            # Character continuity
            "character_continuity": context_data.get('character_continuity', {}),
            "character_development_needs": context_data.get('character_development_needs', {}),
            
            # Plot continuity
            "plot_threads": context_data.get('plot_threads', {}),
            "required_plot_advancement": context_data.get('required_plot_advancement', {}),
            
            # World and theme continuity
            "world_state": context_data.get('world_state', {}),
            "themes_to_continue": context_data.get('themes_to_continue', []),
            
            # Questions and mysteries
            "unresolved_questions": context_data.get('unresolved_questions', []),
            
            # Pacing and continuity guidance
            "pacing_guidance": context_data.get('pacing_guidance', {}),
            "continuity_requirements": context_data.get('continuity_requirements', [])
        }
        
        # Add retry-specific context if this is a retry
        if attempt > 0:
            context["retry_attempt"] = attempt
            context["retry_guidance"] = f"This is retry attempt {attempt}. Focus on addressing previous quality issues."
        
        return context
    
    def _get_previous_chapters_summary(self, up_to_chapter: int) -> str:
        """Get summary of previous chapters for context."""
        summary_parts = []
        
        for i in range(1, up_to_chapter + 1):
            chapter_file = self.chapters_dir / f"chapter-{i:02d}.md"
            if chapter_file.exists():
                try:
                    with open(chapter_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        # Extract first paragraph as summary
                        first_paragraph = content.split('\n\n')[0]
                        summary_parts.append(f"Chapter {i}: {first_paragraph[:200]}...")
                except Exception as e:
                    self.logger.warning(f"Could not read chapter {i}: {e}")
        
        return "\n".join(summary_parts)
    
    async def _assess_chapter_quality(self, chapter_file: Path, chapter_number: int) -> Dict[str, Any]:
        """Assess chapter quality using existing quality assessment system."""
        try:
            with open(chapter_file, 'r', encoding='utf-8') as f:
                chapter_content = f.read()
            
            word_count = len(chapter_content.split())
            
            # Run brutal assessment
            brutal_result = self.brutal_scorer.assess_chapter(chapter_content, chapter_number)
            
            # Run engagement scoring
            engagement_result = self.engagement_scorer.analyze_chapter_engagement(chapter_content, chapter_number)
            
            # Run quality gate validation (check critical failures and word count)
            critical_failures = self.quality_validator.check_critical_failures(chapter_content, {'word_count': word_count})
            word_count_result = self.quality_validator.validate_word_count(word_count)
            
            # Build category scores for overall assessment
            category_scores = {}
            for category, score_obj in brutal_result.category_scores.items():
                category_scores[category] = score_obj.score
            
            # Add engagement score as reader engagement category
            category_scores['reader_engagement'] = engagement_result.engagement_score
            
            # Get overall quality assessment
            quality_assessment = self.quality_validator.assess_overall_quality(category_scores)
            
            # Calculate combined overall score (0-100 scale)
            overall_score = (
                brutal_result.overall_score * 0.5 +  # Brutal assessment (0-100)
                engagement_result.engagement_score * 10 * 0.3 +  # Engagement (0-10) -> (0-100)
                quality_assessment['overall_score'] * 10 * 0.2  # Quality gates (0-10) -> (0-100)
            )
            
            return {
                'overall_score': overall_score,
                'brutal_assessment': {
                    'score': brutal_result.overall_score,
                    'level': brutal_result.assessment_level,
                    'passed': brutal_result.passed,
                    'category_scores': {k: v.score for k, v in brutal_result.category_scores.items()},
                    'critical_failures': brutal_result.critical_failures
                },
                'engagement_score': {
                    'score': engagement_result.engagement_score,
                    'hook_strength': engagement_result.hook_strength,
                    'momentum_maintenance': engagement_result.momentum_maintenance,
                    'ending_propulsion': engagement_result.ending_propulsion,
                    'risk_flags': engagement_result.risk_flags,
                    'recommendations': engagement_result.recommendations
                },
                'quality_gates': {
                    'overall_passed': quality_assessment['overall_passed'],
                    'critical_failures': critical_failures,
                    'word_count_assessment': {
                        'score': word_count_result.score,
                        'passed': word_count_result.passed,
                        'notes': word_count_result.notes
                    }
                },
                'word_count': word_count,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Quality assessment failed for chapter {chapter_number}: {e}")
            return {
                'overall_score': 0.0,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def _passes_quality_gates(self, quality_result: Dict[str, Any]) -> bool:
        """Check if chapter passes quality gates."""
        if 'error' in quality_result:
            return False
        
        overall_score = quality_result.get('overall_score', 0)
        return overall_score >= self.config.minimum_quality_score
    
    def _update_chapter_context(self, chapter_number: int, chapter_content: str, quality_result: Dict[str, Any]):
        """Update context management with completed chapter information using ChapterContextManager."""
        # Use ChapterContextManager to analyze and store chapter context
        chapter_context = self.context_manager.analyze_chapter_content(chapter_number, chapter_content)
        
        # Update legacy state data for compatibility
        context_mgmt = self.state_data['context_management']
        
        # Update previous chapters summary with rich context
        context_mgmt['previous_chapters_summary'] = chapter_context.summary
        
        # Update character development tracking with detected characters
        context_mgmt['character_development_continuity'][f'chapter_{chapter_number}'] = {
            'completed': True,
            'characters_present': chapter_context.characters_present,
            'emotional_tone': chapter_context.emotional_tone,
            'themes_explored': chapter_context.themes_explored,
            'quality_score': quality_result.get('overall_score', 0),
            'timestamp': datetime.now().isoformat()
        }
        
        # Update plot advancement tracking with detailed analysis
        context_mgmt['plot_advancement_tracking'][f'chapter_{chapter_number}'] = {
            'completed': True,
            'word_count': chapter_context.word_count,
            'key_events': chapter_context.key_events,
            'plot_advancement': chapter_context.plot_advancement,
            'questions_raised': len(chapter_context.questions_raised),
            'questions_answered': len(chapter_context.questions_answered),
            'cliffhangers': chapter_context.cliffhangers,
            'quality_score': quality_result.get('overall_score', 0),
            'context_quality': self.context_manager.get_context_summary()['context_quality_score']
        }
        
        self.logger.info(f"Chapter {chapter_number} context updated - Characters: {len(chapter_context.characters_present)}, "
                        f"Events: {len(chapter_context.key_events)}, Questions: {len(chapter_context.questions_raised)}")
        
        # Log context quality for monitoring
        context_summary = self.context_manager.get_context_summary()
        self.logger.info(f"Context quality score: {context_summary['context_quality_score']:.1f}/10.0")
        
        return chapter_context
    
    def _improve_context_for_retry(self, context: Dict[str, Any], quality_result: Dict[str, Any]) -> Dict[str, Any]:
        """Improve context based on quality assessment feedback for retry."""
        improved_context = context.copy()
        
        # Add specific improvement guidance based on quality issues
        if 'brutal_assessment' in quality_result:
            brutal_data = quality_result['brutal_assessment']
            if brutal_data.get('prose_quality_score', 0) < 7:
                improved_context['focus_improvement'] = "prose_quality"
            elif brutal_data.get('character_development_score', 0) < 7:
                improved_context['focus_improvement'] = "character_development"
            elif brutal_data.get('plot_advancement_score', 0) < 7:
                improved_context['focus_improvement'] = "plot_advancement"
        
        improved_context['retry_attempt'] = context.get('attempt', 0) + 1
        improved_context['quality_feedback'] = quality_result
        
        return improved_context
    
    def _check_user_control_requests(self) -> bool:
        """Check for user control requests (pause/stop)."""
        user_control = self.state_data.get('user_control', {})
        
        if user_control.get('pause_requested'):
            self.current_status = AutoCompletionStatus.PAUSED
            self.logger.info("Auto-completion paused by user request")
            return True
        
        if user_control.get('stop_requested'):
            self.current_status = AutoCompletionStatus.CANCELLED
            self.logger.info("Auto-completion cancelled by user request")
            return True
        
        return False
    
    def _log_session_event(self, event_type: str, data: Dict[str, Any]):
        """Log session events to the completion log."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "job_id": self.job_id,
            "data": data
        }
        
        self.state_data['auto_completion_log']['session_logs'].append(log_entry)
        
        # Keep only last 100 log entries
        if len(self.state_data['auto_completion_log']['session_logs']) > 100:
            self.state_data['auto_completion_log']['session_logs'] = self.state_data['auto_completion_log']['session_logs'][-100:]
    
    def pause_auto_completion(self) -> bool:
        """Pause the auto-completion process."""
        if self.current_status in [AutoCompletionStatus.GENERATING, AutoCompletionStatus.QUALITY_CHECKING]:
            self.state_data['user_control']['pause_requested'] = True
            self._save_completion_state()
            self.logger.info("Auto-completion pause requested")
            return True
        return False
    
    def resume_auto_completion(self) -> bool:
        """Resume the auto-completion process."""
        if self.current_status == AutoCompletionStatus.PAUSED:
            self.current_status = AutoCompletionStatus.GENERATING
            self.state_data['user_control']['pause_requested'] = False
            self.state_data['user_control']['resume_requested'] = True
            self._save_completion_state()
            self.logger.info("Auto-completion resumed")
            return True
        return False
    
    def stop_auto_completion(self) -> bool:
        """Stop the auto-completion process."""
        if self.current_status not in [AutoCompletionStatus.COMPLETED, AutoCompletionStatus.CANCELLED]:
            self.current_status = AutoCompletionStatus.CANCELLED
            self.state_data['user_control']['stop_requested'] = True
            self._save_completion_state()
            self.logger.info("Auto-completion stopped")
            return True
        return False
    
    def get_progress_status(self) -> Dict[str, Any]:
        """Get current progress status."""
        completed_chapters = [job for job in self.chapter_jobs if job.status == 'completed']
        failed_chapters = [job for job in self.chapter_jobs if job.status == 'failed']
        
        total_chapters = len(self.chapter_jobs)
        completed_count = len(completed_chapters)
        
        progress_percentage = (completed_count / total_chapters * 100) if total_chapters > 0 else 0
        
        return {
            "job_id": self.job_id,
            "status": self.current_status.value,
            "progress_percentage": progress_percentage,
            "chapters_completed": completed_count,
            "chapters_failed": len(failed_chapters),
            "total_chapters": total_chapters,
            "current_chapter": self._get_current_chapter_number(),
            "estimated_time_remaining": self._calculate_estimated_time_remaining(),
            "last_updated": datetime.now().isoformat()
        }
    
    def _get_current_chapter_number(self) -> Optional[int]:
        """Get the current chapter being processed."""
        for job in self.chapter_jobs:
            if job.status == 'generating':
                return job.chapter_number
        return None
    
    def _calculate_estimated_time_remaining(self) -> Optional[str]:
        """Calculate estimated time remaining for completion."""
        completed_jobs = [job for job in self.chapter_jobs if job.status == 'completed' and job.start_time and job.completion_time]
        
        if not completed_jobs:
            return None
        
        # Calculate average chapter generation time
        total_time = sum(
            (job.completion_time - job.start_time).total_seconds() 
            for job in completed_jobs
        )
        avg_time_per_chapter = total_time / len(completed_jobs)
        
        # Calculate remaining chapters
        remaining_chapters = len([job for job in self.chapter_jobs if job.status == 'pending'])
        
        if remaining_chapters == 0:
            return "0 minutes"
        
        estimated_seconds = remaining_chapters * avg_time_per_chapter
        estimated_minutes = int(estimated_seconds / 60)
        
        if estimated_minutes < 60:
            return f"{estimated_minutes} minutes"
        else:
            hours = estimated_minutes // 60
            minutes = estimated_minutes % 60
            return f"{hours} hours {minutes} minutes"


# CLI Interface
if __name__ == "__main__":
    import argparse
    import asyncio
    
    parser = argparse.ArgumentParser(description="Auto-Complete Book Orchestrator")
    parser.add_argument("action", choices=["start", "status", "pause", "resume", "stop"], 
                       help="Action to perform")
    parser.add_argument("--project-path", default=".", help="Path to project directory")
    parser.add_argument("--chapters", type=int, default=20, help="Target number of chapters")
    parser.add_argument("--words", type=int, default=80000, help="Target word count")
    parser.add_argument("--quality-threshold", type=float, default=80.0, help="Minimum quality score")
    
    args = parser.parse_args()
    
    # Configure orchestrator
    config = AutoCompletionConfig(
        target_chapter_count=args.chapters,
        target_word_count=args.words,
        minimum_quality_score=args.quality_threshold
    )
    
    orchestrator = AutoCompleteBookOrchestrator(args.project_path, config)
    
    if args.action == "start":
        job_id = orchestrator.start_auto_completion(user_initiated=True)
        print(f"🚀 Auto-completion started - Job ID: {job_id}")
        
        # Run the completion process
        results = asyncio.run(orchestrator.run_auto_completion())
        
        print(f"📊 Completion Results:")
        print(f"  Status: {results['completion_status']}")
        print(f"  Chapters generated: {len(results['chapters_generated'])}")
        print(f"  Chapters failed: {len(results['chapters_failed'])}")
        print(f"  Total word count: {results['total_word_count']:,}")
        print(f"  Average quality score: {results['average_quality_score']:.1f}")
        
    elif args.action == "status":
        status = orchestrator.get_progress_status()
        print(f"📈 Auto-Completion Status:")
        print(f"  Job ID: {status['job_id']}")
        print(f"  Status: {status['status']}")
        print(f"  Progress: {status['progress_percentage']:.1f}%")
        print(f"  Chapters completed: {status['chapters_completed']}/{status['total_chapters']}")
        print(f"  Current chapter: {status['current_chapter']}")
        print(f"  Estimated time remaining: {status['estimated_time_remaining']}")
        
    elif args.action == "pause":
        success = orchestrator.pause_auto_completion()
        print(f"⏸️  Auto-completion {'paused' if success else 'could not be paused'}")
        
    elif args.action == "resume":
        success = orchestrator.resume_auto_completion()
        print(f"▶️  Auto-completion {'resumed' if success else 'could not be resumed'}")
        
    elif args.action == "stop":
        success = orchestrator.stop_auto_completion()
        print(f"⏹️  Auto-completion {'stopped' if success else 'could not be stopped'}") 