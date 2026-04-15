#!/usr/bin/env python3
"""
Steering Service
Apply user-driven canon updates across references/book bible and record canon logs.
"""

import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from backend.database_integration import (
        get_database_adapter,
        get_project,
        get_project_reference_files,
        update_reference_file,
        create_story_note,
        update_chapter,
        add_chapter_version,
        list_story_notes,
        get_project_chapters
    )
    from backend.services.vector_store_service import VectorStoreService
    from backend.utils.reference_content_generator import ReferenceContentGenerator
    from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig
except Exception:
    from database_integration import (
        get_database_adapter,
        get_project,
        get_project_reference_files,
        update_reference_file,
        create_story_note,
        update_chapter,
        add_chapter_version,
        list_story_notes,
        get_project_chapters
    )
    from services.vector_store_service import VectorStoreService
    from utils.reference_content_generator import ReferenceContentGenerator
    from auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig

logger = logging.getLogger(__name__)


def _normalize_reference_filename(filename: str) -> str:
    return filename if filename.endswith(".md") else f"{filename}.md"


def _reference_type_from_filename(filename: str) -> str:
    return filename.replace(".md", "").strip()


async def _record_canon_log(
    project_id: str,
    user_id: str,
    source_type: str,
    source_label: str,
    instructions: str,
    mode: str,
    scope: str,
    status: str,
    metadata: Optional[Dict[str, Any]] = None,
    applied_targets: Optional[List[str]] = None
) -> Optional[str]:
    entry_id = str(uuid.uuid4())
    payload = {
        "id": entry_id,
        "project_id": project_id,
        "user_id": user_id,
        "source_type": source_type,
        "source_label": source_label,
        "instructions": instructions,
        "mode": mode,
        "scope": scope,
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "metadata": metadata or {},
        "applied_targets": applied_targets or []
    }

    try:
        db = get_database_adapter()
        if not getattr(db, "use_firestore", False):
            return entry_id
        firestore_client = getattr(getattr(db, "firestore", None), "db", None)
        if firestore_client is None:
            return entry_id
        firestore_client.collection("projects").document(project_id)\
            .collection("canon_logs").document(entry_id).set(payload, merge=True)
        return entry_id
    except Exception as exc:
        logger.warning(f"Failed to record canon log for project {project_id}: {exc}")
        return entry_id


async def create_canon_log_entry(
    project_id: str,
    user_id: str,
    source_type: str,
    source_label: str,
    instructions: str,
    mode: str,
    scope: str,
    status: str,
    metadata: Optional[Dict[str, Any]] = None,
    applied_targets: Optional[List[str]] = None
) -> Optional[str]:
    return await _record_canon_log(
        project_id=project_id,
        user_id=user_id,
        source_type=source_type,
        source_label=source_label,
        instructions=instructions,
        mode=mode,
        scope=scope,
        status=status,
        metadata=metadata,
        applied_targets=applied_targets
    )


async def _update_canon_log(
    project_id: str,
    entry_id: Optional[str],
    updates: Dict[str, Any]
) -> None:
    if not entry_id:
        return
    try:
        db = get_database_adapter()
        if not getattr(db, "use_firestore", False):
            return
        firestore_client = getattr(getattr(db, "firestore", None), "db", None)
        if firestore_client is None:
            return
        firestore_client.collection("projects").document(project_id)\
            .collection("canon_logs").document(entry_id).update(updates)
    except Exception as exc:
        logger.warning(f"Failed to update canon log {entry_id}: {exc}")


async def _update_book_bible_content(
    project_id: str,
    user_id: str,
    content: str
) -> bool:
    try:
        db = get_database_adapter()
        if not getattr(db, "use_firestore", False) or not getattr(db, "firestore", None):
            logger.warning("Book bible update skipped; Firestore not available")
            return False
        updates = {
            "book_bible.content": content,
            "book_bible.last_modified": datetime.now(timezone.utc),
            "book_bible.modified_by": user_id,
            "book_bible.word_count": len(content.split())
        }
        success = await db.firestore.update_project(project_id, updates)
        if success:
            try:
                vector_service = VectorStoreService()
                await vector_service.upsert_book_bible(project_id, user_id, content)
            except Exception as vector_err:
                logger.warning(f"Vector memory update failed for book bible {project_id}: {vector_err}")
        return success
    except Exception as exc:
        logger.warning(f"Failed to update book bible for {project_id}: {exc}")
        return False


def _build_steering_instruction(instructions: str, source_label: str, source_type: str, source_content: str) -> str:
    base_instruction = instructions.strip() if instructions else (
        "Align this document with the updated canonical source below. "
        "Preserve relevant facts unless they conflict with the canonical update."
    )
    return (
        f"{base_instruction}\n\n"
        f"CANONICAL SOURCE ({source_type} - {source_label}):\n"
        f"{source_content}\n"
    )


