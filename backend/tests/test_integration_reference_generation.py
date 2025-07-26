"""
Integration tests for reference generation endpoints.
Tests the full end-to-end flow of reference content generation.
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
from backend.main import app
from backend.utils.reference_content_generator import ReferenceContentGenerator


@pytest.fixture
def test_client():
    """Create test client for FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_auth_token():
    """Mock authentication token verification."""
    return {
        "sub": "test_user_123",
        "email": "test@example.com"
    }


@pytest.fixture
def sample_book_bible():
    """Sample book bible content for testing."""
    return """# Test Book Bible

## 📝 **GENERAL BOOK DESCRIPTION**

This is a test book about adventures in testing. It features comprehensive characters,
an intricate plot, and a well-developed world that serves as the perfect testing ground.

## 👥 **CHARACTER DEVELOPMENT**

### Protagonist(s)
**Character Name:** Alice Tester
- **Age:** 28
- **Occupation:** Quality Assurance Engineer
- **External Goal:** Debug the mysterious software bug
- **Internal Goal:** Overcome her fear of deployment failures

### Antagonist(s)
**Character Name:** The Bug
- **Motivation:** Crash all production systems
- **Method:** Subtle logic errors and race conditions

## 🌍 **WORLD BUILDING**

### Setting Foundation
- **Time Period:** Present day (2024)
- **Location:** Tech startup office in Silicon Valley
- **Technology Level:** Cutting-edge development tools and cloud infrastructure

## 📊 **PLOT STRUCTURE**

### Overall Arc
Alice discovers a critical bug in the system just before a major product launch.
She must trace through complex code paths while dealing with pressure from
management and her own perfectionist tendencies.

## 🎨 **STYLE & TECHNIQUE**

### Prose Style
- **Description Density:** Technical but accessible
- **Dialogue vs Narrative:** Balanced, with realistic developer conversations
- **Sentence Structure:** Clean, professional prose with technical accuracy
"""


