#!/usr/bin/env python3
"""
Prewriting Summary Service
Generates comprehensive summaries from Book Bible content for efficient chapter generation.
"""

import logging
import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from backend.auto_complete.llm_orchestrator import LLMOrchestrator, GenerationResult

logger = logging.getLogger(__name__)

@dataclass
class PrewritingSummary:
    """Structured summary of book bible content for chapter generation."""
    project_id: str
    title: str
    genre: str
    
    # Core story elements
    premise: str
    main_characters: List[Dict[str, str]]
    setting: Dict[str, str]
    central_conflict: str
    themes: List[str]
    
    # Structure elements
    story_structure: Dict[str, str]
    chapter_outline: List[Dict[str, Any]]
    must_include_elements: List[str]
    
    # Writing guidelines
    tone: str
    target_audience: str
    writing_style: str
    pacing_strategy: str
    
    # Metadata
    generated_at: datetime
    word_count_target: int
    total_chapters: int

class PrewritingSummaryService:
    """Service for generating and managing prewriting summaries."""
    
    def __init__(self, llm_orchestrator: Optional[LLMOrchestrator] = None):
        """Initialize the prewriting summary service."""
        self.llm_orchestrator = llm_orchestrator or LLMOrchestrator()
        self.logger = logging.getLogger(__name__)
        
    async def generate_summary(self, project_data: Dict[str, Any]) -> PrewritingSummary:
        """Generate a comprehensive prewriting summary from book bible content."""
        try:
            self.logger.info(f"Generating prewriting summary for project: {project_data.get('title', 'Unknown')}")
            
            # Extract book bible content
            book_bible_content = project_data.get('book_bible_content', '')
            if not book_bible_content:
                raise ValueError("Book bible content is required for summary generation")
            
            # Generate structured summary using LLM
            summary_result = await self._generate_structured_summary(book_bible_content, project_data)
            
            if not summary_result.success:
                raise Exception(f"Failed to generate structured summary: {summary_result.error}")
            
            # Parse the LLM response into structured data
            parsed_summary = self._parse_summary_response(summary_result.content, project_data)
            
            self.logger.info(f"Successfully generated prewriting summary for project: {parsed_summary.project_id}")
            return parsed_summary
            
        except Exception as e:
            self.logger.error(f"Failed to generate prewriting summary: {e}")
            raise
    
    async def _generate_structured_summary(self, book_bible_content: str, project_data: Dict[str, Any]) -> GenerationResult:
        """Use LLM to generate a structured summary from book bible content."""
        
        system_prompt = """You are an expert story analyst and writing assistant. Your task is to analyze a book bible and extract key elements into a structured format that will be used for chapter generation.

Extract and organize the following elements from the provided book bible:

1. PREMISE: Core story concept in 2-3 sentences
2. MAIN CHARACTERS: Name, role, key traits, and motivations for each major character
3. SETTING: Time period, location, world details
4. CENTRAL CONFLICT: Primary tension driving the story
5. THEMES: Key themes and messages
6. STORY STRUCTURE: Three-act breakdown with major plot points
7. CHAPTER OUTLINE: If available, extract chapter-by-chapter breakdown
8. TONE: Overall mood and voice of the story
9. TARGET AUDIENCE: Intended readership
10. WRITING STYLE: Preferred style elements
11. PACING STRATEGY: How tension and reveals should be managed

Format your response as a structured analysis that preserves all important details while making them easily accessible for chapter generation. Be comprehensive but concise."""

        user_prompt = f"""Analyze this book bible and extract the key elements:

BOOK BIBLE CONTENT:
{book_bible_content}

PROJECT SETTINGS:
- Title: {project_data.get('title', 'Unknown')}
- Genre: {project_data.get('genre', 'Fiction')}
- Target Chapters: {project_data.get('settings', {}).get('target_chapters', 25)}
- Word Count per Chapter: {project_data.get('settings', {}).get('word_count_per_chapter', 2000)}

MUST INCLUDE ELEMENTS:
{chr(10).join(project_data.get('must_include_sections', []))}

Please provide a comprehensive structured analysis that will guide chapter generation."""

        # Use the LLM orchestrator to generate the summary
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            # Make the API call using the orchestrator's internal method
            response = self.llm_orchestrator._make_api_call(
                messages=messages,
                temperature=0.3,  # Lower temperature for analytical tasks
                max_tokens=4000,
                top_p=0.9
            )
            
            content = response.choices[0].message.content
            usage = response.usage
            
            return GenerationResult(
                success=True,
                content=content,
                metadata={
                    "task": "prewriting_summary",
                    "timestamp": datetime.now().isoformat(),
                    "tokens_used": usage.total_tokens if usage else 0
                },
                tokens_used=usage.total_tokens if usage else 0,
                cost_estimate=self._calculate_cost(usage) if usage else 0.0
            )
            
        except Exception as e:
            self.logger.error(f"LLM summary generation failed: {e}")
            return GenerationResult(
                success=False,
                content="",
                metadata={"task": "prewriting_summary", "error": str(e)},
                error=str(e)
            )
    
    def _parse_summary_response(self, llm_response: str, project_data: Dict[str, Any]) -> PrewritingSummary:
        """Parse the LLM response into a structured PrewritingSummary object."""
        
        # Extract sections using regex patterns
        premise = self._extract_section(llm_response, r"(?i)premise[:\s]*(.*?)(?=\n\n|\n[A-Z]|$)", "A compelling story premise")
        
        # Parse characters - look for character descriptions
        characters = self._parse_characters(llm_response)
        
        # Parse setting
        setting = self._parse_setting(llm_response)
        
        # Extract conflict
        conflict = self._extract_section(llm_response, r"(?i)central conflict[:\s]*(.*?)(?=\n\n|\n[A-Z]|$)", "Central story conflict")
        
        # Parse themes
        themes = self._parse_themes(llm_response)
        
        # Parse structure
        structure = self._parse_story_structure(llm_response)
        
        # Parse chapter outline if available
        chapter_outline = self._parse_chapter_outline(llm_response, project_data.get('settings', {}).get('target_chapters', 25))
        
        # Extract writing guidelines
        tone = self._extract_section(llm_response, r"(?i)tone[:\s]*(.*?)(?=\n\n|\n[A-Z]|$)", "Professional")
        target_audience = self._extract_section(llm_response, r"(?i)target audience[:\s]*(.*?)(?=\n\n|\n[A-Z]|$)", "General")
        writing_style = self._extract_section(llm_response, r"(?i)writing style[:\s]*(.*?)(?=\n\n|\n[A-Z]|$)", "Professional narrative")
        pacing_strategy = self._extract_section(llm_response, r"(?i)pacing[:\s]*(.*?)(?=\n\n|\n[A-Z]|$)", "Balanced progression")
        
        return PrewritingSummary(
            project_id=project_data.get('id', 'unknown'),
            title=project_data.get('title', 'Unknown'),
            genre=project_data.get('genre', 'Fiction'),
            premise=premise,
            main_characters=characters,
            setting=setting,
            central_conflict=conflict,
            themes=themes,
            story_structure=structure,
            chapter_outline=chapter_outline,
            must_include_elements=project_data.get('must_include_sections', []),
            tone=tone,
            target_audience=target_audience,
            writing_style=writing_style,
            pacing_strategy=pacing_strategy,
            generated_at=datetime.now(),
            word_count_target=project_data.get('settings', {}).get('word_count_per_chapter', 2000),
            total_chapters=project_data.get('settings', {}).get('target_chapters', 25)
        )
    
    def _extract_section(self, text: str, pattern: str, default: str) -> str:
        """Extract a section from text using regex pattern."""
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return default
    
    def _parse_characters(self, text: str) -> List[Dict[str, str]]:
        """Parse character information from the summary."""
        characters = []
        
        # Look for character sections
        character_patterns = [
            r"(?i)main characters?[:\s]*(.*?)(?=\n\n|\n[A-Z][A-Z]|$)",
            r"(?i)characters?[:\s]*(.*?)(?=\n\n|\n[A-Z][A-Z]|$)"
        ]
        
        for pattern in character_patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                character_text = match.group(1)
                
                # Parse individual characters
                lines = character_text.split('\n')
                current_character = {}
                
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith('-') or line.startswith('•'):
                        continue
                    
                    # Look for character names and details
                    if ':' in line and not current_character:
                        name, details = line.split(':', 1)
                        current_character = {
                            'name': name.strip(),
                            'description': details.strip()
                        }
                        characters.append(current_character)
                        current_character = {}
                
                break
        
        # Fallback: create a generic character entry
        if not characters:
            characters.append({
                'name': 'Protagonist',
                'description': 'Main character driving the story forward'
            })
        
        return characters
    
    def _parse_setting(self, text: str) -> Dict[str, str]:
        """Parse setting information from the summary."""
        setting = {}
        
        setting_match = re.search(r"(?i)setting[:\s]*(.*?)(?=\n\n|\n[A-Z][A-Z]|$)", text, re.DOTALL)
        if setting_match:
            setting_text = setting_match.group(1).strip()
            setting['description'] = setting_text
            
            # Try to extract time and place if specifically mentioned
            time_match = re.search(r"(?i)time[:\s]*([^\n]+)", setting_text)
            place_match = re.search(r"(?i)place[:\s]*([^\n]+)", setting_text)
            
            if time_match:
                setting['time'] = time_match.group(1).strip()
            if place_match:
                setting['place'] = place_match.group(1).strip()
        else:
            setting['description'] = 'Contemporary setting'
        
        return setting
    
    def _parse_themes(self, text: str) -> List[str]:
        """Parse themes from the summary."""
        themes = []
        
        theme_match = re.search(r"(?i)themes?[:\s]*(.*?)(?=\n\n|\n[A-Z][A-Z]|$)", text, re.DOTALL)
        if theme_match:
            theme_text = theme_match.group(1)
            
            # Split on common delimiters
            theme_lines = re.split(r'[,\n•\-]', theme_text)
            for theme in theme_lines:
                theme = theme.strip()
                if theme and len(theme) > 3:
                    themes.append(theme)
        
        # Fallback themes
        if not themes:
            themes = ['Character growth', 'Conflict resolution']
        
        return themes[:5]  # Limit to 5 themes
    
    def _parse_story_structure(self, text: str) -> Dict[str, str]:
        """Parse story structure from the summary."""
        structure = {}
        
        structure_match = re.search(r"(?i)story structure[:\s]*(.*?)(?=\n\n|\n[A-Z][A-Z]|$)", text, re.DOTALL)
        if structure_match:
            structure_text = structure_match.group(1)
            
            # Look for act breakdowns
            act1_match = re.search(r"(?i)act (?:i|1|one)[:\s]*([^\n]+)", structure_text)
            act2_match = re.search(r"(?i)act (?:ii|2|two)[:\s]*([^\n]+)", structure_text)
            act3_match = re.search(r"(?i)act (?:iii|3|three)[:\s]*([^\n]+)", structure_text)
            
            if act1_match:
                structure['act1'] = act1_match.group(1).strip()
            if act2_match:
                structure['act2'] = act2_match.group(1).strip()
            if act3_match:
                structure['act3'] = act3_match.group(1).strip()
        
        # Provide default structure
        if not structure:
            structure = {
                'act1': 'Setup and introduction of characters and conflict',
                'act2': 'Development and escalation of conflict',
                'act3': 'Resolution and conclusion'
            }
        
        return structure
    
    def _parse_chapter_outline(self, text: str, total_chapters: int) -> List[Dict[str, Any]]:
        """Parse chapter outline if available."""
        outline = []
        
        # Look for chapter outline section
        outline_match = re.search(r"(?i)chapter outline[:\s]*(.*?)(?=\n\n|\n[A-Z][A-Z]|$)", text, re.DOTALL)
        if outline_match:
            outline_text = outline_match.group(1)
            
            # Parse individual chapters
            chapter_matches = re.findall(r"(?i)chapter (\d+)[:\s]*([^\n]+)", outline_text)
            for chapter_num, description in chapter_matches:
                outline.append({
                    'chapter': int(chapter_num),
                    'description': description.strip()
                })
        
        # Fill in missing chapters with generic descriptions
        existing_chapters = {item['chapter'] for item in outline}
        for i in range(1, total_chapters + 1):
            if i not in existing_chapters:
                outline.append({
                    'chapter': i,
                    'description': f'Chapter {i} content to be developed'
                })
        
        # Sort by chapter number
        outline.sort(key=lambda x: x['chapter'])
        return outline
    
    def _calculate_cost(self, usage) -> float:
        """Calculate the cost of the API call."""
        if not usage:
            return 0.0
        
        input_cost = (usage.prompt_tokens / 1000) * 0.005
        output_cost = (usage.completion_tokens / 1000) * 0.015
        return input_cost + output_cost
    
    def to_chapter_context(self, summary: PrewritingSummary, chapter_number: int) -> Dict[str, Any]:
        """Convert prewriting summary to chapter generation context."""
        
        # Find specific chapter info if available
        chapter_info = None
        for chapter in summary.chapter_outline:
            if chapter['chapter'] == chapter_number:
                chapter_info = chapter
                break
        
        # Determine story act based on chapter number
        act1_end = summary.total_chapters // 3
        act2_end = (summary.total_chapters * 2) // 3
        
        if chapter_number <= act1_end:
            current_act = "act1"
            act_description = summary.story_structure.get('act1', 'Setup and introduction')
        elif chapter_number <= act2_end:
            current_act = "act2"
            act_description = summary.story_structure.get('act2', 'Development and conflict')
        else:
            current_act = "act3"
            act_description = summary.story_structure.get('act3', 'Resolution and conclusion')
        
        # Build context for chapter generation
        context = {
            "chapter_number": chapter_number,
            "title": summary.title,
            "genre": summary.genre,
            "premise": summary.premise,
            "central_conflict": summary.central_conflict,
            "current_act": current_act,
            "act_description": act_description,
            "tone": summary.tone,
            "target_audience": summary.target_audience,
            "writing_style": summary.writing_style,
            "pacing_strategy": summary.pacing_strategy,
            "target_words": summary.word_count_target,
            "must_include_elements": summary.must_include_elements,
            
            # Character context
            "main_characters": [f"{char['name']}: {char['description']}" for char in summary.main_characters],
            "character_focus": summary.main_characters[0]['name'] if summary.main_characters else "Protagonist",
            
            # Setting context
            "setting": summary.setting.get('description', 'Contemporary setting'),
            "time_period": summary.setting.get('time', 'Present day'),
            "location": summary.setting.get('place', 'Urban setting'),
            
            # Chapter-specific context
            "chapter_description": chapter_info['description'] if chapter_info else f"Chapter {chapter_number} development",
            "themes": summary.themes,
            
            # Progress context
            "total_chapters": summary.total_chapters,
            "progress_percentage": (chapter_number / summary.total_chapters) * 100
        }
        
        return context 