#!/usr/bin/env python3
"""
Projects API v2 - Firestore Integration
New project management endpoints using the commercial architecture.
"""

import logging
import html
import re
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pathlib import Path

import asyncio
import time

from backend.models.firestore_models import (
    Project, CreateProjectRequest, UpdateProjectRequest,
    ProjectListResponse, ProjectMetadata, ProjectSettings,
    BookBible, ReferenceFile, BookLengthTier
)
# Robust imports that work from both repo root and backend directory
try:
    from backend.database_integration import (
        get_user_projects, create_project, get_project,
        migrate_project_from_filesystem, track_usage,
        get_database_adapter, create_reference_file
    )
    from backend.auth_middleware import get_current_user
except ImportError:
    # Fallback when running from backend directory
    from backend.database_integration import (
        get_user_projects, create_project, get_project,
        migrate_project_from_filesystem, track_usage,
        get_database_adapter, create_reference_file
    )
    from backend.auth_middleware import get_current_user

# Simple in-memory progress store for reference generation jobs
_reference_jobs: Dict[str, Dict[str, Any]] = {}

def _update_reference_job_progress(job_id: str, progress: int, stage: str, message: str = ""):
    """Update progress for a reference generation job."""
    # Determine status based on stage and progress
    if stage.lower() == "failed":
        status = 'failed-rate-limit'
    elif progress >= 100:
        status = 'completed'
    else:
        status = 'running'
    
    _reference_jobs[job_id] = {
        'id': job_id,
        'status': status,
        'progress': progress,
        'stage': stage,
        'message': message,
        'updated_at': time.time()
    }

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v2/projects", tags=["projects-v2"])
security = HTTPBearer()