async def apply_steering_update(
    project_id: str,
    user_id: str,
    source_type: str,
    source_label: str,
    source_content: str,
    instructions: str = "",
    mode: str = "manual",
    scope: str = "document"
) -> None:
    source_excerpt = (source_content or "").strip()[:800]
    entry_id = await _record_canon_log(
        project_id=project_id,
        user_id=user_id,
        source_type=source_type,
        source_label=source_label,
        instructions=instructions,
        mode=mode,
        scope=scope,
        status="running",
        metadata={
            "source_length": len(source_content or ""),
            "source_excerpt": source_excerpt
        }
    )

    try:
        from backend.services.canon_log_service import append_manual_canon_update
        await append_manual_canon_update(
            project_id=project_id,
            user_id=user_id,
            source_type=source_type,
            source_label=source_label,
            source_content=source_content,
            instructions=instructions
        )
    except Exception as canon_err:
        logger.warning(f"Failed to append canon update for {project_id}: {canon_err}")

    applied_targets: List[str] = []

    try:
        project = await get_project(project_id)
        if not project:
            await _update_canon_log(project_id, entry_id, {"status": "failed", "error": "Project not found"})
            return

        generator = ReferenceContentGenerator(user_id=user_id)
        if not generator.is_available():
            await _update_canon_log(project_id, entry_id, {"status": "skipped", "error": "LLM unavailable"})
            return

        steering_instruction = _build_steering_instruction(
            instructions=instructions,
            source_label=source_label,
            source_type=source_type,
            source_content=source_content
        )

        reference_docs = []
        try:
            reference_docs = await get_project_reference_files(project_id)
        except Exception as exc:
            logger.warning(f"Failed to load reference files for steering: {exc}")

        book_bible_entry = project.get("book_bible", {})
        book_bible_content = ""
        if isinstance(book_bible_entry, dict):
            book_bible_content = book_bible_entry.get("content") or ""
        elif isinstance(book_bible_entry, str):
            book_bible_content = book_bible_entry

        # Update book bible if the source isn't the book bible itself
        if source_type != "book_bible" and book_bible_content:
            updated_book_bible = await generator.apply_reference_edit(
                "book-bible",
                book_bible_content,
                steering_instruction,
                scope=scope
            )
            if updated_book_bible and updated_book_bible.strip():
                success = await _update_book_bible_content(project_id, user_id, updated_book_bible)
                if success:
                    applied_targets.append("book_bible")

        # Update reference files
        for ref in reference_docs:
            filename = ref.get("filename") or ref.get("name") or ref.get("file_name")
            if not filename:
                continue
            normalized_name = _normalize_reference_filename(str(filename))
            if source_type == "reference" and normalized_name == _normalize_reference_filename(source_label):
                continue

            current_content = ref.get("content") or ""
            if not current_content.strip():
                continue

            reference_type = _reference_type_from_filename(normalized_name)
            try:
                updated_content = await generator.apply_reference_edit(
                    reference_type,
                    current_content,
                    steering_instruction,
                    scope=scope
                )
            except Exception as edit_err:
                logger.warning(f"Steering update failed for {normalized_name}: {edit_err}")
                continue

            if not updated_content or not updated_content.strip():
                continue

            updated = await update_reference_file(
                project_id=project_id,
                filename=normalized_name,
                content=updated_content,
                user_id=user_id
            )
            if updated:
                applied_targets.append(normalized_name)
                try:
                    vector_service = VectorStoreService()
                    await vector_service.upsert_reference_file(
                        project_id=project_id,
                        user_id=user_id,
                        filename=normalized_name,
                        content=updated_content,
                        file_type=reference_type.replace("-", "_")
                    )
                except Exception as vector_err:
                    logger.warning(f"Vector update failed for {normalized_name}: {vector_err}")

        # Create a global steering note for future chapters
        note_text = instructions.strip() or (
            "Use the updated canonical source to maintain continuity across future chapters."
        )
        await create_story_note(
            project_id,
            {
                "chapter_id": "global",
                "content": f"Steering update from {source_label}: {note_text}",
                "created_by": user_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "resolved": False,
                "apply_to_future": True,
                "scope": "global",
                "intent": "continuity"
            },
            user_id=user_id
        )

        await _update_canon_log(
            project_id,
            entry_id,
            {
                "status": "completed",
                "applied_targets": applied_targets,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }
        )
    except Exception as exc:
        logger.error(f"Steering update failed for project {project_id}: {exc}")
        await _update_canon_log(
            project_id,
            entry_id,
            {
                "status": "failed",
                "error": str(exc),
                "completed_at": datetime.now(timezone.utc).isoformat()
            }
        )


