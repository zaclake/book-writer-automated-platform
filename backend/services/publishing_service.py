#!/usr/bin/env python3
"""
Publishing Service - Book to EPUB/PDF/HTML conversion
Ports Print_Book_Maker shell scripts to Python for integration with the platform.
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import tempfile
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable, Any
import zipfile
import shutil

from google.cloud.firestore_v1.base_query import FieldFilter

from backend.models.firestore_models import (
    PublishConfig, PublishFormat, PublishResult, PublishJobStatus
)

# Import database functions
import sys
import os

# Add current directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from backend.database_integration import (
        get_project, get_project_chapters, get_project_reference_files, get_database_adapter
    )
    from backend.services.firestore_service import get_firestore_client
    from backend.services.vector_store_service import VectorStoreService
except ImportError:
    try:
        # Try without backend prefix
        from database_integration import (
            get_project, get_project_chapters, get_project_reference_files, get_database_adapter
        )
        from services.firestore_service import get_firestore_client
        from services.vector_store_service import VectorStoreService
    except ImportError:
        # Final fallback - import with full path
        sys.path.insert(0, '/app/backend')
        from database_integration import (
            get_project, get_project_chapters, get_project_reference_files, get_database_adapter
        )
        from services.firestore_service import get_firestore_client
        from services.vector_store_service import VectorStoreService

# Run summary helpers
try:
    from backend.utils.run_summaries import emit_summary
except Exception:  # pragma: no cover
    try:
        from utils.run_summaries import emit_summary  # type: ignore
    except Exception:
        emit_summary = None  # type: ignore

# Import Firebase Storage for file uploads
try:
    from firebase_admin import storage
except ImportError:
    storage = None

logger = logging.getLogger(__name__)

PANDOC_TIMEOUT_SECONDS = 600
COVER_ART_DOWNLOAD_TIMEOUT_SECONDS = 60

class PublishingService:
    """Service for converting book projects to publishable formats."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.firebase_bucket = None
        if storage:
            try:
                self.firebase_bucket = storage.bucket()
                self.logger.info("Firebase Storage initialized for publishing")
            except Exception as e:
                self.logger.warning(f"Firebase Storage not available: {e}")
    
    async def _download_cover_art(self, cover_art_url: str, temp_path: Path) -> Optional[Path]:
        """Download and normalize cover art image for embedding.

        Returns a path to a JPEG file suitable for EPUB/PDF embedding.
        """
        try:
            import aiohttp
            from PIL import Image
            from io import BytesIO

            target_file = temp_path / "cover.jpg"

            timeout = aiohttp.ClientTimeout(total=COVER_ART_DOWNLOAD_TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(cover_art_url) as response:
                    if response.status != 200:
                        self.logger.warning(f"Failed to download cover art: HTTP {response.status}")
                        return None

                    data = await response.read()
                    content_type = (response.headers.get('Content-Type') or '').lower()

                    try:
                        image = Image.open(BytesIO(data))
                        if image.mode in ("RGBA", "LA"):
                            background = Image.new("RGB", image.size, (255, 255, 255))
                            background.paste(image, mask=image.split()[-1])
                            image = background
                        elif image.mode != "RGB":
                            image = image.convert("RGB")
                        image.save(target_file, format="JPEG", quality=92, optimize=True)
                        self.logger.info(f"Normalized cover art to JPEG at {target_file} (source {content_type})")
                        return target_file
                    except Exception as pil_err:
                        if 'jpeg' in content_type or 'jpg' in content_type:
                            with open(target_file, 'wb') as f:
                                f.write(data)
                            self.logger.info(f"Saved cover art JPEG bytes directly at {target_file}")
                            return target_file
                        self.logger.error(f"Failed to normalize cover art to JPEG: {pil_err}")
                        return None

        except Exception as e:
            self.logger.error(f"Error downloading cover art: {e}")
            return None

    async def upload_file_to_storage(self, file_path: Path, project_id: str, filename: str) -> str:
        """Upload a file to Firebase Storage and return the public URL.
        
        Returns empty string on failure so downstream checks correctly detect
        missing outputs instead of treating a placeholder path as a valid URL.
        """
        if not self.firebase_bucket:
            self.logger.error("Firebase Storage not available - cannot upload published file")
            return ""
        
        try:
            blob_path = f"published_books/{project_id}/{filename}"
            blob = self.firebase_bucket.blob(blob_path)
            
            with open(file_path, 'rb') as file_data:
                blob.upload_from_file(file_data, content_type=self._get_content_type(filename))
            
            blob.make_public()
            
            public_url = blob.public_url
            self.logger.info(f"File uploaded to Firebase Storage: {public_url}")
            return public_url
            
        except Exception as e:
            self.logger.error(f"Failed to upload {filename} to Firebase Storage: {e}")
            return ""
        
    async def publish_book(
        self,
        project_id: str,
        config: PublishConfig,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        job_id_override: Optional[str] = None,
    ) -> PublishResult:
        """
        Publish a book project to the specified formats.
        
        Args:
            project_id: The project to publish
            config: Publishing configuration
            progress_callback: Optional callback for progress updates
            
        Returns:
            PublishResult with download URLs and metadata
        """
        job_id = job_id_override or f"publish_{project_id}_{int(datetime.now().timestamp())}"
        
        def update_progress(status: str, progress: float):
            if progress_callback:
                progress_callback(status, progress)
            self.logger.info(f"Publishing progress [{job_id}]: {status} ({progress:.1%})")
        
        try:
            update_progress("Starting publication", 0.0)
            
            # Create temporary working directory
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # Step 1: Fetch project data
                update_progress("Fetching project data", 0.1)
                project_data = await self._fetch_project_data(project_id)

                # Step 1.5: Pre-publish readiness validation (ordering, gaps/dupes, artifact presence, versions)
                try:
                    readiness = await self._validate_publish_readiness(project_data)
                    if not readiness.get("ready"):
                        errors = readiness.get("errors") or []
                        raise RuntimeError("Publish readiness validation failed: " + "; ".join([str(e) for e in errors[:8]]))
                except Exception:
                    raise
                
                # Step 2: Build combined markdown
                update_progress("Building book content", 0.2)
                combined_md, metadata_yaml = await self._build_combined_content(
                    project_data, config, temp_path
                )
                cover_art_url = None
                if config.use_existing_cover:
                    if 'cover_art' in project_data and isinstance(project_data['cover_art'], dict):
                        cover_art_url = project_data['cover_art'].get('image_url')
                    elif 'cover_art_url' in project_data:
                        cover_art_url = project_data.get('cover_art_url')
                
                # Step 3: Generate requested formats
                output_files = {}
                format_progress_map = {
                    PublishFormat.EPUB: (0.4, 0.6),
                    PublishFormat.PDF: (0.6, 0.8),
                    PublishFormat.HTML: (0.3, 0.4)
                }
                
                for fmt in config.formats:
                    start_progress, end_progress = format_progress_map[fmt]
                    update_progress(f"Generating {fmt.upper()}", start_progress)
                    
                    output_file = await self._generate_format(
                        fmt, combined_md, metadata_yaml, temp_path, config, cover_art_url
                    )
                    if output_file:
                        output_files[fmt.value] = output_file
                    
                    update_progress(f"Completed {fmt.upper()}", end_progress)
                
                if config.include_kdp_kit:
                    await self._auto_fill_kdp_fields(
                        project_data=project_data,
                        combined_md=combined_md,
                        config=config
                    )
                    update_progress("Generating KDP publishing kit", 0.82)
                    kdp_kit_file = await self._generate_kdp_kit(
                        project_data=project_data,
                        combined_md=combined_md,
                        temp_path=temp_path,
                        config=config
                    )
                    if kdp_kit_file:
                        output_files["kdp_kit"] = kdp_kit_file
                    update_progress("Completed KDP publishing kit", 0.86)
                
                # Step 4: Upload files to storage
                update_progress("Uploading files", 0.88)
                download_urls = await self._upload_files(project_id, job_id, output_files)
                # Ensure at least one output exists; otherwise, fail the job explicitly
                if not any(download_urls.values()):
                    raise RuntimeError("No outputs were generated (EPUB/PDF/HTML missing). Ensure publishing dependencies are installed.")
                
                # Step 5: Calculate metadata
                update_progress("Finalizing", 0.95)
                file_sizes = {}
                word_count = self._count_words(combined_md)
                
                for fmt, file_path in output_files.items():
                    if file_path.exists():
                        file_sizes[fmt] = file_path.stat().st_size
                
                # Create result
                result = PublishResult(
                    job_id=job_id,
                    project_id=project_id,
                    status=PublishJobStatus.COMPLETED,
                    config=config,
                    epub_url=download_urls.get("epub"),
                    pdf_url=download_urls.get("pdf"),
                    html_url=download_urls.get("html"),
                    kdp_kit_url=download_urls.get("kdp_kit"),
                    created_at=datetime.now(timezone.utc),
                    completed_at=datetime.now(timezone.utc),
                    file_sizes=file_sizes,
                    word_count=word_count,
                    page_count=max(1, word_count // 250)  # Estimate 250 words per page
                )
                
                update_progress("Publication completed", 1.0)

                # Emit + persist one publish run summary artifact (best-effort).
                try:
                    summary = {
                        "event": "PUBLISH_RUN_SUMMARY",
                        "job_id": job_id,
                        "project_id": project_id,
                        "status": "completed",
                        "formats": [f.value if hasattr(f, "value") else str(f) for f in (config.formats or [])],
                        "chapters": {
                            "count": len((project_data or {}).get("chapters") or []),
                            "numbers": [c.get("chapter_number") for c in ((project_data or {}).get("chapters") or [])][:200],
                        },
                        "artifacts": {
                            "has_canon_log": bool(((project_data or {}).get("reference_files") or {}).get("canon-log.md")),
                            "has_chapter_ledger": bool(((project_data or {}).get("reference_files") or {}).get("chapter-ledger.md")),
                        },
                        "word_count": word_count,
                        "file_sizes": file_sizes,
                        "download_urls": {k: v for k, v in (download_urls or {}).items() if v},
                    }
                    if emit_summary is not None:
                        emit_summary(self.logger, summary)
                    try:
                        if get_firestore_client:
                            db = get_firestore_client()
                            db.collection("publish_jobs").document(job_id).set({"run_summary": summary}, merge=True)
                    except Exception:
                        pass
                except Exception:
                    pass
                return result
                
        except Exception as e:
            self.logger.error(f"Publishing failed for {project_id}: {e}")
            try:
                summary = {
                    "event": "PUBLISH_RUN_SUMMARY",
                    "job_id": job_id,
                    "project_id": project_id,
                    "status": "failed",
                    "error": f"{type(e).__name__}: {str(e)[:480]}",
                }
                if emit_summary is not None:
                    emit_summary(self.logger, summary)
                try:
                    if get_firestore_client:
                        db = get_firestore_client()
                        db.collection("publish_jobs").document(job_id).set({"run_summary": summary}, merge=True)
                except Exception:
                    pass
            except Exception:
                pass
            return PublishResult(
                job_id=job_id,
                project_id=project_id,
                status=PublishJobStatus.FAILED,
                config=config,
                created_at=datetime.now(timezone.utc),
                error_message=str(e)
            )

    async def _validate_publish_readiness(self, project_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate chapter ordering, content availability, and coherence artifact presence.
        Returns {ready: bool, errors: [...], warnings: [...], details: {...}}.
        """
        errors: List[str] = []
        warnings: List[str] = []

        project = (project_data or {}).get("project") or {}
        chapters = (project_data or {}).get("chapters") or []
        refs = (project_data or {}).get("reference_files") or {}

        # Required artifacts
        canon = (refs.get("canon-log.md") or "").strip()
        ledger = (refs.get("chapter-ledger.md") or "").strip()
        if not canon:
            errors.append("Missing or empty canon-log.md reference file.")
        if not ledger:
            errors.append("Missing or empty chapter-ledger.md reference file.")

        # Chapter ordering validation
        nums: List[int] = []
        for ch in chapters:
            try:
                nums.append(int((ch or {}).get("chapter_number") or 0))
            except Exception:
                nums.append(0)
        if any(n <= 0 for n in nums):
            errors.append("One or more chapters missing a valid chapter_number (>0).")
        seen = set()
        dups = sorted({n for n in nums if n in seen or (seen.add(n) or False)})  # type: ignore[misc]
        if dups:
            errors.append(f"Duplicate chapter_number(s): {dups[:10]}")
        if nums:
            positive = sorted([n for n in nums if n > 0])
            if positive and positive[0] != 1:
                errors.append(f"Chapter numbering must start at 1 (found {positive[0]}).")
            if positive:
                expected = list(range(1, max(positive) + 1))
                missing = sorted(set(expected) - set(positive))
                if missing:
                    errors.append(f"Missing chapter_number(s): {missing[:12]}")

        # Content availability (latest version preferred).
        # Cache resolved content on each chapter dict so _build_combined_content
        # can reuse it without re-fetching versions from Firestore.
        owner_id = (project.get("metadata", {}) or {}).get("owner_id")
        for ch in chapters:
            chapter_id = (ch or {}).get("id")
            chapter_num = (ch or {}).get("chapter_number")
            try:
                content = await self._get_chapter_content_for_publish(ch, owner_id=owner_id, project_id=project.get("metadata", {}).get("project_id") or project.get("project_id") or project_data.get("project_id"))
            except Exception:
                content = (ch or {}).get("content", "")
            ch["_resolved_content"] = content
            if not (content or "").strip():
                errors.append(f"Chapter {chapter_num} has no publishable content (id={chapter_id}).")

        return {
            "ready": not errors,
            "errors": errors,
            "warnings": warnings,
        }

    async def _get_chapter_content_for_publish(self, chapter: Dict[str, Any], *, owner_id: Optional[str], project_id: Optional[str]) -> str:
        """
        Prefer latest version content if available; else fallback to chapter.content.
        If versions are not present on the chapter payload, try to load via Firestore service.
        """
        if not isinstance(chapter, dict):
            return ""
        # 1) Inline versions array
        versions = chapter.get("versions", [])
        if isinstance(versions, list) and versions:
            best = None
            best_num = -1
            for v in versions:
                if not isinstance(v, dict):
                    continue
                try:
                    num = int(v.get("version_number") or 0)
                except Exception:
                    num = 0
                content = v.get("content") or ""
                if content and num >= best_num:
                    best = content
                    best_num = num
            if best and str(best).strip():
                return str(best)

        # 2) Fetch only the latest version from Firestore (limit=1 descending)
        chapter_id = chapter.get("id") or chapter.get("chapter_id")
        if chapter_id and owner_id and project_id:
            try:
                adapter = get_database_adapter()
                fs = getattr(adapter, "firestore", None) if adapter else None
                getter = getattr(fs, "get_chapter_versions", None) if fs else None
                if callable(getter):
                    versions = await getter(str(chapter_id), user_id=str(owner_id), project_id=str(project_id), limit=1)
                    if isinstance(versions, list) and versions:
                        best = None
                        best_num = -1
                        for v in versions:
                            if not isinstance(v, dict):
                                continue
                            try:
                                num = int(v.get("version_number") or 0)
                            except Exception:
                                num = 0
                            content = v.get("content") or ""
                            if content and num >= best_num:
                                best = content
                                best_num = num
                        if best and str(best).strip():
                            return str(best)
            except Exception:
                pass

        return str(chapter.get("content") or "")
    
    async def _fetch_project_data(self, project_id: str) -> Dict[str, Any]:
        """Fetch all project data needed for publishing."""
        try:
            # Get project metadata
            project_data = await get_project(project_id)
            if not project_data:
                raise ValueError(f"Project {project_id} not found")
            
            # Get chapters
            chapters = await get_project_chapters(project_id)
            chapters.sort(key=lambda x: x.get('chapter_number', 0))

            # Get reference files (for publish readiness checks)
            reference_files: Dict[str, str] = {}
            try:
                ref_docs = await get_project_reference_files(project_id)
                for ref in ref_docs or []:
                    if not isinstance(ref, dict):
                        continue
                    fname = (ref.get("filename") or "").strip()
                    if not fname:
                        continue
                    reference_files[fname] = ref.get("content", "") or ""
            except Exception:
                reference_files = {}
            
            # Get cover art if exists
            cover_art_url = None
            if 'cover_art' in project_data and isinstance(project_data['cover_art'], dict):
                cover_art_url = project_data['cover_art'].get('image_url')
            # Fallback: query latest cover_art_jobs for this project if not set on project doc
            if not cover_art_url:
                try:
                    from backend.services.firestore_service import get_firestore_client  # type: ignore
                except Exception:
                    from services.firestore_service import get_firestore_client  # type: ignore
                try:
                    client = get_firestore_client()
                    # Avoid composite index by querying and picking latest client-side
                    query = client.collection('cover_art_jobs').where(
                        filter=FieldFilter('project_id', '==', project_id)
                    )
                    docs = list(query.stream())
                    latest = None
                    latest_ts = None
                    for doc in docs:
                        data = doc.to_dict() or {}
                        ts = data.get('created_at') or data.get('updated_at')
                        if ts and (latest_ts is None or ts > latest_ts):
                            latest = data
                            latest_ts = ts
                    if latest:
                        cover_art_url = latest.get('image_url')
                        if cover_art_url:
                            self.logger.info(f"Using fallback cover art from latest job for project {project_id}")
                except Exception as e:
                    self.logger.warning(f"Cover art fallback lookup failed for {project_id}: {e}")
            
            return {
                'project': project_data,
                'chapters': chapters,
                'cover_art_url': cover_art_url,
                'reference_files': reference_files,
            }
            
        except Exception as e:
            self.logger.error(f"Failed to fetch project data: {e}")
            raise
    
    async def _build_combined_content(
        self, 
        project_data: Dict[str, Any], 
        config: PublishConfig,
        temp_path: Path
    ) -> Tuple[str, str]:
        """Build combined markdown content and metadata YAML."""
        
        # Extract project info
        project = project_data['project']
        chapters = project_data['chapters']
        
        # Build metadata YAML
        metadata = {
            'title': config.title,
            'author': config.author,
            'date': config.date or datetime.now().strftime('%Y'),
            'publisher': config.publisher or config.author,
            'rights': config.rights,
        }
        
        if config.isbn:
            metadata['isbn'] = config.isbn
            
        # Add optional sections to metadata
        optional_fields = [
            'dedication', 'acknowledgments', 'foreword', 'preface',
            'epilogue', 'about_author', 'call_to_action', 'other_books',
            'connect_author', 'book_club_questions'
        ]
        
        for field in optional_fields:
            value = getattr(config, field, None)
            if value:
                metadata[field] = value
        
        metadata_yaml = yaml.dump(metadata, default_flow_style=False, allow_unicode=True)
        
        # Build combined markdown content
        combined_lines = [
            "---",
            metadata_yaml.strip(),
            "---",
            ""
        ]
        
        # Add optional front matter sections
        self._add_optional_section(combined_lines, "dedication", config.dedication, "center")
        self._add_optional_section(combined_lines, "acknowledgments", config.acknowledgments)
        self._add_optional_section(combined_lines, "foreword", config.foreword)
        self._add_optional_section(combined_lines, "preface", config.preface)
        
        # Add chapters (use cached content from validation when available)
        for chapter in chapters:
            chapter_num = chapter.get('chapter_number', 0)
            raw_title = chapter.get('title')
            chapter_title = raw_title.strip() if isinstance(raw_title, str) and raw_title.strip() else f'Chapter {chapter_num}'
            if "_resolved_content" in chapter:
                raw_content = chapter["_resolved_content"]
            else:
                try:
                    owner_id = (project.get("metadata", {}) or {}).get("owner_id")
                    project_meta_id = (project.get("metadata", {}) or {}).get("project_id") or project.get("project_id")
                    raw_content = await self._get_chapter_content_for_publish(chapter, owner_id=owner_id, project_id=project_meta_id)
                except Exception:
                    raw_content = chapter.get("content", "")
            content = self._escape_markdown_text(self._normalize_plain_text_chapter(raw_content))
            
            combined_lines.extend([
                '<div style="page-break-before: always;"></div>',
                "",
                f"# {chapter_title}",
                "",
                content,
                "",
                ""
            ])
        
        # Add optional back matter sections
        self._add_optional_section(combined_lines, "epilogue", config.epilogue)
        self._add_optional_section(combined_lines, "about-the-author", config.about_author)
        self._add_optional_section(combined_lines, "author-notes", config.call_to_action, "center")
        self._add_optional_section(combined_lines, "other-books", config.other_books)
        self._add_optional_section(combined_lines, "connect-with-author", config.connect_author, "center")
        self._add_optional_section(combined_lines, "book-club-questions", config.book_club_questions)
        
        combined_md = "\n".join(combined_lines)
        
        # Write combined markdown to file
        combined_file = temp_path / "book.md"
        combined_file.write_text(combined_md, encoding='utf-8')
        
        # Write metadata to separate YAML file
        metadata_file = temp_path / "metadata.yaml"
        metadata_file.write_text(metadata_yaml, encoding='utf-8')
        
        return combined_md, metadata_yaml
    
    def _add_optional_section(
        self, 
        lines: List[str], 
        section_type: str, 
        content: Optional[str], 
        alignment: str = "left"
    ):
        """Add an optional section to the markdown if content exists."""
        if not content or not content.strip():
            return
            
        title_case = section_type.replace('-', ' ').replace('_', ' ').title()
        
        lines.extend([
            f'<div class="{section_type}-page" style="text-align: {alignment}; page-break-before: always;">',
            "",
            f"# {title_case}",
            "",
            self._escape_markdown_text(self._normalize_plain_text_chapter(content.strip())),
            "",
            "</div>",
            "",
            "\\newpage",
            ""
        ])

    def _normalize_plain_text_chapter(self, text: str) -> str:
        """
        Normalize chapter/section text for Pandoc Markdown while preserving
        legitimate prose formatting (em dashes, emphasis, scene breaks).
        """
        if not text or not isinstance(text, str):
            return ""
        t = text.replace("\r\n", "\n").replace("\r", "\n")
        # Remove duplicate chapter headers (e.g., "Chapter 4\nCHAPTER 4")
        t = re.sub(r"(?im)(chapter\s+\d+)\s*\n\s*chapter\s+\d+", r"\1", t)
        # Strip leading "Chapter X" lines (the epub build step adds its own heading)
        t = re.sub(r"(?im)^\s*chapter\s+\d+\s*\n", "", t)
        # Remove code fences (not expected in prose)
        t = re.sub(r"(?m)^\s*```[a-zA-Z0-9_-]*\s*$", "", t)
        t = t.replace("```", "")
        # Remove heading markers (chapters get their own h1 from the build step)
        t = re.sub(r"(?m)^\s*#{1,6}\s+", "", t)
        # Remove blockquote markers but keep text
        t = re.sub(r"(?m)^\s*>\s?", "", t)
        # Remove list bullets/numbers (unlikely in prose but clean up if present)
        t = re.sub(r"(?m)^\s*([-*+]|•)\s+", "", t)
        t = re.sub(r"(?m)^\s*\d+[.)]\s+", "", t)
        # Remove backticks (code formatting not expected in book prose)
        t = t.replace("`", "")
        # Convert scene break markers to a styled HTML break
        t = re.sub(r"(?m)^\s*(\*\s*\*\s*\*|---|\*\*\*|___)\s*$",
                    '\n<div class="scene-break">* * *</div>\n', t)
        # Collapse excessive blank lines
        t = re.sub(r"\n{3,}", "\n\n", t)
        return t.strip()

    def _escape_markdown_text(self, text: str) -> str:
        """Light escaping that preserves intentional emphasis (italic/bold) and scene breaks."""
        if not text or not isinstance(text, str):
            return ""
        return text
    
    async def _generate_format(
        self,
        fmt: PublishFormat,
        combined_md: str,
        metadata_yaml: str,
        temp_path: Path,
        config: PublishConfig,
        cover_art_url: Optional[str] = None
    ) -> Optional[Path]:
        """Generate a specific format using Pandoc."""
        
        combined_file = temp_path / "book.md"
        metadata_file = temp_path / "metadata.yaml"
        
        try:
            if fmt == PublishFormat.EPUB:
                return await self._generate_epub(combined_file, metadata_file, temp_path, config, cover_art_url)
            elif fmt == PublishFormat.PDF:
                return await self._generate_pdf(combined_file, metadata_file, temp_path, config, cover_art_url)
            elif fmt == PublishFormat.HTML:
                return await self._generate_html(combined_file, metadata_file, temp_path, config)
            else:
                self.logger.warning(f"Unsupported format: {fmt}")
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to generate {fmt}: {e}")
            return None
    
    async def _generate_epub(
        self, 
        combined_file: Path, 
        metadata_file: Path, 
        temp_path: Path,
        config: PublishConfig,
        cover_art_url: Optional[str] = None
    ) -> Path:
        """Generate EPUB using Pandoc."""
        
        output_file = temp_path / f"{self._get_book_slug(config.title)}.epub"
        
        # Download cover art if available
        cover_file = None
        if cover_art_url:
            cover_file = await self._download_cover_art(cover_art_url, temp_path)
        
        # Create CSS file for EPUB
        css_file = temp_path / "epub.css"
        css_file.write_text(self._get_epub_css(), encoding='utf-8')
        
        # Build Pandoc command
        cmd = [
            "pandoc", str(combined_file),
            "--from", "markdown+smart+raw_html",
            "--to", "epub3",
            "--output", str(output_file),
            "--metadata-file", str(metadata_file),
            "--css", str(css_file),
            "--standalone",
            "--variable", "lang=en-US",
            "--variable", "dir=ltr",
            "--variable", "epub-version=3"
        ]
        
        # Add cover art if available
        if cover_file and cover_file.exists():
            cmd.extend(["--epub-cover-image", str(cover_file)])
            self.logger.info(f"Adding cover art to EPUB: {cover_file}")
        
        if config.include_toc:
            cmd.extend(["--toc", "--toc-depth", "1"])
        
        # Run Pandoc with timeout
        result = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                result.communicate(), timeout=PANDOC_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            result.kill()
            raise RuntimeError(f"Pandoc EPUB timed out after {PANDOC_TIMEOUT_SECONDS}s")
        
        if result.returncode != 0:
            raise RuntimeError(f"Pandoc EPUB failed: {stderr.decode()}")
        
        return output_file
    
    async def _generate_pdf(
        self, 
        combined_file: Path, 
        metadata_file: Path, 
        temp_path: Path,
        config: PublishConfig,
        cover_art_url: Optional[str] = None
    ) -> Path:
        """Generate PDF using Pandoc with XeLaTeX."""
        
        output_file = temp_path / f"{self._get_book_slug(config.title)}-print.pdf"
        
        # Download cover art if available and create cover page
        cover_file = None
        if cover_art_url:
            cover_file = await self._download_cover_art(cover_art_url, temp_path)
            if cover_file and cover_file.exists():
                # Create a markdown file with cover page
                combined_with_cover = temp_path / "book_with_cover.md"
                with open(combined_file, 'r', encoding='utf-8') as f:
                    original_content = f.read()
                
                # Add cover page at the beginning (full width)
                cover_content = f"""\\newpage
\\thispagestyle{{empty}}
\\begin{{center}}
\\vspace*{{\\fill}}
\\includegraphics[width=\\textwidth]{{{cover_file}}}
\\vspace*{{\\fill}}
\\end{{center}}
\\newpage

{original_content}"""
                
                with open(combined_with_cover, 'w', encoding='utf-8') as f:
                    f.write(cover_content)
                
                combined_file = combined_with_cover
                self.logger.info(f"Added cover art to PDF content: {cover_file}")
        
        # Build Pandoc command for PDF
        cmd = [
            "pandoc", str(combined_file),
            "--from", "markdown+smart",
            "--to", "pdf",
            "--output", str(output_file),
            "--metadata-file", str(metadata_file),
            "--pdf-engine", "xelatex",
            "--number-sections",
            "--top-level-division", "chapter",
            "--standalone",
            "--variable", "fontsize=11pt",
            "--variable", "linestretch=1.15",
            "--variable", "documentclass=book",
            "--variable", "classoption=twoside,openright",
            "--variable", "lang=en-US",
            "--variable", "babel-lang=english",
            "--variable", "colorlinks=false",
            "--variable", "links-as-notes=true",
            "--variable", "indent=true"
        ]
        
        if config.include_toc:
            cmd.extend(["--toc", "--toc-depth", "3"])
        
        # Run Pandoc with timeout
        result = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                result.communicate(), timeout=PANDOC_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            result.kill()
            self.logger.warning(f"XeLaTeX timed out after {PANDOC_TIMEOUT_SECONDS}s, trying HTML->PDF fallback")
            return await self._generate_pdf_via_html(combined_file, metadata_file, temp_path, config)
        
        if result.returncode != 0:
            self.logger.warning(f"XeLaTeX failed, trying HTML->PDF fallback: {stderr.decode()}")
            return await self._generate_pdf_via_html(combined_file, metadata_file, temp_path, config)
        
        return output_file
    
    async def _generate_pdf_via_html(
        self, 
        combined_file: Path, 
        metadata_file: Path, 
        temp_path: Path,
        config: PublishConfig
    ) -> Path:
        """Generate PDF via HTML using Playwright (fallback)."""
        
        # First generate HTML
        html_file = await self._generate_html(combined_file, metadata_file, temp_path, config)
        
        # Then convert to PDF using Playwright
        try:
            from playwright.async_api import async_playwright
            
            output_file = temp_path / f"{self._get_book_slug(config.title)}-print.pdf"
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                # Load HTML content
                html_content = html_file.read_text(encoding='utf-8')
                await page.set_content(html_content)
                await page.wait_for_load_state('networkidle')
                
                # Generate PDF with print settings
                await page.pdf(
                    path=str(output_file),
                    format='A4',
                    print_background=True,
                    margin={
                        'top': '0.75in',
                        'right': '0.625in',
                        'bottom': '0.75in',
                        'left': '0.875in'
                    }
                )
                
                await browser.close()
            
            return output_file
            
        except ImportError:
            raise RuntimeError("Playwright not available for PDF fallback")

    async def _generate_kdp_kit(
        self,
        project_data: Dict[str, Any],
        combined_md: str,
        temp_path: Path,
        config: PublishConfig
    ) -> Optional[Path]:
        """Generate a KDP publishing kit PDF with copy-ready fields."""
        self._validate_kdp_config(config)
        output_file = temp_path / f"{self._get_book_slug(config.title)}-kdp-publishing-kit.pdf"
        kdp_md_file = temp_path / "kdp_publishing_kit.md"
        kdp_md_file.write_text(self._build_kdp_markdown(project_data, combined_md, config), encoding="utf-8")

        cmd = [
            "pandoc", str(kdp_md_file),
            "--from", "markdown+smart",
            "--to", "pdf",
            "--output", str(output_file),
            "--pdf-engine", "xelatex",
            "--standalone",
            "--variable", "fontsize=11pt",
            "--variable", "linestretch=1.2",
            "--variable", "documentclass=article",
            "--variable", "colorlinks=false",
            "--variable", "links-as-notes=true",
        ]

        result = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                result.communicate(), timeout=PANDOC_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            result.kill()
            self.logger.warning(f"KDP kit XeLaTeX timed out after {PANDOC_TIMEOUT_SECONDS}s, trying HTML->PDF fallback")
            return await self._generate_kdp_kit_via_html(kdp_md_file, temp_path, config)
        if result.returncode != 0:
            self.logger.warning(f"KDP kit XeLaTeX failed, trying HTML->PDF fallback: {stderr.decode()}")
            return await self._generate_kdp_kit_via_html(kdp_md_file, temp_path, config)

        return output_file

    async def _generate_kdp_kit_via_html(
        self,
        kdp_md_file: Path,
        temp_path: Path,
        config: PublishConfig
    ) -> Path:
        """Fallback KDP kit PDF via HTML + Playwright."""
        html_file = temp_path / "kdp_publishing_kit.html"
        cmd = [
            "pandoc", str(kdp_md_file),
            "--from", "markdown+smart",
            "--to", "html5",
            "--output", str(html_file),
            "--standalone",
            "--variable", "lang=en-US"
        ]
        result = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            _, stderr = await asyncio.wait_for(
                result.communicate(), timeout=PANDOC_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            result.kill()
            raise RuntimeError(f"Pandoc HTML timed out for KDP kit after {PANDOC_TIMEOUT_SECONDS}s")
        if result.returncode != 0:
            raise RuntimeError(f"Pandoc HTML failed for KDP kit: {stderr.decode()}")

        try:
            from playwright.async_api import async_playwright
            output_file = temp_path / f"{self._get_book_slug(config.title)}-kdp-publishing-kit.pdf"
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                html_content = html_file.read_text(encoding="utf-8")
                await page.set_content(html_content)
                await page.wait_for_load_state("networkidle")
                await page.pdf(
                    path=str(output_file),
                    format="A4",
                    print_background=True,
                    margin={
                        "top": "0.75in",
                        "right": "0.75in",
                        "bottom": "0.75in",
                        "left": "0.75in"
                    }
                )
                await browser.close()
            return output_file
        except ImportError:
            raise RuntimeError("Playwright not available for KDP kit PDF fallback")

    async def _auto_fill_kdp_fields(
        self,
        project_data: Dict[str, Any],
        combined_md: str,
        config: PublishConfig
    ) -> None:
        """Auto-fill required KDP fields from book content when missing."""
        if not config.include_kdp_kit:
            return

        missing_required = []
        if not config.kdp_description or not config.kdp_description.strip():
            missing_required.append("description")
        if not config.kdp_keywords or len([k for k in config.kdp_keywords if k.strip()]) < 3:
            missing_required.append("keywords")
        if not config.kdp_categories or len([c for c in config.kdp_categories if c.strip()]) < 1:
            missing_required.append("categories")
        if not config.kdp_language or not config.kdp_language.strip():
            missing_required.append("language")
        if not config.kdp_primary_marketplace or not config.kdp_primary_marketplace.strip():
            missing_required.append("primary_marketplace")

        if not missing_required:
            return

        vector_context = ""
        try:
            project = project_data.get("project", {}) if isinstance(project_data, dict) else {}
            metadata = project.get("metadata", {}) if isinstance(project, dict) else {}
            owner_id = metadata.get("owner_id")
            project_id = metadata.get("project_id") or project.get("id") or project_data.get("project_id")
            if project_id and owner_id:
                vector_service = VectorStoreService()
                vector_context = await vector_service.retrieve_kdp_context(project_id, owner_id)
        except Exception as vector_err:
            self.logger.warning(f"KDP vector context retrieval failed: {vector_err}")

        source_material = self._build_kdp_source_material(project_data, combined_md, config, vector_context)
        llm_payload = await self._generate_kdp_payload(source_material, config)

        if not config.kdp_description:
            config.kdp_description = llm_payload.get("description")
        if not config.kdp_keywords:
            config.kdp_keywords = llm_payload.get("keywords", [])
        if not config.kdp_categories:
            config.kdp_categories = llm_payload.get("categories", [])
        if not config.kdp_language:
            config.kdp_language = llm_payload.get("language")
        if not config.kdp_primary_marketplace:
            config.kdp_primary_marketplace = llm_payload.get("primary_marketplace")

        if not config.kdp_subtitle:
            config.kdp_subtitle = llm_payload.get("subtitle")
        if not config.kdp_series_name:
            config.kdp_series_name = llm_payload.get("series_name")
        if not config.kdp_series_number:
            config.kdp_series_number = llm_payload.get("series_number")
        if not config.kdp_author_bio:
            config.kdp_author_bio = llm_payload.get("author_bio")

        self._validate_kdp_config(config)

    async def _generate_kdp_payload(self, source_material: str, config: PublishConfig) -> Dict[str, Any]:
        """Use the LLM to generate KDP fields from book content."""
        try:
            from backend.auto_complete.llm_orchestrator import LLMOrchestrator
        except Exception:
            from auto_complete.llm_orchestrator import LLMOrchestrator  # type: ignore

        orchestrator = LLMOrchestrator()
        system_prompt = (
            "You are a KDP publishing strategist. Use ONLY the provided source material. "
            "Do not invent character names, places, plot points, or claims not in the source. "
            "Return a single JSON object and nothing else."
        )
        user_prompt = (
            "Generate KDP-ready fields using the source material below.\n\n"
            "Requirements:\n"
            "- description: 150-220 words, persuasive, SEO-friendly, based only on source\n"
            "- keywords: 7 items max, each 2-4 words, no duplicates\n"
            "- categories: 2-3 BISAC-style categories\n"
            "- language: full language name\n"
            "- primary_marketplace: Amazon marketplace (ex: Amazon.com)\n"
            "- subtitle, series_name, series_number, author_bio are optional (omit or empty if unknown)\n\n"
            "Return JSON with keys: description, keywords, categories, language, primary_marketplace, "
            "subtitle, series_name, series_number, author_bio.\n\n"
            f"BOOK TITLE: {config.title}\n"
            f"AUTHOR: {config.author}\n\n"
            f"SOURCE MATERIAL:\n{source_material}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response = await orchestrator._make_api_call(messages=messages, temperature=0.2, max_tokens=900)
        content = response.choices[0].message.content if hasattr(response, "choices") else ""
        payload = self._parse_kdp_json(content)

        return payload

    def _build_kdp_source_material(
        self,
        project_data: Dict[str, Any],
        combined_md: str,
        config: PublishConfig,
        vector_context: str = ""
    ) -> str:
        """Compile source material for KDP field generation."""
        project = project_data.get("project", {}) if isinstance(project_data, dict) else {}
        settings = project.get("settings", {}) if isinstance(project, dict) else {}
        metadata = project.get("metadata", {}) if isinstance(project, dict) else {}
        genre = settings.get("genre") or project.get("genre") or ""

        book_bible_content = ""
        if isinstance(project, dict):
            if "files" in project and isinstance(project.get("files"), dict) and "book-bible.md" in project.get("files"):
                book_bible_content = project.get("files", {}).get("book-bible.md", "")
            elif "book_bible" in project:
                bb_entry = project.get("book_bible")
                if isinstance(bb_entry, dict):
                    book_bible_content = bb_entry.get("content", "")
                elif isinstance(bb_entry, str):
                    book_bible_content = bb_entry

        plain_text = self._plain_text_from_markdown(combined_md)
        book_excerpt = self._truncate_words(plain_text, 3000)

        sections = [
            f"Title: {config.title}",
            f"Author: {config.author}",
        ]
        if genre:
            sections.append(f"Genre: {genre}")
        if metadata.get("title") and metadata.get("title") != config.title:
            sections.append(f"Project Title: {metadata.get('title')}")
        if book_bible_content:
            sections.append("Book Bible:\n" + self._truncate_words(book_bible_content, 1200))
        if book_excerpt:
            sections.append("Book Excerpt:\n" + book_excerpt)
        if vector_context:
            sections.append("Vector Memory Context:\n" + self._truncate_words(vector_context, 800))

        return "\n\n".join(sections).strip()

    def _parse_kdp_json(self, text: str) -> Dict[str, Any]:
        """Extract JSON from LLM response."""
        if not text:
            raise RuntimeError("KDP field generation failed: empty response")
        json_match = re.search(r"\{[\s\S]*\}", text)
        if not json_match:
            raise RuntimeError("KDP field generation failed: JSON not found in response")
        try:
            payload = json.loads(json_match.group(0))
        except Exception as exc:
            raise RuntimeError(f"KDP field generation failed: invalid JSON ({exc})")

        keywords = [k.strip() for k in payload.get("keywords", []) if isinstance(k, str) and k.strip()]
        categories = [c.strip() for c in payload.get("categories", []) if isinstance(c, str) and c.strip()]

        payload["keywords"] = list(dict.fromkeys(keywords))[:7]
        payload["categories"] = list(dict.fromkeys(categories))[:3]
        payload["description"] = (payload.get("description") or "").strip()
        payload["language"] = (payload.get("language") or "").strip()
        payload["primary_marketplace"] = (payload.get("primary_marketplace") or "").strip()
        payload["subtitle"] = (payload.get("subtitle") or "").strip()
        payload["series_name"] = (payload.get("series_name") or "").strip()
        payload["series_number"] = (payload.get("series_number") or "").strip()
        payload["author_bio"] = (payload.get("author_bio") or "").strip()

        return payload

    def _plain_text_from_markdown(self, text: str) -> str:
        """Convert markdown/HTML to plain text for LLM context."""
        if not text:
            return ""
        cleaned = re.sub(r"^---[\s\S]*?---\s*", "", text)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = re.sub(r"\[(.*?)\]\([^\)]*\)", r"\1", cleaned)
        cleaned = re.sub(r"[#*_>`~]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    def _truncate_words(self, text: str, max_words: int) -> str:
        """Return at most max_words words."""
        if not text:
            return ""
        words = text.split()
        if len(words) <= max_words:
            return text.strip()
        return " ".join(words[:max_words]).strip()

    def _validate_kdp_config(self, config: PublishConfig) -> None:
        """Validate KDP kit fields when requested."""
        if not config.include_kdp_kit:
            return
        missing = []
        if not config.kdp_description or not config.kdp_description.strip():
            missing.append("KDP description")
        if not config.kdp_keywords or len([k for k in config.kdp_keywords if k.strip()]) < 3:
            missing.append("at least 3 KDP keywords")
        if not config.kdp_categories or len([c for c in config.kdp_categories if c.strip()]) < 1:
            missing.append("at least 1 KDP category")
        if not config.kdp_language or not config.kdp_language.strip():
            missing.append("KDP language")
        if not config.kdp_primary_marketplace or not config.kdp_primary_marketplace.strip():
            missing.append("KDP primary marketplace")
        if missing:
            raise ValueError("Missing required KDP kit fields: " + ", ".join(missing))

    def _build_kdp_markdown(
        self,
        project_data: Dict[str, Any],
        combined_md: str,
        config: PublishConfig
    ) -> str:
        """Build a copy-ready KDP publishing kit in Markdown."""
        word_count = self._count_words(combined_md)
        page_estimate = max(1, word_count // 250)
        cover_art_url = None
        if config.use_existing_cover:
            cover_art_url = project_data.get("cover_art_url")

        keywords = [k.strip() for k in (config.kdp_keywords or []) if k.strip()]
        categories = [c.strip() for c in (config.kdp_categories or []) if c.strip()]

        series_line = config.kdp_series_name or ""
        if config.kdp_series_number:
            series_line = f"{series_line} (Book {config.kdp_series_number})" if series_line else f"Book {config.kdp_series_number}"

        lines = [
            f"# KDP Publishing Kit: {config.title}",
            "",
            "## Ready-to-Copy KDP Fields",
            "",
            f"**Book Title:** {config.title}",
        ]
        if config.kdp_subtitle:
            lines.append(f"**Subtitle:** {config.kdp_subtitle}")
        if series_line:
            lines.append(f"**Series:** {series_line}")
        lines.append(f"**Author:** {config.author}")
        if config.kdp_contributors:
            lines.append(f"**Contributors:** {config.kdp_contributors}")
        if config.kdp_edition:
            lines.append(f"**Edition:** {config.kdp_edition}")
        lines.append(f"**Language:** {config.kdp_language}")
        lines.append(f"**Primary Marketplace:** {config.kdp_primary_marketplace}")
        if config.kdp_imprint or config.publisher:
            lines.append(f"**Imprint:** {config.kdp_imprint or config.publisher}")
        if config.isbn:
            lines.append(f"**ISBN:** {config.isbn}")
        if config.rights:
            lines.append(f"**Publishing Rights:** {config.rights}")

        lines.extend([
            "",
            "### Book Description",
            config.kdp_description.strip(),
            "",
            "### Keywords",
        ])
        for keyword in keywords:
            lines.append(f"- {keyword}")
        lines.extend([
            "",
            "### Categories (BISAC)",
        ])
        for category in categories:
            lines.append(f"- {category}")
        if config.kdp_author_bio:
            lines.extend([
                "",
                "### Author Bio",
                config.kdp_author_bio.strip()
            ])
        if config.kdp_pricing:
            lines.extend([
                "",
                "### Pricing Notes",
                config.kdp_pricing.strip()
            ])

        lines.extend([
            "",
            "## File Package Checklist",
            f"- EPUB file (for Kindle ebook): generated by the publishing system",
            f"- Print-ready PDF (for paperback/hardcover): generated by the publishing system",
            f"- Cover art: {cover_art_url or ''}",
            "",
            "## KDP Publishing Steps (Quick Guide)",
            "1. Sign in to KDP and choose **Create** → **Kindle eBook** or **Paperback**.",
            "2. In **Book Details**, copy the fields from the **Ready-to-Copy KDP Fields** section above.",
            "3. In **Keywords** and **Categories**, paste the lists exactly as provided.",
            "4. In **Content**, upload the EPUB (ebook) or PDF (print) generated by this system.",
            "5. Upload cover art if required for your chosen format.",
            "6. Review the previewer to ensure formatting and navigation look correct.",
            "7. Set pricing and territories, then publish.",
            "",
            "## Quick Book Stats",
            f"- Total word count: {word_count}",
            f"- Estimated pages: {page_estimate}",
        ])

        return "\n".join(lines).strip() + "\n"
    
    async def _generate_html(
        self, 
        combined_file: Path, 
        metadata_file: Path, 
        temp_path: Path,
        config: PublishConfig
    ) -> Path:
        """Generate HTML using Pandoc."""
        
        output_file = temp_path / f"{self._get_book_slug(config.title)}.html"
        
        # Create CSS file for HTML
        css_file = temp_path / "html.css"
        css_file.write_text(self._get_html_css(), encoding='utf-8')
        
        # Build Pandoc command
        cmd = [
            "pandoc", str(combined_file),
            "--from", "markdown+smart",
            "--to", "html5",
            "--output", str(output_file),
            "--metadata-file", str(metadata_file),
            "--css", str(css_file),
            "--section-divs",
            "--standalone",
            "--highlight-style", "breezedark",
            "--variable", "toc-title=Table of Contents",
            "--variable", "lang=en-US",
            "--variable", "dir=ltr",
            "--variable", "html5=true"
        ]
        
        if config.include_toc:
            cmd.extend(["--toc", "--toc-depth", "3"])
        
        # Run Pandoc with timeout
        result = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                result.communicate(), timeout=PANDOC_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            result.kill()
            raise RuntimeError(f"Pandoc HTML timed out after {PANDOC_TIMEOUT_SECONDS}s")
        
        if result.returncode != 0:
            raise RuntimeError(f"Pandoc HTML failed: {stderr.decode()}")
        
        return output_file
    
    async def _upload_files(
        self, 
        project_id: str, 
        job_id: str, 
        output_files: Dict[str, Path]
    ) -> Dict[str, str]:
        """Upload generated files to storage and return download URLs."""
        
        download_urls = {}
        
        for fmt, file_path in output_files.items():
            if not file_path.exists():
                continue
                
            try:
                # Generate storage path
                storage_path = f"projects/{project_id}/publishing/{job_id}/book.{fmt}"
                
                # Upload file
                filename = f"book.{fmt}"
                if fmt == "kdp_kit":
                    filename = "kdp-publishing-kit.pdf"
                download_url = await self.upload_file_to_storage(
                    file_path=file_path,
                    project_id=project_id,
                    filename=filename
                )
                
                download_urls[fmt] = download_url
                self.logger.info(f"Uploaded {fmt} to {download_url}")
                
            except Exception as e:
                self.logger.error(f"Failed to upload {fmt}: {e}")
        
        return download_urls
    
    def _get_book_slug(self, title: str) -> str:
        """Generate a URL-safe slug from book title."""
        slug = re.sub(r'[^a-zA-Z0-9\s]', '', title).lower().replace(' ', '-')
        slug = re.sub(r'-+', '-', slug).strip('-')
        return slug or "untitled-book"
    
    def _count_words(self, text: str) -> int:
        """Count words in text."""
        # Remove markdown formatting and count words
        clean_text = re.sub(r'[#*`_\[\]()]', '', text)
        words = clean_text.split()
        return len(words)
    
    def _get_content_type(self, fmt: str) -> str:
        """Get MIME type for format."""
        content_types = {
            'epub': 'application/epub+zip',
            'pdf': 'application/pdf',
            'html': 'text/html',
            'kdp_kit': 'application/pdf'
        }
        return content_types.get(fmt, 'application/octet-stream')
    
    def _get_epub_css(self) -> str:
        """Professional book-interior EPUB stylesheet."""
        return """
@page {
    margin: 1in 0.75in;
}

body {
    font-family: "Georgia", "Palatino Linotype", "Book Antiqua", Palatino, serif;
    font-size: 1em;
    line-height: 1.7;
    margin: 0;
    padding: 0 1em;
    text-align: justify;
    color: #1a1a1a;
    orphans: 2;
    widows: 2;
    -webkit-hyphens: auto;
    hyphens: auto;
}

h1, h2, h3, h4, h5, h6 {
    font-family: "Georgia", "Palatino Linotype", serif;
    color: #111;
    text-align: center;
    text-indent: 0;
    hyphens: none;
    -webkit-hyphens: none;
    line-height: 1.3;
    page-break-after: avoid;
}

h1 {
    font-size: 1.8em;
    font-weight: normal;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    page-break-before: always;
    margin-top: 30%;
    margin-bottom: 1.5em;
    border-bottom: none;
}

h2 {
    font-size: 1.3em;
    font-weight: normal;
    font-style: italic;
    margin-top: 2em;
    margin-bottom: 1em;
}

p {
    margin: 0;
    text-indent: 1.5em;
}

/* First paragraph after headings: no indent, optional drop-cap styling */
h1 + p, h2 + p, h3 + p,
.scene-break + p,
div.scene-break + p {
    text-indent: 0;
}

h1 + p::first-letter {
    font-size: 3.2em;
    float: left;
    line-height: 0.8;
    padding-right: 0.08em;
    margin-top: 0.05em;
    font-weight: bold;
}

/* Scene breaks */
.scene-break {
    text-align: center;
    margin: 1.8em 0;
    font-size: 1.1em;
    letter-spacing: 0.5em;
    text-indent: 0;
    color: #666;
}

hr {
    border: none;
    text-align: center;
    margin: 1.8em 0;
}

hr::after {
    content: "* * *";
    letter-spacing: 0.5em;
    color: #666;
}

blockquote {
    margin: 1.2em 1.5em;
    padding-left: 0.8em;
    border-left: 2px solid #999;
    font-style: italic;
    color: #333;
}

em, i {
    font-style: italic;
}

strong, b {
    font-weight: bold;
}

/* Front/back matter styling */
.dedication-page {
    text-align: center;
    font-style: italic;
    margin-top: 30%;
    page-break-before: always;
}

.dedication-page h1 {
    font-size: 1.2em;
    text-transform: none;
    letter-spacing: normal;
    margin-top: 0;
}

.about-the-author-page h1,
.acknowledgments-page h1 {
    font-size: 1.4em;
    margin-top: 15%;
}

/* Images */
img {
    max-width: 100%;
    height: auto;
}

/* Table of contents */
nav#toc ol {
    list-style-type: none;
    padding-left: 0;
}

nav#toc a {
    text-decoration: none;
    color: #1a1a1a;
}
"""
    
    def _get_html_css(self) -> str:
        """Professional HTML book stylesheet with responsive design."""
        return """
:root {
    --bg: #fafaf9;
    --text: #1a1a1a;
    --text-muted: #6b7280;
    --accent: #4f46e5;
    --border: #e5e7eb;
}

*, *::before, *::after { box-sizing: border-box; }

body {
    font-family: "Georgia", "Palatino Linotype", "Book Antiqua", Palatino, serif;
    font-size: 18px;
    line-height: 1.8;
    color: var(--text);
    background-color: var(--bg);
    max-width: 38em;
    margin: 0 auto;
    padding: 2rem 1.5rem;
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
}

h1, h2, h3, h4, h5, h6 {
    font-family: "Georgia", "Palatino Linotype", serif;
    color: var(--text);
    text-align: center;
    line-height: 1.3;
    font-weight: normal;
    page-break-after: avoid;
}

h1 {
    font-size: 2rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    margin-top: 4rem;
    margin-bottom: 2rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border);
}

