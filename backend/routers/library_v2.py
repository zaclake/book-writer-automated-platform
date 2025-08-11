#!/usr/bin/env python3
"""
Library API v2 - Public/Private Book Library Endpoints
Provides endpoints to list user's books and public books, and to serve EPUB for reader.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer

try:
    from backend.auth_middleware import get_current_user
    from backend.database_integration import get_database_adapter
except ImportError:
    from auth_middleware import get_current_user
    from database_integration import get_database_adapter

import httpx


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v2/library", tags=["library-v2"])
security = HTTPBearer()


async def _get_latest_cover_art_url(project_id: str) -> Optional[str]:
    """Fetch latest cover art image_url from cover_art_jobs for a project."""
    try:
        try:
            from backend.services.firestore_service import get_firestore_client
        except Exception:
            from services.firestore_service import get_firestore_client  # type: ignore

        client = get_firestore_client()
        from google.cloud import firestore  # type: ignore
        query = (
            client.collection('cover_art_jobs')
            .where('project_id', '==', project_id)
            .order_by('created_at', direction=firestore.Query.DESCENDING)
            .limit(1)
        )
        docs = list(query.stream())
        if docs:
            data = docs[0].to_dict() or {}
            return data.get('image_url')
    except Exception as e:
        logger.warning(f"Failed to fetch latest cover art for {project_id}: {e}")
    return None

def _project_card_from_project(
    project: Dict[str, Any],
    publishing: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    metadata = project.get("metadata", {})
    settings = project.get("settings", {})

    # Try to detect cover URL from project (and allow callers to inject merged fields)
    cover_url = None
    if isinstance(project.get("cover_art"), dict):
        cover_url = project.get("cover_art", {}).get("image_url")

    epub_url = None
    pdf_url = None
    if publishing and isinstance(publishing.get("latest"), dict):
        epub_url = publishing.get("latest", {}).get("epub_url")
        pdf_url = publishing.get("latest", {}).get("pdf_url")
    elif isinstance(project.get("publishing"), dict) and isinstance(project["publishing"].get("latest"), dict):
        epub_url = project["publishing"]["latest"].get("epub_url")
        pdf_url = project["publishing"]["latest"].get("pdf_url")

    owner_display_name = metadata.get("owner_display_name") or None

    return {
        "project_id": metadata.get("project_id") or project.get("id"),
        "title": metadata.get("title"),
        "owner_id": metadata.get("owner_id"),
        "author_name": owner_display_name,
        "genre": settings.get("genre"),
        "status": metadata.get("status", "active"),
        "visibility": metadata.get("visibility", "private"),
        "cover_url": cover_url,
        "epub_url": epub_url,
        "pdf_url": pdf_url,
        "updated_at": metadata.get("updated_at") or metadata.get("created_at"),
    }


async def _get_root_project_doc(project_id: str) -> Optional[Dict[str, Any]]:
    """Fetch the root projects/{project_id} document if present."""
    try:
        from backend.services.firestore_service import get_firestore_client
    except Exception:
        from services.firestore_service import get_firestore_client  # type: ignore

    try:
        client = get_firestore_client()
        doc = client.collection("projects").document(project_id).get()
        if doc.exists:
            data = doc.to_dict()
            data["id"] = project_id
            return data
    except Exception as e:
        logger.warning(f"Failed to read root project doc {project_id}: {e}")
    return None


@router.get("/")
async def get_library(current_user: dict = Depends(get_current_user), limit: int = 24, cursor: Optional[str] = None):
    """Return user's projects and public projects for library view."""
    try:
        user_id = current_user.get("user_id")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user authentication")

        db = get_database_adapter()

        # User projects
        user_projects: List[Dict[str, Any]] = await db.get_user_projects(user_id)
        my_cards: List[Dict[str, Any]] = []
        for p in user_projects:
            # Enrich with root publishing data if available
            project_id = p.get("metadata", {}).get("project_id") or p.get("id")
            root_doc = await _get_root_project_doc(project_id) if project_id else None
            publishing = (root_doc or {}).get("publishing") if root_doc else p.get("publishing")
            # Merge cover_art from root doc if not present on user-scoped project
            if root_doc and not p.get("cover_art") and root_doc.get("cover_art"):
                # Avoid mutating original
                p = dict(p)
                p["cover_art"] = root_doc.get("cover_art")
            # Fallback: if still no cover_art, pull from latest cover_art_jobs
            if not (p.get('cover_art') and p['cover_art'].get('image_url')) and project_id:
                url = await _get_latest_cover_art_url(project_id)
                if url:
                    p = dict(p)
                    p['cover_art'] = {'image_url': url}
            my_cards.append(_project_card_from_project(p, publishing))

        # Public projects (from root collection with visibility == public)
        public_cards: List[Dict[str, Any]] = []
        next_cursor: Optional[str] = None
        try:
            # Prefer querying root collection for public projects
            from google.cloud import firestore
            try:
                from backend.services.firestore_service import get_firestore_client
            except Exception:
                from services.firestore_service import get_firestore_client  # type: ignore

            client = get_firestore_client()
            query = client.collection("projects").where("metadata.visibility", "==", "public")

            # Pagination by updated_at desc if available, else by title
            order_by_field = "metadata.updated_at"
            try:
                if cursor:
                    # Interpret cursor as ISO datetime
                    try:
                        cursor_dt = datetime.fromisoformat(cursor)
                        query = query.where(order_by_field, "<", cursor_dt)
                    except Exception:
                        pass
                query = query.order_by(order_by_field, direction=firestore.Query.DESCENDING).limit(limit)
            except Exception:
                # Fallback ordering by title
                query = query.order_by("metadata.title").limit(limit)

            docs = list(query.stream())
            for doc in docs:
                data = doc.to_dict() or {}
                data["id"] = doc.id
                # Skip if owned by current user (to avoid duplication with my_cards)
                owner_id = data.get("metadata", {}).get("owner_id")
                if owner_id == user_id:
                    continue
                # Ensure cover_art present, else fallback to latest cover_art_jobs
                if not (data.get('cover_art') and isinstance(data['cover_art'], dict) and data['cover_art'].get('image_url')):
                    url = await _get_latest_cover_art_url(data.get('id') or data.get('metadata', {}).get('project_id'))
                    if url:
                        data = dict(data)
                        data['cover_art'] = {'image_url': url}
                public_cards.append(_project_card_from_project(data, data.get("publishing")))

            if not docs:
                # Fallback: query all user subcollections via collection group 'projects'
                try:
                    cg = client.collection_group('projects').where('metadata.visibility', '==', 'public')
                    # No reliable pagination without composite index on updated_at; limit for safety
                    cg_docs = list(cg.limit(limit).stream())
                    for d in cg_docs:
                        data = d.to_dict() or {}
                        # collection group doc id is project id
                        data['id'] = d.id
                        owner_id = data.get('metadata', {}).get('owner_id')
                        if owner_id == user_id:
                            continue
                        public_cards.append(_project_card_from_project(data, data.get('publishing')))
                except Exception as ee:
                    logger.warning(f"Collection group fallback failed: {ee}")

            if docs:
                last = docs[-1]
                last_updated = (last.to_dict() or {}).get("metadata", {}).get("updated_at")
                if isinstance(last_updated, datetime):
                    next_cursor = last_updated.isoformat()
        except Exception as e:
            logger.error(f"Failed to query public projects: {e}")
            public_cards = []
            next_cursor = None

        # Filter to only published (has EPUB). Treat published as complete for library purposes.
        my_cards = [c for c in my_cards if c.get("epub_url")]
        public_cards = [c for c in public_cards if c.get("epub_url")]

        return {
            "my_projects": my_cards,
            "public_projects": public_cards,
            "next_cursor": next_cursor,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to load library: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to load library")


@router.get("/public")
async def get_public_library(current_user: dict = Depends(get_current_user), limit: int = 24, cursor: Optional[str] = None):
    """Return only public projects with pagination."""
    try:
        user_id = current_user.get("user_id")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user authentication")

        from google.cloud import firestore
        try:
            from backend.services.firestore_service import get_firestore_client
        except Exception:
            from services.firestore_service import get_firestore_client  # type: ignore

        client = get_firestore_client()
        query = client.collection("projects").where("metadata.visibility", "==", "public")
        order_by_field = "metadata.updated_at"
        next_cursor: Optional[str] = None
        try:
            if cursor:
                try:
                    cursor_dt = datetime.fromisoformat(cursor)
                    query = query.where(order_by_field, "<", cursor_dt)
                except Exception:
                    pass
            query = query.order_by(order_by_field, direction=firestore.Query.DESCENDING).limit(limit)
        except Exception:
            query = query.order_by("metadata.title").limit(limit)

        docs = list(query.stream())
        projects: List[Dict[str, Any]] = []
        for doc in docs:
            data = doc.to_dict() or {}
            data["id"] = doc.id
            projects.append(_project_card_from_project(data, data.get("publishing")))

        if docs:
            last = docs[-1]
            last_updated = (last.to_dict() or {}).get("metadata", {}).get("updated_at")
            if isinstance(last_updated, datetime):
                next_cursor = last_updated.isoformat()

        # Filter to only published (has EPUB)
        projects = [c for c in projects if c.get("epub_url")]
        return {"projects": projects, "next_cursor": next_cursor}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to load public library: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to load public library")


@router.get("/book/{project_id}")
async def get_book_card(project_id: str, current_user: dict = Depends(get_current_user)):
    """Return minimal card info and permissions for a single project."""
    try:
        user_id = current_user.get("user_id")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user authentication")

        db = get_database_adapter()
        project = await db.get_project(project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

        metadata = project.get("metadata", {})
        owner_id = metadata.get("owner_id")
        collaborators = metadata.get("collaborators", [])
        visibility = metadata.get("visibility", "private")

        root_doc = await _get_root_project_doc(project_id)
        publishing = (root_doc or {}).get("publishing") or project.get("publishing")
        card = _project_card_from_project(project, publishing)

        epub_url = card.get("epub_url")
        is_owner_or_collab = (user_id == owner_id) or (user_id in collaborators)
        is_public = visibility == "public"
        can_access_public = is_public

        can_read = bool(epub_url) and (is_owner_or_collab or can_access_public)
        can_download = can_read

        return {**card, "can_read": can_read, "can_download": can_download}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get book card for {project_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to load book details")


@router.get("/book/{project_id}/reader")
async def get_book_reader_payload(project_id: str, current_user: dict = Depends(get_current_user)):
    """Return reader payload with metadata and stream URL for EPUB."""
    card = await get_book_card(project_id, current_user)
    if not card.get("can_read"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    # Provide same-origin EPUB stream URL via this API namespace
    epub_stream_url = f"/v2/library/book/{project_id}/epub"
    return {
        "title": card.get("title"),
        "author_name": card.get("author_name"),
        "cover_url": card.get("cover_url"),
        "genre": card.get("genre"),
        "epub_stream_url": epub_stream_url,
    }


@router.get("/book/{project_id}/epub")
async def stream_book_epub(project_id: str, current_user: dict = Depends(get_current_user)):
    """Stream the EPUB file to enable same-origin reading/downloading."""
    try:
        card = await get_book_card(project_id, current_user)
        if not card.get("can_read"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        epub_url = card.get("epub_url")
        if not epub_url:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="EPUB not available")

        # Stream via httpx to avoid CORS and present as same-origin
        async with httpx.AsyncClient(timeout=None) as client:
            r = await client.get(epub_url, follow_redirects=True)
            if r.status_code != 200:
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to fetch EPUB from storage")

            headers = {
                "Content-Type": "application/epub+zip",
                "Content-Disposition": f"inline; filename=book-{project_id}.epub",
            }

            async def file_iterator(chunk_size: int = 1024 * 128):
                async for chunk in r.aiter_bytes(chunk_size=chunk_size):
                    yield chunk

            return StreamingResponse(file_iterator(), headers=headers)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stream EPUB for {project_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to stream EPUB")


@router.get("/book/{project_id}/pdf")
async def stream_book_pdf(project_id: str, current_user: dict = Depends(get_current_user)):
    """Stream the PDF file (owned or public) to enable same-origin download."""
    try:
        card = await get_book_card(project_id, current_user)
        # Re-check access: same rules as read (owner/collab or public)
        visibility_ok = card.get("can_read")
        if not visibility_ok:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        # Fetch latest card again to ensure we get fresh publishing urls
        db_card = card
        pdf_url = db_card.get("pdf_url")
        if not pdf_url:
            # If pdf not available, report 404
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF not available")

        async with httpx.AsyncClient(timeout=None) as client:
            r = await client.get(pdf_url, follow_redirects=True)
            if r.status_code != 200:
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to fetch PDF from storage")

            headers = {
                "Content-Type": "application/pdf",
                "Content-Disposition": f"inline; filename=book-{project_id}.pdf",
            }

            async def file_iterator(chunk_size: int = 1024 * 128):
                async for chunk in r.aiter_bytes(chunk_size=chunk_size):
                    yield chunk

            return StreamingResponse(file_iterator(), headers=headers)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stream PDF for {project_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to stream PDF")


