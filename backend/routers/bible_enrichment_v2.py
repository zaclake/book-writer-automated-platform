#!/usr/bin/env python3
"""
Bible Enrichment API (v2)

Endpoints:
  GET  /v2/bible-enrichment/questions
       Return the canonical question registry (id, label, helper text, model).
       Used by the frontend to render the intake form.

  POST /v2/bible-enrichment/preview
       Stateless: take a draft bible + draft answers + skipped list, run the
       enrichment pipeline (auto-fill + anti-cliché evaluation), return the
       fully enriched payload. Used by the create-project flow BEFORE the
       project exists.

  POST /v2/projects/{project_id}/bible-enrichment
       Persist enrichment for an existing project. Re-renders the bible's
       Author Intent appendix and updates `book_bible.content` accordingly.

  GET  /v2/projects/{project_id}/bible-enrichment
       Read the persisted enrichment payload for a project.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2", tags=["bible-enrichment-v2"])


# --- Auth + DB imports with the codebase's standard fallback ladder ---------

try:
    from backend.auth_middleware import get_current_user
except Exception:
    try:
        from auth_middleware import get_current_user  # type: ignore
    except Exception:
        from ..auth_middleware import get_current_user  # type: ignore

try:
    from backend.database_integration import get_project, get_database_adapter
except Exception:
    try:
        from database_integration import get_project, get_database_adapter  # type: ignore
    except Exception:
        from ..database_integration import get_project, get_database_adapter  # type: ignore

try:
    from backend.services.bible_enrichment import (
        EnrichmentRunner,
        EnrichmentPromptRegistry,
        QUESTION_IDS,
        merge_bible_with_enrichment,
        enrichment_result_from_dict,
    )
except Exception:
    from ..services.bible_enrichment import (  # type: ignore
        EnrichmentRunner,
        EnrichmentPromptRegistry,
        QUESTION_IDS,
        merge_bible_with_enrichment,
        enrichment_result_from_dict,
    )

try:
    from backend.services.voice_exemplars import (
        list_for_user_payload as voice_list_for_user,
        get_registry as voice_get_registry,
        compose_bible_preface as voice_compose_bible_preface,
        MAX_SELECTIONS as VOICE_MAX_SELECTIONS,
    )
except Exception:
    from ..services.voice_exemplars import (  # type: ignore
        list_for_user_payload as voice_list_for_user,
        get_registry as voice_get_registry,
        compose_bible_preface as voice_compose_bible_preface,
        MAX_SELECTIONS as VOICE_MAX_SELECTIONS,
    )


# --- Request / Response models ----------------------------------------------


class EnrichmentPreviewRequest(BaseModel):
    bible: str
    genre: str = "Fiction"
    user_answers: Optional[Dict[str, str]] = None
    skipped: Optional[List[str]] = None
    prior_references: Optional[Dict[str, str]] = None
    project_id: Optional[str] = None  # informational; enrichment may be unbound


class EnrichmentSaveRequest(BaseModel):
    user_answers: Optional[Dict[str, str]] = None
    skipped: Optional[List[str]] = None
    use_existing: bool = False  # if True, do not re-run; expect `payload`
    payload: Optional[Dict[str, Any]] = None  # pre-computed result from /preview


# --- Helpers ----------------------------------------------------------------


_REGISTRY_SINGLETON: Optional[EnrichmentPromptRegistry] = None


def _get_registry() -> EnrichmentPromptRegistry:
    global _REGISTRY_SINGLETON
    if _REGISTRY_SINGLETON is None:
        _REGISTRY_SINGLETON = EnrichmentPromptRegistry()
    return _REGISTRY_SINGLETON


def _runner() -> EnrichmentRunner:
    return EnrichmentRunner(registry=_get_registry())


def _check_owner(user_id: str, project: Dict[str, Any]) -> None:
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    metadata = project.get("metadata") or {}
    owner_id = metadata.get("owner_id")
    collaborators = metadata.get("collaborators") or []
    if user_id == owner_id or user_id in collaborators:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied to this project",
    )


def _project_genre(project: Dict[str, Any]) -> str:
    settings = project.get("settings") or {}
    genre = settings.get("genre") or settings.get("category")
    if genre:
        return str(genre)
    return "Fiction"


def _project_bible_content(project: Dict[str, Any]) -> str:
    bb = project.get("book_bible") or {}
    return str(bb.get("content") or "")


def _project_prior_references(project: Dict[str, Any]) -> Dict[str, str]:
    refs = project.get("references") or {}
    files = refs.get("files") if isinstance(refs, dict) else None
    out: Dict[str, str] = {}
    if isinstance(files, dict):
        for key, val in files.items():
            if isinstance(val, dict):
                content = val.get("content")
                if isinstance(content, str) and content.strip():
                    out[key.replace(".md", "")] = content
            elif isinstance(val, str):
                out[key.replace(".md", "")] = val
    return out


# --- Endpoints --------------------------------------------------------------


@router.get("/bible-enrichment/questions")
async def list_questions(current_user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Return the canonical question registry for the intake form."""
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user authentication",
        )
    registry = _get_registry()
    questions = []
    for qid in QUESTION_IDS:
        q = registry.get_question(qid)
        questions.append(
            {
                "question_id": qid,
                "question_text": q.question_text,
                "short_label": q.short_label,
                "model": q.model,
            }
        )
    return {"questions": questions, "schema_version": 1}


