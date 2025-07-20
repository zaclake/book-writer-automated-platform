#!/usr/bin/env python3
"""
Chapter Context Manager
Manages story continuity, character development, and context between sequential chapters.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict


@dataclass
class CharacterState:
    """Tracks the state and development of a character."""
    name: str
    first_appearance: int
    last_appearance: int
    development_arc: List[str]
    relationships: Dict[str, str]
    current_goals: List[str]
    resolved_conflicts: List[str]
    personality_traits: List[str]
    dialogue_patterns: List[str]
    physical_descriptions: List[str]
    emotional_state: str
    location: Optional[str] = None


@dataclass
class PlotThread:
    """Tracks a plot thread across chapters."""
    thread_id: str
    title: str
    start_chapter: int
    current_status: str  # "active", "resolved", "paused", "abandoned"
    resolution_chapter: Optional[int]
    key_events: List[Dict[str, Any]]
    related_characters: List[str]
    urgency_level: str  # "high", "medium", "low"
    completion_percentage: float


@dataclass
class WorldState:
    """Tracks the state of the world/setting."""
    locations: Dict[str, Dict[str, Any]]
    time_progression: List[Dict[str, Any]]
    world_rules: Dict[str, Any]
    established_facts: List[Dict[str, Any]]
    ongoing_situations: List[Dict[str, Any]]
    environment_changes: List[Dict[str, Any]]


@dataclass
class ChapterContext:
    """Complete context for a chapter."""
    chapter_number: int
    summary: str
    word_count: int
    key_events: List[str]
    characters_present: List[str]
    new_information: List[str]
    plot_advancement: Dict[str, float]
    emotional_tone: str
    themes_explored: List[str]
    cliffhangers: List[str]
    questions_raised: List[str]
    questions_answered: List[str]
    timestamp: str


class ChapterContextManager:
    """
    Manages comprehensive context and continuity across sequential chapter generation.
    
    Features:
    - Character development tracking and consistency
    - Plot thread management and advancement
    - World state evolution
    - Theme continuity
    - Context optimization for next chapter generation
    """
    
    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.state_dir = self.project_path / ".project-state"
        self.chapters_dir = self.project_path / "chapters"
        
        # Context state files
        self.context_file = self.state_dir / "chapter-contexts.json"
        self.characters_file = self.state_dir / "character-states.json"
        self.plot_threads_file = self.state_dir / "plot-threads.json"
        self.world_state_file = self.state_dir / "world-state.json"
        
        # Ensure directories exist
        self.state_dir.mkdir(exist_ok=True)
        
        # Load existing state
        self.chapter_contexts: Dict[int, ChapterContext] = self._load_chapter_contexts()
        self.character_states: Dict[str, CharacterState] = self._load_character_states()
        self.plot_threads: Dict[str, PlotThread] = self._load_plot_threads()
        self.world_state: WorldState = self._load_world_state()
    
    def _load_chapter_contexts(self) -> Dict[int, ChapterContext]:
        """Load chapter contexts from file."""
        if not self.context_file.exists():
            return {}
        
        try:
            with open(self.context_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            contexts = {}
            for chapter_num_str, context_data in data.items():
                chapter_num = int(chapter_num_str)
                contexts[chapter_num] = ChapterContext(**context_data)
            
            return contexts
        except (json.JSONDecodeError, KeyError, ValueError):
            return {}
    
    def _load_character_states(self) -> Dict[str, CharacterState]:
        """Load character states from file."""
        if not self.characters_file.exists():
            return {}
        
        try:
            with open(self.characters_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            characters = {}
            for name, character_data in data.items():
                characters[name] = CharacterState(**character_data)
            
            return characters
        except (json.JSONDecodeError, KeyError, ValueError):
            return {}
    
    def _load_plot_threads(self) -> Dict[str, PlotThread]:
        """Load plot threads from file."""
        if not self.plot_threads_file.exists():
            return {}
        
        try:
            with open(self.plot_threads_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            threads = {}
            for thread_id, thread_data in data.items():
                threads[thread_id] = PlotThread(**thread_data)
            
            return threads
        except (json.JSONDecodeError, KeyError, ValueError):
            return {}
    
    def _load_world_state(self) -> WorldState:
        """Load world state from file."""
        if not self.world_state_file.exists():
            return WorldState(
                locations={},
                time_progression=[],
                world_rules={},
                established_facts=[],
                ongoing_situations=[],
                environment_changes=[]
            )
        
        try:
            with open(self.world_state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return WorldState(**data)
        except (json.JSONDecodeError, KeyError, ValueError):
            return WorldState(
                locations={},
                time_progression=[],
                world_rules={},
                established_facts=[],
                ongoing_situations=[],
                environment_changes=[]
            )
    
    def _save_all_state(self):
        """Save all context state to files."""
        # Save chapter contexts
        contexts_data = {}
        for chapter_num, context in self.chapter_contexts.items():
            contexts_data[str(chapter_num)] = asdict(context)
        
        with open(self.context_file, 'w', encoding='utf-8') as f:
            json.dump(contexts_data, f, indent=2, ensure_ascii=False)
        
        # Save character states
        characters_data = {}
        for name, character in self.character_states.items():
            characters_data[name] = asdict(character)
        
        with open(self.characters_file, 'w', encoding='utf-8') as f:
            json.dump(characters_data, f, indent=2, ensure_ascii=False)
        
        # Save plot threads
        threads_data = {}
        for thread_id, thread in self.plot_threads.items():
            threads_data[thread_id] = asdict(thread)
        
        with open(self.plot_threads_file, 'w', encoding='utf-8') as f:
            json.dump(threads_data, f, indent=2, ensure_ascii=False)
        
        # Save world state
        with open(self.world_state_file, 'w', encoding='utf-8') as f:
            json.dump(asdict(self.world_state), f, indent=2, ensure_ascii=False)
    
    def analyze_chapter_content(self, chapter_number: int, chapter_content: str) -> ChapterContext:
        """Analyze chapter content and extract context information."""
        
        # Basic analysis
        word_count = len(chapter_content.split())
        summary = self._extract_chapter_summary(chapter_content)
        
        # Extract characters
        characters_present = self._extract_characters(chapter_content)
        
        # Extract key events
        key_events = self._extract_key_events(chapter_content)
        
        # Analyze emotional tone
        emotional_tone = self._analyze_emotional_tone(chapter_content)
        
        # Extract themes
        themes_explored = self._extract_themes(chapter_content)
        
        # Extract questions and cliffhangers
        cliffhangers = self._extract_cliffhangers(chapter_content)
        questions_raised = self._extract_questions_raised(chapter_content)
        questions_answered = self._extract_questions_answered(chapter_content, chapter_number)
        
        # Identify new information
        new_information = self._extract_new_information(chapter_content, chapter_number)
        
        # Analyze plot advancement
        plot_advancement = self._analyze_plot_advancement(chapter_content, chapter_number)
        
        # Create chapter context
        context = ChapterContext(
            chapter_number=chapter_number,
            summary=summary,
            word_count=word_count,
            key_events=key_events,
            characters_present=characters_present,
            new_information=new_information,
            plot_advancement=plot_advancement,
            emotional_tone=emotional_tone,
            themes_explored=themes_explored,
            cliffhangers=cliffhangers,
            questions_raised=questions_raised,
            questions_answered=questions_answered,
            timestamp=datetime.now().isoformat()
        )
        
        # Store context
        self.chapter_contexts[chapter_number] = context
        
        # Update character states
        self._update_character_states(chapter_number, chapter_content, characters_present)
        
        # Update plot threads
        self._update_plot_threads(chapter_number, chapter_content, key_events)
        
        # Update world state
        self._update_world_state(chapter_number, chapter_content)
        
        # Save all state
        self._save_all_state()
        
        return context
    
    def build_next_chapter_context(self, next_chapter_number: int) -> Dict[str, Any]:
        """Build comprehensive context for generating the next chapter."""
        
        # Get previous chapter context
        previous_contexts = [
            context for chapter_num, context in self.chapter_contexts.items()
            if chapter_num < next_chapter_number
        ]
        previous_contexts.sort(key=lambda c: c.chapter_number)
        
        # Build context
        context = {
            "chapter_number": next_chapter_number,
            "previous_chapters_count": len(previous_contexts),
            "story_so_far": self._build_story_summary(previous_contexts),
            "character_continuity": self._build_character_continuity_context(),
            "plot_threads": self._build_plot_threads_context(),
            "world_state": self._build_world_state_context(),
            "themes_to_continue": self._get_ongoing_themes(),
            "unresolved_questions": self._get_unresolved_questions(),
            "required_plot_advancement": self._determine_required_plot_advancement(next_chapter_number),
            "character_development_needs": self._determine_character_development_needs(),
            "pacing_guidance": self._generate_pacing_guidance(next_chapter_number),
            "continuity_requirements": self._generate_continuity_requirements(),
            "context_quality_score": self._calculate_context_quality_score()
        }
        
        return context
    
    def _extract_chapter_summary(self, chapter_content: str) -> str:
        """Extract a brief summary of the chapter."""
        # Use first paragraph or first 200 words as summary
        paragraphs = chapter_content.split('\n\n')
        if paragraphs:
            summary = paragraphs[0]
            if len(summary.split()) > 50:
                words = summary.split()[:50]
                summary = ' '.join(words) + '...'
            return summary
        else:
            words = chapter_content.split()[:50]
            return ' '.join(words) + '...'
    
    def _extract_characters(self, chapter_content: str) -> List[str]:
        """Extract character names from chapter content."""
        # Look for capitalized names and dialogue speakers
        name_patterns = [
            r'\b[A-Z][a-z]+\b(?:\s+[A-Z][a-z]+)*',  # Capitalized names
            r'"[^"]*",?\s*([A-Z][a-z]+)\s+(?:said|asked|replied|shouted|whispered)',  # Dialogue speakers
        ]
        
        names = set()
        for pattern in name_patterns:
            matches = re.findall(pattern, chapter_content)
            names.update(matches)
        
        # Filter out common words
        common_words = {
            'The', 'He', 'She', 'It', 'They', 'We', 'You', 'I',
            'But', 'And', 'Or', 'So', 'Then', 'Now', 'Here', 'There',
            'This', 'That', 'These', 'Those', 'When', 'Where', 'Why',
            'How', 'What', 'Who', 'Which', 'Chapter', 'Book', 'Story'
        }
        
        filtered_names = [name for name in names if name not in common_words and len(name) > 2]
        return sorted(list(set(filtered_names)))
    
    def _extract_key_events(self, chapter_content: str) -> List[str]:
        """Extract key events from chapter content."""
        # Look for action verbs and significant events
        event_patterns = [
            r'\b(?:discovered|found|realized|learned|understood|revealed)\b[^.!?]*[.!?]',
            r'\b(?:decided|chose|agreed|refused|accepted|rejected)\b[^.!?]*[.!?]',
            r'\b(?:met|confronted|faced|encountered|attacked|defended)\b[^.!?]*[.!?]',
            r'\b(?:arrived|left|departed|entered|exited|escaped)\b[^.!?]*[.!?]',
            r'\b(?:died|killed|murdered|injured|wounded)\b[^.!?]*[.!?]'
        ]
        
        events = []
        for pattern in event_patterns:
            matches = re.findall(pattern, chapter_content, re.IGNORECASE)
            events.extend([match.strip() for match in matches])
        
        # Limit to most significant events
        return events[:10]
    
    def _analyze_emotional_tone(self, chapter_content: str) -> str:
        """Analyze the emotional tone of the chapter."""
        tone_indicators = {
            'dark': ['death', 'murder', 'violence', 'danger', 'threat', 'fear', 'terror'],
            'suspenseful': ['mystery', 'unknown', 'hidden', 'secret', 'question', 'wonder'],
            'hopeful': ['hope', 'light', 'better', 'improve', 'positive', 'optimistic'],
            'romantic': ['love', 'heart', 'kiss', 'passion', 'romance', 'tender'],
            'action': ['run', 'fight', 'chase', 'escape', 'battle', 'struggle'],
            'reflective': ['thought', 'remember', 'consider', 'reflect', 'ponder'],
            'tense': ['urgent', 'pressure', 'stress', 'tension', 'anxiety', 'worry']
        }
        
        content_lower = chapter_content.lower()
        tone_scores = {}
        
        for tone, indicators in tone_indicators.items():
            score = sum(1 for indicator in indicators if indicator in content_lower)
            tone_scores[tone] = score
        
        # Return dominant tone
        if tone_scores:
            return max(tone_scores, key=tone_scores.get)
        else:
            return 'neutral'
    
    def _extract_themes(self, chapter_content: str) -> List[str]:
        """Extract themes explored in the chapter."""
        theme_indicators = {
            'justice': ['justice', 'right', 'wrong', 'fair', 'unfair', 'law', 'crime'],
            'truth': ['truth', 'lie', 'honest', 'deception', 'reveal', 'hidden'],
            'power': ['power', 'control', 'authority', 'influence', 'dominance'],
            'loyalty': ['loyal', 'betray', 'trust', 'faithful', 'allegiance'],
            'sacrifice': ['sacrifice', 'give up', 'loss', 'cost', 'price'],
            'redemption': ['redeem', 'forgive', 'atone', 'make up', 'second chance'],
            'survival': ['survive', 'danger', 'threat', 'escape', 'safety']
        }
        
        content_lower = chapter_content.lower()
        themes = []
        
        for theme, indicators in theme_indicators.items():
            if any(indicator in content_lower for indicator in indicators):
                themes.append(theme)
        
        return themes
    
    def _extract_cliffhangers(self, chapter_content: str) -> List[str]:
        """Extract cliffhangers from chapter ending."""
        # Look at the last few paragraphs
        paragraphs = chapter_content.split('\n\n')
        ending_paragraphs = paragraphs[-3:] if len(paragraphs) >= 3 else paragraphs
        ending_text = '\n\n'.join(ending_paragraphs)
        
        cliffhanger_patterns = [
            r'[.!?]\s*$',  # Ends with punctuation (check for dramatic statements)
            r'\?\s*$',     # Ends with question
            r'\.{3}\s*$',  # Ends with ellipsis
            r'!\s*$'       # Ends with exclamation
        ]
        
        cliffhangers = []
        
        # Look for specific cliffhanger indicators
        cliffhanger_indicators = [
            'but then', 'suddenly', 'however', 'until', 'unless',
            'would never', 'couldn\'t', 'shouldn\'t', 'question',
            'mystery', 'danger', 'threat', 'unknown', 'secret'
        ]
        
        ending_lower = ending_text.lower()
        for indicator in cliffhanger_indicators:
            if indicator in ending_lower:
                # Extract sentence containing the indicator
                sentences = re.split(r'[.!?]', ending_text)
                for sentence in sentences:
                    if indicator in sentence.lower():
                        cliffhangers.append(sentence.strip())
        
        return cliffhangers[:3]  # Limit to top 3
    
    def _extract_questions_raised(self, chapter_content: str) -> List[str]:
        """Extract questions raised in the chapter."""
        # Look for direct questions
        direct_questions = re.findall(r'[^.!?]*\?', chapter_content)
        
        # Look for indirect questions/mysteries
        mystery_patterns = [
            r'(?:wonder|question|mystery|unknown|secret|hidden)[^.!?]*[.!?]',
            r'(?:why|how|what|who|where|when)[^.!?]*[.!?]',
            r'(?:doesn\'t|couldn\'t|wouldn\'t|shouldn\'t)[^.!?]*[.!?]'
        ]
        
        indirect_questions = []
        for pattern in mystery_patterns:
            matches = re.findall(pattern, chapter_content, re.IGNORECASE)
            indirect_questions.extend(matches)
        
        all_questions = direct_questions + indirect_questions
        return [q.strip() for q in all_questions[:10]]  # Limit to 10 questions
    
    def _extract_questions_answered(self, chapter_content: str, chapter_number: int) -> List[str]:
        """Extract questions that were answered in this chapter."""
        answered = []
        
        # Get previous unresolved questions
        previous_questions = []
        for prev_chapter_num in range(1, chapter_number):
            if prev_chapter_num in self.chapter_contexts:
                context = self.chapter_contexts[prev_chapter_num]
                previous_questions.extend(context.questions_raised)
        
        # Check if any previous questions are addressed in current content
        content_lower = chapter_content.lower()
        for question in previous_questions:
            # Simple keyword matching (could be improved with NLP)
            question_keywords = [word.lower() for word in question.split() 
                               if len(word) > 3 and word.isalpha()]
            
            if len(question_keywords) > 0:
                keyword_matches = sum(1 for keyword in question_keywords 
                                    if keyword in content_lower)
                if keyword_matches >= len(question_keywords) * 0.6:  # 60% match threshold
                    answered.append(question)
        
        return answered
    
    def _extract_new_information(self, chapter_content: str, chapter_number: int) -> List[str]:
        """Extract new information revealed in this chapter."""
        revelation_patterns = [
            r'(?:discovered|found|learned|realized|revealed|understood)[^.!?]*[.!?]',
            r'(?:turns out|it was|actually|in fact|the truth)[^.!?]*[.!?]',
            r'(?:secret|hidden|unknown|mysterious)[^.!?]*[.!?]'
        ]
        
        new_info = []
        for pattern in revelation_patterns:
            matches = re.findall(pattern, chapter_content, re.IGNORECASE)
            new_info.extend([match.strip() for match in matches])
        
        return new_info[:8]  # Limit to 8 pieces of new information
    
    def _analyze_plot_advancement(self, chapter_content: str, chapter_number: int) -> Dict[str, float]:
        """Analyze how much each plot thread advanced in this chapter."""
        advancement = {}
        
        # For each active plot thread, estimate advancement
        for thread_id, thread in self.plot_threads.items():
            if thread.current_status == "active":
                # Calculate advancement based on keyword presence and events
                thread_keywords = thread.title.lower().split()
                content_lower = chapter_content.lower()
                
                keyword_matches = sum(1 for keyword in thread_keywords 
                                    if keyword in content_lower)
                advancement_score = min(keyword_matches / len(thread_keywords), 1.0)
                
                advancement[thread_id] = advancement_score
        
        return advancement
    
    def _update_character_states(self, chapter_number: int, chapter_content: str, characters_present: List[str]):
        """Update character states based on chapter content."""
        for character_name in characters_present:
            if character_name not in self.character_states:
                # Create new character
                self.character_states[character_name] = CharacterState(
                    name=character_name,
                    first_appearance=chapter_number,
                    last_appearance=chapter_number,
                    development_arc=[],
                    relationships={},
                    current_goals=[],
                    resolved_conflicts=[],
                    personality_traits=[],
                    dialogue_patterns=[],
                    physical_descriptions=[],
                    emotional_state="unknown"
                )
            else:
                # Update existing character
                character = self.character_states[character_name]
                character.last_appearance = chapter_number
                
                # Extract dialogue for this character
                dialogue_pattern = rf'"{character_name}[^"]*"'
                dialogues = re.findall(dialogue_pattern, chapter_content, re.IGNORECASE)
                character.dialogue_patterns.extend(dialogues[-3:])  # Keep recent dialogue
                
                # Update emotional state based on context
                character.emotional_state = self._analyze_character_emotion(character_name, chapter_content)
    
    def _update_plot_threads(self, chapter_number: int, chapter_content: str, key_events: List[str]):
        """Update plot threads based on chapter events."""
        # This is a simplified implementation
        # In a real system, this would use more sophisticated NLP
        
        for thread_id, thread in self.plot_threads.items():
            if thread.current_status == "active":
                # Check if any key events relate to this thread
                thread_keywords = thread.title.lower().split()
                
                for event in key_events:
                    event_lower = event.lower()
                    if any(keyword in event_lower for keyword in thread_keywords):
                        # Add event to thread
                        thread.key_events.append({
                            "chapter": chapter_number,
                            "event": event,
                            "timestamp": datetime.now().isoformat()
                        })
                        
                        # Update completion percentage
                        thread.completion_percentage = min(thread.completion_percentage + 10, 90)
    
    def _update_world_state(self, chapter_number: int, chapter_content: str):
        """Update world state based on chapter content."""
        # Extract locations mentioned
        location_patterns = [
            r'\b(?:at|in|to|from)\s+(?:the\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b',
            r'\b([A-Z][a-z]+\s+(?:House|Building|Office|Street|Road|Avenue|Park|Hotel|Restaurant))\b'
        ]
        
        for pattern in location_patterns:
            matches = re.findall(pattern, chapter_content)
            for location in matches:
                if location not in self.world_state.locations:
                    self.world_state.locations[location] = {
                        "first_mentioned": chapter_number,
                        "description": "",
                        "importance": "minor"
                    }
        
        # Add time progression entry
        self.world_state.time_progression.append({
            "chapter": chapter_number,
            "relative_time": "continues",
            "duration": "unknown",
            "timestamp": datetime.now().isoformat()
        })
    
    def _build_story_summary(self, previous_contexts: List[ChapterContext]) -> str:
        """Build a comprehensive story summary from previous chapters."""
        if not previous_contexts:
            return "This is the beginning of the story."
        
        summary_parts = []
        for context in previous_contexts[-3:]:  # Use last 3 chapters for summary
            summary_parts.append(f"Chapter {context.chapter_number}: {context.summary}")
        
        return "\n".join(summary_parts)
    
    def _build_character_continuity_context(self) -> Dict[str, Any]:
        """Build character continuity context for next chapter."""
        active_characters = {}
        
        for name, character in self.character_states.items():
            # Include characters that appeared recently
            if len(self.chapter_contexts) - character.last_appearance <= 3:
                active_characters[name] = {
                    "last_appearance": character.last_appearance,
                    "emotional_state": character.emotional_state,
                    "current_goals": character.current_goals,
                    "recent_dialogue_style": character.dialogue_patterns[-2:] if character.dialogue_patterns else [],
                    "unresolved_conflicts": character.resolved_conflicts
                }
        
        return active_characters
    
    def _build_plot_threads_context(self) -> Dict[str, Any]:
        """Build plot threads context for next chapter."""
        threads_context = {}
        
        for thread_id, thread in self.plot_threads.items():
            if thread.current_status == "active":
                threads_context[thread_id] = {
                    "title": thread.title,
                    "urgency_level": thread.urgency_level,
                    "completion_percentage": thread.completion_percentage,
                    "recent_events": thread.key_events[-2:] if thread.key_events else [],
                    "related_characters": thread.related_characters
                }
        
        return threads_context
    
    def _build_world_state_context(self) -> Dict[str, Any]:
        """Build world state context for next chapter."""
        return {
            "established_locations": list(self.world_state.locations.keys()),
            "ongoing_situations": self.world_state.ongoing_situations,
            "recent_time_progression": self.world_state.time_progression[-3:],
            "world_rules": self.world_state.world_rules
        }
    
    def _get_ongoing_themes(self) -> List[str]:
        """Get themes that should continue in the next chapter."""
        if not self.chapter_contexts:
            return []
        
        # Collect themes from recent chapters
        recent_themes = []
        for context in list(self.chapter_contexts.values())[-3:]:
            recent_themes.extend(context.themes_explored)
        
        # Return most common themes
        theme_counts = defaultdict(int)
        for theme in recent_themes:
            theme_counts[theme] += 1
        
        return [theme for theme, count in theme_counts.items() if count >= 2]
    
    def _get_unresolved_questions(self) -> List[str]:
        """Get questions that remain unresolved."""
        all_raised = []
        all_answered = []
        
        for context in self.chapter_contexts.values():
            all_raised.extend(context.questions_raised)
            all_answered.extend(context.questions_answered)
        
        # Simple set difference (could be improved with semantic matching)
        unresolved = [q for q in all_raised if q not in all_answered]
        return unresolved[-10:]  # Return most recent 10 unresolved questions
    
    def _determine_required_plot_advancement(self, next_chapter_number: int) -> Dict[str, str]:
        """Determine what plot advancement is required for the next chapter."""
        advancement_needed = {}
        
        for thread_id, thread in self.plot_threads.items():
            if thread.current_status == "active":
                if thread.completion_percentage < 30:
                    advancement_needed[thread_id] = "significant_development"
                elif thread.completion_percentage < 60:
                    advancement_needed[thread_id] = "moderate_development"
                elif thread.completion_percentage < 90:
                    advancement_needed[thread_id] = "minor_development"
                else:
                    advancement_needed[thread_id] = "resolution_needed"
        
        return advancement_needed
    
    def _determine_character_development_needs(self) -> Dict[str, List[str]]:
        """Determine character development needs for the next chapter."""
        development_needs = {}
        
        for name, character in self.character_states.items():
            needs = []
            
            # Characters who haven't appeared recently need attention
            if len(self.chapter_contexts) - character.last_appearance > 2:
                needs.append("needs_appearance")
            
            # Characters with few development arc entries need growth
            if len(character.development_arc) < 3:
                needs.append("needs_development")
            
            # Characters with unresolved conflicts
            if character.resolved_conflicts:
                needs.append("has_conflicts_to_resolve")
            
            if needs:
                development_needs[name] = needs
        
        return development_needs
    
    def _generate_pacing_guidance(self, next_chapter_number: int) -> Dict[str, str]:
        """Generate pacing guidance for the next chapter."""
        guidance = {}
        
        # Analyze recent chapter lengths and pacing
        recent_chapters = [c for c in self.chapter_contexts.values() 
                          if c.chapter_number >= next_chapter_number - 3]
        
        if recent_chapters:
            avg_word_count = sum(c.word_count for c in recent_chapters) / len(recent_chapters)
            
            if avg_word_count < 3000:
                guidance["length"] = "consider_longer_chapter"
            elif avg_word_count > 5000:
                guidance["length"] = "consider_shorter_chapter"
            else:
                guidance["length"] = "maintain_current_length"
            
            # Analyze emotional tone patterns
            recent_tones = [c.emotional_tone for c in recent_chapters]
            if all(tone == "dark" for tone in recent_tones):
                guidance["tone"] = "consider_lighter_moment"
            elif all(tone == "hopeful" for tone in recent_tones):
                guidance["tone"] = "consider_adding_tension"
            else:
                guidance["tone"] = "maintain_variety"
        
        return guidance
    
    def _generate_continuity_requirements(self) -> List[str]:
        """Generate specific continuity requirements for the next chapter."""
        requirements = []
        
        # Check for characters that need follow-up
        for name, character in self.character_states.items():
            if character.current_goals and len(self.chapter_contexts) - character.last_appearance <= 1:
                requirements.append(f"Address {name}'s current goals: {', '.join(character.current_goals)}")
        
        # Check for plot threads needing attention
        for thread_id, thread in self.plot_threads.items():
            if thread.current_status == "active" and thread.urgency_level == "high":
                requirements.append(f"Advance high-priority plot thread: {thread.title}")
        
        # Check for unresolved questions that have been pending too long
        unresolved = self._get_unresolved_questions()
        if len(unresolved) > 8:
            requirements.append("Consider answering some pending questions to avoid reader confusion")
        
        return requirements
    
    def _calculate_context_quality_score(self) -> float:
        """Calculate a quality score for the current context state."""
        score = 10.0
        
        # Deduct points for issues
        if len(self.character_states) == 0:
            score -= 2.0  # No characters tracked
        
        if len(self.plot_threads) == 0:
            score -= 2.0  # No plot threads tracked
        
        unresolved_questions = self._get_unresolved_questions()
        if len(unresolved_questions) > 10:
            score -= 1.0  # Too many unresolved questions
        
        # Check for stale characters (not appeared recently)
        stale_characters = sum(1 for char in self.character_states.values() 
                             if len(self.chapter_contexts) - char.last_appearance > 5)
        if stale_characters > 3:
            score -= 1.0
        
        return max(score, 0.0)
    
    def _analyze_character_emotion(self, character_name: str, chapter_content: str) -> str:
        """Analyze a character's emotional state in the chapter."""
        # Simple keyword-based emotion detection
        emotion_patterns = {
            'angry': ['angry', 'furious', 'rage', 'mad', 'annoyed'],
            'sad': ['sad', 'depressed', 'sorrowful', 'grief', 'melancholy'],
            'happy': ['happy', 'joyful', 'excited', 'pleased', 'cheerful'],
            'afraid': ['afraid', 'scared', 'terrified', 'anxious', 'worried'],
            'determined': ['determined', 'focused', 'resolved', 'committed'],
            'confused': ['confused', 'puzzled', 'uncertain', 'bewildered']
        }
        
        content_lower = chapter_content.lower()
        
        # Look for character-specific emotional indicators
        for emotion, keywords in emotion_patterns.items():
            for keyword in keywords:
                # Look for patterns like "John was angry" or "angry John"
                if (f"{character_name.lower()} was {keyword}" in content_lower or
                    f"{keyword} {character_name.lower()}" in content_lower):
                    return emotion
        
        return "neutral"
    
    def get_context_summary(self) -> Dict[str, Any]:
        """Get a comprehensive summary of the current context state."""
        return {
            "chapters_analyzed": len(self.chapter_contexts),
            "characters_tracked": len(self.character_states),
            "active_plot_threads": len([t for t in self.plot_threads.values() if t.current_status == "active"]),
            "locations_established": len(self.world_state.locations),
            "unresolved_questions": len(self._get_unresolved_questions()),
            "ongoing_themes": self._get_ongoing_themes(),
            "context_quality_score": self._calculate_context_quality_score(),
            "last_updated": datetime.now().isoformat()
        }
    
    def create_initial_plot_thread(self, thread_id: str, title: str, urgency: str = "medium") -> PlotThread:
        """Create an initial plot thread for the story."""
        thread = PlotThread(
            thread_id=thread_id,
            title=title,
            start_chapter=1,
            current_status="active",
            resolution_chapter=None,
            key_events=[],
            related_characters=[],
            urgency_level=urgency,
            completion_percentage=0.0
        )
        
        self.plot_threads[thread_id] = thread
        self._save_all_state()
        return thread
    
    def resolve_plot_thread(self, thread_id: str, resolution_chapter: int) -> bool:
        """Mark a plot thread as resolved."""
        if thread_id in self.plot_threads:
            thread = self.plot_threads[thread_id]
            thread.current_status = "resolved"
            thread.resolution_chapter = resolution_chapter
            thread.completion_percentage = 100.0
            self._save_all_state()
            return True
        return False