@pytest.fixture
def temp_project_workspace(sample_book_bible):
    """Create temporary project workspace with book bible."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)
        
        # Create book bible
        book_bible_path = project_path / "book-bible.md"
        book_bible_path.write_text(sample_book_bible)
        
        # Create references directory
        references_dir = project_path / "references"
        references_dir.mkdir()
        
        yield project_path


@pytest.mark.asyncio
class TestReferenceGenerationIntegration:
    """Integration tests for reference generation endpoints."""
    
    @patch('backend.main.verify_token')
    @patch('backend.main.get_project_workspace')
    @patch('backend.utils.reference_content_generator.ReferenceContentGenerator')
    async def test_generate_all_references_success(
        self, 
        mock_generator_class,
        mock_get_workspace,
        mock_verify_token,
        test_client,
        mock_auth_token,
        temp_project_workspace
    ):
        """Test successful generation of all reference files."""
        # Setup mocks
        mock_verify_token.return_value = mock_auth_token
        mock_get_workspace.return_value = temp_project_workspace
        
        # Mock the generator
        mock_generator = MagicMock()
        mock_generator.is_available.return_value = True
        mock_generator.generate_all_references.return_value = {
            'characters': {'success': True, 'filename': 'characters.md'},
            'outline': {'success': True, 'filename': 'outline.md'},
            'world-building': {'success': True, 'filename': 'world-building.md'},
            'style-guide': {'success': True, 'filename': 'style-guide.md'},
            'plot-timeline': {'success': True, 'filename': 'plot-timeline.md'}
        }
        mock_generator_class.return_value = mock_generator
        
        # Make request
        response = test_client.post(
            "/references/generate",
            json={"project_id": "test_project"},
            headers={"Authorization": "Bearer test_token"}
        )
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["project_id"] == "test_project"
        assert data["generated_files"] == 5
        assert data["failed_files"] == 0
        assert "Successfully generated 5 reference files" in data["message"]
        
        # Verify generator was called correctly
        mock_generator.generate_all_references.assert_called_once()
        call_args = mock_generator.generate_all_references.call_args
        assert "Alice Tester" in call_args[1]["book_bible_content"]  # Book bible content passed
        assert call_args[1]["references_dir"] == temp_project_workspace / "references"

    @patch('backend.main.verify_token')
    @patch('backend.main.get_project_workspace')
    @patch('backend.utils.reference_content_generator.ReferenceContentGenerator')
    async def test_generate_specific_references(
        self,
        mock_generator_class,
        mock_get_workspace,
        mock_verify_token,
        test_client,
        mock_auth_token,
        temp_project_workspace
    ):
        """Test generation of specific reference types."""
        # Setup mocks
        mock_verify_token.return_value = mock_auth_token
        mock_get_workspace.return_value = temp_project_workspace
        
        mock_generator = MagicMock()
        mock_generator.is_available.return_value = True
        mock_generator.generate_all_references.return_value = {
            'characters': {'success': True, 'filename': 'characters.md'},
            'outline': {'success': True, 'filename': 'outline.md'}
        }
        mock_generator_class.return_value = mock_generator
        
        # Make request for specific types
        response = test_client.post(
            "/references/generate",
            json={
                "project_id": "test_project",
                "reference_types": ["characters", "outline"]
            },
            headers={"Authorization": "Bearer test_token"}
        )
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["generated_files"] == 2
        
        # Verify correct types were requested
        call_args = mock_generator.generate_all_references.call_args
        assert call_args[1]["reference_types"] == ["characters", "outline"]

    @patch('backend.main.verify_token')
    @patch('backend.main.get_project_workspace')
    async def test_generate_references_missing_book_bible(
        self,
        mock_get_workspace,
        mock_verify_token,
        test_client,
        mock_auth_token
    ):
        """Test error handling when book bible is missing."""
        # Setup mocks
        mock_verify_token.return_value = mock_auth_token
        
        # Create empty workspace without book bible
        with tempfile.TemporaryDirectory() as temp_dir:
            mock_get_workspace.return_value = Path(temp_dir)
            
            response = test_client.post(
                "/references/generate",
                json={"project_id": "test_project"},
                headers={"Authorization": "Bearer test_token"}
            )
            
            assert response.status_code == 400
            assert "Book bible not found" in response.json()["detail"]

    @patch('backend.main.verify_token')
    @patch('backend.main.get_project_workspace')
    @patch('backend.utils.reference_content_generator.ReferenceContentGenerator')
    async def test_generate_references_openai_unavailable(
        self,
        mock_generator_class,
        mock_get_workspace,
        mock_verify_token,
        test_client,
        mock_auth_token,
        temp_project_workspace
    ):
        """Test error handling when OpenAI API is unavailable."""
        # Setup mocks
        mock_verify_token.return_value = mock_auth_token
        mock_get_workspace.return_value = temp_project_workspace
        
        # Mock generator as unavailable
        mock_generator = MagicMock()
        mock_generator.is_available.return_value = False
        mock_generator_class.return_value = mock_generator
        
        response = test_client.post(
            "/references/generate",
            json={"project_id": "test_project"},
            headers={"Authorization": "Bearer test_token"}
        )
        
        assert response.status_code == 503
        assert "OpenAI API key not configured" in response.json()["detail"]

    @patch('backend.main.verify_token')
    @patch('backend.main.get_project_workspace')
    @patch('backend.utils.reference_content_generator.ReferenceContentGenerator')
    async def test_generate_references_partial_failure(
        self,
        mock_generator_class,
        mock_get_workspace,
        mock_verify_token,
        test_client,
        mock_auth_token,
        temp_project_workspace
    ):
        """Test handling of partial generation failures."""
        # Setup mocks
        mock_verify_token.return_value = mock_auth_token
        mock_get_workspace.return_value = temp_project_workspace
        
        # Mock mixed success/failure results
        mock_generator = MagicMock()
        mock_generator.is_available.return_value = True
        mock_generator.generate_all_references.return_value = {
            'characters': {'success': True, 'filename': 'characters.md'},
            'outline': {'success': True, 'filename': 'outline.md'},
            'world-building': {'success': False, 'error': 'API timeout'},
            'style-guide': {'success': True, 'filename': 'style-guide.md'},
            'plot-timeline': {'success': False, 'error': 'Invalid prompt'}
        }
        mock_generator_class.return_value = mock_generator
        
        response = test_client.post(
            "/references/generate",
            json={"project_id": "test_project"},
            headers={"Authorization": "Bearer test_token"}
        )
        
        # Should still return 200 but indicate partial success
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is False  # Overall failure due to some failed files
        assert data["generated_files"] == 3
        assert data["failed_files"] == 2
        assert "Generated 3 files, 2 failed" in data["message"]

    @patch('backend.main.verify_token')
    @patch('backend.main.get_project_workspace')
    async def test_regenerate_single_reference(
        self,
        mock_get_workspace,
        mock_verify_token,
        test_client,
        mock_auth_token,
        temp_project_workspace
    ):
        """Test regenerating a single reference file."""
        # Setup mocks
        mock_verify_token.return_value = mock_auth_token
        mock_get_workspace.return_value = temp_project_workspace
        
        with patch('backend.utils.reference_content_generator.ReferenceContentGenerator') as mock_generator_class:
            mock_generator = MagicMock()
            mock_generator.is_available.return_value = True
            mock_generator.regenerate_reference.return_value = {
                'success': True,
                'filename': 'characters.md',
                'message': 'Successfully regenerated characters.md'
            }
            mock_generator_class.return_value = mock_generator
            
            response = test_client.post(
                "/references/characters.md/regenerate",
                json={"project_id": "test_project"},
                headers={"Authorization": "Bearer test_token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "Successfully regenerated" in data["message"]

    async def test_unauthorized_access(self, test_client):
        """Test that endpoints require authentication."""
        response = test_client.post(
            "/references/generate",
            json={"project_id": "test_project"}
            # No Authorization header
        )
        
        assert response.status_code == 403  # Forbidden

    @patch('backend.main.verify_token')
    async def test_invalid_project_id(self, mock_verify_token, test_client, mock_auth_token):
        """Test validation of project ID parameter."""
        mock_verify_token.return_value = mock_auth_token
        
        # Test empty project ID
        response = test_client.post(
            "/references/generate",
            json={"project_id": ""},
            headers={"Authorization": "Bearer test_token"}
        )
        
        assert response.status_code == 422  # Validation error


@pytest.mark.integration
class TestReferenceGenerationRealGenerator:
    """Integration tests using the real ReferenceContentGenerator (with mocked OpenAI)."""
    
    @patch('backend.main.verify_token')
    @patch('backend.main.get_project_workspace')
    @patch('openai.OpenAI')
    async def test_end_to_end_generation_with_real_generator(
        self,
        mock_openai_class,
        mock_get_workspace,
        mock_verify_token,
        test_client,
        mock_auth_token,
        temp_project_workspace
    ):
        """Test end-to-end generation using real generator class but mocked OpenAI."""
        # Setup mocks
        mock_verify_token.return_value = mock_auth_token
        mock_get_workspace.return_value = temp_project_workspace
        
        # Mock OpenAI client and response
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """# Character Reference Guide

