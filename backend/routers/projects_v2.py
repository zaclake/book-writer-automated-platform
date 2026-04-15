#!/usr/bin/env python3
"""
Projects API v2 - Firestore Integration
New project management endpoints using the commercial architecture.
"""

import logging
import os
import time
import html
import re
import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pathlib import Path
from pydantic import BaseModel
try:
    from google.cloud.firestore_v1.base_query import FieldFilter
except Exception:
    FieldFilter = None

import asyncio
import time

# Models import with robust fallback to support /app runtime without backend package
try:
    from backend.models.firestore_models import (
        Project, CreateProjectRequest, UpdateProjectRequest,
        ProjectListResponse, ProjectMetadata, ProjectSettings,
        BookBible, ReferenceFile, BookLengthTier
    )
except Exception:
    from models.firestore_models import (
        Project, CreateProjectRequest, UpdateProjectRequest,
        ProjectListResponse, ProjectMetadata, ProjectSettings,
        BookBible, ReferenceFile, BookLengthTier
    )
"""Robust imports that work from repo root and backend directory."""
logger = logging.getLogger(__name__)

_PROJECT_RESOLVE_LOGS: dict[str, float] = {}
_PROJECT_RESOLVE_THROTTLE_SECONDS = max(
    1, int(os.getenv("PROJECT_RESOLVE_LOG_THROTTLE_SEC", "300"))
)
_PROJECT_RESOLVE_LOG_ENABLED = os.getenv("LOG_PROJECT_RESOLVED", "false").strip().lower() == "true"

def _should_log_project_resolved(project_id: str) -> bool:
    now = time.time()
    last = _PROJECT_RESOLVE_LOGS.get(project_id, 0.0)
    if now - last < _PROJECT_RESOLVE_THROTTLE_SECONDS:
        return False
    _PROJECT_RESOLVE_LOGS[project_id] = now
    return True

try:
    from backend.database_integration import (
        get_user_projects, create_project, get_project,
        migrate_project_from_filesystem, track_usage,
        get_database_adapter, create_reference_file, update_reference_file,
        get_project_chapters, get_project_reference_files, list_story_notes
    )
    from backend.auth_middleware import get_current_user
except Exception:
    try:
        # Fallback when running from backend/ directory
        from database_integration import (
            get_user_projects, create_project, get_project,
            migrate_project_from_filesystem, track_usage,
            get_database_adapter, create_reference_file, update_reference_file,
            get_project_chapters, get_project_reference_files, list_story_notes
        )
        from auth_middleware import get_current_user
    except Exception:
        from ..database_integration import (
            get_user_projects, create_project, get_project,
            migrate_project_from_filesystem, track_usage,
            get_database_adapter, create_reference_file, update_reference_file,
            get_project_chapters, get_project_reference_files, list_story_notes
        )
        from ..auth_middleware import get_current_user

# Optional services - allow router to load even if dependencies are missing
VectorStoreService = None
TitleRecommendationService = None
apply_steering_update = None
create_canon_log_entry = None
rewrite_chapter_for_canon = None
_VECTOR_STORE_UNAVAILABLE_LOGGED = False
try:
    try:
        from backend.services.vector_store_service import VectorStoreService as _VectorStoreService
    except Exception:
        from services.vector_store_service import VectorStoreService as _VectorStoreService
    VectorStoreService = _VectorStoreService
except Exception as _svc_err:
    logger.warning(f"Vector store service unavailable; memory indexing disabled: {_svc_err}")

try:
    try:
        from backend.services.steering_service import (
            apply_steering_update as _apply_steering_update,
            create_canon_log_entry as _create_canon_log_entry,
            rewrite_chapter_for_canon as _rewrite_chapter_for_canon
        )
    except Exception:
        from services.steering_service import (
            apply_steering_update as _apply_steering_update,
            create_canon_log_entry as _create_canon_log_entry,
            rewrite_chapter_for_canon as _rewrite_chapter_for_canon
        )
    apply_steering_update = _apply_steering_update
    create_canon_log_entry = _create_canon_log_entry
    rewrite_chapter_for_canon = _rewrite_chapter_for_canon
except Exception as _svc_err:
    logger.warning(f"Steering service unavailable; canon log endpoints disabled: {_svc_err}")

try:
    try:
        from backend.services.title_recommendation_service import TitleRecommendationService as _TitleRecommendationService
    except Exception:
        from services.title_recommendation_service import TitleRecommendationService as _TitleRecommendationService
    TitleRecommendationService = _TitleRecommendationService
except Exception as _svc_err:
    logger.warning(f"Title recommendation service unavailable: {_svc_err}")

def require_vector_store_service():
    if VectorStoreService is None:
        raise HTTPException(status_code=503, detail="Vector store service unavailable")
    service = VectorStoreService()
    if not getattr(service, "available", True):
        raise HTTPException(status_code=503, detail="Vector store service unavailable")
    return service

def get_vector_store_service_optional():
    global _VECTOR_STORE_UNAVAILABLE_LOGGED
    if VectorStoreService is None:
        if not _VECTOR_STORE_UNAVAILABLE_LOGGED:
            logger.info("Vector store service unavailable; skipping indexing.")
            _VECTOR_STORE_UNAVAILABLE_LOGGED = True
        return None
    try:
        service = VectorStoreService()
    except Exception as exc:
        if not _VECTOR_STORE_UNAVAILABLE_LOGGED:
            logger.info(f"Vector store service unavailable; skipping indexing: {exc}")
            _VECTOR_STORE_UNAVAILABLE_LOGGED = True
        return None
    if not getattr(service, "available", True):
        if not _VECTOR_STORE_UNAVAILABLE_LOGGED:
            reason = getattr(service, "unavailable_reason", None)
            if reason:
                logger.info(f"Vector store service disabled; skipping indexing: {reason}")
            else:
                logger.info("Vector store service disabled; skipping indexing.")
            _VECTOR_STORE_UNAVAILABLE_LOGGED = True
        return None
    return service

def require_title_service(user_id: str):
    if TitleRecommendationService is None:
        raise HTTPException(status_code=503, detail="Title recommendation service unavailable")
    return TitleRecommendationService(user_id=user_id)

def _steering_unavailable(*args, **kwargs):
    raise HTTPException(status_code=503, detail="Steering service unavailable")

if apply_steering_update is None:
    apply_steering_update = _steering_unavailable
if create_canon_log_entry is None:
    create_canon_log_entry = _steering_unavailable
if rewrite_chapter_for_canon is None:
    rewrite_chapter_for_canon = _steering_unavailable

# Cover art service is optional; guard import/initialization to avoid breaking v2 router
CoverArtService = None
CoverArtJob = None
try:
    try:
        from backend.services.cover_art_service import CoverArtService as _CoverArtService, CoverArtJob as _CoverArtJob
    except ImportError:
        from services.cover_art_service import CoverArtService as _CoverArtService, CoverArtJob as _CoverArtJob
    CoverArtService = _CoverArtService
    CoverArtJob = _CoverArtJob
except Exception as _cover_art_import_err:
    logger = logging.getLogger(__name__)
    logger.warning(f"CoverArtService unavailable; cover-art endpoints will be disabled: {_cover_art_import_err}")

# Simple in-memory progress store for reference generation jobs
_reference_jobs: Dict[str, Dict[str, Any]] = {}

# Simple in-memory store for cover art jobs
# Use Any to avoid type errors when CoverArtJob is not available
_cover_art_jobs: Dict[str, Any] = {}

# Initialize cover art service if available; otherwise leave as None
try:
    cover_art_service = CoverArtService() if CoverArtService else None
except Exception as _svc_err:
    logger = logging.getLogger(__name__)
    logger.warning(f"Failed to initialize CoverArtService; disabling cover-art endpoints: {_svc_err}")
    cover_art_service = None

class CoverArtRequest(BaseModel):
    """Request model for cover art generation."""
    user_feedback: Optional[str] = None
    regenerate: bool = False
    options: Optional[Dict[str, Any]] = None
    requirements: Optional[str] = None


class TitleRecommendationRequest(BaseModel):
    """Request model for title recommendations."""
    count: Optional[int] = 6

def _can_use_firestore_cover_art(db) -> bool:
    """Return True when Firestore is usable for cover art job storage."""
    return bool(getattr(db, 'use_firestore', False) and getattr(db, 'firestore', None))

def _get_latest_memory_cover_art_job(user_id: str, project_id: str):
    """Return the most recent in-memory cover art job for a user/project."""
    try:
        jobs = [
            job for job in _cover_art_jobs.values()
            if getattr(job, 'user_id', None) == user_id and getattr(job, 'project_id', None) == project_id
        ]
        if not jobs:
            return None
        def sort_key(job):
            return job.completed_at or job.created_at or datetime.min.replace(tzinfo=timezone.utc)
        jobs.sort(key=sort_key, reverse=True)
        return jobs[0]
    except Exception:
        return None

def _allow_cover_art_access(user_id: str, owner_id: Optional[str], collaborators: List[str]) -> bool:
    """Allow access when auth is disabled or user is owner/collaborator."""
    if user_id == "anonymous-user":
        return True
    return bool(owner_id == user_id or user_id in (collaborators or []))

def _update_reference_job_progress(
    job_id: str,
    progress: int,
    stage: str,
    message: str = "",
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    files_completed: int = 0,
    files_total: int = 0,
):
    """Update progress for a reference generation job and mirror to Firestore if possible."""
    if stage.lower() == "failed":
        status = 'failed-rate-limit'
    elif progress >= 100:
        status = 'completed'
    else:
        status = 'running'

    resolved_project_id = project_id or (job_id.split('_', 2)[2].rsplit('_', 1)[0] if '_' in job_id else job_id)

    progress_data = {
        'id': job_id,
        'status': status,
        'progress': progress,
        'stage': stage,
        'message': message,
        'files_completed': files_completed,
        'files_total': files_total,
        'updated_at': time.time()
    }

    _reference_jobs[job_id] = progress_data
    _reference_jobs[resolved_project_id] = progress_data

    try:
        from google.cloud import firestore as _gcf
        from backend.services.firestore_service import get_firestore_client
        client = get_firestore_client()
        payload = {
            'job_id': job_id,
            'project_id': resolved_project_id,
            'user_id': user_id,
            'status': status,
            'progress': progress,
            'stage': stage,
            'message': message,
            'files_completed': files_completed,
            'files_total': files_total,
            'updated_at': _gcf.SERVER_TIMESTAMP,
        }
        client.collection('reference_jobs').document(job_id).set(payload, merge=True)
    except Exception:
        pass

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v2/projects", tags=["projects-v2"])
security = HTTPBearer()

