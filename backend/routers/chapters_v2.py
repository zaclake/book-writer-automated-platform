#!/usr/bin/env python3
"""
Chapters API v2 - Firestore Integration with Versioning
Chapter management endpoints with full versioning support.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, status, Query

from backend.models.firestore_models import (
    Chapter, CreateChapterRequest, ChapterListResponse,
    ChapterVersion, QualityScores, ChapterStage
)
# Robust imports that work from both repo root and backend directory
try:
    from backend.database_integration import (
        get_project_chapters, create_chapter, get_project,
        track_usage, get_database_adapter, get_project_reference_files
    )
    from backend.auth_middleware import get_current_user
except ImportError:
    # Fallback when running from backend directory
    from database_integration import (
        get_project_chapters, create_chapter, get_project,
        track_usage, get_database_adapter, get_project_reference_files
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

class GenerateChapterRequest(BaseModel):
    """Request model for generating a new chapter with AI."""
    project_id: str
    chapter_number: int
    target_word_count: int = 2000
    stage: Optional[str] = "simple"  # simple, spike, complete, 5-stage

# =====================================================================
# AI CHAPTER GENERATION
# =====================================================================

@router.post("/generate", response_model=dict)
async def generate_chapter_simple(
    request: GenerateChapterRequest,
    current_user: dict = Depends(get_current_user)
):
    """Generate a new chapter using AI with reference-aware prompts."""
    try:
        logger.info(f"🚀 Chapter generation started - project: {request.project_id}, chapter: {request.chapter_number}")
        
        user_id = current_user.get('user_id')
        if not user_id:
            logger.error("❌ No user_id in current_user")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )
        
        logger.info(f"✅ User authenticated: {user_id}")
        
        # Verify user has access to the project
        try:
            logger.info(f"📁 Fetching project data for: {request.project_id}")
            project_data = await get_project(request.project_id)
        except Exception as e:
            logger.error(f"💥 Database error fetching project {request.project_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to access project data"
            )
            
        if not project_data:
            logger.error(f"❌ Project not found: {request.project_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        logger.info(f"✅ Project found: {request.project_id}")
        
        # Check project access
        owner_id = project_data.get('metadata', {}).get('owner_id')
        collaborators = project_data.get('metadata', {}).get('collaborators', [])
        
        if owner_id != user_id and user_id not in collaborators:
            logger.error(f"🚫 Access denied - user {user_id} not owner ({owner_id}) or collaborator")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )
        
        logger.info("✅ Project access verified")
        
        # Check OpenAI API key availability  
        try:
            logger.info("🤖 Checking AI service availability...")
            import os
            openai_api_key = os.getenv('OPENAI_API_KEY')
            if not openai_api_key:
                logger.error("❌ AI generation service not available - no OpenAI API key")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="AI generation service not available. Check OpenAI API configuration."
                )
            logger.info("✅ AI service available")
        except Exception as e:
            logger.error(f"💥 Failed to check AI service: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AI service check failed"
            )
        
        # =====================================================================
        # Get book bible and reference files for context
        # =====================================================================
        book_bible_content: str = ""
        references_content: dict[str, str] = {}

        try:
            logger.info("📖 Loading book bible and references...")

            # ------------------------------
            # Book bible retrieval
            # ------------------------------
            if 'files' in project_data and 'book-bible.md' in project_data['files']:
                book_bible_content = project_data['files']['book-bible.md']
            elif 'book_bible' in project_data:
                # Handle both legacy (string) and new (dict with content) formats
                bb_entry = project_data['book_bible']
                if isinstance(bb_entry, dict):
                    book_bible_content = bb_entry.get('content', '')
                elif isinstance(bb_entry, str):
                    book_bible_content = bb_entry

            # ------------------------------
            # Reference files retrieval
            # ------------------------------
            # 1. New schema (dict of references with nested content)
            if 'references' in project_data and isinstance(project_data['references'], dict):
                for ref_name, ref_val in project_data['references'].items():
                    if isinstance(ref_val, dict):
                        references_content[ref_name] = ref_val.get('content', '')
                    elif isinstance(ref_val, str):
                        references_content[ref_name] = ref_val

            # 2. Legacy in-document reference_files dict
            if not references_content and 'reference_files' in project_data:
                for ref_name, ref_content in project_data['reference_files'].items():
                    if ref_name.endswith('.md'):
                        references_content[ref_name] = ref_content

            # 3. If still empty, query database adapter for reference files collection
            if not references_content:
                try:
                    reference_docs = await get_project_reference_files(request.project_id)
                    for ref in reference_docs:
                        fname = ref.get('filename', 'unnamed.md')
                        references_content[fname] = ref.get('content', '')
                except Exception as ref_err:
                    logger.warning(f"⚠️ Failed to fetch reference files separately: {ref_err}")

            logger.info(f"✅ Loaded book bible ({len(book_bible_content)} chars) and {len(references_content)} references")

        except Exception as e:
            logger.warning(f"⚠️ Could not load full project context: {e}")
            # Continue with limited context
        
        # Build chapter generation context
        chapter_context = {
            'book_bible_content': book_bible_content,
            'references': references_content,
            'chapter_number': request.chapter_number,
            'target_word_count': request.target_word_count,
            'project_id': request.project_id
        }
        
        # Get previous chapters for context
        try:
            logger.info("📚 Loading previous chapters for context...")
            existing_chapters = await get_project_chapters(request.project_id)
            previous_chapters = [
                ch for ch in existing_chapters 
                if ch.get('chapter_number', 0) < request.chapter_number
            ]
            if previous_chapters:
                # Sort by chapter number and get summary of recent chapters
                previous_chapters.sort(key=lambda x: x.get('chapter_number', 0))
                recent_summaries = []
                for prev_ch in previous_chapters[-3:]:  # Last 3 chapters
                    content = prev_ch.get('content', '')
                    # Create brief summary (first 200 chars)
                    summary = content[:200] + "..." if len(content) > 200 else content
                    recent_summaries.append(f"Chapter {prev_ch.get('chapter_number')}: {summary}")
                chapter_context['previous_chapters_summary'] = "\n".join(recent_summaries)
                logger.info(f"✅ Loaded context from {len(previous_chapters)} previous chapters")
        except Exception as e:
            logger.warning(f"⚠️ Could not load previous chapters context: {e}")
            chapter_context['previous_chapters_summary'] = ""
        
        # Generate chapter content using AI
        try:
            logger.info(f"🎯 Starting AI generation for chapter {request.chapter_number}...")
            
            # Build the prompt
            prompt_template = """You are a professional novelist writing Chapter {chapter_number} for this book.

