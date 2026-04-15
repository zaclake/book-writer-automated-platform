#!/usr/bin/env python3
"""
Background Job Processor - FastAPI Backend Version
Handles async execution of auto-completion jobs.
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# Optional log correlation context (job_id / run_id)
try:
    from ..utils.logging_config import job_id_contextvar, run_id_contextvar
except Exception:  # pragma: no cover
    try:
        from backend.utils.logging_config import job_id_contextvar, run_id_contextvar  # type: ignore
    except Exception:
        job_id_contextvar = None  # type: ignore
        run_id_contextvar = None  # type: ignore

# Run summary helpers
try:
    from ..utils.run_summaries import emit_summary
except Exception:  # pragma: no cover
    try:
        from backend.utils.run_summaries import emit_summary  # type: ignore
    except Exception:
        emit_summary = None  # type: ignore

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
        self.job_controls: Dict[str, Dict[str, Any]] = {}
        self.logger = logger
        # Stable worker identifier for job leasing/claiming across processes.
        self.worker_id = (
            (os.getenv("RAILWAY_REPLICA_ID") or os.getenv("HOSTNAME") or "").strip()
            or f"worker-{uuid.uuid4()}"
        )
        
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
        try:
            if job_id_contextvar is not None:
                job_id_contextvar.set(job_id)
        except Exception:
            pass
        try:
            if run_id_contextvar is not None:
                # Default run correlation for whole job is the job id.
                run_id_contextvar.set(job_id[:12])
        except Exception:
            pass
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
            try:
                if job_id_contextvar is not None:
                    job_id_contextvar.set(job_id)
            except Exception:
                pass
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
            
            # Notify SSE listeners for completion
            try:
                from ..main import job_update_events
                if job_id in job_update_events:
                    job_update_events[job_id].set()
            except Exception as notify_err:
                self.logger.warning(f"Failed to notify completion for job {job_id}: {notify_err}")
            
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
            # Notify SSE listeners for cancellation
            try:
                from ..main import job_update_events
                if job_id in job_update_events:
                    job_update_events[job_id].set()
            except Exception as notify_err:
                self.logger.warning(f"Failed to notify cancellation for job {job_id}: {notify_err}")
            
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
            # Notify SSE listeners for failure
            try:
                from ..main import job_update_events
                if job_id in job_update_events:
                    job_update_events[job_id].set()
            except Exception as notify_err:
                self.logger.warning(f"Failed to notify failure for job {job_id}: {notify_err}")
            
        finally:
            # Always release the per-project generation lock (best-effort).
            try:
                controller = self.job_controls.get(job_id, {})
                project_id = controller.get("project_id")
                if project_id:
                    try:
                        from backend.database_integration import get_database_adapter
                        db = get_database_adapter()
                        if getattr(db, "use_firestore", False) and getattr(db, "firestore", None):
                            release = getattr(db.firestore, "release_generation_lock", None)
                            if callable(release):
                                await release(project_id, job_id=job_id, worker_id=self.worker_id)
                    except Exception:
                        pass
            except Exception:
                pass
            # Remove from running jobs
            if job_id in self.running_jobs:
                del self.running_jobs[job_id]
            if job_id in self.job_controls:
                del self.job_controls[job_id]
    
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
        controller = self.job_controls.get(job_id, {})
        orchestrator = controller.get("orchestrator")
        if orchestrator and hasattr(orchestrator, "pause_auto_completion"):
            try:
                orchestrator.pause_auto_completion()
            except Exception as e:
                self.logger.warning(f"Failed to pause orchestrator for job {job_id}: {e}")
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
        controller = self.job_controls.get(job_id, {})
        orchestrator = controller.get("orchestrator")
        if orchestrator and hasattr(orchestrator, "resume_auto_completion"):
            try:
                orchestrator.resume_auto_completion()
            except Exception as e:
                self.logger.warning(f"Failed to resume orchestrator for job {job_id}: {e}")
        self.logger.info(f"Job {job_id} resumed")
        return True

    async def recover_job(self, job_id: str) -> bool:
        """
        Recover an auto-complete job after process restart.

        If the job is not currently running in-memory but exists in Firestore/local job storage,
        re-submit it using the persisted config and resume from the last known chapter.
        """
        if not job_id:
            return False
        if job_id in self.running_jobs:
            return True
        try:
            from ..firestore_client import firestore_client as fs_client
        except Exception:
            try:
                from backend.firestore_client import firestore_client as fs_client  # type: ignore
            except Exception:
                return False

        job_data = await fs_client.load_job(job_id)
        if not job_data:
            return False

        project_id = job_data.get("project_id")
        user_id = job_data.get("user_id")
        config = job_data.get("config") or {}
        progress = job_data.get("progress") or {}

        if not project_id or not user_id:
            return False

        # Resume deterministically:
        # 1) Prefer persisted chapter queue state from progress (if present)
        # 2) Otherwise use max chapter_number already persisted for the project
        starting_chapter = 1
        try:
            chapter_jobs = progress.get("chapter_jobs")
        except Exception:
            chapter_jobs = None

        if isinstance(chapter_jobs, list) and chapter_jobs:
            completed_nums = set()
            resumable_nums = []
            for item in chapter_jobs:
                if not isinstance(item, dict):
                    continue
                try:
                    ch_num = int(item.get("chapter_number") or 0)
                except Exception:
                    ch_num = 0
                if ch_num <= 0:
                    continue
                status = str(item.get("status") or "").strip().lower()
                if status == "completed":
                    completed_nums.add(ch_num)
                elif status in {"pending", "failed", "generating", "running", "paused"}:
                    resumable_nums.append(ch_num)
            resumable_nums.sort()
            if resumable_nums:
                starting_chapter = max(1, resumable_nums[0])
            elif completed_nums:
                starting_chapter = max(1, max(completed_nums) + 1)
            else:
                starting_chapter = 1
        else:
            try:
                from backend.database_integration import get_project_chapters
                chapters = await get_project_chapters(project_id)
                max_existing = 0
                for ch in chapters or []:
                    try:
                        num = int((ch or {}).get("chapter_number") or 0)
                    except Exception:
                        num = 0
                    if num > max_existing:
                        max_existing = num
                starting_chapter = max(1, max_existing + 1)
            except Exception:
                # Fallback: resume from progress current_chapter
                try:
                    last_chapter = int(progress.get("current_chapter") or 0)
                except Exception:
                    last_chapter = 0
                starting_chapter = max(1, last_chapter + 1)

        # Rebuild orchestrator config (same shape as convert_request_to_config output).
        target_chapters = config.get("target_chapters") or config.get("target_chapter_count") or progress.get("total_chapters") or 20
        words_per_chapter = config.get("words_per_chapter") or 3800
        quality_threshold = config.get("quality_threshold") or config.get("minimum_quality_score") or 7.0
        try:
            target_chapters = int(target_chapters)
        except Exception:
            target_chapters = 20
        try:
            words_per_chapter = int(words_per_chapter)
        except Exception:
            words_per_chapter = 3800
        try:
            quality_threshold = float(quality_threshold)
        except Exception:
            quality_threshold = 7.0

        # If we've already met/exceeded the target chapter count, there's nothing to recover.
        try:
            if starting_chapter > int(target_chapters):
                self.logger.info(f"Job {job_id} recovery skipped: starting_chapter={starting_chapter} > target_chapters={target_chapters}")
                return False
        except Exception:
            pass

        orchestrator_config = {
            "project_id": project_id,
            "target_word_count": int(target_chapters) * int(words_per_chapter),
            "target_chapter_count": int(target_chapters),
            "words_per_chapter": int(words_per_chapter),
            "minimum_quality_score": float(quality_threshold),
            "starting_chapter": starting_chapter,
        }

        # Mark job status as generating before resubmission.
        try:
            job_data["status"] = "generating"
            job_data["updated_at"] = datetime.utcnow()
            await fs_client.save_job(job_id, job_data)
        except Exception:
            pass

        await self.submit_auto_complete_job(job_id, orchestrator_config, {"user_id": user_id})
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
        
        # Signal orchestrator to cancel if available
        controller = self.job_controls.get(job_id, {})
        orchestrator = controller.get("orchestrator")
        if orchestrator and hasattr(orchestrator, "cancel_auto_completion"):
            try:
                orchestrator.cancel_auto_completion()
            except Exception as e:
                self.logger.warning(f"Failed to cancel orchestrator for job {job_id}: {e}")

        # Cancel the task if it's running
        if job_id in self.running_jobs:
            task = self.running_jobs[job_id]
            task.cancel()
        
        job_info.status = JobStatus.CANCELLED
        job_info.completed_at = datetime.utcnow()
        job_info.error_message = "Job was cancelled by user"

        # Release the generation lock so the project can start new jobs
        try:
            controller = self.job_controls.get(job_id, {})
            project_id = controller.get("project_id") if isinstance(controller, dict) else None
            if project_id:
                from backend.database_integration import get_database_adapter
                db = get_database_adapter()
                if getattr(db, "use_firestore", False) and getattr(db, "firestore", None):
                    release = getattr(db.firestore, "release_generation_lock", None)
                    if callable(release):
                        await release(project_id, job_id=job_id, worker_id=self.worker_id)
                        self.logger.info(f"Released generation lock for project {project_id}")
        except Exception as e:
            self.logger.warning(f"Failed to release generation lock for cancelled job {job_id}: {e}")

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
                    # Enforce monotonic progress (best-effort).
                    try:
                        existing = job_data.get("progress", {}) or {}
                        old_ch = int(existing.get("current_chapter") or 0)
                        new_ch = int(progress.get("current_chapter") or 0)
                        if new_ch < old_ch:
                            return
                        old_pct = float(existing.get("progress_percentage") or 0.0)
                        new_pct = float(progress.get("progress_percentage") or 0.0)
                        if new_pct + 1e-9 < old_pct:
                            return
                    except Exception:
                        pass
                    job_data['progress'] = progress
                    # Never overwrite a terminal status with an in-flight status.
                    # Because persistence here is fire-and-forget, it can race with the
                    # completion persist path in execute_job(), which sets status=completed.
                    try:
                        existing_status = str(job_data.get('status') or '').strip().lower()
                    except Exception:
                        existing_status = ""
                    if existing_status not in ("completed", "failed", "cancelled"):
                        job_data['status'] = progress.get('status') or existing_status or 'generating'
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
                job_started_at = datetime.utcnow()
                # Import orchestrator (no simulation fallback)
                try:
                    # Try Railway path first (running from /app/backend/), then local dev path
                    from backend.auto_complete import AutoCompleteBookOrchestrator, AutoCompletionConfig
                    orchestrator_available = True
                except ImportError as e:
                    self.logger.error(f"AutoCompleteBookOrchestrator not available: {e}")
                    orchestrator_available = False
                
                self.logger.info(f"Starting auto-complete job {job_id}")
                self.logger.info(f"Config: {auto_complete_request}")
                
                # Extract values with proper defaults (orchestrator_config from main.py)
                target_chapters = auto_complete_request.get('target_chapter_count', 5)
                total_words = auto_complete_request.get('target_word_count', 20000)
                words_per_chapter = auto_complete_request.get('words_per_chapter', max(1, total_words // max(1, target_chapters)))
                quality_threshold_raw = auto_complete_request.get('minimum_quality_score', 7.0)
                # Normalize threshold to 0-10 scale if client sent 0-100
                quality_threshold = (quality_threshold_raw / 10.0) if quality_threshold_raw and quality_threshold_raw > 10 else quality_threshold_raw
                project_id = auto_complete_request.get('project_id', 'unknown')

                # Transactionally claim the job lease in Firestore (if available).
                # This protects against multiple replicas processing the same job.
                try:
                    claim_attempted = False
                    from backend.database_integration import get_database_adapter
                    db = get_database_adapter()
                    if getattr(db, "use_firestore", False) and getattr(db, "firestore", None):
                        claimer = getattr(db.firestore, "claim_generation_job", None)
                        if callable(claimer):
                            claim_attempted = True
                            claimed = await claimer(job_id, worker_id=self.worker_id, lease_seconds=1800)
                            if not claimed:
                                raise RuntimeError("Job already claimed by another worker.")
                except Exception as claim_err:
                    # If we attempted a real claim and it failed, fail fast to prevent duplicate work.
                    if locals().get("claim_attempted"):
                        raise
                    self.logger.warning(f"Job {job_id} claim skipped: {claim_err}")

                # Ensure the per-project lock is held by this job/worker (idempotent).
                try:
                    from backend.database_integration import get_database_adapter
                    db = get_database_adapter()
                    if getattr(db, "use_firestore", False) and getattr(db, "firestore", None):
                        acquire_lock = getattr(db.firestore, "acquire_generation_lock", None)
                        if callable(acquire_lock):
                            lock_result = await acquire_lock(
                                project_id,
                                job_id=job_id,
                                worker_id=self.worker_id,
                                lease_seconds=1800,
                                status="running",
                            )
                            if not (lock_result or {}).get("acquired"):
                                raise RuntimeError("Project generation lock held by another job.")
                except Exception:
                    raise
                
                if not orchestrator_available:
                    raise RuntimeError("AutoCompleteBookOrchestrator unavailable; cannot proceed without real generation.")

                # Use real orchestrator
                self.logger.info(f"Job {job_id}: Using real AutoCompleteBookOrchestrator")
                    
                # Create orchestrator config
                config = AutoCompletionConfig(
                    target_word_count=total_words,
                    target_chapter_count=target_chapters,
                    words_per_chapter=words_per_chapter,
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
                self.job_controls[job_id] = {"orchestrator": orchestrator}
                self.job_controls[job_id]["project_id"] = project_id

                # Create progress callback
                def progress_callback(chapter_num: int, total_chapters: int, status: str):
                    progress = {
                        'current_chapter': chapter_num,
                        'total_chapters': total_chapters,
                        'progress_percentage': (chapter_num / total_chapters) * 100 if total_chapters else 0,
                        'status': status,
                        'project_id': project_id,
                    }
                    # Persist chapter queue state for resume/recovery (bounded size).
                    try:
                        progress["chapter_jobs"] = orchestrator.get_chapter_jobs()
                    except Exception:
                        pass
                    self.update_job_progress(job_id, progress)
                    self.logger.info(f"Job {job_id}: {status} - Chapter {chapter_num}/{total_chapters}")

                    # Best-effort heartbeat to extend lease while running.
                    async def _heartbeat():
                        try:
                            from backend.database_integration import get_database_adapter
                            db = get_database_adapter()
                            if getattr(db, "use_firestore", False) and getattr(db, "firestore", None):
                                hb = getattr(db.firestore, "heartbeat_generation_job", None)
                                if callable(hb):
                                    await hb(job_id, worker_id=self.worker_id, lease_seconds=1800)
                                lock_hb = getattr(db.firestore, "heartbeat_generation_lock", None)
                                if callable(lock_hb):
                                    await lock_hb(
                                        project_id,
                                        job_id=job_id,
                                        worker_id=self.worker_id,
                                        lease_seconds=1800,
                                        status="running",
                                    )
                        except Exception:
                            return
                    try:
                        asyncio.create_task(_heartbeat())
                    except Exception:
                        pass

                # Map config to orchestrator request schema
                orchestrator_request = {
                    "project_id": project_id,
                    "book_bible": auto_complete_request.get("book_bible"),
                    "target_chapters": target_chapters,
                    "words_per_chapter": words_per_chapter,
                    "quality_threshold": quality_threshold,
                    "starting_chapter": auto_complete_request.get("starting_chapter", 1)
                }
                orchestrator_job_id = orchestrator.start_auto_completion(orchestrator_request)
                self.logger.info(f"Job {job_id}: Started orchestrator with job ID {orchestrator_job_id}")

                # Run auto-completion with progress monitoring
                self.logger.info(f"Job {job_id}: Starting orchestrator execution")
                progress_callback(0, target_chapters, "Starting auto-completion")

                async def progress_callback_wrapper(progress_status: Dict[str, Any]):
                    progress = progress_status.get("progress", {})
                    current = progress.get("current_chapter", 0)
                    total = progress.get("total_chapters", target_chapters)
                    status = progress_status.get("status", "generating")
                    progress_callback(current, total, status)

                result = await orchestrator.run_auto_completion(progress_callback=progress_callback_wrapper)
                job_completed_at = datetime.utcnow()

                # Final progress update from orchestrator completion data
                progress = result.get("progress", {})
                chapters_completed = progress.get("chapters_completed", 0)
                progress_callback(chapters_completed, progress.get("total_chapters", target_chapters), f"Completed {chapters_completed} chapters")

                quality_scores = result.get("quality_scores", [])
                avg_quality = 0.0
                if quality_scores:
                    avg_quality = sum(item.get("score", 0) for item in quality_scores) / max(1, len(quality_scores))

                # Single structured book run summary line.
                book_run_summary = {
                    "event": "BOOK_RUN_SUMMARY",
                    "job_id": job_id,
                    "run_id": job_id,
                    "project_id": project_id,
                    "user_id": user.get("user_id"),
                    "status": result.get("status", "unknown"),
                    "completion_reason": result.get("completion_reason"),
                    "started_at": job_started_at.isoformat(),
                    "ended_at": job_completed_at.isoformat(),
                    "chapters": {
                        "planned": int(target_chapters),
                        "completed": int(chapters_completed),
                        "failed": int(len([j for j in (orchestrator.get_chapter_jobs() or []) if j.get("status") == "failed"])),
                    },
                    "aggregate": {
                        "total_words": int(progress.get("total_words", 0) or 0),
                        "average_quality_score": float(avg_quality),
                    },
                }
                try:
                    if emit_summary is not None:
                        emit_summary(self.logger, book_run_summary)
                except Exception:
                    pass

                # Update project progress in Firestore so dashboard shows accurate counts
                try:
                    from backend.database_integration import get_database_adapter as _get_db
                    _db = _get_db()
                    if getattr(_db, "use_firestore", False) and getattr(_db, "firestore", None):
                        _fs_db = getattr(_db.firestore, "db", None)
                        _uid = user.get("user_id")
                        if _fs_db and _uid:
                            proj_ref = _fs_db.collection("users").document(_uid)\
                                .collection("projects").document(project_id)
                            proj_ref.update({
                                "progress.chapters_completed": int(chapters_completed),
                                "progress.current_word_count": int(progress.get("total_words", 0) or 0),
                                "progress.completion_percentage": round(
                                    min(100.0, (chapters_completed / max(1, target_chapters)) * 100), 1
                                ),
                                "progress.last_chapter_generated": int(chapters_completed),
                            })
                            self.logger.info(f"Job {job_id}: Updated project progress ({chapters_completed}/{target_chapters} chapters)")
                except Exception as prog_err:
                    self.logger.warning(f"Job {job_id}: Failed to update project progress: {prog_err}")

                return {
                    'success': result.get("status") == "completed",
                    'orchestrator_job_id': orchestrator_job_id,
                    'chapters_generated': chapters_completed,
                    'total_word_count': progress.get("total_words", 0),
                    'average_quality_score': avg_quality,
                    'completion_status': result.get("status", "completed"),
                    'project_id': project_id,
                    'run_summary': book_run_summary,
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