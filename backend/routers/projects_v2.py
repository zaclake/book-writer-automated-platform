#!/usr/bin/env python3
"""
Projects API v2 - Firestore Integration
New project management endpoints using the commercial architecture.
"""

import logging
import html
import re
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from models.firestore_models import (
    Project, CreateProjectRequest, UpdateProjectRequest, 
    ProjectListResponse, ProjectMetadata, ProjectSettings,
    BookBible, ReferenceFile
)
from database_integration import (
    get_user_projects, create_project, get_project,
    migrate_project_from_filesystem, track_usage,
    get_database_adapter, create_reference_file
)
from auth_middleware import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v2/projects", tags=["projects-v2"])
security = HTTPBearer()

def _sanitize_text_for_markdown(text: str) -> str:
    """Sanitize user input for safe inclusion in markdown content."""
    if not text:
        return "[Not specified]"
    
    # HTML escape to prevent injection
    sanitized = html.escape(str(text).strip())
    
    # Remove/replace problematic markdown characters
    sanitized = re.sub(r'[#*`\[\](){}]', '', sanitized)
    
    # Limit length to prevent excessive content
    if len(sanitized) > 200:
        sanitized = sanitized[:200] + "..."
    
    return sanitized if sanitized else "[Not specified]"

def _validate_numeric_inputs(target_chapters: int, word_count_per_chapter: int) -> tuple[int, int]:
    """Validate and sanitize numeric inputs for series bible generation."""
    # Ensure reasonable bounds for chapter count
    safe_chapters = max(1, min(target_chapters, 100))
    
    # Ensure reasonable bounds for word count
    safe_word_count = max(500, min(word_count_per_chapter, 10000))
    
    return safe_chapters, safe_word_count

async def generate_series_bible(project_id: str, request: CreateProjectRequest, user_id: str):
    """Generate a series bible for multi-book projects."""
    try:
        # Get database adapter
        db = get_database_adapter()
        
        # Validate and sanitize inputs
        safe_title = _sanitize_text_for_markdown(request.title)
        safe_genre = _sanitize_text_for_markdown(request.genre)
        safe_chapters, safe_word_count = _validate_numeric_inputs(
            request.target_chapters, 
            request.word_count_per_chapter
        )
        
        # Create series bible content based on the project
        series_bible_content = f"""# Series Bible for {safe_title}

## Series Overview
This is a multi-book series in the {safe_genre} genre.

## World Building
- Setting: [To be expanded based on book bible content]
- Rules/Magic System: [To be defined]
- Timeline: [To be established]

## Character Arcs Across Books
- Main Character Development: [Track growth across series]
- Supporting Characters: [Roles in multiple books]
- Antagonists: [Series-wide conflicts]

## Continuity Tracking
- Plot threads that span multiple books
- Recurring locations and their evolution
- Technology/societal changes over time

## Book Structure
- Target books in series: {max(3, safe_chapters // 8)}
- Estimated chapters per book: {safe_chapters}
- Words per chapter target: {safe_word_count}

## Series Themes
[To be developed based on individual book themes]

## Publication Notes
- Target audience: General Fiction
- Genre consistency: {safe_genre}
- Writing style: Professional

---
Generated on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC
"""

        # Save series bible as a reference file
        reference_data = {
            'name': 'series-bible.md',
            'content': series_bible_content,
            'project_id': project_id,
            'created_by': user_id,
            'file_type': 'series_bible'
        }
        
        # Create the reference file
        try:
            result = await create_reference_file(reference_data)
            if result:
                logger.info(f"Successfully created series bible reference file for project {project_id}")
            else:
                logger.warning(f"Series bible reference file creation returned None for project {project_id}")
        except Exception as ref_error:
            logger.error(f"Failed to create series bible reference file: {ref_error}")
            # Don't fail the entire series bible generation for this
        
        logger.info(f"Generated series bible for project {project_id}")
        
    except Exception as e:
        logger.error(f"Failed to generate series bible: {e}")
        raise

# =====================================================================
# PROJECT CRUD OPERATIONS
# =====================================================================

@router.get("/", response_model=ProjectListResponse)
async def list_user_projects(
    current_user: dict = Depends(get_current_user)
):
    """Get all projects for the authenticated user."""
    try:
        user_id = current_user.get('sub')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )
        
        projects_data = await get_user_projects(user_id)
        
        # Convert to Pydantic models for validation
        projects = []
        for project_data in projects_data:
            try:
                project = Project(**project_data)
                projects.append(project)
            except Exception as e:
                logger.error(f"Failed to parse project data: {e}")
                # Skip malformed projects rather than failing the entire request
                continue
        
        return ProjectListResponse(
            projects=projects,
            total=len(projects)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list projects: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve projects"
        )

