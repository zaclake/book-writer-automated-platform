#!/usr/bin/env python3
"""
Audiobook API v2 - Audiobook Generation Endpoints

Handles audiobook generation using ElevenLabs Text-to-Speech.
Provides voice listing, cost estimation, preview, generation, and status polling.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from backend.models.firestore_models import (
    AudiobookConfig, PronunciationEntry
)
from backend.auto_complete import BackgroundJobProcessor, JobStatus, JobInfo

try:
    from backend.database_integration import get_project, get_project_chapters
    from backend.auth_middleware import get_current_user
    from backend.services.firestore_service import get_firestore_client
except Exception:
    from database_integration import get_project, get_project_chapters
    from auth_middleware import get_current_user
    from services.firestore_service import get_firestore_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v2/audiobook", tags=["audiobook-v2"])

job_processor: Optional[BackgroundJobProcessor] = None


def get_job_processor() -> BackgroundJobProcessor:
    global job_processor
    if job_processor is None:
        job_processor = BackgroundJobProcessor()
    return job_processor


def _verify_project_access(project_data: dict, user_id: str):
    """Raise 403 if user doesn't own or collaborate on the project."""
    owner_id = project_data.get("metadata", {}).get("owner_id")
    collaborators = project_data.get("metadata", {}).get("collaborators", [])
    if owner_id != user_id and user_id not in collaborators:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this project",
        )


# ── Request models ──────────────────────────────────────────────────

class PreviewRequest(BaseModel):
    voice_id: str = Field(..., description="ElevenLabs voice ID")
    model_id: str = Field(default="eleven_multilingual_v2")
    chapter_number: Optional[int] = Field(None, description="Chapter to preview (default: first)")
    pronunciation_glossary: List[Dict[str, str]] = Field(default_factory=list)


class AbbreviationScanRequest(BaseModel):
    pass  # no body needed; reads chapters from project


# ── Endpoints ───────────────────────────────────────────────────────

@router.get("/voices", response_model=List[Dict[str, Any]])
async def list_voices(current_user: dict = Depends(get_current_user)):
    """Return curated narrator voice list."""
    from backend.services.audiobook_service import AudiobookService

    service = AudiobookService()
    return service.get_voices()


