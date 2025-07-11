#!/usr/bin/env python3
"""
FastAPI Backend for Auto-Complete Book Writing System
Provides API endpoints for sequential chapter generation with quality gates.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any, Union
import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from contextlib import asynccontextmanager
from pathlib import Path
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s - %(pathname)s:%(lineno)d',
    handlers=[
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

# Add request ID for tracing
import contextvars
request_id_contextvar = contextvars.ContextVar('request_id', default=None)

# Models
class AutoCompleteRequest(BaseModel):
    """Request model for auto-complete book generation."""
    project_id: str = Field(..., min_length=1, max_length=100, description="Unique project identifier")
    book_bible: str = Field(..., min_length=100, max_length=50000, description="Complete book bible content")
    starting_chapter: int = Field(default=1, ge=1, le=100, description="Chapter to start from")
    target_chapters: Optional[int] = Field(default=None, ge=1, le=100, description="Target number of chapters")
    quality_threshold: float = Field(default=7.0, ge=0.0, le=10.0, description="Minimum quality score")
    words_per_chapter: int = Field(default=3800, ge=500, le=10000, description="Target words per chapter")
    
class JobControlRequest(BaseModel):
    """Request model for job control operations."""
    action: str = Field(..., description="Action: pause, resume, cancel")
    
class JobStatusResponse(BaseModel):
    """Response model for job status."""
    job_id: str
    status: str
    progress: Dict[str, Any]
    current_chapter: Optional[int] = None
    total_chapters: Optional[int] = None
    quality_scores: List[Dict[str, Any]] = []
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
class ChapterGenerationRequest(BaseModel):
    """Request model for single chapter generation."""
    project_id: str = Field(..., min_length=1, max_length=100)
    chapter_number: int = Field(..., ge=1, le=100)
    words: int = Field(default=3800, ge=500, le=10000)
    stage: str = Field(default="complete", pattern="^(draft|complete|revision)$")
    project_data: Dict[str, Any] = Field(default_factory=dict, max_length=10000)
    
class QualityAssessmentRequest(BaseModel):
    """Request model for quality assessment."""
    project_id: str = Field(..., min_length=1, max_length=100)
    chapter_number: int = Field(..., ge=1, le=100)
    chapter_content: str = Field(..., min_length=100, max_length=50000)

class BookBibleInitializeRequest(BaseModel):
    """Request model for book bible initialization."""
    project_id: str = Field(..., min_length=1, max_length=100, description="Unique project identifier")
    content: str = Field(..., min_length=100, max_length=50000, description="Book bible markdown content")

# Import Firestore client
from firestore_client import firestore_client

# Global job update events for SSE optimization
job_update_events: Dict[str, asyncio.Event] = {}

# Application lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting Auto-Complete Book Backend...")
    
    # Initialize services
    try:
        # Import and initialize orchestration modules
        from auto_complete_book_orchestrator import AutoCompleteBookOrchestrator
        from background_job_processor import BackgroundJobProcessor
        from chapter_context_manager import ChapterContextManager
        
        # Store initialized services in app state
        app.state.job_processor = BackgroundJobProcessor()
        
        # Start background job cleanup task
        import asyncio
        asyncio.create_task(periodic_cleanup())
        
        logger.info("All services initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        # Don't fail startup, but log the error
        
    yield
    
    # Cleanup
    logger.info("Shutting down Auto-Complete Book Backend...")

# Create rate limiter
limiter = Limiter(key_func=get_remote_address)

# Create FastAPI app
app = FastAPI(
    title="Auto-Complete Book Writing System",
    description="Backend API for sequential chapter generation with quality gates",
    version="1.0.0",
    lifespan=lifespan
)

# Add rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure CORS and security headers
cors_origins = os.getenv('CORS_ORIGINS', 'http://localhost:3000,https://bookwriterautomated-f9vhlimib-zaclakes-projects.vercel.app').split(',')

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
    expose_headers=["Content-Type", "Authorization"],
)

# Add security headers and logging middleware
@app.middleware("http")
async def add_security_headers_and_logging(request, call_next):
    """Add security headers and request logging to all responses."""
    # Generate request ID for tracing
    req_id = str(uuid.uuid4())[:8]
    request_id_contextvar.set(req_id)
    
    # Log request
    logger.info(
        f"Request started",
        extra={
            "request_id": req_id,
            "method": request.method,
            "url": str(request.url),
            "client_ip": request.client.host if request.client else "unknown"
        }
    )
    
    start_time = datetime.utcnow()
    
    try:
        response = await call_next(request)
        
        # Calculate request duration
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        # Log response
        logger.info(
            f"Request completed",
            extra={
                "request_id": req_id,
                "status_code": response.status_code,
                "duration_seconds": duration
            }
        )
        
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["X-Request-ID"] = req_id
        
        # HTTPS enforcement in production
        if os.getenv('ENVIRONMENT') == 'production':
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        return response
        
    except Exception as e:
        # Log error
        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.error(
            f"Request failed",
            extra={
                "request_id": req_id,
                "error": str(e),
                "duration_seconds": duration
            }
        )
        raise

# Security
security = HTTPBearer()

from auth_middleware import get_current_user, security

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify JWT token using Clerk authentication."""
    from auth_middleware import auth_middleware
    return auth_middleware.verify_token(credentials)

