#!/usr/bin/env python3
"""
Mobile API v2 - Lightweight endpoints for the mobile reader/player app.
Provides library listing, chapter content, audiobook info, and progress sync.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

try:
    from backend.auth_middleware import get_current_user
    from backend.database_integration import get_user_projects, get_project, get_project_chapters
    from backend.services.firestore_service import get_firestore_client
except Exception:
    from auth_middleware import get_current_user
    from database_integration import get_user_projects, get_project, get_project_chapters
    from services.firestore_service import get_firestore_client

try:
    from google.cloud.firestore_v1.base_query import FieldFilter
except Exception:
    FieldFilter = None

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v2/mobile", tags=["mobile-v2"])


ANONYMOUS_USER_ID = "anonymous-user"


def _require_authenticated_user(user_id: Optional[str]) -> str:
    """Return user_id or raise 401 if missing / anonymous."""
    if not user_id or user_id == ANONYMOUS_USER_ID:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user_id


def _verify_project_access(project_data: dict, user_id: str):
    """Raise 403 if user doesn't own, collaborate on, or have public access to the project."""
    metadata = project_data.get("metadata") or {}
    visibility = metadata.get("visibility", "private")
    if visibility == "public":
        return
    owner_id = metadata.get("owner_id")
    collaborators = metadata.get("collaborators", [])
    if owner_id != user_id and user_id not in collaborators:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this project",
        )


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class ReadingProgress(BaseModel):
    chapter_number: int = 1
    scroll_position: float = 0.0
    updated_at: Optional[str] = None

class ListeningProgress(BaseModel):
    chapter_number: int = 1
    position_seconds: float = 0.0
    updated_at: Optional[str] = None

class BookSummary(BaseModel):
    id: str
    title: str
    genre: str = "Fiction"
    status: str = "active"
    visibility: str = "private"
    author_name: Optional[str] = None
    chapter_count: int = 0
    word_count: int = 0
    cover_art_url: Optional[str] = None
    has_audiobook: bool = False
    audiobook_url: Optional[str] = None
    updated_at: Optional[str] = None
    reading_progress: Optional[ReadingProgress] = None
    listening_progress: Optional[ListeningProgress] = None

class LibraryResponse(BaseModel):
    books: List[BookSummary]
    public_books: List[BookSummary] = []
    total: int

class ChapterContent(BaseModel):
    chapter_number: int
    chapter_id: str
    title: Optional[str] = None
    word_count: int = 0
    content: str

class ChaptersResponse(BaseModel):
    chapters: List[ChapterContent]
    total: int
    project_title: str

class AudiobookInfoResponse(BaseModel):
    job_id: str
    status: str
    chapter_urls: Dict[int, str] = {}
    full_book_url: Optional[str] = None
    total_duration_seconds: Optional[float] = None
    chapter_count: int = 0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_cover_art_url(project_id: str) -> Optional[str]:
    try:
        client = get_firestore_client()
        query = client.collection('cover_art_jobs').where(
            filter=FieldFilter('project_id', '==', project_id)
        )
        latest = None
        latest_ts = None
        for doc in query.stream():
            data = doc.to_dict() or {}
            ts = data.get('created_at') or data.get('updated_at')
            if ts and (latest_ts is None or ts > latest_ts):
                latest = data
                latest_ts = ts
        if latest:
            return latest.get('image_url')
    except Exception as e:
        logger.debug(f"Cover art lookup failed for {project_id}: {e}")
    return None

async def _get_latest_audiobook(project_id: str) -> Optional[Dict[str, Any]]:
    try:
        client = get_firestore_client()
        query = client.collection('audiobook_jobs').where(
            filter=FieldFilter('project_id', '==', project_id)
        ).where(
            filter=FieldFilter('status', '==', 'completed')
        )
        latest = None
        latest_ts = None
        for doc in query.stream():
            data = doc.to_dict() or {}
            ts = data.get('completed_at') or data.get('created_at')
            if ts and (latest_ts is None or ts > latest_ts):
                latest = data
                latest_ts = ts
                latest['job_id'] = doc.id
        return latest
    except Exception as e:
        logger.debug(f"Audiobook lookup failed for {project_id}: {e}")
    return None

