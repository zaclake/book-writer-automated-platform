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
        self.prompts_dir = prompts_dir or Path(__file__).parent.parent / "prompts" / "reference-generation"
        
        # Initialize OpenAI client if API key is available
        api_key = os.getenv('OPENAI_API_KEY')
        if api_key:
            self.client = OpenAI(api_key=api_key)
        else:
            logger.warning("OPENAI_API_KEY not found. Content generation will be disabled.")
    
    def is_available(self) -> bool:
        """Check if content generation is available (API key configured)."""
        return self.client is not None
    
    def load_prompt(self, reference_type: str) -> Dict[str, Any]:
        """
        Load YAML prompt configuration for a specific reference type.
        
        Args:
            reference_type: Type of reference (characters, outline, world-building, style-guide, plot-timeline)
            
        Returns:
            Dictionary containing prompt configuration
            
        Raises:
            FileNotFoundError: If prompt file doesn't exist
            yaml.YAMLError: If prompt file is invalid YAML
        """
        prompt_file = self.prompts_dir / f"{reference_type}-prompt.yaml"
        
        if not prompt_file.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
        
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                prompt_config = yaml.safe_load(f)
            
            # Validate required fields
            required_fields = ['name', 'system_prompt', 'user_prompt_template', 'model_config']
            for field in required_fields:
                if field not in prompt_config:
                    raise ValueError(f"Missing required field in prompt config: {field}")
            
            return prompt_config
            
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"Invalid YAML in prompt file {prompt_file}: {e}")
    
    def generate_content(self, reference_type: str, book_bible_content: str, 
                        additional_context: Optional[Dict[str, Any]] = None) -> str:
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
        
        # Prepare user prompt with book bible content
        context = {
            'book_bible_content': book_bible_content,
            **(additional_context or {})
        }
        
        try:
            user_prompt = user_prompt_template.format(**context)
        except KeyError as e:
            raise Exception(f"Template formatting failed - missing context key: {e}")
        
        # Prepare messages for OpenAI API
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # Make API request
        try:
            logger.info(f"Generating content for {reference_type} using {model_config.get('model', 'gpt-4o')}")
            
            response = self.client.chat.completions.create(
                model=model_config.get('model', 'gpt-4o'),
                messages=messages,
                temperature=model_config.get('temperature', 0.7),
                max_tokens=model_config.get('max_tokens', 4000),
                top_p=model_config.get('top_p', 0.9)
            )
            
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
                               reference_types: Optional[List[str]] = None) -> Dict[str, Any]:
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
            reference_types = ['characters', 'outline', 'world-building', 'style-guide', 'plot-timeline']
        
        results = {}
        references_dir.mkdir(parents=True, exist_ok=True)
        
        for ref_type in reference_types:
            try:
                logger.info(f"Generating content for {ref_type}")
                
                # Generate content
                content = self.generate_content(ref_type, book_bible_content)
                
                # Determine filename
                filename_map = {
                    'characters': 'characters.md',
                    'outline': 'outline.md',
                    'world-building': 'world-building.md',
                    'style-guide': 'style-guide.md',
                    'plot-timeline': 'plot-timeline.md'
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
            # Generate new content
            content = self.generate_content(reference_type, book_bible_content)
            
            # Determine filename and write
            filename_map = {
                'characters': 'characters.md',
                'outline': 'outline.md', 
                'world-building': 'world-building.md',
                'style-guide': 'style-guide.md',
                'plot-timeline': 'plot-timeline.md'
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