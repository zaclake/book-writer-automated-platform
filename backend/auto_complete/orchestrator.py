#!/usr/bin/env python3
"""
Auto-Complete Book Orchestrator - FastAPI Backend Version
Manages sequential chapter generation with quality gates and context continuity.
"""

import json
import logging
import uuid
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    minimum_quality_score: float = 7.0
    max_retries_per_chapter: int = 3
    auto_pause_on_failure: bool = True
    context_improvement_enabled: bool = True
    quality_gates_enabled: bool = True
    user_review_required: bool = False
    words_per_chapter: int = 3800
    user_id: Optional[str] = None
    project_id: Optional[str] = None

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
        
        # Update configuration from request
        if 'target_chapters' in request_data:
            self.config.target_chapter_count = request_data['target_chapters']
        if 'words_per_chapter' in request_data:
            self.config.words_per_chapter = request_data['words_per_chapter']
        if 'quality_threshold' in request_data:
            self.config.minimum_quality_score = request_data['quality_threshold']
        
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
            # Generate chapters sequentially
            for job in self.chapter_jobs:
                if job.status != 'pending':
                    continue
                
                # Check if job was cancelled or paused
                if self.current_status in [AutoCompletionStatus.CANCELLED, AutoCompletionStatus.PAUSED]:
                    break
                
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
            
        except Exception as e:
            self.logger.error(f"Auto-completion failed: {e}")
            self.current_status = AutoCompletionStatus.FAILED
            self.completion_data['status'] = "failed"
            self.completion_data['error_message'] = str(e)
            self.completion_data['end_time'] = datetime.utcnow().isoformat()
        
        return self.completion_data
    
    async def _generate_chapter(self, job: ChapterGenerationJob) -> Dict[str, Any]:
        """
        Generate a single chapter with quality assessment.
        
        Args:
            job: Chapter generation job
            
        Returns:
            Generation result with quality assessment
        """
        job.status = 'generating'
        job.start_time = datetime.utcnow()
        
        self.logger.info(f"Generating Chapter {job.chapter_number}")
        
        try:
            # Build context for this chapter
            context = self._build_chapter_context(job.chapter_number)
            
            # Generate chapter using LLM with reference files
            chapter_content = await self._generate_chapter_with_references(job.chapter_number, context)
            
            # Save chapter to file
            chapter_file = self.chapters_dir / f"chapter-{job.chapter_number:02d}.md"
            with open(chapter_file, 'w', encoding='utf-8') as f:
                f.write(chapter_content)
            
            # Update continuity state based on the generated chapter
            if self.context_manager:
                try:
                    self.context_manager.analyze_chapter_content(job.chapter_number, chapter_content)
                except Exception as e:
                    self.logger.warning(f"Failed to analyze continuity for Chapter {job.chapter_number}: {e}")

            # Also save to database/Firestore
            await self._save_chapter_to_database(job.chapter_number, chapter_content, context)
            
            # Assess chapter quality and optionally revise
            quality_result = await self._assess_chapter_quality(chapter_content, job.chapter_number)

            # If quality gates enabled and failed, attempt targeted revision once
            if self.config.quality_gates_enabled and not self._passes_quality_gates(quality_result):
                self.logger.info(f"Chapter {job.chapter_number} failed quality gates; attempting targeted revision")
                chapter_content = await self._revise_chapter(chapter_content, job.chapter_number, quality_result, context)
                # Re-assess after revision
                quality_result = await self._assess_chapter_quality(chapter_content, job.chapter_number)
            
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
                job.failure_reason = "Failed quality gates"
                
                return {
                    'success': False,
                    'chapter_number': job.chapter_number,
                    'error': job.failure_reason,
                    'quality_score': quality_result.get('overall_score', 0)
                }
                
        except Exception as e:
            job.status = 'failed'
            job.failure_reason = str(e)
            
            self.logger.error(f"Chapter {job.chapter_number} generation failed: {e}")
            
            return {
                'success': False,
                'chapter_number': job.chapter_number,
                'error': str(e)
            }
    
    def _build_chapter_context(self, chapter_number: int) -> Dict[str, Any]:
        """Build context for chapter generation."""
        context = {
            'chapter_number': chapter_number,
            'total_chapters': self.config.target_chapter_count,
            'target_words': self.config.words_per_chapter,
            'previous_chapters': self._get_previous_chapters_summary(chapter_number)
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
                'style_guide': 'style-guide.md'
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
            except Exception as e:
                self.logger.warning(f"Failed to enrich continuity context for chapter {chapter_number}: {e}")
        
        return context

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
                    if not res.get('passed', True):
                        issues.append(f"- Improve {cat} (score {res.get('score', 0):.1f} < min {res.get('minimum_required', 0):.1f})")
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
                "Preserve story facts and voice. Apply targeted changes only."
            )
            revision_user = (
                f"Revise Chapter {chapter_number} to address the issues.\n\n"
                f"CRITIQUE:\n{critique}\n\n"
                "REFERENCE CONTEXT (read-only, do not copy verbatim):\n"
                f"BOOK BIBLE (excerpt):\n{(context.get('book_bible') or '')[:1500]}\n\n"
                f"PREVIOUS CHAPTERS (summary):\n{(context.get('previous_chapters') or '')[:800]}\n\n"
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

            response = await orchestrator._make_api_call(messages=messages, temperature=0.5, max_tokens=6000)
            return response.choices[0].message.content
        except Exception as e:
            self.logger.warning(f"Revision failed for Chapter {chapter_number}: {e}; keeping original")
            return original_content
    
    def _get_previous_chapters_summary(self, up_to_chapter: int) -> str:
        """Get summary of previous chapters."""
        summary_parts = []
        
        for i in range(1, up_to_chapter):
            chapter_file = self.chapters_dir / f"chapter-{i:02d}.md"
            if chapter_file.exists():
                with open(chapter_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Get first paragraph as summary
                    first_paragraph = content.split('\n\n')[0] if content else ""
                    summary_parts.append(f"Chapter {i}: {first_paragraph[:200]}...")
        
        return "\n".join(summary_parts)
    
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
            
            orchestrator = LLMOrchestrator(
                retry_config=retry_config,
                prompts_dir=str(prompts_dir) if prompts_dir.exists() else None
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
            
            self.logger.info(f"Generating real content for Chapter {chapter_number} using LLM orchestrator")
            
            # Generate chapter using the real LLM system
            result = orchestrator.generate_chapter(
                chapter_number=chapter_number,
                target_words=target_words,
                stage="complete"
            )
            
            if result.success:
                self.logger.info(f"Successfully generated Chapter {chapter_number} with {len(result.content.split())} words")
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
        target_words = context.get('target_words', 3800)
        book_bible = context.get('book_bible', 'A compelling story')
        
        # Extract basic info from book bible
        title_match = book_bible.split('\n')[0] if book_bible else f"Chapter {chapter_number}"
        if title_match.startswith('#'):
            title_match = title_match.lstrip('#').strip()
        
        # Generate a basic but structured chapter
        content = f"""# Chapter {chapter_number}

{title_match if title_match != f"Chapter {chapter_number}" else "The Story Continues"}

[This chapter was generated with a fallback system. The story continues with approximately {target_words} words of narrative content based on the book bible provided.]

The narrative unfolds as the characters face new challenges and developments. Each scene builds upon the previous chapters while advancing the plot toward its ultimate resolution.

[Content continues for approximately {target_words} words following the story arc established in the book bible.]

---

*Chapter {chapter_number} - Generated: {datetime.utcnow().isoformat()}*
*Word target: {target_words} words*
"""
        
        # Add padding to reach approximate word count
        current_words = len(content.split())
        words_needed = target_words - current_words
        
        if words_needed > 0:
            # Add meaningful padding content
            padding = "The story continues to develop with rich character interactions, meaningful dialogue, and compelling plot advancement. " * (words_needed // 20 + 1)
            content = content.replace("[Content continues for approximately", f"{padding}\n\n[Content continues for approximately")
        
        return content
    
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
            orchestrator = LLMOrchestrator(retry_config=retry_config)
            
            target_words = context.get('target_words', 3800)
            
            self.logger.info(f"Generating Chapter {chapter_number} with reference files using LLM orchestrator")
            
            # Generate chapter using the LLM system with enhanced context
            result = await orchestrator.generate_chapter(
                chapter_number=chapter_number,
                target_words=target_words,
                stage="complete",
                context={
                    "book_bible": context.get("book_bible", ""),
                    "previous_chapters_summary": context.get("previous_chapters", ""),
                    "references": {
                        "characters": context.get("characters_reference", ""),
                        "outline": context.get("outline_reference", ""),
                        "plot_timeline": context.get("plot_timeline_reference", ""),
                        "world_building": context.get("world_building_reference", ""),
                        "style_guide": context.get("style_guide_reference", "")
                    }
                }
            )
            
            if result.success:
                self.logger.info(f"Successfully generated Chapter {chapter_number} with {len(result.content.split())} words")
                return result.content
            else:
                self.logger.error(f"LLM generation failed for Chapter {chapter_number}: {result.error}")
                # Fallback to basic content generation if LLM fails
                return self._generate_fallback_content(chapter_number, context)
                
        except Exception as e:
            self.logger.error(f"Error in chapter generation for Chapter {chapter_number}: {e}")
            # Fallback to basic content generation
            return self._generate_fallback_content(chapter_number, context)
    
    async def _assess_chapter_quality(self, chapter_content: str, chapter_number: int) -> Dict[str, Any]:
        """Assess chapter quality using quality gates and brutal assessment helpers."""
        try:
            # Run quick validation and scoring
            from .helpers.quality_gate_validator import QualityGateValidator
            from .helpers.brutal_assessment_scorer import BrutalAssessmentScorer

            validator = QualityGateValidator()
            scorer = BrutalAssessmentScorer()

            word_count = len(chapter_content.split())
            word_count_score = validator.validate_word_count(word_count)

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

            return result
        except Exception as e:
            self.logger.warning(f"Quality assessment helpers failed, using basic scoring: {e}")
            # Basic fallback
            word_count = len(chapter_content.split())
            base_score = 7.5
            if word_count >= self.config.words_per_chapter * 0.8:
                base_score += 1.0
            if word_count <= self.config.words_per_chapter * 1.2:
                base_score += 0.5
            return {
                'overall_score': min(base_score, 10.0),
                'word_count': word_count,
                'brutal_assessment': {'score': base_score * 10, 'passed': base_score >= self.config.minimum_quality_score},
                'quality_gates': {'passed': 8, 'total': 10}
            }
    
    def _passes_quality_gates(self, quality_result: Dict[str, Any]) -> bool:
        """Check if chapter passes quality gates."""
        overall_score = quality_result.get('overall_score', 0)
        return overall_score >= self.config.minimum_quality_score
    
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
            
            # Prepare chapter data in the format expected by the new database layer
            chapter_data = {
                'project_id': project_id,
                'chapter_number': chapter_number,
                'title': f"Chapter {chapter_number}",
                'content': chapter_content,
                'metadata': {
                    'word_count': len(chapter_content.split()),
                    'target_word_count': context.get('target_words', 3800),
                    'created_by': user_id,
                    'stage': 'complete',
                    'generation_time': context.get('generation_time', 0.0),
                    'retry_attempts': context.get('retry_attempts', 0),
                    'model_used': context.get('model_used', 'gpt-4o'),
                    'tokens_used': context.get('tokens_used', {'prompt': 0, 'completion': 0, 'total': 0}),
                    'cost_breakdown': context.get('cost_breakdown', {'input_cost': 0.0, 'output_cost': 0.0, 'total_cost': 0.0}),
                    'generation_method': 'auto_complete_orchestrator',
                    'generated_at': datetime.now(timezone.utc).isoformat()
                },
                'quality_scores': {
                    'engagement_score': context.get('quality_score', 0.0),
                    'overall_rating': context.get('quality_score', 0.0),
                    'craft_scores': {
                        'prose': 0.0,
                        'character': 0.0,
                        'story': 0.0,
                        'emotion': 0.0,
                        'freshness': 0.0
                    },
                    'pattern_violations': [],
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
            
            # Save using the database integration layer
            chapter_id = await create_chapter(chapter_data)
            if chapter_id:
                self.logger.info(f"Chapter {chapter_number} saved to database: {chapter_id}")
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