@router.post("/bible-enrichment/preview")
async def preview_enrichment(
    request: EnrichmentPreviewRequest,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Run the enrichment pipeline statelessly. Used during create-project intake."""
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user authentication",
        )

    bible = (request.bible or "").strip()
    if len(bible) < 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Book bible content is too short for enrichment "
                "(need at least 50 characters)."
            ),
        )

    if not _openai_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenAI service is not available. Enrichment cannot run.",
        )

    runner = _runner()
    try:
        result = await runner.run(
            project_id=request.project_id or "",
            bible=bible,
            genre=request.genre or "Fiction",
            user_answers=request.user_answers,
            skipped=request.skipped,
            prior_references=request.prior_references,
        )
    except Exception as exc:
        logger.exception("Bible enrichment preview failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Enrichment failed: {exc}",
        )

    appendix = EnrichmentRunner.compose_appendix(result)
    return {
        "enrichment": result.to_dict(),
        "appendix_markdown": appendix,
        "merged_bible": merge_bible_with_enrichment(bible, result),
    }


@router.post("/projects/{project_id}/bible-enrichment")
async def save_project_enrichment(
    project_id: str,
    request: EnrichmentSaveRequest,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Persist enrichment for an existing project and update the bible content."""
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user authentication",
        )

    project = await get_project(project_id)
    _check_owner(user_id, project)

    bible = _project_bible_content(project)
    if not bible:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project has no book bible to enrich.",
        )

    if request.use_existing:
        if not request.payload:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="use_existing=true requires a payload.",
            )
        try:
            result = enrichment_result_from_dict(request.payload)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid enrichment payload: {exc}",
            )
        if not result.project_id:
            result.project_id = project_id
    else:
        if not _openai_available():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OpenAI service is not available. Enrichment cannot run.",
            )
        runner = _runner()
        try:
            result = await runner.run(
                project_id=project_id,
                bible=bible,
                genre=_project_genre(project),
                user_answers=request.user_answers,
                skipped=request.skipped,
                prior_references=_project_prior_references(project),
            )
        except Exception as exc:
            logger.exception("Bible enrichment save failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Enrichment failed: {exc}",
            )

    # Strip any prior appendix from the bible body before re-merging so we
    # never accumulate duplicates when the user re-runs enrichment.
    cleaned_bible = _strip_existing_appendix(bible)
    merged_bible = merge_bible_with_enrichment(cleaned_bible, result)
    enrichment_dict = result.to_dict()

    db = get_database_adapter()
    if getattr(db, "use_firestore", False):
        success = await db.firestore.update_project(
            project_id,
            {
                "book_bible.content": merged_bible,
                "book_bible.bible_enrichment": enrichment_dict,
                "book_bible.last_modified": datetime.now(timezone.utc),
                "book_bible.modified_by": user_id,
                "book_bible.word_count": len(merged_bible.split()),
            },
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to persist enrichment to project.",
            )

    return {
        "success": True,
        "enrichment": enrichment_dict,
        "merged_bible_word_count": len(merged_bible.split()),
    }


@router.get("/projects/{project_id}/bible-enrichment")
async def get_project_enrichment(
    project_id: str,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Read the persisted enrichment payload for a project."""
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user authentication",
        )

    project = await get_project(project_id)
    _check_owner(user_id, project)
    bb = project.get("book_bible") or {}
    payload = bb.get("bible_enrichment") or {}
    return {
        "enrichment": payload,
        "has_enrichment": bool(payload and payload.get("answers")),
    }


# ---------------------------------------------------------------------------
# Voice exemplars (Proposal 10 — Author and Book Inspiration)
# ---------------------------------------------------------------------------


class VoiceExemplarsSaveRequest(BaseModel):
    selected: List[Dict[str, Any]]
    consent: bool = False
    consent_at: Optional[str] = None


@router.get("/voice-exemplars")
async def list_voice_exemplars(
    allow_contemporary: bool = False,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return the available voice exemplars in the seed library.

    Contemporary entries are included only when `allow_contemporary=true` AND
    the user has read the consent notice (the frontend gates this behind a
    one-time confirmation in the intake flow).
    """
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user authentication",
        )
    summaries = voice_list_for_user(allow_contemporary=allow_contemporary)
    return {
        "exemplars": summaries,
        "max_selections": VOICE_MAX_SELECTIONS,
        "schema_version": 1,
    }


