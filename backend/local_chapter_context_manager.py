#!/usr/bin/env python3
"""
Chapter Context Manager - FastAPI Backend Version
Manages context continuity between chapters during auto-completion.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ChapterContext:
    """Context information for a chapter."""
    chapter_number: int
    word_count: int
    key_events: List[str]
    characters_introduced: List[str]
    plot_threads: List[str]
    theme_elements: List[str]
    setting_details: Dict[str, Any]
    character_development: Dict[str, str]
    quality_score: float
    timestamp: str

class ChapterContextManager:
    """
    Manages context continuity between chapters.
    Simplified version for FastAPI backend.
    """
    
    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.context_file = self.project_path / ".project-state" / "chapter-context.json"
        self.chapters_dir = self.project_path / "chapters"
        
        # Create necessary directories
        self.context_file.parent.mkdir(parents=True, exist_ok=True)
        self.chapters_dir.mkdir(parents=True, exist_ok=True)
        
        # Context storage
        self.chapter_contexts: Dict[int, ChapterContext] = {}
        self.story_continuity: Dict[str, Any] = {}
        
        # Setup logging
        self.logger = logger
        
        # Load existing context
        self._load_context()
    
    def _load_context(self):
        """Load existing context from file."""
        if self.context_file.exists():
            try:
                with open(self.context_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Load chapter contexts
                for chapter_num, context_data in data.get('chapter_contexts', {}).items():
                    context = ChapterContext(
                        chapter_number=int(chapter_num),
                        word_count=context_data.get('word_count', 0),
                        key_events=context_data.get('key_events', []),
                        characters_introduced=context_data.get('characters_introduced', []),
                        plot_threads=context_data.get('plot_threads', []),
                        theme_elements=context_data.get('theme_elements', []),
                        setting_details=context_data.get('setting_details', {}),
                        character_development=context_data.get('character_development', {}),
                        quality_score=context_data.get('quality_score', 0.0),
                        timestamp=context_data.get('timestamp', '')
                    )
                    self.chapter_contexts[int(chapter_num)] = context
                
                # Load story continuity
                self.story_continuity = data.get('story_continuity', {})
                
                self.logger.info(f"Loaded context for {len(self.chapter_contexts)} chapters")
                
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                self.logger.warning(f"Failed to load context: {e}")
                self._initialize_default_context()
        else:
            self._initialize_default_context()
    
    def _initialize_default_context(self):
        """Initialize default context structure."""
        self.story_continuity = {
            'main_characters': [],
            'active_plot_threads': [],
            'world_building_elements': {},
            'theme_tracking': {},
            'timeline_events': [],
            'character_relationships': {},
            'settings_visited': [],
            'story_arc_progress': 0.0,
            'tone_consistency': {},
            'last_updated': datetime.utcnow().isoformat()
        }
    
    def _save_context(self):
        """Save current context to file."""
        data = {
            'chapter_contexts': {},
            'story_continuity': self.story_continuity,
            'metadata': {
                'last_updated': datetime.utcnow().isoformat(),
                'total_chapters': len(self.chapter_contexts)
            }
        }
        
        # Convert chapter contexts to dict
        for chapter_num, context in self.chapter_contexts.items():
            data['chapter_contexts'][str(chapter_num)] = asdict(context)
        
        # Save to file
        with open(self.context_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def add_chapter_context(self, chapter_number: int, chapter_content: str, 
                          quality_result: Dict[str, Any]) -> ChapterContext:
        """
        Add context for a newly generated chapter.
        
        Args:
            chapter_number: Chapter number
            chapter_content: Full chapter content
            quality_result: Quality assessment results
            
        Returns:
            ChapterContext object
        """
        # Extract context from chapter content
        context_data = self._extract_chapter_context(chapter_content)
        
        # Create chapter context
        context = ChapterContext(
            chapter_number=chapter_number,
            word_count=len(chapter_content.split()),
            key_events=context_data['key_events'],
            characters_introduced=context_data['characters_introduced'],
            plot_threads=context_data['plot_threads'],
            theme_elements=context_data['theme_elements'],
            setting_details=context_data['setting_details'],
            character_development=context_data['character_development'],
            quality_score=quality_result.get('overall_score', 0.0),
            timestamp=datetime.utcnow().isoformat()
        )
        
        # Store context
        self.chapter_contexts[chapter_number] = context
        
        # Update story continuity
        self._update_story_continuity(context)
        
        # Save to file
        self._save_context()
        
        self.logger.info(f"Added context for Chapter {chapter_number}")
        return context
    
    def _extract_chapter_context(self, chapter_content: str) -> Dict[str, Any]:
        """
        Extract context information from chapter content.
        Simplified version using basic text analysis.
        """
        # This is a simplified version - in production, this would use NLP
        # and more sophisticated analysis
        
        lines = chapter_content.split('\n')
        paragraphs = [p.strip() for p in chapter_content.split('\n\n') if p.strip()]
        
        # Basic extraction
        context_data = {
            'key_events': [],
            'characters_introduced': [],
            'plot_threads': [],
            'theme_elements': [],
            'setting_details': {},
            'character_development': {}
        }
        
        # Look for action verbs and events (simplified)
        action_keywords = ['entered', 'discovered', 'revealed', 'confronted', 'decided', 'realized']
        for paragraph in paragraphs:
            for keyword in action_keywords:
                if keyword in paragraph.lower():
                    event = paragraph[:100] + "..." if len(paragraph) > 100 else paragraph
                    context_data['key_events'].append(event)
                    break
        
        # Look for character names (simplified - capitalized words)
        words = chapter_content.split()
        potential_names = [word for word in words if word.isalpha() and word[0].isupper() and len(word) > 2]
        unique_names = list(set(potential_names))[:5]  # Limit to 5 potential names
        context_data['characters_introduced'] = unique_names
        
        # Basic plot thread detection
        plot_keywords = ['mystery', 'conflict', 'journey', 'quest', 'secret', 'danger']
        for keyword in plot_keywords:
            if keyword in chapter_content.lower():
                context_data['plot_threads'].append(f"Story element: {keyword}")
        
        # Basic theme detection
        theme_keywords = ['love', 'betrayal', 'friendship', 'courage', 'sacrifice', 'justice']
        for keyword in theme_keywords:
            if keyword in chapter_content.lower():
                context_data['theme_elements'].append(keyword)
        
        return context_data
    
    def _update_story_continuity(self, context: ChapterContext):
        """Update overall story continuity tracking."""
        # Update main characters
        for char in context.characters_introduced:
            if char not in self.story_continuity['main_characters']:
                self.story_continuity['main_characters'].append(char)
        
        # Update active plot threads
        for thread in context.plot_threads:
            if thread not in self.story_continuity['active_plot_threads']:
                self.story_continuity['active_plot_threads'].append(thread)
        
        # Update theme tracking
        for theme in context.theme_elements:
            if theme not in self.story_continuity['theme_tracking']:
                self.story_continuity['theme_tracking'][theme] = []
            self.story_continuity['theme_tracking'][theme].append(context.chapter_number)
        
        # Update story arc progress
        total_chapters = len(self.chapter_contexts)
        self.story_continuity['story_arc_progress'] = total_chapters / 20.0  # Assume 20 chapter target
        
        # Update last updated
        self.story_continuity['last_updated'] = datetime.utcnow().isoformat()
    
    def get_chapter_context(self, chapter_number: int) -> Optional[ChapterContext]:
        """Get context for a specific chapter."""
        return self.chapter_contexts.get(chapter_number)
    
    def get_previous_chapters_context(self, up_to_chapter: int) -> List[ChapterContext]:
        """Get context for all chapters up to a specific chapter."""
        contexts = []
        for i in range(1, up_to_chapter):
            context = self.chapter_contexts.get(i)
            if context:
                contexts.append(context)
        return contexts
    
    def build_generation_context(self, chapter_number: int) -> Dict[str, Any]:
        """
        Build context for generating a new chapter.
        
        Args:
            chapter_number: Chapter number to generate
            
        Returns:
            Context dictionary for chapter generation
        """
        previous_contexts = self.get_previous_chapters_context(chapter_number)
        
        # Build comprehensive context
        generation_context = {
            'chapter_number': chapter_number,
            'previous_chapters_count': len(previous_contexts),
            'story_continuity': self.story_continuity,
            'previous_chapters_summary': self._build_chapters_summary(previous_contexts),
            'active_characters': self.story_continuity['main_characters'],
            'active_plot_threads': self.story_continuity['active_plot_threads'],
            'story_arc_progress': self.story_continuity['story_arc_progress'],
            'theme_consistency': self.story_continuity['theme_tracking'],
            'last_chapter_events': self._get_last_chapter_events(chapter_number - 1) if chapter_number > 1 else []
        }
        
        return generation_context
    
    def _build_chapters_summary(self, contexts: List[ChapterContext]) -> str:
        """Build a summary of previous chapters."""
        if not contexts:
            return "This is the first chapter."
        
        summary_parts = []
        for context in contexts[-3:]:  # Use last 3 chapters for summary
            events_summary = "; ".join(context.key_events[:2])  # Top 2 events
            summary_parts.append(f"Chapter {context.chapter_number}: {events_summary}")
        
        return "\n".join(summary_parts)
    
    def _get_last_chapter_events(self, chapter_number: int) -> List[str]:
        """Get key events from the last chapter."""
        context = self.chapter_contexts.get(chapter_number)
        return context.key_events if context else []
    
    def get_continuity_analysis(self) -> Dict[str, Any]:
        """Get analysis of story continuity."""
        return {
            'total_chapters': len(self.chapter_contexts),
            'story_arc_progress': self.story_continuity['story_arc_progress'],
            'character_count': len(self.story_continuity['main_characters']),
            'active_plot_threads': len(self.story_continuity['active_plot_threads']),
            'theme_diversity': len(self.story_continuity['theme_tracking']),
            'average_chapter_quality': self._calculate_average_quality(),
            'context_consistency_score': self._calculate_consistency_score()
        }
    
    def _calculate_average_quality(self) -> float:
        """Calculate average quality score across all chapters."""
        if not self.chapter_contexts:
            return 0.0
        
        total_quality = sum(context.quality_score for context in self.chapter_contexts.values())
        return total_quality / len(self.chapter_contexts)
    
    def _calculate_consistency_score(self) -> float:
        """Calculate a basic consistency score."""
        if len(self.chapter_contexts) < 2:
            return 1.0
        
        # Simple consistency based on character and theme continuity
        base_score = 0.8
        
        # Bonus for character continuity
        if len(self.story_continuity['main_characters']) >= 3:
            base_score += 0.1
        
        # Bonus for theme consistency
        if len(self.story_continuity['theme_tracking']) >= 2:
            base_score += 0.1
        
        return min(base_score, 1.0)
    
    def reset_context(self):
        """Reset all context data."""
        self.chapter_contexts.clear()
        self._initialize_default_context()
        self._save_context()
        self.logger.info("Context reset")
    
    def export_context(self) -> Dict[str, Any]:
        """Export all context data."""
        return {
            'chapter_contexts': {str(k): asdict(v) for k, v in self.chapter_contexts.items()},
            'story_continuity': self.story_continuity,
            'analysis': self.get_continuity_analysis()
        } 