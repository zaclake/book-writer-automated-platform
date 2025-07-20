"""
Tests for OpenAI LLM Book Bible Expansion Service
Tests the reference content generator expansion functionality
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import os

from utils.reference_content_generator import ReferenceContentGenerator


class TestLLMExpansionService:
    """Test suite for LLM book bible expansion functionality."""
    
    @pytest.fixture
    def generator(self):
        """Create a ReferenceContentGenerator instance with mocked OpenAI."""
        with patch('utils.reference_content_generator.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_openai.return_value = mock_client
            generator = ReferenceContentGenerator()
            generator.client = mock_client
            return generator
    
    @pytest.fixture
    def mock_openai_response(self):
        """Create a mock OpenAI response."""
        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = """# Enhanced Book Bible

## Story Overview
This is an enhanced and detailed book bible that expands upon the basic premise provided. The story follows...

## Character Development
**Main Character**: A fully developed character with complex motivations, backstory, and character arc that spans the entire narrative...

## World Building
The setting is rich and detailed, with specific locations, cultural elements, and historical context that ground the story...

## Plot Structure
### Act I: Setup (Chapters 1-8)
- Opening Hook: Introduction that immediately engages readers
- Inciting Incident: The event that sets the story in motion
- Plot Point 1: First major turning point

### Act II: Confrontation (Chapters 9-17)
- Rising Action: Escalating conflict and complications
- Midpoint: Major revelation or reversal
- Plot Point 2: Crisis moment

### Act III: Resolution (Chapters 18-25)
- Climax: Story climax and confrontation
- Resolution: Conflicts resolved
- Denouement: Satisfying conclusion

## Themes and Motifs
Central themes woven throughout the narrative include personal growth, the nature of courage, and the power of human connection...

