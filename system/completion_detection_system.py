#!/usr/bin/env python3
"""
Completion Detection System
Analyzes story content to determine when a book is complete based on multiple criteria.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import logging

@dataclass
class CompletionCriteria:
    """Criteria for determining book completion."""
    target_word_count: int = 80000
    minimum_word_count: int = 70000
    maximum_word_count: int = 90000
    target_chapter_count: int = 20
    minimum_chapter_count: int = 18
    maximum_chapter_count: int = 25
    plot_resolution_required: bool = True
    character_arc_completion_required: bool = True
    quality_threshold_maintained: bool = True
    minimum_conclusion_score: float = 7.0

class CompletionStatus(Enum):
    """Status of book completion analysis."""
    INCOMPLETE = "incomplete"
    READY_TO_COMPLETE = "ready_to_complete"
    COMPLETED = "completed"
    OVER_TARGET = "over_target"
    NEEDS_REVISION = "needs_revision"

@dataclass
class CompletionAnalysis:
    """Results of completion analysis."""
    status: CompletionStatus
    current_word_count: int
    current_chapter_count: int
    word_count_progress: float
    chapter_count_progress: float
    plot_resolution_score: float
    character_arc_score: float
    conclusion_quality_score: float
    story_completeness_score: float
    recommendations: List[str]
    missing_elements: List[str]
    next_actions: List[str]

class CompletionDetectionSystem:
    """
    Analyzes story content to determine completion status.
    
    Features:
    - Word count and chapter count analysis
    - Plot resolution detection
    - Character arc completion assessment
    - Story conclusion quality evaluation
    - Recommendations for completion
    """
    
    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.state_dir = self.project_path / ".project-state"
        self.chapters_dir = self.project_path / "chapters"
        
        self.logger = logging.getLogger(__name__)
        
        # Load completion criteria
        self.criteria = self._load_completion_criteria()
        
        # Story analysis patterns
        self._init_analysis_patterns()
    
    def _load_completion_criteria(self) -> CompletionCriteria:
        """Load completion criteria from state file."""
        try:
            completion_state_file = self.state_dir / "book-completion-state.json"
            if completion_state_file.exists():
                with open(completion_state_file, 'r', encoding='utf-8') as f:
                    state_data = json.load(f)
                
                criteria_data = state_data.get('completion_criteria', {})
                return CompletionCriteria(
                    target_word_count=criteria_data.get('target_word_count', 80000),
                    minimum_word_count=criteria_data.get('minimum_word_count', 70000),
                    maximum_word_count=criteria_data.get('maximum_word_count', 90000),
                    target_chapter_count=criteria_data.get('target_chapter_count', 20),
                    minimum_chapter_count=criteria_data.get('minimum_chapter_count', 18),
                    maximum_chapter_count=criteria_data.get('maximum_chapter_count', 25),
                    plot_resolution_required=criteria_data.get('plot_resolution_required', True),
                    character_arc_completion_required=criteria_data.get('character_arc_completion_required', True),
                    quality_threshold_maintained=criteria_data.get('quality_threshold_maintained', True),
                    minimum_conclusion_score=criteria_data.get('minimum_conclusion_score', 7.0)
                )
        except Exception as e:
            self.logger.warning(f"Failed to load completion criteria: {e}")
        
        return CompletionCriteria()
    
    def _init_analysis_patterns(self):
        """Initialize patterns for story analysis."""
        self.plot_resolution_patterns = [
            r'(?:resolved|solved|concluded|finished|completed)',
            r'(?:finally|at\s+last|in\s+the\s+end)',
            r'(?:justice|peace|resolution|closure)',
            r'(?:mystery.*?solved|question.*?answered)',
            r'(?:villain.*?defeated|enemy.*?overcome)',
            r'(?:goal.*?achieved|mission.*?accomplished)',
            r'(?:truth.*?revealed|secret.*?exposed)',
            r'(?:conflict.*?ended|war.*?over)',
            r'(?:balance.*?restored|order.*?returned)',
            r'(?:prophecy.*?fulfilled|destiny.*?realized)'
        ]
        
        self.character_arc_patterns = [
            r'(?:learned|realized|understood|discovered)',
            r'(?:changed|transformed|evolved|grew)',
            r'(?:overcame|conquered|defeated|faced)',
            r'(?:forgave|accepted|embraced|let\s+go)',
            r'(?:found.*?peace|made.*?peace|at.*?peace)',
            r'(?:redeemed|atoned|made\s+amends)',
            r'(?:loved|trusted|believed|hoped)',
            r'(?:strength|courage|wisdom|maturity)',
            r'(?:home|family|belonging|identity)',
            r'(?:purpose|meaning|calling|path)'
        ]
        
        self.conclusion_patterns = [
            r'(?:the\s+end|epilogue|conclusion|finale)',
            r'(?:years\s+later|months\s+later|time\s+passed)',
            r'(?:ever\s+after|forever|always|never\s+again)',
            r'(?:legacy|memory|remembrance|honor)',
            r'(?:new\s+beginning|fresh\s+start|different\s+life)',
            r'(?:learned.*?lesson|wisdom.*?gained)',
            r'(?:happily|peacefully|contentedly|satisfied)',
            r'(?:future.*?bright|hope.*?renewed)',
            r'(?:story.*?ends|tale.*?complete|journey.*?over)',
            r'(?:sunrise|dawn|new\s+day|tomorrow)'
        ]
        
        self.incomplete_patterns = [
            r'(?:to\s+be\s+continued|what\s+happens\s+next)',
            r'(?:but\s+suddenly|just\s+then|without\s+warning)$',
            r'(?:will\s+they|can\s+they|what\s+will)(?:\s+\w+){0,5}\?$',
            r'(?:the\s+mystery|the\s+question|the\s+answer)\s+(?:remains|waits)',
            r'(?:unresolved|unfinished|incomplete|pending)',
            r'(?:still\s+need|must\s+still|yet\s+to)',
            r'(?:hanging|suspended|uncertain|unknown)',
            r'(?:cliffhanger|suspense|tension|anticipation)'
        ]
    
    def analyze_completion_status(self) -> CompletionAnalysis:
        """Analyze current story completion status."""
        # Get current metrics
        word_count, chapter_count = self._get_current_metrics()
        
        # Analyze story content
        story_content = self._get_story_content()
        plot_score = self._analyze_plot_resolution(story_content)
        character_score = self._analyze_character_arcs(story_content)
        conclusion_score = self._analyze_conclusion_quality(story_content)
        
        # Calculate progress percentages
        word_progress = (word_count / self.criteria.target_word_count) * 100
        chapter_progress = (chapter_count / self.criteria.target_chapter_count) * 100
        
        # Calculate overall story completeness
        story_completeness = self._calculate_story_completeness(
            word_count, chapter_count, plot_score, character_score, conclusion_score
        )
        
        # Determine completion status
        status = self._determine_completion_status(
            word_count, chapter_count, plot_score, character_score, conclusion_score, story_completeness
        )
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            status, word_count, chapter_count, plot_score, character_score, conclusion_score
        )
        
        missing_elements = self._identify_missing_elements(
            plot_score, character_score, conclusion_score
        )
        
        next_actions = self._generate_next_actions(
            status, word_count, chapter_count, missing_elements
        )
        
        return CompletionAnalysis(
            status=status,
            current_word_count=word_count,
            current_chapter_count=chapter_count,
            word_count_progress=word_progress,
            chapter_count_progress=chapter_progress,
            plot_resolution_score=plot_score,
            character_arc_score=character_score,
            conclusion_quality_score=conclusion_score,
            story_completeness_score=story_completeness,
            recommendations=recommendations,
            missing_elements=missing_elements,
            next_actions=next_actions
        )
    
    def _get_current_metrics(self) -> Tuple[int, int]:
        """Get current word count and chapter count."""
        word_count = 0
        chapter_count = 0
        
        if self.chapters_dir.exists():
            for chapter_file in sorted(self.chapters_dir.glob("chapter-*.md")):
                try:
                    with open(chapter_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        word_count += len(content.split())
                        chapter_count += 1
                except Exception as e:
                    self.logger.warning(f"Error reading {chapter_file}: {e}")
        
        return word_count, chapter_count
    
    def _get_story_content(self) -> str:
        """Get combined story content for analysis."""
        content = ""
        
        if self.chapters_dir.exists():
            for chapter_file in sorted(self.chapters_dir.glob("chapter-*.md")):
                try:
                    with open(chapter_file, 'r', encoding='utf-8') as f:
                        content += f.read() + "\n\n"
                except Exception as e:
                    self.logger.warning(f"Error reading {chapter_file}: {e}")
        
        return content
    
    def _analyze_plot_resolution(self, content: str) -> float:
        """Analyze plot resolution completeness."""
        if not content:
            return 0.0
        
        # Look for resolution patterns
        resolution_score = 0.0
        total_patterns = len(self.plot_resolution_patterns)
        
        for pattern in self.plot_resolution_patterns:
            matches = len(re.findall(pattern, content, re.IGNORECASE))
            if matches > 0:
                resolution_score += min(matches, 3) / 3.0  # Cap at 3 matches per pattern
        
        # Check for incomplete patterns (negative score)
        incomplete_score = 0.0
        for pattern in self.incomplete_patterns:
            matches = len(re.findall(pattern, content, re.IGNORECASE))
            incomplete_score += matches * 0.5
        
        # Calculate final score
        final_score = (resolution_score / total_patterns) * 10.0 - incomplete_score
        
        return max(0.0, min(10.0, final_score))
    
    def _analyze_character_arcs(self, content: str) -> float:
        """Analyze character arc completion."""
        if not content:
            return 0.0
        
        # Look for character development patterns
        arc_score = 0.0
        total_patterns = len(self.character_arc_patterns)
        
        for pattern in self.character_arc_patterns:
            matches = len(re.findall(pattern, content, re.IGNORECASE))
            if matches > 0:
                arc_score += min(matches, 2) / 2.0  # Cap at 2 matches per pattern
        
        # Calculate final score
        final_score = (arc_score / total_patterns) * 10.0
        
        return max(0.0, min(10.0, final_score))
    
    def _analyze_conclusion_quality(self, content: str) -> float:
        """Analyze conclusion quality and satisfaction."""
        if not content:
            return 0.0
        
        # Get last 20% of content for conclusion analysis
        words = content.split()
        conclusion_start = max(0, len(words) - len(words) // 5)
        conclusion_text = " ".join(words[conclusion_start:])
        
        # Look for conclusion patterns
        conclusion_score = 0.0
        total_patterns = len(self.conclusion_patterns)
        
        for pattern in self.conclusion_patterns:
            matches = len(re.findall(pattern, conclusion_text, re.IGNORECASE))
            if matches > 0:
                conclusion_score += min(matches, 2) / 2.0
        
        # Calculate final score
        final_score = (conclusion_score / total_patterns) * 10.0
        
        return max(0.0, min(10.0, final_score))
    
    def _calculate_story_completeness(self, word_count: int, chapter_count: int, 
                                    plot_score: float, character_score: float, 
                                    conclusion_score: float) -> float:
        """Calculate overall story completeness score."""
        # Word count component (25%)
        word_component = min(word_count / self.criteria.target_word_count, 1.0) * 0.25
        
        # Chapter count component (15%)
        chapter_component = min(chapter_count / self.criteria.target_chapter_count, 1.0) * 0.15
        
        # Plot resolution component (30%)
        plot_component = (plot_score / 10.0) * 0.30
        
        # Character arc component (20%)
        character_component = (character_score / 10.0) * 0.20
        
        # Conclusion quality component (10%)
        conclusion_component = (conclusion_score / 10.0) * 0.10
        
        total_score = (word_component + chapter_component + plot_component + 
                      character_component + conclusion_component) * 100
        
        return max(0.0, min(100.0, total_score))
    
    def _determine_completion_status(self, word_count: int, chapter_count: int,
                                   plot_score: float, character_score: float,
                                   conclusion_score: float, story_completeness: float) -> CompletionStatus:
        """Determine overall completion status."""
        # Check if over target
        if word_count > self.criteria.maximum_word_count:
            return CompletionStatus.OVER_TARGET
        
        # Check if complete
        if (word_count >= self.criteria.minimum_word_count and
            chapter_count >= self.criteria.minimum_chapter_count and
            plot_score >= self.criteria.minimum_conclusion_score and
            character_score >= self.criteria.minimum_conclusion_score and
            conclusion_score >= self.criteria.minimum_conclusion_score):
            return CompletionStatus.COMPLETED
        
        # Check if ready to complete
        if (word_count >= self.criteria.minimum_word_count * 0.9 and
            chapter_count >= self.criteria.minimum_chapter_count - 2 and
            story_completeness >= 80.0):
            return CompletionStatus.READY_TO_COMPLETE
        
        # Check if needs revision
        if (word_count >= self.criteria.minimum_word_count and
            (plot_score < 5.0 or character_score < 5.0)):
            return CompletionStatus.NEEDS_REVISION
        
        return CompletionStatus.INCOMPLETE
    
    def _generate_recommendations(self, status: CompletionStatus, word_count: int,
                                chapter_count: int, plot_score: float,
                                character_score: float, conclusion_score: float) -> List[str]:
        """Generate recommendations based on analysis."""
        recommendations = []
        
        if status == CompletionStatus.OVER_TARGET:
            recommendations.append("Consider editing to reduce word count")
            recommendations.append("Review for unnecessary scenes or descriptions")
        
        elif status == CompletionStatus.COMPLETED:
            recommendations.append("Story appears complete - consider final editing pass")
            recommendations.append("Review for consistency and polish")
        
        elif status == CompletionStatus.READY_TO_COMPLETE:
            if conclusion_score < 7.0:
                recommendations.append("Strengthen the conclusion for better reader satisfaction")
            recommendations.append("Consider adding 1-2 more chapters to reach target length")
        
        elif status == CompletionStatus.NEEDS_REVISION:
            if plot_score < 5.0:
                recommendations.append("Address unresolved plot threads")
            if character_score < 5.0:
                recommendations.append("Develop character arcs further")
        
        else:  # INCOMPLETE
            if word_count < self.criteria.minimum_word_count * 0.7:
                recommendations.append("Continue writing - significant content still needed")
            if plot_score < 5.0:
                recommendations.append("Develop plot resolution elements")
            if character_score < 5.0:
                recommendations.append("Show more character growth and development")
        
        return recommendations
    
    def _identify_missing_elements(self, plot_score: float, character_score: float,
                                 conclusion_score: float) -> List[str]:
        """Identify missing story elements."""
        missing = []
        
        if plot_score < 5.0:
            missing.append("Plot resolution")
        if character_score < 5.0:
            missing.append("Character arc completion")
        if conclusion_score < 5.0:
            missing.append("Satisfying conclusion")
        
        return missing
    
    def _generate_next_actions(self, status: CompletionStatus, word_count: int,
                             chapter_count: int, missing_elements: List[str]) -> List[str]:
        """Generate specific next actions."""
        actions = []
        
        if status == CompletionStatus.COMPLETED:
            actions.append("Run final quality check")
            actions.append("Prepare for publication")
        
        elif status == CompletionStatus.READY_TO_COMPLETE:
            actions.append("Write concluding chapter(s)")
            actions.append("Add resolution scenes")
        
        elif status == CompletionStatus.OVER_TARGET:
            actions.append("Begin editing process")
            actions.append("Identify scenes to cut or condense")
        
        elif status == CompletionStatus.NEEDS_REVISION:
            actions.extend([f"Address {element}" for element in missing_elements])
        
        else:  # INCOMPLETE
            actions.append("Continue sequential chapter generation")
            if word_count < self.criteria.minimum_word_count * 0.5:
                actions.append("Focus on story progression")
            else:
                actions.append("Begin incorporating resolution elements")
        
        return actions
    
    def should_continue_generation(self) -> bool:
        """Determine if auto-completion should continue generating chapters."""
        analysis = self.analyze_completion_status()
        
        return analysis.status in [
            CompletionStatus.INCOMPLETE,
            CompletionStatus.READY_TO_COMPLETE
        ]
    
    def get_completion_summary(self) -> Dict[str, Any]:
        """Get a summary of completion analysis for reporting."""
        analysis = self.analyze_completion_status()
        
        return {
            "completion_status": analysis.status.value,
            "progress_metrics": {
                "word_count": analysis.current_word_count,
                "chapter_count": analysis.current_chapter_count,
                "word_progress_percentage": analysis.word_count_progress,
                "chapter_progress_percentage": analysis.chapter_count_progress,
                "story_completeness_percentage": analysis.story_completeness_score
            },
            "quality_scores": {
                "plot_resolution": analysis.plot_resolution_score,
                "character_arcs": analysis.character_arc_score,
                "conclusion_quality": analysis.conclusion_quality_score
            },
            "recommendations": analysis.recommendations,
            "missing_elements": analysis.missing_elements,
            "next_actions": analysis.next_actions,
            "analysis_timestamp": datetime.now().isoformat()
        } 