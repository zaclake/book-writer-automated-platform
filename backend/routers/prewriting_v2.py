#!/usr/bin/env python3
"""
Prewriting API v2 - Firestore Integration
Prewriting summary generation endpoints.
"""

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

# Robust imports that work from both repo root and backend directory
try:
    from backend.auth_middleware import get_current_user
    from backend.services.prewriting_summary_service import PrewritingSummaryService, PrewritingSummary
    from backend.database_integration import get_project
except ImportError:
    # Fallback when running from backend directory
    from backend.auth_middleware import get_current_user
    from backend.services.prewriting_summary_service import PrewritingSummaryService, PrewritingSummary
    from backend.database_integration import get_project

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/prewriting", tags=["prewriting"])
security = HTTPBearer()

class PrewritingSummaryRequest(BaseModel):
    """Request model for prewriting summary generation."""
    project_id: str = Field(..., min_length=1, max_length=100, description="Unique project identifier")
    project_data: Dict[str, Any] = Field(default_factory=dict, description="Optional project data override")

class PrewritingSummaryResponse(BaseModel):
    """Response model for prewriting summary generation."""
    success: bool
    summary: Optional[PrewritingSummary]
    message: str

@router.post("/summary", response_model=PrewritingSummaryResponse)
async def generate_prewriting_summary(
    request: PrewritingSummaryRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Generate a comprehensive prewriting summary from project data."""
    try:
        logger.info(f"Generating prewriting summary for project {request.project_id} by user {current_user.get('uid')}")
        
        # Get project data if not provided in request
        project_data = request.project_data
        if not project_data:
            project = await get_project(request.project_id, user_id=current_user.get('uid'))
            if not project:
                raise HTTPException(
                    status_code=404,
                    detail=f"Project {request.project_id} not found"
                )
            project_data = project
        
        # Initialize prewriting summary service
        summary_service = PrewritingSummaryService()
        
        # Generate summary
        summary = await summary_service.generate_summary(project_data)
        
        return PrewritingSummaryResponse(
            success=True,
            summary=summary,
            message="Prewriting summary generated successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate prewriting summary for project {request.project_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate prewriting summary: {str(e)}"
        )

@router.get("/summary", response_model=PrewritingSummaryResponse)
async def get_prewriting_summary(
    project_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get existing prewriting summary for a project."""
    try:
        logger.info(f"Retrieving prewriting summary for project {project_id} by user {current_user.get('uid')}")
        
        # Get project data
        project = await get_project(project_id, user_id=current_user.get('uid'))
        if not project:
            raise HTTPException(
                status_code=404,
                detail=f"Project {project_id} not found"
            )
        
        # Check if summary already exists in project metadata
        # For now, we'll generate a new one each time
        # In the future, this could be cached in Firestore
        summary_service = PrewritingSummaryService()
        summary = await summary_service.generate_summary(project)
        
        return PrewritingSummaryResponse(
            success=True,
            summary=summary,
            message="Prewriting summary retrieved successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve prewriting summary for project {project_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve prewriting summary: {str(e)}"
        ) 