BOOK BIBLE:
{book_bible_content}

REFERENCE FILES:
{references_summary}

PREVIOUS CHAPTERS CONTEXT:
{previous_chapters_summary}

GENERATION REQUIREMENTS:
- Chapter Number: {chapter_number}
- Target Word Count: {target_word_count} words
- Genre: Based on book bible
- Maintain consistency with established characters, plot, and world-building
- Advance the plot meaningfully
- Create engaging, publishable-quality prose

Write Chapter {chapter_number} in full, ensuring it flows naturally from previous events and maintains the established tone and style. Include proper scene transitions and character development."""

            # Prepare references summary with length limits
            references_summary = ""
            total_ref_chars = 0
            max_total_ref_chars = 2000  # Limit total reference content
            
            for ref_name, ref_content in references_content.items():
                if total_ref_chars >= max_total_ref_chars:
                    break
                remaining_chars = max_total_ref_chars - total_ref_chars
                ref_excerpt = ref_content[:min(500, remaining_chars)]
                references_summary += f"\n--- {ref_name} ---\n{ref_excerpt}...\n"
                total_ref_chars += len(ref_excerpt)
            
            if not references_summary:
                references_summary = "No reference files available."
            
            # Limit book bible length to prevent token overflow
            max_bible_chars = 3000
            if book_bible_content and isinstance(book_bible_content, str):
                limited_book_bible = book_bible_content[:max_bible_chars] + ("..." if len(book_bible_content) > max_bible_chars else "")
            else:
                limited_book_bible = "No book bible available."
            
            # Format the prompt
            formatted_prompt = prompt_template.format(
                chapter_number=request.chapter_number,
                book_bible_content=limited_book_bible,
                references_summary=references_summary,
                previous_chapters_summary=chapter_context.get('previous_chapters_summary', 'No previous chapters.'),
                target_word_count=request.target_word_count
            )
            
            # Final safety check for prompt length (rough token estimate: 4 chars = 1 token)
            estimated_tokens = len(formatted_prompt) // 4
            max_prompt_tokens = 6000  # Leave room for response tokens
            
            if estimated_tokens > max_prompt_tokens:
                logger.warning(f"⚠️ Prompt too long ({estimated_tokens} tokens), truncating...")
                # Truncate the prompt to fit within limits
                max_chars = max_prompt_tokens * 4
                formatted_prompt = formatted_prompt[:max_chars] + "\n\n[Content truncated for length]"
            
            logger.info(f"📝 Prompt prepared ({len(formatted_prompt)} characters, ~{len(formatted_prompt)//4} tokens)")
            
            # Call OpenAI API with credits billing if enabled
            logger.info("🔗 Calling OpenAI API...")
            
            # Check if billing is enabled and use BillableClient
            enable_billing = os.getenv('ENABLE_CREDITS_BILLING', 'false').lower() == 'true'
            
            if enable_billing and user_id:
                try:
                    from backend.services.billable_client import BillableOpenAIClient
                    billable_client = BillableOpenAIClient(user_id)
                    
                    response, credits_charged = await billable_client.chat_completions_create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": "You are a professional novelist writing high-quality fiction chapters."},
                            {"role": "user", "content": formatted_prompt}
                        ],
                        temperature=0.7,
                        max_tokens=4000
                    )
                    
                    logger.info(f"✅ AI generation completed with billing! Credits charged: {credits_charged}")
                    
                except ImportError:
                    logger.warning("BillableClient not available, using regular OpenAI client")
                    import openai
                    client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
                    
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": "You are a professional novelist writing high-quality fiction chapters."},
                            {"role": "user", "content": formatted_prompt}
                        ],
                        temperature=0.7,
                        max_tokens=4000
                    )
            else:
                # Use regular OpenAI client (billing disabled or no user_id)
                import openai
                client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
                
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "You are a professional novelist writing high-quality fiction chapters."},
                        {"role": "user", "content": formatted_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=4000
                )
            
            generated_content = response.choices[0].message.content
            
            if not generated_content or len(generated_content.strip()) < 100:
                logger.error("❌ Generated content is too short or empty")
                raise Exception("Generated content is too short or empty")
            
            logger.info(f"✅ AI generation completed ({len(generated_content)} characters)")
                
            # Calculate costs and tokens (approximate)
            tokens_used = {
                'prompt': len(formatted_prompt) // 4,  # Rough estimate
                'completion': len(generated_content) // 4,
                'total': (len(formatted_prompt) + len(generated_content)) // 4
            }
            
            cost_breakdown = {
                'input_cost': tokens_used['prompt'] * 0.0001,  # Rough estimate
                'output_cost': tokens_used['completion'] * 0.0002,
                'total_cost': tokens_used['prompt'] * 0.0001 + tokens_used['completion'] * 0.0002
            }
            
        except Exception as e:
            logger.error(f"💥 AI generation failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Chapter generation failed: {str(e)}"
            )
        
        # Create chapter data structure for database
        logger.info("💾 Preparing chapter data for database...")
        chapter_data = {
            'project_id': request.project_id,
            'chapter_number': request.chapter_number,
            'content': generated_content,
            'title': f"Chapter {request.chapter_number}",
            'metadata': {
                'word_count': len(generated_content.split()),
                'target_word_count': request.target_word_count,
                'created_by': user_id,
                'stage': 'draft',
                'generation_time': 0.0,  # Could track actual time
                'retry_attempts': 0,
                'model_used': 'gpt-4o',
                'tokens_used': tokens_used,
                'cost_breakdown': cost_breakdown
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
                'content': generated_content,
                'timestamp': datetime.now(timezone.utc),
                'reason': 'ai_generation',
                'user_id': user_id,
                'changes_summary': f'AI-generated chapter using {request.stage} generation'
            }],
            'context_data': {
                'character_states': {},
                'plot_threads': [],
                'world_state': {},
                'timeline_position': None,
                'previous_chapter_summary': chapter_context.get('previous_chapters_summary', '')
            }
        }
        
        # Check if chapter already exists and update or create accordingly
        try:
            logger.info("💾 Checking if chapter exists and saving to database...")
            
            # Check if chapter already exists
            existing_chapters = await get_project_chapters(request.project_id)
            existing_chapter = None
            for ch in existing_chapters:
                if ch.get('chapter_number') == request.chapter_number:
                    existing_chapter = ch
                    break
            
            if existing_chapter:
                # Update existing chapter
                logger.info(f"📝 Updating existing chapter {request.chapter_number}...")
                chapter_id = existing_chapter.get('id')
                
                # Update the existing chapter with new content using dot notation for nested fields
                update_data = {
                    'content': generated_content,
                    'metadata.word_count': len(generated_content.split()),
                    'metadata.updated_at': datetime.now(timezone.utc),
                    'metadata.updated_by': user_id,
                    'metadata.model_used': 'gpt-4o',
                    'metadata.tokens_used': tokens_used,
                    'metadata.cost_breakdown': cost_breakdown,
                    'metadata.last_generation_reason': 'ai_rewrite'
                }
                
                # Add new version to versions array
                if 'versions' not in existing_chapter:
                    existing_chapter['versions'] = []
                
                new_version = {
                    'version_number': len(existing_chapter['versions']) + 1,
                    'content': generated_content,
                    'timestamp': datetime.now(timezone.utc),
                    'reason': 'ai_rewrite',
                    'user_id': user_id,
                    'changes_summary': f'AI rewrite using {request.stage} generation'
                }
                
                update_data['versions'] = existing_chapter['versions'] + [new_version]
                
                from backend.database_integration import get_database_adapter
                db = get_database_adapter()
                if db.use_firestore:
                    success = await db.firestore.update_chapter(chapter_id, update_data)
                    if not success:
                        raise Exception("Failed to update chapter")
                else:
                    success = True
                
                logger.info(f"✅ Chapter {request.chapter_number} updated successfully")
            else:
                # Create new chapter
                logger.info(f"🆕 Creating new chapter {request.chapter_number}...")
                chapter_id = await create_chapter(chapter_data, user_id)
                
                if not chapter_id:
                    raise Exception("Chapter creation returned invalid ID")
                    
                logger.info(f"✅ New chapter {request.chapter_number} created successfully")
                
        except Exception as e:
            logger.error(f"💥 Database error saving chapter: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save generated chapter to database"
            )
        
        logger.info(f"✅ Chapter saved with ID: {chapter_id}")
        
        # Track usage
        try:
            await track_usage(user_id, {
                'chapters_generated': 1,
                'words_generated': len(generated_content.split()),
                'ai_generations': 1,
                'tokens_used': tokens_used['total'],
                'generation_cost': cost_breakdown['total_cost']
            })
            logger.info("✅ Usage tracked")
        except Exception as e:
            logger.warning(f"⚠️ Failed to track usage for user {user_id}: {e}")
        
        logger.info(f"🎉 Chapter generation completed successfully!")
        
        return {
            'chapter_id': chapter_id,
            'content': generated_content,
            'message': 'Chapter generated successfully with AI',
            'word_count': len(generated_content.split()),
            'target_word_count': request.target_word_count,
            'generation_cost': cost_breakdown['total_cost'],
            'model_used': 'gpt-4o'
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions (they're already properly handled)
        raise
    except Exception as e:
        logger.error(f"💥 Unexpected error in chapter generation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chapter generation failed: {str(e)}"
        )

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
            chapters = await db.firestore.get_project_chapters(project_id)
            chapter_data = None
            for chapter in chapters:
                if chapter.get('chapter_number') == chapter_number:
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
        
        # Fix legacy data: convert invalid stage values to valid ones
        metadata = chapter_data.get('metadata', {})
        if metadata.get('stage') == 'ai_generated':
            metadata['stage'] = 'draft'
            chapter_data['metadata'] = metadata
        
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
            chapters = await db.firestore.get_project_chapters(project_id)
            chapter_data = None
            chapter_id = None
            for chapter in chapters:
                if chapter.get('chapter_number') == chapter_number:
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