def _where_project_id(query, project_id: str):
    """Apply a project_id filter with FieldFilter fallback."""
    if FieldFilter is not None:
        return query.where(filter=FieldFilter('project_id', '==', project_id))
    return query.where('project_id', '==', project_id)

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
        _update_reference_job_progress(job_id, 0, "Initializing", "Starting reference generation...", project_id, user_id)
        
        try:
            from backend.utils.reference_content_generator import ReferenceContentGenerator
            from backend.utils.paths import get_project_workspace
        except Exception:
            from utils.reference_content_generator import ReferenceContentGenerator
            from utils.paths import get_project_workspace
        
        generator = ReferenceContentGenerator()
        if not generator.is_available():
            logger.warning(f"Reference generator not available for project {project_id}")
            _update_reference_job_progress(job_id, 0, "Failed", "AI service not available")
            return
        
        _update_reference_job_progress(job_id, 10, "Preparing", "Setting up workspace...", project_id, user_id)
        
        project_workspace = get_project_workspace(project_id)
        references_dir = project_workspace / "references"

        # Load book length metadata from project settings
        book_length_tier = None
        estimated_chapters = None
        target_word_count = None
        try:
            project = await get_project(project_id)
            if project:
                settings = project.get('settings', {}) or {}
                book_length_tier = settings.get('book_length_tier')
                estimated_chapters = settings.get('target_chapters') or settings.get('estimated_chapters')
                target_word_count = settings.get('target_word_count')
                if estimated_chapters:
                    estimated_chapters = int(estimated_chapters)
                if target_word_count:
                    target_word_count = int(target_word_count)
        except Exception as e:
            logger.warning(f"Could not load project settings for book length metadata: {e}")
        
        _update_reference_job_progress(job_id, 20, "Generating", "Creating reference files...", project_id, user_id)

        reference_types = list(ReferenceContentGenerator.CHAINED_GENERATION_ORDER)
        if include_series_bible and 'series-bible' not in reference_types:
            reference_types.append('series-bible')

        filename_map = {
            'characters': 'characters.md',
            'outline': 'outline.md',
            'world-building': 'world-building.md',
            'style-guide': 'style-guide.md',
            'plot-timeline': 'plot-timeline.md',
            'themes-and-motifs': 'themes-and-motifs.md',
            'research-notes': 'research-notes.md',
            'target-audience-profile': 'target-audience-profile.md',
            'director-guide': 'director-guide.md',
            'series-bible': 'series-bible.md',
            'entity-registry': 'entity-registry.md',
            'relationship-map': 'relationship-map.md',
        }

        references_dir.mkdir(parents=True, exist_ok=True)
        total = len(reference_types)
        stored_count = 0
        generated_content: dict[str, str] = {}

        for idx, ref_type in enumerate(reference_types):
            if idx > 0:
                try:
                    await asyncio.sleep(12.0)
                except Exception:
                    pass

            progress_value = 20 + int((idx / max(1, total)) * 75)
            _update_reference_job_progress(
                job_id, progress_value, "Generating",
                f"Generating {ref_type} ({idx + 1} of {total})...",
                project_id, user_id,
                files_completed=stored_count, files_total=total,
            )

            try:
                loop = asyncio.get_event_loop()
                prior_refs = dict(generated_content) if generated_content else None
                content = await loop.run_in_executor(
                    None,
                    lambda rt=ref_type, pr=prior_refs, blt=book_length_tier, ec=estimated_chapters, twc=target_word_count: generator.generate_content(
                        rt, book_bible_content,
                        prior_references=pr,
                        book_length_tier=blt,
                        estimated_chapters=ec,
                        target_word_count=twc,
                    )
                )

                filename = filename_map.get(ref_type, f"{ref_type}.md")
                file_path = references_dir / filename
                try:
                    file_path.write_text(content, encoding='utf-8')
                except Exception:
                    logger.warning(f"Failed to write {filename} to workspace; continuing to publish")

                generated_content[ref_type] = content

                await create_reference_file(
                    project_id=project_id,
                    filename=filename,
                    content=content,
                    user_id=user_id
                )
                vector_service = get_vector_store_service_optional()
                if vector_service:
                    try:
                        await vector_service.upsert_reference_file(
                            project_id=project_id,
                            user_id=user_id,
                            filename=filename,
                            content=content,
                            file_type=ref_type.replace("-", "_")
                        )
                    except Exception as vector_err:
                        logger.warning(f"Failed to index reference {filename} in vector store: {vector_err}")

                stored_count += 1
                progress_value = 20 + int(((idx + 1) / total) * 75)
                _update_reference_job_progress(
                    job_id, progress_value, "Generating",
                    f"Generated {filename} ({stored_count} of {total})",
                    project_id, user_id,
                    files_completed=stored_count, files_total=total,
                )
                logger.info(f"Published reference file {filename} for project {project_id}")

            except Exception as e:
                logger.error(f"Reference generation failed for {ref_type}: {e}")
                _update_reference_job_progress(
                    job_id, progress_value, "Generating",
                    f"Failed {ref_type}: {str(e)}",
                    project_id, user_id,
                    files_completed=stored_count, files_total=total,
                )

        if stored_count > 0:
            _update_reference_job_progress(
                job_id, 100, "Complete",
                f"Successfully generated {stored_count} of {total} reference files",
                project_id, user_id,
                files_completed=stored_count, files_total=total,
            )
            logger.info(f"Successfully generated and published {stored_count} reference files for project {project_id}")
            try:
                await _sync_project_settings_from_specs(project_id, user_id)
            except Exception as sync_err:
                logger.warning(f"Settings sync skipped after references for {project_id}: {sync_err}")
        else:
            _update_reference_job_progress(job_id, 0, "Failed", "Reference generation failed (AI errors or rate limits)", project_id, user_id)
            logger.error(f"Failed to generate any reference files for project {project_id}")
        

        
    except Exception as e:
        logger.error(f"Background reference generation failed for project {project_id}: {e}")
        _update_reference_job_progress(job_id, 0, "Failed", f"Error: {str(e)}", project_id, user_id)

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

def _parse_open_dialogue_preferences(source_data: Optional[dict]) -> Dict[str, Any]:
    if not isinstance(source_data, dict):
        return {}
    open_dialogue = source_data.get("open_dialogue")
    if isinstance(open_dialogue, dict):
        return open_dialogue
    return {}

def _normalize_book_length_tier(value: Optional[str]) -> Optional[BookLengthTier]:
    if not value:
        return None
    if isinstance(value, BookLengthTier):
        return value
    try:
        return BookLengthTier(str(value))
    except Exception:
        return None

def _derive_length_settings(
    tier_value: Optional[str],
    target_word_count: Optional[int],
    target_chapters: Optional[int],
    word_count_per_chapter: Optional[int],
    pacing_preference: Optional[str]
) -> Dict[str, Any]:
    """Derive length settings from tier, word count, and pacing preference."""
    tier = _normalize_book_length_tier(tier_value) or BookLengthTier.STANDARD_NOVEL
    specs = BookBible.get_book_length_specs(tier)
    pacing = (pacing_preference or "").strip().lower()
    pacing_factor = 1.0
    if pacing == "fast":
        pacing_factor = 0.85
    elif pacing == "expansive":
        pacing_factor = 1.2

    derived_target_word_count = int(target_word_count or specs["word_count_target"])
    avg_words = int(max(800, specs["avg_words_per_chapter"] * pacing_factor))

    if target_chapters:
        derived_target_chapters = int(target_chapters)
    else:
        raw_chapters = round(derived_target_word_count / max(1, avg_words))
        derived_target_chapters = int(min(specs["chapter_count_max"], max(specs["chapter_count_min"], raw_chapters)))

    if word_count_per_chapter:
        derived_words_per_chapter = int(word_count_per_chapter)
    else:
        derived_words_per_chapter = int(max(800, round(derived_target_word_count / max(1, derived_target_chapters))))

    return {
        "book_length_tier": tier.value,
        "target_word_count": derived_target_word_count,
        "target_chapters": derived_target_chapters,
        "word_count_per_chapter": derived_words_per_chapter,
        "chapter_count_min": specs["chapter_count_min"],
        "chapter_count_max": specs["chapter_count_max"]
    }

async def _sync_project_settings_from_specs(project_id: str, user_id: str) -> None:
    """Backfill project settings from book bible specs and open dialogue preferences."""
    try:
        project = await get_project(project_id)
        if not project:
            return

        settings = project.get("settings", {}) or {}
        book_bible = project.get("book_bible", {}) or {}
        source_data = book_bible.get("source_data") if isinstance(book_bible, dict) else None
        prefs = _parse_open_dialogue_preferences(source_data)

        derived = _derive_length_settings(
            book_bible.get("book_length_tier"),
            book_bible.get("target_word_count"),
            settings.get("target_chapters"),
            settings.get("word_count_per_chapter"),
            prefs.get("pacing_preference")
        )

        updates: Dict[str, Any] = {}

        if not settings.get("target_chapters"):
            updates["settings.target_chapters"] = derived["target_chapters"]
        if not settings.get("word_count_per_chapter"):
            updates["settings.word_count_per_chapter"] = derived["word_count_per_chapter"]

        if prefs.get("target_audience") and settings.get("target_audience") in [None, "", "General", "Adult"]:
            updates["settings.target_audience"] = prefs.get("target_audience")
        if prefs.get("writing_style") and settings.get("writing_style") in [None, "", "Professional", "Narrative"]:
            updates["settings.writing_style"] = prefs.get("writing_style")
        if prefs.get("involvement_level") and settings.get("involvement_level") in [None, "", "balanced"]:
            updates["settings.involvement_level"] = prefs.get("involvement_level")
        if prefs.get("purpose") and settings.get("purpose") in [None, "", "personal"]:
            updates["settings.purpose"] = prefs.get("purpose")

        if updates:
            db = get_database_adapter()
            if db.use_firestore and db.firestore:
                await db.firestore.update_project(project_id, updates)
                try:
                    from backend.services.firestore_service import get_firestore_client
                except ImportError:
                    from services.firestore_service import get_firestore_client
                client = get_firestore_client()
                client.collection('users').document(user_id).collection('projects').document(project_id).update(updates)
    except Exception as e:
        logger.warning(f"Failed to sync settings for project {project_id}: {e}")