@router.post("/", response_model=dict)
async def create_new_project(
    request: CreateProjectRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create a new project for the authenticated user."""
    try:
        user_id = current_user.get('sub')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )
        
        # Create project data structure
        project_data = {
            'metadata': {
                'title': request.title,
                'owner_id': user_id,
                'collaborators': [],
                'status': 'active',
                'visibility': 'private'
            },
            'settings': {
                'genre': request.genre,
                'target_chapters': request.target_chapters,
                'word_count_per_chapter': request.word_count_per_chapter,
                'target_audience': 'General',
                'writing_style': 'Professional',
                'quality_gates_enabled': True,
                'auto_completion_enabled': False,
                'include_series_bible': request.include_series_bible
            }
        }
        
        # Add book bible if provided
        if request.book_bible_content:
            project_data['book_bible'] = {
                'content': request.book_bible_content,
                'last_modified': datetime.now(timezone.utc),
                'modified_by': user_id,
                'version': 1,
                'word_count': len(request.book_bible_content.split())
            }
        
        # Create the project
        project_id = await create_project(project_data)
        
        if not project_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create project"
            )
        
        # Generate series bible if requested
        if request.include_series_bible:
            try:
                await generate_series_bible(project_id, request, user_id)
            except Exception as e:
                logger.warning(f"Failed to generate series bible for project {project_id}: {e}")
                # Don't fail the project creation, just log the warning
        
        if not project_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create project"
            )
        
        # Track usage
        await track_usage(user_id, {
            'projects_created': 1,
            'api_calls': 1
        })
        
        return {
            'project': {
                'id': project_id,
                'title': request.title,
                'genre': request.genre,
                'status': 'active',
                'created_at': datetime.now().isoformat(),
                'settings': {
                    'target_chapters': request.target_chapters,
                    'word_count_per_chapter': request.word_count_per_chapter,
                    'genre': request.genre,
                    'include_series_bible': request.include_series_bible
                }
            },
            'message': 'Project created successfully'
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create project: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create project"
        )

@router.get("/{project_id}", response_model=Project)
async def get_project_details(
    project_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get detailed information about a specific project."""
    try:
        user_id = current_user.get('sub')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )
        
        # Get project data
        project_data = await get_project(project_id)
        
        if not project_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        # Verify user has access to this project
        owner_id = project_data.get('metadata', {}).get('owner_id')
        collaborators = project_data.get('metadata', {}).get('collaborators', [])
        
        if owner_id != user_id and user_id not in collaborators:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )
        
        # Convert to Pydantic model for validation
        project = Project(**project_data)
        
        return project
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve project"
        )

@router.put("/{project_id}", response_model=dict)
async def update_project(
    project_id: str,
    request: UpdateProjectRequest,
    current_user: dict = Depends(get_current_user)
):
    """Update an existing project."""
    try:
        user_id = current_user.get('sub')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )
        
        # Get current project to verify ownership
        project_data = await get_project(project_id)
        
        if not project_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        # Verify user is owner (only owners can update metadata/settings)
        owner_id = project_data.get('metadata', {}).get('owner_id')
        if owner_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only project owners can update project settings"
            )
        
        # Build update dictionary
        updates = {}
        
        if request.title:
            updates['metadata.title'] = request.title
        
        if request.status:
            updates['metadata.status'] = request.status.value
        
        if request.settings:
            # Update individual settings fields
            settings_dict = request.settings.dict()
            for key, value in settings_dict.items():
                updates[f'settings.{key}'] = value
        
        if request.book_bible_content:
            updates.update({
                'book_bible.content': request.book_bible_content,
                'book_bible.last_modified': datetime.now(timezone.utc),
                'book_bible.modified_by': user_id,
                'book_bible.word_count': len(request.book_bible_content.split())
            })
        
        # Perform the update
        from database_integration import get_database_adapter
        db = get_database_adapter()
        success = await db.firestore.update_project(project_id, updates) if db.use_firestore else True
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update project"
            )
        
        return {
            'message': 'Project updated successfully'
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update project"
        )

# =====================================================================
# MIGRATION ENDPOINTS
# =====================================================================

@router.post("/migrate", response_model=dict)
async def migrate_filesystem_project(
    project_path: str,
    current_user: dict = Depends(get_current_user)
):
    """Migrate an existing filesystem project to Firestore."""
    try:
        user_id = current_user.get('sub')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )
        
        # Migrate the project
        project_id = await migrate_project_from_filesystem(project_path, user_id)
        
        if not project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to migrate project. Check project path and structure."
            )
        
        return {
            'project_id': project_id,
            'message': 'Project migrated successfully'
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to migrate project: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to migrate project"
        )

# =====================================================================
# COLLABORATION ENDPOINTS
# =====================================================================

@router.post("/{project_id}/collaborators", response_model=dict)
async def add_collaborator(
    project_id: str,
    collaborator_email: str,
    current_user: dict = Depends(get_current_user)
):
    """Add a collaborator to a project."""
    try:
        user_id = current_user.get('sub')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )
        
        # Get project to verify ownership
        project_data = await get_project(project_id)
        
        if not project_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        # Verify user is owner
        owner_id = project_data.get('metadata', {}).get('owner_id')
        if owner_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only project owners can add collaborators"
            )
        
        # TODO: Implement user lookup by email to get Clerk user ID
        # For now, we'll assume the collaborator_email is actually a user ID
        collaborator_user_id = collaborator_email
        
        # Add to collaborators list
        current_collaborators = project_data.get('metadata', {}).get('collaborators', [])
        if collaborator_user_id not in current_collaborators:
            current_collaborators.append(collaborator_user_id)
            
            # Update project
            from database_integration import get_database_adapter
            db = get_database_adapter()
            success = await db.firestore.update_project(
                project_id, 
                {'metadata.collaborators': current_collaborators}
            ) if db.use_firestore else True
            
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to add collaborator"
                )
        
        return {
            'message': 'Collaborator added successfully'
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add collaborator: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add collaborator"
        ) 