#!/usr/bin/env python3
"""
Chapters API v2 - Firestore Integration with Versioning
Chapter management endpoints with full versioning support.
"""

import logging
import os
import re
import asyncio
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
import json
import importlib.util
from typing import List, Optional, Any
from fastapi import APIRouter, HTTPException, Depends, status, Query, BackgroundTasks

# Optional request correlation (rid)
try:
    from backend.utils.logging_config import request_id_contextvar, run_id_contextvar
except Exception:  # pragma: no cover
    try:
        from ..utils.logging_config import request_id_contextvar, run_id_contextvar  # type: ignore
    except Exception:
        request_id_contextvar = None  # type: ignore
        run_id_contextvar = None  # type: ignore

# Run summary helpers
try:
    from backend.utils.run_summaries import emit_summary, text_stats
except Exception:  # pragma: no cover
    from ..utils.run_summaries import emit_summary, text_stats  # type: ignore

# Stage normalization / gating (simple-default vs legacy 5-stage)
try:
    from backend.utils.generation_stage import resolve_generation_stage
except Exception:  # pragma: no cover
    try:
        from ..utils.generation_stage import resolve_generation_stage  # type: ignore
    except Exception:
        resolve_generation_stage = None  # type: ignore

# Models import with robust fallback to support /app runtime without backend package
try:
    from backend.models.firestore_models import (
        Chapter, CreateChapterRequest, ChapterListResponse,
        ChapterVersion, QualityScores, ChapterStage
    )
except Exception:
    from models.firestore_models import (
        Chapter, CreateChapterRequest, ChapterListResponse,
        ChapterVersion, QualityScores, ChapterStage
    )
# Robust imports that work from both repo root and backend directory
try:
    from backend.database_integration import (
        get_project_chapters, create_chapter, get_project,
        track_usage, get_database_adapter, get_project_reference_files,
        create_reference_file, update_reference_file,
        list_story_notes, create_story_note, update_story_note, delete_story_note
    )
    from backend.auth_middleware import get_current_user
except ImportError:
    # Fallback when running from backend directory
    from database_integration import (
        get_project_chapters, create_chapter, get_project,
        track_usage, get_database_adapter, get_project_reference_files,
        create_reference_file, update_reference_file,
        list_story_notes, create_story_note, update_story_note, delete_story_note
    )
    from auth_middleware import get_current_user

_VECTOR_STORE_IMPORT_ERROR = None
_STEERING_IMPORT_ERROR = None

try:
    from backend.services.vector_store_service import VectorStoreService
except Exception as exc:
    _VECTOR_STORE_IMPORT_ERROR = exc
    VectorStoreService = None

try:
    from backend.services.steering_service import apply_steering_update
except Exception as exc:
    _STEERING_IMPORT_ERROR = exc
    apply_steering_update = None

if VectorStoreService is None:
    try:
        from services.vector_store_service import VectorStoreService  # type: ignore
        _VECTOR_STORE_IMPORT_ERROR = None
    except Exception as exc:
        _VECTOR_STORE_IMPORT_ERROR = _VECTOR_STORE_IMPORT_ERROR or exc
        VectorStoreService = None

if apply_steering_update is None:
    try:
        from services.steering_service import apply_steering_update  # type: ignore
        _STEERING_IMPORT_ERROR = None
    except Exception as exc:
        _STEERING_IMPORT_ERROR = _STEERING_IMPORT_ERROR or exc
        apply_steering_update = None

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v2/chapters", tags=["chapters-v2"])

# Quota/billing exhaustion should fail fast (no candidate loops).
try:
    from backend.auto_complete.llm_orchestrator import LLMQuotaError
except Exception:  # pragma: no cover
    try:
        from ..auto_complete.llm_orchestrator import LLMQuotaError  # type: ignore
    except Exception:
        LLMQuotaError = None  # type: ignore

# Local workspace sync for auto-complete continuity
try:
    from backend.utils.paths import get_project_workspace, ensure_project_structure
except Exception:  # pragma: no cover
    try:
        from ..utils.paths import get_project_workspace, ensure_project_structure  # type: ignore
    except Exception:
        get_project_workspace = None  # type: ignore
        ensure_project_structure = None  # type: ignore


def _sync_chapter_to_local_workspace(project_id: str, chapter_number: int, content: str) -> None:
    if not project_id or chapter_number <= 0 or not isinstance(content, str):
        return
    if get_project_workspace is None or ensure_project_structure is None:
        return
    try:
        ws = get_project_workspace(project_id)
        ensure_project_structure(ws)
        chapter_path = ws / "chapters" / f"chapter-{int(chapter_number):02d}.md"
        chapter_path.write_text(content, encoding="utf-8")
    except Exception:
        return

def _summarize_generation_failure(raw_error: str) -> str:
    if not raw_error:
        return "unknown_error"
    lowered = raw_error.lower()
    if "failures:" in lowered:
        match = re.search(r"Failures:\s*(.*)", raw_error, flags=re.IGNORECASE)
        if match:
            failures = [item.strip() for item in match.group(1).split(",") if item.strip()]
            return "failures=" + ",".join(failures[:5])
    if "errors:" in lowered:
        match = re.search(r"Errors:\s*(.*)", raw_error, flags=re.IGNORECASE)
        if match:
            chunk = match.group(1).split("|")[0].strip()
            return f"errors={chunk[:160]}"
    return raw_error.strip()[:180]

def _normalize_plain_text_output(text: str) -> str:
    """
    Normalize chapter output to plain text.
    - Remove Markdown artifacts (headings, list markers, blockquotes, code fences, horizontal rules).
    - Normalize em/en dash characters.
    """
    if not text or not isinstance(text, str):
        return ""

    t = text.replace("\r\n", "\n").replace("\r", "\n")

    # Normalize dash-like punctuation to commas for plain-text output.
    for dash in ("—", "–", "―", "‒"):
        t = t.replace(dash, ", ")

    # Strip code fences and horizontal rules.
    t = re.sub(r"(?m)^\s*```[a-zA-Z0-9_-]*\s*$", "", t)
    t = t.replace("```", "")
    t = re.sub(r"(?m)^\s*(---|\*\*\*|___)\s*$", "", t)

    # Strip common Markdown line prefixes.
    t = re.sub(r"(?m)^\s*#{1,6}\s+", "", t)     # headings
    t = re.sub(r"(?m)^\s*>\s?", "", t)          # blockquotes
    t = re.sub(r"(?m)^\s*([-*+]|•)\s+", "", t)  # bullets
    t = re.sub(r"(?m)^\s*\d+[.)]\s+", "", t)    # numbered lists

    # Remove inline emphasis markers and stray backticks.
    t = t.replace("**", "").replace("__", "")
    t = t.replace("*", "").replace("`", "")

    # Normalize spacing.
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()

if VectorStoreService is None:
    logger.warning(
        "VectorStoreService unavailable; vector memory disabled: %s",
        _VECTOR_STORE_IMPORT_ERROR
    )

    class VectorStoreService:  # type: ignore
        """Fallback vector service that no-ops when optional dependency is missing."""

        def __init__(self, *args, **kwargs):
            self.available = False

        async def ensure_project_vector_store(self, *args, **kwargs):
            return None

        async def ensure_user_vector_store(self, *args, **kwargs):
            return None

        async def retrieve_chapter_context(self, *args, **kwargs):
            return []

        def format_results(self, *args, **kwargs):
            return ""

        async def upsert_chapter(self, *args, **kwargs):
            return None

        async def upsert_story_note(self, *args, **kwargs):
            return None

        async def delete_story_note(self, *args, **kwargs):
            return None

if apply_steering_update is None:
    logger.warning(
        "Steering service unavailable; steering updates disabled: %s",
        _STEERING_IMPORT_ERROR
    )

    async def apply_steering_update(*args, **kwargs):  # type: ignore
        return {"status": "skipped", "reason": "steering service unavailable"}

def _extract_character_names(text: str, limit: int = 6) -> List[str]:
    """Extract likely character names from text using simple heuristics."""
    if not text:
        return []
    words = [w.strip(".,:;!?\"'()[]{}") for w in text.split()]
    candidates = [w for w in words if w.isalpha() and w[0].isupper() and len(w) > 2]
    seen = []
    for name in candidates:
        if name not in seen:
            seen.append(name)
        if len(seen) >= limit:
            break
    return seen

def _extract_plot_points(text: str, limit: int = 3) -> List[str]:
    """Extract plot-point-like lines or sentences from reference text."""
    if not text:
        return []
    raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
    bullets: List[str] = []
    for line in raw_lines:
        stripped = line.lstrip()
        if stripped.startswith(("-", "•", "*")):
            bullets.append(stripped.lstrip("-•* ").strip())
            continue
        if len(stripped) > 2 and stripped[0].isdigit() and stripped[1] in {".", ")"}:
            bullets.append(stripped[2:].strip())
            continue
    candidates = bullets or raw_lines
    points: List[str] = []
    for line in candidates:
        cleaned = re.sub(r"\s+", " ", line).strip()
        if cleaned and cleaned not in points:
            points.append(cleaned)
        if len(points) >= limit:
            break
    if points:
        return points
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    for sentence in sentences:
        cleaned = re.sub(r"\s+", " ", sentence).strip()
        if cleaned and cleaned not in points:
            points.append(cleaned)
        if len(points) >= limit:
            break
    return points

def _get_reference_content(references: dict, name_options: List[str]) -> str:
    """Find reference content by matching keys or filenames."""
    if not references:
        return ""
    lowered = {str(k).lower(): v for k, v in references.items()}
    for name in name_options:
        key = name.lower()
        if key in lowered:
            return lowered[key] or ""
        if f"{key}.md" in lowered:
            return lowered[f"{key}.md"] or ""
        for ref_key, ref_val in lowered.items():
            if key in ref_key:
                return ref_val or ""
    return ""

def _trim_text(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"

async def _build_vector_prompt_context(
    project_id: str,
    user_id: str,
    query: str,
    max_results: int = 12
) -> str:
    """Retrieve and format vector store context for prompts."""
    vector_service = VectorStoreService()
    results = await vector_service.retrieve_chapter_context(
        project_id=project_id,
        user_id=user_id,
        query=query,
        max_results=max_results
    )
    return vector_service.format_results(results, max_chars=2200)

async def _load_chapter_with_access(chapter_id: str, current_user: dict) -> dict:
    """Load chapter and verify access, returning chapter data with project info."""
    user_id = current_user.get('user_id')
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user authentication"
        )

    db = get_database_adapter()
    chapter_data = await db.get_chapter(chapter_id, user_id=user_id)
    if not chapter_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chapter not found"
        )

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

    return {
        'chapter': chapter_data,
        'project': project_data,
        'user_id': user_id,
        'project_id': project_id
    }

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

class StoryNoteRequest(BaseModel):
    """Request model for adding a story/director note."""
    content: str
    position: Optional[int] = None
    selection_start: Optional[int] = None
    selection_end: Optional[int] = None
    selection_text: Optional[str] = None
    scope: Optional[str] = "chapter"  # chapter | global
    apply_to_future: Optional[bool] = True
    intent: Optional[str] = None  # continuity | style | dialogue | plot | pacing | character | other

class UpdateStoryNoteRequest(BaseModel):
    """Request model for updating a story/director note."""
    content: Optional[str] = None
    resolved: Optional[bool] = None
    apply_to_future: Optional[bool] = None
    intent: Optional[str] = None
    scope: Optional[str] = None


async def _rebuild_chapter_artifacts(
    *,
    project_id: str,
    user_id: str,
    chapter_number: int,
    chapter_content: str,
    book_bible_content: str,
    references_content: dict[str, str],
    vector_store_ids: Optional[list[str]] = None,
    pov_context: Optional[dict] = None,
) -> dict:
    """
    Regenerate canon-log and chapter-ledger for the given chapter content.
    Best-effort: returns details and never raises.
    """
    result: dict[str, Any] = {
        "canon": {"success": False},
        "ledger": {"success": False},
    }
    try:
        from backend.services.chapter_ledger_service import update_chapter_ledger, update_local_chapter_ledger
    except Exception:
        try:
            from ..services.chapter_ledger_service import update_chapter_ledger, update_local_chapter_ledger  # type: ignore
        except Exception:
            update_chapter_ledger = None  # type: ignore
            update_local_chapter_ledger = None  # type: ignore
    try:
        from backend.services.canon_log_service import update_canon_log
    except Exception:
        try:
            from ..services.canon_log_service import update_canon_log  # type: ignore
        except Exception:
            update_canon_log = None  # type: ignore

    try:
        if callable(update_chapter_ledger):
            ledger_res = await update_chapter_ledger(
                project_id=project_id,
                user_id=user_id,
                chapter_number=chapter_number,
                chapter_content=chapter_content,
                book_bible=book_bible_content,
                references=references_content,
                pov_context=pov_context,
                vector_store_ids=vector_store_ids or [],
            )
            result["ledger"] = ledger_res
            try:
                if ledger_res.get("success") and ledger_res.get("entry"):
                    # Mirror into local workspace state for continuity tooling.
                    from backend.utils.paths import get_project_workspace
                    ws = get_project_workspace(project_id)
                    if callable(update_local_chapter_ledger):
                        update_local_chapter_ledger(str(ws), ledger_res["entry"], chapter_number)
            except Exception:
                pass
    except Exception as e:
        result["ledger"] = {"success": False, "error": str(e)}

    try:
        if callable(update_canon_log):
            canon_res = await update_canon_log(
                project_id=project_id,
                user_id=user_id,
                chapter_number=chapter_number,
                chapter_content=chapter_content,
                book_bible=book_bible_content,
                references=references_content,
                vector_store_ids=vector_store_ids or [],
            )
            result["canon"] = canon_res
    except Exception as e:
        result["canon"] = {"success": False, "error": str(e)}

    return result

class RewriteSectionRequest(BaseModel):
    """Request model for rewriting a selected section."""
    selection_start: int
    selection_end: int
    instruction: str
    preview: bool = False

class ConfirmRewriteRequest(BaseModel):
    """Request model for confirming a previewed rewrite without re-running the LLM."""
    proposed_content: str
    original_selection_start: int
    original_selection_end: int
    instruction: str = ""

class RippleAnalysisRequest(BaseModel):
    """Request model for analyzing downstream chapter impact after an edit."""
    edit_summary: str = ""
    chapter_number: int = 0

class PropagateEditsRequest(BaseModel):
    """Request model for propagating edits to affected downstream chapters."""
    chapter_ids: List[str]
    source_chapter_number: int
    edit_summary: str = ""

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
    rewrite_mode: Optional[str] = None  # polish, full
    rewrite_instruction: Optional[str] = None

# =====================================================================
# AI CHAPTER GENERATION
# =====================================================================