@router.get("/estimate/{project_id}", response_model=Dict[str, Any])
async def estimate_audiobook_cost(
    project_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Return character count and cost estimate for a project."""
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth")

    project_data = await get_project(project_id)
    if not project_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    _verify_project_access(project_data, user_id)

    chapters_raw = await get_project_chapters(project_id)
    if not chapters_raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project has no chapters",
        )

    chapters = _normalize_chapters(chapters_raw)

    # Load saved glossary if any
    glossary = _load_glossary(project_id)

    from backend.services.audiobook_service import AudiobookService

    service = AudiobookService()
    return service.estimate_cost(chapters, glossary)


@router.post("/preview/{project_id}")
async def generate_voice_preview(
    project_id: str,
    req: PreviewRequest,
    current_user: dict = Depends(get_current_user),
):
    """Generate a short audio preview for a voice."""
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth")

    project_data = await get_project(project_id)
    if not project_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    _verify_project_access(project_data, user_id)

    chapters_raw = await get_project_chapters(project_id)
    if not chapters_raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No chapters")

    chapters = _normalize_chapters(chapters_raw)

    # Pick the requested chapter or the first one
    target_chapter = None
    if req.chapter_number:
        target_chapter = next(
            (c for c in chapters if c["chapter_number"] == req.chapter_number), None
        )
    if not target_chapter:
        target_chapter = chapters[0]

    from backend.services.audiobook_service import AudiobookService

    service = AudiobookService(user_id=user_id)
    if not service.is_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Audiobook service not available",
        )

    try:
        audio_bytes = await service.generate_preview(
            text=target_chapter.get("content", ""),
            voice_id=req.voice_id,
            model_id=req.model_id,
            glossary=req.pronunciation_glossary or None,
            chapter_number=target_chapter.get("chapter_number", 1),
            chapter_title=target_chapter.get("title", ""),
        )
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception as e:
        logger.error(f"Preview generation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Preview generation failed: {str(e)}",
        )


@router.post("/abbreviations/{project_id}", response_model=List[Dict[str, Any]])
async def scan_abbreviations(
    project_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Scan project chapters for abbreviations and suggest pronunciations."""
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth")

    project_data = await get_project(project_id)
    if not project_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    _verify_project_access(project_data, user_id)

    chapters_raw = await get_project_chapters(project_id)
    if not chapters_raw:
        return []

    chapters = _normalize_chapters(chapters_raw)
    chapter_texts = [c.get("content", "") for c in chapters]

    from backend.services.audiobook_text_prep import detect_abbreviations

    return detect_abbreviations(chapter_texts)


@router.post("/project/{project_id}", response_model=Dict[str, str])
async def start_audiobook_job(
    project_id: str,
    config: AudiobookConfig,
    current_user: dict = Depends(get_current_user),
):
    """Start audiobook generation for a project."""
    audiobook_job_id = None
    try:
        user_id = current_user.get("user_id")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth")

        project_data = await get_project(project_id)
        if not project_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        _verify_project_access(project_data, user_id)

        chapters_raw = await get_project_chapters(project_id)
        if not chapters_raw:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No chapters")

        chapters = _normalize_chapters(chapters_raw)

        # Save glossary to project for future sessions
        if config.pronunciation_glossary:
            _save_glossary(project_id, config.pronunciation_glossary)

        # Create Firestore job doc
        audiobook_job_id = f"audiobook_{project_id}_{int(datetime.now(timezone.utc).timestamp())}"
        now = datetime.now(timezone.utc).isoformat()
        try:
            db = get_firestore_client()
            db.collection("audiobook_jobs").document(audiobook_job_id).set({
                "job_id": audiobook_job_id,
                "project_id": project_id,
                "user_id": user_id,
                "status": "pending",
                "config": config.dict(),
                "progress": {
                    "current_step": "Initializing",
                    "current_chapter": 0,
                    "total_chapters": len(chapters),
                    "progress_percentage": 0.0,
                    "last_update": now,
                },
                "created_at": now,
                "started_at": None,
                "completed_at": None,
            })
        except Exception as e:
            logger.warning(f"Failed to create audiobook job doc: {e}")

        # Background job
        processor = get_job_processor()

        async def audiobook_job_func():
            from backend.services.audiobook_service import AudiobookService

            api_key = config.elevenlabs_api_key or None
            service = AudiobookService(user_id=user_id, elevenlabs_api_key=api_key)
            if not service.is_available():
                raise RuntimeError("Audiobook service not available")

            _started_at_written = False

            async def _progress(step: str, current_ch: int, total_ch: int, pct: float):
                nonlocal _started_at_written
                try:
                    if step == "generating":
                        step_text = f"Generating chapter {current_ch} of {total_ch}"
                    elif step == "concatenating":
                        step_text = "Concatenating audio..."
                    elif step == "uploading":
                        step_text = "Uploading files..."
                    else:
                        step_text = step.replace("_", " ").capitalize()

                    update: Dict[str, Any] = {
                        "status": step,
                        "progress": {
                            "current_step": step_text,
                            "current_chapter": current_ch,
                            "total_chapters": total_ch,
                            "progress_percentage": round(pct, 1),
                            "last_update": datetime.now(timezone.utc).isoformat(),
                        },
                    }
                    if not _started_at_written:
                        update["started_at"] = datetime.now(timezone.utc).isoformat()
                        _started_at_written = True

                    db = get_firestore_client()
                    db.collection("audiobook_jobs").document(audiobook_job_id).set(
                        update, merge=True
                    )
                except Exception as pe:
                    logger.warning(f"Progress update failed: {pe}")

            config_dict = config.dict()
            config_dict["job_id"] = audiobook_job_id
            glossary_dicts = [
                {"abbreviation": e.abbreviation, "spoken_form": e.spoken_form}
                for e in (config.pronunciation_glossary or [])
            ]
            config_dict["pronunciation_glossary"] = glossary_dicts

            try:
                result = await service.generate_audiobook(
                    project_id=project_id,
                    chapters=chapters,
                    config=config_dict,
                    progress_callback=_progress,
                )
            except Exception as gen_err:
                # Persist failure to audiobook_jobs so polling sees it
                try:
                    db = get_firestore_client()
                    db.collection("audiobook_jobs").document(audiobook_job_id).set({
                        "status": "failed",
                        "error_message": str(gen_err),
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "progress": {
                            "current_step": "Failed",
                            "progress_percentage": 0.0,
                            "last_update": datetime.now(timezone.utc).isoformat(),
                        },
                    }, merge=True)
                except Exception:
                    pass
                raise

            # Persist completed result
            try:
                db = get_firestore_client()
                db.collection("audiobook_jobs").document(audiobook_job_id).set({
                    "status": "completed",
                    "progress": {
                        "current_step": "Completed",
                        "current_chapter": len(chapters),
                        "total_chapters": len(chapters),
                        "progress_percentage": 100.0,
                        "last_update": datetime.now(timezone.utc).isoformat(),
                    },
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "result": {
                        "chapter_urls": {str(k): v for k, v in (result.get("chapter_urls") or {}).items()},
                        "full_book_url": result.get("full_book_url"),
                        "file_sizes": result.get("file_sizes"),
                        "total_characters": result.get("total_characters"),
                        "total_duration_seconds": result.get("total_duration_seconds"),
                        "credits_charged": result.get("credits_charged"),
                        "cost_usd": result.get("cost_usd"),
                    },
                }, merge=True)
            except Exception as pe:
                logger.error(f"Failed to persist audiobook result: {pe}")

            return {
                "status": "completed",
                "result": result,
                "job_id": audiobook_job_id,
            }

        await processor.submit_job(audiobook_job_id, audiobook_job_func)

        logger.info(f"Audiobook job {audiobook_job_id} submitted for {project_id}")
        return {
            "job_id": audiobook_job_id,
            "status": "submitted",
            "message": f"Audiobook generation started for {len(chapters)} chapters",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start audiobook job: {e}")
        if audiobook_job_id:
            try:
                db = get_firestore_client()
                db.collection("audiobook_jobs").document(audiobook_job_id).set({
                    "status": "failed",
                    "error_message": str(e),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }, merge=True)
            except Exception:
                pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start audiobook job: {str(e)}",
        )


@router.get("/{job_id}", response_model=Dict[str, Any])
async def get_audiobook_job_status(
    job_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Poll audiobook job status."""
    try:
        user_id = current_user.get("user_id")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth")

        # Read from Firestore (source of truth)
        try:
            db = get_firestore_client()
            doc = db.collection("audiobook_jobs").document(job_id).get()
            if doc.exists:
                data = doc.to_dict() or {}

                # Verify the requesting user owns this job
                job_owner = data.get("user_id")
                if job_owner and job_owner != user_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access denied to this job",
                    )

                progress = data.get("progress", {}) or {}
                result = data.get("result", {}) or {}

                response_data = {
                    "job_id": job_id,
                    "status": data.get("status", "pending"),
                    "progress": {
                        "current_step": progress.get("current_step", ""),
                        "current_chapter": progress.get("current_chapter", 0),
                        "total_chapters": progress.get("total_chapters", 0),
                        "progress_percentage": progress.get("progress_percentage", 0),
                    },
                    "result": result,
                    "created_at": data.get("created_at"),
                    "started_at": data.get("started_at"),
                    "completed_at": data.get("completed_at"),
                }

                error_msg = result.get("error_message") or data.get("error_message")
                if error_msg and data.get("status") == "failed":
                    response_data["error"] = error_msg

                return response_data
        except Exception as e:
            logger.warning(f"Audiobook job Firestore read failed: {e}")

        # Fallback to in-memory processor.
        # Verify ownership by extracting project_id from the job_id
        # (format: audiobook_{project_id}_{timestamp}).
        processor = get_job_processor()
        job = processor.get_job_status(job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

        parts = job_id.split("_", 2)
        if len(parts) >= 3:
            embedded_project_id = parts[1]
            try:
                project_data = await get_project(embedded_project_id)
                if project_data:
                    _verify_project_access(project_data, user_id)
            except HTTPException:
                raise
            except Exception:
                pass

        response = {
            "job_id": job.job_id,
            "status": job.status.value,
            "progress": job.progress or {},
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }
        if job.status == JobStatus.COMPLETED and job.result:
            response["result"] = job.result
        if job.status == JobStatus.FAILED and job.error_message:
            response["error"] = job.error_message
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get audiobook job status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get job status: {str(e)}",
        )


# ── Helpers ─────────────────────────────────────────────────────────

def _normalize_chapters(chapters_raw) -> List[Dict[str, Any]]:
    """Convert raw chapter data to a simple list of dicts sorted by chapter_number."""
    chapters = []
    for ch in chapters_raw:
        if isinstance(ch, dict):
            data = ch
        elif hasattr(ch, "to_dict"):
            data = ch.to_dict()
        else:
            data = dict(ch)

        # Resolve content: prefer latest version
        content = data.get("content", "")
        versions = data.get("versions", [])
        if versions and isinstance(versions, list):
            latest = sorted(versions, key=lambda v: v.get("version_number", 0), reverse=True)
            if latest and latest[0].get("content"):
                content = latest[0]["content"]

        chapters.append({
            "chapter_number": data.get("chapter_number", 0),
            "title": data.get("title", ""),
            "content": content,
        })

    chapters.sort(key=lambda c: c["chapter_number"])
    return chapters


def _load_glossary(project_id: str) -> Optional[List[Dict[str, str]]]:
    """Load saved pronunciation glossary from project document."""
    try:
        db = get_firestore_client()
        doc = db.collection("projects").document(project_id).get()
        if doc.exists:
            settings = (doc.to_dict() or {}).get("audiobook_settings", {})
            return settings.get("pronunciation_glossary")
    except Exception as e:
        logger.warning(f"Failed to load glossary: {e}")
    return None


def _save_glossary(project_id: str, glossary: List[PronunciationEntry]):
    """Persist pronunciation glossary to project document."""
    try:
        db = get_firestore_client()
        db.collection("projects").document(project_id).set({
            "audiobook_settings": {
                "pronunciation_glossary": [
                    {"abbreviation": e.abbreviation, "spoken_form": e.spoken_form}
                    for e in glossary
                ],
            },
        }, merge=True)
    except Exception as e:
        logger.warning(f"Failed to save glossary: {e}")