@router.post("/projects/{project_id}/voice-exemplars")
async def save_project_voice_exemplars(
    project_id: str,
    request: VoiceExemplarsSaveRequest,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Persist the user's voice-exemplar selection for a project."""
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user authentication",
        )

    project = await get_project(project_id)
    _check_owner(user_id, project)

    selections = request.selected or []
    if len(selections) > VOICE_MAX_SELECTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"At most {VOICE_MAX_SELECTIONS} exemplars may be selected.",
        )

    registry = voice_get_registry()
    contemporary_attempted = False
    cleaned: List[Dict[str, Any]] = []
    for sel in selections:
        if not isinstance(sel, dict):
            continue
        author = (sel.get("author") or "").strip()
        book = (sel.get("book") or "").strip()
        if not author or not book:
            continue
        entry = registry.find(author=author, book=book)
        if entry is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown voice exemplar: {author} — {book}",
            )
        if entry.licensing_tier == "contemporary_excerpt":
            contemporary_attempted = True
            if not request.consent:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Contemporary author exemplars require explicit consent. "
                        "Set consent=true (and consent_at) before selecting."
                    ),
                )
        cleaned.append(
            {
                "author": entry.author,
                "book": entry.book,
                "rationale": (sel.get("rationale") or "").strip()[:500],
            }
        )

    payload = {
        "selected": cleaned,
        "consent": bool(request.consent and contemporary_attempted),
        "consent_at": request.consent_at,
        "schema_version": 1,
    }

    # Re-render the bible's Voice Inspiration preface (idempotent — strips any
    # previous preface before injecting).
    bible = _project_bible_content(project)
    cleaned_bible = _strip_voice_preface(bible)
    preface = voice_compose_bible_preface(payload)
    if preface:
        merged = preface + "\n\n" + cleaned_bible
    else:
        merged = cleaned_bible

    db = get_database_adapter()
    if getattr(db, "use_firestore", False):
        success = await db.firestore.update_project(
            project_id,
            {
                "book_bible.content": merged,
                "book_bible.voice_exemplars": payload,
                "book_bible.last_modified": datetime.now(timezone.utc),
                "book_bible.modified_by": user_id,
                "book_bible.word_count": len(merged.split()),
            },
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to persist voice exemplars to project.",
            )

    return {
        "success": True,
        "voice_exemplars": payload,
        "merged_bible_word_count": len(merged.split()),
    }


@router.get("/projects/{project_id}/voice-exemplars")
async def get_project_voice_exemplars(
    project_id: str,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user authentication",
        )
    project = await get_project(project_id)
    _check_owner(user_id, project)
    bb = project.get("book_bible") or {}
    payload = bb.get("voice_exemplars") or {}
    return {
        "voice_exemplars": payload,
        "has_voice_exemplars": bool(payload and payload.get("selected")),
    }


def _strip_voice_preface(bible: str) -> str:
    """Remove a previously-injected Voice Inspiration preface, if present."""
    if not bible:
        return ""
    marker = "# Voice Inspiration (planner-only)"
    idx = bible.find(marker)
    if idx == -1:
        return bible
    # Find the next blank line after the preface block (the preface ends with
    # a list block followed by a double newline before the rest of the bible).
    rest_start = bible.find("\n\n", idx)
    if rest_start == -1:
        return ""
    # Walk forward past consecutive blank lines.
    while rest_start < len(bible) and bible[rest_start] == "\n":
        rest_start += 1
    return bible[rest_start:]


# --- Helpers ----------------------------------------------------------------


def _openai_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def _strip_existing_appendix(bible: str) -> str:
    """Remove a previously-rendered Author Intent appendix, if present."""
    if not bible:
        return ""
    marker = "# Author Intent (Bible Enrichment)"
    idx = bible.find(marker)
    if idx == -1:
        return bible
    # The appendix is preceded by `\n---\n\n` (rendered by compose_appendix).
    # Walk backwards through any whitespace + horizontal rule.
    cut = idx
    # Trim the preceding "---" rule line.
    body = bible[:cut].rstrip()
    if body.endswith("---"):
        body = body[: -len("---")].rstrip()
    return body + "\n"