def _normalize_reference_filename(filename: str) -> str:
    """Ensure reference filenames include .md extension."""
    return filename if filename.endswith('.md') else f"{filename}.md"

async def _resolve_reference_file(project_id: str, filename: str) -> Optional[Dict[str, Any]]:
    """Locate a reference file by filename using all supported storage models."""
    db = get_database_adapter()
    normalized_name = _normalize_reference_filename(filename)
    search_names = {filename, normalized_name}

    # Primary: subcollection reference files
    reference_files = []
    try:
        reference_files = await db.get_project_reference_files(project_id)
    except Exception as e:
        logger.warning(f"Adapter get_project_reference_files failed for {project_id}: {e}")

    for ref_file in reference_files:
        ref_name = ref_file.get('filename') or ref_file.get('name') or ref_file.get('file_name')
        if ref_name in search_names:
            return ref_file

    # Fallback: legacy embedded references
    try:
        project_data = await get_project(project_id)
        if project_data:
            refs = project_data.get('references')
            if isinstance(refs, dict):
                for ref_name, ref_val in refs.items():
                    normalized = _normalize_reference_filename(ref_name)
                    if normalized in search_names:
                        content = ref_val.get('content', '') if isinstance(ref_val, dict) else str(ref_val)
                        return {'filename': normalized, 'content': content}
            if isinstance(project_data.get('reference_files'), dict):
                content = project_data['reference_files'].get(filename) or project_data['reference_files'].get(normalized_name)
                if content is not None:
                    return {'filename': normalized_name, 'content': content}
    except Exception as e:
        logger.warning(f"Fallback lookup for reference '{filename}' in project {project_id} failed: {e}")

    # Final fallback: legacy root collection
    try:
        try:
            from backend.services.firestore_service import get_firestore_client
        except ImportError:
            from services.firestore_service import get_firestore_client
        client = get_firestore_client()
        query = _where_project_id(client.collection('references'), project_id)
        docs = list(query.stream())
        for doc in docs:
            data = doc.to_dict() or {}
            fname = data.get('filename') or data.get('name') or 'unnamed.md'
            normalized = _normalize_reference_filename(fname)
            if normalized in search_names:
                return {'filename': normalized, 'content': data.get('content', ''), **data}
    except Exception as e:
        logger.warning(f"Root collection lookup for '{filename}' in project {project_id} failed: {e}")

    return None