async def generate_references_background(
    project_id: str,
    book_bible_content: str,
    include_series_bible: bool,
    user_id: str
):
    """Generate reference files in the background after project creation."""
    job_id = f"ref_gen_{project_id}_{int(time.time())}"
    
    try:
        logger.info(f"Starting background reference generation for project {project_id}")
        _update_reference_job_progress(job_id, 0, "Initializing", "Starting reference generation...")
        
        from utils.reference_content_generator import ReferenceContentGenerator
        from utils.paths import get_project_workspace
        
        generator = ReferenceContentGenerator()
        if not generator.is_available():
            logger.warning(f"Reference generator not available for project {project_id}")
            _update_reference_job_progress(job_id, 0, "Failed", "AI service not available")
            return
        
        _update_reference_job_progress(job_id, 10, "Preparing", "Setting up workspace...")
        
        project_workspace = get_project_workspace(project_id)
        references_dir = project_workspace / "references"
        
        # Generate default reference files with explicit arguments
        _update_reference_job_progress(job_id, 20, "Generating", "Creating reference files...")
        
        results = await asyncio.get_event_loop().run_in_executor(
            None,
            generator.generate_all_references,
            book_bible_content,      # book_bible_content
            references_dir,          # references_dir  
            None                     # reference_types (use defaults)
        )
        
        _update_reference_job_progress(job_id, 60, "Processing", f"Generated {len(results)} reference files")
        logger.info(f"Generated {len(results)} reference files for project {project_id}")
        
        # Store reference file content in Firestore by reading from generated files
        _update_reference_job_progress(job_id, 70, "Storing", "Saving files to database...")
        
        stored_count = 0
        for ref_type, metadata in results.items():
            if metadata and metadata.get('success'):
                try:
                    # Read the actual markdown content from the generated file
                    file_path = Path(metadata["file_path"])
                    if file_path.exists():
                        markdown_content = file_path.read_text(encoding="utf-8")
                        await create_reference_file(
                            project_id=project_id,
                            filename=metadata["filename"],
                            content=markdown_content,  # Pass actual markdown content, not metadata dict
                            user_id=user_id
                        )
                        stored_count += 1
                        logger.info(f"Successfully stored reference file {metadata['filename']} for project {project_id}")
                    else:
                        logger.error(f"Generated file not found: {file_path}")
                except Exception as e:
                    logger.error(f"Failed to store reference file {ref_type} for project {project_id}: {e}")
            else:
                logger.warning(f"Reference generation failed for {ref_type}: {metadata.get('error', 'Unknown error')}")
        
        # Check if we had any successful generations
        if stored_count > 0:
            _update_reference_job_progress(job_id, 100, "Complete", f"Successfully generated {stored_count} reference files")
            logger.info(f"Successfully generated and stored {stored_count} reference files for project {project_id}")
        else:
            # All reference generations failed - mark as failed instead of complete
            _update_reference_job_progress(job_id, 0, "Failed", "All reference file generations failed due to rate limits")
            logger.error(f"Failed to generate any reference files for project {project_id} - likely rate limit issues")
        
        # Store the job_id in the project for later reference
        _reference_jobs[project_id] = _reference_jobs[job_id]  # Also store by project_id for lookup
        
    except Exception as e:
        logger.error(f"Background reference generation failed for project {project_id}: {e}")
        _update_reference_job_progress(job_id, 0, "Failed", f"Error: {str(e)}")

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
            result = await create_reference_file(
                project_id=project_id,
                filename=reference_data['name'],
                content=reference_data['content'],
                user_id=reference_data['created_by']
            )
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
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )
        
        projects_data = await get_user_projects(user_id)
        
        # Debug logging to trace title issue
        logger.info(f"Retrieved {len(projects_data)} projects for user {user_id}")
        for i, project in enumerate(projects_data[:3]):  # Log first 3 projects
            title = project.get('metadata', {}).get('title', 'NO_TITLE')
            project_id = project.get('id', 'NO_ID')
            logger.info(f"Project {i}: id={project_id}, title='{title}'")
        
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
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Create a new project for the authenticated user."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )
        
        # Validate title is not empty
        if not request.title or not request.title.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Project title cannot be empty"
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
            # Try to expand content with OpenAI if source data is available
            final_content = request.book_bible_content
            if request.source_data and request.creation_mode in ['quickstart', 'guided']:
                try:
                    # Check if OpenAI expansion is enabled
                    import os
                    openai_enabled = os.getenv('ENABLE_OPENAI_EXPANSION', 'true').lower() == 'true'
                    
                    if openai_enabled:
                        from utils.reference_content_generator import ReferenceContentGenerator
                        from models.firestore_models import BookBible
                        
                        generator = ReferenceContentGenerator()
                        if generator.is_available():
                            logger.info(f"Expanding {request.creation_mode} content with OpenAI for project")
                            
                            # Get book length specs
                            if request.book_length_tier:
                                try:
                                    tier_enum = BookLengthTier(request.book_length_tier)
                                    book_specs = BookBible.get_book_length_specs(tier_enum)
                                except ValueError:
                                    # Fallback if invalid tier
                                    book_specs = {
                                        'chapter_count_target': request.target_chapters,
                                        'word_count_target': request.target_word_count or 75000,
                                        'avg_words_per_chapter': request.word_count_per_chapter
                                    }
                            else:
                                # Default specs
                                book_specs = {
                                    'chapter_count_target': request.target_chapters,
                                    'word_count_target': request.target_word_count or 75000,
                                    'avg_words_per_chapter': request.word_count_per_chapter
                                }
                            
                            # Expand the content
                            expanded_content = generator.expand_book_bible(
                                source_data=request.source_data,
                                creation_mode=request.creation_mode,
                                book_specs=book_specs
                            )
                            
                            if expanded_content and len(expanded_content) > len(final_content):
                                final_content = expanded_content
                                logger.info(f"Successfully expanded book bible from {len(request.book_bible_content)} to {len(expanded_content)} characters")
                            else:
                                logger.warning("OpenAI expansion failed or produced shorter content, using original")
                        else:
                            logger.info("OpenAI not available, using template content")
                    else:
                        logger.info("OpenAI expansion disabled via ENABLE_OPENAI_EXPANSION=false")
                        
                except Exception as e:
                    logger.warning(f"Failed to expand book bible content with OpenAI: {e}, using template content")
                    # Continue with original content if expansion fails
            
            project_data['book_bible'] = {
                'content': final_content,
                'must_include_sections': request.must_include_sections,
                'book_length_tier': request.book_length_tier,
                'estimated_chapters': request.estimated_chapters or request.target_chapters,
                'target_word_count': request.target_word_count,
                'last_modified': datetime.now(timezone.utc),
                'modified_by': user_id,
                'version': 1,
                'word_count': len(final_content.split()),
                'creation_mode': request.creation_mode,
                'source_data': request.source_data,
                'ai_expanded': final_content != request.book_bible_content
            }
        
        # Create the project
        project_id = await create_project(project_data)
        
        if not project_id:
            logger.error(f"Project creation failed", extra={
                'user_id': user_id,
                'title': request.title,
                'genre': request.genre,
                'creation_mode': request.creation_mode,
                'book_length_tier': request.book_length_tier
            })
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create project"
            )
        
        logger.info(f"Project created successfully", extra={
            'project_id': project_id,
            'user_id': user_id,
            'title': request.title,
            'genre': request.genre,
            'creation_mode': request.creation_mode,
            'book_length_tier': request.book_length_tier,
            'target_chapters': request.target_chapters,
            'word_count_per_chapter': request.word_count_per_chapter,
            'include_series_bible': request.include_series_bible,
            'book_bible_length': len(request.book_bible_content) if request.book_bible_content else 0,
            'must_include_sections_count': len(request.must_include_sections)
        })
        
        # Generate series bible if requested
        if request.include_series_bible:
            try:
                await generate_series_bible(project_id, request, user_id)
            except Exception as e:
                logger.warning(f"Failed to generate series bible for project {project_id}: {e}")
                # Don't fail the project creation, just log the warning

        # Start reference generation in background (non-blocking)
        references_generated = False
        reference_files = []
        
        try:
            from utils.reference_content_generator import ReferenceContentGenerator
            
            generator = ReferenceContentGenerator()
            if generator.is_available() and request.book_bible_content:
                logger.info(f"Scheduling background reference generation for project {project_id}")
                
                # Start reference generation in background
                background_tasks.add_task(
                    generate_references_background,
                    project_id,
                    request.book_bible_content,
                    request.include_series_bible,
                    user_id
                )
                
                # References will be generated in background
                references_generated = True  # Indicates generation was scheduled
                logger.info(f"Background reference generation scheduled for project {project_id}")
            else:
                logger.info(f"Skipping reference generation for project {project_id} - OpenAI not available or no book bible")
                        
        except Exception as e:
            logger.error(f"Failed to schedule reference generation for project {project_id}: {e}")
            # Don't fail the project creation, just log the error
            references_generated = False
        
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
                # Note: book_bible.source_data not included in response for privacy
            },
            'references_generated': references_generated,
            'reference_files': reference_files,
            'message': 'Project created successfully' + (' - references generating in background' if references_generated else '')
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create project: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create project"
        )

