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
    PublishJobStatus, ProjectPublishingHistory, JobProgress
)
from backend.auto_complete import (
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
        job_processor = BackgroundJobProcessor()
    return job_processor


def _persist_publish_result(project_id: str, result: PublishResult):
    """Persist publish result to Firestore under projects/{project_id}.publishing.{history,latest}."""
    try:
        db = get_firestore_client()
        project_doc = db.collection('projects').document(project_id)
        snapshot = project_doc.get()
        current_publishing = {}
        if snapshot.exists:
            data = snapshot.to_dict() or {}
            current_publishing = data.get('publishing', {})
        # Append to history
        history = current_publishing.get('history', [])
        history.append(result.dict())
        # Latest only if completed
        from backend.models.firestore_models import PublishJobStatus
        publishing_data = {
            'history': history,
            'latest': result.dict() if result.status == PublishJobStatus.COMPLETED else current_publishing.get('latest')
        }
        project_doc.set({'publishing': publishing_data, 'updated_at': datetime.now(timezone.utc)}, merge=True)
        logger.info(f"📦 Persisted publish result to projects/{project_id}")
    except Exception as e:
        logger.error(f"Failed to persist publish result for {project_id}: {e}")

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
            current_step="Initializing",
            total_steps=len(config.formats) + 3,  # fetch, build, formats, upload
            completed_steps=0,
            percentage=0.0,
            estimated_time_remaining=None
        )
        
        # Create a unique job_id and initialize Firestore record for cross-instance status
        publish_job_id = f"publish_{project_id}_{int(datetime.now(timezone.utc).timestamp())}"
        try:
            db = get_firestore_client()
            db.collection('publish_jobs').document(publish_job_id).set({
                'job_id': publish_job_id,
                'project_id': project_id,
                'user_id': user_id,
                'status': 'pending',
                'progress': {
                    'current_step': 'Initializing',
                    'progress_percentage': 0.0,
                    'last_update': datetime.now(timezone.utc).isoformat()
                },
                'created_at': datetime.now(timezone.utc).isoformat(),
                'started_at': None,
                'completed_at': None
            })
        except Exception as _init_err:
            logger.warning(f"Failed to create publish job doc: {_init_err}")

        # Submit job (simplified interface - no priority support)
        async def publish_job_func():
            # Import and use the real publishing service
            from backend.services.publishing_service import PublishingService
            
            # Create service and run publishing
            service = PublishingService()
            def _progress(step: str, p: float):
                try:
                    db = get_firestore_client()
                    db.collection('publish_jobs').document(publish_job_id).set({
                        'status': 'running',
                        'progress': {
                            'current_step': step,
                            'progress_percentage': round(float(p) * 100.0, 1),
                            'last_update': datetime.now(timezone.utc).isoformat()
                        },
                        'started_at': datetime.now(timezone.utc).isoformat()
                    }, merge=True)
                except Exception as pe:
                    logger.warning(f"Failed to persist publish progress: {pe}")

            result = await service.publish_book(project_id, config, progress_callback=_progress)
            # Persist publish result for Library access
            try:
                _persist_publish_result(project_id, result)
            except Exception as persist_err:
                logger.error(f"Publish result persistence failed: {persist_err}")
            
            # Return result as dict
            from backend.models.firestore_models import PublishJobStatus
            
            # Build download URLs dict
            download_urls = {}
            if result.epub_url:
                download_urls["epub"] = result.epub_url
            if result.pdf_url:
                download_urls["pdf"] = result.pdf_url
            if result.html_url:
                download_urls["html"] = result.html_url
            
            # Persist final job status
            try:
                db = get_firestore_client()
                download_urls_safe = {
                    'epub': download_urls.get('epub'),
                    'pdf': download_urls.get('pdf'),
                    'html': download_urls.get('html')
                }
                db.collection('publish_jobs').document(publish_job_id).set({
                    'status': result.status.value,
                    'progress': {
                        'current_step': 'Completed' if result.status == PublishJobStatus.COMPLETED else 'Failed',
                        'progress_percentage': 100.0 if result.status == PublishJobStatus.COMPLETED else 0.0,
                        'last_update': datetime.now(timezone.utc).isoformat()
                    },
                    'completed_at': datetime.now(timezone.utc).isoformat(),
                    'result': {
                        'download_urls': download_urls_safe,
                        'error_message': result.error_message
                    }
                }, merge=True)
            except Exception as _final_err:
                logger.warning(f"Failed to persist final publish job result: {_final_err}")

            return {
                "success": result.status == PublishJobStatus.COMPLETED,
                "message": "Publishing completed successfully" if result.status == PublishJobStatus.COMPLETED else result.error_message or "Publishing failed",
                "status": result.status.value,
                "download_urls": download_urls,
                "project_id": result.project_id,
                "job_id": publish_job_id,
                "error_message": result.error_message
            }
        
        job_info = await processor.submit_job(publish_job_id, publish_job_func)
        job_id = publish_job_id
        
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
        
        # Prefer Firestore-backed job; fallback to in-memory processor
        try:
            db = get_firestore_client()
            doc = db.collection('publish_jobs').document(job_id).get()
            if doc.exists:
                data = doc.to_dict() or {}
                progress = data.get('progress', {}) or {}
                result = data.get('result', {}) or {}
                return {
                    "job_id": job_id,
                    "status": data.get('status', 'pending'),
                    "progress": {
                        "current_step": progress.get('current_step', ''),
                        "progress_percentage": progress.get('progress_percentage', 0)
                    },
                    "result": result,
                    "created_at": data.get('created_at'),
                    "started_at": data.get('started_at'),
                    "completed_at": data.get('completed_at')
                }
        except Exception as _fs_err:
            logger.warning(f"Publish job Firestore read failed: {_fs_err}")

        processor = get_job_processor()
        job = processor.get_job_status(job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        response = {
            "job_id": job.job_id,
            "status": job.status.value,
            "progress": job.progress or {},
            "created_at": job.created_at.isoformat(),
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None
        }
        if job.status == JobStatus.COMPLETED and job.result:
            response["result"] = job.result
            if "download_urls" in job.result:
                response["download_urls"] = job.result["download_urls"]
                if isinstance(job.result["download_urls"], dict):
                    response["result"]["epub_url"] = job.result["download_urls"].get("epub")
                    response["result"]["pdf_url"] = job.result["download_urls"].get("pdf")
                    response["result"]["html_url"] = job.result["download_urls"].get("html")
        if job.status == JobStatus.FAILED and job.error_message:
            response["error"] = job.error_message
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