async def generate_series_bible(project_id: str, request: CreateProjectRequest, user_id: str):
    """Generate a series bible for multi-book projects."""
    try:
        book_bible_content = (request.book_bible_content or "").strip()
        if not book_bible_content:
            logger.info(f"Skipping series bible generation for project {project_id} - book bible missing")
            return

        try:
            from backend.utils.reference_content_generator import ReferenceContentGenerator
        except Exception:
            from utils.reference_content_generator import ReferenceContentGenerator

        generator = ReferenceContentGenerator()
        if not generator.is_available():
            logger.warning(f"Skipping series bible generation for project {project_id} - OpenAI not available")
            return

        series_bible_content = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: generator.generate_content("series-bible", book_bible_content)
        )
        if not series_bible_content or not series_bible_content.strip():
            logger.warning(f"Series bible generation returned empty content for project {project_id}")
            return

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
                try:
                    vector_service = require_vector_store_service()
                    await vector_service.upsert_reference_file(
                        project_id=project_id,
                        user_id=user_id,
                        filename=reference_data['name'],
                        content=reference_data['content'],
                        file_type="series_bible"
                    )
                except Exception as vector_err:
                    logger.warning(f"Failed to index series bible in vector store: {vector_err}")
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

        # Enrich each project with live chapter counts from Firestore
        # so the dashboard shows accurate progress instead of stale zeros.
        try:
            db = get_database_adapter()
            fs = getattr(db, "firestore", None) if db else None
            fs_db = getattr(fs, "db", None) if fs else None
            if fs_db:
                for proj in projects_data:
                    proj_id = (
                        proj.get("id")
                        or (proj.get("metadata") or {}).get("project_id")
                    )
                    if not proj_id:
                        continue
                    try:
                        chapters_ref = (
                            fs_db.collection("users").document(user_id)
                            .collection("projects").document(proj_id)
                            .collection("chapters")
                        )
                        chapter_docs = list(chapters_ref.stream())
                        chapter_count = 0
                        total_words = 0
                        for doc in chapter_docs:
                            ch = doc.to_dict() or {}
                            ch_num = 0
                            try:
                                ch_num = int(ch.get("chapter_number") or 0)
                            except Exception:
                                pass
                            if ch_num > 0:
                                chapter_count += 1
                                word_count = (
                                    ch.get("word_count")
                                    or (ch.get("metadata") or {}).get("word_count")
                                    or 0
                                )
                                try:
                                    total_words += int(word_count)
                                except Exception:
                                    pass

                        if chapter_count > 0:
                            progress = proj.setdefault("progress", {})
                            settings = proj.get("settings") or {}
                            target = int(settings.get("target_chapters") or 25)
                            progress["chapters_completed"] = chapter_count
                            progress["current_word_count"] = total_words
                            progress["completion_percentage"] = round(
                                min(100.0, (chapter_count / max(1, target)) * 100), 1
                            )
                            progress["last_chapter_generated"] = max(
                                progress.get("last_chapter_generated", 0),
                                chapter_count,
                            )
                    except Exception as ch_err:
                        logger.warning(
                            f"Failed to compute chapter progress for project {proj_id}: {ch_err}"
                        )
        except Exception as enrich_err:
            logger.warning(f"Failed to enrich projects with chapter counts: {enrich_err}")
        
        # Convert to Pydantic models for validation
        projects = []
        for project_data in projects_data:
            try:
                project = Project(**project_data)
                projects.append(project)
            except Exception as e:
                logger.error(f"Failed to parse project data: {e}")
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
        
        # Derive length settings and preferences (Open Dialogue)
        prefs = _parse_open_dialogue_preferences(request.source_data)
        derived_length = _derive_length_settings(
            request.book_length_tier,
            request.target_word_count,
            request.target_chapters,
            request.word_count_per_chapter,
            prefs.get("pacing_preference")
        )

        # Create project data structure
        project_data = {
            'metadata': {
                'title': request.title,
                'owner_id': user_id,
                'collaborators': [],
                'status': 'active',
                'visibility': 'private',
                'owner_display_name': f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip()
            },
            'settings': {
                'genre': request.genre,
                'target_chapters': derived_length["target_chapters"],
                'word_count_per_chapter': derived_length["word_count_per_chapter"],
                'target_audience': prefs.get("target_audience") or 'General',
                'writing_style': prefs.get("writing_style") or 'Professional',
                'quality_gates_enabled': True,
                'auto_completion_enabled': False,
                'involvement_level': prefs.get("involvement_level") or 'balanced',
                'purpose': prefs.get("purpose") or 'personal',
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
                        try:
                            from backend.utils.reference_content_generator import ReferenceContentGenerator
                            from backend.models.firestore_models import BookBible
                        except Exception:
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
                'book_length_tier': derived_length["book_length_tier"],
                'estimated_chapters': request.estimated_chapters or derived_length["target_chapters"],
                'target_word_count': request.target_word_count or derived_length["target_word_count"],
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

        # Initialize vector store memory for the project
        try:
            vector_service = require_vector_store_service()
            vector_store_id = await vector_service.ensure_project_vector_store(
                project_id=project_id,
                user_id=user_id,
                project_title=request.title
            )
            user_store_id = await vector_service.ensure_user_vector_store(user_id)
            if user_store_id:
                await vector_service.update_project_memory_fields(
                    project_id=project_id,
                    user_id=user_id,
                    updates={"user_vector_store_id": user_store_id}
                )
            if vector_store_id and request.book_bible_content:
                await vector_service.upsert_book_bible(
                    project_id=project_id,
                    user_id=user_id,
                    content=project_data.get('book_bible', {}).get('content', request.book_bible_content)
                )
        except Exception as vector_err:
            logger.warning(f"Vector store setup failed for project {project_id}: {vector_err}")
        
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
            try:
                from backend.utils.reference_content_generator import ReferenceContentGenerator
            except Exception:
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
                    'target_chapters': derived_length["target_chapters"],
                    'word_count_per_chapter': derived_length["word_count_per_chapter"],
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
    background_tasks: BackgroundTasks,
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
        
        # Write initial "running" status BEFORE scheduling the background task.
        # This eliminates the race condition where the frontend polls for progress
        # before the background task has written its first update, and gets a stale
        # "completed" response from a previous run.
        job_id = f"ref_gen_{project_id}_{int(time.time())}"
        _update_reference_job_progress(
            job_id, 0, "Initializing",
            "Reference generation starting...",
            project_id, user_id,
            files_completed=0, files_total=0,
        )

        background_tasks.add_task(
            generate_references_background,
            project_id,
            book_bible_content,
            bool(project.get('settings', {}).get('include_series_bible', False)),
            user_id
        )

        logger.info(f"Reference generation scheduled in background for project {project_id}")
        return {
            'success': True,
            'message': 'Reference generation started',
            'project_id': project_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate references for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate reference files"
        )

@router.post("/{project_id}/book-plan/regenerate")
async def regenerate_book_plan(
    project_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Regenerate the master book plan from the current book bible and reference files."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )

        project = await get_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )

        if project.get('metadata', {}).get('owner_id') != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )

        book_bible = project.get('book_bible', {})
        book_bible_content = book_bible.get('content')
        if not book_bible_content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No book bible content found for this project"
            )

        settings = project.get('settings', {}) or {}
        target_chapters = int(settings.get('target_chapters', 25))

        # Load reference files for plan generation
        references = {}
        try:
            ref_files = await get_project_reference_files(project_id)
            for ref in (ref_files or []):
                filename = ref.get('filename') or ref.get('name') or ''
                content = ref.get('content', '')
                if filename and content:
                    key = filename.replace('.md', '').replace('-', '_')
                    references[key] = content
        except Exception as e:
            logger.warning(f"Could not load reference files for plan regeneration: {e}")

        try:
            from backend.auto_complete.helpers.book_plan_generator import BookPlanGenerator
        except Exception:
            from auto_complete.helpers.book_plan_generator import BookPlanGenerator

        plan_generator = BookPlanGenerator()
        result = await plan_generator.generate_plan(
            book_bible=book_bible_content,
            references=references,
            target_chapters=target_chapters,
        )

        if not result.success or not result.plan:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.error or "Failed to generate book plan"
            )

        # Persist to Firestore as a reference file so chapters_v2 can find it
        import json as _json
        plan_json = _json.dumps(result.plan, indent=2, ensure_ascii=False)
        plan_filename = "book-plan.json"
        try:
            updated = await update_reference_file(project_id, plan_filename, plan_json, user_id)
            if not updated:
                await create_reference_file(project_id, plan_filename, plan_json, user_id)
        except Exception as e:
            logger.warning(f"Failed to persist book plan to references: {e}")

        chapter_count = len(result.plan.get('chapters', []))
        return {
            'success': True,
            'message': f'Book plan regenerated with {chapter_count} chapters',
            'chapters': chapter_count,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to regenerate book plan for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to regenerate book plan"
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
        
        if not project_data or not (isinstance(project_data, dict) and project_data.get('metadata')):
            if not project_data:
                logger.warning(f"[projects_v2] Project {project_id} not found for user {user_id}")
            else:
                logger.warning(
                    f"[projects_v2] Project payload missing metadata for {project_id}: keys={list(project_data.keys()) if isinstance(project_data, dict) else 'n/a'}"
                )

            # Attempt a repair pass if Firestore has an empty user-scoped doc.
            try:
                db = get_database_adapter()
                if db.use_firestore and db.firestore:
                    repaired = await db.firestore.repair_project_document(project_id, owner_id_hint=user_id)
                    if repaired:
                        project_data = await get_project(project_id)
            except Exception as repair_error:
                logger.warning(f"[projects_v2] Repair attempt failed for {project_id}: {repair_error}")

        if not project_data or not (isinstance(project_data, dict) and project_data.get('metadata')):
            logger.warning(f"[projects_v2] Project {project_id} not found for user {user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        # Verify user has access to this project
        owner_id = project_data.get('metadata', {}).get('owner_id')
        collaborators = project_data.get('metadata', {}).get('collaborators', [])

        if owner_id and not _allow_cover_art_access(user_id, owner_id, collaborators):
            logger.warning(
                f"[projects_v2] Access denied for project {project_id}; user={user_id}, owner={owner_id}, collaborators={len(collaborators)}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )

        # Ensure title is present before validation
        metadata = project_data.get('metadata', {}) or {}
        if not metadata.get('title'):
            candidate_title = project_data.get('title') or project_data.get('project_name') or project_data.get('projectName')
            if candidate_title:
                metadata['title'] = candidate_title
                project_data['metadata'] = metadata

        # Enrich with live chapter counts so progress is accurate
        try:
            db = get_database_adapter()
            fs = getattr(db, "firestore", None) if db else None
            fs_db = getattr(fs, "db", None) if fs else None
            if fs_db:
                chapters_ref = (
                    fs_db.collection("users").document(user_id)
                    .collection("projects").document(project_id)
                    .collection("chapters")
                )
                chapter_docs = list(chapters_ref.stream())
                chapter_count = 0
                total_words = 0
                for doc in chapter_docs:
                    ch = doc.to_dict() or {}
                    ch_num = 0
                    try:
                        ch_num = int(ch.get("chapter_number") or 0)
                    except Exception:
                        pass
                    if ch_num > 0:
                        chapter_count += 1
                        wc = ch.get("word_count") or (ch.get("metadata") or {}).get("word_count") or 0
                        try:
                            total_words += int(wc)
                        except Exception:
                            pass
                if chapter_count > 0:
                    progress = project_data.setdefault("progress", {})
                    settings = project_data.get("settings") or {}
                    target = int(settings.get("target_chapters") or 25)
                    progress["chapters_completed"] = chapter_count
                    progress["current_word_count"] = total_words
                    progress["completion_percentage"] = round(
                        min(100.0, (chapter_count / max(1, target)) * 100), 1
                    )
                    progress["last_chapter_generated"] = max(
                        progress.get("last_chapter_generated", 0), chapter_count
                    )
        except Exception as enrich_err:
            logger.warning(f"Failed to enrich project {project_id} with chapter counts: {enrich_err}")

        # Convert to Pydantic model for validation
        try:
            project = Project(**project_data)
            if _PROJECT_RESOLVE_LOG_ENABLED and _should_log_project_resolved(project_id):
                logger.info(
                    f"[projects_v2] Project {project_id} resolved; owner={owner_id}, title={project.metadata.title}"
                )
            return project
        except Exception as validation_error:
            logger.error(f"[projects_v2] Project validation failed for {project_id}: {validation_error}")
            return JSONResponse(jsonable_encoder(project_data))
        
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
    background_tasks: BackgroundTasks,
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

        # Support visibility update if present in request body directly (frontend convenience)
        try:
            # request may have extra key 'visibility' not in UpdateProjectRequest; access from body if available
            # Note: FastAPI already parsed 'request' into UpdateProjectRequest; use raw visibility via attribute access if present
            visibility_value = getattr(request, 'visibility', None)
            if visibility_value:
                updates['metadata.visibility'] = visibility_value if isinstance(visibility_value, str) else visibility_value.value
        except Exception:
            pass
        
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
        db = get_database_adapter()

        # If visibility is being updated, upsert a minimal root project doc with core fields for public library
        try:
            vis_update = updates.get('metadata.visibility')
            if vis_update:
                try:
                    # Fetch full project to get title/genre/owner for card data
                    current = await get_project(project_id)
                except Exception:
                    current = None
                # Prepare minimal document
                minimal = {
                    'metadata': {
                        'project_id': project_id,
                        'title': (current or {}).get('metadata', {}).get('title'),
                        'owner_id': (current or {}).get('metadata', {}).get('owner_id'),
                        'collaborators': (current or {}).get('metadata', {}).get('collaborators', []),
                        'owner_display_name': (current or {}).get('metadata', {}).get('owner_display_name'),
                        'visibility': vis_update,
                        'updated_at': datetime.now(timezone.utc)
                    },
                    'settings': {
                        'genre': (current or {}).get('settings', {}).get('genre')
                    }
                }
                # Use raw Firestore client to set merge=True on root doc
                try:
                    from backend.services.firestore_service import get_firestore_client
                except ImportError:
                    from services.firestore_service import get_firestore_client
                client = get_firestore_client()
                client.collection('projects').document(project_id).set(minimal, merge=True)
                # Also update the user-scoped project document for consistency
                owner_id = (current or {}).get('metadata', {}).get('owner_id')
                if owner_id:
                    try:
                        client.collection('users').document(owner_id).collection('projects').document(project_id).update({
                            'metadata.visibility': vis_update,
                            'metadata.updated_at': datetime.now(timezone.utc)
                        })
                    except Exception as ue:
                        logger.warning(f"Failed to update user-scoped project visibility: {ue}")
        except Exception as e:
            logger.warning(f"Failed to upsert root project doc for visibility change: {e}")

        # If title is being updated, mirror it into user-scoped project doc
        try:
            title_update = updates.get('metadata.title')
            if title_update:
                try:
                    from backend.services.firestore_service import get_firestore_client
                except ImportError:
                    from services.firestore_service import get_firestore_client
                client = get_firestore_client()
                owner_id = project_data.get('metadata', {}).get('owner_id')
                if owner_id:
                    try:
                        client.collection('users').document(owner_id).collection('projects').document(project_id).update({
                            'metadata.title': title_update,
                            'metadata.updated_at': datetime.now(timezone.utc)
                        })
                    except Exception as ue:
                        logger.warning(f"Failed to update user-scoped project title: {ue}")
        except Exception as e:
            logger.warning(f"Failed to mirror project title update: {e}")

        # Mirror settings updates into user-scoped project doc for list views
        try:
            settings_updates = {k: v for k, v in updates.items() if k.startswith('settings.')}
            if settings_updates:
                try:
                    from backend.services.firestore_service import get_firestore_client
                except ImportError:
                    from services.firestore_service import get_firestore_client
                client = get_firestore_client()
                owner_id = project_data.get('metadata', {}).get('owner_id')
                if owner_id:
                    settings_updates['metadata.updated_at'] = datetime.now(timezone.utc)
                    try:
                        client.collection('users').document(owner_id).collection('projects').document(project_id).update(settings_updates)
                    except Exception as ue:
                        logger.warning(f"Failed to update user-scoped project settings: {ue}")
        except Exception as e:
            logger.warning(f"Failed to mirror project settings update: {e}")

        success = await db.firestore.update_project(project_id, updates) if db.use_firestore else True
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update project"
            )

        try:
            vector_service = require_vector_store_service()
            if request.book_bible_content:
                await vector_service.upsert_book_bible(
                    project_id=project_id,
                    user_id=user_id,
                    content=request.book_bible_content
                )
            if request.settings:
                await vector_service.upsert_project_settings_snapshot(project_id, user_id)
        except Exception as vector_err:
            logger.warning(f"Failed to update vector memory for project {project_id}: {vector_err}")

        if request.book_bible_content:
            background_tasks.add_task(
                apply_steering_update,
                project_id,
                user_id,
                "book_bible",
                "book-bible",
                request.book_bible_content,
                "",
                "manual",
                "document"
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


@router.patch("/{project_id}", response_model=dict)
async def patch_project(
    project_id: str,
    request: UpdateProjectRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Patch an existing project (PUT-compatible)."""
    return await update_project(
        project_id=project_id,
        request=request,
        background_tasks=background_tasks,
        current_user=current_user
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
            try:
                from backend.utils.paths import get_project_workspace
            except Exception:
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
        if not _allow_cover_art_access(user_id, owner_id, collaborators):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )
        
        # Get database adapter
        from backend.database_integration import get_database_adapter
        db = get_database_adapter()
        
        # Get chapters using the database adapter
        chapters_data = await db.get_project_chapters(project_id)
        
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

@router.delete("/{project_id}/chapters", response_model=dict)
async def clear_all_chapters(
    project_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete all chapters for a project while preserving references and book bible."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )

        project_data = await get_project(project_id)
        if not project_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )

        owner_id = project_data.get('metadata', {}).get('owner_id')
        if owner_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only project owners can clear chapters"
            )

        from backend.database_integration import get_database_adapter
        db = get_database_adapter()

        chapters_data = await db.get_project_chapters(project_id)
        deleted_count = 0

        if db.use_firestore:
            batch = db.firestore.db.batch()
            batch_size = 0

            for chapter in chapters_data:
                chapter_id = chapter.get('id')
                if not chapter_id:
                    continue

                # Delete from user-scoped subcollection
                user_chapter_ref = db.firestore.db.collection('users').document(owner_id)\
                    .collection('projects').document(project_id)\
                    .collection('chapters').document(chapter_id)
                batch.delete(user_chapter_ref)
                batch_size += 1

                # Firestore batch limit is 500 writes
                if batch_size >= 400:
                    batch.commit()
                    batch = db.firestore.db.batch()
                    batch_size = 0

                deleted_count += 1

            # Also delete from top-level chapters collection if present
            try:
                from google.cloud.firestore_v1.base_query import FieldFilter as FF
                top_level_query = db.firestore.db.collection('chapters').where(
                    filter=FF('project_id', '==', project_id)
                )
                for doc in top_level_query.stream():
                    batch.delete(doc.reference)
                    batch_size += 1
                    if batch_size >= 400:
                        batch.commit()
                        batch = db.firestore.db.batch()
                        batch_size = 0
            except Exception as e:
                logger.warning(f"Top-level chapter cleanup failed for {project_id}: {e}")

            if batch_size > 0:
                batch.commit()

            # Reset project progress
            try:
                project_ref = db.firestore.db.collection('users').document(owner_id)\
                    .collection('projects').document(project_id)
                project_ref.update({
                    'progress.chapters_completed': 0,
                    'progress.current_word_count': 0,
                    'progress.completion_percentage': 0,
                    'progress.last_chapter_generated': 0,
                })
            except Exception as e:
                logger.warning(f"Failed to reset progress for {project_id}: {e}")

        logger.info(f"Cleared {deleted_count} chapters from project {project_id} for user {user_id}")

        return {
            'success': True,
            'deleted_count': deleted_count,
            'message': f'Successfully cleared {deleted_count} chapters'
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear chapters for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear chapters"
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
        
        if not _allow_cover_art_access(user_id, owner_id, collaborators):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )
        
        # Look for reference generation job progress.
        # Check in-memory first (always up-to-date, no replication lag),
        # then fall back to Firestore.
        job_progress = _reference_jobs.get(project_id)

        if not job_progress:
            try:
                from google.cloud import firestore as _gcf
                from backend.services.firestore_service import get_firestore_client
                client = get_firestore_client()
                query = _where_project_id(client.collection('reference_jobs'), project_id) \
                    .order_by('updated_at', direction=_gcf.Query.DESCENDING) \
                    .limit(1)
                docs = list(query.stream())
                if docs:
                    data = docs[0].to_dict()
                    job_progress = {
                        'status': data.get('status', 'running'),
                        'progress': data.get('progress', 0),
                        'stage': data.get('stage', ''),
                        'message': data.get('message', ''),
                        'files_completed': data.get('files_completed', 0),
                        'files_total': data.get('files_total', 0),
                        'updated_at': time.time()
                    }
            except Exception:
                pass
        
        if not job_progress:
            # Check if references already exist (generation might be complete)
            from backend.database_integration import get_database_adapter
            db = get_database_adapter()
            try:
                reference_files = await db.get_project_reference_files(project_id)
            except Exception as e:
                logger.warning(f"Adapter get_project_reference_files failed for progress check: {e}")
                reference_files = []
            
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
            'files_completed': job_progress.get('files_completed', 0),
            'files_total': job_progress.get('files_total', 0),
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

class ReferenceAiEditRequest(BaseModel):
    instructions: str
    current_content: Optional[str] = None
    scope: Optional[str] = None
    section_title: Optional[str] = None

class SteeringRewriteCandidateRequest(BaseModel):
    canon_log_id: Optional[str] = None
    instructions: Optional[str] = None
    source_type: Optional[str] = None
    source_label: Optional[str] = None
    source_excerpt: Optional[str] = None

class SteeringRewriteRequest(BaseModel):
    canon_log_id: Optional[str] = None
    chapter_ids: List[str] = []

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
        
        if not _allow_cover_art_access(user_id, owner_id, collaborators):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )
        
        # Get reference files (primary: subcollection)
        db = get_database_adapter()
        # Use adapter abstraction to avoid AttributeError when Firestore client is not attached
        reference_files = []
        try:
            reference_files = await db.get_project_reference_files(project_id)
        except Exception as e:
            logger.warning(f"Adapter get_project_reference_files failed for {project_id}: {e}")

        # Fallbacks for legacy data models if subcollection is empty
        if not reference_files:
            try:
                project_data = await get_project(project_id)
                legacy_files = []
                # Legacy embedded references dict: { name: { content, ... } } or { name: content }
                if project_data and 'references' in project_data and isinstance(project_data['references'], dict):
                    for ref_name, ref_val in project_data['references'].items():
                        if isinstance(ref_val, dict):
                            content = ref_val.get('content', '')
                        else:
                            content = str(ref_val) if ref_val is not None else ''
                        legacy_files.append({'filename': f"{ref_name if ref_name.endswith('.md') else ref_name + '.md'}", 'content': content})
                # Older legacy key: 'reference_files' as dict of filename -> content
                if not legacy_files and 'reference_files' in project_data and isinstance(project_data['reference_files'], dict):
                    for fname, content in project_data['reference_files'].items():
                        legacy_files.append({'filename': fname, 'content': content})
                if legacy_files:
                    reference_files = legacy_files
            except Exception as e:
                logger.warning(f"Fallback load of legacy references failed for project {project_id}: {e}")

        # Final fallback: legacy root collection 'references' (filename/content per doc)
        if not reference_files:
            try:
                from backend.services.firestore_service import get_firestore_client
            except ImportError:
                from services.firestore_service import get_firestore_client
            try:
                client = get_firestore_client()
                query = _where_project_id(client.collection('references'), project_id)
                docs = list(query.stream())
                root_files = []
                for doc in docs:
                    data = doc.to_dict() or {}
                    fname = data.get('filename') or data.get('name') or 'unnamed.md'
                    content = data.get('content', '')
                    root_files.append({'filename': fname, 'content': content})
                if root_files:
                    reference_files = root_files
            except Exception as e:
                logger.warning(f"Root collection references lookup failed for project {project_id}: {e}")

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


@router.post("/{project_id}/memory/reindex", response_model=dict)
async def reindex_project_memory(
    project_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Reindex all project content into the vector store memory."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )

        project = await get_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )

        owner_id = project.get('metadata', {}).get('owner_id')
        collaborators = project.get('metadata', {}).get('collaborators', [])
        if not _allow_cover_art_access(user_id, owner_id, collaborators):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )

        vector_service = require_vector_store_service()
        vector_store_id = await vector_service.ensure_project_vector_store(
            project_id=project_id,
            user_id=user_id,
            project_title=(project.get('metadata') or {}).get('title')
        )
        user_store_id = await vector_service.ensure_user_vector_store(user_id)
        if user_store_id:
            await vector_service.update_project_memory_fields(
                project_id=project_id,
                user_id=user_id,
                updates={"user_vector_store_id": user_store_id}
            )

        indexed = {
            "book_bible": 0,
            "references": 0,
            "chapters": 0,
            "notes": 0
        }

        book_bible = project.get('book_bible', {})
        book_bible_content = ""
        if isinstance(book_bible, dict):
            book_bible_content = book_bible.get('content') or ""
        elif isinstance(book_bible, str):
            book_bible_content = book_bible

        if book_bible_content.strip():
            await vector_service.upsert_book_bible(project_id, user_id, book_bible_content)
            indexed["book_bible"] = 1

        reference_files = []
        try:
            reference_files = await get_project_reference_files(project_id)
        except Exception as e:
            logger.warning(f"Adapter get_project_reference_files failed for {project_id}: {e}")

        for ref in reference_files:
            content = (ref.get('content') or '').strip()
            if not content:
                continue
            await vector_service.upsert_reference_file(
                project_id=project_id,
                user_id=user_id,
                filename=ref.get('filename', 'reference.md'),
                content=content,
                file_type=ref.get('file_type') or 'reference_file'
            )
            indexed["references"] += 1

        chapters = []
        try:
            chapters = await get_project_chapters(project_id)
        except Exception as e:
            logger.warning(f"Adapter get_project_chapters failed for {project_id}: {e}")

        for chapter in chapters:
            content = (chapter.get('content') or '').strip()
            if not content:
                continue
            chapter_id = chapter.get('id') or chapter.get('chapter_id') or f"chapter-{chapter.get('chapter_number', 0)}"
            await vector_service.upsert_chapter(
                project_id=project_id,
                user_id=user_id,
                chapter_id=chapter_id,
                chapter_number=chapter.get('chapter_number', 0),
                title=chapter.get('title') or f"Chapter {chapter.get('chapter_number', '')}",
                content=content
            )
            indexed["chapters"] += 1

        notes = []
        try:
            notes = await list_story_notes(project_id, user_id)
        except Exception as e:
            logger.warning(f"Adapter list_story_notes failed for {project_id}: {e}")

        for note in notes:
            if note.get('resolved'):
                continue
            content = (note.get('content') or '').strip()
            if not content:
                continue
            note_id = note.get('note_id') or note.get('id')
            if not note_id:
                continue
            await vector_service.upsert_story_note(
                project_id=project_id,
                user_id=user_id,
                note_id=note_id,
                content=content,
                scope=note.get('scope', 'chapter'),
                chapter_id=note.get('chapter_id'),
                intent=note.get('intent')
            )
            indexed["notes"] += 1

        return {
            "success": True,
            "project_id": project_id,
            "vector_store_id": vector_store_id,
            "indexed": indexed
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reindex vector memory for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reindex vector memory"
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
        
        target_file = await _resolve_reference_file(project_id, filename)

        if not target_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reference file '{filename}' not found"
            )
        
        resolved_name = target_file.get('filename') or target_file.get('name') or target_file.get('file_name') or filename

        return {
            'success': True,
            'name': resolved_name,
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


@router.put("/{project_id}/references/{filename}")
async def update_reference_file_content(
    project_id: str,
    filename: str,
    request: dict,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Update a reference file's content."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )

        project = await get_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )

        owner_id = project.get('metadata', {}).get('owner_id')
        collaborators = project.get('metadata', {}).get('collaborators', [])
        if not _allow_cover_art_access(user_id, owner_id, collaborators):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )

        content = request.get('content')
        if content is None or not isinstance(content, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Content is required"
            )

        target_file = await _resolve_reference_file(project_id, filename)
        if not target_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reference file '{filename}' not found"
            )

        normalized_name = _normalize_reference_filename(filename)
        updated = await update_reference_file(
            project_id=project_id,
            filename=normalized_name,
            content=content,
            user_id=user_id
        )

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update reference file"
            )

        try:
            vector_service = require_vector_store_service()
            await vector_service.upsert_reference_file(
                project_id=project_id,
                user_id=user_id,
                filename=normalized_name,
                content=content
            )
        except Exception as vector_err:
            logger.warning(f"Failed to update vector memory for reference {normalized_name}: {vector_err}")

        steer = request.get('steer', True)
        steering_instructions = request.get('steering_instructions') or ""
        if steer:
            background_tasks.add_task(
                apply_steering_update,
                project_id,
                user_id,
                "reference",
                normalized_name,
                content,
                steering_instructions,
                "manual",
                "document"
            )

        return {
            'success': True,
            'name': normalized_name,
            'content': content,
            'lastModified': datetime.now(timezone.utc).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update reference file {filename} for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update reference file"
        )


@router.post("/{project_id}/references/{filename}/ai-edit")
async def ai_edit_reference_file(
    project_id: str,
    filename: str,
    request: ReferenceAiEditRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Apply AI edits to a reference file based on user instructions."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )

        instructions = (request.instructions or '').strip()
        if not instructions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Instructions are required"
            )

        project = await get_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )

        owner_id = project.get('metadata', {}).get('owner_id')
        collaborators = project.get('metadata', {}).get('collaborators', [])
        if not _allow_cover_art_access(user_id, owner_id, collaborators):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )

        target_file = await _resolve_reference_file(project_id, filename)
        current_content = request.current_content or (target_file.get('content') if target_file else None)
        if not current_content:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Reference file '{filename}' not found"
            )

        try:
            from backend.utils.reference_content_generator import ReferenceContentGenerator
        except Exception:
            from utils.reference_content_generator import ReferenceContentGenerator

        generator = ReferenceContentGenerator(user_id=user_id)
        if not generator.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OpenAI API key not configured. Cannot apply AI edits."
            )

        reference_type = filename.replace('.md', '')
        scope = (request.scope or "document").lower()
        section_title = request.section_title
        updated_content = await generator.apply_reference_edit(
            reference_type,
            current_content,
            instructions,
            scope=scope,
            section_title=section_title
        )

        normalized_name = _normalize_reference_filename(filename)
        if scope == "section":
            return {
                'success': True,
                'name': normalized_name,
                'content': updated_content
            }

        updated = await update_reference_file(
            project_id=project_id,
            filename=normalized_name,
            content=updated_content,
            user_id=user_id
        )
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save AI edits"
            )

        try:
            vector_service = require_vector_store_service()
            await vector_service.upsert_reference_file(
                project_id=project_id,
                user_id=user_id,
                filename=normalized_name,
                content=updated_content,
                file_type=reference_type.replace("-", "_")
            )
        except Exception as vector_err:
            logger.warning(f"Failed to update vector memory for AI-edited reference {normalized_name}: {vector_err}")

        background_tasks.add_task(
            apply_steering_update,
            project_id,
            user_id,
            "reference",
            normalized_name,
            updated_content,
            instructions,
            "ai",
            "document"
        )

        return {
            'success': True,
            'name': normalized_name,
            'content': updated_content,
            'lastModified': datetime.now(timezone.utc).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"AI edit failed for reference file {filename} on project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to apply AI edits"
        )


@router.post("/{project_id}/book-bible/ai-edit")
async def ai_edit_book_bible(
    project_id: str,
    request: ReferenceAiEditRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Apply AI edits to the book bible based on user instructions."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )

        instructions = (request.instructions or '').strip()
        if not instructions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Instructions are required"
            )

        project = await get_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )

        owner_id = project.get('metadata', {}).get('owner_id')
        collaborators = project.get('metadata', {}).get('collaborators', [])
        if not _allow_cover_art_access(user_id, owner_id, collaborators):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )

        book_bible_content = request.current_content or project.get('book_bible', {}).get('content')
        if not book_bible_content:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Book bible not found"
            )

        try:
            from backend.utils.reference_content_generator import ReferenceContentGenerator
        except Exception:
            from utils.reference_content_generator import ReferenceContentGenerator

        generator = ReferenceContentGenerator(user_id=user_id)
        if not generator.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OpenAI API key not configured. Cannot apply AI edits."
            )

        scope = (request.scope or "document").lower()
        section_title = request.section_title
        updated_content = await generator.apply_reference_edit(
            "book-bible",
            book_bible_content,
            instructions,
            scope=scope,
            section_title=section_title
        )

        if scope == "section":
            return {
                'success': True,
                'content': updated_content
            }

        updates = {
            'book_bible.content': updated_content,
            'book_bible.last_modified': datetime.now(timezone.utc),
            'book_bible.modified_by': user_id,
            'book_bible.word_count': len(updated_content.split())
        }

        db = get_database_adapter()
        success = await db.firestore.update_project(project_id, updates) if db.use_firestore else True
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save book bible"
            )

        try:
            vector_service = require_vector_store_service()
            await vector_service.upsert_book_bible(project_id, user_id, updated_content)
        except Exception as vector_err:
            logger.warning(f"Failed to update vector memory for book bible {project_id}: {vector_err}")

        background_tasks.add_task(
            apply_steering_update,
            project_id,
            user_id,
            "book_bible",
            "book-bible",
            updated_content,
            instructions,
            "ai",
            "document"
        )

        return {
            'success': True,
            'content': updated_content,
            'lastModified': datetime.now(timezone.utc).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to apply AI edits to book bible for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to apply AI edits"
        )


# =====================================================================
# CANON LOGS
# =====================================================================

@router.get("/{project_id}/canon-log", response_model=dict)
async def list_canon_log(
    project_id: str,
    limit: int = 20,
    current_user: dict = Depends(get_current_user)
):
    """List recent canon log entries for a project."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )

        project = await get_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )

        owner_id = project.get('metadata', {}).get('owner_id')
        collaborators = project.get('metadata', {}).get('collaborators', [])
        if not _allow_cover_art_access(user_id, owner_id, collaborators):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )

        db = get_database_adapter()
        if not getattr(db, "use_firestore", False) or not getattr(db, "firestore", None):
            return {"success": True, "entries": []}

        client = getattr(db.firestore, "db", None)
        if client is None:
            return {"success": True, "entries": []}

        try:
            from google.cloud import firestore as _firestore
            direction = _firestore.Query.DESCENDING
        except Exception:
            direction = "DESCENDING"

        logs_ref = client.collection("projects").document(project_id).collection("canon_logs")
        query = logs_ref.order_by("created_at", direction=direction).limit(limit)
        docs = query.stream()
        entries = []
        for doc in docs:
            entry = doc.to_dict()
            entry["id"] = entry.get("id") or doc.id
            entries.append(entry)

        return {"success": True, "entries": entries}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list canon logs for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list canon logs"
        )


async def _load_canon_log_entry(project_id: str, entry_id: str) -> Optional[dict]:
    try:
        db = get_database_adapter()
        if not getattr(db, "use_firestore", False) or not getattr(db, "firestore", None):
            return None
        client = getattr(db.firestore, "db", None)
        if client is None:
            return None
        doc = client.collection("projects").document(project_id).collection("canon_logs").document(entry_id).get()
        if not doc.exists:
            return None
        return doc.to_dict()
    except Exception:
        return None


@router.post("/{project_id}/steering/rewrite-candidates", response_model=dict)
async def get_steering_rewrite_candidates(
    project_id: str,
    request: SteeringRewriteCandidateRequest,
    current_user: dict = Depends(get_current_user)
):
    """Find prior chapters that likely need rewriting for a canon update."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )

        project = await get_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )

        owner_id = project.get('metadata', {}).get('owner_id')
        collaborators = project.get('metadata', {}).get('collaborators', [])
        if not _allow_cover_art_access(user_id, owner_id, collaborators):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )

        canon_entry = None
        if request.canon_log_id:
            canon_entry = await _load_canon_log_entry(project_id, request.canon_log_id)

        source_type = (request.source_type or (canon_entry or {}).get("source_type") or "").strip()
        source_label = (request.source_label or (canon_entry or {}).get("source_label") or "").strip()
        instructions = (request.instructions or (canon_entry or {}).get("instructions") or "").strip()
        source_excerpt = request.source_excerpt or (canon_entry or {}).get("metadata", {}).get("source_excerpt") or ""

        query = "Canon update review."
        if source_label:
            query += f" Focus: {source_label}."
        if instructions:
            query += f" Update: {instructions}"
        if source_excerpt:
            query += f" Source details: {source_excerpt[:500]}"

        vector_service = require_vector_store_service()
        if not vector_service.available:
            return {"success": True, "candidates": []}

        results = await vector_service.retrieve_chapter_context(
            project_id=project_id,
            user_id=user_id,
            query=query,
            max_results=12
        )

        file_ids = [r.file_id for r in results if r.file_id]
        if not file_ids:
            return {"success": True, "candidates": []}

        documents = await vector_service.resolve_documents_by_file_ids(project_id, user_id, file_ids)
        chapter_ids = []
        for doc in documents:
            if doc.get("doc_type") == "chapter" and doc.get("source_id"):
                chapter_ids.append(doc["source_id"])

        if not chapter_ids:
            return {"success": True, "candidates": []}

        db = get_database_adapter()
        candidates = []
        for chapter_id in list(dict.fromkeys(chapter_ids)):
            chapter_data = await db.get_chapter(chapter_id, user_id=user_id)
            if not chapter_data:
                continue
            candidates.append({
                "chapter_id": chapter_id,
                "chapter_number": chapter_data.get("chapter_number"),
                "title": chapter_data.get("title") or f"Chapter {chapter_data.get('chapter_number', '')}"
            })

        return {"success": True, "candidates": candidates}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get steering rewrite candidates for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get rewrite candidates"
        )


@router.post("/{project_id}/steering/rewrite-chapters", response_model=dict)
async def rewrite_chapters_for_steering(
    project_id: str,
    request: SteeringRewriteRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Rewrite selected chapters to align with a canon update."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )

        if not request.chapter_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No chapters selected for rewrite"
            )

        project = await get_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )

        owner_id = project.get('metadata', {}).get('owner_id')
        collaborators = project.get('metadata', {}).get('collaborators', [])
        if not _allow_cover_art_access(user_id, owner_id, collaborators):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )

        canon_entry = None
        if request.canon_log_id:
            canon_entry = await _load_canon_log_entry(project_id, request.canon_log_id)

        source_type = (canon_entry or {}).get("source_type") or "canon"
        source_label = (canon_entry or {}).get("source_label") or "Canon Update"
        instructions = (canon_entry or {}).get("instructions") or ""
        source_excerpt = (canon_entry or {}).get("metadata", {}).get("source_excerpt") or ""
        source_content = source_excerpt

        try:
            if source_type == "book_bible":
                bb_entry = project.get("book_bible", {})
                if isinstance(bb_entry, dict):
                    source_content = bb_entry.get("content") or source_excerpt
                elif isinstance(bb_entry, str):
                    source_content = bb_entry
            elif source_type == "reference" and source_label:
                target_file = await _resolve_reference_file(project_id, source_label)
                if target_file:
                    source_content = target_file.get("content") or source_excerpt
            elif source_type == "chapter" and source_label:
                try:
                    chapter_number = int(str(source_label).replace("chapter-", ""))
                except Exception:
                    chapter_number = None
                if chapter_number is not None:
                    chapters = await get_project_chapters(project_id)
                    for chapter in chapters:
                        if chapter.get("chapter_number") == chapter_number:
                            source_content = chapter.get("content") or source_excerpt
                            break
        except Exception:
            source_content = source_excerpt

        rewrite_log_id = await create_canon_log_entry(
            project_id=project_id,
            user_id=user_id,
            source_type="chapter_rewrite",
            source_label=source_label,
            instructions=instructions,
            mode="ai",
            scope="document",
            status="running",
            metadata={
                "parent_canon_log_id": request.canon_log_id,
                "source_excerpt": source_excerpt
            }
        )

        for chapter_id in request.chapter_ids:
            background_tasks.add_task(
                rewrite_chapter_for_canon,
                project_id,
                user_id,
                chapter_id,
                instructions,
                source_label,
                source_type,
                source_content,
                rewrite_log_id
            )

        return {"success": True, "queued": len(request.chapter_ids), "log_id": rewrite_log_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to rewrite chapters for steering in project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue chapter rewrites"
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
        try:
            from backend.utils.reference_content_generator import ReferenceContentGenerator
        except Exception:
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


@router.post("/{project_id}/cover-art")
async def generate_cover_art(
    project_id: str,
    request: CoverArtRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Generate cover art for a project using OpenAI DALL-E 3."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )

        # Check if cover art service is available
        if not cover_art_service or not cover_art_service.is_available():
            if not cover_art_service:
                detail = "Cover art generation service unavailable."
            elif not cover_art_service.openai_client:
                detail = "Cover art generation service unavailable: OpenAI API key not configured."
            elif not cover_art_service.firebase_bucket:
                detail = "Cover art generation service unavailable: Firebase Storage not configured."
            else:
                detail = "Cover art generation service is temporarily unavailable."
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=detail
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
        
        if not _allow_cover_art_access(user_id, owner_id, collaborators):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )
        
        # Check if references are completed
        from backend.database_integration import get_database_adapter
        db = get_database_adapter()
        can_use_firestore = _can_use_firestore_cover_art(db)
        # Use adapter method with internal fallbacks instead of direct Firestore-only call
        try:
            reference_files_data = await db.get_project_reference_files(project_id)
        except Exception as e:
            logger.warning(f"Adapter get_project_reference_files failed for cover art check: {e}")
            reference_files_data = []
        
        if not reference_files_data or len(reference_files_data) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reference files must be generated before creating cover art. Please generate reference files first."
            )
        
        # Get book bible content
        book_bible_content = project.get('book_bible', {}).get('content', '')
        if not book_bible_content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Book bible content is required for cover art generation"
            )
        
        # Convert reference files to dictionary format
        reference_files = {}
        for ref_file in reference_files_data:
            filename = ref_file.get('filename', '')
            content = ref_file.get('content', '')
            if filename and content:
                reference_files[filename] = content
        
        if len(reference_files) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid reference file content found"
            )
        
        # Check if this is a regeneration request
        job_id = None
        attempt_number = 1
        if request.regenerate:
            # Find existing job for this project
            if can_use_firestore:
                user_jobs = await db.firestore.get_user_cover_art_jobs(user_id, project_id, limit=1)
                if user_jobs:
                    job_id = user_jobs[0].get('job_id')
                    attempt_number = int(user_jobs[0].get('attempt_number') or 1) + 1
            if not job_id:
                memory_job = _get_latest_memory_cover_art_job(user_id, project_id)
                if memory_job:
                    job_id = memory_job.job_id
                    attempt_number = int(getattr(memory_job, 'attempt_number', 1) or 1) + 1
        
        # Create or get job ID
        if not job_id:
            job_id = str(uuid.uuid4())
            attempt_number = 1
        
        # Create initial job entry in Firestore
        job_data = {
            'job_id': job_id,
            'project_id': project_id,
            'user_id': user_id,
            'status': 'pending',
            'user_feedback': request.user_feedback,
            'attempt_number': attempt_number,
            'requirements': request.requirements
        }
        
        # Save to Firestore if available
        if can_use_firestore:
            await db.firestore.create_cover_art_job(job_data)
        
        # Also keep in memory for backward compatibility
        initial_job = CoverArtJob(
            job_id=job_id,
            project_id=project_id,
            user_id=user_id,
            status='pending',
            user_feedback=request.user_feedback,
            created_at=datetime.now(timezone.utc),
            attempt_number=attempt_number
        )
        _cover_art_jobs[job_id] = initial_job
        
        # Start background generation
        async def generate_cover_background():
            """Background task for cover art generation."""
            try:
                logger.info(f"Starting background cover art generation for project {project_id}")
                logger.info(f"Book bible content length: {len(book_bible_content)}")
                # Log a small excerpt of the bible to verify correctness
                try:
                    safe_excerpt = (book_bible_content or "").replace("\n", " ")[:180]
                    logger.info(f"Book bible excerpt: {safe_excerpt}")
                except Exception:
                    pass
                # Log filenames and first 100 chars of each reference
                try:
                    ref_preview = {name: (content or "").replace("\n", " ")[:100] for name, content in reference_files.items()}
                    logger.info(f"Reference files preview: {ref_preview}")
                except Exception:
                    logger.info(f"Reference files: {list(reference_files.keys())}")
                logger.info(f"User feedback: {request.user_feedback}")

                # Prepare UI options with robust server-side fallbacks for exact text overlay
                ui_options = dict(request.options or {})
                try:
                    meta = project.get('metadata', {}) if isinstance(project, dict) else {}
                    # If title requested but missing, use project title
                    if ui_options.get('include_title') and not (ui_options.get('title_text') or '').strip():
                        fallback_title = (meta.get('title') or '').strip()
                        if fallback_title:
                            ui_options['title_text'] = fallback_title
                    # If author requested but missing, use owner's display name
                    if ui_options.get('include_author') and not (ui_options.get('author_text') or '').strip():
                        fallback_author = (meta.get('owner_display_name') or '').strip()
                        if fallback_author:
                            ui_options['author_text'] = fallback_author
                except Exception:
                    pass
                
                # Build short grounding excerpts for prompt fidelity
                bible_excerpt = (book_bible_content or "")[:400]
                # Create a concise references digest (filenames + first 120 chars)
                try:
                    ref_parts = []
                    for name, content in (reference_files or {}).items():
                        if not content:
                            continue
                        ref_parts.append(f"{name}: {content[:120]}")
                    references_digest = "; ".join(ref_parts)[:400]
                except Exception:
                    references_digest = None

                logger.info(f"Cover art UI options: {request.options}")
                vector_context = ""
                try:
                    from backend.services.vector_store_service import VectorStoreService
                except Exception:
                    from services.vector_store_service import VectorStoreService

                try:
                    vector_service = require_vector_store_service()
                    if vector_service.available:
                        await vector_service.ensure_project_vector_store(
                            project_id=project_id,
                            user_id=user_id,
                            project_title=project.get('metadata', {}).get('title')
                        )
                        await vector_service.ensure_user_vector_store(user_id)
                        vector_context = await vector_service.retrieve_cover_art_context(project_id, user_id)
                except Exception as e:
                    logger.warning(f"Vector context unavailable for cover art: {e}")

                job = await cover_art_service.generate_cover_art(
                    project_id=project_id,
                    user_id=user_id,
                    book_bible_content=book_bible_content,
                    reference_files=reference_files,
                    user_feedback=request.user_feedback,
                    options=ui_options,
                    job_id=job_id,
                    requirements=request.requirements,
                    vector_context=vector_context
                )
                # Regenerate prompt with explicit grounding context for improved adherence (stored in job)
                try:
                    job.prompt = cover_art_service.generate_cover_prompt(
                        cover_art_service.extract_book_details(book_bible_content, reference_files, ui_options or {}),
                        request.user_feedback,
                        ui_options,
                        request.requirements,
                        raw_bible_excerpt=bible_excerpt,
                        references_digest=references_digest,
                        vector_context=vector_context
                    )
                except Exception:
                    pass
                job.attempt_number = attempt_number
                _cover_art_jobs[job_id] = job
                
                logger.info(f"Cover art generation completed with status: {job.status}")
                if job.status == 'completed':
                    logger.info(f"Generated image URL: {job.image_url}")
                elif job.status == 'failed':
                    logger.error(f"Cover art generation failed: {job.error}")
                
                # Update job in Firestore if available
                if can_use_firestore:
                    await db.firestore.update_cover_art_job(job_id, {
                        'status': job.status,
                        'image_url': job.image_url,
                        'storage_path': job.storage_path,
                        'prompt': job.prompt,
                        'error': job.error,
                        'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                        'attempt_number': attempt_number
                    })
                
                # If successful, save cover art URL to project document
                if can_use_firestore and job.status == 'completed' and job.image_url:
                    try:
                        await db.firestore.update_project(project_id, {
                            'cover_art': {
                                'image_url': job.image_url,
                                'job_id': job_id,
                                'storage_path': job.storage_path,
                                'generated_at': job.completed_at.isoformat() if job.completed_at else None
                            }
                        })
                        logger.info(f"Successfully saved cover art URL to project {project_id}")
                    except Exception as e:
                        logger.error(f"Failed to save cover art URL to project {project_id}: {e}")
                        # Don't fail the entire operation if this fails
                
                # Track usage
                await track_usage(
                    user_id=user_id,
                    usage_data={
                        'operation': 'cover_art_generation',
                        'cost': 0.10,  # Approximate cost for DALL-E 3 HD generation
                        'project_id': project_id,
                        'job_id': job_id,
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    }
                )
                
            except Exception as e:
                logger.error(f"Background cover art generation failed: {e}")
                logger.error(f"Exception type: {type(e).__name__}")
                logger.error(f"Exception details: {str(e)}")
                failed_job = _cover_art_jobs.get(job_id)
                if failed_job:
                    failed_job.status = 'failed'
                    failed_job.error = str(e)
                    failed_job.completed_at = datetime.now(timezone.utc)
                    _cover_art_jobs[job_id] = failed_job
                    
                    # Update failure in Firestore
                    if can_use_firestore:
                        await db.firestore.update_cover_art_job(job_id, {
                            'status': 'failed',
                            'error': str(e),
                            'completed_at': datetime.now(timezone.utc).isoformat(),
                            'attempt_number': attempt_number
                        })
        
        background_tasks.add_task(generate_cover_background)
        
        return {
            'success': True,
            'job_id': job_id,
            'status': 'pending',
            'message': 'Cover art generation started. Use the job_id to check progress.'
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start cover art generation for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start cover art generation"
        )


@router.get("/{project_id}/cover-art")
async def get_cover_art_status(
    project_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get cover art status for a project."""
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
        
        if not _allow_cover_art_access(user_id, owner_id, collaborators):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )
        
        # Check service availability
        service_available = bool(cover_art_service and cover_art_service.is_available())
        openai_available = bool(cover_art_service and cover_art_service.openai_client is not None)
        firebase_available = bool(cover_art_service and cover_art_service.firebase_bucket is not None)
        
        logger.info(f"Cover art service status check - Available: {service_available}, OpenAI: {openai_available}, Firebase: {firebase_available}")
        
        # Get latest cover art job for this project
        from backend.database_integration import get_database_adapter
        db = get_database_adapter()
        can_use_firestore = _can_use_firestore_cover_art(db)
        user_jobs = await db.firestore.get_user_cover_art_jobs(user_id, project_id, limit=1) if can_use_firestore else []
        
        if user_jobs:
            latest_job = user_jobs[0]
            job_id = latest_job.get('job_id')
            
            # Also check in-memory jobs
            memory_job = _cover_art_jobs.get(job_id)
            if memory_job:
                return {
                    'job_id': memory_job.job_id,
                    'status': memory_job.status,
                    'image_url': memory_job.image_url,
                    'prompt': memory_job.prompt,
                    'error': memory_job.error,
                    'message': f'Cover art {memory_job.status}',
                    'created_at': memory_job.created_at.isoformat() if memory_job.created_at else None,
                    'completed_at': memory_job.completed_at.isoformat() if memory_job.completed_at else None,
                    'attempt_number': memory_job.attempt_number,
                    'service_available': service_available,
                    'openai_available': openai_available,
                    'firebase_available': firebase_available
                }
            else:
                # Return Firestore job data
                return {
                    'job_id': latest_job.get('job_id'),
                    'status': latest_job.get('status', 'unknown'),
                    'image_url': latest_job.get('image_url'),
                    'prompt': latest_job.get('prompt'),
                    'error': latest_job.get('error'),
                    'message': f'Cover art {latest_job.get("status", "unknown")}',
                    'created_at': latest_job.get('created_at'),
                    'completed_at': latest_job.get('completed_at'),
                    'attempt_number': latest_job.get('attempt_number', 1),
                    'service_available': service_available,
                    'openai_available': openai_available,
                    'firebase_available': firebase_available
                }
        # If no Firestore jobs, check in-memory jobs
        memory_job = _get_latest_memory_cover_art_job(user_id, project_id)
        if memory_job:
            return {
                'job_id': memory_job.job_id,
                'status': memory_job.status,
                'image_url': memory_job.image_url,
                'prompt': memory_job.prompt,
                'error': memory_job.error,
                'message': f'Cover art {memory_job.status}',
                'created_at': memory_job.created_at.isoformat() if memory_job.created_at else None,
                'completed_at': memory_job.completed_at.isoformat() if memory_job.completed_at else None,
                'attempt_number': memory_job.attempt_number,
                'service_available': service_available,
                'openai_available': openai_available,
                'firebase_available': firebase_available
            }

        # No cover art jobs found
        return {
            'status': 'not_started',
            'message': 'No cover art generated yet',
            'service_available': service_available,
            'openai_available': openai_available,
            'firebase_available': firebase_available
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get cover art status for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get cover art status"
        ) 