async def rewrite_chapter_for_canon(
    project_id: str,
    user_id: str,
    chapter_id: str,
    instructions: str,
    source_label: str,
    source_type: str,
    source_content: str,
    log_entry_id: Optional[str] = None
) -> None:
    try:
        db = get_database_adapter()
        chapter_data = await db.get_chapter(chapter_id, user_id=user_id)
        if not chapter_data:
            await _update_canon_log(project_id, log_entry_id, {"status": "failed", "error": "Chapter not found"})
            return

        project = await get_project(project_id)
        if not project:
            await _update_canon_log(project_id, log_entry_id, {"status": "failed", "error": "Project not found"})
            return

        book_bible_content = ""
        bb_entry = project.get("book_bible", {})
        if isinstance(bb_entry, dict):
            book_bible_content = bb_entry.get("content", "")
        elif isinstance(bb_entry, str):
            book_bible_content = bb_entry

        references_content: Dict[str, str] = {}
        try:
            reference_docs = await get_project_reference_files(project_id)
            for ref in reference_docs:
                fname = ref.get("filename") or ref.get("name") or ref.get("file_name")
                if fname:
                    references_content[str(fname)] = ref.get("content", "")
        except Exception:
            pass

        notes = await list_story_notes(project_id, user_id)
        usable_notes = [
            n for n in notes
            if not n.get("resolved") and n.get("apply_to_future") is not False
        ]
        note_lines = []
        for note in usable_notes[:10]:
            content = (note.get("content") or "").strip()
            if content:
                note_lines.append(content[:240])

        steer_context = {
            "book_bible": book_bible_content,
            "references": references_content,
            "director_notes": "\n".join(note_lines),
            "canon_source": source_content,
            "canon_label": source_label,
            "canon_type": source_type
        }

        enable_billing = os.getenv("ENABLE_CREDITS_BILLING", "false").lower() == "true"
        orchestrator = LLMOrchestrator(
            retry_config=RetryConfig(max_retries=2),
            user_id=user_id,
            enable_billing=enable_billing
        )

        rewrite_instruction = instructions.strip() or (
            f"Align this chapter with the updated canon from {source_label}. "
            "Preserve existing plot beats unless they conflict with the canon update."
        )

        result = await orchestrator.rewrite_full_chapter(
            chapter_text=chapter_data.get("content", ""),
            instruction=rewrite_instruction,
            context={**steer_context, "chapter_number": chapter_data.get("chapter_number", 0)},
            chapter_number=chapter_data.get("chapter_number", 0),
        )

        if not result.success or not result.content:
            await _update_canon_log(project_id, log_entry_id, {"status": "failed", "error": result.error or "Rewrite failed"})
            return

        updated_content = result.content.strip()
        updates = {
            "content": updated_content,
            "metadata.word_count": len(updated_content.split()),
            "metadata.updated_at": datetime.now(timezone.utc).isoformat(),
            "metadata.updated_by": user_id
        }
        await update_chapter(chapter_id, updates, user_id=user_id, project_id=project_id)

        version_data = {
            "content": updated_content,
            "reason": "steering_rewrite",
            "user_id": user_id,
            "changes_summary": f"Canon rewrite from {source_label}"
        }
        await add_chapter_version(chapter_id, version_data, user_id=user_id, project_id=project_id)

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
            logger.warning(f"Failed to update vector memory after steering rewrite for chapter {chapter_id}: {vector_err}")

        # Keep local workspace chapter files in sync for auto-complete continuity.
        try:
            from backend.utils.paths import get_project_workspace, ensure_project_structure
            ws = get_project_workspace(project_id)
            ensure_project_structure(ws)
            ch_num = int(chapter_data.get("chapter_number", 0) or 0)
            if ch_num > 0:
                (ws / "chapters" / f"chapter-{ch_num:02d}.md").write_text(updated_content, encoding="utf-8")
        except Exception:
            pass

        # After canon-driven rewrite, rebuild canon-log + chapter-ledger from the new chapter text.
        try:
            from backend.services.chapter_ledger_service import update_chapter_ledger
            from backend.services.canon_log_service import update_canon_log
            pov_context = None
            ch_num = int(chapter_data.get("chapter_number", 0) or 0)
            if ch_num > 0:
                await update_chapter_ledger(
                    project_id=project_id,
                    user_id=user_id,
                    chapter_number=ch_num,
                    chapter_content=updated_content,
                    book_bible=book_bible_content,
                    references=references_content,
                    pov_context=pov_context,
                    vector_store_ids=[]
                )
                await update_canon_log(
                    project_id=project_id,
                    user_id=user_id,
                    chapter_number=ch_num,
                    chapter_content=updated_content,
                    book_bible=book_bible_content,
                    references=references_content,
                    vector_store_ids=[]
                )
        except Exception as artifact_err:
            logger.warning(f"Failed to rebuild canon/ledger after steering rewrite: {artifact_err}")

        await _update_canon_log(
            project_id,
            log_entry_id,
            {
                "status": "completed"
            }
        )
    except Exception as exc:
        logger.error(f"Steering rewrite failed for chapter {chapter_id}: {exc}")
        await _update_canon_log(project_id, log_entry_id, {"status": "failed", "error": str(exc)})