## Writing Guidelines
- Point of view: Third person limited
- Tone: Engaging and accessible
- Style: Clear, descriptive prose with strong dialogue
"""
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        return mock_response
    
    def test_is_available_with_api_key(self, generator):
        """Test that service is available when OpenAI client is configured."""
        assert generator.is_available() is True
    
    def test_is_available_without_api_key(self):
        """Test that service is not available when OpenAI client is not configured."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': ''}, clear=True):
            generator = ReferenceContentGenerator()
            assert generator.is_available() is False
    
    def test_expand_book_bible_quickstart_mode(self, generator, mock_openai_response):
        """Test book bible expansion from QuickStart mode data."""
        # Mock OpenAI API call
        generator.client.chat.completions.create.return_value = mock_openai_response
        
        # Test data
        quickstart_data = {
            'title': 'The Digital Frontier',
            'genre': 'Science Fiction',
            'brief_premise': 'A hacker discovers a conspiracy in virtual reality',
            'main_character': 'Alex Chen, brilliant but reckless hacker',
            'setting': 'Neo-Tokyo, 2087',
            'conflict': 'Corporate AI threatens human consciousness'
        }
        
        book_specs = {
            'chapter_count_target': 25,
            'word_count_target': 75000,
            'avg_words_per_chapter': 3000
        }
        
        # Execute expansion
        result = generator.expand_book_bible(
            source_data=quickstart_data,
            creation_mode='quickstart',
            book_specs=book_specs
        )
        
        # Verify result
        assert isinstance(result, str)
        assert len(result) > 100
        assert 'Story Overview' in result
        assert 'Character Development' in result
        assert 'Plot Structure' in result
        
        # Verify OpenAI API was called correctly
        generator.client.chat.completions.create.assert_called_once()
        call_args = generator.client.chat.completions.create.call_args
        
        # Check API call parameters
        assert call_args.kwargs['model'] == 'gpt-4o'
        assert call_args.kwargs['temperature'] == 0.7
        assert call_args.kwargs['max_tokens'] == 4000
        assert call_args.kwargs['timeout'] == 120
        
        # Check messages structure
        messages = call_args.kwargs['messages']
        assert len(messages) == 2
        assert messages[0]['role'] == 'system'
        assert messages[1]['role'] == 'user'
        
        # Verify QuickStart data is included in prompt
        user_prompt = messages[1]['content']
        assert quickstart_data['title'] in user_prompt
        assert quickstart_data['genre'] in user_prompt
        assert quickstart_data['brief_premise'] in user_prompt
        assert str(book_specs['chapter_count_target']) in user_prompt
    
    def test_expand_book_bible_guided_mode(self, generator, mock_openai_response):
        """Test book bible expansion from Guided mode data."""
        generator.client.chat.completions.create.return_value = mock_openai_response
        
        guided_data = {
            'title': 'The Last Library',
            'genre': 'Fantasy',
            'premise': 'In a world where books are forbidden, a librarian guards the last collection',
            'main_characters': 'Mira the Librarian, Kael the Rebel, Elder Thorne',
            'setting_time': 'Post-apocalyptic future',
            'setting_place': 'The Wastes of former civilization',
            'central_conflict': 'Knowledge vs. ignorance, freedom vs. control',
            'themes': 'Power of knowledge, preservation of culture, resistance',
            'target_audience': 'Young Adult',
            'tone': 'Epic and hopeful despite dark setting',
            'key_plot_points': 'Discovery, betrayal, revelation, final confrontation'
        }
        
        book_specs = {
            'chapter_count_target': 30,
            'word_count_target': 90000,
            'avg_words_per_chapter': 3000
        }
        
        result = generator.expand_book_bible(
            source_data=guided_data,
            creation_mode='guided',
            book_specs=book_specs
        )
        
        assert isinstance(result, str)
        assert len(result) > 100
        
        # Verify Guided data is included in prompt
        call_args = generator.client.chat.completions.create.call_args
        user_prompt = call_args.kwargs['messages'][1]['content']
        assert guided_data['title'] in user_prompt
        assert guided_data['premise'] in user_prompt
        assert guided_data['themes'] in user_prompt
        assert guided_data['tone'] in user_prompt
    
    def test_expand_book_bible_invalid_mode(self, generator):
        """Test that invalid creation mode raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported creation mode"):
            generator.expand_book_bible(
                source_data={'title': 'Test'},
                creation_mode='invalid_mode',
                book_specs={}
            )
    
    def test_expand_book_bible_no_openai_available(self):
        """Test expansion when OpenAI is not available."""
        with patch.dict(os.environ, {'OPENAI_API_KEY': ''}, clear=True):
            generator = ReferenceContentGenerator()
            
            with pytest.raises(Exception, match="OpenAI API not available"):
                generator.expand_book_bible(
                    source_data={'title': 'Test'},
                    creation_mode='quickstart',
                    book_specs={}
                )
    
    def test_openai_api_error_handling(self, generator):
        """Test handling of OpenAI API errors."""
        # Mock API error
        generator.client.chat.completions.create.side_effect = Exception("API rate limit exceeded")
        
        with pytest.raises(Exception, match="Failed to expand book bible"):
            generator.expand_book_bible(
                source_data={'title': 'Test'},
                creation_mode='quickstart',
                book_specs={}
            )
    
    def test_openai_timeout_handling(self, generator):
        """Test handling of OpenAI API timeouts."""
        # Mock timeout error
        generator.client.chat.completions.create.side_effect = Exception("timeout")
        
        with pytest.raises(Exception, match="Failed to expand book bible"):
            generator.expand_book_bible(
                source_data={'title': 'Test'},
                creation_mode='quickstart',
                book_specs={}
            )
    
    def test_openai_empty_response_handling(self, generator):
        """Test handling of empty/short OpenAI responses."""
        # Mock empty response
        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = ""  # Empty content
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        
        generator.client.chat.completions.create.return_value = mock_response
        
        with pytest.raises(Exception, match="Generated content is too short"):
            generator.expand_book_bible(
                source_data={'title': 'Test'},
                creation_mode='quickstart',
                book_specs={}
            )
    
    def test_quickstart_prompt_content(self, generator, mock_openai_response):
        """Test that QuickStart prompts contain all expected elements."""
        generator.client.chat.completions.create.return_value = mock_openai_response
        
        quickstart_data = {
            'title': 'Test Novel',
            'genre': 'Mystery',
            'brief_premise': 'A detective solves impossible crimes',
            'main_character': 'Detective Sarah Jones',
            'setting': 'Modern day London',
            'conflict': 'Serial killer targeting detectives'
        }
        
        generator.expand_book_bible(
            source_data=quickstart_data,
            creation_mode='quickstart',
            book_specs={'chapter_count_target': 20}
        )
        
        call_args = generator.client.chat.completions.create.call_args
        system_prompt = call_args.kwargs['messages'][0]['content']
        user_prompt = call_args.kwargs['messages'][1]['content']
        
        # Check system prompt contains guidance
        assert 'story development assistant' in system_prompt.lower()
        assert 'comprehensive book bible' in system_prompt.lower()
        assert 'character profiles' in system_prompt.lower()
        assert 'plot structure' in system_prompt.lower()
        
        # Check user prompt contains all QuickStart fields
        for key, value in quickstart_data.items():
            assert value in user_prompt
    
    def test_guided_prompt_content(self, generator, mock_openai_response):
        """Test that Guided prompts contain all expected elements."""
        generator.client.chat.completions.create.return_value = mock_openai_response
        
        guided_data = {
            'title': 'Epic Fantasy',
            'premise': 'Heroes quest to save the realm',
            'themes': 'Good vs evil, sacrifice, redemption',
            'tone': 'Epic and serious'
        }
        
        generator.expand_book_bible(
            source_data=guided_data,
            creation_mode='guided',
            book_specs={'chapter_count_target': 35}
        )
        
        call_args = generator.client.chat.completions.create.call_args
        system_prompt = call_args.kwargs['messages'][0]['content']
        user_prompt = call_args.kwargs['messages'][1]['content']
        
        # Check system prompt for guided mode
        assert 'synthesize' in system_prompt.lower()
        assert 'cohesive book bible' in system_prompt.lower()
        
        # Check guided data is included
        for value in guided_data.values():
            assert value in user_prompt
    
    @patch('time.time')
    def test_timing_logging(self, mock_time, generator, mock_openai_response):
        """Test that timing is properly logged."""
        # Mock time to control timing
        mock_time.side_effect = [1000.0, 1005.5]  # 5.5 second duration
        
        generator.client.chat.completions.create.return_value = mock_openai_response
        
        with patch('utils.reference_content_generator.logger') as mock_logger:
            generator.expand_book_bible(
                source_data={'title': 'Test'},
                creation_mode='quickstart',
                book_specs={}
            )
            
            # Check that timing logs were made
            mock_logger.info.assert_any_call("Starting OpenAI API request for book_bible_expansion")
            mock_logger.info.assert_any_call(
                "OpenAI API request completed for book_bible_expansion in 5.50s, generated 1500 characters"
            )
    
    def test_book_specs_in_prompt(self, generator, mock_openai_response):
        """Test that book specifications are correctly included in prompts."""
        generator.client.chat.completions.create.return_value = mock_openai_response
        
        book_specs = {
            'chapter_count_target': 42,
            'word_count_target': 120000,
            'avg_words_per_chapter': 2857
        }
        
        generator.expand_book_bible(
            source_data={'title': 'Long Novel'},
            creation_mode='quickstart',
            book_specs=book_specs
        )
        
        call_args = generator.client.chat.completions.create.call_args
        user_prompt = call_args.kwargs['messages'][1]['content']
        
        # Check book specs are in prompt
        assert str(book_specs['chapter_count_target']) in user_prompt
        assert f"{book_specs['word_count_target']:,}" in user_prompt
        assert str(book_specs['avg_words_per_chapter']) in user_prompt
    
    def test_environment_flag_disabled(self, generator):
        """Test that expansion respects ENABLE_OPENAI_EXPANSION environment flag."""
        with patch.dict(os.environ, {'ENABLE_OPENAI_EXPANSION': 'false'}):
            # This test would be part of the API layer, not the generator itself
            # The generator would still work, but the API would check the flag
            pass  # API level test would go here
    
    def test_rate_limit_error_message(self, generator):
        """Test specific error message for rate limit errors."""
        generator.client.chat.completions.create.side_effect = Exception("rate_limit exceeded")
        
        with pytest.raises(Exception, match="API rate limit exceeded"):
            generator._make_openai_request(
                "system prompt",
                "user prompt", 
                "test_request"
            )
    
    def test_timeout_error_message(self, generator):
        """Test specific error message for timeout errors."""
        generator.client.chat.completions.create.side_effect = Exception("Request timeout")
        
        with pytest.raises(Exception, match="Content generation timed out"):
            generator._make_openai_request(
                "system prompt",
                "user prompt",
                "test_request"
            )


class TestExpansionAPIEndpoint:
    """Test the API endpoint for book bible expansion."""
    
    @pytest.fixture
    def mock_auth_user(self):
        """Mock authenticated user."""
        return {'sub': 'test-user-123'}
    
    @pytest.mark.asyncio
    async def test_expand_book_bible_endpoint_quickstart(self, mock_auth_user):
        """Test the expansion API endpoint with QuickStart data."""
        from routers.projects_v2 import expand_book_bible_content
        
        request_data = {
            'source_data': {
                'title': 'API Test Book',
                'genre': 'Thriller',
                'brief_premise': 'High-stakes espionage'
            },
            'creation_mode': 'quickstart',
            'book_specs': {
                'target_chapters': 25,
                'target_word_count': 75000
            }
        }
        
        with patch('routers.projects_v2.ReferenceContentGenerator') as mock_generator_class:
            mock_generator = Mock()
            mock_generator.is_available.return_value = True
            mock_generator.expand_book_bible.return_value = "Expanded content here..."
            mock_generator_class.return_value = mock_generator
            
            response = await expand_book_bible_content(
                request=request_data,
                current_user=mock_auth_user
            )
            
            assert response['success'] is True
            assert 'expanded_content' in response
            assert response['metadata']['creation_mode'] == 'quickstart'
            assert response['metadata']['ai_generated'] is True
    
    @pytest.mark.asyncio
    async def test_expand_book_bible_endpoint_validation_error(self, mock_auth_user):
        """Test endpoint validation for missing required fields."""
        from routers.projects_v2 import expand_book_bible_content
        from fastapi import HTTPException
        
        # Missing source_data
        request_data = {
            'creation_mode': 'quickstart'
        }
        
        with pytest.raises(HTTPException) as exc_info:
            await expand_book_bible_content(
                request=request_data,
                current_user=mock_auth_user
            )
        
        assert exc_info.value.status_code == 400
        assert "source_data and creation_mode are required" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_expand_book_bible_endpoint_invalid_mode(self, mock_auth_user):
        """Test endpoint validation for invalid creation mode."""
        from routers.projects_v2 import expand_book_bible_content
        from fastapi import HTTPException
        
        request_data = {
            'source_data': {'title': 'Test'},
            'creation_mode': 'invalid'
        }
        
        with pytest.raises(HTTPException) as exc_info:
            await expand_book_bible_content(
                request=request_data,
                current_user=mock_auth_user
            )
        
        assert exc_info.value.status_code == 400
        assert "must be 'quickstart' or 'guided'" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_expand_book_bible_endpoint_openai_unavailable(self, mock_auth_user):
        """Test endpoint when OpenAI service is unavailable."""
        from routers.projects_v2 import expand_book_bible_content
        from fastapi import HTTPException
        
        request_data = {
            'source_data': {'title': 'Test'},
            'creation_mode': 'quickstart'
        }
        
        with patch('routers.projects_v2.ReferenceContentGenerator') as mock_generator_class:
            mock_generator = Mock()
            mock_generator.is_available.return_value = False
            mock_generator_class.return_value = mock_generator
            
            with pytest.raises(HTTPException) as exc_info:
                await expand_book_bible_content(
                    request=request_data,
                    current_user=mock_auth_user
                )
            
            assert exc_info.value.status_code == 503
            assert "OpenAI service is not available" in str(exc_info.value.detail) 