@router.post("/{project_id}/title-recommendations")
async def generate_title_recommendations(
    project_id: str,
    request: TitleRecommendationRequest,
    current_user: dict = Depends(get_current_user)
):
    """Generate title recommendations grounded in project materials."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )

        project = await get_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )

        owner_id = project.get('metadata', {}).get('owner_id')
        collaborators = project.get('metadata', {}).get('collaborators', [])
        if not _allow_cover_art_access(user_id, owner_id, collaborators):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )

        book_bible_content = project.get('book_bible', {}).get('content', '')
        if not book_bible_content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Book bible content is required to generate title recommendations"
            )

        from backend.database_integration import get_database_adapter
        db = get_database_adapter()
        try:
            reference_files_data = await db.get_project_reference_files(project_id)
        except Exception as e:
            logger.warning(f"Adapter get_project_reference_files failed for title recommendations: {e}")
            reference_files_data = []

        reference_files = {}
        for ref_file in reference_files_data or []:
            filename = ref_file.get('filename', '')
            content = ref_file.get('content', '')
            if filename and content:
                reference_files[filename] = content

        count = int(request.count or 6)
        count = max(3, min(count, 10))

        service = require_title_service(user_id=user_id)
        if not service.is_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Title recommendation service unavailable: OpenAI API key not configured."
            )

        vector_context = ""
        try:
            vector_service = require_vector_store_service()
            if vector_service.available:
                await vector_service.ensure_project_vector_store(
                    project_id=project_id,
                    user_id=user_id,
                    project_title=project.get('metadata', {}).get('title')
                )
                await vector_service.ensure_user_vector_store(user_id)
                vector_context = await vector_service.retrieve_title_context(project_id, user_id)
        except Exception as e:
            logger.warning(f"Vector context unavailable for title recommendations: {e}")

        recommendations = await service.generate_recommendations(
            book_bible_content=book_bible_content,
            reference_files=reference_files,
            vector_context=vector_context,
            current_title=project.get('metadata', {}).get('title'),
            max_results=count
        )

        return {
            'recommendations': recommendations,
            'count': len(recommendations)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate title recommendations for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate title recommendations"
        )

# ----------------------------
# DELETE COVER ART ENDPOINT
# ----------------------------
@router.delete("/{project_id}/cover-art/{job_id}")
async def delete_cover_art(
    project_id: str,
    job_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Permanently delete a generated cover-art image and its job entry."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user auth")

        # Verify ownership
        project = await get_project(project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

        owner_id = project.get('metadata', {}).get('owner_id')
        collaborators = project.get('metadata', {}).get('collaborators', [])
        if not _allow_cover_art_access(user_id, owner_id, collaborators):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        from backend.database_integration import get_database_adapter
        db = get_database_adapter()
        can_use_firestore = _can_use_firestore_cover_art(db)
        job = await db.firestore.get_cover_art_job(job_id) if can_use_firestore else None
        if not job:
            memory_job = _cover_art_jobs.get(job_id)
            if memory_job and memory_job.project_id == project_id:
                job = {
                    'job_id': memory_job.job_id,
                    'project_id': memory_job.project_id,
                    'storage_path': memory_job.storage_path
                }
        if not job or job.get('project_id') != project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover art job not found")

        # Delete blob from Firebase Storage
        if job.get('storage_path') and cover_art_service and cover_art_service.firebase_bucket:
            try:
                blob = cover_art_service.firebase_bucket.blob(job['storage_path'])
                blob.delete()
            except Exception as e:
                logger.warning(f"Failed to delete blob: {e}")

        # Mark Firestore doc as deleted
        if can_use_firestore:
            await db.firestore.update_cover_art_job(job_id, {
                'status': 'deleted',
                'deleted_at': datetime.now(timezone.utc).isoformat()
            })

        # Remove from memory store
        _cover_art_jobs.pop(job_id, None)

        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete cover art job {job_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete cover art") 