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
    from backend.services.story_intake_service import StoryIntakeService
    from backend.database_integration import get_project
except ImportError:
    # Fallback when running from backend directory
    from backend.auth_middleware import get_current_user
    from backend.services.prewriting_summary_service import PrewritingSummaryService, PrewritingSummary
    from backend.services.story_intake_service import StoryIntakeService
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

class StoryClarifyRequest(BaseModel):
    idea: str = Field(..., min_length=50, description="Raw story idea")
    mode: str = Field("brief", description="brief | extended")
    previous_answers: Dict[str, str] = Field(default_factory=dict)
    round_index: int = Field(1, description="Clarification round number")

class StoryRefineRequest(BaseModel):
    idea: str = Field(..., min_length=50, description="Raw story idea")
    mode: str = Field("brief", description="brief | extended")
    answers: Dict[str, str] = Field(default_factory=dict)

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

@router.post("/clarify", response_model=dict)
async def generate_story_clarification_questions(
    request: StoryClarifyRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Generate clarifying questions for paste-idea intake."""
    try:
        user_id = current_user.get('user_id') or current_user.get('uid')
        intake_service = StoryIntakeService(user_id=user_id)
        result = await intake_service.generate_questions(
            idea=request.idea,
            mode=request.mode,
            previous_answers=request.previous_answers,
            round_index=request.round_index
        )
        return {
            'success': True,
            'questions': result.questions,
            'mode': result.mode,
            'round_index': result.round_index
        }
    except Exception as e:
        logger.error(f"Failed to generate story clarification questions: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate questions: {str(e)}"
        )

@router.post("/refine", response_model=dict)
async def refine_story_intake(
    request: StoryRefineRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Refine raw story idea + answers into a clean story brief."""
    try:
        user_id = current_user.get('user_id') or current_user.get('uid')
        intake_service = StoryIntakeService(user_id=user_id)
        result = await intake_service.refine_story(
            idea=request.idea,
            answers=request.answers,
            mode=request.mode
        )
        return {
            'success': True,
            'summary': result.summary,
            'refined_content': result.refined_content,
            'followup_questions': result.followup_questions
        }
    except Exception as e:
        logger.error(f"Failed to refine story intake: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to refine story intake: {str(e)}"
        )