# CLI Interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Chapter Context Manager")
    parser.add_argument("action", choices=["analyze", "summary", "context", "create-thread"], 
                       help="Action to perform")
    parser.add_argument("--project-path", default=".", help="Path to project directory")
    parser.add_argument("--chapter", type=int, help="Chapter number to analyze")
    parser.add_argument("--chapter-file", help="Chapter file to analyze")
    parser.add_argument("--thread-id", help="Plot thread ID")
    parser.add_argument("--thread-title", help="Plot thread title")
    parser.add_argument("--urgency", choices=["low", "medium", "high"], default="medium",
                       help="Plot thread urgency level")
    
    args = parser.parse_args()
    
    manager = ChapterContextManager(args.project_path)
    
    if args.action == "analyze" and args.chapter and args.chapter_file:
        try:
            with open(args.chapter_file, 'r', encoding='utf-8') as f:
                chapter_content = f.read()
            
            context = manager.analyze_chapter_content(args.chapter, chapter_content)
            
            print(f"📖 Chapter {args.chapter} Analysis Complete")
            print(f"📊 Summary: {context.summary}")
            print(f"👥 Characters: {', '.join(context.characters_present)}")
            print(f"🎯 Key Events: {len(context.key_events)}")
            print(f"❓ Questions Raised: {len(context.questions_raised)}")
            print(f"✅ Questions Answered: {len(context.questions_answered)}")
            print(f"🎭 Emotional Tone: {context.emotional_tone}")
            print(f"🎪 Themes: {', '.join(context.themes_explored)}")
            
        except FileNotFoundError:
            print(f"❌ Chapter file not found: {args.chapter_file}")
        except Exception as e:
            print(f"❌ Analysis failed: {e}")
    
    elif args.action == "summary":
        summary = manager.get_context_summary()
        print("📈 Context Summary:")
        print(f"  Chapters analyzed: {summary['chapters_analyzed']}")
        print(f"  Characters tracked: {summary['characters_tracked']}")
        print(f"  Active plot threads: {summary['active_plot_threads']}")
        print(f"  Locations established: {summary['locations_established']}")
        print(f"  Unresolved questions: {summary['unresolved_questions']}")
        print(f"  Ongoing themes: {', '.join(summary['ongoing_themes'])}")
        print(f"  Context quality score: {summary['context_quality_score']:.1f}/10.0")
    
    elif args.action == "context" and args.chapter:
        context = manager.build_next_chapter_context(args.chapter)
        print(f"🎯 Context for Chapter {args.chapter}:")
        print(f"  Previous chapters: {context['previous_chapters_count']}")
        print(f"  Active characters: {len(context['character_continuity'])}")
        print(f"  Active plot threads: {len(context['plot_threads'])}")
        print(f"  Unresolved questions: {len(context['unresolved_questions'])}")
        print(f"  Context quality: {context['context_quality_score']:.1f}/10.0")
        
        if context['continuity_requirements']:
            print("\n📋 Continuity Requirements:")
            for req in context['continuity_requirements']:
                print(f"  - {req}")
    
    elif args.action == "create-thread" and args.thread_id and args.thread_title:
        thread = manager.create_initial_plot_thread(args.thread_id, args.thread_title, args.urgency)
        print(f"✅ Created plot thread: {thread.title}")
        print(f"  ID: {thread.thread_id}")
        print(f"  Urgency: {thread.urgency_level}")
        print(f"  Status: {thread.current_status}")
    
    else:
        print("Please provide required arguments for the specified action")
        parser.print_help() 