#!/usr/bin/env python3
"""
Chapters API v2 - Firestore Integration with Versioning
Chapter management endpoints with full versioning support.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, status, Query

from models.firestore_models import (
    Chapter, CreateChapterRequest, ChapterListResponse,
    ChapterVersion, QualityScores, ChapterStage
)
from database_integration import (
    get_project_chapters, create_chapter, get_project,
    track_usage, get_database_adapter
)
from auth_middleware import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v2/chapters", tags=["chapters-v2"])

# =====================================================================
# REQUEST/RESPONSE MODELS
# =====================================================================

from pydantic import BaseModel

class UpdateChapterRequest(BaseModel):
    """Request model for updating chapter content."""
    content: Optional[str] = None
    title: Optional[str] = None
    stage: Optional[ChapterStage] = None
    quality_scores: Optional[QualityScores] = None

class AddVersionRequest(BaseModel):
    """Request model for adding a new chapter version."""
    content: str
    reason: str  # "quality_revision", "user_edit", "ai_improvement"
    changes_summary: str = ""

class ChapterStatsResponse(BaseModel):
    """Response model for chapter statistics."""
    word_count: int
    version_count: int
    latest_version: int
    quality_score: float
    generation_cost: float
    last_modified: datetime

# =====================================================================
# CHAPTER CRUD OPERATIONS
# =====================================================================

@router.get("/project/{project_id}", response_model=ChapterListResponse)
async def list_project_chapters(
    project_id: str,
    current_user: dict = Depends(get_current_user),
    include_content: bool = Query(False, description="Include full chapter content in response")
):
    """Get all chapters for a specific project."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )
        
        # Verify user has access to this project
        try:
            project_data = await get_project(project_id)
        except Exception as e:
            logger.error(f"Database error fetching project {project_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to access project data"
            )
            
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
        
        # Get chapters
        try:
            chapters_data = await get_project_chapters(project_id)
        except Exception as e:
            logger.error(f"Database error fetching chapters for project {project_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve chapters from database"
            )
        
        # Convert to Pydantic models
        chapters = []
        for chapter_data in chapters_data:
            try:
                # Remove content if not requested (for performance)
                if not include_content:
                    chapter_data_copy = chapter_data.copy()
                    chapter_data_copy['content'] = ""
                    # Also remove version content
                    if 'versions' in chapter_data_copy:
                        for version in chapter_data_copy['versions']:
                            version['content'] = ""
                    chapter = Chapter(**chapter_data_copy)
                else:
                    chapter = Chapter(**chapter_data)
                
                chapters.append(chapter)
            except Exception as e:
                logger.error(f"Failed to parse chapter data: {e}")
                continue
        
        return ChapterListResponse(
            chapters=chapters,
            total=len(chapters)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list chapters for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chapters"
        )

@router.post("/", response_model=dict)
async def create_new_chapter(
    request: CreateChapterRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create a new chapter in a project."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )
        
        # Verify user has access to the project
        try:
            project_data = await get_project(request.project_id)
        except Exception as e:
            logger.error(f"Database error fetching project {request.project_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to access project data"
            )
            
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
        
        # Create chapter data structure
        chapter_data = {
            'project_id': request.project_id,
            'chapter_number': request.chapter_number,
            'content': request.content,
            'title': request.title,
            'metadata': {
                'word_count': len(request.content.split()),
                'target_word_count': request.target_word_count,
                'created_by': user_id,
                'stage': 'draft',
                'generation_time': 0.0,
                'retry_attempts': 0,
                'model_used': 'manual',
                'tokens_used': {'prompt': 0, 'completion': 0, 'total': 0},
                'cost_breakdown': {'input_cost': 0.0, 'output_cost': 0.0, 'total_cost': 0.0}
            },
            'quality_scores': {
                'engagement_score': 0.0,
                'overall_rating': 0.0,
                'craft_scores': {
                    'prose': 0.0,
                    'character': 0.0,
                    'story': 0.0,
                    'emotion': 0.0,
                    'freshness': 0.0
                },
                'pattern_violations': [],
                'improvement_suggestions': []
            },
            'versions': [{
                'version_number': 1,
                'content': request.content,
                'timestamp': datetime.now(timezone.utc),
                'reason': 'initial_creation',
                'user_id': user_id,
                'changes_summary': 'Initial chapter creation'
            }],
            'context_data': {
                'character_states': {},
                'plot_threads': [],
                'world_state': {},
                'timeline_position': None,
                'previous_chapter_summary': ''
            }
        }
        
        # Create the chapter
        try:
            chapter_id = await create_chapter(chapter_data)
        except Exception as e:
            logger.error(f"Database error creating chapter: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create chapter in database"
            )
        
        if not chapter_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Chapter creation returned invalid ID"
            )
        
        # Track usage (non-critical, don't fail the request if this fails)
        try:
            await track_usage(user_id, {
                'chapters_generated': 1,
                'words_generated': len(request.content.split()),
                'api_calls': 1
            })
        except Exception as e:
            logger.warning(f"Failed to track usage for user {user_id}: {e}")
            # Continue without failing the request
        
        return {
            'chapter_id': chapter_id,
            'message': 'Chapter created successfully'
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create chapter: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create chapter"
        )