# Debug endpoints
@app.get("/debug/auth-config")
async def debug_auth_config():
    """Debug endpoint to check authentication configuration."""
    clerk_publishable_key = os.getenv('CLERK_PUBLISHABLE_KEY')
    clerk_secret_key = os.getenv('CLERK_SECRET_KEY')
    
    # Parse publishable key to construct JWKS URL
    jwks_url = None
    if clerk_publishable_key:
        if clerk_publishable_key.startswith('pk_test_') or clerk_publishable_key.startswith('pk_live_'):
            parts = clerk_publishable_key.split('_')
            if len(parts) > 2:
                instance_id = parts[2]
                if clerk_publishable_key.startswith('pk_live_'):
                    jwks_url = f"https://clerk.{instance_id}.com/.well-known/jwks.json"
                else:
                    jwks_url = f"https://clerk.{instance_id}.lcl.dev/.well-known/jwks.json"
    
    return {
        "environment": os.getenv('ENVIRONMENT', 'production'),
        "clerk_config": {
            "has_publishable_key": bool(clerk_publishable_key),
            "has_secret_key": bool(clerk_secret_key),
            "publishable_key_prefix": clerk_publishable_key[:20] + "..." if clerk_publishable_key else None,
            "jwks_url": jwks_url,
            "development_mode": os.getenv('ENVIRONMENT') == 'development'
        },
        "cors_origins": os.getenv('CORS_ORIGINS', '').split(',') if os.getenv('CORS_ORIGINS') else [],
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/debug/test-auth")
async def test_auth_simple():
    """Simple test endpoint that doesn't require authentication."""
    return {
        "message": "Backend is accessible",
        "timestamp": datetime.utcnow().isoformat(),
        "status": "ok"
    }

# Root endpoint
@app.get("/")
@limiter.limit("60/minute")
async def root(request: Request):
    """Root endpoint for health check."""
    return {"message": "Auto-Complete Book Backend is running", "version": "1.0.0"}

# Health check endpoint
@app.get("/health")
@limiter.limit("30/minute")
async def health_check(request: Request):
    """Basic health check endpoint."""
    try:
        # Check job processor
        job_processor_healthy = hasattr(app.state, 'job_processor')
        
        # Check storage
        storage_stats = await firestore_client.get_storage_stats()
        storage_healthy = 'error' not in storage_stats
        
        # Check environment variables
        required_env_vars = ['ENVIRONMENT']
        env_status = {var: os.getenv(var) is not None for var in required_env_vars}
        env_healthy = all(env_status.values())
        
        # Overall health status
        overall_healthy = job_processor_healthy and storage_healthy and env_healthy
        
        # Return minimal status for unauthenticated users
        return {
            "status": "healthy" if overall_healthy else "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0"
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat()
        }

# Detailed health check endpoint (requires authentication)
@app.get("/health/detailed")
async def detailed_health_check(user: Dict = Depends(verify_token)):
    """Detailed health check endpoint with comprehensive system status."""
    try:
        # Check job processor
        job_processor_healthy = hasattr(app.state, 'job_processor')
        
        # Check storage
        storage_stats = await firestore_client.get_storage_stats()
        storage_healthy = 'error' not in storage_stats
        
        # Check environment variables
        required_env_vars = ['ENVIRONMENT']
        env_status = {var: os.getenv(var) is not None for var in required_env_vars}
        env_healthy = all(env_status.values())
        
        # Overall health status
        overall_healthy = job_processor_healthy and storage_healthy and env_healthy
        
        health_data = {
            "status": "healthy" if overall_healthy else "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0",
            "environment": os.getenv('ENVIRONMENT', 'unknown'),
            "services": {
                "job_processor": job_processor_healthy,
                "storage": storage_healthy,
                "authentication": os.getenv('CLERK_PUBLISHABLE_KEY') is not None or os.getenv('ENVIRONMENT') == 'development'
            },
            "storage": storage_stats,
            "environment_variables": env_status
        }
        
        # Add job statistics if available
        if hasattr(app.state, 'job_processor'):
            job_stats = {
                "total_jobs": len(app.state.job_processor.jobs),
                "running_jobs": len(app.state.job_processor.running_jobs),
                "completed_jobs": len([j for j in app.state.job_processor.jobs.values() if j.status.value == 'completed'])
            }
            health_data["job_statistics"] = job_stats
        
        return health_data
        
    except Exception as e:
        logger.error(f"Detailed health check failed: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }

# Auto-complete endpoints
@app.post("/auto-complete/start")
@limiter.limit("5/minute")
async def start_auto_complete(
    request_obj: Request,
    request: AutoCompleteRequest,
    background_tasks: BackgroundTasks,
    user: Dict = Depends(verify_token)
):
    """Start auto-complete book generation."""
    try:
        # Generate unique job ID
        job_id = str(uuid.uuid4())
        
        # Create job record
        job_data = {
            "job_id": job_id,
            "user_id": user["user_id"],
            "project_id": request.project_id,
            "status": "initializing",
            "progress": {"current_chapter": 0, "total_chapters": request.target_chapters},
            "config": request.dict(),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "quality_scores": [],
            "error_message": None
        }
        
        # Store job in persistent storage
        await firestore_client.save_job(job_id, job_data)
        
        # Submit job to background processor
        if hasattr(app.state, 'job_processor'):
            await app.state.job_processor.submit_job(
                job_id, 
                run_auto_complete_job, 
                job_id, 
                request
            )
        else:
            # Fallback to background tasks
            background_tasks.add_task(run_auto_complete_job, job_id, request)
        
        return {
            "job_id": job_id,
            "status": "started",
            "message": "Auto-complete job started successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to start auto-complete job: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/auto-complete/{job_id}/status")
async def get_job_status(job_id: str, user: Dict = Depends(verify_token)):
    """Get job status and progress."""
    job_data = await firestore_client.load_job(job_id)
    if not job_data:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Check if user owns this job
    if job_data["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return JobStatusResponse(
        job_id=job_id,
        status=job_data["status"],
        progress=job_data["progress"],
        current_chapter=job_data["progress"].get("current_chapter"),
        total_chapters=job_data["progress"].get("total_chapters"),
        quality_scores=job_data["quality_scores"],
        error_message=job_data.get("error_message"),
        created_at=job_data["created_at"],
        updated_at=job_data["updated_at"]
    )

@app.post("/auto-complete/{job_id}/control")
async def control_job(
    job_id: str,
    request: JobControlRequest,
    user: Dict = Depends(verify_token)
):
    """Control job execution (pause, resume, cancel)."""
    job_data = await firestore_client.load_job(job_id)
    if not job_data:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Check if user owns this job
    if job_data["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update job status based on action
    if request.action == "pause":
        job_data["status"] = "paused"
        # Try to pause in background processor
        if hasattr(app.state, 'job_processor'):
            app.state.job_processor.pause_job(job_id)
    elif request.action == "resume":
        if job_data["status"] == "paused":
            job_data["status"] = "generating"
            # Try to resume in background processor
            if hasattr(app.state, 'job_processor'):
                app.state.job_processor.resume_job(job_id)
    elif request.action == "cancel":
        job_data["status"] = "cancelled"
        # Try to cancel in background processor
        if hasattr(app.state, 'job_processor'):
            app.state.job_processor.cancel_job(job_id)
    else:
        raise HTTPException(status_code=400, detail="Invalid action")
    
    job_data["updated_at"] = datetime.utcnow()
    
    # Save updated job data
    await firestore_client.save_job(job_id, job_data)
    
    return {"message": f"Job {request.action}ed successfully"}

@app.get("/auto-complete/{job_id}/progress")
async def get_job_progress_stream(job_id: str, request: Request, token: Optional[str] = None):
    """Get real-time job progress via Server-Sent Events."""
    job_data = await firestore_client.load_job(job_id)
    if not job_data:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Verify user access - try token from query param first, then header
    user = None
    if token:
        try:
            from fastapi.security import HTTPAuthorizationCredentials
            creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
            user = await verify_token(creds)
        except:
            raise HTTPException(status_code=401, detail="Invalid token")
    else:
        # Try header auth
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                from fastapi.security import HTTPAuthorizationCredentials
                creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
                user = await verify_token(creds)
            except:
                raise HTTPException(status_code=401, detail="Invalid token")
        else:
            raise HTTPException(status_code=401, detail="Authentication required")
    
    # Check if user owns this job
    if job_data["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    async def event_stream():
        """Stream progress updates using event-driven pattern."""
        last_update = None
        
        # Create event for this job if it doesn't exist
        if job_id not in job_update_events:
            job_update_events[job_id] = asyncio.Event()
        
        event = job_update_events[job_id]
        
        # Send initial job state
        try:
            current_job = await firestore_client.load_job(job_id)
            if current_job:
                data = {
                    "job_id": job_id,
                    "status": current_job["status"],
                    "progress": current_job["progress"],
                    "timestamp": current_job["updated_at"].isoformat()
                }
                yield f"data: {json.dumps(data)}\n\n"
                last_update = current_job["updated_at"]
        except Exception as e:
            logger.error(f"Error sending initial job state: {e}")
        
        while True:
            try:
                # Wait for job update event or timeout after 30 seconds
                try:
                    await asyncio.wait_for(event.wait(), timeout=30.0)
                    event.clear()  # Reset event for next update
                except asyncio.TimeoutError:
                    # Send heartbeat
                    yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': datetime.utcnow().isoformat()})}\n\n"
                    continue
                
                current_job = await firestore_client.load_job(job_id)
                if not current_job:
                    break
                
                # Send update if job has changed
                if current_job["updated_at"] != last_update:
                    data = {
                        "job_id": job_id,
                        "status": current_job["status"],
                        "progress": current_job["progress"],
                        "timestamp": current_job["updated_at"].isoformat()
                    }
                    
                    yield f"data: {json.dumps(data)}\n\n"
                    last_update = current_job["updated_at"]
                
                # Break if job is complete
                if current_job["status"] in ["completed", "failed", "cancelled"]:
                    # Clean up event
                    if job_id in job_update_events:
                        del job_update_events[job_id]
                    break
                
            except Exception as e:
                logger.error(f"Error in progress stream: {e}")
                break
    
    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.get("/auto-complete/jobs")
async def list_jobs(
    user: Dict = Depends(verify_token),
    status: Optional[str] = None,
    limit: int = 10,
    offset: int = 0
):
    """List user's auto-complete jobs."""
    user_jobs = await firestore_client.list_user_jobs(user["user_id"], limit=limit + offset, offset=0)
    
    # Filter by status if provided
    if status:
        user_jobs = [job for job in user_jobs if job["status"] == status]
    
    # Apply pagination
    total = len(user_jobs)
    user_jobs = user_jobs[offset:offset + limit]
    
    return {
        "jobs": user_jobs,
        "total": total,
        "limit": limit,
        "offset": offset
    }

# Single chapter generation endpoint (BETA)
@app.post("/v1/chapters/generate")
@limiter.limit("10/minute")
async def generate_chapter(
    request_obj: Request,
    request: ChapterGenerationRequest,
    user: Dict = Depends(verify_token)
):
    """Generate a single chapter. [BETA - Mock Implementation]"""
    try:
        # TODO: Implement actual chapter generation logic
        # For now, return mock response
        return {
            "success": True,
            "chapter": request.chapter_number,
            "content": f"# Chapter {request.chapter_number}\n\nGenerated chapter content...",
            "metadata": {
                "word_count": request.words,
                "stage": request.stage,
                "generated_at": datetime.utcnow().isoformat(),
                "api_version": "v1",
                "status": "BETA - Mock implementation"
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to generate chapter: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Quality assessment endpoint (BETA)
@app.post("/v1/quality/assess")
@limiter.limit("20/minute")
async def assess_quality(
    request_obj: Request,
    request: QualityAssessmentRequest,
    user: Dict = Depends(verify_token)
):
    """Assess chapter quality. [BETA - Mock Implementation]"""
    try:
        # TODO: Implement actual quality assessment logic
        # For now, return mock response
        return {
            "success": True,
            "chapter_number": request.chapter_number,
            "assessment": {
                "overall_score": 8.5,
                "brutal_assessment": {"score": 8.0},
                "engagement_score": {"score": 9.0},
                "quality_gates": {"passed": 8, "total": 10}
            },
            "timestamp": datetime.utcnow().isoformat(),
            "api_version": "v1",
            "status": "BETA - Mock implementation"
        }
        
    except Exception as e:
        logger.error(f"Failed to assess quality: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Book Bible initialization endpoint
@app.post("/book-bible/initialize")
@limiter.limit("10/minute")
async def initialize_book_bible(
    request_obj: Request,
    request: BookBibleInitializeRequest,
    user: Dict = Depends(verify_token)
):
    """Persist the uploaded Book Bible markdown for a given project."""
    try:
        # Validate project directory
        project_workspace = Path(f"./temp_projects/{request.project_id}")
        project_workspace.mkdir(parents=True, exist_ok=True)

        # Write book-bible.md
        book_bible_path = project_workspace / "book-bible.md"
        book_bible_path.write_text(request.content, encoding="utf-8")

        logger.info(f"Book Bible saved for project {request.project_id} at {book_bible_path}")

        # Persist minimal metadata
        metadata_path = project_workspace / "metadata.json"
        metadata = {
            "project_id": request.project_id,
            "book_bible_path": str(book_bible_path),
            "uploaded_by": user.get("user_id"),
            "uploaded_at": datetime.utcnow().isoformat()
        }
        metadata_path.write_text(json.dumps(metadata, indent=2))

        return {
            "success": True,
            "project_id": request.project_id,
            "message": "Book Bible uploaded and project initialized successfully."
        }
    except Exception as e:
        logger.error(f"Failed to initialize Book Bible: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Background job execution
async def run_auto_complete_job(job_id: str, request: AutoCompleteRequest):
    """Run auto-complete job in background."""
    try:
        from auto_complete_book_orchestrator import AutoCompleteBookOrchestrator
        from chapter_context_manager import ChapterContextManager
        
        job_data = await firestore_client.load_job(job_id)
        if not job_data:
            logger.error(f"Job {job_id} not found in storage")
            return
        
        # Create project workspace
        project_workspace = Path(f"./temp_projects/{request.project_id}")
        project_workspace.mkdir(parents=True, exist_ok=True)
        
        # Initialize orchestrator and context manager
        orchestrator = AutoCompleteBookOrchestrator(str(project_workspace))
        context_manager = ChapterContextManager(str(project_workspace))
        
        # Start auto-completion
        request_data = {
            'project_id': request.project_id,
            'book_bible': request.book_bible,
            'target_chapters': request.target_chapters,
            'starting_chapter': request.starting_chapter,
            'quality_threshold': request.quality_threshold,
            'words_per_chapter': request.words_per_chapter
        }
        
        orchestrator.start_auto_completion(request_data)
        
        # Define progress callback
        async def progress_callback(progress_data):
            """Update job progress."""
            job_data["progress"] = progress_data["progress"]
            job_data["quality_scores"] = progress_data.get("quality_scores", [])
            job_data["status"] = progress_data["status"]
            job_data["updated_at"] = datetime.utcnow()
            
            # Save updated job data
            await firestore_client.save_job(job_id, job_data)
            
            # Notify SSE listeners
            if job_id in job_update_events:
                job_update_events[job_id].set()
            
            # Check for user control requests
            if job_data["status"] == "paused":
                orchestrator.pause_auto_completion()
            elif job_data["status"] == "cancelled":
                orchestrator.cancel_auto_completion()
        
        # Run auto-completion with progress callback
        completion_result = await orchestrator.run_auto_completion(progress_callback)
        
        # Update final job status
        job_data["status"] = completion_result["status"]
        job_data["progress"] = completion_result.get("progress", {})
        job_data["quality_scores"] = completion_result.get("quality_scores", [])
        job_data["updated_at"] = datetime.utcnow()
        
        if completion_result["status"] == "completed":
            job_data["completed_at"] = datetime.utcnow()
        
        # Save final job status
        await firestore_client.save_job(job_id, job_data)
            
    except Exception as e:
        logger.error(f"Auto-complete job failed: {e}")
        
        # Load current job data and update with error
        current_job_data = await firestore_client.load_job(job_id)
        if current_job_data:
            current_job_data["status"] = "failed"
            current_job_data["error_message"] = str(e)
            current_job_data["updated_at"] = datetime.utcnow()
            await firestore_client.save_job(job_id, current_job_data)

# Background cleanup task
async def periodic_cleanup():
    """Periodic cleanup of old jobs and temporary files."""
    while True:
        try:
            # Wait 1 hour between cleanup runs
            await asyncio.sleep(3600)
            
            # Cleanup old jobs from storage
            await firestore_client.cleanup_old_jobs(max_age_days=7)
            
            # Cleanup old jobs from memory
            if hasattr(app.state, 'job_processor'):
                app.state.job_processor.cleanup_completed_jobs(max_age_hours=24)
            
            logger.info("Periodic cleanup completed")
            
        except Exception as e:
            logger.error(f"Periodic cleanup failed: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 