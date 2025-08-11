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
        get_project, get_project_chapters
    )
    from backend.services.firestore_service import get_firestore_client
except ImportError:
    try:
        # Try without backend prefix
        from database_integration import (
            get_project, get_project_chapters
        )
        from services.firestore_service import get_firestore_client
    except ImportError:
        # Final fallback - import with full path
        sys.path.insert(0, '/app/backend')
        from database_integration import (
            get_project, get_project_chapters
        )
        from services.firestore_service import get_firestore_client

# Import Firebase Storage for file uploads
try:
    from firebase_admin import storage
except ImportError:
    storage = None

logger = logging.getLogger(__name__)

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
        """Download cover art image to temp directory."""
        try:
            import aiohttp
            cover_file = temp_path / "cover.jpg"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(cover_art_url) as response:
                    if response.status == 200:
                        with open(cover_file, 'wb') as f:
                            f.write(await response.read())
                        self.logger.info(f"Downloaded cover art to {cover_file}")
                        return cover_file
                    else:
                        self.logger.warning(f"Failed to download cover art: HTTP {response.status}")
                        return None
                        
        except Exception as e:
            self.logger.error(f"Error downloading cover art: {e}")
            return None

    async def upload_file_to_storage(self, file_path: Path, project_id: str, filename: str) -> str:
        """Upload a file to Firebase Storage and return the public URL."""
        if not self.firebase_bucket:
            # Return local file URL as fallback
            self.logger.warning("Firebase Storage not available, using local file")
            return f"/local_storage/{project_id}/{filename}"
        
        try:
            # Create blob path
            blob_path = f"published_books/{project_id}/{filename}"
            blob = self.firebase_bucket.blob(blob_path)
            
            # Upload file
            with open(file_path, 'rb') as file_data:
                blob.upload_from_file(file_data, content_type=self._get_content_type(filename))
            
            # Make blob publicly accessible
            blob.make_public()
            
            public_url = blob.public_url
            self.logger.info(f"File uploaded to Firebase Storage: {public_url}")
            return public_url
            
        except Exception as e:
            self.logger.error(f"Failed to upload {filename} to Firebase Storage: {e}")
            # Return local file URL as fallback
            return f"/local_storage/{project_id}/{filename}"
        
    async def publish_book(
        self,
        project_id: str,
        config: PublishConfig,
        progress_callback: Optional[Callable[[str, float], None]] = None
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
        job_id = f"publish_{project_id}_{int(datetime.now().timestamp())}"
        
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
                
                # Step 2: Build combined markdown
                update_progress("Building book content", 0.2)
                combined_md, metadata_yaml = await self._build_combined_content(
                    project_data, config, temp_path
                )
                
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
                    
                    # Get cover art URL from project data
                    cover_art_url = None
                    if 'cover_art' in project_data and isinstance(project_data['cover_art'], dict):
                        cover_art_url = project_data['cover_art'].get('image_url')
                    elif 'cover_art_url' in project_data:
                        # Fallback for legacy structure
                        cover_art_url = project_data.get('cover_art_url')
                    
                    output_file = await self._generate_format(
                        fmt, combined_md, metadata_yaml, temp_path, config, cover_art_url
                    )
                    if output_file:
                        output_files[fmt.value] = output_file
                    
                    update_progress(f"Completed {fmt.upper()}", end_progress)
                
                # Step 4: Upload files to storage
                update_progress("Uploading files", 0.85)
                download_urls = await self._upload_files(project_id, job_id, output_files)
                
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
                    created_at=datetime.now(timezone.utc),
                    completed_at=datetime.now(timezone.utc),
                    file_sizes=file_sizes,
                    word_count=word_count,
                    page_count=max(1, word_count // 250)  # Estimate 250 words per page
                )
                
                update_progress("Publication completed", 1.0)
                return result
                
        except Exception as e:
            self.logger.error(f"Publishing failed for {project_id}: {e}")
            return PublishResult(
                job_id=job_id,
                project_id=project_id,
                status=PublishJobStatus.FAILED,
                config=config,
                created_at=datetime.now(timezone.utc),
                error_message=str(e)
            )
    
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
            
            # Get cover art if exists
            cover_art_url = None
            if 'cover_art' in project_data:
                cover_art_url = project_data['cover_art'].get('image_url')
            
            return {
                'project': project_data,
                'chapters': chapters,
                'cover_art_url': cover_art_url
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
        
        # Add chapters
        for chapter in chapters:
            chapter_num = chapter.get('chapter_number', 0)
            chapter_title = chapter.get('title', f'Chapter {chapter_num}')
            content = chapter.get('content', '')
            
            # Add page break and chapter
            combined_lines.extend([
                "\\newpage",
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
            content.strip(),
            "",
            "</div>",
            "",
            "\\newpage",
            ""
        ])
    
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
            "--epub-subdirectory", "EPUB",
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
            cmd.extend(["--toc", "--toc-depth", "3"])
        
        # Run Pandoc
        result = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await result.communicate()
        
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
                
                # Add cover page at the beginning
                cover_content = f"""\\newpage
\\thispagestyle{{empty}}
\\begin{{center}}
\\vspace*{{\\fill}}
\\includegraphics[width=0.6\\textwidth]{{{cover_file}}}
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
        
        # Run Pandoc
        result = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await result.communicate()
        
        if result.returncode != 0:
            # If XeLaTeX fails, try fallback to HTML->PDF
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
        
        # Run Pandoc
        result = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await result.communicate()
        
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
            'html': 'text/html'
        }
        return content_types.get(fmt, 'application/octet-stream')
    
    def _get_epub_css(self) -> str:
        """Get CSS for EPUB formatting."""
        return """
/* EPUB Stylesheet */
body {
    font-family: "Georgia", "Times New Roman", serif;
    font-size: 1.1em;
    line-height: 1.6;
    margin: 1em;
    text-align: left;
}

h1, h2, h3, h4, h5, h6 {
    font-family: "Helvetica Neue", "Arial", sans-serif;
    color: #333;
    margin-top: 1.5em;
    margin-bottom: 0.5em;
    line-height: 1.3;
}

h1 {
    font-size: 2em;
    text-align: center;
    page-break-before: always;
    margin-top: 2em;
    margin-bottom: 1em;
}

p {
    margin: 0.8em 0;
    text-indent: 1.2em;
}

blockquote {
    margin: 1em 2em;
    font-style: italic;
    border-left: 3px solid #ccc;
    padding-left: 1em;
}

.chapter {
    page-break-before: always;
}
"""
    
    def _get_html_css(self) -> str:
        """Get CSS for HTML formatting."""
        return """
/* HTML Book Stylesheet */
body {
    font-family: "Georgia", "Times New Roman", serif;
    font-size: 18px;
    line-height: 1.7;
    color: #333;
    background-color: #fdfdfd;
    max-width: 800px;
    margin: 0 auto;
    padding: 2rem;
}

h1, h2, h3, h4, h5, h6 {
    font-family: "Helvetica Neue", "Arial", sans-serif;
    color: #2c3e50;
    margin-top: 2.5rem;
    margin-bottom: 1rem;
    line-height: 1.3;
    font-weight: 600;
}

h1 {
    font-size: 2.5rem;
    text-align: center;
    border-bottom: 1px solid #333;
    padding-bottom: 0.5rem;
    margin-bottom: 2rem;
}

p {
    margin: 1.2rem 0;
    text-align: justify;
}

blockquote {
    margin: 2rem 0;
    padding: 1rem 2rem;
    background-color: #f8f9fa;
    border-left: 2px solid #333;
    font-style: italic;
}

@media print {
    body {
        font-size: 12pt;
        line-height: 1.4;
        color: black;
        background: white;
        max-width: none;
        margin: 0;
        padding: 1in;
    }
    
    h1 {
        page-break-before: always;
    }
}
""" 