@router.get("/{chapter_id}", response_model=Chapter)
async def get_chapter_details(
    chapter_id: str,
    current_user: dict = Depends(get_current_user),
    version: Optional[int] = Query(None, description="Specific version to retrieve")
):
    """Get detailed information about a specific chapter."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )
        
        db = get_database_adapter()
        
        # Get chapter data
        if db.use_firestore:
            chapter_data = await db.firestore.get_chapter(chapter_id)
        else:
            # Mock implementation for local storage
            chapter_data = None
        
        if not chapter_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chapter not found"
            )
        
        # Verify user has access to the project
        project_id = chapter_data.get('project_id')
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
                detail="Access denied to this chapter"
            )
        
        # If specific version requested, replace content with that version
        if version is not None:
            versions = chapter_data.get('versions', [])
            version_found = None
            
            for v in versions:
                if v.get('version_number') == version:
                    version_found = v
                    break
            
            if not version_found:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Version {version} not found"
                )
            
            # Replace main content with version content
            chapter_data['content'] = version_found['content']
        
        # Convert to Pydantic model
        chapter = Chapter(**chapter_data)
        
        return chapter
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get chapter {chapter_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chapter"
        )

@router.put("/{chapter_id}", response_model=dict)
async def update_chapter(
    chapter_id: str,
    request: UpdateChapterRequest,
    current_user: dict = Depends(get_current_user)
):
    """Update a chapter and create a new version."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )
        
        db = get_database_adapter()
        
        # Get current chapter
        if db.use_firestore:
            chapter_data = await db.firestore.get_chapter(chapter_id)
        else:
            chapter_data = None
        
        if not chapter_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chapter not found"
            )
        
        # Verify user has access to the project
        project_id = chapter_data.get('project_id')
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
                detail="Access denied to this chapter"
            )
        
        # Build update dictionary
        updates = {}
        
        if request.title is not None:
            updates['title'] = request.title
        
        if request.stage is not None:
            updates['metadata.stage'] = request.stage.value
        
        if request.quality_scores is not None:
            updates['quality_scores'] = request.quality_scores.dict()
        
        # If content is being updated, create a new version
        if request.content is not None:
            updates['content'] = request.content
            updates['metadata.word_count'] = len(request.content.split())
            
            # Create new version entry
            current_versions = chapter_data.get('versions', [])
            new_version = {
                'version_number': len(current_versions) + 1,
                'content': request.content,
                'timestamp': datetime.now(timezone.utc),
                'reason': 'user_edit',
                'user_id': user_id,
                'changes_summary': 'Manual content update'
            }
            
            current_versions.append(new_version)
            updates['versions'] = current_versions
        
        # Perform the update
        if db.use_firestore:
            success = await db.firestore.update_chapter(chapter_id, updates)
        else:
            success = True
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update chapter"
            )
        
        return {
            'message': 'Chapter updated successfully',
            'version_created': request.content is not None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update chapter {chapter_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update chapter"
        )

# =====================================================================
# VERSIONING OPERATIONS
# =====================================================================

@router.post("/{chapter_id}/versions", response_model=dict)
async def add_chapter_version(
    chapter_id: str,
    request: AddVersionRequest,
    current_user: dict = Depends(get_current_user)
):
    """Add a new version to a chapter."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )
        
        db = get_database_adapter()
        
        # Verify chapter exists and user has access
        if db.use_firestore:
            chapter_data = await db.firestore.get_chapter(chapter_id)
        else:
            chapter_data = None
        
        if not chapter_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chapter not found"
            )
        
        # Verify project access
        project_id = chapter_data.get('project_id')
        project_data = await get_project(project_id)
        
        if not project_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        owner_id = project_data.get('metadata', {}).get('owner_id')
        collaborators = project_data.get('metadata', {}).get('collaborators', [])
        
        if owner_id != user_id and user_id not in collaborators:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this chapter"
            )
        
        # Create version data
        version_data = {
            'content': request.content,
            'reason': request.reason,
            'user_id': user_id,
            'changes_summary': request.changes_summary
        }
        
        # Add the version
        if db.use_firestore:
            success = await db.firestore.add_chapter_version(chapter_id, version_data)
        else:
            success = True
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to add chapter version"
            )
        
        return {
            'message': 'Chapter version added successfully'
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add version to chapter {chapter_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add chapter version"
        )

@router.get("/{chapter_id}/versions", response_model=List[ChapterVersion])
async def get_chapter_versions(
    chapter_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get all versions of a chapter."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )
        
        db = get_database_adapter()
        
        # Get chapter data
        if db.use_firestore:
            chapter_data = await db.firestore.get_chapter(chapter_id)
        else:
            chapter_data = None
        
        if not chapter_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chapter not found"
            )
        
        # Verify project access
        project_id = chapter_data.get('project_id')
        project_data = await get_project(project_id)
        
        if not project_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        owner_id = project_data.get('metadata', {}).get('owner_id')
        collaborators = project_data.get('metadata', {}).get('collaborators', [])
        
        if owner_id != user_id and user_id not in collaborators:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this chapter"
            )
        
        # Get versions
        versions_data = chapter_data.get('versions', [])
        
        # Convert to Pydantic models
        versions = []
        for version_data in versions_data:
            try:
                version = ChapterVersion(**version_data)
                versions.append(version)
            except Exception as e:
                logger.error(f"Failed to parse version data: {e}")
                continue
        
        return versions
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get versions for chapter {chapter_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chapter versions"
        )

# =====================================================================
# STATISTICS & ANALYTICS
# =====================================================================

@router.get("/{chapter_id}/stats", response_model=ChapterStatsResponse)
async def get_chapter_statistics(
    chapter_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get statistics for a specific chapter."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )
        
        db = get_database_adapter()
        
        # Get chapter data
        if db.use_firestore:
            chapter_data = await db.firestore.get_chapter(chapter_id)
        else:
            chapter_data = None
        
        if not chapter_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chapter not found"
            )
        
        # Verify project access
        project_id = chapter_data.get('project_id')
        project_data = await get_project(project_id)
        
        if not project_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        owner_id = project_data.get('metadata', {}).get('owner_id')
        collaborators = project_data.get('metadata', {}).get('collaborators', [])
        
        if owner_id != user_id and user_id not in collaborators:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this chapter"
            )
        
        # Calculate statistics
        metadata = chapter_data.get('metadata', {})
        versions = chapter_data.get('versions', [])
        quality_scores = chapter_data.get('quality_scores', {})
        
        stats = ChapterStatsResponse(
            word_count=metadata.get('word_count', 0),
            version_count=len(versions),
            latest_version=max([v.get('version_number', 0) for v in versions], default=0),
            quality_score=quality_scores.get('overall_rating', 0.0),
            generation_cost=metadata.get('cost_breakdown', {}).get('total_cost', 0.0),
            last_modified=metadata.get('updated_at', datetime.now(timezone.utc))
        )
        
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get statistics for chapter {chapter_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chapter statistics"
        ) 

# =====================================================================
# PROJECT-SPECIFIC CHAPTER ENDPOINTS
# =====================================================================

@router.get("/project/{project_id}/chapter/{chapter_number}", response_model=Chapter)
async def get_chapter_by_number(
    project_id: str,
    chapter_number: int,
    current_user: dict = Depends(get_current_user),
    version: Optional[int] = Query(None, description="Specific version to retrieve")
):
    """Get chapter by project ID and chapter number."""
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
        
        db = get_database_adapter()
        
        # Find chapter by project_id and chapter_number
        if db.use_firestore:
            chapters = await db.firestore.get_chapters_by_project(project_id)
            chapter_data = None
            for chapter in chapters:
                if chapter.get('metadata', {}).get('chapter_number') == chapter_number:
                    chapter_data = chapter
                    break
        else:
            # Mock implementation for local storage
            chapter_data = None
        
        if not chapter_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chapter {chapter_number} not found in project {project_id}"
            )
        
        # Get specific version if requested
        if version is not None:
            versions = chapter_data.get('versions', [])
            version_data = next((v for v in versions if v.get('version_number') == version), None)
            if not version_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Version {version} not found for chapter {chapter_number}"
                )
            chapter_data['content'] = version_data.get('content', '')
        
        return Chapter(**chapter_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get chapter {chapter_number} for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chapter"
        )

@router.put("/project/{project_id}/chapter/{chapter_number}", response_model=dict)
async def update_chapter_by_number(
    project_id: str,
    chapter_number: int,
    request: UpdateChapterRequest,
    current_user: dict = Depends(get_current_user)
):
    """Update chapter by project ID and chapter number."""
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
        
        db = get_database_adapter()
        
        # Find chapter by project_id and chapter_number
        if db.use_firestore:
            chapters = await db.firestore.get_chapters_by_project(project_id)
            chapter_data = None
            chapter_id = None
            for chapter in chapters:
                if chapter.get('metadata', {}).get('chapter_number') == chapter_number:
                    chapter_data = chapter
                    chapter_id = chapter.get('id')
                    break
        else:
            # Mock implementation for local storage
            chapter_data = None
            chapter_id = None
        
        if not chapter_data or not chapter_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chapter {chapter_number} not found in project {project_id}"
            )
        
        # Update chapter content
        update_data = {
            'content': request.content,
            'metadata': {
                **chapter_data.get('metadata', {}),
                'updated_at': datetime.now(timezone.utc),
                'updated_by': user_id,
                'word_count': len(request.content.split()) if request.content else 0
            }
        }
        
        if db.use_firestore:
            await db.firestore.update_chapter(chapter_id, update_data)
        
        logger.info(f"Updated chapter {chapter_number} in project {project_id}")
        
        return {
            "success": True,
            "message": f"Chapter {chapter_number} updated successfully",
            "chapter_number": chapter_number,
            "project_id": project_id,
            "word_count": update_data['metadata']['word_count']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update chapter {chapter_number} for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update chapter"
        ) 