## Core Character Profiles

### Alice Tester
**Character Foundation:**
- **Age & Demographics:** 28, Quality Assurance Engineer
- **Physical Presence:** Professional demeanor, focused attention to detail
- **Occupation & Skills:** Expert in software testing, debugging, quality assurance

**Psychology & Motivation:**
- **Core Desire:** To ensure perfect software quality
- **Greatest Fear:** Deployment failures in production
"""
        
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client
        
        # Mock environment variable for OpenAI API key
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            response = test_client.post(
                "/references/generate",
                json={
                    "project_id": "test_project",
                    "reference_types": ["characters"]
                },
                headers={"Authorization": "Bearer test_token"}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["generated_files"] == 1
        
        # Verify that the file was actually created
        characters_file = temp_project_workspace / "references" / "characters.md"
        assert characters_file.exists()
        content = characters_file.read_text()
        assert "Alice Tester" in content
        assert "Character Foundation" in content 


@pytest.mark.asyncio
async def test_reference_generation_stores_content_not_metadata():
    """
    Regression test for the dict-vs-string bug.
    Ensures create_reference_file receives actual markdown content, not metadata dictionaries.
    """
    from backend.routers.projects_v2 import generate_references_background
    from unittest.mock import AsyncMock, patch
    from pathlib import Path
    import tempfile
    
    # Mock data
    project_id = "test_project_123"
    book_bible_content = "# Test Book\n\n## Characters\nAlice - protagonist"
    user_id = "test_user_123"
    
    # Create temporary directory structure
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        references_dir = temp_path / "references"
        references_dir.mkdir(parents=True)
        
        # Create sample reference files that would be generated
        sample_files = {
            'characters': references_dir / 'characters.md',
            'outline': references_dir / 'outline.md',
            'world-building': references_dir / 'world-building.md'
        }
        
        expected_content = {
            'characters': "# Characters\n\n## Main Characters\nAlice - A brave protagonist",
            'outline': "# Outline\n\n## Chapter 1\nThe adventure begins",
            'world-building': "# World Building\n\n## Setting\nA magical testing realm"
        }
        
        # Write sample content to files
        for ref_type, file_path in sample_files.items():
            file_path.write_text(expected_content[ref_type], encoding='utf-8')
        
        # Mock the generate_all_references to return metadata with file paths
        mock_results = {}
        for ref_type, file_path in sample_files.items():
            mock_results[ref_type] = {
                "success": True,
                "filename": f"{ref_type}.md",
                "content_length": len(expected_content[ref_type]),
                "file_path": str(file_path)
            }
        
        with patch('utils.reference_content_generator.ReferenceContentGenerator') as mock_generator_class, \
             patch('utils.paths.get_project_workspace') as mock_workspace, \
             patch('backend.routers.projects_v2.create_reference_file') as mock_create_ref:
            
            # Setup mocks
            mock_generator = MagicMock()
            mock_generator.is_available.return_value = True
            mock_generator.generate_all_references.return_value = mock_results
            mock_generator_class.return_value = mock_generator
            mock_workspace.return_value = temp_path
            mock_create_ref.return_value = AsyncMock()
            
            # Run the function
            await generate_references_background(
                project_id=project_id,
                book_bible_content=book_bible_content,
                include_series_bible=False,
                user_id=user_id
            )
            
            # Verify create_reference_file was called with actual content, not metadata dicts
            assert mock_create_ref.call_count == len(sample_files)
            
            # Check each call to ensure content parameter is a string, not a dict
            for call in mock_create_ref.call_args_list:
                args, kwargs = call
                
                # Function could be called with positional or keyword arguments
                if args:
                    # Positional arguments: create_reference_file(project_id, filename, content, user_id)
                    assert args[0] == project_id  # project_id
                    assert args[1] in ['characters.md', 'outline.md', 'world-building.md']  # filename
                    content_arg = args[2]  # content
                    assert args[3] == user_id  # user_id
                else:
                    # Keyword arguments
                    assert kwargs['project_id'] == project_id
                    assert kwargs['filename'] in ['characters.md', 'outline.md', 'world-building.md']
                    content_arg = kwargs['content']
                    assert kwargs['user_id'] == user_id
                
                # CRITICAL: Ensure content is a string, not a dictionary
                assert isinstance(content_arg, str), f"Expected string content, got {type(content_arg)}: {content_arg}"
                assert len(content_arg) > 10, "Content should be substantial markdown, not empty"
                
                # Verify it's actual markdown content, not metadata
                assert 'success' not in content_arg, "Content should not contain metadata fields like 'success'"
                assert 'filename' not in content_arg, "Content should not contain metadata fields like 'filename'"
                assert 'file_path' not in content_arg, "Content should not contain metadata fields like 'file_path'"
                
                # Verify it looks like markdown
                assert content_arg.startswith('#'), "Content should start with markdown header" 