def _get_progress(client, user_id: str, project_id: str):
    reading = None
    listening = None
    try:
        doc = client.collection('users').document(user_id).collection('mobile_progress').document(project_id).get()
        if doc.exists:
            data = doc.to_dict() or {}
            rp = data.get('reading')
            if rp:
                reading = ReadingProgress(
                    chapter_number=rp.get('chapter_number', 1),
                    scroll_position=rp.get('scroll_position', 0),
                    updated_at=str(rp.get('updated_at', '')),
                )
            lp = data.get('listening')
            if lp:
                listening = ListeningProgress(
                    chapter_number=lp.get('chapter_number', 1),
                    position_seconds=lp.get('position_seconds', 0),
                    updated_at=str(lp.get('updated_at', '')),
                )
    except Exception as e:
        logger.debug(f"Progress lookup failed for {user_id}/{project_id}: {e}")
    return reading, listening

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/library", response_model=LibraryResponse)
async def get_mobile_library(current_user: dict = Depends(get_current_user)):
    """Lightweight library listing optimized for mobile.

    Performance note: cover art, audiobook, and chapter-count lookups run
    per-book (N+1).  Acceptable for small libraries (<50 books); for scale,
    batch Firestore queries or add a denormalized mobile_library_cache
    collection updated via Cloud Functions on project/audiobook changes.
    """
    user_id = _require_authenticated_user(current_user.get('user_id'))

    projects_data = await get_user_projects(user_id)
    client = get_firestore_client()

    books: List[BookSummary] = []
    for proj in projects_data:
        metadata = proj.get('metadata', {})
        settings = proj.get('settings', {})
        progress = proj.get('progress', {})
        project_id = proj.get('id') or metadata.get('project_id')
        if not project_id:
            continue

        # Chapter stats
        chapter_count = progress.get('chapters_completed', 0)
        word_count = progress.get('current_word_count', 0)
        if chapter_count == 0:
            try:
                chapters_ref = (
                    client.collection('users').document(user_id)
                    .collection('projects').document(project_id)
                    .collection('chapters')
                )
                for doc in chapters_ref.stream():
                    ch = doc.to_dict() or {}
                    ch_num = 0
                    try:
                        ch_num = int(ch.get('chapter_number') or 0)
                    except Exception:
                        pass
                    if ch_num > 0:
                        chapter_count += 1
                        wc = ch.get('word_count') or (ch.get('metadata') or {}).get('word_count') or 0
                        try:
                            word_count += int(wc)
                        except Exception:
                            pass
            except Exception:
                pass

        # Cover art
        cover_url = None
        ca = proj.get('cover_art')
        if isinstance(ca, dict):
            cover_url = ca.get('image_url')
        if not cover_url:
            cover_url = await _get_cover_art_url(project_id)

        # Audiobook
        audiobook = await _get_latest_audiobook(project_id)
        has_audiobook = audiobook is not None
        audiobook_url = audiobook.get('full_book_url') if audiobook else None

        # Progress
        reading, listening = _get_progress(client, user_id, project_id)

        updated_at = metadata.get('updated_at') or metadata.get('created_at')
        if updated_at and isinstance(updated_at, datetime):
            updated_at = updated_at.isoformat()
        elif updated_at:
            updated_at = str(updated_at)

        books.append(BookSummary(
            id=project_id,
            title=metadata.get('title', 'Untitled'),
            genre=settings.get('genre', 'Fiction'),
            status=metadata.get('status', 'active'),
            visibility=metadata.get('visibility', 'private'),
            chapter_count=chapter_count,
            word_count=word_count,
            cover_art_url=cover_url,
            has_audiobook=has_audiobook,
            audiobook_url=audiobook_url,
            updated_at=updated_at,
            reading_progress=reading,
            listening_progress=listening,
        ))

    # Public projects from other users
    public_books: List[BookSummary] = []
    try:
        if FieldFilter:
            query = client.collection("projects").where(
                filter=FieldFilter("metadata.visibility", "==", "public")
            )
            pub_docs = list(query.limit(50).stream())
            for doc in pub_docs:
                data = doc.to_dict() or {}
                pub_metadata = data.get("metadata", {})
                pub_settings = data.get("settings", {})
                pub_id = doc.id
                pub_owner = pub_metadata.get("owner_id")
                if pub_owner == user_id:
                    continue

                pub_cover = None
                pub_ca = data.get("cover_art")
                if isinstance(pub_ca, dict):
                    pub_cover = pub_ca.get("image_url")
                if not pub_cover:
                    pub_cover = await _get_cover_art_url(pub_id)

                pub_audiobook = await _get_latest_audiobook(pub_id)

                pub_progress_r, pub_progress_l = _get_progress(client, user_id, pub_id)

                pub_updated = pub_metadata.get("updated_at") or pub_metadata.get("created_at")
                if pub_updated and isinstance(pub_updated, datetime):
                    pub_updated = pub_updated.isoformat()
                elif pub_updated:
                    pub_updated = str(pub_updated)

                pub_chapter_count = data.get("progress", {}).get("chapters_completed", 0)
                pub_word_count = data.get("progress", {}).get("current_word_count", 0)

                public_books.append(BookSummary(
                    id=pub_id,
                    title=pub_metadata.get("title", "Untitled"),
                    genre=pub_settings.get("genre", "Fiction"),
                    status=pub_metadata.get("status", "active"),
                    visibility="public",
                    author_name=pub_metadata.get("owner_display_name"),
                    chapter_count=pub_chapter_count,
                    word_count=pub_word_count,
                    cover_art_url=pub_cover,
                    has_audiobook=pub_audiobook is not None,
                    audiobook_url=pub_audiobook.get("full_book_url") if pub_audiobook else None,
                    updated_at=pub_updated,
                    reading_progress=pub_progress_r,
                    listening_progress=pub_progress_l,
                ))
    except Exception as e:
        logger.debug(f"Public books query failed: {e}")

    return LibraryResponse(books=books, public_books=public_books, total=len(books) + len(public_books))


