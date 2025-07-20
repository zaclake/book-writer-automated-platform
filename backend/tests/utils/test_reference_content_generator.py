"""
Unit tests for reference content generator
"""
import pytest
import os
import yaml
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from utils.reference_content_generator import ReferenceContentGenerator


@pytest.fixture
def sample_book_bible():
    """Sample book bible content for testing"""
    return """
# Test Book Bible

## 📝 GENERAL BOOK DESCRIPTION
This is a test book about testing.

## 👥 CHARACTER DEVELOPMENT
### Protagonist
- Name: Test Hero
- Age: 30
- Occupation: Software Tester

### Supporting Characters
- Test Villain: The antagonist who breaks systems
- Test Helper: The mentor who fixes bugs

## 📖 PLOT STRUCTURE
### Act I - Setup
The hero discovers bugs in the system.

### Act II - Confrontation
The hero must debug the entire codebase.

### Act III - Resolution
The system is fixed and all tests pass.

## 🌍 WORLD BUILDING
The story takes place in a digital realm where code comes to life.

## ✍️ STYLE & TECHNIQUE
Written in a technical thriller style with programming metaphors.
"""


@pytest.fixture
def mock_prompts_dir(tmp_path):
    """Create a temporary prompts directory with test YAML files"""
    prompts_dir = tmp_path / "prompts" / "reference-generation"
    prompts_dir.mkdir(parents=True)
    
    # Create sample prompt files
    characters_prompt = {
        "name": "Test Character Generator",
        "description": "Test prompt for character generation",
        "version": "1.0",
        "model_config": {
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_tokens": 1000,
            "top_p": 0.9
        },
        "system_prompt": "You are a character development expert.",
        "user_prompt_template": "Create characters based on: {book_bible_content}",
        "expected_sections": ["Main Characters", "Supporting Characters"],
        "validation_rules": ["Must include character profiles"]
    }
    
    outline_prompt = {
        "name": "Test Outline Generator", 
        "description": "Test prompt for outline generation",
        "version": "1.0",
        "model_config": {
            "model": "gpt-4o",
            "temperature": 0.6,
            "max_tokens": 1000
        },
        "system_prompt": "You are a story structure expert.",
        "user_prompt_template": "Create an outline based on: {book_bible_content}",
        "expected_sections": ["Three-Act Structure", "Chapter Breakdown"]
    }
    
    # Write YAML files
    (prompts_dir / "characters-prompt.yaml").write_text(yaml.dump(characters_prompt))
    (prompts_dir / "outline-prompt.yaml").write_text(yaml.dump(outline_prompt))
    
    return prompts_dir