@router.post("/{project_id}/references/generate")
async def generate_project_references(
    project_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Generate or regenerate reference files for a project."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )
        
        # Get project to verify ownership and get book bible content
        project = await get_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        # Check if user owns this project
        if project.get('metadata', {}).get('owner_id') != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        # Get book bible content
        book_bible = project.get('book_bible', {})
        book_bible_content = book_bible.get('content')
        if not book_bible_content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No book bible content found for this project"
            )
        
        # Generate references
        from utils.reference_content_generator import ReferenceContentGenerator
        from utils.paths import get_project_workspace
        import asyncio
        
        generator = ReferenceContentGenerator()
        if not generator.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI content generation service not available"
            )
        
        project_workspace = get_project_workspace(project_id)
        references_dir = project_workspace / "references"
        
        logger.info(f"Generating references for project {project_id}")
        
        # Run generation in executor to avoid blocking
        results = await asyncio.get_event_loop().run_in_executor(
            None,
            generator.generate_all_references,
            book_bible_content,
            references_dir,
            None  # reference_types (use defaults)
        )
        
        # Store reference file content in Firestore by reading from generated files
        generated_files = []
        for ref_type, metadata in results.items():
            if metadata and metadata.get('success'):
                try:
                    # Read the actual markdown content from the generated file
                    file_path = Path(metadata["file_path"])
                    if file_path.exists():
                        markdown_content = file_path.read_text(encoding="utf-8")
                        await create_reference_file(
                            project_id=project_id,
                            filename=metadata["filename"],
                            content=markdown_content,  # Pass actual markdown content, not metadata dict
                            user_id=user_id
                        )
                        generated_files.append({
                            'type': ref_type,
                            'filename': metadata["filename"],
                            'size': len(markdown_content)
                        })
                        logger.info(f"Successfully stored reference file {metadata['filename']} for project {project_id}")
                    else:
                        logger.error(f"Generated file not found: {file_path}")
                except Exception as e:
                    logger.error(f"Failed to store reference file {ref_type} for project {project_id}: {e}")
            else:
                logger.warning(f"Reference generation failed for {ref_type}: {metadata.get('error', 'Unknown error')}")
        
        logger.info(f"Generated {len(generated_files)} reference files for project {project_id}")
        
        return {
            'success': True,
            'message': f'Generated {len(generated_files)} reference files',
            'files': generated_files
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate references for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate reference files"
        )

