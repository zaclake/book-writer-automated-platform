#!/usr/bin/env python3
"""
Brutal Assessment Scorer
Automated scoring system implementing the brutal-quality-assessment-system.md rubric.
"""

import re
import json
import yaml
from pathlib import Path
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

@dataclass
class AssessmentScore:
    """Represents a brutal assessment score breakdown."""
    category: str
    score: float
    max_score: float
    percentage: float
    notes: List[str]
    sub_scores: Dict[str, float] = None

@dataclass
class BrutalAssessmentResult:
    """Complete brutal assessment result."""
    overall_score: float
    assessment_level: str
    category_scores: Dict[str, AssessmentScore]
    critical_failures: List[str]
    word_count: int
    chapter_number: int
    assessment_date: str
    passed: bool

class BrutalAssessmentScorer:
    """Automated brutal assessment scoring implementation."""
    
    def __init__(self, quality_config_path: str = "quality-gates.yml"):
        self.config_path = Path(quality_config_path)
        self.config = self._load_config()
        self.brutal_config = self.config.get('brutal_assessment', {})
        
    def _load_config(self) -> Dict[str, Any]:
        """Load quality gates configuration."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Quality config not found: {self.config_path}")
    
    def assess_chapter(self, chapter_text: str, chapter_number: int = 1, 
                      metadata: Dict[str, Any] = None) -> BrutalAssessmentResult:
        """Perform complete brutal assessment of a chapter."""
        metadata = metadata or {}
        
        # Calculate word count
        word_count = len(chapter_text.split())
        
        # Check for critical failures first
        critical_failures = self._check_critical_failures(chapter_text, word_count, metadata)
        
        # Score all categories
        category_scores = {}
        
        # 1. Structural Integrity (25 points)
        category_scores['structural_integrity'] = self._score_structural_integrity(
            chapter_text, word_count, metadata)
        
        # 2. Character Development (20 points)
        category_scores['character_development'] = self._score_character_development(
            chapter_text, metadata)
        
        # 3. Technical Authenticity (15 points)
        category_scores['technical_authenticity'] = self._score_technical_authenticity(
            chapter_text, metadata)
        
        # 4. Prose Quality (15 points)
        category_scores['prose_quality'] = self._score_prose_quality(chapter_text)
        
        # 5. Market Viability (15 points)
        category_scores['market_viability'] = self._score_market_viability(
            chapter_text, metadata)
        
        # 6. Execution Quality (10 points)
        category_scores['execution_quality'] = self._score_execution_quality(
            chapter_text, critical_failures)
        
        # Calculate overall score
        overall_score = self._calculate_overall_score(category_scores)
        assessment_level = self._determine_assessment_level(overall_score)
        
        # Determine if passed
        min_score = self.brutal_config.get('minimum_score', 8.5) * 10
        passed = overall_score >= min_score and not critical_failures
        
        return BrutalAssessmentResult(
            overall_score=overall_score,
            assessment_level=assessment_level,
            category_scores=category_scores,
            critical_failures=critical_failures,
            word_count=word_count,
            chapter_number=chapter_number,
            assessment_date=datetime.now().isoformat(),
            passed=passed
        )
    
    def _check_critical_failures(self, chapter_text: str, word_count: int, 
                                metadata: Dict) -> List[str]:
        """Check for critical failure conditions."""
        failures = []
        
        # Em-dash usage check
        if '—' in chapter_text:
            failures.append("EM-DASH USAGE (—) - Automatic failure")
        
        # Word count check
        target_range = self.config['enhanced_system_compliance']['requirements']['word_count_verification']['target_range_words']
        target = sum(target_range) // 2
        variance_pct = abs(word_count - target) / target * 100
        
        if variance_pct > 30:
            failures.append(f"Word count >30% off target ({variance_pct:.1f}% variance)")
        
        # Plot advancement check
        if not self._has_plot_advancement(chapter_text):
            failures.append("No meaningful plot advancement detected")
        
        # Series contamination check
        series_pct = metadata.get('series_content_percentage', 0)
        if series_pct > 10:
            failures.append(f"Series setup exceeds 10% of content ({series_pct}%)")
        
        return failures
    
    def _score_structural_integrity(self, chapter_text: str, word_count: int, 
                                  metadata: Dict) -> AssessmentScore:
        """Score structural integrity (25 points maximum)."""
        notes = []
        sub_scores = {}
        
        # Word Count Performance (5 points)
        target_range = self.config['enhanced_system_compliance']['requirements']['word_count_verification']['target_range_words']
        target = sum(target_range) // 2
        variance_pct = abs(word_count - target) / target * 100
        
        if variance_pct <= 2:
            word_count_score = 5
        elif variance_pct <= 5:
            word_count_score = 4
        elif variance_pct <= 10:
            word_count_score = 3
        elif variance_pct <= 20:
            word_count_score = 2
        elif variance_pct <= 30:
            word_count_score = 1
        else:
            word_count_score = 0
        
        sub_scores['word_count_performance'] = word_count_score
        notes.append(f"Word count: {word_count} (target: {target}, variance: {variance_pct:.1f}%)")
        
        # Plot Advancement Consistency (10 points)
        plot_score = self._assess_plot_advancement(chapter_text)
        sub_scores['plot_advancement_consistency'] = plot_score
        
        # Three-Act Structure Execution (5 points)
        structure_score = self._assess_structure(chapter_text)
        sub_scores['structure_execution'] = structure_score
        
        # Series Balance (5 points)
        series_score = self._assess_series_balance(metadata)
        sub_scores['series_balance'] = series_score
        
        total_score = sum(sub_scores.values())
        percentage = (total_score / 25) * 100
        
        return AssessmentScore(
            category="structural_integrity",
            score=total_score,
            max_score=25,
            percentage=percentage,
            notes=notes,
            sub_scores=sub_scores
        )
    
    def _score_character_development(self, chapter_text: str, 
                                   metadata: Dict) -> AssessmentScore:
        """Score character development (20 points maximum)."""
        notes = []
        sub_scores = {}
        
        # Protagonist Development (8 points)
        protagonist_score = self._assess_protagonist_development(chapter_text)
        sub_scores['protagonist_development'] = protagonist_score
        
        # Supporting Character Quality (8 points)
        supporting_score = self._assess_supporting_characters(chapter_text)
        sub_scores['supporting_character_quality'] = supporting_score
        notes.append(f"Supporting characters detected: {self._count_characters(chapter_text)}")
        
        # Voice Distinction (4 points)
        voice_score = self._assess_voice_distinction(chapter_text)
        sub_scores['voice_distinction'] = voice_score
        
        total_score = sum(sub_scores.values())
        percentage = (total_score / 20) * 100
        
        return AssessmentScore(
            category="character_development",
            score=total_score,
            max_score=20,
            percentage=percentage,
            notes=notes,
            sub_scores=sub_scores
        )
    
    def _score_technical_authenticity(self, chapter_text: str, 
                                     metadata: Dict) -> AssessmentScore:
        """Score technical authenticity (15 points maximum)."""
        notes = []
        sub_scores = {}
        
        # Research Accuracy (8 points)
        research_score = self._assess_research_accuracy(chapter_text, metadata)
        sub_scores['research_accuracy'] = research_score
        
        # Professional Representation (4 points)
        professional_score = self._assess_professional_authenticity(chapter_text)
        sub_scores['professional_representation'] = professional_score
        
        # Setting Authenticity (3 points)
        setting_score = self._assess_setting_authenticity(chapter_text)
        sub_scores['setting_authenticity'] = setting_score
        
        total_score = sum(sub_scores.values())
        percentage = (total_score / 15) * 100
        
        return AssessmentScore(
            category="technical_authenticity",
            score=total_score,
            max_score=15,
            percentage=percentage,
            notes=notes,
            sub_scores=sub_scores
        )
    
    def _score_prose_quality(self, chapter_text: str) -> AssessmentScore:
        """Score prose quality (15 points maximum)."""
        notes = []
        sub_scores = {}
        
        # Language Mastery (8 points)
        language_score = self._assess_language_mastery(chapter_text)
        sub_scores['language_mastery'] = language_score
        
        # Theme Integration (4 points)
        theme_score = self._assess_theme_integration(chapter_text)
        sub_scores['theme_integration'] = theme_score
        
        # Narrative Flow (3 points)
        flow_score = self._assess_narrative_flow(chapter_text)
        sub_scores['narrative_flow'] = flow_score
        
        total_score = sum(sub_scores.values())
        percentage = (total_score / 15) * 100
        
        return AssessmentScore(
            category="prose_quality",
            score=total_score,
            max_score=15,
            percentage=percentage,
            notes=notes,
            sub_scores=sub_scores
        )
    
    def _score_market_viability(self, chapter_text: str, 
                               metadata: Dict) -> AssessmentScore:
        """Score market viability (15 points maximum)."""
        notes = []
        sub_scores = {}
        
        # Reader Engagement (8 points)
        engagement_score = self._assess_reader_engagement(chapter_text)
        sub_scores['reader_engagement'] = engagement_score
        
        # Genre Expectations (4 points)
        genre_score = self._assess_genre_expectations(chapter_text, metadata)
        sub_scores['genre_expectations'] = genre_score
        
        # Commercial Potential (3 points)
        commercial_score = self._assess_commercial_potential(chapter_text)
        sub_scores['commercial_potential'] = commercial_score
        
        total_score = sum(sub_scores.values())
        percentage = (total_score / 15) * 100
        
        return AssessmentScore(
            category="market_viability",
            score=total_score,
            max_score=15,
            percentage=percentage,
            notes=notes,
            sub_scores=sub_scores
        )
    
    def _score_execution_quality(self, chapter_text: str, 
                                critical_failures: List[str]) -> AssessmentScore:
        """Score execution quality (10 points maximum)."""
        notes = []
        sub_scores = {}
        
        # Consistency Maintenance (5 points)
        consistency_score = self._assess_consistency(chapter_text)
        sub_scores['consistency_maintenance'] = consistency_score
        
        # Professional Polish (5 points)
        if critical_failures:
            polish_score = 0  # Automatic failure for critical issues
            notes.append(f"Critical failures detected: {len(critical_failures)}")
        else:
            polish_score = self._assess_professional_polish(chapter_text)
        
        sub_scores['professional_polish'] = polish_score
        
        total_score = sum(sub_scores.values())
        percentage = (total_score / 10) * 100
        
        return AssessmentScore(
            category="execution_quality",
            score=total_score,
            max_score=10,
            percentage=percentage,
            notes=notes,
            sub_scores=sub_scores
        )
    
    def _calculate_overall_score(self, category_scores: Dict[str, AssessmentScore]) -> float:
        """Calculate weighted overall score."""
        weights = self.brutal_config.get('categories', {})
        
        total_weighted = 0.0
        total_weight = 0.0
        
        for category, score_obj in category_scores.items():
            weight = weights.get(category, {}).get('weight', 0.1)
            total_weighted += score_obj.percentage * weight
            total_weight += weight
        
        return total_weighted / total_weight if total_weight > 0 else 0.0
    
    def _determine_assessment_level(self, overall_score: float) -> str:
        """Determine assessment level from score."""
        scale = self.brutal_config.get('scoring_scale', {})
        
        if overall_score >= scale.get('publication_ready', [90, 100])[0]:
            return "Publication Ready"
        elif overall_score >= scale.get('professional_quality', [85, 89])[0]:
            return "Professional Quality"
        elif overall_score >= scale.get('solid_foundation', [80, 84])[0]:
            return "Solid Foundation"
        elif overall_score >= scale.get('major_revision_required', [75, 79])[0]:
            return "Major Revision Required"
        elif overall_score >= scale.get('serious_problems', [70, 74])[0]:
            return "Serious Problems"
        else:
            return "Not Ready"
    
    # Assessment helper methods
    def _has_plot_advancement(self, text: str) -> bool:
        """Check if chapter has meaningful plot advancement."""
        # Look for action indicators
        action_indicators = [
            'decided', 'discovered', 'realized', 'found', 'learned',
            'confronted', 'met', 'arrived', 'left', 'called',
            'revealed', 'understood', 'chose', 'agreed', 'refused'
        ]
        return any(indicator in text.lower() for indicator in action_indicators)
    
    def _assess_plot_advancement(self, text: str) -> float:
        """Assess plot advancement quality (0-10 points)."""
        if not self._has_plot_advancement(text):
            return 0.0
        
        # Count significant story events
        events = self._count_story_events(text)
        if events >= 3:
            return 10.0
        elif events >= 2:
            return 8.0
        elif events >= 1:
            return 6.0
        else:
            return 2.0
    
    def _count_story_events(self, text: str) -> int:
        """Count significant story events in text."""
        event_patterns = [
            r'\b(discovered|found|realized|learned|understood)\b',
            r'\b(met|confronted|faced|encountered)\b',
            r'\b(decided|chose|agreed|refused|accepted)\b',
            r'\b(revealed|told|confessed|admitted)\b',
            r'\b(arrived|left|departed|entered|exited)\b'
        ]
        
        count = 0
        for pattern in event_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            count += len(matches)
        
        return min(count, 5)  # Cap at 5 events
    
    def _assess_structure(self, text: str) -> float:
        """Assess three-act structure (0-5 points)."""
        paragraphs = text.split('\n\n')
        if len(paragraphs) < 3:
            return 1.0
        
        # Basic structure check
        has_opening = len(paragraphs[0]) > 100
        has_middle = len(paragraphs) > 5
        has_ending = len(paragraphs[-1]) > 50
        
        if has_opening and has_middle and has_ending:
            return 5.0
        elif has_opening and has_ending:
            return 4.0
        elif has_opening or has_ending:
            return 3.0
        else:
            return 2.0
    
    def _assess_series_balance(self, metadata: Dict) -> float:
        """Assess series vs individual story balance (0-5 points)."""
        series_pct = metadata.get('series_content_percentage', 0)
        
        if series_pct <= 5:
            return 5.0
        elif series_pct <= 10:
            return 4.0
        elif series_pct <= 15:
            return 3.0
        elif series_pct <= 20:
            return 2.0
        else:
            return 0.0
    
    def _count_characters(self, text: str) -> int:
        """Count distinct characters in text."""
        # Look for dialogue patterns and name patterns
        dialogue_speakers = re.findall(r'"[^"]*"\s*,?\s*(\w+)\s+(?:said|asked|replied)', text)
        name_patterns = re.findall(r'\b[A-Z][a-z]+\b', text)
        
        # Combine and deduplicate
        all_names = set(dialogue_speakers + name_patterns)
        
        # Filter out common words
        common_words = {'The', 'He', 'She', 'It', 'They', 'But', 'And', 'Or', 'So', 'Then', 'Now'}
        characters = all_names - common_words
        
        return len(characters)
    
    def _assess_protagonist_development(self, text: str) -> float:
        """Assess protagonist development (0-8 points)."""
        # Look for character growth indicators
        growth_indicators = [
            'thought', 'realized', 'understood', 'felt', 'decided',
            'remembered', 'wondered', 'hoped', 'feared', 'wanted'
        ]
        
        growth_count = sum(1 for indicator in growth_indicators 
                          if indicator in text.lower())
        
        if growth_count >= 10:
            return 8.0
        elif growth_count >= 7:
            return 6.0
        elif growth_count >= 5:
            return 4.0
        elif growth_count >= 3:
            return 2.0
        else:
            return 0.0
    
    def _assess_supporting_characters(self, text: str) -> float:
        """Assess supporting character quality (0-8 points)."""
        char_count = self._count_characters(text)
        
        if char_count >= 4:
            return 8.0
        elif char_count >= 3:
            return 6.0
        elif char_count >= 2:
            return 4.0
        elif char_count >= 1:
            return 2.0
        else:
            return 0.0
    
    def _assess_voice_distinction(self, text: str) -> float:
        """Assess voice distinction (0-4 points)."""
        # Count unique dialogue patterns
        dialogue_count = len(re.findall(r'"[^"]*"', text))
        
        if dialogue_count >= 10:
            return 4.0
        elif dialogue_count >= 6:
            return 3.0
        elif dialogue_count >= 3:
            return 2.0
        elif dialogue_count >= 1:
            return 1.0
        else:
            return 0.0
    
    def _assess_research_accuracy(self, text: str, metadata: Dict) -> float:
        """Assess research accuracy (0-8 points)."""
        # Check if research verification was performed
        research_verified = metadata.get('research_verified', False)
        technical_elements = metadata.get('technical_elements_count', 0)
        
        if research_verified and technical_elements > 0:
            return 8.0
        elif technical_elements == 0:
            return 6.0  # No technical elements to verify
        else:
            return 2.0  # Technical elements without verification
    
    def _assess_professional_authenticity(self, text: str) -> float:
        """Assess professional representation (0-4 points)."""
        # Look for professional terminology
        professional_indicators = [
            'procedure', 'protocol', 'evidence', 'investigation',
            'report', 'analysis', 'department', 'supervisor'
        ]
        
        prof_count = sum(1 for indicator in professional_indicators 
                        if indicator in text.lower())
        
        if prof_count >= 5:
            return 4.0
        elif prof_count >= 3:
            return 3.0
        elif prof_count >= 1:
            return 2.0
        else:
            return 1.0
    
    def _assess_setting_authenticity(self, text: str) -> float:
        """Assess setting authenticity (0-3 points)."""
        # Look for specific, detailed setting descriptions
        setting_indicators = [
            'street', 'building', 'room', 'office', 'house',
            'outside', 'inside', 'downtown', 'neighborhood'
        ]
        
        setting_count = sum(1 for indicator in setting_indicators 
                           if indicator in text.lower())
        
        if setting_count >= 5:
            return 3.0
        elif setting_count >= 3:
            return 2.0
        elif setting_count >= 1:
            return 1.0
        else:
            return 0.0
    
    def _assess_language_mastery(self, text: str) -> float:
        """Assess language mastery (0-8 points)."""
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if not sentences:
            return 0.0
        
        # Check sentence variety
        lengths = [len(s.split()) for s in sentences]
        avg_length = sum(lengths) / len(lengths)
        length_variance = max(lengths) - min(lengths)
        
        score = 4.0  # Base score
        
        # Bonus for good average length
        if 12 <= avg_length <= 20:
            score += 2.0
        elif 8 <= avg_length <= 25:
            score += 1.0
        
        # Bonus for sentence variety
        if length_variance >= 15:
            score += 2.0
        elif length_variance >= 10:
            score += 1.0
        
        return min(score, 8.0)
    
    def _assess_theme_integration(self, text: str) -> float:
        """Assess theme integration (0-4 points)."""
        # Look for thematic words and concepts
        theme_indicators = [
            'justice', 'truth', 'power', 'love', 'fear', 'hope',
            'betrayal', 'loyalty', 'family', 'friendship', 'death',
            'life', 'freedom', 'choice', 'consequence'
        ]
        
        theme_count = sum(1 for indicator in theme_indicators 
                         if indicator in text.lower())
        
        if theme_count >= 5:
            return 4.0
        elif theme_count >= 3:
            return 3.0
        elif theme_count >= 1:
            return 2.0
        else:
            return 1.0
    
    def _assess_narrative_flow(self, text: str) -> float:
        """Assess narrative flow (0-3 points)."""
        paragraphs = text.split('\n\n')
        
        # Check for transition words
        transitions = [
            'however', 'meanwhile', 'then', 'next', 'after',
            'before', 'later', 'suddenly', 'finally', 'eventually'
        ]
        
        transition_count = sum(1 for transition in transitions 
                              if transition in text.lower())
        
        if transition_count >= 5:
            return 3.0
        elif transition_count >= 3:
            return 2.0
        elif transition_count >= 1:
            return 1.0
        else:
            return 0.0
    
    def _assess_reader_engagement(self, text: str) -> float:
        """Assess reader engagement (0-8 points)."""
        # Check for engagement indicators
        engagement_indicators = [
            '?', '!', 'suddenly', 'unexpected', 'surprised',
            'shocking', 'amazing', 'incredible', 'couldn\'t believe'
        ]
        
        engagement_count = sum(text.count(indicator) for indicator in engagement_indicators)
        
        if engagement_count >= 10:
            return 8.0
        elif engagement_count >= 7:
            return 6.0
        elif engagement_count >= 5:
            return 4.0
        elif engagement_count >= 3:
            return 2.0
        else:
            return 0.0
    
    def _assess_genre_expectations(self, text: str, metadata: Dict) -> float:
        """Assess genre expectations (0-4 points)."""
        genre = metadata.get('genre', 'unknown').lower()
        
        # Genre-specific scoring
        if 'thriller' in genre or 'mystery' in genre:
            indicators = ['investigate', 'suspect', 'evidence', 'clue', 'danger']
        elif 'romance' in genre:
            indicators = ['love', 'heart', 'kiss', 'relationship', 'feelings']
        elif 'horror' in genre:
            indicators = ['fear', 'terror', 'dark', 'scream', 'nightmare']
        else:
            indicators = ['character', 'story', 'conflict', 'resolution']
        
        genre_count = sum(1 for indicator in indicators 
                         if indicator in text.lower())
        
        if genre_count >= 3:
            return 4.0
        elif genre_count >= 2:
            return 3.0
        elif genre_count >= 1:
            return 2.0
        else:
            return 1.0
    
    def _assess_commercial_potential(self, text: str) -> float:
        """Assess commercial potential (0-3 points)."""
        # Check for marketable elements
        commercial_indicators = [
            'compelling', 'exciting', 'dramatic', 'intense',
            'emotional', 'powerful', 'gripping', 'page-turning'
        ]
        
        # This is a simplified check - real assessment would be more complex
        word_count = len(text.split())
        
        if word_count >= 3000:
            return 3.0
        elif word_count >= 2000:
            return 2.0
        elif word_count >= 1000:
            return 1.0
        else:
            return 0.0
    
    def _assess_consistency(self, text: str) -> float:
        """Assess consistency maintenance (0-5 points)."""
        # Basic consistency checks
        paragraphs = text.split('\n\n')
        
        if len(paragraphs) >= 5:
            return 5.0
        elif len(paragraphs) >= 3:
            return 4.0
        elif len(paragraphs) >= 2:
            return 3.0
        else:
            return 2.0
    
    def _assess_professional_polish(self, text: str) -> float:
        """Assess professional polish (0-5 points)."""
        # Check for basic formatting and structure
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if len(sentences) >= 20:
            return 5.0
        elif len(sentences) >= 15:
            return 4.0
        elif len(sentences) >= 10:
            return 3.0
        elif len(sentences) >= 5:
            return 2.0
        else:
            return 1.0

# CLI Interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Brutal Assessment Scorer")
    parser.add_argument("action", choices=["assess", "test"], 
                       help="Action to perform")
    parser.add_argument("--chapter-file", 
                       help="Chapter file to assess")
    parser.add_argument("--chapter-number", type=int, default=1,
                       help="Chapter number")
    parser.add_argument("--metadata", 
                       help="JSON metadata for the chapter")
    parser.add_argument("--output", 
                       help="Output file for results")
    
    args = parser.parse_args()
    
    scorer = BrutalAssessmentScorer()
    
    if args.action == "assess" and args.chapter_file:
        try:
            with open(args.chapter_file, 'r', encoding='utf-8') as f:
                chapter_text = f.read()
            
            metadata = {}
            if args.metadata:
                metadata = json.loads(args.metadata)
            
            result = scorer.assess_chapter(chapter_text, args.chapter_number, metadata)
            
            print(f"Brutal Assessment Results:")
            print(f"Overall Score: {result.overall_score:.1f}/100")
            print(f"Assessment Level: {result.assessment_level}")
            print(f"Passed: {'✅ Yes' if result.passed else '❌ No'}")
            print(f"Word Count: {result.word_count}")
            
            if result.critical_failures:
                print(f"\nCritical Failures:")
                for failure in result.critical_failures:
                    print(f"  ❌ {failure}")
            
            print(f"\nCategory Breakdown:")
            for category, score in result.category_scores.items():
                print(f"  {category}: {score.score:.1f}/{score.max_score} ({score.percentage:.1f}%)")
            
            if args.output:
                with open(args.output, 'w', encoding='utf-8') as f:
                    json.dump(asdict(result), f, indent=2)
                print(f"\nDetailed results saved to {args.output}")
                
        except FileNotFoundError:
            print(f"Error: Chapter file not found: {args.chapter_file}")
        except Exception as e:
            print(f"Error: {e}")
    
    elif args.action == "test":
        # Test with sample text
        test_text = """
        Chapter 1
        
        The morning sun cast long shadows across the detective's desk as Sarah Martinez reviewed the case files. Three victims, all found in similar circumstances, all connected by a thread she couldn't yet see.
        
        "Another one came in overnight," Detective Johnson said, dropping a fresh file on her desk. "Same pattern."
        
        Sarah looked up, her coffee growing cold. "Where?"
        
        "Downtown. Near the cathedral." Johnson's voice carried the weight of too many similar conversations. "This one's different though."
        
        She opened the file, scanning the preliminary report. The victim was younger, the circumstances slightly altered. But the signature was unmistakable.
        
        "We need to talk to the witness again," Sarah decided, closing the file. "Something's not adding up."
        
        The investigation was just beginning, but Sarah felt the familiar tingle of pieces starting to connect. Truth had a way of surfacing, even when buried deep.
        """
        
        result = scorer.assess_chapter(test_text, 1, {'genre': 'thriller'})
        
        print("Test Assessment:")
        print(f"Score: {result.overall_score:.1f}/100 ({result.assessment_level})")
        print(f"Passed: {'✅ Yes' if result.passed else '❌ No'}")
        
        for category, score in result.category_scores.items():
            print(f"  {category}: {score.percentage:.1f}%")
    
    else:
        print("Please provide required arguments")
        parser.print_help() 