#!/usr/bin/env python3
"""
Vector Store Service
Manages OpenAI vector stores for project/user memory and retrieval.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except Exception:
    OpenAI = None
    _OPENAI_AVAILABLE = False

try:
    from google.cloud.firestore_v1.base_query import FieldFilter
except Exception:
    FieldFilter = None

try:
    from backend.database_integration import get_project, get_database_adapter
    from backend.services.firestore_service import get_firestore_client
except Exception:
    try:
        from database_integration import get_project, get_database_adapter
        from services.firestore_service import get_firestore_client
    except Exception:
        get_project = None
        get_database_adapter = None
        get_firestore_client = None

logger = logging.getLogger(__name__)


@dataclass
class VectorSearchResult:
    text: str
    score: Optional[float] = None
    file_id: Optional[str] = None
    filename: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class VectorStoreService:
    """OpenAI vector store management and retrieval for project memory."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.enabled = os.getenv("ENABLE_VECTOR_MEMORY", "true").lower() == "true"
        self.client = OpenAI(api_key=self.api_key) if _OPENAI_AVAILABLE and self.api_key else None
        self.available = bool(self.enabled and self.client)
        self.local_storage_root = Path("local_storage")
        self.unavailable_reason = self._get_unavailable_reason()

    def _get_unavailable_reason(self) -> Optional[str]:
        if not self.enabled:
            return "ENABLE_VECTOR_MEMORY is false"
        if not _OPENAI_AVAILABLE:
            return "OpenAI SDK not available"
        if not self.api_key:
            return "OPENAI_API_KEY missing"
        if not self.client:
            return "OpenAI client unavailable"
        return None

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------
    async def ensure_project_vector_store(
        self,
        project_id: str,
        user_id: str,
        project_title: Optional[str] = None
    ) -> Optional[str]:
        """Ensure a project-scoped vector store exists and return its id."""
        if not self.available:
            return None

        project_data = await self._load_project(project_id)
        existing = self._extract_project_vector_store_id(project_data)
        if existing:
            return existing

        store_name = f"project-{project_id}"
        if project_title:
            store_name = f"{store_name}-{self._safe_name(project_title)}"

        vector_store_id = await self._create_vector_store(store_name)
        if not vector_store_id:
            return None

        await self._update_project_memory(project_id, user_id, {
            "project_vector_store_id": vector_store_id,
            "last_indexed_at": datetime.now(timezone.utc).isoformat()
        })

        await self._ensure_system_guidelines(project_id, user_id, vector_store_id)
        await self._ensure_project_settings_snapshot(project_id, user_id, project_data, vector_store_id)

        return vector_store_id

    async def ensure_user_vector_store(self, user_id: str) -> Optional[str]:
        """Ensure a user-scoped vector store exists and return its id."""
        if not self.available or not user_id or not get_firestore_client:
            return None

        try:
            client = get_firestore_client()
            user_ref = client.collection("users").document(user_id)
            user_doc = user_ref.get()
            user_data = user_doc.to_dict() if user_doc.exists else {}
            profile = user_data.get("profile", {}) if isinstance(user_data, dict) else {}
            existing = profile.get("vector_store_id")
            if existing:
                return existing

            vector_store_id = await self._create_vector_store(f"user-{user_id}")
            if not vector_store_id:
                return None

            user_ref.set({"profile": {"vector_store_id": vector_store_id}}, merge=True)
            return vector_store_id
        except Exception as e:
            logger.warning(f"Failed to ensure user vector store: {e}")
            return None

    async def update_project_memory_fields(self, project_id: str, user_id: str, updates: Dict[str, Any]) -> None:
        """Public wrapper to update project memory fields."""
        await self._update_project_memory(project_id, user_id, updates)

    async def upsert_book_bible(
        self,
        project_id: str,
        user_id: str,
        content: str
    ) -> None:
        """Upsert book bible content into project vector store."""
        await self._upsert_document(
            project_id=project_id,
            user_id=user_id,
            doc_type="book_bible",
            source_id="book_bible",
            title="Book Bible",
            content=content,
            metadata={"source": "project"}
        )

    async def upsert_reference_file(
        self,
        project_id: str,
        user_id: str,
        filename: str,
        content: str,
        file_type: Optional[str] = None
    ) -> None:
        """Upsert a reference file into project vector store."""
        doc_type = file_type or "reference_file"
        await self._upsert_document(
            project_id=project_id,
            user_id=user_id,
            doc_type=doc_type,
            source_id=filename,
            title=filename,
            content=content,
            metadata={"source": "reference_file"}
        )

    async def upsert_chapter(
        self,
        project_id: str,
        user_id: str,
        chapter_id: str,
        chapter_number: int,
        title: str,
        content: str
    ) -> None:
        """Upsert chapter content into project vector store."""
        await self._upsert_document(
            project_id=project_id,
            user_id=user_id,
            doc_type="chapter",
            source_id=chapter_id,
            title=title or f"Chapter {chapter_number}",
            content=content,
            metadata={"chapter_number": chapter_number}
        )

    async def upsert_story_note(
        self,
        project_id: str,
        user_id: str,
        note_id: str,
        content: str,
        scope: str = "chapter",
        chapter_id: Optional[str] = None,
        intent: Optional[str] = None
    ) -> None:
        """Upsert a story/director note into project vector store."""
        title = f"Story Note ({scope})"
        if chapter_id:
            title = f"{title} - {chapter_id}"
        metadata = {"scope": scope, "intent": intent or ""}
        await self._upsert_document(
            project_id=project_id,
            user_id=user_id,
            doc_type="story_note",
            source_id=note_id,
            title=title,
            content=content,
            metadata=metadata
        )

    async def upsert_project_settings_snapshot(
        self,
        project_id: str,
        user_id: str
    ) -> None:
        """Upsert a snapshot of project settings into vector store."""
        project_data = await self._load_project(project_id)
        await self._ensure_project_settings_snapshot(project_id, user_id, project_data)

    async def delete_story_note(
        self,
        project_id: str,
        user_id: str,
        note_id: str
    ) -> None:
        """Delete a note from vector store when removed."""
        await self._deactivate_document(project_id, user_id, doc_type="story_note", source_id=note_id)

    async def retrieve_chapter_context(
        self,
        project_id: str,
        user_id: str,
        query: str,
        max_results: int = 12
    ) -> List[VectorSearchResult]:
        """Retrieve relevant context for a chapter prompt."""
        return await self._search_project_memory(project_id, user_id, query, max_results=max_results)

    async def resolve_documents_by_file_ids(
        self,
        project_id: str,
        user_id: str,
        file_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """Resolve vector document records for given file ids."""
        if not file_ids or not get_firestore_client:
            return []
        try:
            client = get_firestore_client()
            docs_ref = client.collection("users").document(user_id)\
                .collection("projects").document(project_id)\
                .collection("vector_documents")
            results: List[Dict[str, Any]] = []
            chunk_size = 10
            for idx in range(0, len(file_ids), chunk_size):
                chunk = file_ids[idx:idx + chunk_size]
                query = docs_ref.where(filter=FieldFilter("file_id", "in", chunk)) if FieldFilter else docs_ref
                docs = query.stream()
                for doc in docs:
                    data = doc.to_dict() or {}
                    if data.get("file_id") in chunk:
                        results.append(data)
            return results
        except Exception as e:
            logger.warning(f"Failed to resolve vector documents: {e}")
            return []

    async def retrieve_kdp_context(
        self,
        project_id: str,
        user_id: Optional[str]
    ) -> str:
        """Retrieve context relevant to KDP metadata generation."""
        if not user_id:
            return ""

        query = (
            "Provide a concise summary of the book's core premise, main characters, "
            "setting, tone, themes, and unique hook for marketing copy."
        )
        results = await self._search_project_memory(project_id, user_id, query, max_results=10)
        return self._format_results(results, max_chars=1800)

    async def retrieve_guidelines(
        self,
        project_id: str,
        user_id: Optional[str],
        max_results: int = 6
    ) -> str:
        """Retrieve system/user guidelines and steering notes for writing."""
        if not user_id:
            return ""
        query = (
            "Retrieve system guidelines, writing constraints, steering notes, "
            "tone requirements, and non-negotiable instructions."
        )
        results = await self._search_project_memory(project_id, user_id, query, max_results=max_results)
        return self._format_results(results, max_chars=1400)

    async def retrieve_cover_art_context(
        self,
        project_id: str,
        user_id: Optional[str],
        max_results: int = 8
    ) -> str:
        """Retrieve visual, setting, character, and theme cues for cover art."""
        if not user_id:
            return ""
        query = (
            "Extract only visual cues for cover art: setting/locations, time period, "
            "character appearance or silhouettes, themes, symbols, mood, and color palette. "
            "Return concrete elements supported by the project materials."
        )
        results = await self._search_project_memory(project_id, user_id, query, max_results=max_results)
        return self._format_results(results, max_chars=1600)

    async def retrieve_title_context(
        self,
        project_id: str,
        user_id: Optional[str],
        max_results: int = 8
    ) -> str:
        """Retrieve premise, tone, themes, and hooks for title ideation."""
        if not user_id:
            return ""
        query = (
            "Summarize the story's core premise, genre, tone, themes, setting, "
            "main character archetypes, and unique hooks that would inform a book title. "
            "Avoid spoilers and stick to concrete, explicit details."
        )
        results = await self._search_project_memory(project_id, user_id, query, max_results=max_results)
        return self._format_results(results, max_chars=1600)

    def format_results(self, results: List[VectorSearchResult], max_chars: int = 2000) -> str:
        """Public formatter for vector search results."""
        return self._format_results(results, max_chars=max_chars)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    async def _load_project(self, project_id: str) -> Dict[str, Any]:
        if not get_project:
            return {}
        try:
            return await get_project(project_id) or {}
        except Exception:
            return {}

    def _extract_project_vector_store_id(self, project_data: Optional[Dict[str, Any]]) -> Optional[str]:
        if not project_data or not isinstance(project_data, dict):
            return None
        memory = project_data.get("memory", {}) if isinstance(project_data.get("memory"), dict) else {}
        return memory.get("project_vector_store_id")

    async def _update_project_memory(self, project_id: str, user_id: str, updates: Dict[str, Any]) -> None:
        if not get_firestore_client:
            self._update_local_project_memory(project_id, updates)
            return

        try:
            client = get_firestore_client()
            user_ref = client.collection("users").document(user_id).collection("projects").document(project_id)
            user_ref.set({"memory": updates}, merge=True)
            root_ref = client.collection("projects").document(project_id)
            root_ref.set({"memory": updates}, merge=True)
        except Exception as e:
            logger.warning(f"Failed to update project memory: {e}")
            self._update_local_project_memory(project_id, updates)

    def _update_local_project_memory(self, project_id: str, updates: Dict[str, Any]) -> None:
        try:
            project_file = self.local_storage_root / "projects" / f"{project_id}.json"
            if not project_file.exists():
                return
            data = json.loads(project_file.read_text(encoding="utf-8"))
            memory = data.get("memory", {})
            if not isinstance(memory, dict):
                memory = {}
            memory.update(updates)
            data["memory"] = memory
            project_file.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to update local project memory: {e}")

    async def _create_vector_store(self, name: str) -> Optional[str]:
        if not self.available:
            return None

        def _create():
            if hasattr(self.client, "beta") and hasattr(self.client.beta, "vector_stores"):
                return self.client.beta.vector_stores.create(name=name)
            return self.client.vector_stores.create(name=name)

        try:
            store = await asyncio.to_thread(_create)
            return getattr(store, "id", None)
        except Exception as e:
            logger.error(f"Failed to create vector store {name}: {e}")
            return None

    async def _ensure_system_guidelines(self, project_id: str, user_id: str, vector_store_id: str) -> None:
        guidelines = self._system_guidelines_text()
        if not guidelines:
            return
        await self._upsert_document(
            project_id=project_id,
            user_id=user_id,
            doc_type="system_guideline",
            source_id="system_guidelines",
            title="Writing System Guidelines",
            content=guidelines,
            metadata={"source": "system"},
            vector_store_id=vector_store_id
        )

    async def _ensure_project_settings_snapshot(
        self,
        project_id: str,
        user_id: str,
        project_data: Optional[Dict[str, Any]],
        vector_store_id: Optional[str] = None
    ) -> None:
        if not project_data or not isinstance(project_data, dict):
            return
        settings = project_data.get("settings", {})
        metadata = project_data.get("metadata", {})
        if not settings and not metadata:
            return
        payload = {
            "title": metadata.get("title"),
            "genre": settings.get("genre"),
            "target_chapters": settings.get("target_chapters"),
            "word_count_per_chapter": settings.get("word_count_per_chapter"),
            "target_audience": settings.get("target_audience"),
            "writing_style": settings.get("writing_style"),
            "quality_gates_enabled": settings.get("quality_gates_enabled"),
            "auto_completion_enabled": settings.get("auto_completion_enabled"),
        }
        content = "Project Settings:\n" + json.dumps(payload, indent=2)
        await self._upsert_document(
            project_id=project_id,
            user_id=user_id,
            doc_type="project_settings",
            source_id="project_settings",
            title="Project Settings Snapshot",
            content=content,
            metadata={"source": "system"},
            vector_store_id=vector_store_id
        )

    async def _upsert_document(
        self,
        project_id: str,
        user_id: str,
        doc_type: str,
        source_id: str,
        title: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        vector_store_id: Optional[str] = None
    ) -> None:
        if not self.available or not content or not content.strip():
            return

        project_data = await self._load_project(project_id)
        vector_store_id = vector_store_id or self._extract_project_vector_store_id(project_data)
        if not vector_store_id:
            vector_store_id = await self.ensure_project_vector_store(project_id, user_id, project_data.get("metadata", {}).get("title"))
        if not vector_store_id:
            return

        content_hash = self._content_hash(content)
        existing = await self._find_active_document(project_id, user_id, doc_type, source_id)
        if existing and existing.get("content_hash") == content_hash:
            return

        if existing:
            await self._deactivate_document(project_id, user_id, doc_type, source_id, existing_doc=existing)

        file_payload = self._build_file_payload(project_id, doc_type, source_id, title, content, metadata)
        file_id = await self._upload_file(vector_store_id, file_payload)
        if not file_id:
            return

        record = {
            "doc_id": self._uuid(),
            "project_id": project_id,
            "user_id": user_id,
            "vector_store_id": vector_store_id,
            "file_id": file_id,
            "doc_type": doc_type,
            "source_id": source_id,
            "title": title,
            "is_active": True,
            "content_hash": content_hash,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        await self._save_document_record(project_id, user_id, record)

    async def _deactivate_document(
        self,
        project_id: str,
        user_id: str,
        doc_type: str,
        source_id: str,
        existing_doc: Optional[Dict[str, Any]] = None
    ) -> None:
        if not existing_doc:
            existing_doc = await self._find_active_document(project_id, user_id, doc_type, source_id)
        if not existing_doc:
            return

        vector_store_id = existing_doc.get("vector_store_id")
        file_id = existing_doc.get("file_id")
        if vector_store_id and file_id:
            await self._delete_file(vector_store_id, file_id)

        existing_doc["is_active"] = False
        existing_doc["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self._save_document_record(project_id, user_id, existing_doc, overwrite=True)

    async def _upload_file(self, vector_store_id: str, content: str) -> Optional[str]:
        def _create_file(path: str):
            if hasattr(self.client, "files"):
                with open(path, "rb") as handle:
                    return self.client.files.create(file=handle, purpose="assistants")
            raise RuntimeError("OpenAI client does not support file upload")

        def _attach_file(file_id: str):
            if hasattr(self.client, "beta") and hasattr(self.client.beta, "vector_stores"):
                return self.client.beta.vector_stores.files.create(vector_store_id=vector_store_id, file_id=file_id)
            return self.client.vector_stores.files.create(vector_store_id=vector_store_id, file_id=file_id)

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False) as tmp:
                tmp.write(content)
                tmp.flush()
                temp_path = tmp.name

            file_obj = await asyncio.to_thread(_create_file, temp_path)
            file_id = getattr(file_obj, "id", None)
            if not file_id:
                return None

            await asyncio.to_thread(_attach_file, file_id)
            return file_id
        except Exception as e:
            logger.error(f"Failed to upload file to vector store: {e}")
            return None
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

    async def _delete_file(self, vector_store_id: str, file_id: str) -> None:
        def _delete_vector_file():
            if hasattr(self.client, "beta") and hasattr(self.client.beta, "vector_stores"):
                return self.client.beta.vector_stores.files.delete(vector_store_id=vector_store_id, file_id=file_id)
            return self.client.vector_stores.files.delete(vector_store_id=vector_store_id, file_id=file_id)

        def _delete_file_obj():
            if hasattr(self.client, "files"):
                return self.client.files.delete(file_id)
            return None

        try:
            await asyncio.to_thread(_delete_vector_file)
        except Exception as e:
            logger.warning(f"Failed to delete vector file {file_id}: {e}")
        try:
            await asyncio.to_thread(_delete_file_obj)
        except Exception:
            pass

    async def _search_project_memory(
        self,
        project_id: str,
        user_id: str,
        query: str,
        max_results: int = 8
    ) -> List[VectorSearchResult]:
        if not self.available or not query.strip():
            return []

        project_data = await self._load_project(project_id)
        vector_store_id = self._extract_project_vector_store_id(project_data)
        results: List[VectorSearchResult] = []
        if vector_store_id:
            results.extend(await self._search_vector_store(vector_store_id, query, max_results))

        user_store_id = self._extract_user_vector_store_id(project_data)
        if not user_store_id:
            user_store_id = await self._get_user_vector_store_id(user_id)
        if user_store_id:
            results.extend(await self._search_vector_store(user_store_id, query, max_results=max(3, max_results // 2)))

        # Deduplicate results across project+user stores to reduce token bloat.
        try:
            deduped: List[VectorSearchResult] = []
            seen_keys = set()
            # Prefer higher scores first when available.
            def _score_key(item: VectorSearchResult) -> float:
                try:
                    return float(item.score or 0.0)
                except Exception:
                    return 0.0
            for item in sorted(results, key=_score_key, reverse=True):
                file_key = (item.file_id or "").strip()
                text_key = (item.text or "").strip()[:180]
                key = (file_key or text_key).lower()
                if not key:
                    continue
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                deduped.append(item)
                if len(deduped) >= int(max_results):
                    break
            return deduped
        except Exception:
            return results[:max_results]

    def _extract_user_vector_store_id(self, project_data: Optional[Dict[str, Any]]) -> Optional[str]:
        if not project_data or not isinstance(project_data, dict):
            return None
        memory = project_data.get("memory", {}) if isinstance(project_data.get("memory"), dict) else {}
        return memory.get("user_vector_store_id")

    async def _get_user_vector_store_id(self, user_id: str) -> Optional[str]:
        if not get_firestore_client or not user_id:
            return None
        try:
            client = get_firestore_client()
            user_doc = client.collection("users").document(user_id).get()
            data = user_doc.to_dict() if user_doc.exists else {}
            profile = data.get("profile", {}) if isinstance(data, dict) else {}
            return profile.get("vector_store_id")
        except Exception:
            return None

    async def _search_vector_store(
        self,
        vector_store_id: str,
        query: str,
        max_results: int = 8
    ) -> List[VectorSearchResult]:
        def _search_variant(limit_key: Optional[str]):
            search_fn = None
            if hasattr(self.client, "beta") and hasattr(self.client.beta, "vector_stores") and hasattr(self.client.beta.vector_stores, "search"):
                search_fn = self.client.beta.vector_stores.search
            elif hasattr(self.client, "vector_stores") and hasattr(self.client.vector_stores, "search"):
                search_fn = self.client.vector_stores.search
            if not search_fn:
                return None

            kwargs = {}
            if limit_key:
                kwargs[limit_key] = max_results
            return search_fn(
                vector_store_id=vector_store_id,
                query=query,
                **kwargs
            )

        try:
            raw = None
            for limit_key in ("max_results", "top_k", "k", "limit", "max_num_results", None):
                try:
                    raw = await asyncio.to_thread(_search_variant, limit_key)
                    break
                except TypeError:
                    continue
        except Exception as e:
            logger.warning(f"Vector search failed: {e}")
            return []

        if raw is None:
            return []

        data = getattr(raw, "data", raw) or []
        results: List[VectorSearchResult] = []
        for item in data:
            text_chunks = []
            content = getattr(item, "content", None) or item.get("content") if isinstance(item, dict) else None
            if isinstance(content, list):
                for part in content:
                    text = getattr(part, "text", None) or (part.get("text") if isinstance(part, dict) else None)
                    if text:
                        text_chunks.append(text)
            elif isinstance(content, str):
                text_chunks.append(content)

            text = "\n".join(text_chunks).strip()
            if not text:
                continue

            metadata = getattr(item, "metadata", None) or (item.get("metadata") if isinstance(item, dict) else None)
            results.append(VectorSearchResult(
                text=text,
                score=getattr(item, "score", None) or (item.get("score") if isinstance(item, dict) else None),
                file_id=getattr(item, "file_id", None) or (item.get("file_id") if isinstance(item, dict) else None),
                filename=getattr(item, "filename", None) or (item.get("filename") if isinstance(item, dict) else None),
                metadata=metadata if isinstance(metadata, dict) else None
            ))
        return results

    async def _find_active_document(
        self,
        project_id: str,
        user_id: str,
        doc_type: str,
        source_id: str
    ) -> Optional[Dict[str, Any]]:
        if get_database_adapter:
            adapter = get_database_adapter()
            if not adapter.use_firestore:
                return self._find_local_document(project_id, doc_type, source_id)

        if not get_firestore_client:
            return self._find_local_document(project_id, doc_type, source_id)

        try:
            client = get_firestore_client()
            docs_ref = client.collection("users").document(user_id)\
                .collection("projects").document(project_id)\
                .collection("vector_documents")

            if FieldFilter:
                query = docs_ref.where(filter=FieldFilter("doc_type", "==", doc_type))\
                    .where(filter=FieldFilter("source_id", "==", source_id))\
                    .where(filter=FieldFilter("is_active", "==", True))\
                    .limit(1)
            else:
                query = docs_ref.where("doc_type", "==", doc_type)\
                    .where("source_id", "==", source_id)\
                    .where("is_active", "==", True)\
                    .limit(1)

            docs = list(query.stream())
            if not docs:
                return None
            return docs[0].to_dict()
        except Exception as e:
            logger.warning(f"Failed to find vector document: {e}")
            return self._find_local_document(project_id, doc_type, source_id)

    async def _save_document_record(
        self,
        project_id: str,
        user_id: str,
        record: Dict[str, Any],
        overwrite: bool = False
    ) -> None:
        if get_database_adapter:
            adapter = get_database_adapter()
            if not adapter.use_firestore:
                self._save_local_document(project_id, record)
                return

        if not get_firestore_client:
            self._save_local_document(project_id, record)
            return

        try:
            client = get_firestore_client()
            doc_id = record.get("doc_id") or self._uuid()
            record["doc_id"] = doc_id
            doc_ref = client.collection("users").document(user_id)\
                .collection("projects").document(project_id)\
                .collection("vector_documents").document(doc_id)
            if overwrite:
                doc_ref.set(record, merge=True)
            else:
                doc_ref.set(record)
        except Exception as e:
            logger.warning(f"Failed to save vector document record: {e}")
            self._save_local_document(project_id, record)

    def _find_local_document(self, project_id: str, doc_type: str, source_id: str) -> Optional[Dict[str, Any]]:
        docs = self._load_local_docs(project_id)
        for doc in docs:
            if doc.get("doc_type") == doc_type and doc.get("source_id") == source_id and doc.get("is_active"):
                return doc
        return None

    def _save_local_document(self, project_id: str, record: Dict[str, Any]) -> None:
        docs = self._load_local_docs(project_id)
        doc_id = record.get("doc_id")
        updated = False
        for idx, doc in enumerate(docs):
            if doc_id and doc.get("doc_id") == doc_id:
                docs[idx] = record
                updated = True
                break
        if not updated:
            docs.append(record)
        self._write_local_docs(project_id, docs)

    def _load_local_docs(self, project_id: str) -> List[Dict[str, Any]]:
        docs_file = self.local_storage_root / "projects" / project_id / "vector_docs.json"
        if not docs_file.exists():
            return []
        try:
            return json.loads(docs_file.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _write_local_docs(self, project_id: str, docs: List[Dict[str, Any]]) -> None:
        docs_dir = self.local_storage_root / "projects" / project_id
        docs_dir.mkdir(parents=True, exist_ok=True)
        docs_file = docs_dir / "vector_docs.json"
        docs_file.write_text(json.dumps(docs, indent=2, default=str), encoding="utf-8")

    def _build_file_payload(
        self,
        project_id: str,
        doc_type: str,
        source_id: str,
        title: str,
        content: str,
        metadata: Optional[Dict[str, Any]]
    ) -> str:
        header = {
            "project_id": project_id,
            "doc_type": doc_type,
            "source_id": source_id,
            "title": title,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }
        if metadata:
            header.update(metadata)
        header_lines = "\n".join([f"{key}: {value}" for key, value in header.items() if value is not None])
        return f"{header_lines}\n\n{content.strip()}\n"

    def _system_guidelines_text(self) -> str:
        return (
            "Writing System Guidelines:\n"
            "- Maintain continuity with established facts, characters, and world rules.\n"
            "- Do not contradict book bible or confirmed edits.\n"
            "- Avoid repetition loops; vary phrasing and imagery.\n"
            "- Keep openings and endings fresh while staying in-scene.\n"
            "- Use em dashes sparingly.\n"
            "- Follow target word counts without padding or filler.\n"
        )

    def _content_hash(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _format_results(self, results: List[VectorSearchResult], max_chars: int = 2000) -> str:
        if not results:
            return ""
        chunks: List[str] = []
        used = 0
        for result in results:
            snippet = result.text.strip()
            if not snippet:
                continue
            label = self._infer_doc_label(snippet, result)
            block = f"[{label}]\n{snippet}"
            if used + len(block) > max_chars:
                remaining = max_chars - used
                if remaining > 80:
                    chunks.append(block[:remaining])
                break
            chunks.append(block)
            used += len(block)
        return "\n\n".join(chunks).strip()

    def _infer_doc_label(self, text: str, result: VectorSearchResult) -> str:
        lines = text.splitlines()[:6] if text else []
        for line in lines:
            if line.lower().startswith("doc_type:"):
                return line.split(":", 1)[1].strip().upper()
        first_line = lines[0] if lines else ""
        if ":" in first_line and len(first_line.split(":")[0]) < 20:
            return first_line.split(":")[0].strip().upper()
        if result.filename:
            return result.filename
        return "MEMORY"

    def _uuid(self) -> str:
        import uuid
        return str(uuid.uuid4())

    def _safe_name(self, name: str) -> str:
        cleaned = "".join(c for c in name if c.isalnum() or c in ("-", "_")).strip()
        return cleaned[:40] or "project"

