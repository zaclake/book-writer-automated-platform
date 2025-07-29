#!/usr/bin/env python3
"""
Tests for Publishing Service
"""

import pytest
import tempfile
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone

from backend.services.publishing_service import PublishingService
from backend.models.firestore_models import (
    PublishConfig, PublishFormat, PublishJobStatus
)

@pytest.fixture
def publishing_service():
    """Create a publishing service instance."""
    return PublishingService()

@pytest.fixture
def sample_config():
    """Create a sample publishing configuration."""
    return PublishConfig(
        title="Test Book",
        author="Test Author",
        formats=[PublishFormat.EPUB, PublishFormat.PDF],
        dedication="To my test readers",
        acknowledgments="Thanks to the testing team"
    )

@pytest.fixture
def mock_project_data():
    """Create mock project data."""
    return {
        'project': {
            'metadata': {
                'title': 'Test Book',
                'author': 'Test Author',
                'owner_id': 'user123'
            }
        },
        'chapters': [
            {
                'chapter_number': 1,
                'title': 'Chapter 1: The Beginning',
                'content': 'This is the first chapter content. It has some text to test word counting.'
            },
            {
                'chapter_number': 2,
                'title': 'Chapter 2: The Middle',
                'content': 'This is the second chapter content. It continues the story.'
            }
        ],
        'cover_art_url': None
    }