@router.get("/{project_id}", response_model=Project)
async def get_project_details(
    project_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get detailed information about a specific project."""
    try:
        user_id = current_user.get('user_id')
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
        user_id = current_user.get('user_id')
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
        from backend.database_integration import get_database_adapter
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

@router.delete("/{project_id}", response_model=dict)
async def delete_project(
    project_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a project and all its associated data."""
    try:
        user_id = current_user.get('user_id')
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
        
        # Verify user is owner (only owners can delete projects)
        owner_id = project_data.get('metadata', {}).get('owner_id')
        if owner_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only project owners can delete projects"
            )
        
        # Get database adapter
        from backend.database_integration import get_database_adapter
        db = get_database_adapter()
        
        logger.info(f"Starting deletion of project {project_id} for user {user_id}")
        logger.info(f"Database adapter using Firestore: {db.use_firestore}")
        
        # Delete project from database
        if db.use_firestore:
            logger.info(f"Attempting Firestore deletion for project {project_id}")
            # Delete all associated data (references, chapters, etc.)
            # This should be a cascading delete in Firestore
            try:
                success = await db.firestore.delete_project(project_id)
                logger.info(f"Firestore delete_project returned: {success}")
            except Exception as e:
                logger.error(f"Firestore deletion failed for project {project_id}: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Database deletion failed: {str(e)}"
                )
        else:
            logger.info(f"Using local storage deletion for project {project_id}")
            # For local storage, remove project directory
            from utils.paths import get_project_workspace
            import shutil
            
            project_workspace = get_project_workspace(project_id)
            if project_workspace.exists():
                shutil.rmtree(project_workspace)
                logger.info(f"Removed local project directory: {project_workspace}")
            success = True
        
        if not success:
            logger.error(f"Project deletion returned false for project {project_id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete project"
            )
        
        logger.info(f"Project {project_id} deletion completed successfully")
        
        # Clean up any reference generation jobs
        if project_id in _reference_jobs:
            del _reference_jobs[project_id]
        
        # Track usage
        await track_usage(user_id, {
            'projects_deleted': 1,
            'api_calls': 1
        })
        
        logger.info(f"Successfully deleted project {project_id} for user {user_id}")
        
        return {
            'message': 'Project deleted successfully',
            'deleted_project_id': project_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete project"
        )

