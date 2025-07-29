#!/usr/bin/env python3
"""
Background Job Processor
Handles long-running auto-completion jobs with state persistence, recovery, and progress tracking.
"""

import asyncio
import json
import logging
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, asdict
from enum import Enum
from concurrent.futures import ThreadPoolExecutor
import signal
import os

from auto_complete_book_orchestrator import AutoCompleteBookOrchestrator, AutoCompletionConfig
from backend.services.publishing_service import PublishingService
from backend.models.firestore_models import PublishConfig, PublishFormat


class JobStatus(Enum):
    """Job status enumeration."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    QUEUED = "queued"


class JobPriority(Enum):
    """Job priority levels."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


@dataclass
class JobProgress:
    """Progress information for a job."""
    job_id: str
    current_step: str
    total_steps: int
    completed_steps: int
    progress_percentage: float
    estimated_time_remaining: Optional[str]
    current_chapter: Optional[int]
    chapters_completed: int
    total_chapters: int
    last_update: str
    detailed_status: Dict[str, Any]


@dataclass
class BackgroundJob:
    """Represents a background job."""
    job_id: str
    job_type: str
    status: JobStatus
    priority: JobPriority
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    config: Dict[str, Any]
    progress: JobProgress
    error: Optional[str]
    result: Optional[Dict[str, Any]]
    retries: int
    max_retries: int
    user_id: Optional[str]
    project_path: str


