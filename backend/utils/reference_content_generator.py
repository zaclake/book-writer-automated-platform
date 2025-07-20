"""
Reference Content Generator
Uses OpenAI API to generate rich, book-specific content for reference files based on book bible and YAML prompts.
"""
import os
import json
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from openai import OpenAI

logger = logging.getLogger(__name__)


class ReferenceContentGenerator:
    """Generates AI-powered content for reference files based on book bible and prompts."""
    
    def __init__(self, prompts_dir: Optional[Path] = None):
        """
        Initialize the content generator.
        
        Args:
            prompts_dir: Directory containing YAML prompt files (defaults to prompts/reference-generation)
        """
        self.client = None
        
        if prompts_dir:
            self.prompts_dir = prompts_dir
        else:
            # Simple path resolution
            self.prompts_dir = Path(__file__).parent.parent / "prompts" / "reference-generation"
        
        # Initialize OpenAI client if API key is available
        api_key = os.getenv('OPENAI_API_KEY')
        if api_key:
            self.client = OpenAI(api_key=api_key)
        else:
            logger.warning("OPENAI_API_KEY not found. Content generation will be disabled.")
    
    def is_available(self) -> bool:
        """Check if content generation is available (API key configured)."""
        return self.client is not None
    
    def expand_book_bible(self, source_data: dict, creation_mode: str, book_specs: dict) -> str:
        """
        Expand QuickStart or Guided wizard data into a comprehensive book bible using OpenAI.
        
        Args:
            source_data: Data from QuickStart or Guided wizard
            creation_mode: 'quickstart' or 'guided'
            book_specs: Book length specifications (target_chapters, word_count, etc.)
            
        Returns:
            Expanded book bible content as markdown
        """
        if not self.is_available():
            raise Exception("OpenAI API not available. Check OPENAI_API_KEY configuration.")
        
        try:
            # Build the expansion prompt based on creation mode
            if creation_mode == 'quickstart':
                return self._expand_quickstart_data(source_data, book_specs)
            elif creation_mode == 'guided':
                return self._expand_guided_data(source_data, book_specs)
            else:
                raise ValueError(f"Unsupported creation mode: {creation_mode}")
                
        except Exception as e:
            logger.error(f"Failed to expand book bible for mode {creation_mode}: {e}")
            raise
    
    def _expand_quickstart_data(self, data: dict, book_specs: dict) -> str:
        """Expand QuickStart data into full book bible."""
        system_prompt = """You are an expert story development assistant. Your task is to take basic story elements and expand them into a comprehensive book bible that will guide the writing of a full novel.

You must create a detailed, professional book bible that includes:
1. Expanded character profiles with motivations, backstories, and arcs
2. Rich world-building with specific details about setting, culture, and rules  
3. Detailed plot structure with three-act breakdown and chapter outline
4. Themes and motifs woven throughout the story
5. Writing style guidelines and tone consistency
6. Conflict escalation and resolution planning

The book bible should be comprehensive enough for a writer to begin crafting chapters immediately."""

        user_prompt = f"""Please expand the following basic story elements into a comprehensive book bible:

**Title:** {data.get('title', 'Untitled')}
**Genre:** {data.get('genre', 'Fiction')}
**Brief Premise:** {data.get('brief_premise', 'Not provided')}
**Main Character:** {data.get('main_character', 'Not provided')}
**Setting:** {data.get('setting', 'Not provided')}
**Central Conflict:** {data.get('conflict', 'Not provided')}

**Book Specifications:**
- Target Chapters: {book_specs.get('chapter_count_target', 25)}
- Target Word Count: {book_specs.get('word_count_target', 75000):,} words
- Words per Chapter: {book_specs.get('avg_words_per_chapter', 3000)}

Create a detailed book bible in markdown format that includes:

## Story Overview
- Expanded premise with deeper thematic elements
- Genre-specific conventions and expectations

## Character Development
- Detailed main character profile with background, motivations, flaws, and character arc
- Supporting characters and their relationships
- Character growth throughout the story

## World Building
- Expanded setting details with specific locations
- Cultural, social, and historical context
- Rules and constraints of this world

## Plot Structure
- Three-act structure breakdown
- Major plot points and turning points
- Chapter-by-chapter outline with key scenes
- Conflict escalation and resolution

## Themes and Motifs
- Central themes explored in the story
- Recurring motifs and symbols
- How themes develop across chapters

## Writing Guidelines
- Tone and voice consistency
- Point of view and narrative style
- Genre-specific elements to include

Generate comprehensive, specific content that gives a writer everything needed to begin writing chapters immediately."""

        return self._make_openai_request(system_prompt, user_prompt, "book_bible_expansion")
    
    def _expand_guided_data(self, data: dict, book_specs: dict) -> str:
        """Expand Guided wizard data into full book bible."""
        system_prompt = """You are an expert story development assistant. Your task is to take detailed story planning information and synthesize it into a comprehensive, professional book bible for novel writing.

You must create a cohesive book bible that weaves together all the provided elements into a unified vision, expanding where needed and ensuring consistency throughout. The book bible should be detailed enough for immediate chapter writing."""

        user_prompt = f"""Please synthesize and expand the following detailed story elements into a comprehensive book bible:

**Title:** {data.get('title', 'Untitled')}
**Genre:** {data.get('genre', 'Fiction')}
**Premise:** {data.get('premise', 'Not provided')}
**Main Characters:** {data.get('main_characters', 'Not provided')}
**Setting Time:** {data.get('setting_time', 'Not provided')}
**Setting Place:** {data.get('setting_place', 'Not provided')}
**Central Conflict:** {data.get('central_conflict', 'Not provided')}
**Themes:** {data.get('themes', 'Not provided')}
**Target Audience:** {data.get('target_audience', 'Not provided')}
**Tone:** {data.get('tone', 'Not provided')}
**Key Plot Points:** {data.get('key_plot_points', 'Not provided')}

**Book Specifications:**
- Target Chapters: {book_specs.get('chapter_count_target', 25)}
- Target Word Count: {book_specs.get('word_count_target', 75000):,} words
- Words per Chapter: {book_specs.get('avg_words_per_chapter', 3000)}

Create a detailed, cohesive book bible in markdown format that includes:

## Story Overview
- Unified premise incorporating all provided elements
- Genre analysis and reader expectations

## Character Profiles
- Expanded character descriptions with psychological depth
- Character relationships and dynamics
- Character arcs and development throughout the story

## World and Setting
- Detailed world-building combining time and place elements
- Cultural, historical, and environmental context
- Specific locations and their significance

## Plot Architecture
- Comprehensive plot structure incorporating provided plot points
- Three-act breakdown with clear progression
- Detailed chapter outline with scene descriptions
- Conflict development and resolution path

## Thematic Framework
- Deep exploration of provided themes
- How themes manifest in plot, character, and setting
- Thematic consistency throughout chapters

## Voice and Style Guide
- Tone implementation guidelines based on target audience
- Narrative voice and point of view decisions
- Style consistency for the specified tone: "{data.get('tone', 'Not specified')}"

## Writing Direction
- Scene-by-scene guidance for opening chapters
- Pacing and rhythm guidelines
- Key scenes that must be included

Ensure all elements work together cohesively and provide specific, actionable guidance for writing."""

        return self._make_openai_request(system_prompt, user_prompt, "book_bible_expansion")
    
    def _make_openai_request(self, system_prompt: str, user_prompt: str, request_type: str) -> str:
        """Make OpenAI API request with proper error handling."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            import time
            start_time = time.time()
            logger.info(f"Starting OpenAI API request for {request_type}")
            
            response = self.client.chat.completions.create(
                model='gpt-4o',
                messages=messages,
                temperature=0.7,
                max_tokens=4000,
                top_p=0.9,
                timeout=120  # 2 minute timeout for complex requests
            )
            
            duration = time.time() - start_time
            content = response.choices[0].message.content
            
            logger.info(f"OpenAI API request completed for {request_type} in {duration:.2f}s, generated {len(content)} characters")
            
            if not content or len(content.strip()) < 200:
                raise Exception("Generated content is too short or empty")
            
            return content
            
        except Exception as e:
            logger.error(f"OpenAI API request failed for {request_type}: {e}")
            if "timeout" in str(e).lower():
                raise Exception("Content generation timed out. Please try again.")
            elif "rate_limit" in str(e).lower():
                raise Exception("API rate limit exceeded. Please try again in a moment.")
            else:
                raise Exception(f"Content generation failed: {str(e)}")
    
    def load_prompt(self, reference_type: str) -> Dict[str, Any]:
        """
        Load YAML prompt configuration for a specific reference type.
        
        Args:
            reference_type: Type of reference (characters, outline, world-building, style-guide, plot-timeline)
            
        Returns:
            Dictionary containing prompt configuration
            
        Raises:
            FileNotFoundError: If prompt file doesn't exist
        """
        # Simple fallback for missing prompt files
        fallback_prompt = {
            'name': f'{reference_type.title()} Reference Generator',
            'system_prompt': f'You are an expert {reference_type} specialist. Create comprehensive {reference_type} documentation based on the book bible.',
            'user_prompt_template': f'Based on this book bible content:\n\n{{book_bible_content}}\n\nCreate detailed {reference_type} documentation. Format as markdown.',
            'model_config': {'model': 'gpt-4', 'temperature': 0.7, 'max_tokens': 3000}
        }
        
        prompt_file = self.prompts_dir / f"{reference_type}-prompt.yaml"
        
        if prompt_file.exists():
            try:
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    prompt_config = yaml.safe_load(f)
                
                # Validate required fields
                required_fields = ['name', 'system_prompt', 'user_prompt_template', 'model_config']
                for field in required_fields:
                    if field not in prompt_config:
                        logger.warning(f"Missing field {field} in prompt config, using fallback")
                        return fallback_prompt
                
                return prompt_config
                
            except Exception as e:
                logger.warning(f"Error loading prompt file {prompt_file}: {e}, using fallback")
                return fallback_prompt
        
        # Use fallback if file doesn't exist
        logger.info(f"Prompt file not found: {prompt_file}, using fallback")
        return fallback_prompt
    
    def generate_content(self, reference_type: str, book_bible_content: str, 
                        additional_context: Optional[Dict[str, Any]] = None,
                        book_length_tier: Optional[str] = None,
                        estimated_chapters: Optional[int] = None,
                        target_word_count: Optional[int] = None) -> str:
        """
        Generate content for a specific reference file type.
        
        Args:
            reference_type: Type of reference to generate (characters, outline, etc.)
            book_bible_content: The complete book bible markdown content
            additional_context: Optional additional context to include in prompt
            
        Returns:
            Generated markdown content for the reference file
            
        Raises:
            RuntimeError: If OpenAI API is not available
            Exception: If content generation fails
        """
        if not self.is_available():
            raise RuntimeError("OpenAI API key not configured. Cannot generate content.")
        
        # Load prompt configuration
        try:
            prompt_config = self.load_prompt(reference_type)
        except (FileNotFoundError, yaml.YAMLError, ValueError) as e:
            logger.error(f"Failed to load prompt for {reference_type}: {e}")
            raise Exception(f"Prompt loading failed: {e}")
        
        # Extract configuration
        model_config = prompt_config['model_config']
        system_prompt = prompt_config['system_prompt']
        user_prompt_template = prompt_config['user_prompt_template']
        
        # Prepare user prompt with book bible content and book specifications
        context = {
            'book_bible_content': book_bible_content,
            **(additional_context or {})
        }
        
        # Add book length context if provided
        if book_length_tier or estimated_chapters or target_word_count:
            book_specs = []
            if book_length_tier:
                book_specs.append(f"Book Length Category: {book_length_tier.replace('_', ' ').title()}")
            if estimated_chapters:
                book_specs.append(f"Estimated Chapters: {estimated_chapters}")
            if target_word_count:
                book_specs.append(f"Target Word Count: {target_word_count:,} words")
            
            context['book_specifications'] = "\n".join(book_specs)
            
            # Update book bible content to include specifications
            if book_specs:
                context['book_bible_content'] = f"{book_bible_content}\n\n## Book Specifications\n{context['book_specifications']}"
        
        try:
            user_prompt = user_prompt_template.format(**context)
        except KeyError as e:
            raise Exception(f"Template formatting failed - missing context key: {e}")
        
        # Prepare messages for OpenAI API
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # Make API request with timeout
        try:
            import time
            start_time = time.time()
            logger.info(f"Starting OpenAI API request for {reference_type} using {model_config.get('model', 'gpt-4o')}")
            
            response = self.client.chat.completions.create(
                model=model_config.get('model', 'gpt-4o'),
                messages=messages,
                temperature=model_config.get('temperature', 0.7),
                max_tokens=model_config.get('max_tokens', 4000),
                top_p=model_config.get('top_p', 0.9),
                timeout=90  # 90 second timeout for OpenAI API calls
            )
            
            duration = time.time() - start_time
            logger.info(f"OpenAI API request completed for {reference_type} in {duration:.2f} seconds")
            
            generated_content = response.choices[0].message.content
            
            if not generated_content or len(generated_content.strip()) < 100:
                raise Exception("Generated content is too short or empty")
            
            # Validate content contains expected sections (if specified)
            if 'expected_sections' in prompt_config:
                missing_sections = self._validate_content_sections(
                    generated_content, 
                    prompt_config['expected_sections']
                )
                if missing_sections:
                    logger.warning(f"Generated content missing sections: {missing_sections}")
            
            logger.info(f"Successfully generated {len(generated_content)} characters for {reference_type}")
            return generated_content
            
        except Exception as e:
            # Handle specific timeout and API errors
            error_message = str(e)
            
            if "timeout" in error_message.lower():
                logger.error(f"OpenAI API request timed out for {reference_type}: {e}")
                raise Exception(f"Content generation timed out after 90 seconds. Please try again later.")
            elif "rate_limit" in error_message.lower():
                logger.error(f"OpenAI API rate limit exceeded for {reference_type}: {e}")
                raise Exception(f"OpenAI API rate limit exceeded. Please wait a moment and try again.")
            elif "quota" in error_message.lower():
                logger.error(f"OpenAI API quota exceeded for {reference_type}: {e}")
                raise Exception(f"OpenAI API quota exceeded. Please check your API usage.")
            elif "authentication" in error_message.lower():
                logger.error(f"OpenAI API authentication failed for {reference_type}: {e}")
                raise Exception(f"OpenAI API authentication failed. Please check your API key.")
            else:
                logger.error(f"OpenAI API request failed for {reference_type}: {e}")
                raise Exception(f"Content generation failed: {e}")
    
    def _validate_content_sections(self, content: str, expected_sections: List[str]) -> List[str]:
        """
        Validate that generated content contains expected sections.
        
        Args:
            content: Generated markdown content
            expected_sections: List of section names that should be present
            
        Returns:
            List of missing section names
        """
        missing_sections = []
        content_lower = content.lower()
        
        for section in expected_sections:
            # Look for section headers (## Section Name or # Section Name)
            section_patterns = [
                f"## {section.lower()}",
                f"# {section.lower()}",
                section.lower().replace(' ', '')  # Also check without spaces
            ]
            
            if not any(pattern in content_lower for pattern in section_patterns):
                missing_sections.append(section)
        
        return missing_sections
    
    def generate_all_references(self, book_bible_content: str, 
                               references_dir: Path,
                               reference_types: Optional[List[str]] = None,
                               book_length_tier: Optional[str] = None,
                               estimated_chapters: Optional[int] = None,
                               target_word_count: Optional[int] = None,
                               include_series_bible: bool = False) -> Dict[str, Any]:
        """
        Generate content for all reference file types.
        
        Args:
            book_bible_content: The complete book bible markdown content
            references_dir: Directory to write generated reference files
            reference_types: List of reference types to generate (defaults to all)
            
        Returns:
            Dictionary with generation results for each reference type
        """
        if not self.is_available():
            return {"error": "OpenAI API key not configured"}
        
        # Default reference types
        if reference_types is None:
            reference_types = [
                'characters', 'outline', 'world-building', 'style-guide', 'plot-timeline',
                'themes-and-motifs', 'research-notes', 'target-audience-profile'
            ]
        
        # Add series bible if requested
        if include_series_bible and 'series-bible' not in reference_types:
            reference_types.append('series-bible')
        
        results = {}
        references_dir.mkdir(parents=True, exist_ok=True)
        
        for ref_type in reference_types:
            try:
                logger.info(f"Generating content for {ref_type}")
                
                # Generate content with book specifications
                content = self.generate_content(
                    ref_type, 
                    book_bible_content,
                    book_length_tier=book_length_tier,
                    estimated_chapters=estimated_chapters,
                    target_word_count=target_word_count
                )
                
                # Determine filename
                filename_map = {
                    'characters': 'characters.md',
                    'outline': 'outline.md',
                    'world-building': 'world-building.md',
                    'style-guide': 'style-guide.md',
                    'plot-timeline': 'plot-timeline.md',
                    'themes-and-motifs': 'themes-and-motifs.md',
                    'research-notes': 'research-notes.md',
                    'target-audience-profile': 'target-audience-profile.md',
                    'series-bible': 'series-bible.md'
                }
                
                filename = filename_map.get(ref_type, f"{ref_type}.md")
                file_path = references_dir / filename
                
                # Write content to file
                file_path.write_text(content, encoding='utf-8')
                
                results[ref_type] = {
                    "success": True,
                    "filename": filename,
                    "content_length": len(content),
                    "file_path": str(file_path)
                }
                
                logger.info(f"Successfully generated {filename} ({len(content)} characters)")
                
            except Exception as e:
                logger.error(f"Failed to generate {ref_type}: {e}")
                results[ref_type] = {
                    "success": False,
                    "error": str(e)
                }
        
        return results
    
    def regenerate_reference(self, reference_type: str, book_bible_content: str,
                           references_dir: Path) -> Dict[str, Any]:
        """
        Regenerate content for a specific reference file.
        
        Args:
            reference_type: Type of reference to regenerate
            book_bible_content: The complete book bible content
            references_dir: Directory containing reference files
            
        Returns:
            Dictionary with regeneration result
        """
        try:
            logger.info(f"Starting regeneration of {reference_type} reference")
            
            # Generate new content
            content = self.generate_content(reference_type, book_bible_content)
            
            # Determine filename and write
            filename_map = {
                'characters': 'characters.md',
                'outline': 'outline.md', 
                'world-building': 'world-building.md',
                'style-guide': 'style-guide.md',
                'plot-timeline': 'plot-timeline.md',
                'themes-and-motifs': 'themes-and-motifs.md',
                'research-notes': 'research-notes.md',
                'target-audience-profile': 'target-audience-profile.md',
                'series-bible': 'series-bible.md'
            }
            
            filename = filename_map.get(reference_type, f"{reference_type}.md")
            file_path = references_dir / filename
            
            # Backup existing file if it exists
            if file_path.exists():
                backup_path = file_path.with_suffix('.bak')
                file_path.rename(backup_path)
                logger.info(f"Backed up existing {filename} to {backup_path.name}")
            
            # Write new content
            file_path.write_text(content, encoding='utf-8')
            
            return {
                "success": True,
                "filename": filename,
                "content_length": len(content),
                "file_path": str(file_path),
                "message": f"Successfully regenerated {filename}"
            }
            
        except Exception as e:
            logger.error(f"Failed to regenerate {reference_type}: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Regeneration failed for {reference_type}: {e}"
            }


# Convenience function for use in other modules
def generate_reference_content(reference_type: str, book_bible_content: str, 
                             output_path: Path) -> Dict[str, Any]:
    """
    Convenience function to generate content for a single reference file.
    
    Args:
        reference_type: Type of reference to generate
        book_bible_content: Book bible markdown content
        output_path: Path where to write the generated content
        
    Returns:
        Generation result dictionary
    """
    generator = ReferenceContentGenerator()
    
    if not generator.is_available():
        return {"success": False, "error": "OpenAI API not configured"}
    
    try:
        content = generator.generate_content(reference_type, book_bible_content)
        output_path.write_text(content, encoding='utf-8')
        
        return {
            "success": True,
            "content_length": len(content),
            "file_path": str(output_path)
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)} 