class TestReferenceContentGenerator:
    """Test cases for ReferenceContentGenerator"""
    
    def test_init_without_api_key(self, mock_prompts_dir):
        """Test initialization when OpenAI API key is not available"""
        with patch.dict(os.environ, {}, clear=True):
            generator = ReferenceContentGenerator(prompts_dir=mock_prompts_dir)
            assert not generator.is_available()
            assert generator.client is None
    
    def test_init_with_api_key(self, mock_prompts_dir):
        """Test initialization when OpenAI API key is available"""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with patch('utils.reference_content_generator.OpenAI') as mock_openai:
                generator = ReferenceContentGenerator(prompts_dir=mock_prompts_dir)
                assert generator.is_available()
                mock_openai.assert_called_once_with(api_key="test-key")
    
    def test_load_prompt_success(self, mock_prompts_dir):
        """Test successful prompt loading"""
        generator = ReferenceContentGenerator(prompts_dir=mock_prompts_dir)
        prompt_config = generator.load_prompt("characters")
        
        assert prompt_config["name"] == "Test Character Generator"
        assert "system_prompt" in prompt_config
        assert "user_prompt_template" in prompt_config
        assert "model_config" in prompt_config
    
    def test_load_prompt_file_not_found(self, mock_prompts_dir):
        """Test prompt loading with non-existent file"""
        generator = ReferenceContentGenerator(prompts_dir=mock_prompts_dir)
        
        with pytest.raises(FileNotFoundError):
            generator.load_prompt("nonexistent")
    
    def test_load_prompt_invalid_yaml(self, tmp_path):
        """Test prompt loading with invalid YAML"""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        
        # Create invalid YAML file
        invalid_file = prompts_dir / "invalid-prompt.yaml"
        invalid_file.write_text("invalid: yaml: content: [")
        
        generator = ReferenceContentGenerator(prompts_dir=prompts_dir)
        
        with pytest.raises(yaml.YAMLError):
            generator.load_prompt("invalid")
    
    def test_load_prompt_missing_required_fields(self, tmp_path):
        """Test prompt loading with missing required fields"""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        
        # Create YAML with missing required fields
        incomplete_prompt = {"name": "Incomplete"}
        incomplete_file = prompts_dir / "incomplete-prompt.yaml"
        incomplete_file.write_text(yaml.dump(incomplete_prompt))
        
        generator = ReferenceContentGenerator(prompts_dir=prompts_dir)
        
        with pytest.raises(ValueError, match="Missing required field"):
            generator.load_prompt("incomplete")
    
    @patch('utils.reference_content_generator.OpenAI')
    def test_generate_content_success(self, mock_openai_class, mock_prompts_dir, sample_book_bible):
        """Test successful content generation"""
        # Setup mock OpenAI client
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = """
# Test Generated Content

## Main Characters
- Test Hero: A dedicated software tester
- Test Villain: The antagonist who breaks systems

## Supporting Characters  
- Test Helper: The mentor who fixes bugs

This is a comprehensive character guide with proper sections.
"""
        
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client
        
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            generator = ReferenceContentGenerator(prompts_dir=mock_prompts_dir)
            
            result = generator.generate_content("characters", sample_book_bible)
            
            assert len(result) > 100  # Content should be substantial
            assert "Main Characters" in result
            assert "Test Hero" in result
            
            # Verify OpenAI API was called correctly
            mock_client.chat.completions.create.assert_called_once()
            call_args = mock_client.chat.completions.create.call_args
            
            assert call_args[1]["model"] == "gpt-4o"
            assert call_args[1]["temperature"] == 0.7
            assert call_args[1]["max_tokens"] == 1000
            assert len(call_args[1]["messages"]) == 2
            assert call_args[1]["messages"][0]["role"] == "system"
            assert call_args[1]["messages"][1]["role"] == "user"
    
    def test_generate_content_no_api_key(self, mock_prompts_dir, sample_book_bible):
        """Test content generation without API key"""
        with patch.dict(os.environ, {}, clear=True):
            generator = ReferenceContentGenerator(prompts_dir=mock_prompts_dir)
            
            with pytest.raises(RuntimeError, match="OpenAI API key not configured"):
                generator.generate_content("characters", sample_book_bible)
    
    @patch('utils.reference_content_generator.OpenAI')
    def test_generate_content_empty_response(self, mock_openai_class, mock_prompts_dir, sample_book_bible):
        """Test handling of empty or too-short responses"""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Short"  # Too short
        
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client
        
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            generator = ReferenceContentGenerator(prompts_dir=mock_prompts_dir)
            
            with pytest.raises(Exception, match="Generated content is too short"):
                generator.generate_content("characters", sample_book_bible)
    
    @patch('utils.reference_content_generator.OpenAI')
    def test_generate_content_api_error(self, mock_openai_class, mock_prompts_dir, sample_book_bible):
        """Test handling of OpenAI API errors"""
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        mock_openai_class.return_value = mock_client
        
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            generator = ReferenceContentGenerator(prompts_dir=mock_prompts_dir)
            
            with pytest.raises(Exception, match="Content generation failed"):
                generator.generate_content("characters", sample_book_bible)
    
    def test_validate_content_sections(self, mock_prompts_dir):
        """Test content section validation"""
        generator = ReferenceContentGenerator(prompts_dir=mock_prompts_dir)
        
        content_with_sections = """
        # Test Content
        
        ## Main Characters
        Character info here
        
        ## Supporting Characters
        More character info
        """
        
        content_missing_sections = """
        # Test Content
        
        ## Main Characters
        Character info here
        
        ## Wrong Section
        Wrong info here
        """
        
        expected_sections = ["Main Characters", "Supporting Characters"]
        
        # Test with all sections present
        missing = generator._validate_content_sections(content_with_sections, expected_sections)
        assert missing == []
        
        # Test with missing sections
        missing = generator._validate_content_sections(content_missing_sections, expected_sections)
        assert "Supporting Characters" in missing
        assert len(missing) == 1
    
    @patch('utils.reference_content_generator.OpenAI')
    def test_generate_all_references(self, mock_openai_class, mock_prompts_dir, sample_book_bible, tmp_path):
        """Test generating all reference types"""
        # Setup mock
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "# Generated Reference Content\n\nThis is comprehensive content for testing."
        
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client
        
        references_dir = tmp_path / "references"
        
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            generator = ReferenceContentGenerator(prompts_dir=mock_prompts_dir)
            
            results = generator.generate_all_references(
                sample_book_bible, 
                references_dir, 
                reference_types=["characters", "outline"]
            )
            
            # Check results
            assert "characters" in results
            assert "outline" in results
            assert results["characters"]["success"] is True
            assert results["outline"]["success"] is True
            
            # Check files were created
            assert (references_dir / "characters.md").exists()
            assert (references_dir / "outline.md").exists()
            
            # Check file contents
            characters_content = (references_dir / "characters.md").read_text()
            assert "Generated Reference Content" in characters_content
    
    def test_generate_all_references_no_api_key(self, mock_prompts_dir, sample_book_bible, tmp_path):
        """Test generate_all_references without API key"""
        with patch.dict(os.environ, {}, clear=True):
            generator = ReferenceContentGenerator(prompts_dir=mock_prompts_dir)
            
            results = generator.generate_all_references(
                sample_book_bible,
                tmp_path / "references"
            )
            
            assert "error" in results
            assert "OpenAI API key not configured" in results["error"]
    
    @patch('utils.reference_content_generator.OpenAI')
    def test_regenerate_reference(self, mock_openai_class, mock_prompts_dir, sample_book_bible, tmp_path):
        """Test regenerating a single reference file"""
        # Setup mock
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "# Regenerated Content\n\nThis is new content."
        
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client
        
        references_dir = tmp_path / "references"
        references_dir.mkdir()
        
        # Create existing file
        existing_file = references_dir / "characters.md"
        existing_file.write_text("Old content")
        
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            generator = ReferenceContentGenerator(prompts_dir=mock_prompts_dir)
            
            result = generator.regenerate_reference("characters", sample_book_bible, references_dir)
            
            assert result["success"] is True
            assert "characters.md" in result["filename"]
            
            # Check file was updated
            new_content = existing_file.read_text()
            assert "Regenerated Content" in new_content
            assert "Old content" not in new_content
            
            # Check backup was created
            backup_files = list(references_dir.glob("*.backup.*"))
            assert len(backup_files) == 1


# Integration test (requires actual API key - skipped by default)
@pytest.mark.skip(reason="Requires actual OpenAI API key")
def test_integration_with_real_api():
    """Integration test with real OpenAI API (requires API key)"""
    if not os.getenv('OPENAI_API_KEY'):
        pytest.skip("OPENAI_API_KEY not set")
    
    sample_bible = """
    # Test Book
    
    ## Characters
    - Hero: A brave protagonist
    - Villain: A cunning antagonist
    
    ## Plot
    The hero must defeat the villain to save the world.
    """
    
    generator = ReferenceContentGenerator()
    
    if generator.is_available():
        result = generator.generate_content("characters", sample_bible)
        
        # Basic checks for real API response
        assert len(result) > 200
        assert "character" in result.lower()
        assert result.count("#") >= 2  # Should have multiple sections 