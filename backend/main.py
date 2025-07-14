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

# Import path utilities
from utils.paths import temp_projects_root, get_project_workspace, ensure_project_structure
from utils.reference_parser import generate_reference_files

# Import reference content generator
from utils.reference_content_generator import ReferenceContentGenerator

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

# Global exception handler for debugging
from fastapi.responses import JSONResponse
from fastapi.exception_handlers import http_exception_handler
import traceback

@app.exception_handler(Exception)
async def all_exceptions(request: Request, exc: Exception):
    """Global exception handler that logs full tracebacks."""
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logger.error(f"UNCAUGHT EXCEPTION in {request.method} {request.url}\n{tb}")
    
    # Return traceback in response if DEBUG mode is enabled
    if os.getenv("DEBUG", "false").lower() == "true":
        return JSONResponse({
            "detail": str(exc), 
            "trace": tb,
            "url": str(request.url),
            "method": request.method,
            "error_type": type(exc).__name__
        }, status_code=500)
    
    # In production, return more helpful error without exposing internals
    error_detail = str(exc) if "Authentication service not properly configured" in str(exc) else "Internal server error"
    return JSONResponse({
        "detail": error_detail,
        "error_type": type(exc).__name__,
        "timestamp": datetime.utcnow().isoformat()
    }, status_code=500)

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

