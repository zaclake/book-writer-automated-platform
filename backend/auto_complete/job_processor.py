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

            # Persist job state to Firestore
            try:
                from ..firestore_client import firestore_client as fs_client
                job_data = await fs_client.load_job(job_id)
                if job_data:
                    job_data['status'] = 'completed'
                    job_data['updated_at'] = datetime.utcnow()
                    if 'progress' in job_info.__dict__ and job_info.progress is not None:
                        job_data['progress'] = job_info.progress
                    job_data['result'] = result
                    await fs_client.save_job(job_id, job_data)
            except Exception as persist_err:
                self.logger.warning(f"Failed to persist completed job {job_id} to storage: {persist_err}")
            
            # Handle credit finalization for completed job
            await self._finalize_job_credits(job_id, success=True, result=result)
            
            self.logger.info(f"Job {job_id} completed successfully")
            
        except asyncio.CancelledError:
            # Job was cancelled
            job_info.status = JobStatus.CANCELLED
            job_info.completed_at = datetime.utcnow()
            job_info.error_message = "Job was cancelled"
            
            self.logger.info(f"Job {job_id} was cancelled")

            # Persist job state to Firestore
            try:
                from ..firestore_client import firestore_client as fs_client
                job_data = await fs_client.load_job(job_id)
                if job_data:
                    job_data['status'] = 'cancelled'
                    job_data['error_message'] = 'Job was cancelled'
                    job_data['updated_at'] = datetime.utcnow()
                    await fs_client.save_job(job_id, job_data)
            except Exception as persist_err:
                self.logger.warning(f"Failed to persist cancelled job {job_id}: {persist_err}")
            
        except Exception as e:
            # Job failed
            job_info.status = JobStatus.FAILED
            job_info.completed_at = datetime.utcnow()
            job_info.error_message = str(e)
            
            # Handle credit voiding for failed job
            await self._finalize_job_credits(job_id, success=False, error=str(e))
            
            self.logger.error(f"Job {job_id} failed: {e}")

            # Persist job failure to Firestore
            try:
                from ..firestore_client import firestore_client as fs_client
                job_data = await fs_client.load_job(job_id)
                if job_data:
                    job_data['status'] = 'failed'
                    job_data['error_message'] = str(e)
                    job_data['updated_at'] = datetime.utcnow()
                    await fs_client.save_job(job_id, job_data)
            except Exception as persist_err:
                self.logger.warning(f"Failed to persist failed job {job_id}: {persist_err}")
            
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
    
    async def cancel_job(self, job_id: str) -> bool:
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
        
        # Handle credit voiding for cancelled job
        try:
            await self._finalize_job_credits(job_id, success=False, error="Job cancelled by user")
        except Exception as e:
            self.logger.error(f"Failed to void credits for cancelled job {job_id}: {e}")
        
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

        # Persist progress to Firestore to support status endpoints
        async def _persist_progress():
            try:
                from ..firestore_client import firestore_client as fs_client
                job_data = await fs_client.load_job(job_id)
                if job_data:
                    job_data['progress'] = progress
                    job_data['status'] = 'generating'
                    job_data['updated_at'] = datetime.utcnow()
                    await fs_client.save_job(job_id, job_data)
                    
                    # Trigger SSE event for progress update
                    self._notify_progress_listeners(job_id)
                    
            except Exception as persist_err:
                self.logger.warning(f"Failed to persist progress for job {job_id}: {persist_err}")

        try:
            # Fire and forget persistence
            asyncio.create_task(_persist_progress())
        except Exception:
            pass

        return True
    
    def _notify_progress_listeners(self, job_id: str):
        """Notify SSE listeners about job progress update."""
        try:
            # Import here to avoid circular imports
            from ..main import job_update_events
            if job_id in job_update_events:
                job_update_events[job_id].set()
                self.logger.debug(f"Notified SSE listeners for job {job_id}")
        except Exception as e:
            self.logger.warning(f"Failed to notify SSE listeners for job {job_id}: {e}")
    
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
                    # Try Railway path first (running from /app/backend/), then local dev path
                    from backend.auto_complete import AutoCompleteBookOrchestrator, AutoCompletionConfig
                    orchestrator_available = True
                except ImportError as e:
                    self.logger.warning(f"AutoCompleteBookOrchestrator not available: {e}, using simulation")
                    orchestrator_available = False
                
                self.logger.info(f"Starting auto-complete job {job_id}")
                self.logger.info(f"Config: {auto_complete_request}")
                
                # Extract values with proper defaults
                target_chapters = auto_complete_request.get('target_chapter_count', 5)
                target_words = auto_complete_request.get('target_word_count', 20000)
                quality_threshold_raw = auto_complete_request.get('minimum_quality_score', 7.0)
                # Normalize threshold to 0-10 scale if client sent 0-100
                quality_threshold = (quality_threshold_raw / 10.0) if quality_threshold_raw and quality_threshold_raw > 10 else quality_threshold_raw
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
                        user_review_required=False,
                        user_id=user.get('user_id'),
                        project_id=project_id
                    )
                    
                    # Initialize orchestrator with project path
                    # Use robust paths helper to ensure writable temp workspace
                    try:
                        from backend.utils.paths import get_project_workspace, ensure_project_structure
                    except ImportError:
                        from ..utils.paths import get_project_workspace, ensure_project_structure
                    project_workspace = get_project_workspace(project_id)
                    ensure_project_structure(project_workspace)

                    # Safeguard: ensure workspace belongs to this project; if not, reset it
                    try:
                        import json as _json
                        from pathlib import Path as _Path
                        from datetime import datetime as _dt
                        import shutil as _shutil

                        manifest_path = project_workspace / 'project-manifest.json'
                        if manifest_path.exists():
                            try:
                                existing = _json.loads(manifest_path.read_text(encoding='utf-8') or '{}')
                            except Exception:
                                existing = {}
                            existing_id = existing.get('project_id')
                            if existing_id and existing_id != project_id:
                                # Different project left data here -> reset workspace
                                for child in project_workspace.iterdir():
                                    if child.is_dir():
                                        _shutil.rmtree(child, ignore_errors=True)
                                    else:
                                        try:
                                            child.unlink(missing_ok=True)
                                        except Exception:
                                            pass
                                ensure_project_structure(project_workspace)
                        
                        # Always write/update manifest for clarity
                        manifest = {
                            'project_id': project_id,
                            'updated_at': _dt.utcnow().isoformat()
                        }
                        manifest_path.write_text(_json.dumps(manifest, indent=2), encoding='utf-8')

                        # Proactively clear and recreate references dir to avoid stale refs bleed-over
                        refs_dir = project_workspace / 'references'
                        if refs_dir.exists():
                            for f in refs_dir.iterdir():
                                try:
                                    if f.is_dir():
                                        _shutil.rmtree(f, ignore_errors=True)
                                    else:
                                        f.unlink(missing_ok=True)
                                except Exception:
                                    pass
                        refs_dir.mkdir(exist_ok=True)
                    except Exception as ws_guard_err:
                        self.logger.warning(f"Workspace guard failed for project {project_id}: {ws_guard_err}")

                    # Hydrate workspace with book bible and reference files from database, if available
                    try:
                        from backend.database_integration import get_project, get_project_reference_files
                    except ImportError:
                        from ..database_integration import get_project, get_project_reference_files

                    try:
                        project_data = await get_project(project_id)
                        # Book bible
                        bb_content = None
                        if project_data:
                            if 'files' in project_data and 'book-bible.md' in project_data['files']:
                                bb_content = project_data['files']['book-bible.md']
                            elif 'book_bible' in project_data:
                                bb_entry = project_data['book_bible']
                                if isinstance(bb_entry, dict):
                                    bb_content = bb_entry.get('content')
                                elif isinstance(bb_entry, str):
                                    bb_content = bb_entry
                        if bb_content:
                            (project_workspace / 'book-bible.md').write_text(bb_content, encoding='utf-8')

                        # References collection
                        try:
                            reference_docs = await get_project_reference_files(project_id)
                            refs_dir = project_workspace / 'references'
                            refs_dir.mkdir(exist_ok=True)
                            for ref in reference_docs or []:
                                filename = ref.get('filename') or 'unnamed.md'
                                content = ref.get('content') or ''
                                (refs_dir / filename).write_text(content, encoding='utf-8')
                        except Exception:
                            # Best-effort; continue even if not present
                            pass
                    except Exception as e:
                        self.logger.warning(f"Workspace hydration failed for project {project_id}: {e}")

                    project_path = str(project_workspace)
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
                    # Provide job configuration as request data to orchestrator
                    orchestrator_job_id = orchestrator.start_auto_completion(auto_complete_request)
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
    
    async def _finalize_job_credits(self, job_id: str, success: bool, result: Optional[Dict] = None, error: Optional[str] = None):
        """
        Finalize or void credits for a completed/failed auto-complete job.
        
        Args:
            job_id: Job identifier
            success: Whether the job completed successfully
            result: Job result data (for successful jobs)
            error: Error message (for failed jobs)
        """
        try:
            # Load job data to get provisional transaction info
            # Import the global compatibility instance, not the module
            from ..firestore_client import firestore_client as fs_client
            job_data = await fs_client.load_job(job_id)
            
            if not job_data:
                self.logger.warning(f"No job data found for credit finalization: {job_id}")
                return
                
            provisional_txn_id = job_data.get('provisional_txn_id')
            estimated_credits = job_data.get('estimated_credits', 0)
            user_id = job_data.get('user_id')
            
            if not provisional_txn_id or not user_id:
                self.logger.info(f"No provisional transaction to finalize for job {job_id}")
                return
                
            # Get credits service
            try:
                from ..services.credits_service import get_credits_service_instance
                credits_service = get_credits_service_instance()
                import os
                # If per-request billing is enabled, the billable client already finalized actual charges.
                # In that case, treat the job-level provisional debit as a hold and always VOID it.
                per_request_billing_enabled = os.getenv('ENABLE_CREDITS_BILLING', 'false').lower() == 'true'
                
                if not credits_service or not credits_service.is_available():
                    self.logger.warning(f"Credits service not available for job {job_id} finalization")
                    return
                    
                # If per-request billing is enabled, always void the job-level hold regardless of outcome
                if per_request_billing_enabled:
                    await credits_service.void_provisional_debit(
                        user_id=user_id,
                        txn_id=provisional_txn_id,
                        reason=f"auto_complete_job_release_hold: {'success' if success else 'failure'}",
                        meta={
                            "job_id": job_id,
                            "estimated_credits": estimated_credits,
                            "success": success,
                            "error": error
                        }
                    )
                    self.logger.info(f"Released provisional hold for job {job_id} (per-request billing active)")
                else:
                    # No per-request billing; finalize on success, void on failure
                    if success:
                        # Calculate actual credits used from job result if available
                        actual_credits_used = 0
                        if result and 'total_credits_used' in result:
                            actual_credits_used = result['total_credits_used']
                        else:
                            actual_credits_used = estimated_credits
                            self.logger.warning(f"Using estimated credits for finalization of job {job_id}: {actual_credits_used}")
                        await credits_service.finalize_provisional_debit(
                            user_id=user_id,
                            txn_id=provisional_txn_id,
                            final_amount=actual_credits_used,
                            meta={
                                "job_id": job_id,
                                "finalization_reason": "auto_complete_job_completed",
                                "estimated_credits": estimated_credits,
                                "actual_credits": actual_credits_used
                            }
                        )
                        self.logger.info(f"Finalized {actual_credits_used} credits for completed job {job_id} (estimated: {estimated_credits})")
                    else:
                        await credits_service.void_provisional_debit(
                            user_id=user_id,
                            txn_id=provisional_txn_id,
                            reason=f"auto_complete_job_failed: {error or 'unknown error'}",
                            meta={
                                "job_id": job_id,
                                "estimated_credits": estimated_credits,
                                "error": error
                            }
                        )
                        self.logger.info(f"Voided {estimated_credits} credits for failed job {job_id}: {error}")
                    
            except ImportError:
                self.logger.warning(f"Credits service not available for job {job_id} finalization")
            except Exception as e:
                self.logger.error(f"Credit finalization failed for job {job_id}: {e}")
                # Don't raise - credit errors shouldn't fail job completion
                
        except Exception as e:
            self.logger.error(f"Failed to finalize credits for job {job_id}: {e}")
            # Don't raise - credit errors shouldn't fail job completion 