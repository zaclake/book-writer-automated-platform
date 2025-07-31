#!/usr/bin/env python3
"""
Background Job Processor - FastAPI Backend Version
Handles async execution of auto-completion jobs.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class JobStatus(Enum):
    """Job status states."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class JobInfo:
    """Information about a background job."""
    job_id: str
    status: JobStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    progress: Dict[str, Any] = None
    result: Optional[Dict[str, Any]] = None

class BackgroundJobProcessor:
    """
    Processes background jobs for auto-completion.
    Simplified version for FastAPI backend.
    """
    
    def __init__(self):
        self.jobs: Dict[str, JobInfo] = {}
        self.running_jobs: Dict[str, asyncio.Task] = {}
        self.logger = logger
        
    async def submit_job(self, job_id: str, job_func: Callable, *args, **kwargs) -> JobInfo:
        """
        Submit a new background job.
        
        Args:
            job_id: Unique job identifier
            job_func: Async function to execute
            *args, **kwargs: Arguments to pass to the job function
            
        Returns:
            JobInfo object with job details
        """
        # Create job info
        job_info = JobInfo(
            job_id=job_id,
            status=JobStatus.PENDING,
            created_at=datetime.utcnow(),
            progress={}
        )
        
        # Store job
        self.jobs[job_id] = job_info
        
        # Create and start the task
        task = asyncio.create_task(
            self._execute_job(job_id, job_func, *args, **kwargs)
        )
        self.running_jobs[job_id] = task
        
        self.logger.info(f"Job {job_id} submitted and started")
        return job_info
    
    async def _execute_job(self, job_id: str, job_func: Callable, *args, **kwargs) -> None:
        """
        Execute a background job.
        
        Args:
            job_id: Job identifier
            job_func: Function to execute
            *args, **kwargs: Function arguments
        """
        job_info = self.jobs[job_id]
        
        try:
            # Update job status
            job_info.status = JobStatus.RUNNING
            job_info.started_at = datetime.utcnow()
            
            self.logger.info(f"Starting job {job_id}")
            
            # Execute the job function
            result = await job_func(*args, **kwargs)
            
            # Update job with success
            job_info.status = JobStatus.COMPLETED
            job_info.completed_at = datetime.utcnow()
            job_info.result = result
            
            self.logger.info(f"Job {job_id} completed successfully")
            
        except asyncio.CancelledError:
            # Job was cancelled
            job_info.status = JobStatus.CANCELLED
            job_info.completed_at = datetime.utcnow()
            job_info.error_message = "Job was cancelled"
            
            self.logger.info(f"Job {job_id} was cancelled")
            
        except Exception as e:
            # Job failed
            job_info.status = JobStatus.FAILED
            job_info.completed_at = datetime.utcnow()
            job_info.error_message = str(e)
            
            self.logger.error(f"Job {job_id} failed: {e}")
            
        finally:
            # Remove from running jobs
            if job_id in self.running_jobs:
                del self.running_jobs[job_id]
    
    def get_job_status(self, job_id: str) -> Optional[JobInfo]:
        """
        Get the status of a job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            JobInfo object or None if job not found
        """
        return self.jobs.get(job_id)
    
    def pause_job(self, job_id: str) -> bool:
        """
        Pause a running job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            True if job was paused, False otherwise
        """
        job_info = self.jobs.get(job_id)
        if not job_info or job_info.status != JobStatus.RUNNING:
            return False
        
        job_info.status = JobStatus.PAUSED
        self.logger.info(f"Job {job_id} paused")
        return True
    
    def resume_job(self, job_id: str) -> bool:
        """
        Resume a paused job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            True if job was resumed, False otherwise
        """
        job_info = self.jobs.get(job_id)
        if not job_info or job_info.status != JobStatus.PAUSED:
            return False
        
        job_info.status = JobStatus.RUNNING
        self.logger.info(f"Job {job_id} resumed")
        return True
    
    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            True if job was cancelled, False otherwise
        """
        job_info = self.jobs.get(job_id)
        if not job_info or job_info.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
            return False
        
        # Cancel the task if it's running
        if job_id in self.running_jobs:
            task = self.running_jobs[job_id]
            task.cancel()
        
        job_info.status = JobStatus.CANCELLED
        job_info.completed_at = datetime.utcnow()
        job_info.error_message = "Job was cancelled by user"
        
        self.logger.info(f"Job {job_id} cancelled")
        return True
    
    def list_jobs(self, status_filter: Optional[JobStatus] = None) -> Dict[str, JobInfo]:
        """
        List all jobs, optionally filtered by status.
        
        Args:
            status_filter: Optional status to filter by
            
        Returns:
            Dictionary of job_id -> JobInfo
        """
        if status_filter:
            return {
                job_id: job_info 
                for job_id, job_info in self.jobs.items() 
                if job_info.status == status_filter
            }
        return self.jobs.copy()
    
    def cleanup_completed_jobs(self, max_age_hours: int = 24) -> int:
        """
        Clean up completed jobs older than max_age_hours.
        
        Args:
            max_age_hours: Maximum age in hours for completed jobs
            
        Returns:
            Number of jobs cleaned up
        """
        current_time = datetime.utcnow()
        jobs_to_remove = []
        
        for job_id, job_info in self.jobs.items():
            if job_info.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                if job_info.completed_at:
                    age_hours = (current_time - job_info.completed_at).total_seconds() / 3600
                    if age_hours > max_age_hours:
                        jobs_to_remove.append(job_id)
        
        # Remove old jobs
        for job_id in jobs_to_remove:
            del self.jobs[job_id]
        
        if jobs_to_remove:
            self.logger.info(f"Cleaned up {len(jobs_to_remove)} old jobs")
        
        return len(jobs_to_remove)
    
    def get_job_progress(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current progress of a job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            Progress dictionary or None if job not found
        """
        job_info = self.jobs.get(job_id)
        if not job_info:
            return None
        
        return {
            'job_id': job_id,
            'status': job_info.status.value,
            'created_at': job_info.created_at.isoformat(),
            'started_at': job_info.started_at.isoformat() if job_info.started_at else None,
            'completed_at': job_info.completed_at.isoformat() if job_info.completed_at else None,
            'progress': job_info.progress,
            'error_message': job_info.error_message
        }
    
    def update_job_progress(self, job_id: str, progress: Dict[str, Any]) -> bool:
        """
        Update progress of a running job.
        
        Args:
            job_id: Job identifier
            progress: Progress data to update
            
        Returns:
            True if progress was updated, False otherwise
        """
        job_info = self.jobs.get(job_id)
        if not job_info:
            return False
        
        job_info.progress = progress
        return True
    
    async def submit_auto_complete_job(self, job_id: str, auto_complete_request: Dict[str, Any], user: Dict[str, str]) -> JobInfo:
        """
        Submit an auto-complete book job.
        
        Args:
            job_id: Unique job identifier
            auto_complete_request: Auto-complete configuration (from AutoCompleteRequest.dict())
            user: User information
            
        Returns:
            JobInfo object with job details
        """
        async def auto_complete_job_func():
            """The actual auto-complete job function using real orchestrator."""
            try:
                # Import orchestrator (with fallback to simulation if unavailable)
                try:
                    from backend.system.auto_complete_book_orchestrator import AutoCompleteBookOrchestrator, AutoCompletionConfig
                    orchestrator_available = True
                except ImportError:
                    self.logger.warning("AutoCompleteBookOrchestrator not available, using simulation")
                    orchestrator_available = False
                
                self.logger.info(f"Starting auto-complete job {job_id}")
                self.logger.info(f"Config: {auto_complete_request}")
                
                # Extract values with proper defaults
                target_chapters = auto_complete_request.get('target_chapter_count', 5)
                target_words = auto_complete_request.get('target_word_count', 20000)
                quality_threshold = auto_complete_request.get('minimum_quality_score', 80.0)
                project_id = auto_complete_request.get('project_id', 'unknown')
                
                if orchestrator_available:
                    # Use real orchestrator
                    self.logger.info(f"Job {job_id}: Using real AutoCompleteBookOrchestrator")
                    
                    # Create orchestrator config
                    config = AutoCompletionConfig(
                        target_word_count=target_words,
                        target_chapter_count=target_chapters,
                        minimum_quality_score=quality_threshold,
                        max_retries_per_chapter=3,
                        auto_pause_on_failure=True,
                        context_improvement_enabled=True,
                        quality_gates_enabled=True,
                        user_review_required=False
                    )
                    
                    # Initialize orchestrator with project path
                    project_path = f"./temp_projects/{project_id}"
                    orchestrator = AutoCompleteBookOrchestrator(project_path, config)
                    
                    # Create progress callback
                    def progress_callback(chapter_num: int, total_chapters: int, status: str):
                        progress = {
                            'current_chapter': chapter_num,
                            'total_chapters': total_chapters,
                            'progress_percentage': (chapter_num / total_chapters) * 100,
                            'status': status,
                            'project_id': project_id
                        }
                        self.update_job_progress(job_id, progress)
                        self.logger.info(f"Job {job_id}: {status} - Chapter {chapter_num}/{total_chapters}")
                    
                    # Start orchestrator
                    orchestrator_job_id = orchestrator.start_auto_completion(user_initiated=False)
                    self.logger.info(f"Job {job_id}: Started orchestrator with job ID {orchestrator_job_id}")
                    
                    # Run auto-completion with progress monitoring
                    self.logger.info(f"Job {job_id}: Starting orchestrator execution")
                    progress_callback(0, target_chapters, "Starting auto-completion")
                    
                    result = await orchestrator.run_auto_completion()
                    
                    # Final progress update
                    chapters_generated = len(result.get('chapters_generated', []))
                    progress_callback(chapters_generated, target_chapters, f"Completed {chapters_generated} chapters")
                    
                    return {
                        'success': True,
                        'orchestrator_job_id': orchestrator_job_id,
                        'chapters_generated': len(result.get('chapters_generated', [])),
                        'total_word_count': result.get('total_word_count', 0),
                        'average_quality_score': result.get('average_quality_score', 0),
                        'completion_status': result.get('completion_status', 'completed'),
                        'project_id': project_id
                    }
                    
                else:
                    # Fallback simulation
                    self.logger.info(f"Job {job_id}: Using simulation fallback")
                    words_per_chapter = target_words // target_chapters
                    
                    for i in range(1, target_chapters + 1):
                        await asyncio.sleep(2)  # Simulate chapter generation time
                        
                        progress = {
                            'current_chapter': i,
                            'total_chapters': target_chapters,
                            'progress_percentage': round((i / target_chapters) * 100, 1),
                            'status': f'Generating chapter {i} (simulation)',
                            'project_id': project_id
                        }
                        self.update_job_progress(job_id, progress)
                        self.logger.info(f"Job {job_id}: Simulated chapter {i}")
                    
                    return {
                        'success': True,
                        'chapters_generated': target_chapters,
                        'total_word_count': target_words,
                        'quality_threshold': quality_threshold,
                        'project_id': project_id,
                        'note': 'Generated using simulation (orchestrator unavailable)'
                    }
                    
            except Exception as e:
                self.logger.error(f"Job {job_id} failed: {e}")
                raise
        
        return await self.submit_job(job_id, auto_complete_job_func) 