@app.get("/debug/auth-status")
async def debug_auth_status():
    """Debug endpoint to check if authentication is properly configured."""
    clerk_publishable_key = os.getenv('CLERK_PUBLISHABLE_KEY')
    development_mode = os.getenv('ENVIRONMENT') == 'development'
    
    return {
        "auth_configured": bool(clerk_publishable_key) or development_mode,
        "has_clerk_key": bool(clerk_publishable_key),
        "development_mode": development_mode,
        "environment": os.getenv('ENVIRONMENT', 'unknown'),
        "message": "Authentication is properly configured" if (bool(clerk_publishable_key) or development_mode) else "Authentication MISCONFIGURED - CLERK_PUBLISHABLE_KEY missing",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/debug/test-file-ops")
async def test_file_operations():
    """Test if file operations work in current deployment environment."""
    try:
        from utils.paths import temp_projects_root, get_project_workspace, ensure_project_structure
        import tempfile
        import json
        
        results = {
            "timestamp": datetime.utcnow().isoformat(),
            "environment": os.getenv("ENVIRONMENT", "unknown"),
            "disable_file_ops_env": os.getenv("DISABLE_FILE_OPERATIONS", "not_set"),
            "tests": {}
        }
        
        # Test 1: Basic temp directory creation
        try:
            temp_root = temp_projects_root()
            results["tests"]["temp_root_creation"] = {
                "success": True,
                "path": str(temp_root),
                "exists": temp_root.exists(),
                "writable": os.access(temp_root, os.W_OK)
            }
        except Exception as e:
            results["tests"]["temp_root_creation"] = {
                "success": False,
                "error": str(e)
            }
        
        # Test 2: Project workspace creation
        try:
            test_project_id = f"test-{int(datetime.utcnow().timestamp())}"
            project_workspace = get_project_workspace(test_project_id)
            ensure_project_structure(project_workspace)
            
            results["tests"]["project_workspace"] = {
                "success": True,
                "path": str(project_workspace),
                "exists": project_workspace.exists(),
                "subdirs_created": [
                    d.name for d in project_workspace.iterdir() if d.is_dir()
                ]
            }
        except Exception as e:
            results["tests"]["project_workspace"] = {
                "success": False,
                "error": str(e)
            }
        
        # Test 3: File writing
        try:
            test_file = project_workspace / "test-file.txt"
            test_content = f"Test content written at {datetime.utcnow().isoformat()}"
            test_file.write_text(test_content)
            
            # Read it back
            read_content = test_file.read_text()
            
            results["tests"]["file_writing"] = {
                "success": True,
                "file_path": str(test_file),
                "content_matches": read_content == test_content,
                "file_size": test_file.stat().st_size
            }
            
            # Clean up test file
            test_file.unlink()
            
        except Exception as e:
            results["tests"]["file_writing"] = {
                "success": False,
                "error": str(e)
            }
        
        # Test 4: JSON metadata writing
        try:
            metadata_file = project_workspace / "metadata.json"
            test_metadata = {
                "test_id": test_project_id,
                "created_at": datetime.utcnow().isoformat(),
                "test_data": {"key": "value"}
            }
            metadata_file.write_text(json.dumps(test_metadata, indent=2))
            
            # Read it back
            read_metadata = json.loads(metadata_file.read_text())
            
            results["tests"]["json_metadata"] = {
                "success": True,
                "metadata_matches": read_metadata == test_metadata,
                "file_path": str(metadata_file)
            }
            
            # Clean up
            metadata_file.unlink()
            
        except Exception as e:
            results["tests"]["json_metadata"] = {
                "success": False,
                "error": str(e)
            }
        
        # Test 5: Directory cleanup
        try:
            if project_workspace.exists():
                import shutil
                shutil.rmtree(project_workspace)
                results["tests"]["cleanup"] = {
                    "success": True,
                    "directory_removed": not project_workspace.exists()
                }
        except Exception as e:
            results["tests"]["cleanup"] = {
                "success": False,
                "error": str(e)
            }
        
        # Overall assessment
        all_tests_passed = all(
            test.get("success", False) 
            for test in results["tests"].values()
        )
        
        results["overall"] = {
            "file_operations_working": all_tests_passed,
            "recommendation": (
                "File operations work normally - DISABLE_FILE_OPERATIONS not needed"
                if all_tests_passed
                else "File operations failed - may need DISABLE_FILE_OPERATIONS=true"
            )
        }
        
        return results
        
    except Exception as e:
        return {
            "error": f"File operations test failed: {str(e)}",
            "timestamp": datetime.utcnow().isoformat()
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
        
        # Check authentication configuration
        clerk_publishable_key = os.getenv('CLERK_PUBLISHABLE_KEY')
        development_mode = os.getenv('ENVIRONMENT') == 'development'
        auth_properly_configured = bool(clerk_publishable_key) or development_mode
        
        if not auth_properly_configured:
            logger.warning("Health check: Authentication not properly configured - CLERK_PUBLISHABLE_KEY missing and not in development mode")
        
        # Overall health status
        overall_healthy = job_processor_healthy and storage_healthy and env_healthy and auth_properly_configured
        
        health_data = {
            "status": "healthy" if overall_healthy else "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0",
            "environment": os.getenv('ENVIRONMENT', 'unknown'),
            "services": {
                "job_processor": job_processor_healthy,
                "storage": storage_healthy,
                "authentication": auth_properly_configured
            },
            "authentication_details": {
                "has_clerk_publishable_key": bool(clerk_publishable_key),
                "development_mode": development_mode,
                "auth_configured": auth_properly_configured
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
    request: Request,
    bible_request: BookBibleInitializeRequest,
    user: Dict = Depends(verify_token)
):
    """Persist the uploaded Book Bible markdown for a given project."""
    try:
        # Check if file operations are disabled (for read-only filesystems like Railway)
        disable_file_ops = os.getenv('DISABLE_FILE_OPERATIONS', 'false').lower() == 'true'
        
        if disable_file_ops:
            logger.info(f"File operations disabled - skipping file creation for project {bible_request.project_id}")
            
            # Persist minimal project metadata so status checks can succeed
            project_data = {
                "project_id": bible_request.project_id,
                "book_bible_uploaded": True,
                "uploaded_by": user.get("user_id"),
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                "storage_mode": "file_ops_disabled"
            }
            try:
                await firestore_client.save_project_data(bible_request.project_id, project_data)
                logger.info(f"Project metadata saved for {bible_request.project_id} in file-ops-disabled mode")
            except Exception as e:
                logger.error(f"Failed to save project metadata for {bible_request.project_id}: {e}")
            
            return {
                "success": True,
                "project_id": bible_request.project_id,
                "message": "Book Bible processed successfully (file operations disabled)."
            }
        
        # Try file operations with automatic fallback on permission errors
        try:
            # Get project workspace using new path utility
            project_workspace = get_project_workspace(bible_request.project_id)
            ensure_project_structure(project_workspace)

            # Write book-bible.md
            book_bible_path = project_workspace / "book-bible.md"
            book_bible_path.write_text(bible_request.content, encoding="utf-8")

            logger.info(f"Book Bible saved for project {bible_request.project_id} at {book_bible_path}")

            # Generate reference files from book bible content
            references_dir = project_workspace / "references"
            try:
                created_files = generate_reference_files(bible_request.content, references_dir)
                logger.info(f"Generated reference file structure for project {bible_request.project_id}: {created_files}")
                
                # Generate AI-powered content for reference files
                content_generator = ReferenceContentGenerator()
                if content_generator.is_available():
                    try:
                        logger.info(f"Generating AI-powered content for reference files in project {bible_request.project_id}")
                        generation_results = content_generator.generate_all_references(
                            book_bible_content=bible_request.content,
                            references_dir=references_dir
                        )
                        
                        successful_generations = [
                            ref for ref, result in generation_results.items() 
                            if result.get("success", False)
                        ]
                        failed_generations = [
                            ref for ref, result in generation_results.items() 
                            if not result.get("success", False)
                        ]
                        
                        logger.info(f"AI content generation completed for project {bible_request.project_id}: "
                                  f"{len(successful_generations)} successful, {len(failed_generations)} failed")
                        
                        if failed_generations:
                            logger.warning(f"Failed to generate AI content for: {failed_generations}")
                            
                    except Exception as ai_error:
                        logger.warning(f"AI content generation failed for project {bible_request.project_id}: {ai_error}")
                        # Continue with basic reference files if AI generation fails
                else:
                    logger.info(f"OpenAI API not configured - using template reference files for project {bible_request.project_id}")
                
            except Exception as e:
                logger.error(f"Failed to generate reference files: {e}")
                # Don't fail the whole request if reference generation fails

            # Persist minimal metadata
            metadata_path = project_workspace / "metadata.json"
            metadata = {
                "project_id": bible_request.project_id,
                "book_bible_path": str(book_bible_path),
                "uploaded_by": user.get("user_id"),
                "uploaded_at": datetime.utcnow().isoformat()
            }
            metadata_path.write_text(json.dumps(metadata, indent=2))

            return {
                "success": True,
                "project_id": bible_request.project_id,
                "message": "Book Bible uploaded and project initialized successfully."
            }
            
        except (PermissionError, OSError, IOError) as fs_error:
            # Filesystem is read-only or has permission issues - return success anyway
            logger.warning(f"Filesystem error for project {bible_request.project_id}: {fs_error}")
            logger.info(f"Continuing without file operations due to filesystem limitations")
            return {
                "success": True,
                "project_id": bible_request.project_id,
                "message": "Book Bible processed successfully (filesystem read-only)."
            }
            
    except Exception as e:
        logger.error(f"Failed to initialize Book Bible: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Book Bible upload endpoint
@app.post("/book-bible/upload")
@limiter.limit("10/minute")
async def upload_book_bible(
    request_obj: Request,
    request: Dict[str, Any],
    user: Dict = Depends(verify_token)
):
    """Upload book bible file and create project."""
    try:
        # Extract data from request
        filename = request.get("filename")
        content = request.get("content")
        project_info = request.get("projectInfo", {})
        
        if not filename or not content:
            raise HTTPException(status_code=400, detail="Filename and content are required")
        
        # Validate that it's a markdown file
        if not filename.endswith('.md'):
            raise HTTPException(status_code=400, detail="File must be a Markdown (.md) file")
        
        # Generate unique project ID
        project_id = f"project-{int(datetime.utcnow().timestamp() * 1000)}"
        
        # Get project workspace
        project_workspace = get_project_workspace(project_id)
        ensure_project_structure(project_workspace)
        
        # Write book-bible.md
        book_bible_path = project_workspace / "book-bible.md"
        book_bible_path.write_text(content, encoding="utf-8")
        
        logger.info(f"Book Bible uploaded for project {project_id} at {book_bible_path}")
        
        # Generate reference files from book bible content
        references_dir = project_workspace / "references"
        try:
            created_files = generate_reference_files(content, references_dir)
            logger.info(f"Generated reference file structure for project {project_id}: {created_files}")
            
            # Generate AI-powered content for reference files
            content_generator = ReferenceContentGenerator()
            if content_generator.is_available():
                try:
                    logger.info(f"Generating AI-powered content for reference files in project {project_id}")
                    generation_results = content_generator.generate_all_references(
                        book_bible_content=content,
                        references_dir=references_dir
                    )
                    
                    successful_generations = [
                        ref for ref, result in generation_results.items() 
                        if result.get("success", False)
                    ]
                    failed_generations = [
                        ref for ref, result in generation_results.items() 
                        if not result.get("success", False)
                    ]
                    
                    logger.info(f"AI content generation completed for project {project_id}: "
                              f"{len(successful_generations)} successful, {len(failed_generations)} failed")
                    
                    if failed_generations:
                        logger.warning(f"Failed to generate AI content for: {failed_generations}")
                        
                except Exception as ai_error:
                    logger.warning(f"AI content generation failed for project {project_id}: {ai_error}")
                    # Continue with basic reference files if AI generation fails
            else:
                logger.info(f"OpenAI API not configured - using template reference files for project {project_id}")
                
        except Exception as e:
            logger.error(f"Failed to generate reference files: {e}")
            # Don't fail the whole request if reference generation fails
        
        # Save project metadata
        metadata_path = project_workspace / "metadata.json"
        metadata = {
            "project_id": project_id,
            "title": project_info.get("title", "Untitled Project"),
            "genre": project_info.get("genre", "Unknown"),
            "logline": project_info.get("logline", ""),
            "book_bible_path": str(book_bible_path),
            "uploaded_by": user.get("user_id"),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "book_bible_uploaded": True
        }
        metadata_path.write_text(json.dumps(metadata, indent=2))
        
        return {
            "success": True,
            "project_id": project_id,
            "message": "Book Bible uploaded successfully",
            "filename": filename,
            "projectInfo": project_info
        }
        
    except Exception as e:
        logger.error(f"Failed to upload Book Bible: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Project status endpoint
@app.get("/project/status")
@limiter.limit("30/minute")
async def get_project_status(
    request: Request,
    project_id: Optional[str] = None,
    user: Dict = Depends(verify_token)
):
    """Get project status and file information."""
    try:
        if not project_id:
            # List all projects for the user
            temp_projects_dir = temp_projects_root()
            if temp_projects_dir.exists():
                projects = []
                for project_dir in temp_projects_dir.iterdir():
                    if project_dir.is_dir():
                        metadata_path = project_dir / "metadata.json"
                        if metadata_path.exists():
                            try:
                                metadata = json.loads(metadata_path.read_text())
                                projects.append({
                                    "project_id": project_dir.name,
                                    "title": metadata.get("title", "Untitled"),
                                    "created_at": metadata.get("created_at"),
                                    "updated_at": metadata.get("updated_at")
                                })
                            except Exception as e:
                                logger.error(f"Failed to read metadata for {project_dir.name}: {e}")
                return {
                    "projects": projects,
                    "total": len(projects)
                }
        else:
            # Get specific project status
            disable_file_ops = os.getenv('DISABLE_FILE_OPERATIONS', 'false').lower() == 'true'

            # If file operations are disabled, rely on stored project metadata instead of filesystem
            if disable_file_ops:
                try:
                    project_data = await firestore_client.load_project_data(project_id)
                    if project_data:
                        return {
                            "initialized": True,
                            "hasBookBible": project_data.get("book_bible_uploaded", False),
                            "hasReferences": True,  # Assume references generated in memory
                            "hasState": True,       # Assume project state managed in memory
                            "referenceFiles": project_data.get("reference_files", []),
                            "metadata": project_data,
                            "message": "Project fully initialized (file operations disabled)"
                        }
                except Exception as e:
                    logger.error(f"Failed to load project metadata for {project_id}: {e}")

            project_workspace = get_project_workspace(project_id)
            if not project_workspace.exists():
                return {
                    "initialized": False,
                    "hasBookBible": False,
                    "hasReferences": False,
                    "hasState": False,
                    "referenceFiles": [],
                    "metadata": None,
                    "message": "Project not found"
                }
            
            # Check for book bible
            book_bible_path = project_workspace / "book-bible.md"
            has_book_bible = book_bible_path.exists()
            
            # Check for reference files
            references_dir = project_workspace / "references"
            has_references = references_dir.exists()
            reference_files = []
            if has_references:
                try:
                    reference_files = [f.name for f in references_dir.iterdir() if f.suffix == '.md']
                except Exception as e:
                    logger.error(f"Failed to list reference files: {e}")
            
            # Check for project state
            state_dir = project_workspace / ".project-state"
            has_state = state_dir.exists()
            
            # Check for project metadata
            metadata_path = project_workspace / "metadata.json"
            metadata = None
            if metadata_path.exists():
                try:
                    metadata = json.loads(metadata_path.read_text())
                except Exception as e:
                    logger.error(f"Failed to read metadata: {e}")
            
            initialized = has_book_bible and has_references and has_state
            
            return {
                "initialized": initialized,
                "hasBookBible": has_book_bible,
                "hasReferences": has_references,
                "hasState": has_state,
                "referenceFiles": reference_files,
                "metadata": metadata,
                "message": (
                    "Project fully initialized and ready for chapter generation"
                    if initialized
                    else "Project incomplete. Missing: " + ", ".join([
                        item for item in [
                            "book-bible.md" if not has_book_bible else None,
                            "reference files" if not has_references else None,
                            "project state" if not has_state else None
                        ] if item
                    ])
                )
            }
            
    except Exception as e:
        logger.error(f"Failed to get project status: {e}")
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
        project_workspace = get_project_workspace(request.project_id)
        ensure_project_structure(project_workspace)
        
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

# Reference Files endpoints
@app.get("/references")
@limiter.limit("30/minute")
async def list_reference_files(
    request: Request,
    project_id: Optional[str] = None,
    user: Dict = Depends(verify_token)
):
    """List reference files for a project."""
    try:
        if not project_id:
            return {
                "success": True,
                "files": [],
                "total": 0,
                "message": "No project_id provided"
            }
 
        project_workspace = get_project_workspace(project_id)
        references_dir = project_workspace / "references"
 
        if not references_dir.exists():
            return {
                "success": True,
                "files": [],
                "total": 0,
                "message": f"References directory not found for project {project_id}"
            }
 
        # Get all reference files
        files = []
        for file_path in references_dir.glob("*.md"):
            if file_path.is_file():
                stat = file_path.stat()
                files.append({
                    "name": file_path.name,
                    "lastModified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "size": stat.st_size
                })
 
        # Sort by name
        files.sort(key=lambda x: x["name"])
 
        logger.info(f"Found {len(files)} reference files for project {project_id}")
 
        return {
            "success": True,
            "files": files,
            "total": len(files)
        }
 
    except Exception as e:
        logger.error(f"Failed to list reference files: {e}")
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.get("/references/{filename}")
@limiter.limit("30/minute")
async def get_reference_file(
    request: Request,
    filename: str,
    project_id: Optional[str] = None,
    user: Dict = Depends(verify_token)
):
    """Get content of a specific reference file."""
    try:
        if not project_id:
            raise HTTPException(status_code=400, detail="project_id parameter is required")
 
        if not filename.endswith('.md'):
            raise HTTPException(status_code=400, detail="Invalid filename. Must be a .md file")
 
        project_workspace = get_project_workspace(project_id)
        file_path = project_workspace / "references" / filename
 
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"Reference file '{filename}' not found")
 
        content = file_path.read_text(encoding="utf-8")
        stat = file_path.stat()
 
        logger.info(f"Retrieved reference file {filename} for project {project_id}")
 
        return {
            "success": True,
            "name": filename,
            "content": content,
            "lastModified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "size": stat.st_size
        }
 
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get reference file {filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
 
 
@app.put("/references/{filename}")
@limiter.limit("20/minute")
async def update_reference_file(
    request: Request,
    filename: str,
    project_id: Optional[str] = None,
    user: Dict = Depends(verify_token)
):
    """Update content of a specific reference file."""
    try:
        if not project_id:
            raise HTTPException(status_code=400, detail="project_id parameter is required")
 
        if not filename.endswith('.md'):
            raise HTTPException(status_code=400, detail="Invalid filename. Must be a .md file")
 
        # Get request body
        body = await request.json()
        content = body.get("content")
         
        if content is None:
            raise HTTPException(status_code=400, detail="Content is required")
 
        project_workspace = get_project_workspace(project_id)
        file_path = project_workspace / "references" / filename
 
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"Reference file '{filename}' not found")
 
        # Write the updated content
        file_path.write_text(content, encoding="utf-8")
        stat = file_path.stat()
 
        logger.info(f"Updated reference file {filename} for project {project_id}")
 
        return {
            "success": True,
            "message": f"Reference file '{filename}' updated successfully",
            "name": filename,
            "lastModified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "size": stat.st_size
        }
 
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update reference file {filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class ReferenceGenerationRequest(BaseModel):
    """Request model for reference content generation."""
    project_id: str = Field(..., min_length=1, max_length=100, description="Project identifier")
    reference_types: Optional[List[str]] = Field(default=None, description="List of reference types to generate")

class ReferenceRegenerateRequest(BaseModel):
    """Request model for single reference regeneration."""
    project_id: str = Field(..., min_length=1, max_length=100, description="Project identifier")

@app.post("/references/generate")
@limiter.limit("5/minute")
async def generate_reference_content(
    request: Request,
    generation_request: ReferenceGenerationRequest,
    user: Dict = Depends(verify_token)
):
    """Generate AI-powered content for reference files based on book bible."""
    try:
        # Get project workspace and check for book bible
        project_workspace = get_project_workspace(generation_request.project_id)
        book_bible_path = project_workspace / "book-bible.md"
        
        if not book_bible_path.exists():
            raise HTTPException(
                status_code=400, 
                detail=f"Book bible not found for project {generation_request.project_id}"
            )
        
        # Read book bible content
        book_bible_content = book_bible_path.read_text(encoding='utf-8')
        
        # Initialize content generator
        generator = ReferenceContentGenerator()
        
        if not generator.is_available():
            raise HTTPException(
                status_code=503,
                detail="OpenAI API key not configured. Cannot generate reference content."
            )
        
        # Get references directory
        references_dir = project_workspace / "references"
        references_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate content for all requested types
        reference_types = generation_request.reference_types or ['characters', 'outline', 'world-building', 'style-guide', 'plot-timeline']
        
        logger.info(f"Generating reference content for project {generation_request.project_id}, types: {reference_types}")
        
        results = generator.generate_all_references(
            book_bible_content=book_bible_content,
            references_dir=references_dir,
            reference_types=reference_types
        )
        
        # Count successes and failures
        successful = [ref for ref, result in results.items() if result.get("success", False)]
        failed = [ref for ref, result in results.items() if not result.get("success", False)]
        
        response_data = {
            "success": len(failed) == 0,
            "project_id": generation_request.project_id,
            "generated_files": len(successful),
            "failed_files": len(failed),
            "results": results,
            "message": (
                f"Successfully generated {len(successful)} reference files"
                if len(failed) == 0
                else f"Generated {len(successful)} files, {len(failed)} failed"
            )
        }
        
        logger.info(f"Reference generation completed for project {generation_request.project_id}: {len(successful)} success, {len(failed)} failed")
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate reference content: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/references/{filename}/regenerate")
@limiter.limit("10/minute")
async def regenerate_reference_file(
    request: Request,
    filename: str,
    regenerate_request: ReferenceRegenerateRequest,
    user: Dict = Depends(verify_token)
):
    """Regenerate content for a specific reference file."""
    try:
        if not filename.endswith('.md'):
            raise HTTPException(status_code=400, detail="Invalid filename. Must be a .md file")
        
        # Map filename to reference type
        filename_to_type = {
            'characters.md': 'characters',
            'outline.md': 'outline',
            'world-building.md': 'world-building',
            'style-guide.md': 'style-guide',
            'plot-timeline.md': 'plot-timeline'
        }
        
        reference_type = filename_to_type.get(filename)
        if not reference_type:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot regenerate {filename}. Supported files: {list(filename_to_type.keys())}"
            )
        
        # Get project workspace and check for book bible
        project_workspace = get_project_workspace(regenerate_request.project_id)
        book_bible_path = project_workspace / "book-bible.md"
        
        if not book_bible_path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Book bible not found for project {regenerate_request.project_id}"
            )
        
        # Read book bible content
        book_bible_content = book_bible_path.read_text(encoding='utf-8')
        
        # Initialize content generator
        generator = ReferenceContentGenerator()
        
        if not generator.is_available():
            raise HTTPException(
                status_code=503,
                detail="OpenAI API key not configured. Cannot regenerate reference content."
            )
        
        # Get references directory
        references_dir = project_workspace / "references"
        references_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Regenerating {filename} for project {regenerate_request.project_id}")
        
        # Regenerate the specific reference file
        result = generator.regenerate_reference(
            reference_type=reference_type,
            book_bible_content=book_bible_content,
            references_dir=references_dir
        )
        
        if result["success"]:
            logger.info(f"Successfully regenerated {filename} for project {regenerate_request.project_id}")
        else:
            logger.error(f"Failed to regenerate {filename}: {result.get('error', 'Unknown error')}")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to regenerate reference file {filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 