@router.get("/book/{project_id}/chapters", response_model=ChaptersResponse)
async def get_mobile_chapters(
    project_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get all chapters for a book, optimized for mobile reader."""
    user_id = _require_authenticated_user(current_user.get('user_id'))

    project = await get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    _verify_project_access(project, user_id)

    chapters_data = await get_project_chapters(project_id)
    chapters: List[ChapterContent] = []
    for ch in chapters_data:
        content = ch.get('content') or ''
        versions = ch.get('versions', [])
        if versions:
            latest = sorted(versions, key=lambda v: v.get('version_number', 0))
            if latest:
                content = latest[-1].get('content') or content

        chapter_number = ch.get('chapter_number', 0)
        if chapter_number <= 0:
            continue

        chapters.append(ChapterContent(
            chapter_number=chapter_number,
            chapter_id=ch.get('chapter_id') or ch.get('id') or f"ch_{chapter_number}",
            title=ch.get('title'),
            word_count=ch.get('word_count') if ch.get('word_count') is not None else (ch.get('metadata') or {}).get('word_count', 0),
            content=content,
        ))

    chapters.sort(key=lambda c: c.chapter_number)

    project_title = 'Untitled'
    if isinstance(project, dict):
        project_title = project.get('metadata', {}).get('title', 'Untitled')

    return ChaptersResponse(
        chapters=chapters,
        total=len(chapters),
        project_title=project_title,
    )


@router.get("/book/{project_id}/audiobook")
async def get_mobile_audiobook_info(
    project_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get audiobook info and download URLs for a project."""
    user_id = _require_authenticated_user(current_user.get('user_id'))

    project = await get_project(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    _verify_project_access(project, user_id)

    audiobook = await _get_latest_audiobook(project_id)
    if not audiobook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No audiobook found")

    chapter_urls_raw = audiobook.get('chapter_urls') or {}
    chapter_urls: Dict[int, str] = {}
    for k, v in chapter_urls_raw.items():
        try:
            chapter_urls[int(k)] = v
        except (ValueError, TypeError):
            logger.debug(f"Skipping non-numeric chapter_url key: {k}")
            continue

    return AudiobookInfoResponse(
        job_id=audiobook.get('job_id', ''),
        status=audiobook.get('status', 'completed'),
        chapter_urls=chapter_urls,
        full_book_url=audiobook.get('full_book_url'),
        total_duration_seconds=audiobook.get('total_duration_seconds'),
        chapter_count=len(chapter_urls),
    )


@router.put("/progress/{project_id}/reading")
async def update_reading_progress(
    project_id: str,
    progress: ReadingProgress,
    current_user: dict = Depends(get_current_user)
):
    """Update reading progress for a project."""
    user_id = _require_authenticated_user(current_user.get('user_id'))

    try:
        client = get_firestore_client()
        doc_ref = client.collection('users').document(user_id).collection('mobile_progress').document(project_id)
        doc_ref.set({
            'reading': {
                'chapter_number': progress.chapter_number,
                'scroll_position': progress.scroll_position,
                'updated_at': datetime.now(timezone.utc),
            }
        }, merge=True)
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to update reading progress: {e}")
        raise HTTPException(status_code=500, detail="Failed to save progress")


@router.put("/progress/{project_id}/listening")
async def update_listening_progress(
    project_id: str,
    progress: ListeningProgress,
    current_user: dict = Depends(get_current_user)
):
    """Update listening progress for a project."""
    user_id = _require_authenticated_user(current_user.get('user_id'))

    try:
        client = get_firestore_client()
        doc_ref = client.collection('users').document(user_id).collection('mobile_progress').document(project_id)
        doc_ref.set({
            'listening': {
                'chapter_number': progress.chapter_number,
                'position_seconds': progress.position_seconds,
                'updated_at': datetime.now(timezone.utc),
            }
        }, merge=True)
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to update listening progress: {e}")
        raise HTTPException(status_code=500, detail="Failed to save progress")
