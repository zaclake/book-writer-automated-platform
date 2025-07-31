#!/usr/bin/env python3
"""
Publishing API v2 - Book Publishing Endpoints
Handles book publishing to EPUB, PDF, and HTML formats.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, status
from pathlib import Path

from backend.models.firestore_models import (
    PublishRequest, PublishResult, PublishConfig, PublishFormat,
    PublishJobStatus, ProjectPublishingHistory
)
from backend.background_job_processor import (
    BackgroundJobProcessor, JobStatus, JobInfo
)

# Robust imports that work from both repo root and backend directory
try:
    from backend.database_integration import get_project
    from backend.auth_middleware import get_current_user
    from backend.services.firestore_service import get_firestore_client
except ImportError:
    from database_integration import get_project
    from auth_middleware import get_current_user
    from services.firestore_service import get_firestore_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v2/publish", tags=["publish-v2"])

# Global job processor instance
job_processor: Optional[BackgroundJobProcessor] = None

def get_job_processor() -> BackgroundJobProcessor:
    """Get or create job processor instance."""
    global job_processor
    if job_processor is None:
        job_processor = BackgroundJobProcessor(max_concurrent_jobs=2)
    return job_processor

@router.post("/project/{project_id}", response_model=Dict[str, str])
async def start_publish_job(
    project_id: str,
    config: PublishConfig,
    current_user: dict = Depends(get_current_user)
):
    """Start a publishing job for a project."""
    try:
        logger.info(f"🚀 Starting publish job for project: {project_id}")
        
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )
        
        # Verify user has access to the project
        project_data = await get_project(project_id)
        if not project_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        # Check project access
        owner_id = project_data.get('metadata', {}).get('owner_id')
        collaborators = project_data.get('metadata', {}).get('collaborators', [])
        
        if owner_id != user_id and user_id not in collaborators:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )
        
        # Validate formats
        if not config.formats:
            config.formats = [PublishFormat.EPUB, PublishFormat.PDF]
        
        # Create job
        processor = get_job_processor()
        
        job_config = {
            'project_id': project_id,
            'publish_config': config.dict()
        }
        
        # Create initial progress
        progress = JobProgress(
            job_id="temp",  # Will be set by processor
            current_step="Initializing",
            total_steps=len(config.formats) + 3,  # fetch, build, formats, upload
            completed_steps=0,
            progress_percentage=0.0,
            estimated_time_remaining=None,
            current_chapter=None,
            chapters_completed=0,
            total_chapters=0,
            last_update=datetime.now().isoformat(),
            detailed_status={}
        )
        
        # Submit job (simplified interface - no priority support)
        async def publish_job_func():
            # Placeholder for actual publishing logic
            return {"success": True, "message": "Publishing completed"}
        
        job_info = await processor.submit_job(f"publish_{project_id}", publish_job_func)
        job_id = job_info.job_id
        
        logger.info(f"✅ Publish job {job_id} submitted for project {project_id}")
        
        return {
            "job_id": job_id,
            "status": "submitted",
            "message": f"Publishing job started for {len(config.formats)} format(s)"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start publish job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start publishing job: {str(e)}"
        )

@router.get("/{job_id}", response_model=Dict[str, Any])
async def get_publish_job_status(
    job_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get the status of a publishing job."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )
        
        processor = get_job_processor()
        job = processor.get_job(job_id)
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found"
            )
        
        # Check if user owns this job
        if job.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this job"
            )
        
        # Build response
        response = {
            "job_id": job.job_id,
            "status": job.status.value,
            "progress": {
                "current_step": job.progress.current_step,
                "progress_percentage": job.progress.progress_percentage,
                "last_update": job.progress.last_update
            },
            "created_at": job.created_at.isoformat(),
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None
        }
        
        # Add result if completed
        if job.status == JobStatus.COMPLETED and job.result:
            response["result"] = job.result
        
        # Add error if failed
        if job.status == JobStatus.FAILED and job.error:
            response["error"] = job.error
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get job status: {str(e)}"
        )

@router.get("/project/{project_id}/history", response_model=Dict[str, Any])
async def get_project_publish_history(
    project_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get publishing history for a project."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )
        
        # Verify user has access to the project
        project_data = await get_project(project_id)
        if not project_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        # Check project access
        owner_id = project_data.get('metadata', {}).get('owner_id')
        collaborators = project_data.get('metadata', {}).get('collaborators', [])
        
        if owner_id != user_id and user_id not in collaborators:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )
        
        # Get publishing history from Firestore
        db = get_firestore_client()
        project_doc = db.collection('projects').document(project_id)
        project_snapshot = project_doc.get()
        
        publishing_data = {}
        if project_snapshot.exists:
            project_data = project_snapshot.to_dict()
            publishing_data = project_data.get('publishing', {})
        
        return {
            "project_id": project_id,
            "history": publishing_data.get('history', []),
            "latest": publishing_data.get('latest')
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get publish history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get publish history: {str(e)}"
        )

@router.post("/project/{project_id}/save-result", response_model=Dict[str, str])
async def save_publish_result(
    project_id: str,
    result: PublishResult,
    current_user: dict = Depends(get_current_user)
):
    """Save a publish result to project history."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )
        
        # Verify user has access to the project
        project_data = await get_project(project_id)
        if not project_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        # Check project access
        owner_id = project_data.get('metadata', {}).get('owner_id')
        collaborators = project_data.get('metadata', {}).get('collaborators', [])
        
        if owner_id != user_id and user_id not in collaborators:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )
        
        # Save to Firestore
        db = get_firestore_client()
        project_doc = db.collection('projects').document(project_id)
        
        # Get current publishing data
        project_snapshot = project_doc.get()
        current_publishing = {}
        if project_snapshot.exists:
            project_data = project_snapshot.to_dict()
            current_publishing = project_data.get('publishing', {})
        
        # Add to history
        history = current_publishing.get('history', [])
        history.append(result.dict())
        
        # Update publishing data
        publishing_data = {
            'history': history,
            'latest': result.dict() if result.status == PublishJobStatus.COMPLETED else current_publishing.get('latest')
        }
        
        # Save to Firestore (use merge=True to avoid overwriting)
        project_doc.set({
            'publishing': publishing_data,
            'updated_at': datetime.now(timezone.utc)
        }, merge=True)
        
        logger.info(f"✅ Saved publish result for project {project_id}, job {result.job_id}")
        
        return {
            "status": "saved",
            "message": "Publish result saved to project history"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save publish result: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save publish result: {str(e)}"
        )

# Startup event to initialize job processor
@router.on_event("startup")
async def startup_event():
    """Initialize the job processor on startup."""
    try:
        processor = get_job_processor()
        await processor.start()
        logger.info("✅ Publishing job processor started")
    except Exception as e:
        logger.error(f"Failed to start job processor: {e}")

# Shutdown event to cleanup job processor
@router.on_event("shutdown")
async def shutdown_event():
    """Cleanup the job processor on shutdown."""
    try:
        processor = get_job_processor()
        await processor.shutdown()
        logger.info("✅ Publishing job processor shutdown")
    except Exception as e:
        logger.error(f"Failed to shutdown job processor: {e}") 