class BackgroundJobProcessor:
    """
    Background job processor for long-running auto-completion tasks.
    
    Features:
    - Async job execution with state persistence
    - Progress tracking and real-time updates
    - Job queue management with priorities
    - Failure recovery and retry logic
    - System restart recovery
    - Graceful shutdown handling
    """
    
    def __init__(self, max_concurrent_jobs: int = 2, cleanup_after_days: int = 7):
        self.max_concurrent_jobs = max_concurrent_jobs
        self.cleanup_after_days = cleanup_after_days
        
        # Job management
        self.jobs: Dict[str, BackgroundJob] = {}
        self.running_jobs: Set[str] = set()
        self.job_queue: List[str] = []
        
        # State persistence
        self.state_dir = Path(".background-jobs")
        self.state_file = self.state_dir / "jobs-state.json"
        self.state_dir.mkdir(exist_ok=True)
        
        # Threading and async
        self.executor = ThreadPoolExecutor(max_workers=max_concurrent_jobs)
        self.running = False
        self.main_loop_task: Optional[asyncio.Task] = None
        
        # Progress callbacks
        self.progress_callbacks: Dict[str, List[Callable]] = {}
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        self._setup_logging()
        
        # Load existing state
        self._load_state()
        
        # Setup signal handlers for graceful shutdown
        self._setup_signal_handlers()
    
    def _setup_logging(self):
        """Set up logging for the job processor."""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        handler = logging.FileHandler(log_dir / f"background_jobs_{datetime.now().strftime('%Y%m%d')}.log")
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
    
    def _setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            asyncio.create_task(self.shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def _load_state(self):
        """Load job state from persistence."""
        if not self.state_file.exists():
            return
        
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
            
            for job_id, job_data in state_data.get('jobs', {}).items():
                # Convert datetime strings back to datetime objects
                job_data['created_at'] = datetime.fromisoformat(job_data['created_at'])
                if job_data['started_at']:
                    job_data['started_at'] = datetime.fromisoformat(job_data['started_at'])
                if job_data['completed_at']:
                    job_data['completed_at'] = datetime.fromisoformat(job_data['completed_at'])
                
                # Convert enums
                job_data['status'] = JobStatus(job_data['status'])
                job_data['priority'] = JobPriority(job_data['priority'])
                
                # Reconstruct progress object
                progress_data = job_data['progress']
                progress = JobProgress(**progress_data)
                job_data['progress'] = progress
                
                # Create job object
                job = BackgroundJob(**job_data)
                self.jobs[job_id] = job
                
                # Recover running jobs (mark as failed if they were running during shutdown)
                if job.status == JobStatus.RUNNING:
                    job.status = JobStatus.FAILED
                    job.error = "Job was interrupted by system shutdown"
                    self.logger.warning(f"Job {job_id} was running during shutdown, marked as failed")
            
            self.job_queue = state_data.get('job_queue', [])
            self.logger.info(f"Loaded {len(self.jobs)} jobs from state persistence")
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.logger.error(f"Failed to load job state: {e}")
    
    def _save_state(self):
        """Save job state to persistence."""
        try:
            state_data = {
                'jobs': {},
                'job_queue': self.job_queue,
                'last_updated': datetime.now().isoformat()
            }
            
            for job_id, job in self.jobs.items():
                job_dict = asdict(job)
                
                # Convert datetime objects to strings
                job_dict['created_at'] = job.created_at.isoformat()
                job_dict['started_at'] = job.started_at.isoformat() if job.started_at else None
                job_dict['completed_at'] = job.completed_at.isoformat() if job.completed_at else None
                
                # Convert enums to strings
                job_dict['status'] = job.status.value
                job_dict['priority'] = job.priority.value
                
                state_data['jobs'][job_id] = job_dict
            
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            self.logger.error(f"Failed to save job state: {e}")
    
    async def start(self):
        """Start the background job processor."""
        if self.running:
            return
        
        self.running = True
        self.logger.info("Background job processor starting...")
        
        # Start main processing loop
        self.main_loop_task = asyncio.create_task(self._main_processing_loop())
        
        # Clean up old jobs
        await self._cleanup_old_jobs()
        
        # Recover any pending jobs
        await self._recover_pending_jobs()
        
        self.logger.info("Background job processor started successfully")
    
    async def shutdown(self):
        """Gracefully shutdown the job processor."""
        if not self.running:
            return
        
        self.logger.info("Background job processor shutting down...")
        self.running = False
        
        # Cancel main loop
        if self.main_loop_task:
            self.main_loop_task.cancel()
            try:
                await self.main_loop_task
            except asyncio.CancelledError:
                pass
        
        # Wait for running jobs to finish or timeout
        shutdown_timeout = 30  # seconds
        start_time = time.time()
        
        while self.running_jobs and (time.time() - start_time) < shutdown_timeout:
            self.logger.info(f"Waiting for {len(self.running_jobs)} jobs to finish...")
            await asyncio.sleep(1)
        
        # Force cancel remaining jobs
        if self.running_jobs:
            self.logger.warning(f"Force cancelling {len(self.running_jobs)} remaining jobs")
            for job_id in list(self.running_jobs):
                if job_id in self.jobs:
                    self.jobs[job_id].status = JobStatus.CANCELLED
                    self.jobs[job_id].error = "Cancelled due to system shutdown"
        
        # Shutdown executor
        self.executor.shutdown(wait=True)
        
        # Save final state
        self._save_state()
        
        self.logger.info("Background job processor shutdown complete")
    
    async def _main_processing_loop(self):
        """Main processing loop for handling jobs."""
        while self.running:
            try:
                # Process job queue
                await self._process_job_queue()
                
                # Update job progress
                await self._update_job_progress()
                
                # Save state periodically
                self._save_state()
                
                # Sleep before next iteration
                await asyncio.sleep(1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in main processing loop: {e}")
                await asyncio.sleep(5)  # Wait before retrying
    
    async def _process_job_queue(self):
        """Process pending jobs from the queue."""
        # Check if we can start more jobs
        available_slots = self.max_concurrent_jobs - len(self.running_jobs)
        if available_slots <= 0:
            return
        
        # Get next jobs to process
        jobs_to_start = []
        remaining_queue = []
        
        for job_id in self.job_queue:
            if job_id in self.jobs and self.jobs[job_id].status == JobStatus.QUEUED:
                if len(jobs_to_start) < available_slots:
                    jobs_to_start.append(job_id)
                else:
                    remaining_queue.append(job_id)
            elif job_id in self.jobs:
                # Skip jobs that are no longer queued
                continue
            else:
                remaining_queue.append(job_id)
        
        self.job_queue = remaining_queue
        
        # Start jobs
        for job_id in jobs_to_start:
            await self._start_job(job_id)
    
    async def _start_job(self, job_id: str):
        """Start a specific job."""
        if job_id not in self.jobs:
            self.logger.error(f"Job {job_id} not found")
            return
        
        job = self.jobs[job_id]
        
        if job.status != JobStatus.QUEUED:
            self.logger.warning(f"Job {job_id} is not queued, current status: {job.status}")
            return
        
        self.logger.info(f"Starting job {job_id} ({job.job_type})")
        
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now()
        self.running_jobs.add(job_id)
        
        # Submit job to executor
        future = self.executor.submit(self._execute_job, job_id)
        
        # Don't await here - let it run in background
        asyncio.create_task(self._monitor_job_completion(job_id, future))
    
    def _execute_job(self, job_id: str) -> Dict[str, Any]:
        """Execute a job (runs in thread pool)."""
        try:
            job = self.jobs[job_id]
            self.logger.info(f"Executing job {job_id}")
            
            if job.job_type == "auto_complete_book":
                return self._execute_auto_complete_book_job(job)
            else:
                raise ValueError(f"Unknown job type: {job.job_type}")
                
        except Exception as e:
            self.logger.error(f"Job {job_id} execution failed: {e}")
            raise
    
    def _execute_auto_complete_book_job(self, job: BackgroundJob) -> Dict[str, Any]:
        """Execute an auto-complete book job."""
        config = AutoCompletionConfig(**job.config)
        orchestrator = AutoCompleteBookOrchestrator(job.project_path, config)
        
        # Create progress callback
        def progress_callback(chapter_num: int, total_chapters: int, status: str):
            self._update_job_progress_sync(job.job_id, chapter_num, total_chapters, status)
        
        try:
            # Start auto-completion
            orchestrator_job_id = orchestrator.start_auto_completion(user_initiated=False)
            
            # Run auto-completion (this is sync, running in thread pool)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                result = loop.run_until_complete(orchestrator.run_auto_completion())
                return result
            finally:
                loop.close()
                
        except Exception as e:
            self.logger.error(f"Auto-completion job {job.job_id} failed: {e}")
            raise
    
    def _update_job_progress_sync(self, job_id: str, chapter_num: int, total_chapters: int, status: str):
        """Update job progress (thread-safe)."""
        if job_id not in self.jobs:
            return
        
        job = self.jobs[job_id]
        progress = job.progress
        
        progress.current_chapter = chapter_num
        progress.total_chapters = total_chapters
        progress.chapters_completed = chapter_num - 1
        progress.current_step = status
        progress.progress_percentage = (progress.chapters_completed / total_chapters) * 100
        progress.last_update = datetime.now().isoformat()
        
        # Estimate time remaining based on current progress
        if progress.chapters_completed > 0 and job.started_at:
            elapsed_time = datetime.now() - job.started_at
            avg_time_per_chapter = elapsed_time.total_seconds() / progress.chapters_completed
            remaining_chapters = total_chapters - progress.chapters_completed
            estimated_seconds = remaining_chapters * avg_time_per_chapter
            
            if estimated_seconds < 3600:  # Less than 1 hour
                progress.estimated_time_remaining = f"{int(estimated_seconds // 60)} minutes"
            else:  # More than 1 hour
                hours = int(estimated_seconds // 3600)
                minutes = int((estimated_seconds % 3600) // 60)
                progress.estimated_time_remaining = f"{hours}h {minutes}m"
        
        # Call progress callbacks
        if job_id in self.progress_callbacks:
            for callback in self.progress_callbacks[job_id]:
                try:
                    callback(progress)
                except Exception as e:
                    self.logger.error(f"Progress callback failed: {e}")
    
    async def _monitor_job_completion(self, job_id: str, future):
        """Monitor job completion in the background."""
        try:
            # Wait for job completion
            result = await asyncio.wrap_future(future)
            
            # Job completed successfully
            job = self.jobs[job_id]
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.now()
            job.result = result
            
            self.logger.info(f"Job {job_id} completed successfully")
            
        except Exception as e:
            # Job failed
            job = self.jobs[job_id]
            job.status = JobStatus.FAILED
            job.error = str(e)
            job.completed_at = datetime.now()
            
            self.logger.error(f"Job {job_id} failed: {e}")
            
            # Check if we should retry
            if job.retries < job.max_retries:
                job.retries += 1
                job.status = JobStatus.QUEUED
                self.job_queue.append(job_id)
                self.logger.info(f"Job {job_id} queued for retry ({job.retries}/{job.max_retries})")
        
        finally:
            # Remove from running jobs
            self.running_jobs.discard(job_id)
    
    async def _update_job_progress(self):
        """Update progress for all running jobs."""
        for job_id in list(self.running_jobs):
            if job_id in self.jobs:
                job = self.jobs[job_id]
                job.progress.last_update = datetime.now().isoformat()
    
    async def _cleanup_old_jobs(self):
        """Clean up old completed/failed jobs."""
        cutoff_date = datetime.now() - timedelta(days=self.cleanup_after_days)
        
        jobs_to_remove = []
        for job_id, job in self.jobs.items():
            if (job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED] and
                job.completed_at and job.completed_at < cutoff_date):
                jobs_to_remove.append(job_id)
        
        for job_id in jobs_to_remove:
            del self.jobs[job_id]
            self.logger.info(f"Cleaned up old job {job_id}")
        
        if jobs_to_remove:
            self._save_state()
    
    async def _recover_pending_jobs(self):
        """Recover jobs that were pending during shutdown."""
        pending_jobs = [job_id for job_id, job in self.jobs.items() 
                       if job.status == JobStatus.QUEUED]
        
        if pending_jobs:
            self.logger.info(f"Recovering {len(pending_jobs)} pending jobs")
            self.job_queue.extend(pending_jobs)
    
    async def submit_job(self, job_type: str, config: Dict[str, Any], 
                        priority: JobPriority = JobPriority.NORMAL,
                        user_id: Optional[str] = None,
                        project_path: str = "") -> str:
        """Submit a generic job."""
        job_id = str(uuid.uuid4())
        
        # Determine total steps based on job type
        total_steps = 1
        if job_type == "auto_complete_book" and "target_chapter_count" in config:
            total_steps = config["target_chapter_count"]
        elif job_type == "publish_book":
            formats = config.get("publish_config", {}).get("formats", ["epub", "pdf"])
            total_steps = len(formats) + 3  # fetch, build, formats, upload
        
        progress = JobProgress(
            job_id=job_id,
            current_step="queued",
            total_steps=total_steps,
            completed_steps=0,
            progress_percentage=0.0,
            estimated_time_remaining=None,
            current_chapter=None,
            chapters_completed=0,
            total_chapters=total_steps,
            last_update=datetime.now().isoformat(),
            detailed_status={}
        )
        
        job = BackgroundJob(
            job_id=job_id,
            job_type=job_type,
            status=JobStatus.QUEUED,
            priority=priority,
            created_at=datetime.now(),
            started_at=None,
            completed_at=None,
            config=config,
            progress=progress,
            error=None,
            result=None,
            retries=0,
            max_retries=2,
            user_id=user_id,
            project_path=project_path
        )
        
        self.jobs[job_id] = job
        self.job_queue.append(job_id)
        return job_id
    
    def submit_auto_complete_book_job(self, project_path: str, config: AutoCompletionConfig, 
                                    user_id: Optional[str] = None, 
                                    priority: JobPriority = JobPriority.NORMAL) -> str:
        """Submit an auto-complete book job."""
        job_id = str(uuid.uuid4())
        
        progress = JobProgress(
            job_id=job_id,
            current_step="queued",
            total_steps=config.target_chapter_count,
            completed_steps=0,
            progress_percentage=0.0,
            estimated_time_remaining=None,
            current_chapter=None,
            chapters_completed=0,
            total_chapters=config.target_chapter_count,
            last_update=datetime.now().isoformat(),
            detailed_status={}
        )
        
        job = BackgroundJob(
            job_id=job_id,
            job_type="auto_complete_book",
            status=JobStatus.QUEUED,
            priority=priority,
            created_at=datetime.now(),
            started_at=None,
            completed_at=None,
            config=asdict(config),
            progress=progress,
            error=None,
            result=None,
            retries=0,
            max_retries=2,
            user_id=user_id,
            project_path=project_path
        )
        
        self.jobs[job_id] = job
        self.job_queue.append(job_id)
        
        # Sort queue by priority
        self.job_queue.sort(key=lambda jid: self.jobs[jid].priority.value, reverse=True)
        
        self.logger.info(f"Submitted auto-complete book job {job_id} for project {project_path}")
        
        self._save_state()
        return job_id
    
    def get_job_status(self, job_id: str) -> Optional[BackgroundJob]:
        """Get the status of a specific job."""
        return self.jobs.get(job_id)
    
    def get_job_progress(self, job_id: str) -> Optional[JobProgress]:
        """Get the progress of a specific job."""
        job = self.jobs.get(job_id)
        return job.progress if job else None
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a job."""
        if job_id not in self.jobs:
            return False
        
        job = self.jobs[job_id]
        
        if job.status == JobStatus.QUEUED:
            job.status = JobStatus.CANCELLED
            if job_id in self.job_queue:
                self.job_queue.remove(job_id)
            self.logger.info(f"Cancelled queued job {job_id}")
            return True
        elif job.status == JobStatus.RUNNING:
            # For running jobs, we can only mark them for cancellation
            job.status = JobStatus.CANCELLED
            job.error = "Cancelled by user request"
            self.logger.info(f"Marked running job {job_id} for cancellation")
            return True
        
        return False
    
    def pause_job(self, job_id: str) -> bool:
        """Pause a job."""
        if job_id not in self.jobs:
            return False
        
        job = self.jobs[job_id]
        
        if job.status == JobStatus.RUNNING:
            job.status = JobStatus.PAUSED
            self.logger.info(f"Paused job {job_id}")
            return True
        
        return False
    
    def resume_job(self, job_id: str) -> bool:
        """Resume a paused job."""
        if job_id not in self.jobs:
            return False
        
        job = self.jobs[job_id]
        
        if job.status == JobStatus.PAUSED:
            job.status = JobStatus.QUEUED
            if job_id not in self.job_queue:
                self.job_queue.append(job_id)
                # Sort queue by priority
                self.job_queue.sort(key=lambda jid: self.jobs[jid].priority.value, reverse=True)
            self.logger.info(f"Resumed job {job_id}")
            return True
        
        return False
    
    def list_jobs(self, user_id: Optional[str] = None, 
                  status_filter: Optional[JobStatus] = None) -> List[BackgroundJob]:
        """List jobs with optional filtering."""
        jobs = list(self.jobs.values())
        
        if user_id:
            jobs = [job for job in jobs if job.user_id == user_id]
        
        if status_filter:
            jobs = [job for job in jobs if job.status == status_filter]
        
        # Sort by creation date (newest first)
        jobs.sort(key=lambda job: job.created_at, reverse=True)
        
        return jobs
    
    def add_progress_callback(self, job_id: str, callback: Callable[[JobProgress], None]):
        """Add a progress callback for a specific job."""
        if job_id not in self.progress_callbacks:
            self.progress_callbacks[job_id] = []
        self.progress_callbacks[job_id].append(callback)
    
    def remove_progress_callback(self, job_id: str, callback: Callable[[JobProgress], None]):
        """Remove a progress callback for a specific job."""
        if job_id in self.progress_callbacks:
            try:
                self.progress_callbacks[job_id].remove(callback)
                if not self.progress_callbacks[job_id]:
                    del self.progress_callbacks[job_id]
            except ValueError:
                pass
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get overall system status."""
        status = {
            'running': self.running,
            'total_jobs': len(self.jobs),
            'running_jobs': len(self.running_jobs),
            'queued_jobs': len([job for job in self.jobs.values() if job.status == JobStatus.QUEUED]),
            'completed_jobs': len([job for job in self.jobs.values() if job.status == JobStatus.COMPLETED]),
            'failed_jobs': len([job for job in self.jobs.values() if job.status == JobStatus.FAILED]),
            'max_concurrent_jobs': self.max_concurrent_jobs,
            'available_slots': self.max_concurrent_jobs - len(self.running_jobs),
            'last_updated': datetime.now().isoformat()
        }
        
        return status


# Global job processor instance
_job_processor: Optional[BackgroundJobProcessor] = None


def get_job_processor() -> BackgroundJobProcessor:
    """Get the global job processor instance."""
    global _job_processor
    if _job_processor is None:
        _job_processor = BackgroundJobProcessor()
    return _job_processor


async def initialize_job_processor():
    """Initialize the global job processor."""
    processor = get_job_processor()
    await processor.start()
    return processor


async def shutdown_job_processor():
    """Shutdown the global job processor."""
    global _job_processor
    if _job_processor:
        await _job_processor.shutdown()
        _job_processor = None


# CLI Interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Background Job Processor")
    parser.add_argument("action", choices=["start", "status", "list", "cancel", "pause", "resume"], 
                       help="Action to perform")
    parser.add_argument("--job-id", help="Job ID for cancel/pause/resume actions")
    parser.add_argument("--project-path", default=".", help="Project path for new jobs")
    parser.add_argument("--chapters", type=int, default=20, help="Target number of chapters")
    parser.add_argument("--words", type=int, default=80000, help="Target word count")
    parser.add_argument("--quality-threshold", type=float, default=80.0, help="Minimum quality score")
    
    args = parser.parse_args()
    
    async def main():
        processor = get_job_processor()
        
        if args.action == "start":
            await processor.start()
            
            # Submit a test job
            config = AutoCompletionConfig(
                target_chapter_count=args.chapters,
                target_word_count=args.words,
                minimum_quality_score=args.quality_threshold
            )
            
            job_id = processor.submit_auto_complete_book_job(args.project_path, config)
            print(f"🚀 Submitted auto-complete book job: {job_id}")
            
            try:
                # Keep processor running
                while processor.running:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                print("\n🛑 Shutting down...")
                await processor.shutdown()
        
        elif args.action == "status":
            status = processor.get_system_status()
            print("📊 System Status:")
            print(f"  Running: {'✅ Yes' if status['running'] else '❌ No'}")
            print(f"  Total jobs: {status['total_jobs']}")
            print(f"  Running jobs: {status['running_jobs']}")
            print(f"  Queued jobs: {status['queued_jobs']}")
            print(f"  Completed jobs: {status['completed_jobs']}")
            print(f"  Failed jobs: {status['failed_jobs']}")
            print(f"  Available slots: {status['available_slots']}/{status['max_concurrent_jobs']}")
        
        elif args.action == "list":
            jobs = processor.list_jobs()
            print(f"📋 Jobs ({len(jobs)} total):")
            for job in jobs[:10]:  # Show last 10 jobs
                print(f"  {job.job_id[:8]}... - {job.status.value} - {job.job_type} - {job.created_at.strftime('%Y-%m-%d %H:%M')}")
        
        elif args.action in ["cancel", "pause", "resume"] and args.job_id:
            if args.action == "cancel":
                success = processor.cancel_job(args.job_id)
                print(f"❌ Job {'cancelled' if success else 'could not be cancelled'}")
            elif args.action == "pause":
                success = processor.pause_job(args.job_id)
                print(f"⏸️  Job {'paused' if success else 'could not be paused'}")
            elif args.action == "resume":
                success = processor.resume_job(args.job_id)
                print(f"▶️  Job {'resumed' if success else 'could not be resumed'}")
        
        else:
            print("Please provide required arguments for the specified action")
            parser.print_help()
    
    asyncio.run(main()) 