h2 {
    font-size: 1.4rem;
    font-style: italic;
    margin-top: 3rem;
    margin-bottom: 1rem;
}

p {
    margin: 0;
    text-indent: 1.5em;
    text-align: justify;
    orphans: 2;
    widows: 2;
}

h1 + p, h2 + p, h3 + p,
.scene-break + p,
div.scene-break + p {
    text-indent: 0;
}

h1 + p::first-letter {
    font-size: 3.2em;
    float: left;
    line-height: 0.8;
    padding-right: 0.08em;
    margin-top: 0.05em;
    font-weight: bold;
    color: var(--text);
}

.scene-break {
    text-align: center;
    margin: 2em 0;
    font-size: 1.1em;
    letter-spacing: 0.5em;
    text-indent: 0;
    color: var(--text-muted);
}

blockquote {
    margin: 1.5rem 0;
    padding: 0.5rem 1.5rem;
    border-left: 3px solid var(--border);
    font-style: italic;
    color: var(--text-muted);
}

em, i { font-style: italic; }
strong, b { font-weight: bold; }

.dedication-page {
    text-align: center;
    font-style: italic;
    margin-top: 6rem;
}

img { max-width: 100%; height: auto; }

@media (max-width: 640px) {
    body { font-size: 16px; padding: 1rem; }
    h1 { font-size: 1.5rem; margin-top: 2.5rem; }
}

@media (prefers-color-scheme: dark) {
    :root {
        --bg: #1a1a2e;
        --text: #d4d4d8;
        --text-muted: #a1a1aa;
        --accent: #818cf8;
        --border: #2d2d4a;
    }
}

@media print {
    body {
        font-size: 12pt;
        line-height: 1.5;
        color: black;
        background: white;
        max-width: none;
        margin: 0;
        padding: 0.75in 1in;
    }
    h1 { page-break-before: always; }
}
""" 