class TestPublishingService:
    """Test cases for PublishingService."""
    
    @pytest.mark.asyncio
    async def test_fetch_project_data(self, publishing_service, mock_project_data):
        """Test fetching project data."""
        with patch('backend.services.publishing_service.get_project') as mock_get_project, \
             patch('backend.services.publishing_service.get_project_chapters') as mock_get_chapters:
            
            mock_get_project.return_value = mock_project_data['project']
            mock_get_chapters.return_value = mock_project_data['chapters']
            
            result = await publishing_service._fetch_project_data('test-project')
            
            assert result['project'] == mock_project_data['project']
            assert result['chapters'] == mock_project_data['chapters']
            assert result['cover_art_url'] is None
    
    def test_build_combined_content(self, publishing_service, sample_config, mock_project_data):
        """Test building combined markdown content."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            combined_md, metadata_yaml = asyncio.run(
                publishing_service._build_combined_content(
                    mock_project_data, sample_config, temp_path
                )
            )
            
            # Check that content contains expected elements
            assert "Test Book" in combined_md
            assert "Test Author" in combined_md
            assert "Chapter 1: The Beginning" in combined_md
            assert "Chapter 2: The Middle" in combined_md
            assert "To my test readers" in combined_md  # dedication
            assert "Thanks to the testing team" in combined_md  # acknowledgments
            
            # Check metadata YAML
            assert "title: Test Book" in metadata_yaml
            assert "author: Test Author" in metadata_yaml
    
    def test_add_optional_section(self, publishing_service):
        """Test adding optional sections."""
        lines = []
        
        # Test adding a section
        publishing_service._add_optional_section(
            lines, "dedication", "To my readers", "center"
        )
        
        combined = "\n".join(lines)
        assert "Dedication" in combined
        assert "To my readers" in combined
        assert 'text-align: center' in combined
        
        # Test empty content (should not add anything)
        lines_before = len(lines)
        publishing_service._add_optional_section(lines, "empty", "", "left")
        assert len(lines) == lines_before
    
    def test_get_book_slug(self, publishing_service):
        """Test book slug generation."""
        assert publishing_service._get_book_slug("Test Book") == "test-book"
        assert publishing_service._get_book_slug("Book with Special!@# Characters") == "book-with-special-characters"
        assert publishing_service._get_book_slug("") == "untitled-book"
        assert publishing_service._get_book_slug("Multiple   Spaces") == "multiple-spaces"
    
    def test_count_words(self, publishing_service):
        """Test word counting."""
        text = "This is a test with **bold** and *italic* text."
        assert publishing_service._count_words(text) == 10
        
        text_with_markdown = "# Header\n\nThis is a paragraph with [link](url) and `code`."
        word_count = publishing_service._count_words(text_with_markdown)
        assert word_count == 9  # Should strip markdown formatting
    
    def test_get_content_type(self, publishing_service):
        """Test content type mapping."""
        assert publishing_service._get_content_type("epub") == "application/epub+zip"
        assert publishing_service._get_content_type("pdf") == "application/pdf"
        assert publishing_service._get_content_type("html") == "text/html"
        assert publishing_service._get_content_type("unknown") == "application/octet-stream"
    
    @pytest.mark.asyncio
    async def test_generate_epub_mock_pandoc(self, publishing_service, sample_config):
        """Test EPUB generation with mocked Pandoc."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create test files
            combined_file = temp_path / "book.md"
            combined_file.write_text("# Test Book\n\nContent here")
            
            metadata_file = temp_path / "metadata.yaml"
            metadata_file.write_text("title: Test Book")
            
            # Mock successful Pandoc execution
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate.return_value = (b"", b"")
            
            with patch('asyncio.create_subprocess_exec', return_value=mock_process):
                result = await publishing_service._generate_epub(
                    combined_file, metadata_file, temp_path, sample_config
                )
                
                assert result is not None
                assert result.name.endswith('.epub')
    
    @pytest.mark.asyncio
    async def test_generate_pdf_fallback(self, publishing_service, sample_config):
        """Test PDF generation with fallback to HTML."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create test files
            combined_file = temp_path / "book.md"
            combined_file.write_text("# Test Book\n\nContent here")
            
            metadata_file = temp_path / "metadata.yaml"
            metadata_file.write_text("title: Test Book")
            
            # Mock failed XeLaTeX, successful HTML generation
            mock_process_fail = AsyncMock()
            mock_process_fail.returncode = 1
            mock_process_fail.communicate.return_value = (b"", b"XeLaTeX error")
            
            mock_process_success = AsyncMock()
            mock_process_success.returncode = 0
            mock_process_success.communicate.return_value = (b"", b"")
            
            with patch('asyncio.create_subprocess_exec', side_effect=[mock_process_fail, mock_process_success]):
                with patch.object(publishing_service, '_generate_pdf_via_html') as mock_html_pdf:
                    mock_html_pdf.return_value = temp_path / "test-book-print.pdf"
                    
                    result = await publishing_service._generate_pdf(
                        combined_file, metadata_file, temp_path, sample_config
                    )
                    
                    assert result is not None
                    mock_html_pdf.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_upload_files(self, publishing_service):
        """Test file upload functionality."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create test files
            epub_file = temp_path / "book.epub"
            epub_file.write_text("fake epub content")
            
            pdf_file = temp_path / "book.pdf"
            pdf_file.write_text("fake pdf content")
            
            output_files = {
                "epub": epub_file,
                "pdf": pdf_file
            }
            
            # Mock upload function
            with patch('backend.services.publishing_service.upload_file_to_storage') as mock_upload:
                mock_upload.return_value = "https://storage.example.com/file.epub"
                
                result = await publishing_service._upload_files(
                    "project123", "job456", output_files
                )
                
                assert "epub" in result
                assert "pdf" in result
                assert result["epub"] == "https://storage.example.com/file.epub"
                assert mock_upload.call_count == 2
    
    @pytest.mark.asyncio
    async def test_publish_book_success(self, publishing_service, sample_config, mock_project_data):
        """Test successful book publishing."""
        progress_calls = []
        
        def progress_callback(status: str, progress: float):
            progress_calls.append((status, progress))
        
        with patch.object(publishing_service, '_fetch_project_data', return_value=mock_project_data), \
             patch.object(publishing_service, '_generate_format') as mock_generate, \
             patch.object(publishing_service, '_upload_files', return_value={"epub": "url1", "pdf": "url2"}):
            
            # Mock successful format generation
            mock_generate.return_value = Path("/tmp/book.epub")
            
            result = await publishing_service.publish_book(
                "project123", sample_config, progress_callback
            )
            
            assert result.status == PublishJobStatus.COMPLETED
            assert result.epub_url == "url1"
            assert result.pdf_url == "url2"
            assert result.word_count > 0
            assert len(progress_calls) > 0
    
    @pytest.mark.asyncio
    async def test_publish_book_failure(self, publishing_service, sample_config):
        """Test book publishing failure handling."""
        with patch.object(publishing_service, '_fetch_project_data', side_effect=Exception("Database error")):
            
            result = await publishing_service.publish_book(
                "project123", sample_config
            )
            
            assert result.status == PublishJobStatus.FAILED
            assert "Database error" in result.error_message
            assert result.epub_url is None
            assert result.pdf_url is None

@pytest.mark.asyncio
async def test_css_generation():
    """Test CSS generation methods."""
    service = PublishingService()
    
    epub_css = service._get_epub_css()
    assert "font-family" in epub_css
    assert "Georgia" in epub_css
    
    html_css = service._get_html_css()
    assert "font-family" in html_css
    assert "@media print" in html_css 