@router.post("/generate", response_model=dict)
async def generate_chapter_simple(
    request: GenerateChapterRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Generate a new chapter using AI with reference-aware prompts."""
    try:
        perf_t0 = time.perf_counter()
        perf_marks: dict[str, float] = {}
        chapter_run_id = str(uuid.uuid4())
        try:
            if run_id_contextvar is not None:
                run_id_contextvar.set(chapter_run_id[:12])
        except Exception:
            pass

        def _mark(name: str) -> None:
            perf_marks[name] = time.perf_counter()

        _mark("start")
        logger.info(f"🚀 Chapter generation started - project: {request.project_id}, chapter: {request.chapter_number}")

        if request.chapter_number < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chapter number must be at least 1"
            )
        if request.target_word_count < 500 or request.target_word_count > 12000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target word count must be between 500 and 12000"
            )
        
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
            _mark("project_fetched")
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

            try:
                from backend.services.chapter_context_builder import normalize_references
                references_content = normalize_references(references_content)
            except Exception:
                pass
            logger.info(f"✅ Loaded book bible ({len(book_bible_content)} chars) and {len(references_content)} references")

        except Exception as e:
            logger.warning(f"⚠️ Could not load full project context: {e}")
            # Continue with limited context
        
        # Build chapter generation context (tier-aware, soft targets)
        allow_override = os.getenv("CHAPTER_ALLOW_TARGET_OVERRIDE", "true").strip().lower() in {"1", "true", "yes", "y"}
        request_target = int(getattr(request, "target_word_count", 0) or 0)
        default_request_target = 2000  # GenerateChapterRequest default
        settings_target = 0
        try:
            settings_target = int((project_data.get("settings") or {}).get("word_count_per_chapter") or 0)
        except Exception:
            settings_target = 0

        effective_target_words = 0
        # Heuristic: treat request_target == default as "not an explicit override" when project settings exist.
        if allow_override and request_target and (settings_target <= 0 or request_target != default_request_target):
            effective_target_words = request_target
        elif settings_target > 0:
            effective_target_words = settings_target
        else:
            # Fallback to tier specs if settings are absent.
            try:
                try:
                    from backend.models.firestore_models import BookBible, BookLengthTier
                except Exception:
                    from models.firestore_models import BookBible, BookLengthTier  # type: ignore
                tier_raw = None
                bb = project_data.get("book_bible")
                if isinstance(bb, dict):
                    tier_raw = bb.get("book_length_tier")
                tier = None
                try:
                    tier = BookLengthTier(str(tier_raw)) if tier_raw else None
                except Exception:
                    tier = None
                if tier:
                    specs = BookBible.get_book_length_specs(tier)
                    effective_target_words = int(specs.get("avg_words_per_chapter") or specs.get("word_count_target") or default_request_target)
            except Exception:
                effective_target_words = 0
        if effective_target_words <= 0:
            effective_target_words = request_target or default_request_target
        effective_target_words = max(500, min(12000, int(effective_target_words)))

        variance_ratio = float(os.getenv("CHAPTER_WORDCOUNT_VARIANCE_RATIO", "0.12"))
        min_variance = int(os.getenv("CHAPTER_WORDCOUNT_MIN_VARIANCE", "150"))
        variance = max(min_variance, int(effective_target_words * variance_ratio))
        target_words_min = max(300, effective_target_words - variance)
        target_words_max = max(target_words_min + 200, effective_target_words + variance)
        chapter_context = {
            'book_bible_content': book_bible_content,
            'references': references_content,
            'chapter_number': request.chapter_number,
            'target_word_count': effective_target_words,
            'target_words_min': target_words_min,
            'target_words_max': target_words_max,
            'project_id': request.project_id
        }
        
        # Get previous chapters for context
        previous_chapters: List[dict] = []
        try:
            logger.info("📚 Loading previous chapters for context...")
            # Guard against immediate sequential generation (Chapter N started before Chapter N-1 is visible).
            # This is intentionally short + bounded; we don't want long server hangs.
            existing_chapters: List[dict] = []
            max_attempts = max(1, int(os.getenv("CHAPTER_PREV_FETCH_RETRIES", "6")))
            delay_s = max(0.05, float(os.getenv("CHAPTER_PREV_FETCH_RETRY_DELAY_SEC", "0.35")))
            last_err: Exception | None = None
            for attempt in range(max_attempts):
                try:
                    existing_chapters = await get_project_chapters(request.project_id)
                    if request.chapter_number <= 1:
                        break
                    expected_prev = request.chapter_number - 1
                    prev = next(
                        (
                            ch for ch in existing_chapters
                            if int(ch.get("chapter_number") or 0) == expected_prev
                            and bool((ch.get("content") or "").strip())
                        ),
                        None,
                    )
                    if prev:
                        break
                except Exception as e:
                    last_err = e
                if attempt < max_attempts - 1:
                    await asyncio.sleep(delay_s)
                    delay_s = min(1.25, delay_s * 1.6)
            if last_err and not existing_chapters:
                raise last_err
            previous_chapters = [
                ch for ch in existing_chapters 
                if ch.get('chapter_number', 0) < request.chapter_number
            ]
            if previous_chapters:
                # Sort by chapter number and get summary of recent chapters
                previous_chapters.sort(key=lambda x: x.get('chapter_number', 0))
                def _first_sentence(text: str) -> str:
                    try:
                        first_para = (text or "").split("\n\n")[0].strip()
                        if not first_para:
                            return ""
                        # A rough sentence boundary split; good enough for summary.
                        for sep in (". ", "! ", "? "):
                            if sep in first_para:
                                return first_para.split(sep)[0].strip()
                        return first_para[:220].strip()
                    except Exception:
                        return ""

                def _last_sentence(text: str) -> str:
                    try:
                        paras = [p.strip() for p in (text or "").split("\n\n") if p.strip()]
                        if not paras:
                            return ""
                        last_para = paras[-1]
                        for sep in (". ", "! ", "? "):
                            if sep in last_para:
                                return last_para.split(sep)[-1].strip()
                        return last_para[-220:].strip()
                    except Exception:
                        return ""

                # Provide a plot-aware “breadcrumb” summary for director brief + continuity.
                recent_summaries: list[str] = []
                for prev_ch in previous_chapters[-3:]:
                    content = (prev_ch.get('content', '') or '').strip()
                    ch_num = prev_ch.get('chapter_number')
                    if not content:
                        continue
                    opening = _first_sentence(content)[:220]
                    ending = _last_sentence(content)[:220]
                    parts = [p for p in [opening, ending] if p]
                    summary = " | ".join(parts) if parts else content[:240]
                    recent_summaries.append(f"Chapter {ch_num}: {summary}")
                chapter_context['previous_chapters_summary'] = "\n".join(recent_summaries)

                # Extract last paragraph of immediate previous chapter for continuity
                try:
                    immediate_prev = previous_chapters[-1]
                    prev_content = immediate_prev.get('content', '')
                    paragraphs = [p.strip() for p in prev_content.split('\n\n') if p.strip()]
                    last_paragraph = paragraphs[-1] if paragraphs else ''
                    # Prefer the last 2-3 sentences (bounded) rather than raw tail chars.
                    try:
                        sentences = re.split(r"(?<=[.!?])\s+", last_paragraph.strip()) if last_paragraph else []
                        tail = " ".join([s for s in sentences[-3:] if s]).strip()
                    except Exception:
                        tail = ""
                    chapter_context['last_chapter_ending'] = (tail or last_paragraph)[-450:] if last_paragraph else ''
                except Exception:
                    chapter_context['last_chapter_ending'] = ''
                logger.info(f"✅ Loaded context from {len(previous_chapters)} previous chapters")
            elif request.chapter_number > 1:
                logger.warning(
                    "⚠️ No previous chapters found for chapter>1; proceeding with minimal continuity. "
                    "This can happen if the previous chapter has not been persisted yet."
                )
        except Exception as e:
            logger.warning(f"⚠️ Could not load previous chapters context: {e}")
            chapter_context['previous_chapters_summary'] = ""
            chapter_context['last_chapter_ending'] = ''

        # Initialize project workspace + continuity manager for story state
        try:
            from backend.utils.paths import get_project_workspace, ensure_project_structure
        except Exception:
            from utils.paths import get_project_workspace, ensure_project_structure
        project_workspace = get_project_workspace(request.project_id)
        ensure_project_structure(project_workspace)
        chapter_context["project_workspace"] = str(project_workspace)

        continuity_snapshot = {}
        try:
            from backend.auto_complete.helpers.chapter_context_manager import ChapterContextManager
            context_manager = ChapterContextManager(str(project_workspace))
            for prev_ch in previous_chapters:
                try:
                    ch_num = int(prev_ch.get('chapter_number', 0))
                    content = prev_ch.get('content', '')
                    if ch_num > 0 and content:
                        # Persist for continuity tools
                        chapter_file = project_workspace / "chapters" / f"chapter-{ch_num:02d}.md"
                        if not chapter_file.exists():
                            chapter_file.write_text(content, encoding="utf-8")
                        context_manager.analyze_chapter_content(ch_num, content)
                except Exception:
                    continue
            continuity_snapshot = context_manager.build_next_chapter_context(request.chapter_number)
            chapter_context["continuity"] = continuity_snapshot
        except Exception as cont_err:
            logger.warning(f"⚠️ Continuity manager unavailable: {cont_err}")

        # Bridge requirements for Chapter N>1: keep the opening glued to prior consequences/threads.
        try:
            bridge_reqs: list[str] = []
            last_end = (chapter_context.get("last_chapter_ending") or "").strip()
            if last_end and request.chapter_number > 1:
                bridge_reqs.append(f"Begin from the immediate consequence of the prior ending: {last_end[:240]}")

            # Heuristic clue carry-forward: extract salient named tokens from the end of the prior chapter
            # and require the opening to explicitly carry at least one forward (without recap).
            try:
                if request.chapter_number > 1 and previous_chapters:
                    prev_txt = str((previous_chapters[-1] or {}).get("content", "") or "")
                    tail_words = prev_txt.split()
                    tail = " ".join(tail_words[max(0, len(tail_words) - 650):])
                    # Capture proper nouns and distinctive tokens (allow hyphens/digits).
                    candidates = re.findall(r"\b[A-Z][a-zA-Z0-9-]{2,}\b", tail)
                    stop = {"The", "A", "An", "And", "But", "For", "Or", "Nor", "So", "Yet", "He", "She", "They", "It", "His", "Her", "Their"}
                    tokens: list[str] = []
                    for c in candidates:
                        if c in stop:
                            continue
                        if c not in tokens:
                            tokens.append(c)
                        if len(tokens) >= 4:
                            break
                    if tokens:
                        bridge_reqs.append(
                            "In the first ~200-300 words, explicitly carry forward at least one concrete clue/thread from the prior chapter's last scene: "
                            + ", ".join(tokens[:4])
                        )
            except Exception:
                pass

            if isinstance(continuity_snapshot, dict) and continuity_snapshot:
                for item in (continuity_snapshot.get("unresolved_questions") or [])[:6]:
                    s = str(item).strip()
                    if s:
                        bridge_reqs.append(s)
                # Some implementations store plot threads as list/dict; stringify conservatively.
                plot_threads = continuity_snapshot.get("plot_threads")
                if isinstance(plot_threads, list):
                    for item in plot_threads[:6]:
                        s = str(item).strip()
                        if s:
                            bridge_reqs.append(s)
                elif isinstance(plot_threads, dict):
                    for k in list(plot_threads.keys())[:6]:
                        s = str(k).strip()
                        if s:
                            bridge_reqs.append(s)
            # Deduplicate while preserving order
            seen: set[str] = set()
            bridge_reqs_unique: list[str] = []
            for r in bridge_reqs:
                if r in seen:
                    continue
                seen.add(r)
                bridge_reqs_unique.append(r)
            if bridge_reqs_unique:
                chapter_context["bridge_requirements"] = bridge_reqs_unique[:8]
        except Exception:
            pass

        # Provide previous chapter texts for continuity audits/repair (bounded).
        try:
            prev_texts: list[str] = []
            for prev_ch in (previous_chapters or [])[-2:]:
                txt = (prev_ch.get("content") or "").strip()
                if not txt:
                    continue
                # Cap by words to avoid huge audit payloads
                words = txt.split()
                prev_texts.append(" ".join(words[:2200]))
            if prev_texts:
                chapter_context["previous_texts_for_audit"] = prev_texts
        except Exception:
            pass

        # Load story/director notes for continuity and future guidance
        try:
            notes = await list_story_notes(request.project_id, user_id)
            if notes:
                chapter_number_lookup = {
                    ch.get('id'): ch.get('chapter_number') for ch in previous_chapters if ch.get('id')
                }
                usable_notes = []
                for note in notes:
                    if note.get('resolved'):
                        continue
                    if note.get('apply_to_future') is False:
                        continue
                    if not (note.get('content') or '').strip():
                        continue
                    usable_notes.append(note)

                def _note_sort_key(note: dict) -> float:
                    created = note.get('created_at')
                    try:
                        if hasattr(created, 'timestamp'):
                            return float(created.timestamp())
                        if hasattr(created, 'seconds'):
                            return float(created.seconds)
                        if isinstance(created, str):
                            return datetime.fromisoformat(created.replace('Z', '+00:00')).timestamp()
                    except Exception:
                        pass
                    return 0.0

                usable_notes = sorted(usable_notes, key=_note_sort_key, reverse=True)
                note_lines: list[str] = []
                for note in usable_notes[:12]:
                    scope = note.get('scope', 'chapter')
                    chapter_id = note.get('chapter_id')
                    chapter_label = ""
                    if scope == 'global':
                        chapter_label = "GLOBAL"
                    elif chapter_id:
                        ch_num = chapter_number_lookup.get(chapter_id)
                        chapter_label = f"Chapter {ch_num}" if ch_num else "Chapter Note"
                    else:
                        chapter_label = "Chapter Note"

                    intent = f"[{note.get('intent')}]" if note.get('intent') else ""
                    selection_text = (note.get('selection_text') or '').strip()
                    if selection_text:
                        selection_text = selection_text[:180].replace("\n", " ")
                        selection_segment = f"Selection: \"{selection_text}\""
                    else:
                        selection_segment = ""
                    content_text = (note.get('content') or '').strip()
                    line_parts = [chapter_label, intent, content_text, selection_segment]
                    line = " ".join([p for p in line_parts if p])
                    note_lines.append(line[:400])

                if note_lines:
                    chapter_context['director_notes'] = "\n".join(note_lines)
        except Exception as e:
            logger.warning(f"⚠️ Could not load director notes: {e}")
        
        # Generate chapter content using AI
        try:
            logger.info(f"🎯 Starting AI generation for chapter {request.chapter_number}...")

            # Build previous opening/ending lines for variation guardrails
            previous_opening_lines: list[str] = []
            previous_ending_lines: list[str] = []
            for prev_ch in previous_chapters[-3:]:
                content = prev_ch.get('content', '')
                if content:
                    first_paragraph = content.split('\n\n')[0].strip()
                    first_sentence = first_paragraph.split('. ')[0].split('! ')[0].split('? ')[0].strip()
                    if first_sentence:
                        previous_opening_lines.append(first_sentence[:200])

                    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
                    if paragraphs:
                        last_para = paragraphs[-1]
                        last_sentence = last_para.split('. ')[-1].split('! ')[-1].split('? ')[-1].strip()
                        if last_sentence:
                            previous_ending_lines.append(last_sentence[:200])

            if previous_opening_lines:
                chapter_context['previous_opening_lines'] = previous_opening_lines
            if previous_ending_lines:
                chapter_context['previous_ending_lines'] = previous_ending_lines

            # Pattern database context for repetition avoidance
            pattern_summary_text = ""
            repetition_risks = {}
            try:
                from backend.utils.paths import get_project_workspace, ensure_project_structure
            except Exception:
                from utils.paths import get_project_workspace, ensure_project_structure

            project_workspace = get_project_workspace(request.project_id)
            ensure_project_structure(project_workspace)
            project_state_path = project_workspace
            try:
                import sys
                backend_dir = Path(__file__).resolve().parents[1]
                repo_root = Path(__file__).resolve().parents[2]
                for path in (str(backend_dir), str(repo_root)):
                    if path not in sys.path:
                        sys.path.insert(0, path)
                try:
                    from backend.system.pattern_database_engine import PatternDatabase
                except Exception as backend_err:
                    try:
                        from system.pattern_database_engine import PatternDatabase
                    except Exception as system_err:
                        module_candidates = [
                            backend_dir / "system" / "pattern_database_engine.py",
                            backend_dir / "system" / "pattern-database-engine.py",
                            repo_root / "backend" / "system" / "pattern_database_engine.py",
                            repo_root / "backend" / "system" / "pattern-database-engine.py",
                            repo_root / "backend" / "backend" / "system" / "pattern_database_engine.py",
                            repo_root / "backend" / "backend" / "system" / "pattern-database-engine.py",
                            repo_root / "system" / "pattern_database_engine.py",
                            repo_root / "system" / "pattern-database-engine.py",
                        ]
                        module_path = next((path for path in module_candidates if path.exists()), None)
                        if not module_path:
                            searched = ", ".join(str(path) for path in module_candidates)
                            raise Exception(
                                "backend.system import failed: "
                                f"{backend_err}; system import failed: {system_err}; "
                                f"pattern database file not found under {searched}"
                            )
                        spec = importlib.util.spec_from_file_location("pattern_database_engine", module_path)
                        if not spec or not spec.loader:
                            raise Exception(f"Pattern database module spec unavailable: {module_path}")
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        PatternDatabase = getattr(module, "PatternDatabase")
                pattern_db = PatternDatabase(str(project_state_path))
                summary = pattern_db.get_pattern_summary()
                repetition_risks = summary.get("recent_risks", {})
                pattern_summary_text = "\n".join([
                    f"Chapters tracked: {summary.get('chapters_tracked', 0)}",
                    f"Total metaphors: {summary.get('total_metaphors', 0)}",
                    f"Total similes: {summary.get('total_similes', 0)}",
                    f"Sentence patterns: {summary.get('sentence_patterns', 0)}",
                    f"Paragraph patterns: {summary.get('paragraph_patterns', 0)}",
                    f"Dialogue tags: {summary.get('dialogue_tags', 0)}",
                    f"Freshness score: {repetition_risks.get('score', 0)}/10"
                ])
            except Exception as pattern_err:
                logger.warning(f"Pattern database unavailable for generation context: {pattern_err}")

            # Load or create chapter plan if available
            chapter_plan = {}
            previous_plan = None
            plan_data = None
            target_chapters = 20
            try:
                from backend.auto_complete.helpers.book_plan_generator import BookPlanGenerator
                plan_generator = BookPlanGenerator(str(project_state_path))
                plan_data = None
                plan_source = "none"
                plan_filename = "book-plan.json"
                plan_t0 = time.perf_counter()

                # 1) Prefer persistent cache from project references (Firestore-backed)
                plan_raw = (
                    references_content.get(plan_filename)
                    or references_content.get("book_plan.json")
                    or references_content.get("book-plan")
                    or ""
                )
                if isinstance(plan_raw, str) and plan_raw.strip().startswith("{"):
                    try:
                        plan_data = json.loads(plan_raw)
                        plan_source = "reference"
                    except Exception:
                        plan_data = None

                # 2) Fall back to local project workspace cache
                if not plan_data:
                    plan_data = plan_generator.load_existing_plan()
                    if plan_data:
                        plan_source = "local"

                # If missing, create the plan using book bible and references
                if not plan_data:
                    target_chapters = (
                        (project_data.get('settings') or {}).get('target_chapters')
                        or project_data.get('target_chapters')
                        or (project_data.get('metadata') or {}).get('target_chapters')
                    )
                    if not target_chapters:
                        logger.warning("Project target_chapters not set; skipping master book plan generation.")
                    else:
                        plan_result = await plan_generator.generate_plan(
                            book_bible=book_bible_content,
                            references=references_content,
                            target_chapters=int(target_chapters)
                        )
                        if not plan_result.success:
                            logger.warning(f"Master book plan generation failed: {plan_result.error}")
                        else:
                            plan_data = plan_result.plan
                            plan_source = "generated"

                # If we have a plan, normalize chapter count locally if target differs (no LLM)
                try:
                    target_chapters = (
                        (project_data.get('settings') or {}).get('target_chapters')
                        or project_data.get('target_chapters')
                        or (project_data.get('metadata') or {}).get('target_chapters')
                    )
                    if plan_data and target_chapters:
                        normalized = plan_generator._normalize_chapter_count_local(plan_data, int(target_chapters))
                        if normalized and isinstance(normalized.get("chapters"), list) and len(normalized["chapters"]) == int(target_chapters):
                            plan_data = normalized
                except Exception:
                    pass

                # Invalidation: if the book bible / references changed since plan creation, regenerate.
                try:
                    if plan_data and isinstance(plan_data, dict):
                        expected = plan_generator.compute_source_hashes(book_bible_content, references_content)
                        md = plan_data.get("metadata") if isinstance(plan_data.get("metadata"), dict) else {}
                        existing = md.get("source_hashes") if isinstance(md.get("source_hashes"), dict) else {}
                        if not existing:
                            plan_data.setdefault("metadata", {})
                            plan_data["metadata"]["source_hashes"] = expected
                        else:
                            if (
                                str(existing.get("book_bible_sha256")) != str(expected.get("book_bible_sha256"))
                                or str(existing.get("references_sha256")) != str(expected.get("references_sha256"))
                            ):
                                # Only regenerate when we have a known chapter target.
                                target_chapters = (
                                    (project_data.get('settings') or {}).get('target_chapters')
                                    or project_data.get('target_chapters')
                                    or (project_data.get('metadata') or {}).get('target_chapters')
                                )
                                if target_chapters:
                                    plan_result = await plan_generator.generate_plan(
                                        book_bible=book_bible_content,
                                        references=references_content,
                                        target_chapters=int(target_chapters)
                                    )
                                    if plan_result.success and plan_result.plan:
                                        plan_data = plan_result.plan
                                        plan_source = "regenerated"
                except Exception:
                    pass

                # Persist plan to references so it isn't regenerated per chapter on stateless hosts
                try:
                    if plan_data and isinstance(plan_data, dict):
                        plan_json = json.dumps(plan_data, ensure_ascii=False, separators=(",", ":"))
                        updated = await update_reference_file(request.project_id, plan_filename, plan_json, user_id)
                        if not updated:
                            await create_reference_file(request.project_id, plan_filename, plan_json, user_id)
                        references_content[plan_filename] = plan_json
                except Exception:
                    pass

                try:
                    chapter_context["book_plan_source"] = plan_source
                    chapter_context["book_plan_ms"] = int((time.perf_counter() - plan_t0) * 1000)
                except Exception:
                    pass
                try:
                    _mark("book_plan_done")
                except Exception:
                    pass

                if plan_data:
                    for chapter in plan_data.get("chapters", []):
                        if chapter.get("chapter_number") == request.chapter_number:
                            chapter_plan = chapter
                            break
                if plan_data and request.chapter_number > 1:
                    for chapter in plan_data.get("chapters", []):
                        if chapter.get("chapter_number") == request.chapter_number - 1:
                            previous_plan = chapter
                            break
            except Exception as plan_err:
                logger.warning(f"Failed to load or create chapter plan: {plan_err}")

            # Anti-pattern tracking for chapter structural variety
            pattern_tracker = None
            anti_pattern_context = ""
            try:
                from backend.auto_complete.helpers.chapter_blueprint import ChapterPatternTracker
                pattern_tracker = ChapterPatternTracker(str(project_workspace))
                anti_pattern_context = pattern_tracker.build_anti_pattern_context(request.chapter_number)
            except Exception as apt_err:
                logger.debug(f"Anti-pattern tracker unavailable: {apt_err}")

            # Build unified story state snapshot (ledger + continuity + POV bridge)
            try:
                from backend.services.story_state_service import build_story_state_context
                ledger_text = (
                    references_content.get("chapter-ledger.md")
                    or references_content.get("chapter_ledger.md")
                    or references_content.get("chapter-ledger")
                    or references_content.get("chapter_ledger")
                    or ""
                )
                story_state = build_story_state_context(
                    chapter_number=request.chapter_number,
                    chapter_plan=chapter_plan or {},
                    previous_plan=previous_plan or {},
                    ledger_text=ledger_text,
                    continuity_snapshot=continuity_snapshot or {}
                )
                chapter_context.update(story_state)
            except Exception as state_err:
                logger.warning(f"Failed to build story state snapshot: {state_err}")

            # Vector store retrieval for targeted context
            vector_context = ""
            vector_guidelines = ""
            try:
                plan_summary = chapter_plan.get("summary", "")
                required_points = chapter_plan.get("required_plot_points", [])
                focus_chars = chapter_plan.get("focal_characters", [])
                note_summary = chapter_context.get("director_notes", "")
                previous_summary = chapter_context.get("previous_chapters_summary", "")
                query_parts = [
                    f"Chapter {request.chapter_number}",
                    plan_summary,
                    "Required plot points: " + ", ".join(required_points) if required_points else "",
                    "Focus characters: " + ", ".join(focus_chars) if focus_chars else "",
                    "Director notes: " + note_summary if note_summary else "",
                    "Previous summary: " + previous_summary if previous_summary else "",
                ]
                vector_query = ". ".join([p for p in query_parts if p])
                if vector_query:
                    vector_context = await _build_vector_prompt_context(
                        project_id=request.project_id,
                        user_id=user_id,
                        query=vector_query,
                        max_results=12
                    )
                vector_guidelines = await _build_vector_prompt_context(
                    project_id=request.project_id,
                    user_id=user_id,
                    query="Style guide, tone requirements, and writing rules for this project.",
                    max_results=6
                )
            except Exception as vector_err:
                logger.warning(f"Vector memory retrieval failed: {vector_err}")

            # Build story context for 5-stage prompts
            characters_ref = _get_reference_content(
                references_content, ["characters", "characters_reference", "character_profiles"]
            )
            outline_ref = _get_reference_content(
                references_content, ["outline", "outline_reference", "synopsis"]
            )
            plot_timeline_ref = _get_reference_content(
                references_content, ["plot_timeline", "plot-timeline", "timeline"]
            )
            story_context_parts = [
                book_bible_content,
                vector_context,
                outline_ref,
                plot_timeline_ref
            ]
            story_context = "\n\n".join([p for p in story_context_parts if p]).strip()
            focus_characters = chapter_plan.get("focal_characters") or _extract_character_names(
                " ".join([book_bible_content, characters_ref]),
                limit=6
            )
            required_plot_points = chapter_plan.get("required_plot_points") or (
                [chapter_plan.get("summary")] if chapter_plan.get("summary") else []
            )
            if not required_plot_points:
                fallback_source = outline_ref or plot_timeline_ref or chapter_plan.get("summary", "") or book_bible_content
                required_plot_points = _extract_plot_points(fallback_source, limit=3)
            chapter_climax_goal = chapter_plan.get("ending_type") or chapter_plan.get("summary") or ""
            if not chapter_climax_goal:
                chapter_climax_goal = required_plot_points[-1] if required_plot_points else ""

            # Build LLM context
            quality_orchestrator = None
            llm_context = {
                "book_bible": book_bible_content,
                "project_path": str(project_workspace),
                "previous_chapters_summary": chapter_context.get('previous_chapters_summary', ''),
                "references": references_content,
                "target_words_min": target_words_min,
                "target_words_max": target_words_max,
                "target_words": effective_target_words,
                "previous_opening_lines": chapter_context.get('previous_opening_lines', []),
                "previous_ending_lines": chapter_context.get('previous_ending_lines', []),
                "last_chapter_ending": chapter_context.get('last_chapter_ending', ''),
                "director_notes": chapter_context.get('director_notes', ''),
                "pattern_database_summary": pattern_summary_text,
                "repetition_risks": repetition_risks,
                "chapter_objectives": chapter_plan.get("objectives", []),
                "chapter_plan_summary": chapter_plan.get("summary", ""),
                "required_plot_points": required_plot_points,
                "opening_type": chapter_plan.get("opening_type", ""),
                "ending_type": chapter_plan.get("ending_type", ""),
                "emotional_arc": chapter_plan.get("emotional_arc", ""),
                "focal_characters": focus_characters,
                "plan_continuity_requirements": chapter_plan.get("continuity_requirements", []),
                "pov_character": chapter_plan.get("pov_character", "") or chapter_context.get("pov_character", ""),
                "pov_type": chapter_plan.get("pov_type", "") or chapter_context.get("pov_type", ""),
                "pov_notes": chapter_plan.get("pov_notes", "") or chapter_context.get("pov_notes", ""),
                "pov_shift": chapter_context.get("pov_shift", False),
                "bridge_requirements": chapter_context.get("bridge_requirements", []),
                "chapter_ledger_summary": chapter_context.get("chapter_ledger_summary", ""),
                "continuity_story_so_far": (chapter_context.get("continuity") or {}).get("story_so_far", ""),
                "continuity_unresolved_questions": (chapter_context.get("continuity") or {}).get("unresolved_questions", []),
                "continuity_requirements": (chapter_context.get("continuity") or {}).get("continuity_requirements", []),
                "continuity_character_needs": (chapter_context.get("continuity") or {}).get("character_development_needs", {}),
                "continuity_themes_to_continue": (chapter_context.get("continuity") or {}).get("themes_to_continue", []),
                "pacing_guidance": (chapter_context.get("continuity") or {}).get("pacing_guidance", {}),
                "memory_ledger": (chapter_context.get("continuity") or {}).get("memory_ledger", ""),
                "timeline_state": (chapter_context.get("continuity") or {}).get("timeline_state", {}),
                "timeline_constraints": (chapter_context.get("continuity") or {}).get("timeline_constraints", []),
                "vector_context": vector_context,
                "vector_guidelines": vector_guidelines,
                "genre": (project_data.get("settings", {}) or {}).get("genre", ""),
                "story_context": story_context,
                "previous_chapter_summary": chapter_context.get('previous_chapters_summary', ''),
                "character_requirements": characters_ref,
                "plot_requirements": outline_ref or plot_timeline_ref,
                "focus_characters": focus_characters,
                "chapter_climax_goal": chapter_climax_goal,
                "vector_store_ids": [],
                "use_file_search": True,
                "vector_memory_context": vector_context,
                "vector_memory_guidelines": vector_guidelines,
                # Anti-pattern and structural variety
                "anti_pattern_context": anti_pattern_context,
                # Plan structural fields
                "chapter_title": chapter_plan.get("title", ""),
                "transition_note": chapter_plan.get("transition_note", ""),
                "story_arcs": plan_data.get("story_arcs", {}) if isinstance(plan_data, dict) else {},
                # Pacing awareness
                "total_chapters": int(target_chapters or 20),
                "remaining_chapters": max(0, int(target_chapters or 20) - request.chapter_number),
                "remaining_word_budget": max(0, (int(target_chapters or 20) - request.chapter_number) * effective_target_words),
            }

            # Repetition + cadence targets (balanced allowlist)
            try:
                from backend.auto_complete.orchestrator import AutoCompleteBookOrchestrator, AutoCompletionConfig
                config = AutoCompletionConfig(
                    target_word_count=int((project_data.get("settings") or {}).get("target_word_count") or request.target_word_count),
                    target_chapter_count=int((project_data.get("settings") or {}).get("target_chapters") or 20),
                    user_id=user_id,
                    project_id=request.project_id
                )
                quality_orchestrator = AutoCompleteBookOrchestrator(str(project_workspace), config=config)
                repetition_allowlist = quality_orchestrator._build_repetition_allowlist(llm_context)
                llm_context["repetition_allowlist"] = repetition_allowlist
                llm_context["avoid_phrases"] = quality_orchestrator._build_avoid_phrases(
                    request.chapter_number,
                    repetition_allowlist
                )
                llm_context["cadence_targets"] = quality_orchestrator._build_cadence_targets(request.chapter_number)
                llm_context["pacing_targets"] = quality_orchestrator._build_pacing_targets(request.chapter_number)
                overused = quality_orchestrator._build_overused_words(request.chapter_number, repetition_allowlist)
                if overused:
                    llm_context["overused_words"] = overused
                overused_phrases = quality_orchestrator._build_overused_phrases(request.chapter_number, repetition_allowlist)
                if overused_phrases:
                    llm_context["overused_phrases"] = overused_phrases
            except Exception as rep_err:
                logger.warning(f"Repetition/cadence targets unavailable: {rep_err}")

            # Attach vector store ids for file_search tool
            try:
                vector_service = VectorStoreService()
                project_store_id = (project_data.get("memory", {}) or {}).get("project_vector_store_id")
                if not project_store_id:
                    project_store_id = await vector_service.ensure_project_vector_store(
                        project_id=request.project_id,
                        user_id=user_id,
                        project_title=(project_data.get("metadata", {}) or {}).get("title")
                    )
                if project_store_id:
                    llm_context["vector_store_ids"].append(project_store_id)

                user_store_id = (project_data.get("memory", {}) or {}).get("user_vector_store_id")
                if not user_store_id:
                    user_store_id = await vector_service.ensure_user_vector_store(user_id)
                if user_store_id:
                    llm_context["vector_store_ids"].append(user_store_id)
            except Exception as vector_err:
                logger.warning(f"Vector store id lookup failed: {vector_err}")

            # Keep vector context as fallback if file_search is unavailable

            # Normalize + clamp context to keep long-run generation stable.
            try:
                from backend.services.context_bundle import normalize_generation_context
                llm_context = normalize_generation_context(llm_context)
            except Exception:
                try:
                    from ..services.context_bundle import normalize_generation_context  # type: ignore
                    llm_context = normalize_generation_context(llm_context)
                except Exception:
                    pass

            # Use orchestrator for unified prompt and billing behavior
            from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig
            credits_enabled = os.getenv('ENABLE_CREDITS_SYSTEM', 'false').lower() == 'true'
            enable_billing = os.getenv('ENABLE_CREDITS_BILLING', 'false').lower() == 'true' and credits_enabled
            prompts_dir = os.getenv("PROMPTS_DIR")
            if not prompts_dir:
                repo_root = Path(__file__).resolve().parents[2]
                backend_prompts = repo_root / "backend" / "prompts"
                root_prompts = repo_root / "prompts"
                if backend_prompts.exists():
                    prompts_dir = str(backend_prompts)
                elif root_prompts.exists():
                    prompts_dir = str(root_prompts)
                else:
                    prompts_dir = "prompts"

            orchestrator = LLMOrchestrator(
                retry_config=RetryConfig(max_retries=3),
                user_id=user_id,
                enable_billing=enable_billing,
                prompts_dir=prompts_dir
            )

            # Generate chapter blueprint for structural variety
            try:
                from backend.auto_complete.helpers.chapter_blueprint import (
                    generate_chapter_blueprint, format_blueprint_for_prompt
                )
                style_guide_for_bp = (
                    references_content.get("style-guide", "")
                    or references_content.get("style_guide", "")
                    or references_content.get("style-guide.md", "")
                    or ""
                )
                blueprint = await generate_chapter_blueprint(
                    orchestrator=orchestrator,
                    chapter_number=request.chapter_number,
                    total_chapters=int(target_chapters or 20),
                    chapter_plan=chapter_plan,
                    book_bible=book_bible_content,
                    anti_pattern_context=anti_pattern_context,
                    style_guide=style_guide_for_bp,
                )
                llm_context["chapter_blueprint"] = format_blueprint_for_prompt(blueprint)
                logger.info(
                    f"Chapter {request.chapter_number} blueprint: shape={blueprint.get('chapter_shape')}, "
                    f"register={blueprint.get('prose_register')}, tension={blueprint.get('tension_level')}"
                )
            except Exception as bp_err:
                logger.warning(f"Blueprint generation skipped for Chapter {request.chapter_number}: {bp_err}")

            rewrite_mode = (request.rewrite_mode or "").strip().lower()
            requested_stage_raw = request.stage
            if resolve_generation_stage is not None:
                stage_res = resolve_generation_stage(requested_stage_raw)
                requested_stage = stage_res.requested
                generation_stage = stage_res.effective
                allow_5_stage = bool(stage_res.allow_5_stage)
                if requested_stage == "5-stage" and generation_stage != "5-stage":
                    logger.warning(
                        "5-stage requested but disabled; falling back to simple. "
                        "Set ENABLE_5_STAGE_WRITING=true to enable legacy 5-stage generation."
                    )
            else:
                # Ultra-defensive fallback: treat "simple" as "complete".
                requested_stage = (requested_stage_raw or "simple")
                requested_lower = (requested_stage or "").strip().lower()
                if requested_lower in ("", "simple"):
                    generation_stage = "complete"
                elif requested_lower in ("5-stage", "5stage", "5_stage", "five-stage", "five_stage"):
                    # Fail closed: 5-stage must be explicitly enabled via helper.
                    generation_stage = "complete"
                else:
                    generation_stage = str(requested_stage)
                allow_5_stage = False

            # Shared post-draft LLM budget (caps churn after initial draft exists)
            postdraft_total = max(0, int(os.getenv("CHAPTER_POSTDRAFT_LLM_BUDGET", "5")))
            llm_context["postdraft_budget"] = {
                "total": postdraft_total,
                "used": 0,
                "remaining": postdraft_total,
                "actions": [],
            }

            use_scene_by_scene = (
                os.getenv("ENABLE_SCENE_BY_SCENE", "true").lower() == "true"
                and request.target_word_count >= int(os.getenv("SCENE_BY_SCENE_MIN_WORDS", "2800"))
            )
            logger.info(
                f"Generation mode: stage={generation_stage}, scene_by_scene={use_scene_by_scene}, target_words={request.target_word_count}"
            )

            _mark("llm_start")
            generated_content = ""
            tokens_used = {'prompt': 0, 'completion': 0, 'total': 0}
            cost_breakdown = {'input_cost': 0.0, 'output_cost': 0.0, 'total_cost': 0.0}
            candidate_count = 0
            candidates: list[dict] = []
            candidate_errors: list[str] = []
            best: dict = {}
            skeleton_success = False
            detected_model_used: Optional[str] = None

            if rewrite_mode == "polish":
                existing_chapters = await get_project_chapters(request.project_id)
                existing_chapter = None
                for ch in existing_chapters:
                    if ch.get('chapter_number') == request.chapter_number:
                        existing_chapter = ch
                        break
                if not existing_chapter or not (existing_chapter.get("content") or "").strip():
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Chapter not found for polish rewrite"
                    )

                try:
                    from backend.services.chapter_context_builder import get_canon_log
                    canon_log_content = get_canon_log(references_content)
                except Exception:
                    canon_log_content = references_content.get("canon-log.md") or references_content.get("canon_log") or ""

                instruction = request.rewrite_instruction or (
                    "Polish the chapter for clarity, specificity, and natural prose. "
                    "Preserve plot beats, continuity, POV, and character voice."
                )
                rewrite = await orchestrator.rewrite_full_chapter(
                    chapter_text=existing_chapter.get("content", ""),
                    instruction=instruction,
                    context={
                        "book_bible": book_bible_content,
                        "references": references_content,
                        "canon_source": canon_log_content,
                        "canon_label": "Canon Log",
                        "vector_store_ids": llm_context.get("vector_store_ids", []),
                        "use_file_search": True,
                        "director_notes": chapter_context.get("director_notes", ""),
                        "chapter_number": request.chapter_number,
                    },
                    chapter_number=request.chapter_number,
                )
                if not rewrite.success:
                    raise Exception(rewrite.error or "Chapter polish rewrite failed")
                generated_content = rewrite.content
                tokens_used = (rewrite.metadata or {}).get('tokens_used', tokens_used)
                total_tokens = tokens_used.get("total", 0) if isinstance(tokens_used, dict) else 0
                cost_breakdown = {
                    "input_cost": 0.0,
                    "output_cost": 0.0,
                    "total_cost": 0.0
                }
                if total_tokens and hasattr(orchestrator, "cost_per_1k_input_tokens"):
                    cost_breakdown["total_cost"] = (total_tokens / 1000) * orchestrator.cost_per_1k_output_tokens
                logger.info(f"✅ AI polish rewrite completed ({len(generated_content)} characters)")
            else:
                # Skeleton + Expand generation (preferred path)
                use_skeleton = os.getenv("USE_SKELETON_EXPAND", "true").lower() == "true"
                skeleton_success = False
                if use_skeleton and rewrite_mode != "polish":
                    try:
                        from backend.auto_complete.helpers.skeleton_expand import (
                            generate_chapter_skeleton_expand,
                            EstablishedFactsLedger,
                        )
                        # Build book-wide word counts for overused words context
                        book_word_counts: dict = {}
                        try:
                            if project_workspace:
                                chapters_path = Path(project_workspace) / "chapters"
                                if chapters_path.exists():
                                    for ch_file in sorted(chapters_path.glob("chapter-*.md")):
                                        try:
                                            ch_text = ch_file.read_text(encoding="utf-8").lower()
                                            for w in re.findall(r'\b[a-z]{4,}\b', ch_text):
                                                book_word_counts[w] = book_word_counts.get(w, 0) + 1
                                        except Exception:
                                            pass
                        except Exception:
                            pass
                        llm_context["_book_word_counts"] = book_word_counts
                        llm_context["_chapter_plan"] = chapter_plan

                        # Get established facts
                        try:
                            facts_ledger = EstablishedFactsLedger(str(project_workspace))
                            llm_context["established_facts"] = facts_ledger.get_established_context()
                        except Exception:
                            pass

                        skel_content = await generate_chapter_skeleton_expand(
                            orchestrator=orchestrator,
                            chapter_number=request.chapter_number,
                            total_chapters=int(target_chapters or 20),
                            target_words=effective_target_words,
                            context=llm_context,
                            logger=logger,
                        )

                        if skel_content and len(skel_content.split()) > 200:
                            generated_content = skel_content
                            skeleton_success = True
                            logger.info(
                                f"Skeleton+expand generated Chapter {request.chapter_number}: "
                                f"{len(generated_content.split())} words"
                            )

                            # Update established facts ledger
                            try:
                                facts_ledger = EstablishedFactsLedger(str(project_workspace))
                                new_facts = await facts_ledger.extract_facts_from_chapter(
                                    orchestrator, request.chapter_number, generated_content,
                                    book_bible_content
                                )
                                facts_ledger.add_chapter_facts(request.chapter_number, new_facts)
                            except Exception as facts_err:
                                logger.warning(f"Failed to update established facts: {facts_err}")
                        else:
                            logger.warning(f"Skeleton+expand produced insufficient content; falling back to single-pass.")
                    except Exception as skel_err:
                        logger.warning(f"Skeleton+expand failed: {skel_err}; falling back to single-pass.")

                if skeleton_success:
                    # Skip the candidate loop — skeleton+expand already produced the chapter
                    tokens_used = {'prompt': 0, 'completion': 0, 'total': 0}
                    cost_breakdown = {'input_cost': 0.0, 'output_cost': 0.0, 'total_cost': 0.0}
                    detected_model_used = getattr(orchestrator, 'model', 'gpt-4.1')
                    candidate_count = 0
                    candidates = []
                    candidate_errors = []
                    best = {"content": generated_content, "metadata": {}, "quality_result": {}, "score": 7.0}
                else:
                    candidate_count = max(1, int(os.getenv("CHAPTER_CANDIDATE_COUNT", "1")))
                    candidates = []
                    candidate_errors = []
                    detected_model_used = None

                for idx in range(candidate_count):
                    result = None
                    if generation_stage == "5-stage":
                        required_fields = [
                            "genre",
                            "story_context",
                            "required_plot_points",
                            "focus_characters",
                            "chapter_climax_goal"
                        ]
                        missing = [field for field in required_fields if not llm_context.get(field)]
                        if missing:
                            logger.warning(
                                "5-stage generation missing required fields; falling back to complete stage. "
                                f"Missing: {', '.join(missing)}"
                            )
                            generation_stage = "complete"
                            if use_scene_by_scene:
                                result = await orchestrator.generate_chapter_scene_by_scene(
                                    chapter_number=request.chapter_number,
                                    target_words=effective_target_words,
                                    context=llm_context
                                )
                            else:
                                result = await orchestrator.generate_chapter(
                                    chapter_number=request.chapter_number,
                                    target_words=effective_target_words,
                                    stage=generation_stage,
                                    context=llm_context
                                )
                        else:
                            results = await orchestrator.generate_chapter_5_stage(
                                chapter_number=request.chapter_number,
                                target_words=effective_target_words,
                                context=llm_context
                            )
                            result = results[-1] if results else None
                    else:
                        if use_scene_by_scene:
                            result = await orchestrator.generate_chapter_scene_by_scene(
                                chapter_number=request.chapter_number,
                                target_words=effective_target_words,
                                context=llm_context
                            )
                        else:
                            result = await orchestrator.generate_chapter(
                                chapter_number=request.chapter_number,
                                target_words=effective_target_words,
                                stage=generation_stage,
                                context=llm_context
                            )

                    if not result or not result.success:
                        error_msg = result.error if result else "no result"
                        logger.warning(f"Candidate {idx + 1} failed: {error_msg}")
                        candidate_errors.append(f"candidate {idx + 1}: {error_msg}")
                        if use_scene_by_scene:
                            try:
                                logger.info(f"Retrying candidate {idx + 1} without scene-by-scene...")
                                fallback = await orchestrator.generate_chapter(
                                    chapter_number=request.chapter_number,
                                    target_words=effective_target_words,
                                    stage=generation_stage,
                                    context=llm_context
                                )
                                if fallback and fallback.success and fallback.content.strip():
                                    result = fallback
                                else:
                                    fallback_error = fallback.error if fallback else "no result"
                                    candidate_errors.append(f"candidate {idx + 1} fallback: {fallback_error}")
                                    continue
                            except Exception as fallback_err:
                                candidate_errors.append(f"candidate {idx + 1} fallback exception: {fallback_err}")
                                continue
                        else:
                            continue

                    content = result.content
                    if not content or len(content.strip()) < 100:
                        logger.warning(f"Candidate {idx + 1} content too short")
                        candidate_errors.append(f"candidate {idx + 1}: content too short")
                        continue

                    # Capture the actual model used (best-effort) for accurate reporting/persistence.
                    try:
                        if isinstance(getattr(result, "metadata", None), dict):
                            m = result.metadata.get("model") or result.metadata.get("model_used")
                            if isinstance(m, str) and m.strip():
                                detected_model_used = m.strip()
                    except Exception:
                        pass

                    # Soft safeguard: if scene-by-scene output is severely short, try once without scene-by-scene.
                    try:
                        wc = len(content.split())
                        if use_scene_by_scene and wc < int(effective_target_words * 0.7):
                            budget = llm_context.get("postdraft_budget") if isinstance(llm_context, dict) else None
                            remaining = int((budget or {}).get("remaining", 0) or 0) if isinstance(budget, dict) else 0
                            if remaining > 0:
                                try:
                                    budget["remaining"] = max(0, remaining - 1)
                                    budget["used"] = int(budget.get("used", 0) or 0) + 1
                                    (budget.get("actions") if isinstance(budget.get("actions"), list) else []).append("short_output_safeguard")
                                except Exception:
                                    pass
                                fallback2 = await orchestrator.generate_chapter(
                                    chapter_number=request.chapter_number,
                                    target_words=effective_target_words,
                                    stage=generation_stage,
                                    context=llm_context,
                                )
                                if fallback2 and fallback2.success and (fallback2.content or "").strip():
                                    content = fallback2.content
                    except Exception:
                        pass

                    evaluation = {}
                    if quality_orchestrator:
                        try:
                            evaluation = await quality_orchestrator.evaluate_candidate(
                                content,
                                request.chapter_number,
                                llm_context
                            )
                        except Exception as eval_err:
                            logger.warning(f"Candidate {idx + 1} evaluation failed: {eval_err}")
                    score = evaluation.get("score", 0.0)
                    candidates.append({
                        "content": content,
                        "metadata": result.metadata,
                        **evaluation
                    })
                    logger.info(f"Candidate {idx + 1}/{candidate_count} scored {score:.2f}")
                    try:
                        early_stop_score = float(os.getenv("CHAPTER_EARLY_STOP_SCORE", "9.0"))
                        if quality_orchestrator and quality_orchestrator._passes_quality_gates(evaluation.get("quality_result", {})) and float(score) >= early_stop_score:
                            logger.info(
                                f"Early-stopping candidate search: candidate {idx + 1} cleared gates with score {score:.2f}."
                            )
                            break
                    except Exception:
                        pass

                if not candidates and not skeleton_success:
                    error_detail = "Chapter generation failed to produce any usable candidates"
                    if candidate_errors:
                        error_detail += f". Errors: {' | '.join(candidate_errors[:6])}"
                    raise Exception(error_detail)

                if candidates:
                    if quality_orchestrator:
                        passing = []
                        for candidate in candidates:
                            try:
                                if quality_orchestrator._passes_quality_gates(candidate.get("quality_result", {})):
                                    passing.append(candidate)
                            except Exception as gate_err:
                                logger.warning(f"Quality gate check failed for candidate: {gate_err}")
                        pool = passing if passing else candidates
                        best = max(pool, key=lambda c: c.get("score", 0.0))
                    else:
                        best = candidates[0]

                    generated_content = best["content"]
                    try:
                        if isinstance(best, dict):
                            md = best.get("metadata") or {}
                            if isinstance(md, dict):
                                m = md.get("model") or md.get("model_used")
                                if isinstance(m, str) and m.strip():
                                    detected_model_used = m.strip()
                    except Exception:
                        pass
                if candidates and quality_orchestrator and not quality_orchestrator._passes_quality_gates(best.get("quality_result", {})):
                    # Prefer regeneration over editing/polish when gates fail.
                    max_regen_rounds = max(0, int(os.getenv("CHAPTER_MAX_REGEN_ROUNDS", "3")))
                    regen_round = 0
                    while regen_round < max_regen_rounds and not quality_orchestrator._passes_quality_gates(best.get("quality_result", {})):
                        # Enforce post-draft LLM cap (regen is post-draft churn)
                        budget = llm_context.get("postdraft_budget") if isinstance(llm_context, dict) else None
                        remaining = int((budget or {}).get("remaining", 0) or 0) if isinstance(budget, dict) else 0
                        if remaining <= 0:
                            logger.info("Post-draft LLM budget exhausted; skipping further regeneration.")
                            break
                        try:
                            budget["remaining"] = max(0, remaining - 1)
                            budget["used"] = int(budget.get("used", 0) or 0) + 1
                            (budget.get("actions") if isinstance(budget.get("actions"), list) else []).append("regen_round")
                        except Exception:
                            pass

                        regen_round += 1
                        logger.info(
                            f"Chapter {request.chapter_number} failed quality gates; regenerating candidate (round {regen_round}/{max_regen_rounds})"
                        )
                        try:
                            llm_context["regen_feedback"] = quality_orchestrator._build_regen_feedback(best.get("quality_result", {}) or {})
                        except Exception:
                            llm_context["regen_feedback"] = ""
                        regen_result = None
                        if generation_stage == "5-stage":
                            results = await orchestrator.generate_chapter_5_stage(
                                chapter_number=request.chapter_number,
                                target_words=effective_target_words,
                                context=llm_context
                            )
                            regen_result = results[-1] if results else None
                        else:
                            if use_scene_by_scene:
                                regen_result = await orchestrator.generate_chapter_scene_by_scene(
                                    chapter_number=request.chapter_number,
                                    target_words=effective_target_words,
                                    context=llm_context
                                )
                            else:
                                regen_result = await orchestrator.generate_chapter(
                                    chapter_number=request.chapter_number,
                                    target_words=effective_target_words,
                                    stage=generation_stage,
                                    context=llm_context
                                )

                        try:
                            if regen_result and isinstance(getattr(regen_result, "metadata", None), dict):
                                m = regen_result.metadata.get("model") or regen_result.metadata.get("model_used")
                                if isinstance(m, str) and m.strip():
                                    detected_model_used = m.strip()
                        except Exception:
                            pass

                        if not regen_result or not regen_result.success or not (regen_result.content or "").strip():
                            err = regen_result.error if regen_result else "no result"
                            logger.warning(f"Regeneration candidate failed: {err}")
                            break

                        regen_eval = await quality_orchestrator.evaluate_candidate(
                            regen_result.content,
                            request.chapter_number,
                            llm_context
                        )
                        candidates.append({
                            "content": regen_result.content,
                            "metadata": regen_result.metadata,
                            **regen_eval
                        })
                        passing = [c for c in candidates if quality_orchestrator._passes_quality_gates(c.get("quality_result", {}))]
                        pool = passing if passing else candidates
                        best = max(pool, key=lambda c: c.get("score", 0.0))
                        generated_content = best["content"]

                if candidates:
                    tokens_used = (best.get("metadata") or {}).get('tokens_used', tokens_used)
                    cost_breakdown = (best.get("metadata") or {}).get('cost_breakdown', cost_breakdown)

                # Normalize to plain text (no markdown artifacts).
                generated_content = _normalize_plain_text_output(generated_content)
                logger.info(f"✅ AI generation completed ({len(generated_content)} characters)")

                # Drift/cadence enforcement: if style drift or cadence repetition is detected,
                # do one bounded regeneration attempt using regen_feedback.
                try:
                    voice_drift_min = float(os.getenv("VOICE_DRIFT_MIN", "0.6"))
                    voice_lookback = int(os.getenv("VOICE_DRIFT_LOOKBACK", "10"))
                    cadence_sim_max = float(os.getenv("CADENCE_SIM_MAX", "0.85"))
                    cadence_lookback = int(os.getenv("CADENCE_LOOKBACK", "3"))
                except Exception:
                    voice_drift_min = 0.6
                    voice_lookback = 10
                    cadence_sim_max = 0.85
                    cadence_lookback = 3

                drift_issues: list[str] = []
                drift_metrics: dict[str, Any] = {}
                try:
                    from backend.auto_complete.helpers.voice_fingerprint_manager import VoiceFingerprintManager
                    from backend.auto_complete.helpers.cadence_analyzer import CadenceAnalyzer
                    voice_manager_tmp = VoiceFingerprintManager(str(project_workspace))
                    cadence_tmp = CadenceAnalyzer(str(project_workspace))

                    fps = voice_manager_tmp.fingerprints_from_text(request.chapter_number, generated_content)
                    drift_scores = []
                    for character, fp in (fps or {}).items():
                        score = voice_manager_tmp.global_character_drift(character, fp, lookback=voice_lookback)
                        if score is None:
                            continue
                        drift_scores.append((character, float(score)))
                        if float(score) < voice_drift_min:
                            drift_issues.append(f"Voice drift for {character} (similarity {float(score):.2f} < {voice_drift_min:.2f}).")
                    if drift_scores:
                        drift_metrics["voice_drift"] = drift_scores[:6]

                    cadence_sim = cadence_tmp.cadence_similarity_score(
                        request.chapter_number,
                        generated_content,
                        lookback=cadence_lookback
                    )
                    if cadence_sim is not None:
                        drift_metrics["cadence_similarity"] = float(cadence_sim)
                        if float(cadence_sim) > cadence_sim_max:
                            drift_issues.append(f"Cadence too similar to recent chapters (similarity {float(cadence_sim):.2f} > {cadence_sim_max:.2f}).")
                except Exception:
                    pass

                if drift_issues and quality_orchestrator:
                    try:
                        llm_context["regen_feedback"] = " ".join(drift_issues) + " Regenerate with clearer voice separation and altered sentence rhythm while preserving plot beats."
                    except Exception:
                        llm_context["regen_feedback"] = ""
                    try:
                        regen = await orchestrator.generate_chapter(
                            chapter_number=request.chapter_number,
                            target_words=effective_target_words,
                            stage=generation_stage,
                            context=llm_context
                        )
                        if regen and regen.success and (regen.content or "").strip():
                            regen_eval = await quality_orchestrator.evaluate_candidate(
                                regen.content,
                                request.chapter_number,
                                llm_context
                            )
                            # Accept regeneration only if it improves score and passes gates (or current did not pass).
                            current_score = float(best.get("score", 0.0)) if isinstance(best, dict) else 0.0
                            regen_score = float(regen_eval.get("score", 0.0)) if isinstance(regen_eval, dict) else 0.0
                            regen_passes = quality_orchestrator._passes_quality_gates(regen_eval.get("quality_result", {}))
                            current_passes = quality_orchestrator._passes_quality_gates(best.get("quality_result", {}))
                            if regen_passes and (not current_passes or regen_score >= current_score):
                                generated_content = _normalize_plain_text_output(regen.content)
                                best = {"content": generated_content, "metadata": regen.metadata, **regen_eval}
                                logger.info(f"Accepted drift/cadence regeneration (score {regen_score:.2f} vs {current_score:.2f})")
                            else:
                                logger.info("Drift/cadence regeneration did not improve gates/score; keeping original candidate.")
                    except Exception as _drift_regen_err:
                        logger.warning(f"Drift/cadence regeneration attempt failed: {_drift_regen_err}")

                # Attach drift metrics into run summary (best-effort).
                try:
                    if "run_summary" in locals() and isinstance(locals().get("run_summary"), dict):
                        locals()["run_summary"].setdefault("drift_metrics", drift_metrics)
                except Exception:
                    pass

            # Ensure polish path is also normalized to plain text.
            if rewrite_mode == "polish":
                generated_content = _normalize_plain_text_output(generated_content)

            _mark("llm_end")

            # Update pattern database with the new chapter if available
            try:
                from backend.system.pattern_database_engine import PatternDatabase
                try:
                    from backend.utils.paths import get_project_workspace, ensure_project_structure
                except Exception:
                    from utils.paths import get_project_workspace, ensure_project_structure

                project_workspace = get_project_workspace(request.project_id)
                ensure_project_structure(project_workspace)
                project_state_path = project_workspace
                pattern_db = PatternDatabase(str(project_state_path))
                pattern_db.add_chapter_patterns(request.chapter_number, generated_content)
            except Exception as pattern_err:
                logger.warning(f"Failed to update pattern database after generation: {pattern_err}")

            # Record anti-pattern signals for future chapter variety
            if pattern_tracker:
                try:
                    signals = pattern_tracker.extract_signals(
                        request.chapter_number, generated_content,
                        known_characters=focus_characters if isinstance(focus_characters, list) else []
                    )
                    pattern_tracker.record_chapter(signals)
                    logger.info(
                        f"Chapter {request.chapter_number} patterns recorded: shape={signals.chapter_shape}, "
                        f"opening={signals.opening_type}, ending={signals.ending_type}"
                    )
                except Exception as sig_err:
                    logger.debug(f"Failed to record chapter pattern signals: {sig_err}")

            # Persist chapter file for continuity tooling
            try:
                chapter_file = project_workspace / "chapters" / f"chapter-{request.chapter_number:02d}.md"
                chapter_file.write_text(generated_content, encoding="utf-8")
            except Exception as file_err:
                logger.warning(f"Failed to save chapter file locally: {file_err}")

            # Update continuity state, cadence, and voice fingerprints
            try:
                from backend.auto_complete.helpers.chapter_context_manager import ChapterContextManager
                from backend.auto_complete.helpers.cadence_analyzer import CadenceAnalyzer
                from backend.auto_complete.helpers.voice_fingerprint_manager import VoiceFingerprintManager
                context_manager = ChapterContextManager(str(project_workspace))
                context_manager.analyze_chapter_content(request.chapter_number, generated_content)
                cadence_analyzer = CadenceAnalyzer(str(project_workspace))
                cadence_analyzer.store(cadence_analyzer.analyze(request.chapter_number, generated_content))
                voice_manager = VoiceFingerprintManager(str(project_workspace))
                voice_manager.analyze_chapter(request.chapter_number, generated_content)
            except Exception as continuity_err:
                logger.warning(f"Failed to update continuity tooling: {continuity_err}")

            # Update chapter ledger (delta summary)
            try:
                from backend.services.chapter_ledger_service import update_chapter_ledger, update_local_chapter_ledger
                pov_context = {
                    "pov_character": llm_context.get("pov_character", ""),
                    "pov_type": llm_context.get("pov_type", ""),
                    "pov_notes": llm_context.get("pov_notes", "")
                }
                ledger_result = await update_chapter_ledger(
                    project_id=request.project_id,
                    user_id=user_id,
                    chapter_number=request.chapter_number,
                    chapter_content=generated_content,
                    book_bible=book_bible_content,
                    references=references_content,
                    pov_context=pov_context,
                    vector_store_ids=llm_context.get("vector_store_ids", [])
                )
                if ledger_result.get("success") and ledger_result.get("entry"):
                    update_local_chapter_ledger(str(project_workspace), ledger_result["entry"], request.chapter_number)
            except Exception as ledger_err:
                logger.warning(f"Failed to update chapter ledger: {ledger_err}")

        except Exception as e:
            summary = _summarize_generation_failure(str(e))
            try:
                rid = None
                try:
                    if request_id_contextvar is not None:
                        rid = request_id_contextvar.get()
                except Exception:
                    rid = None
                emit_summary(
                    logger,
                    {
                        "event": "CHAPTER_RUN_SUMMARY",
                        "status": "error",
                        "mode": "over_time",
                        "run_id": chapter_run_id,
                        "request_id": rid,
                        "project_id": request.project_id,
                        "chapter_number": request.chapter_number,
                        "requested_stage": (locals().get("requested_stage") if "requested_stage" in locals() else (request.stage or "unknown")),
                        "generation_stage": (locals().get("generation_stage") if "generation_stage" in locals() else "unknown"),
                        "allow_5_stage": bool(locals().get("allow_5_stage", False)),
                        "error": f"{type(e).__name__}: {str(e)[:480]}",
                        "error_summary": summary,
                    },
                )
            except Exception:
                pass
            logger.error(f"💥 AI generation failed: {e}")
            
            # Return proper JSON error response to prevent frontend parse errors
            from fastapi.responses import JSONResponse
            error_detail = f"Chapter generation failed: {str(e)}"
            
            # Check if this is a timeout or specific OpenAI error
            if "timeout" in str(e).lower():
                return JSONResponse(
                    status_code=504,
                    content={
                        "error": "GENERATION_TIMEOUT",
                        "message": "Chapter generation timed out. Please try again.",
                        "detail": error_detail
                    }
                )
            elif "rate_limit" in str(e).lower() or "429" in str(e):
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "RATE_LIMIT_EXCEEDED",
                        "message": "Rate limit exceeded. Please try again in a moment.",
                        "detail": error_detail
                    }
                )
            else:
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": "GENERATION_FAILED",
                        "message": "Chapter generation failed. Please try again.",
                        "detail": error_detail
                    }
                )
        
        # Consistency check against canon and references
        if os.getenv("ENABLE_CONSISTENCY_CHECK", "true").lower() == "true":
            try:
                try:
                    from backend.services.chapter_context_builder import get_canon_log
                    canon_log_content = get_canon_log(references_content)
                except Exception:
                    canon_log_content = references_content.get("canon-log.md") or references_content.get("canon_log") or ""
                from backend.services.consistency_check_service import check_chapter_consistency
                check_result = await check_chapter_consistency(
                    chapter_number=request.chapter_number,
                    chapter_content=generated_content,
                    book_bible=book_bible_content,
                    references=references_content,
                    canon_log=canon_log_content,
                    vector_store_ids=llm_context.get("vector_store_ids", []),
                    user_id=user_id
                )
                if check_result.get("severity") == "high" and check_result.get("rewrite_instruction"):
                    from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig
                    credits_enabled = os.getenv('ENABLE_CREDITS_SYSTEM', 'false').lower() == 'true'
                    enable_billing = os.getenv('ENABLE_CREDITS_BILLING', 'false').lower() == 'true' and credits_enabled
                    fixer = LLMOrchestrator(
                        retry_config=RetryConfig(max_retries=2),
                        user_id=user_id,
                        enable_billing=enable_billing
                    )
                    rewrite = await fixer.rewrite_full_chapter(
                        chapter_text=generated_content,
                        instruction=check_result["rewrite_instruction"],
                        context={
                            "book_bible": book_bible_content,
                            "references": references_content,
                            "canon_source": canon_log_content,
                            "canon_label": "Canon Log",
                            "vector_store_ids": llm_context.get("vector_store_ids", []),
                            "use_file_search": True
                        },
                        chapter_number=request.chapter_number,
                    )
                    if rewrite.success and rewrite.content.strip():
                        generated_content = _normalize_plain_text_output(rewrite.content)
            except Exception as check_err:
                logger.warning(f"Consistency check failed: {check_err}")

        # Create chapter data structure for database
        logger.info("💾 Preparing chapter data for database...")
        model_used_actual = None
        try:
            # Prefer detected model from the chosen candidate/regeneration, else orchestrator model.
            if "detected_model_used" in locals() and isinstance(locals().get("detected_model_used"), str):
                candidate_model = str(locals().get("detected_model_used") or "").strip()
                model_used_actual = candidate_model or None
        except Exception:
            model_used_actual = None
        try:
            if not model_used_actual and "orchestrator" in locals():
                om = getattr(locals().get("orchestrator"), "model", None)
                if isinstance(om, str) and om.strip():
                    model_used_actual = om.strip()
        except Exception:
            pass
        model_used_actual = model_used_actual or (os.getenv("DEFAULT_AI_MODEL") or "").strip() or "unknown"
        chapter_data = {
            'project_id': request.project_id,
            'chapter_number': request.chapter_number,
            'content': generated_content,
            'title': f"Chapter {request.chapter_number}",
            'metadata': {
                'run_id': chapter_run_id,
                'word_count': len(generated_content.split()),
                'target_word_count': effective_target_words,
                'target_words_min': target_words_min,
                'target_words_max': target_words_max,
                'created_by': user_id,
                'stage': 'draft',
                'generation_time': 0.0,  # Could track actual time
                'retry_attempts': 0,
                'model_used': model_used_actual,
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
                rewrite_reason = "ai_rewrite"
                if rewrite_mode == "polish":
                    rewrite_reason = "ai_polish_rewrite"
                elif rewrite_mode == "full":
                    rewrite_reason = "ai_full_regenerate"
                
                # Update the existing chapter with new content using dot notation for nested fields
                update_data = {
                    'content': generated_content,
                    'metadata.run_id': chapter_run_id,
                    'metadata.word_count': len(generated_content.split()),
                    'metadata.updated_at': datetime.now(timezone.utc),
                    'metadata.updated_by': user_id,
                    'metadata.model_used': model_used_actual,
                    'metadata.tokens_used': tokens_used,
                    'metadata.cost_breakdown': cost_breakdown,
                    'metadata.last_generation_reason': rewrite_reason
                }
                
                from backend.database_integration import get_database_adapter
                db = get_database_adapter()
                success = await db.update_chapter(chapter_id, update_data, user_id, request.project_id)
                if not success:
                    raise Exception("Failed to update chapter")

                version_data = {
                    'content': generated_content,
                    'reason': rewrite_reason,
                    'user_id': user_id,
                    'changes_summary': f'AI rewrite ({rewrite_reason}) using {request.stage} generation'
                }
                await db.add_chapter_version(chapter_id, version_data, user_id, request.project_id)
                
                logger.info(f"✅ Chapter {request.chapter_number} updated successfully")
            else:
                # Create new chapter
                logger.info(f"🆕 Creating new chapter {request.chapter_number}...")
                chapter_id = await create_chapter(chapter_data, user_id)
                
                if not chapter_id:
                    raise Exception("Chapter creation returned invalid ID")
                    
                logger.info(f"✅ New chapter {request.chapter_number} created successfully")

            # Update vector memory with latest chapter content
            try:
                vector_service = VectorStoreService()
                await vector_service.upsert_chapter(
                    project_id=request.project_id,
                    user_id=user_id,
                    chapter_id=chapter_id,
                    chapter_number=request.chapter_number,
                    title=f"Chapter {request.chapter_number}",
                    content=generated_content
                )
            except Exception as vector_err:
                logger.warning(f"Failed to update vector memory for chapter {request.chapter_number}: {vector_err}")

            try:
                from backend.services.canon_log_service import update_canon_log
                background_tasks.add_task(
                    update_canon_log,
                    request.project_id,
                    user_id,
                    request.chapter_number,
                    generated_content,
                    book_bible_content,
                    references_content,
                    llm_context.get("vector_store_ids", [])
                )
            except Exception as canon_err:
                logger.warning(f"Failed to queue canon log update: {canon_err}")
                
        except Exception as e:
            logger.error(f"💥 Database error saving chapter: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save generated chapter to database"
            )
        
        logger.info(f"✅ Chapter saved with ID: {chapter_id}")
        _mark("db_saved")
        
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
            _mark("usage_tracked")
        except Exception as e:
            logger.warning(f"⚠️ Failed to track usage for user {user_id}: {e}")
        
        logger.info(f"🎉 Chapter generation completed successfully!")

        # Single structured chapter run summary (log + persisted to chapter metadata)
        try:
            rid = None
            try:
                if request_id_contextvar is not None:
                    rid = request_id_contextvar.get()
            except Exception:
                rid = None

            now = time.perf_counter()
            total_ms = int((now - perf_t0) * 1000)

            def _span_ms(start_key: str, end_key: str) -> Optional[int]:
                a = perf_marks.get(start_key)
                b = perf_marks.get(end_key)
                if a is None or b is None:
                    return None
                return int((b - a) * 1000)

            llm_perf = {}
            try:
                llm_perf = (best.get("metadata") or {}).get("perf_summary") or {}
            except Exception:
                llm_perf = {}

            canon_text = ""
            try:
                canon_text = canon_log_content  # type: ignore[name-defined]
            except Exception:
                canon_text = ""

            ledger_text_value = ""
            try:
                ledger_text_value = ledger_text  # type: ignore[name-defined]
            except Exception:
                ledger_text_value = ""

            run_summary: dict[str, Any] = {
                "event": "CHAPTER_RUN_SUMMARY",
                "status": "success",
                "mode": "over_time",
                "run_id": chapter_run_id,
                "request_id": rid,
                "project_id": request.project_id,
                "chapter_id": chapter_id,
                "chapter_number": request.chapter_number,
                "rewrite_mode": (rewrite_mode or "").strip(),
                "requested_stage": str(locals().get("requested_stage", "")),
                "generation_stage": generation_stage,
                "allow_5_stage": bool(locals().get("allow_5_stage", False)),
                "scene_by_scene": bool(use_scene_by_scene),
                "candidate_count": int(len(candidates)) if "candidates" in locals() and isinstance(locals().get("candidates"), list) else int(candidate_count),
                "regen_rounds": int(regen_round) if "regen_round" in locals() else 0,
                "selected_candidate_score": float(best.get("score", 0.0)) if isinstance(best, dict) else 0.0,
                "postdraft_budget": (llm_context.get("postdraft_budget") if isinstance(llm_context, dict) else {}),
                "timing_ms": {
                    "total_ms": total_ms,
                    "project_fetch_ms": _span_ms("start", "project_fetched"),
                    "book_plan_ms": _span_ms("project_fetched", "book_plan_done") if "book_plan_done" in perf_marks else int(chapter_context.get("book_plan_ms") or 0),
                    "llm_ms": _span_ms("llm_start", "llm_end"),
                    "db_save_ms": _span_ms("llm_end", "db_saved"),
                    "usage_track_ms": _span_ms("db_saved", "usage_tracked"),
                },
                "targets": {
                    "effective_target_word_count": int(effective_target_words),
                    "target_words_min": int(target_words_min),
                    "target_words_max": int(target_words_max),
                },
                "book_plan": {
                    "source": str(chapter_context.get("book_plan_source") or ""),
                },
                "tokens": tokens_used,
                "cost_breakdown": cost_breakdown,
                "output": {
                    "word_count": len((generated_content or "").split()),
                    "ended_cleanly": bool(generated_content and generated_content.rstrip()[-1:] in {".", "!", "?", "\"", "”", "’"}),
                    "em_dash_count": int((generated_content or "").count("—") + (generated_content or "").count("–")),
                },
                "continuity_inputs": {
                    "book_bible": text_stats(book_bible_content),
                    "canon_log": text_stats(canon_text),
                    "chapter_ledger": text_stats(ledger_text_value),
                },
                "llm_perf": llm_perf,
                "style_signals": (best.get("quality_result") or {}).get("style_signals") if isinstance(best, dict) else {},
                "continuity_audits": (best.get("quality_result") or {}).get("continuity_audits") if isinstance(best, dict) else {},
            }

            emit_summary(logger, run_summary)

            # Persist onto chapter metadata (best-effort).
            try:
                from backend.database_integration import get_database_adapter
                db = get_database_adapter()
                await db.update_chapter(
                    chapter_id,
                    {
                        "metadata.run_id": chapter_run_id,
                        "metadata.run_summary": run_summary,
                    },
                    user_id,
                    request.project_id,
                )
            except Exception:
                pass
        except Exception:
            pass
        
        return {
            'chapter_id': chapter_id,
            'content': generated_content,
            'message': 'Chapter generated successfully with AI',
            'word_count': len(generated_content.split()),
            'target_word_count': effective_target_words,
            'generation_cost': cost_breakdown['total_cost'],
            'model_used': model_used_actual,
            # Transparency: what was requested vs what actually ran.
            'requested_stage': str(locals().get("requested_stage", "")),
            'generation_stage': generation_stage,
            'allow_5_stage': bool(locals().get("allow_5_stage", False)),
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions (they're already properly handled)
        raise
    except Exception as e:
        # Fail fast on provider quota/billing exhaustion (avoid candidate/regeneration loops).
        try:
            if LLMQuotaError is not None and isinstance(e, LLMQuotaError):
                raise HTTPException(
                    status_code=402,
                    detail="OpenAI quota/billing exhausted. Please check your OpenAI plan and billing details and try again.",
                )
        except HTTPException:
            raise
        except Exception:
            pass

        # Emit a single structured summary line on unexpected errors as well.
        try:
            rid = None
            try:
                if request_id_contextvar is not None:
                    rid = request_id_contextvar.get()
            except Exception:
                rid = None
            emit_summary(
                logger,
                {
                    "event": "CHAPTER_RUN_SUMMARY",
                    "status": "error",
                    "mode": "over_time",
                    "run_id": locals().get("chapter_run_id"),
                    "request_id": rid,
                    "project_id": getattr(request, "project_id", None),
                    "chapter_number": getattr(request, "chapter_number", None),
                    "error": f"{type(e).__name__}: {str(e)[:480]}",
                },
            )
        except Exception:
            pass
        logger.error(f"💥 Unexpected error in chapter generation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chapter generation failed: {str(e)}"
        )


@router.get("/context-audit", response_model=dict)
async def get_generation_context_audit(
    project_id: str = Query(...),
    chapter_number: int = Query(..., ge=1),
    target_word_count: int = Query(2000, ge=200, le=20000),
    include_full: bool = Query(False),
    current_user: dict = Depends(get_current_user)
):
    """Return the assembled generation context for auditing/debug."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user authentication"
            )

        project_data = await get_project(project_id)
        if not project_data:
            raise HTTPException(status_code=404, detail="Project not found")

        owner_id = project_data.get('metadata', {}).get('owner_id')
        collaborators = project_data.get('metadata', {}).get('collaborators', [])
        if owner_id != user_id and user_id not in collaborators:
            raise HTTPException(status_code=403, detail="Access denied to this project")

        # Load book bible and references
        book_bible_content = ""
        references_content: dict[str, str] = {}
        if 'files' in project_data and 'book-bible.md' in project_data['files']:
            book_bible_content = project_data['files']['book-bible.md']
        elif 'book_bible' in project_data:
            bb_entry = project_data['book_bible']
            if isinstance(bb_entry, dict):
                book_bible_content = bb_entry.get('content', '')
            elif isinstance(bb_entry, str):
                book_bible_content = bb_entry

        if 'references' in project_data and isinstance(project_data['references'], dict):
            for ref_name, ref_val in project_data['references'].items():
                if isinstance(ref_val, dict):
                    references_content[ref_name] = ref_val.get('content', '')
                elif isinstance(ref_val, str):
                    references_content[ref_name] = ref_val

        if not references_content and 'reference_files' in project_data:
            for ref_name, ref_content in project_data['reference_files'].items():
                if ref_name.endswith('.md'):
                    references_content[ref_name] = ref_content

        if not references_content:
            try:
                reference_docs = await get_project_reference_files(project_id)
                for ref in reference_docs:
                    fname = ref.get('filename', 'unnamed.md')
                    references_content[fname] = ref.get('content', '')
            except Exception:
                pass

        try:
            from backend.services.chapter_context_builder import normalize_references
            references_content = normalize_references(references_content)
        except Exception:
            pass

        chapter_context = {
            'book_bible_content': book_bible_content,
            'references': references_content,
            'chapter_number': chapter_number,
            'target_word_count': target_word_count,
            'project_id': project_id
        }

        # Previous chapters summary + endings
        previous_chapters = []
        try:
            existing_chapters = await get_project_chapters(project_id)
            previous_chapters = [ch for ch in existing_chapters if ch.get('chapter_number', 0) < chapter_number]
            if previous_chapters:
                previous_chapters.sort(key=lambda x: x.get('chapter_number', 0))
                recent_summaries = []
                for prev_ch in previous_chapters[-3:]:
                    content = prev_ch.get('content', '')
                    summary = content[:200] + "..." if len(content) > 200 else content
                    recent_summaries.append(f"Chapter {prev_ch.get('chapter_number')}: {summary}")
                chapter_context['previous_chapters_summary'] = "\n".join(recent_summaries)

                try:
                    immediate_prev = previous_chapters[-1]
                    prev_content = immediate_prev.get('content', '')
                    paragraphs = [p.strip() for p in prev_content.split('\n\n') if p.strip()]
                    last_paragraph = paragraphs[-1] if paragraphs else ''
                    chapter_context['last_chapter_ending'] = last_paragraph[-400:] if last_paragraph else ''
                except Exception:
                    chapter_context['last_chapter_ending'] = ''
        except Exception:
            chapter_context['previous_chapters_summary'] = ""
            chapter_context['last_chapter_ending'] = ''

        # Director notes
        try:
            notes = await list_story_notes(project_id, user_id)
            if notes:
                chapter_number_lookup = {
                    ch.get('id'): ch.get('chapter_number') for ch in previous_chapters if ch.get('id')
                }
                usable_notes = []
                for note in notes:
                    if note.get('resolved'):
                        continue
                    if note.get('apply_to_future') is False:
                        continue
                    if not (note.get('content') or '').strip():
                        continue
                    usable_notes.append(note)

                def _note_sort_key(note: dict) -> float:
                    created = note.get('created_at')
                    try:
                        if hasattr(created, 'timestamp'):
                            return float(created.timestamp())
                        if hasattr(created, 'seconds'):
                            return float(created.seconds)
                        if isinstance(created, str):
                            return datetime.fromisoformat(created.replace('Z', '+00:00')).timestamp()
                    except Exception:
                        pass
                    return 0.0

                usable_notes = sorted(usable_notes, key=_note_sort_key, reverse=True)
                note_lines: list[str] = []
                for note in usable_notes[:12]:
                    scope = note.get('scope', 'chapter')
                    chapter_id = note.get('chapter_id')
                    chapter_label = "GLOBAL" if scope == 'global' else "Chapter Note"
                    if scope != 'global' and chapter_id:
                        ch_num = chapter_number_lookup.get(chapter_id)
                        chapter_label = f"Chapter {ch_num}" if ch_num else "Chapter Note"
                    intent = f"[{note.get('intent')}]" if note.get('intent') else ""
                    selection_text = (note.get('selection_text') or '').strip()
                    selection_segment = f"Selection: \"{selection_text[:180].replace(chr(10), ' ')}\"" if selection_text else ""
                    content_text = (note.get('content') or '').strip()
                    line_parts = [chapter_label, intent, content_text, selection_segment]
                    line = " ".join([p for p in line_parts if p])
                    note_lines.append(line[:400])
                if note_lines:
                    chapter_context['director_notes'] = "\n".join(note_lines)
        except Exception:
            pass

        # Pattern database summary
        pattern_summary_text = ""
        repetition_risks = {}
        try:
            from backend.utils.paths import get_project_workspace, ensure_project_structure
        except Exception:
            from utils.paths import get_project_workspace, ensure_project_structure
        try:
            project_workspace = get_project_workspace(project_id)
            ensure_project_structure(project_workspace)
            project_state_path = project_workspace
            try:
                import sys
                backend_dir = Path(__file__).resolve().parents[1]
                repo_root = Path(__file__).resolve().parents[2]
                for path in (str(backend_dir), str(repo_root)):
                    if path not in sys.path:
                        sys.path.insert(0, path)
                try:
                    from backend.system.pattern_database_engine import PatternDatabase
                except Exception as backend_err:
                    try:
                        from system.pattern_database_engine import PatternDatabase
                    except Exception as system_err:
                        module_candidates = [
                            backend_dir / "system" / "pattern_database_engine.py",
                            backend_dir / "system" / "pattern-database-engine.py",
                            repo_root / "backend" / "system" / "pattern_database_engine.py",
                            repo_root / "backend" / "system" / "pattern-database-engine.py",
                            repo_root / "backend" / "backend" / "system" / "pattern_database_engine.py",
                            repo_root / "backend" / "backend" / "system" / "pattern-database-engine.py",
                            repo_root / "system" / "pattern_database_engine.py",
                            repo_root / "system" / "pattern-database-engine.py",
                        ]
                        module_path = next((path for path in module_candidates if path.exists()), None)
                        if not module_path:
                            searched = ", ".join(str(path) for path in module_candidates)
                            raise Exception(
                                "backend.system import failed: "
                                f"{backend_err}; system import failed: {system_err}; "
                                f"pattern database file not found under {searched}"
                            )
                        spec = importlib.util.spec_from_file_location("pattern_database_engine", module_path)
                        if not spec or not spec.loader:
                            raise Exception(f"Pattern database module spec unavailable: {module_path}")
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        PatternDatabase = getattr(module, "PatternDatabase")
                pattern_db = PatternDatabase(str(project_state_path))
                summary = pattern_db.get_pattern_summary()
                repetition_risks = summary.get("recent_risks", {})
                pattern_summary_text = "\n".join([
                    f"Chapters tracked: {summary.get('chapters_tracked', 0)}",
                    f"Total metaphors: {summary.get('total_metaphors', 0)}",
                    f"Total similes: {summary.get('total_similes', 0)}",
                    f"Sentence patterns: {summary.get('sentence_patterns', 0)}",
                    f"Paragraph patterns: {summary.get('paragraph_patterns', 0)}",
                    f"Dialogue tags: {summary.get('dialogue_tags', 0)}",
                    f"Freshness score: {repetition_risks.get('score', 0)}/10"
                ])
            except Exception:
                pass
        except Exception:
            pass

        # Book plan
        chapter_plan = {}
        try:
            from backend.auto_complete.helpers.book_plan_generator import BookPlanGenerator
            plan_generator = BookPlanGenerator(str(project_state_path))
            plan_data = None
            plan_filename = "book-plan.json"

            # Prefer persistent cache from project references. In this debug/audit context,
            # do NOT generate missing plans (avoid surprise LLM work).
            plan_raw = (
                references_content.get(plan_filename)
                or references_content.get("book_plan.json")
                or references_content.get("book-plan")
                or ""
            )
            if isinstance(plan_raw, str) and plan_raw.strip().startswith("{"):
                try:
                    plan_data = json.loads(plan_raw)
                except Exception:
                    plan_data = None

            if not plan_data:
                plan_data = plan_generator.load_existing_plan()
            if plan_data:
                for chapter in plan_data.get("chapters", []):
                    if chapter.get("chapter_number") == chapter_number:
                        chapter_plan = chapter
                        break
        except Exception:
            pass

        # Vector context
        vector_context = ""
        vector_guidelines = ""
        try:
            plan_summary = chapter_plan.get("summary", "")
            required_points = chapter_plan.get("required_plot_points", [])
            focus_chars = chapter_plan.get("focal_characters", [])
            note_summary = chapter_context.get("director_notes", "")
            previous_summary = chapter_context.get("previous_chapters_summary", "")
            query_parts = [
                f"Chapter {chapter_number}",
                plan_summary,
                "Required plot points: " + ", ".join(required_points) if required_points else "",
                "Focus characters: " + ", ".join(focus_chars) if focus_chars else "",
                "Director notes: " + note_summary if note_summary else "",
                "Previous summary: " + previous_summary if previous_summary else "",
            ]
            vector_query = ". ".join([p for p in query_parts if p])
            if vector_query:
                vector_context = await _build_vector_prompt_context(
                    project_id=project_id,
                    user_id=user_id,
                    query=vector_query,
                    max_results=12
                )
            vector_guidelines = await _build_vector_prompt_context(
                project_id=project_id,
                user_id=user_id,
                query="Style guide, tone requirements, and writing rules for this project.",
                max_results=6
            )
        except Exception:
            pass

        characters_ref = _get_reference_content(
            references_content, ["characters", "characters_reference", "character_profiles"]
        )
        outline_ref = _get_reference_content(
            references_content, ["outline", "outline_reference", "synopsis"]
        )
        plot_timeline_ref = _get_reference_content(
            references_content, ["plot_timeline", "plot-timeline", "timeline"]
        )
        story_context_parts = [
            book_bible_content,
            vector_context,
            outline_ref,
            plot_timeline_ref
        ]
        story_context = "\n\n".join([p for p in story_context_parts if p]).strip()
        focus_characters = chapter_plan.get("focal_characters") or _extract_character_names(
            " ".join([book_bible_content, characters_ref]),
            limit=6
        )
        required_plot_points = chapter_plan.get("required_plot_points") or (
            [chapter_plan.get("summary")] if chapter_plan.get("summary") else []
        )
        if not required_plot_points:
            fallback_source = outline_ref or plot_timeline_ref or chapter_plan.get("summary", "") or book_bible_content
            required_plot_points = _extract_plot_points(fallback_source, limit=3)
        chapter_climax_goal = chapter_plan.get("ending_type") or chapter_plan.get("summary") or ""
        if not chapter_climax_goal:
            chapter_climax_goal = required_plot_points[-1] if required_plot_points else ""

        arc_diagnostics = (chapter_context.get("continuity") or {}).get("arc_diagnostics", {})
        llm_context = {
            "book_bible": book_bible_content,
            "previous_chapters_summary": chapter_context.get('previous_chapters_summary', ''),
            "references": references_content,
            "previous_opening_lines": chapter_context.get('previous_opening_lines', []),
            "previous_ending_lines": chapter_context.get('previous_ending_lines', []),
            "last_chapter_ending": chapter_context.get('last_chapter_ending', ''),
            "director_notes": chapter_context.get('director_notes', ''),
            "pattern_database_summary": pattern_summary_text,
            "repetition_risks": repetition_risks,
            "arc_diagnostics": arc_diagnostics,
            "chapter_objectives": chapter_plan.get("objectives", []),
            "chapter_plan_summary": chapter_plan.get("summary", ""),
            "required_plot_points": required_plot_points,
            "opening_type": chapter_plan.get("opening_type", ""),
            "ending_type": chapter_plan.get("ending_type", ""),
            "emotional_arc": chapter_plan.get("emotional_arc", ""),
            "focal_characters": focus_characters,
            "plan_continuity_requirements": chapter_plan.get("continuity_requirements", []),
            "vector_context": vector_context,
            "vector_guidelines": vector_guidelines,
            "genre": (project_data.get("settings", {}) or {}).get("genre", ""),
            "story_context": story_context,
            "previous_chapter_summary": chapter_context.get('previous_chapters_summary', ''),
            "character_requirements": characters_ref,
            "plot_requirements": outline_ref or plot_timeline_ref,
            "focus_characters": focus_characters,
            "chapter_climax_goal": chapter_climax_goal
        }

        if not include_full:
            llm_context = {
                **llm_context,
                "book_bible": _trim_text(llm_context.get("book_bible", ""), 800),
                "story_context": _trim_text(llm_context.get("story_context", ""), 800),
                "references": {k: _trim_text(v, 400) for k, v in references_content.items()},
                "pattern_database_summary": _trim_text(pattern_summary_text, 400),
                "vector_context": _trim_text(vector_context, 400),
                "vector_guidelines": _trim_text(vector_guidelines, 300),
                "arc_diagnostics": arc_diagnostics
            }

        return {
            "success": True,
            "project_id": project_id,
            "chapter_number": chapter_number,
            "target_word_count": target_word_count,
            "chapter_context": chapter_context,
            "chapter_plan": chapter_plan,
            "llm_context": llm_context
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to assemble context audit for {project_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to assemble context audit")

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
    background_tasks: BackgroundTasks,
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
        
        content_changed = request.content is not None
        if content_changed:
            updates['content'] = request.content
            updates['metadata.word_count'] = len(request.content.split())
            updates['metadata.updated_at'] = datetime.now(timezone.utc)
            updates['metadata.updated_by'] = user_id
        
        # Perform the update
        if db.use_firestore:
            # Use adapter so dot-notation updates are handled consistently.
            success = await db.update_chapter(chapter_id, updates, user_id, project_id)
        else:
            success = await db.update_chapter(chapter_id, updates, user_id, project_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update chapter"
            )

        if content_changed:
            # Add an explicit version entry via transactional service.
            try:
                version_data = {
                    "content": request.content,
                    "reason": "user_edit",
                    "user_id": user_id,
                    "changes_summary": "Manual content update",
                }
                await db.add_chapter_version(chapter_id, version_data, user_id, project_id)
            except Exception as version_err:
                logger.warning(f"Failed to add version for chapter {chapter_id}: {version_err}")

            try:
                vector_service = VectorStoreService()
                await vector_service.upsert_chapter(
                    project_id=project_id,
                    user_id=user_id,
                    chapter_id=chapter_id,
                    chapter_number=chapter_data.get("chapter_number", 0),
                    title=chapter_data.get("title") or f"Chapter {chapter_data.get('chapter_number', '')}",
                    content=request.content
                )
            except Exception as vector_err:
                logger.warning(f"Failed to update vector memory for chapter {chapter_id}: {vector_err}")

            # Sync to local workspace so auto-complete context reflects edits.
            try:
                _sync_chapter_to_local_workspace(project_id, int(chapter_data.get("chapter_number", 0) or 0), request.content)
            except Exception:
                pass

            background_tasks.add_task(
                apply_steering_update,
                project_id,
                user_id,
                "chapter",
                f"chapter-{chapter_data.get('chapter_number', '')}",
                request.content,
                "Manual chapter update. Align canon and references to reflect these changes.",
                "manual",
                "document"
            )
        
        return {
            'message': 'Chapter updated successfully',
            'version_created': bool(content_changed)
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
# STORY NOTES (DIRECTOR NOTES)
# =====================================================================

@router.get("/{chapter_id}/notes", response_model=dict)
async def list_chapter_notes(
    chapter_id: str,
    include_resolved: bool = Query(False, description="Include resolved notes"),
    current_user: dict = Depends(get_current_user)
):
    """List story notes for a chapter."""
    try:
        access = await _load_chapter_with_access(chapter_id, current_user)
        project_id = access['project_id']
        user_id = access['user_id']

        notes = await list_story_notes(project_id, user_id)
        chapter_notes = [
            n for n in notes
            if n.get('chapter_id') == chapter_id and (include_resolved or not n.get('resolved'))
        ]

        return {
            'success': True,
            'notes': chapter_notes,
            'total': len(chapter_notes)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list notes for chapter {chapter_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve notes"
        )

@router.post("/{chapter_id}/notes", response_model=dict)
async def add_chapter_note(
    chapter_id: str,
    request: StoryNoteRequest,
    current_user: dict = Depends(get_current_user)
):
    """Add a story note to a chapter."""
    try:
        if not request.content or not request.content.strip():
            raise HTTPException(status_code=400, detail="Note content is required")

        access = await _load_chapter_with_access(chapter_id, current_user)
        project_id = access['project_id']
        user_id = access['user_id']

        note_payload = {
            'chapter_id': chapter_id,
            'content': request.content.strip(),
            'created_by': user_id,
            'position': request.position,
            'selection_start': request.selection_start,
            'selection_end': request.selection_end,
            'selection_text': request.selection_text,
            'scope': request.scope or 'chapter',
            'apply_to_future': True if request.apply_to_future is None else request.apply_to_future,
            'intent': request.intent,
            'source': 'chapter_editor'
        }

        note_id = await create_story_note(project_id, note_payload, user_id)
        if not note_id:
            raise HTTPException(status_code=500, detail="Failed to create note")

        try:
            vector_service = VectorStoreService()
            await vector_service.upsert_story_note(
                project_id=project_id,
                user_id=user_id,
                note_id=note_id,
                content=note_payload["content"],
                scope=note_payload.get("scope", "chapter"),
                chapter_id=chapter_id,
                intent=note_payload.get("intent")
            )
        except Exception as vector_err:
            logger.warning(f"Failed to index story note {note_id}: {vector_err}")

        return {
            'success': True,
            'note_id': note_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add note for chapter {chapter_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add note"
        )

@router.put("/{chapter_id}/notes/{note_id}", response_model=dict)
async def update_chapter_note(
    chapter_id: str,
    note_id: str,
    request: UpdateStoryNoteRequest,
    current_user: dict = Depends(get_current_user)
):
    """Update a story note for a chapter."""
    try:
        access = await _load_chapter_with_access(chapter_id, current_user)
        project_id = access['project_id']
        user_id = access['user_id']

        updates = {}
        if request.content is not None:
            updates['content'] = request.content.strip()
        if request.resolved is not None:
            updates['resolved'] = request.resolved
            updates['resolved_at'] = datetime.now(timezone.utc) if request.resolved else None
        if request.apply_to_future is not None:
            updates['apply_to_future'] = request.apply_to_future
        if request.intent is not None:
            updates['intent'] = request.intent
        if request.scope is not None:
            updates['scope'] = request.scope

        success = await update_story_note(project_id, note_id, updates, user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Note not found")

        try:
            vector_service = VectorStoreService()
            if request.resolved is True:
                await vector_service.delete_story_note(project_id, user_id, note_id)
            elif request.content is not None:
                await vector_service.upsert_story_note(
                    project_id=project_id,
                    user_id=user_id,
                    note_id=note_id,
                    content=request.content.strip(),
                    scope=updates.get("scope") or "chapter",
                    chapter_id=chapter_id,
                    intent=updates.get("intent")
                )
        except Exception as vector_err:
            logger.warning(f"Failed to update vector memory for note {note_id}: {vector_err}")

        return {'success': True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update note {note_id} for chapter {chapter_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update note"
        )

@router.delete("/{chapter_id}/notes/{note_id}", response_model=dict)
async def delete_chapter_note(
    chapter_id: str,
    note_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a story note for a chapter."""
    try:
        access = await _load_chapter_with_access(chapter_id, current_user)
        project_id = access['project_id']
        user_id = access['user_id']

        success = await delete_story_note(project_id, note_id, user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Note not found")

        try:
            vector_service = VectorStoreService()
            await vector_service.delete_story_note(project_id, user_id, note_id)
        except Exception as vector_err:
            logger.warning(f"Failed to delete note {note_id} from vector memory: {vector_err}")

        return {'success': True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete note {note_id} for chapter {chapter_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete note"
        )

# =====================================================================
# REWRITE SELECTED SECTION
# =====================================================================

@router.post("/{chapter_id}/rewrite-section", response_model=dict)
async def rewrite_chapter_section(
    chapter_id: str,
    request: RewriteSectionRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Rewrite a selected section in a chapter using AI."""
    try:
        if request.selection_start < 0 or request.selection_end <= request.selection_start:
            raise HTTPException(status_code=400, detail="Invalid selection range")
        if not request.instruction or not request.instruction.strip():
            raise HTTPException(status_code=400, detail="Rewrite instruction is required")

        access = await _load_chapter_with_access(chapter_id, current_user)
        chapter_data = access['chapter']
        project_id = access['project_id']
        user_id = access['user_id']

        original_content = chapter_data.get('content') or ""
        if request.selection_end > len(original_content):
            raise HTTPException(status_code=400, detail="Selection range is out of bounds")

        selected_text = original_content[request.selection_start:request.selection_end]

        # Load book bible and references
        project_data = access['project']
        book_bible_content = ""
        if 'book_bible' in project_data:
            bb_entry = project_data['book_bible']
            if isinstance(bb_entry, dict):
                book_bible_content = bb_entry.get('content', '')
            elif isinstance(bb_entry, str):
                book_bible_content = bb_entry

        references_content: dict[str, str] = {}
        try:
            reference_docs = await get_project_reference_files(project_id)
            for ref in reference_docs:
                fname = ref.get('filename', 'unnamed.md')
                references_content[fname] = ref.get('content', '')
        except Exception:
            pass

        # Include active story notes for continuity
        notes = await list_story_notes(project_id, user_id)
        usable_notes = [
            n for n in notes
            if not n.get('resolved') and n.get('apply_to_future') is not False
        ]
        note_lines = []
        for note in usable_notes[:8]:
            content = (note.get('content') or '').strip()
            if content:
                note_lines.append(content[:240])

        vector_context = ""
        vector_guidelines = ""
        try:
            vector_context = await _build_vector_prompt_context(
                project_id=project_id,
                user_id=user_id,
                query=f"Rewrite guidance for chapter {chapter_data.get('chapter_number', '')}. Maintain continuity with book bible, character details, and recent chapters.",
                max_results=8
            )
            vector_guidelines = await _build_vector_prompt_context(
                project_id=project_id,
                user_id=user_id,
                query="Style guide and writing rules for this project.",
                max_results=4
            )
        except Exception as vector_err:
            logger.warning(f"Vector memory retrieval failed for rewrite: {vector_err}")

        surrounding_before = original_content[max(0, request.selection_start - 500):request.selection_start]
        surrounding_after = original_content[request.selection_end:request.selection_end + 500]

        llm_context = {
            "book_bible": book_bible_content,
            "references": references_content,
            "director_notes": "\n".join(note_lines),
            "vector_context": vector_context,
            "vector_guidelines": vector_guidelines,
            "vector_store_ids": [],
            "use_file_search": True,
            "chapter_number": chapter_data.get("chapter_number", 0),
            "surrounding_before": surrounding_before,
            "surrounding_after": surrounding_after,
        }

        try:
            vector_service = VectorStoreService()
            project_store_id = (project_data.get("memory", {}) or {}).get("project_vector_store_id")
            if project_store_id:
                llm_context["vector_store_ids"].append(project_store_id)
            user_store_id = (project_data.get("memory", {}) or {}).get("user_vector_store_id")
            if user_store_id:
                llm_context["vector_store_ids"].append(user_store_id)
        except Exception as vector_err:
            logger.warning(f"Vector store id lookup failed for rewrite: {vector_err}")

        if llm_context["vector_store_ids"] and os.getenv("ENABLE_OPENAI_FILE_SEARCH", "true").lower() == "true":
            llm_context["vector_context"] = ""

        from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig
        credits_enabled = os.getenv('ENABLE_CREDITS_SYSTEM', 'false').lower() == 'true'
        enable_billing = os.getenv('ENABLE_CREDITS_BILLING', 'false').lower() == 'true' and credits_enabled
        orchestrator = LLMOrchestrator(
            retry_config=RetryConfig(max_retries=2),
            user_id=user_id,
            enable_billing=enable_billing
        )

        result = await orchestrator.rewrite_section(
            selected_text=selected_text,
            instruction=request.instruction.strip(),
            context=llm_context
        )

        if not result.success:
            raise HTTPException(status_code=500, detail=result.error or "Rewrite failed")

        rewritten_segment = result.content.strip()
        updated_content = (
            original_content[:request.selection_start]
            + rewritten_segment
            + original_content[request.selection_end:]
        )

        # Preview mode: return proposed content without persisting
        if request.preview:
            return {
                'success': True,
                'content': updated_content,
                'proposed_content': updated_content,
                'proposed_selection': rewritten_segment,
                'original_selection': selected_text,
                'rewritten_section': rewritten_segment,
                'preview': True
            }

        # Persist updated chapter and new version
        await _persist_rewrite(
            chapter_id=chapter_id,
            chapter_data=chapter_data,
            project_id=project_id,
            user_id=user_id,
            updated_content=updated_content,
            instruction=request.instruction.strip(),
            book_bible_content=book_bible_content,
            references_content=references_content,
            llm_context=llm_context,
            background_tasks=background_tasks,
        )

        return {
            'success': True,
            'content': updated_content,
            'rewritten_section': rewritten_segment,
            'preview': False
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to rewrite section for chapter {chapter_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to rewrite selected section"
        )

async def _persist_rewrite(
    *,
    chapter_id: str,
    chapter_data: dict,
    project_id: str,
    user_id: str,
    updated_content: str,
    instruction: str,
    book_bible_content: str,
    references_content: dict,
    llm_context: dict,
    background_tasks: BackgroundTasks,
) -> None:
    """Shared persistence logic for rewrite (used by both rewrite-section and confirm-rewrite)."""
    db = get_database_adapter()
    updates = {
        'content': updated_content,
        'metadata.word_count': len(updated_content.split()),
        'metadata.updated_at': datetime.now(timezone.utc),
        'metadata.updated_by': user_id
    }
    await db.update_chapter(chapter_id, updates, user_id, project_id)

    version_data = {
        'content': updated_content,
        'reason': 'note_rewrite',
        'user_id': user_id,
        'changes_summary': instruction[:200] if instruction else 'AI rewrite applied'
    }
    await db.add_chapter_version(chapter_id, version_data, user_id, project_id)

    try:
        vector_service = VectorStoreService()
        await vector_service.upsert_chapter(
            project_id=project_id,
            user_id=user_id,
            chapter_id=chapter_id,
            chapter_number=chapter_data.get("chapter_number", 0),
            title=chapter_data.get("title") or f"Chapter {chapter_data.get('chapter_number', '')}",
            content=updated_content
        )
    except Exception as vector_err:
        logger.warning(f"Failed to update vector memory after rewrite for chapter {chapter_id}: {vector_err}")

    background_tasks.add_task(
        apply_steering_update,
        project_id,
        user_id,
        "chapter",
        f"chapter-{chapter_data.get('chapter_number', '')}",
        updated_content,
        instruction,
        "ai",
        "document"
    )

    try:
        chapter_num = int(chapter_data.get("chapter_number", 0) or 0)
        pov_context = {
            "pov_character": llm_context.get("pov_character", ""),
            "pov_type": llm_context.get("pov_type", ""),
            "pov_notes": llm_context.get("pov_notes", ""),
        }
        background_tasks.add_task(
            _rebuild_chapter_artifacts,
            project_id=project_id,
            user_id=user_id,
            chapter_number=chapter_num,
            chapter_content=updated_content,
            book_bible_content=book_bible_content,
            references_content=references_content,
            vector_store_ids=llm_context.get("vector_store_ids", []),
            pov_context=pov_context,
        )
    except Exception:
        pass


@router.post("/{chapter_id}/confirm-rewrite", response_model=dict)
async def confirm_chapter_rewrite(
    chapter_id: str,
    request: ConfirmRewriteRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Persist a previously previewed rewrite without re-running the LLM."""
    try:
        if not request.proposed_content or not request.proposed_content.strip():
            raise HTTPException(status_code=400, detail="Proposed content is required")

        access = await _load_chapter_with_access(chapter_id, current_user)
        chapter_data = access['chapter']
        project_id = access['project_id']
        user_id = access['user_id']

        project_data = access['project']
        book_bible_content = ""
        if 'book_bible' in project_data:
            bb_entry = project_data['book_bible']
            if isinstance(bb_entry, dict):
                book_bible_content = bb_entry.get('content', '')
            elif isinstance(bb_entry, str):
                book_bible_content = bb_entry

        references_content: dict[str, str] = {}
        try:
            reference_docs = await get_project_reference_files(project_id)
            for ref in reference_docs:
                fname = ref.get('filename', 'unnamed.md')
                references_content[fname] = ref.get('content', '')
        except Exception:
            pass

        llm_context: dict = {
            "vector_store_ids": [],
        }
        try:
            project_store_id = (project_data.get("memory", {}) or {}).get("project_vector_store_id")
            if project_store_id:
                llm_context["vector_store_ids"].append(project_store_id)
            user_store_id = (project_data.get("memory", {}) or {}).get("user_vector_store_id")
            if user_store_id:
                llm_context["vector_store_ids"].append(user_store_id)
        except Exception:
            pass

        await _persist_rewrite(
            chapter_id=chapter_id,
            chapter_data=chapter_data,
            project_id=project_id,
            user_id=user_id,
            updated_content=request.proposed_content,
            instruction=request.instruction,
            book_bible_content=book_bible_content,
            references_content=references_content,
            llm_context=llm_context,
            background_tasks=background_tasks,
        )

        return {
            'success': True,
            'content': request.proposed_content,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to confirm rewrite for chapter {chapter_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to confirm rewrite"
        )


# =====================================================================
# RIPPLE ANALYSIS & PROPAGATION
# =====================================================================

@router.post("/{chapter_id}/ripple-analysis", response_model=dict)
async def ripple_analysis(
    chapter_id: str,
    request: RippleAnalysisRequest,
    current_user: dict = Depends(get_current_user)
):
    """Analyze which downstream chapters may be affected by an edit to this chapter."""
    try:
        access = await _load_chapter_with_access(chapter_id, current_user)
        chapter_data = access['chapter']
        project_id = access['project_id']
        user_id = access['user_id']
        project_data = access['project']

        source_chapter_number = request.chapter_number or chapter_data.get("chapter_number", 0)

        db = get_database_adapter()
        all_chapters = []
        if db.use_firestore:
            all_chapters = await db.firestore.list_project_chapters(project_id, user_id=user_id)
        downstream = [
            ch for ch in all_chapters
            if int(ch.get("chapter_number", 0)) > source_chapter_number
            and ch.get("content")
        ]

        if not downstream:
            return {"affected_chapters": [], "source_chapter": source_chapter_number}

        book_bible_content = ""
        if 'book_bible' in project_data:
            bb_entry = project_data['book_bible']
            if isinstance(bb_entry, dict):
                book_bible_content = bb_entry.get('content', '')
            elif isinstance(bb_entry, str):
                book_bible_content = bb_entry

        references_content: dict[str, str] = {}
        try:
            reference_docs = await get_project_reference_files(project_id)
            for ref in reference_docs:
                fname = ref.get('filename', 'unnamed.md')
                references_content[fname] = ref.get('content', '')
        except Exception:
            pass

        canon_log = references_content.get("canon-log.md", "")

        from backend.services.consistency_check_service import check_chapter_consistency

        affected = []
        for ch in downstream[:10]:
            ch_num = int(ch.get("chapter_number", 0))
            ch_content = ch.get("content", "")
            if not ch_content:
                continue
            try:
                result = await check_chapter_consistency(
                    chapter_number=ch_num,
                    chapter_content=ch_content,
                    book_bible=book_bible_content,
                    references=references_content,
                    canon_log=canon_log,
                    user_id=user_id,
                )
                severity = result.get("severity", "low")
                issues = result.get("issues", [])
                if severity != "low" or issues:
                    affected.append({
                        "chapter_number": ch_num,
                        "chapter_id": ch.get("id") or ch.get("chapter_id", ""),
                        "severity": severity,
                        "issues": issues,
                        "suggested_fix": result.get("rewrite_instruction", ""),
                    })
            except Exception as check_err:
                logger.warning(f"Consistency check failed for chapter {ch_num}: {check_err}")

        affected.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x["severity"], 3))

        return {
            "affected_chapters": affected,
            "source_chapter": source_chapter_number,
            "total_checked": len(downstream[:10]),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ripple analysis failed for chapter {chapter_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to run ripple analysis"
        )


@router.post("/propagate-edits", response_model=dict)
async def propagate_edits(
    request: PropagateEditsRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """Queue canon-aligned rewrites for selected downstream chapters."""
    try:
        user_id = current_user.get('user_id')
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user authentication")
        if not request.chapter_ids:
            raise HTTPException(status_code=400, detail="No chapter IDs provided")

        from backend.services.steering_service import rewrite_chapter_for_canon

        queued = []
        for cid in request.chapter_ids[:10]:
            try:
                access = await _load_chapter_with_access(cid, current_user)
                project_id = access['project_id']
                instruction = (
                    request.edit_summary
                    or f"Align with changes made in chapter {request.source_chapter_number}."
                )
                background_tasks.add_task(
                    rewrite_chapter_for_canon,
                    project_id=project_id,
                    user_id=user_id,
                    chapter_id=cid,
                    instructions=instruction,
                    source_label=f"Chapter {request.source_chapter_number} edit",
                    source_type="chapter",
                    source_content=request.edit_summary or "",
                )
                queued.append(cid)
            except Exception as cid_err:
                logger.warning(f"Could not queue propagation for chapter {cid}: {cid_err}")

        return {
            "success": True,
            "queued_chapters": queued,
            "total_queued": len(queued),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Propagate edits failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to propagate edits"
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


@router.post("/{chapter_id}/rebuild-artifacts", response_model=dict)
async def rebuild_chapter_artifacts(
    chapter_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """
    Rebuild coherence artifacts (canon-log + chapter-ledger) from the current chapter content.
    Intended for post-edit stabilization (manual edits and post-auto-complete editing).
    """
    access = await _load_chapter_with_access(chapter_id, current_user)
    chapter_data = access["chapter"]
    project_data = access["project"]
    project_id = access["project_id"]
    user_id = access["user_id"]

    chapter_number = int(chapter_data.get("chapter_number", 0) or 0)
    if chapter_number <= 0:
        raise HTTPException(status_code=400, detail="Invalid chapter_number for rebuild")

    # Load book bible and references
    book_bible_content = ""
    bb_entry = project_data.get("book_bible", {})
    if isinstance(bb_entry, dict):
        book_bible_content = bb_entry.get("content", "") or ""
    elif isinstance(bb_entry, str):
        book_bible_content = bb_entry

    references_content: dict[str, str] = {}
    try:
        reference_docs = await get_project_reference_files(project_id)
        for ref in reference_docs or []:
            if not isinstance(ref, dict):
                continue
            fname = ref.get("filename") or "unnamed.md"
            references_content[str(fname)] = ref.get("content", "") or ""
    except Exception:
        references_content = {}

    # Vector store ids if present on project memory
    vector_store_ids: list[str] = []
    try:
        memory = project_data.get("memory", {}) if isinstance(project_data.get("memory"), dict) else {}
        for key in ("project_vector_store_id", "user_vector_store_id"):
            val = memory.get(key)
            if val and val not in vector_store_ids:
                vector_store_ids.append(val)
    except Exception:
        vector_store_ids = []

    background_tasks.add_task(
        _rebuild_chapter_artifacts,
        project_id=project_id,
        user_id=user_id,
        chapter_number=chapter_number,
        chapter_content=str(chapter_data.get("content") or ""),
        book_bible_content=book_bible_content,
        references_content=references_content,
        vector_store_ids=vector_store_ids,
        pov_context=None,
    )

    return {"success": True, "scheduled": True}

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
            chapter_data = None
            if owner_id:
                chapter_data = await db.firestore.get_user_project_chapter_by_number(owner_id, project_id, chapter_number)
            if not chapter_data:
                # Backwards-compatible fallback (should be rare after migration):
                chapters = await db.firestore.get_project_chapters(project_id)
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
            chapter_data = None
            chapter_id = None
            if owner_id:
                chapter_data = await db.firestore.get_user_project_chapter_by_number(owner_id, project_id, chapter_number)
                chapter_id = chapter_data.get('id') if chapter_data else None
            if not chapter_data:
                chapters = await db.firestore.get_project_chapters(project_id)
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
        
        # Update chapter content using dot-notation to avoid overwriting metadata object.
        update_data = {}
        if request.content is not None:
            update_data["content"] = request.content
            update_data["metadata.updated_at"] = datetime.now(timezone.utc)
            update_data["metadata.updated_by"] = user_id
            update_data["metadata.word_count"] = len(request.content.split()) if request.content else 0
        if request.title is not None:
            update_data["title"] = request.title
        if request.stage is not None:
            update_data["metadata.stage"] = request.stage.value
        if request.quality_scores is not None:
            update_data["quality_scores"] = request.quality_scores.dict()

        await db.update_chapter(chapter_id, update_data, user_id, project_id)

        # Create a new version when content changes.
        if request.content is not None:
            try:
                version_data = {
                    "content": request.content,
                    "reason": "user_edit",
                    "user_id": user_id,
                    "changes_summary": "Manual content update (by number)",
                }
                await db.add_chapter_version(chapter_id, version_data, user_id, project_id)
            except Exception as version_err:
                logger.warning(f"Failed to add version for chapter {chapter_number}: {version_err}")
        
        logger.info(f"Updated chapter {chapter_number} in project {project_id}")

        if request.content:
            try:
                vector_service = VectorStoreService()
                await vector_service.upsert_chapter(
                    project_id=project_id,
                    user_id=user_id,
                    chapter_id=chapter_id,
                    chapter_number=chapter_number,
                    title=chapter_data.get("title") or f"Chapter {chapter_number}",
                    content=request.content
                )
            except Exception as vector_err:
                logger.warning(f"Failed to update vector memory for chapter {chapter_number}: {vector_err}")

            try:
                _sync_chapter_to_local_workspace(project_id, chapter_number, request.content)
            except Exception:
                pass
        
        return {
            "success": True,
            "message": f"Chapter {chapter_number} updated successfully",
            "chapter_number": chapter_number,
            "project_id": project_id,
            "word_count": int(update_data.get("metadata.word_count", 0) or 0)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update chapter {chapter_number} for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update chapter"
        ) 