# Add this endpoint after the existing project endpoints, before the migration section

@router.get("/{project_id}/chapters", response_model=dict)
async def get_project_chapters(
    project_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get all chapters for a specific project."""
    try:
        user_id = current_user.get('user_id')
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
        
        # Verify user is owner or collaborator
        owner_id = project_data.get('metadata', {}).get('owner_id')
        collaborators = project_data.get('metadata', {}).get('collaborators', [])
        if owner_id != user_id and user_id not in collaborators:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )
        
        # Get database adapter
        from backend.database_integration import get_database_adapter
        db = get_database_adapter()
        
        # Get chapters using the database adapter
        chapters_data = await db.get_project_chapters(project_id)
        
        logger.info(f"Retrieved {len(chapters_data)} chapters for project {project_id}")
        
        return {
            'chapters': chapters_data,
            'total': len(chapters_data),
            'project_id': project_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get chapters for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chapters"
        )

@router.get("/{project_id}/references/progress")
async def get_reference_generation_progress(
    project_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get progress of reference file generation for a project."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )
        
        # Get project to verify ownership
        project = await get_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        # Check if user owns this project or is a collaborator
        owner_id = project.get('metadata', {}).get('owner_id')
        collaborators = project.get('metadata', {}).get('collaborators', [])
        
        if owner_id != user_id and user_id not in collaborators:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )
        
        # Look for reference generation job progress
        job_progress = _reference_jobs.get(project_id)
        
        if not job_progress:
            # Check if references already exist (generation might be complete)
            from backend.database_integration import get_database_adapter
            db = get_database_adapter()
            reference_files = await db.firestore.get_project_reference_files(project_id)
            
            if reference_files and len(reference_files) > 0:
                # References exist, generation must be complete
                return {
                    'status': 'completed',
                    'progress': 100,
                    'stage': 'Complete',
                    'message': f'{len(reference_files)} reference files available',
                    'completed': True
                }
            else:
                # No progress found and no references - might not have started
                return {
                    'status': 'not_started',
                    'progress': 0,
                    'stage': 'Not Started',
                    'message': 'Reference generation has not started',
                    'completed': False
                }
        
        # Return current progress
        return {
            'status': job_progress['status'],
            'progress': job_progress['progress'],
            'stage': job_progress['stage'],
            'message': job_progress['message'],
            'completed': job_progress['status'] == 'completed',
            'updated_at': job_progress['updated_at']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get reference generation progress for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve progress"
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
        user_id = current_user.get('user_id')
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
# REFERENCE FILES ENDPOINTS
# =====================================================================

@router.get("/{project_id}/references")
async def get_project_references(
    project_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get all reference files for a project."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )
        
        # Get project to verify ownership
        project = await get_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        # Check if user owns this project or is a collaborator
        owner_id = project.get('metadata', {}).get('owner_id')
        collaborators = project.get('metadata', {}).get('collaborators', [])
        
        if owner_id != user_id and user_id not in collaborators:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )
        
        # Get reference files
        from backend.database_integration import get_database_adapter
        db = get_database_adapter()
        reference_files = await db.firestore.get_project_reference_files(project_id)
        
        return {
            'success': True,
            'project_id': project_id,
            'files': reference_files,
            'total': len(reference_files)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get reference files for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve reference files"
        )


@router.get("/{project_id}/references/{filename}")
async def get_reference_file(
    project_id: str,
    filename: str,
    current_user: dict = Depends(get_current_user)
):
    """Get a specific reference file by filename."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )
        
        # Get project to verify ownership
        project = await get_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        # Check if user owns this project or is a collaborator
        owner_id = project.get('metadata', {}).get('owner_id')
        collaborators = project.get('metadata', {}).get('collaborators', [])
        
        if owner_id != user_id and user_id not in collaborators:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )
        
        # Get reference files and find the specific one
        from backend.database_integration import get_database_adapter
        db = get_database_adapter()
        reference_files = await db.firestore.get_project_reference_files(project_id)
        
        # Find the file by filename
        target_file = None
        for ref_file in reference_files:
            if ref_file.get('filename') == filename:
                target_file = ref_file
                break
        
        if not target_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reference file '{filename}' not found"
            )
        
        return {
            'success': True,
            'name': target_file.get('filename'),
            'content': target_file.get('content', ''),
            'lastModified': target_file.get('updated_at', target_file.get('created_at')),
            'size': target_file.get('size', len(target_file.get('content', ''))),
            'metadata': target_file.get('metadata', {})
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get reference file {filename} for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve reference file"
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
        user_id = current_user.get('user_id')
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
            from backend.database_integration import get_database_adapter
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
        
    except Exception as e:
        logger.error(f"Failed to add collaborator to project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add collaborator"
        )

@router.post("/expand-book-bible")
async def expand_book_bible_content(
    request: dict,
    current_user: dict = Depends(get_current_user)
):
    """Expand QuickStart or Guided wizard data into comprehensive book bible."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )
        
        # Validate request data
        source_data = request.get('source_data')
        creation_mode = request.get('creation_mode')
        book_specs = request.get('book_specs', {})
        
        if not source_data or not creation_mode:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="source_data and creation_mode are required"
            )
        
        if creation_mode not in ['quickstart', 'guided']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="creation_mode must be 'quickstart' or 'guided'"
            )
        
        # Check if OpenAI expansion is enabled
        import os
        openai_enabled = os.getenv('ENABLE_OPENAI_EXPANSION', 'true').lower() == 'true'
        
        if not openai_enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OpenAI expansion is disabled via environment configuration."
            )
        
        # Initialize content generator
        from utils.reference_content_generator import ReferenceContentGenerator
        generator = ReferenceContentGenerator()
        
        if not generator.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OpenAI service is not available. Check API key configuration."
            )
        
        logger.info(f"Expanding book bible content", extra={
            'user_id': user_id,
            'creation_mode': creation_mode,
            'source_data_keys': list(source_data.keys()) if isinstance(source_data, dict) else 'not_dict'
            # Note: source_data values intentionally omitted from logs for privacy
        })
        
        # Set default book specs if not provided
        default_specs = {
            'chapter_count_target': book_specs.get('target_chapters', 25),
            'word_count_target': book_specs.get('target_word_count', 75000),
            'avg_words_per_chapter': book_specs.get('word_count_per_chapter', 3000)
        }
        
        # Expand the content
        import time
        start_time = time.time()
        
        expanded_content = generator.expand_book_bible(
            source_data=source_data,
            creation_mode=creation_mode,
            book_specs=default_specs
        )
        
        expansion_time = time.time() - start_time
        word_count = len(expanded_content.split()) if expanded_content else 0
        
        logger.info(f"Successfully expanded book bible content", extra={
            'user_id': user_id,
            'creation_mode': creation_mode,
            'expansion_time': expansion_time,
            'output_length': len(expanded_content) if expanded_content else 0,
            'word_count': word_count
            # Note: source_data intentionally omitted from logs for privacy
        })
        
        return {
            'success': True,
            'expanded_content': expanded_content,
            'expansion_time': expansion_time,
            'word_count': word_count,
            'metadata': {
                'creation_mode': creation_mode,
                'book_specs': default_specs,
                'ai_generated': True,
                'generated_at': datetime.now(timezone.utc).isoformat()
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to expand book bible content: {e}", extra={
            'user_id': current_user.get('user_id'),
            'creation_mode': request.get('creation_mode'),
            'error': str(e)
        })
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to expand book bible content"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add collaborator: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add collaborator"
        ) 