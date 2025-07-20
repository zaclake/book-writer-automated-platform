#!/usr/bin/env python3
"""
Reader Engagement Scorer
Evaluates predicted engagement scores per reader-engagement-predictor.md
"""

import re
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass, asdict

@dataclass
class EngagementAnalysis:
    """Results of engagement analysis for a chapter."""
    chapter_number: int
    hook_strength: str  # strong, medium, weak
    momentum_maintenance: str  # strong, medium, weak
    ending_propulsion: str  # strong, medium, weak
    conflict_density: str  # strong, medium, weak
    dialogue_exposition_ratio: float
    question_generation_rate: int
    surprise_factor: str  # strong, medium, weak
    engagement_score: float  # 1-10 scale
    risk_flags: List[str]
    genre_compliance: str
    recommendations: List[str]

class ReaderEngagementScorer:
    """Automated reader engagement prediction and scoring."""
    
    def __init__(self, project_path: str = ".", target_genre: str = "thriller"):
        self.project_path = Path(project_path)
        self.state_dir = self.project_path / ".project-state"
        self.results_path = self.state_dir / "engagement-scores.json"
        self.target_genre = target_genre.lower()
        
        # Ensure state directory exists
        self.state_dir.mkdir(exist_ok=True)
        
        # Engagement patterns
        self.hook_patterns = {
            'strong': [
                r'(?:^|\n).*(?:gunshot|scream|crash|explosion|bang)',
                r'(?:^|\n).*(?:dead|murder|killed|blood|body)',
                r'(?:^|\n).*(?:wrong|problem|trouble|danger|threat)',
                r'(?:^|\n).*(?:question|mystery|secret|hidden|unknown)',
                r'(?:^|\n).*(?:never|wasn\'t|couldn\'t|shouldn\'t).*(?:supposed|expected|normal)'
            ],
            'medium': [
                r'(?:^|\n).*(?:walked|entered|arrived|came|went)',
                r'(?:^|\n).*(?:morning|evening|day|night|time)',
                r'(?:^|\n).*(?:remembered|thought|considered|wondered)',
                r'(?:^|\n).*(?:phone|call|message|email|knock)'
            ]
        }
        
        self.conflict_patterns = [
            r'\b(?:argument|fight|confrontation|dispute|clash)\b',
            r'\b(?:angry|furious|enraged|hostile|aggressive)\b',
            r'\b(?:opposed|against|resist|refuse|deny)\b',
            r'\b(?:problem|difficulty|trouble|challenge|obstacle)\b',
            r'\b(?:tension|pressure|stress|strain|conflict)\b',
            r'\b(?:danger|threat|risk|peril|hazard)\b'
        ]
        
        self.question_patterns = [
            r'\?',  # Direct questions
            r'\b(?:why|how|what|when|where|who)\b.*\?',
            r'\b(?:wondered|puzzled|confused|unclear|uncertain)\b',
            r'\b(?:mystery|secret|hidden|unknown|unexplained)\b',
            r'\b(?:strange|odd|weird|unusual|suspicious)\b'
        ]
        
        self.surprise_patterns = [
            r'\b(?:suddenly|unexpectedly|surprisingly|shocking|startling)\b',
            r'\b(?:never|never before|first time|unprecedented)\b',
            r'\b(?:twist|turn|revelation|discovery|surprise)\b',
            r'\b(?:realized|discovered|found out|learned)\b.*(?:that|how|why)'
        ]
        
        # Genre-specific requirements
        self.genre_standards = {
            'thriller': {
                'min_conflict_density': 6,
                'min_question_rate': 4,
                'required_tension': True,
                'pacing_requirement': 'fast'
            },
            'mystery': {
                'min_conflict_density': 4,
                'min_question_rate': 6,
                'required_tension': True,
                'pacing_requirement': 'measured'
            },
            'romance': {
                'min_conflict_density': 3,
                'min_question_rate': 2,
                'required_tension': False,
                'pacing_requirement': 'character_driven'
            },
            'literary': {
                'min_conflict_density': 2,
                'min_question_rate': 1,
                'required_tension': False,
                'pacing_requirement': 'thoughtful'
            },
            'science_fiction': {
                'min_conflict_density': 4,
                'min_question_rate': 5,
                'required_tension': True,
                'pacing_requirement': 'escalating'
            },
            'fantasy': {
                'min_conflict_density': 5,
                'min_question_rate': 4,
                'required_tension': True,
                'pacing_requirement': 'adventure'
            }
        }
    
    def analyze_chapter_engagement(self, chapter_text: str, chapter_number: int) -> EngagementAnalysis:
        """Analyze a chapter for reader engagement prediction."""
        
        # Analyze hook strength (first 200 words)
        opening_text = ' '.join(chapter_text.split()[:200])
        hook_strength = self._analyze_hook_strength(opening_text)
        
        # Analyze momentum maintenance
        momentum_maintenance = self._analyze_momentum_maintenance(chapter_text)
        
        # Analyze ending propulsion (last 200 words)
        ending_text = ' '.join(chapter_text.split()[-200:])
        ending_propulsion = self._analyze_ending_propulsion(ending_text)
        
        # Analyze conflict density
        conflict_density = self._analyze_conflict_density(chapter_text)
        
        # Calculate dialogue vs exposition ratio
        dialogue_ratio = self._calculate_dialogue_ratio(chapter_text)
        
        # Count question generation
        question_rate = self._count_question_generation(chapter_text)
        
        # Analyze surprise factor
        surprise_factor = self._analyze_surprise_factor(chapter_text)
        
        # Calculate overall engagement score
        engagement_score = self._calculate_engagement_score(
            hook_strength, momentum_maintenance, ending_propulsion,
            conflict_density, dialogue_ratio, question_rate, surprise_factor
        )
        
        # Generate risk flags
        risk_flags = self._generate_risk_flags(
            engagement_score, hook_strength, momentum_maintenance,
            ending_propulsion, conflict_density, dialogue_ratio, question_rate
        )
        
        # Check genre compliance
        genre_compliance = self._check_genre_compliance(
            conflict_density, question_rate, chapter_text
        )
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            hook_strength, momentum_maintenance, ending_propulsion,
            conflict_density, dialogue_ratio, question_rate, surprise_factor
        )
        
        analysis = EngagementAnalysis(
            chapter_number=chapter_number,
            hook_strength=hook_strength,
            momentum_maintenance=momentum_maintenance,
            ending_propulsion=ending_propulsion,
            conflict_density=conflict_density,
            dialogue_exposition_ratio=dialogue_ratio,
            question_generation_rate=question_rate,
            surprise_factor=surprise_factor,
            engagement_score=engagement_score,
            risk_flags=risk_flags,
            genre_compliance=genre_compliance,
            recommendations=recommendations
        )
        
        # Save analysis
        self._save_analysis(analysis)
        
        return analysis
    
    def _analyze_hook_strength(self, opening_text: str) -> str:
        """Analyze the strength of the chapter opening hook."""
        
        # Check for strong hook patterns
        strong_matches = 0
        for pattern in self.hook_patterns['strong']:
            if re.search(pattern, opening_text, re.IGNORECASE):
                strong_matches += 1
        
        if strong_matches >= 2:
            return 'strong'
        elif strong_matches >= 1:
            return 'medium'
        
        # Check for medium hook patterns
        medium_matches = 0
        for pattern in self.hook_patterns['medium']:
            if re.search(pattern, opening_text, re.IGNORECASE):
                medium_matches += 1
        
        if medium_matches >= 2:
            return 'medium'
        else:
            return 'weak'
    
    def _analyze_momentum_maintenance(self, chapter_text: str) -> str:
        """Analyze how well the chapter maintains momentum."""
        
        # Split chapter into segments for analysis
        words = chapter_text.split()
        total_words = len(words)
        
        if total_words < 500:
            return 'medium'  # Too short to properly assess
        
        # Analyze in segments
        segment_size = max(200, total_words // 5)
        segments = []
        
        for i in range(0, total_words, segment_size):
            segment = ' '.join(words[i:i + segment_size])
            segments.append(segment)
        
        # Count momentum indicators per segment
        momentum_scores = []
        for segment in segments:
            score = 0
            
            # Action/dialogue indicators
            if re.search(r'"[^"]*"', segment):  # Has dialogue
                score += 2
            if re.search(r'\b(?:ran|jumped|grabbed|shouted|turned|moved|walked)\b', segment, re.IGNORECASE):
                score += 1
            if re.search(r'\b(?:suddenly|quickly|immediately|now|then)\b', segment, re.IGNORECASE):
                score += 1
            
            # Question/tension indicators
            question_count = len(re.findall(r'\?', segment))
            score += min(question_count, 2)
            
            momentum_scores.append(score)
        
        avg_momentum = sum(momentum_scores) / len(momentum_scores) if momentum_scores else 0
        
        if avg_momentum >= 3:
            return 'strong'
        elif avg_momentum >= 1.5:
            return 'medium'
        else:
            return 'weak'
    
    def _analyze_ending_propulsion(self, ending_text: str) -> str:
        """Analyze how well the chapter ending creates forward momentum."""
        
        propulsion_indicators = [
            r'\b(?:but|however|yet|still|until|unless|if|when)\b.*[.!?]$',  # Cliffhanger setup
            r'\b(?:realized|discovered|saw|heard|noticed)\b.*[.!?]$',  # Revelation
            r'\b(?:question|mystery|problem|danger|trouble)\b.*[.!?]$',  # Ongoing tension
            r'\?$',  # Ends with question
            r'\.{3}$',  # Ends with ellipsis
            r'!$',  # Ends with exclamation
            r'\b(?:tomorrow|next|later|soon|would)\b.*[.!?]$'  # Future tension
        ]
        
        strong_count = 0
        for pattern in propulsion_indicators:
            if re.search(pattern, ending_text, re.IGNORECASE | re.MULTILINE):
                strong_count += 1
        
        # Check for weak endings
        weak_endings = [
            r'\b(?:slept|sleep|fell asleep|closed.*eyes)\b.*[.]$',
            r'\b(?:finished|completed|done|over|ended)\b.*[.]$',
            r'\b(?:peaceful|quiet|calm|satisfied|content)\b.*[.]$'
        ]
        
        weak_count = 0
        for pattern in weak_endings:
            if re.search(pattern, ending_text, re.IGNORECASE):
                weak_count += 1
        
        if strong_count >= 2 and weak_count == 0:
            return 'strong'
        elif strong_count >= 1 and weak_count <= 1:
            return 'medium'
        else:
            return 'weak'
    
    def _analyze_conflict_density(self, chapter_text: str) -> str:
        """Analyze the density of conflict throughout the chapter."""
        
        total_conflicts = 0
        for pattern in self.conflict_patterns:
            conflicts = len(re.findall(pattern, chapter_text, re.IGNORECASE))
            total_conflicts += conflicts
        
        # Normalize by chapter length (conflicts per 1000 words)
        word_count = len(chapter_text.split())
        conflict_density = (total_conflicts / word_count) * 1000 if word_count > 0 else 0
        
        genre_min = self.genre_standards.get(self.target_genre, {}).get('min_conflict_density', 4)
        
        if conflict_density >= genre_min + 2:
            return 'strong'
        elif conflict_density >= genre_min:
            return 'medium'
        else:
            return 'weak'
    
    def _calculate_dialogue_ratio(self, chapter_text: str) -> float:
        """Calculate the ratio of dialogue to exposition."""
        
        # Count dialogue (text in quotes)
        dialogue_matches = re.findall(r'"[^"]*"', chapter_text)
        dialogue_words = sum(len(match.split()) for match in dialogue_matches)
        
        # Total words
        total_words = len(chapter_text.split())
        
        if total_words == 0:
            return 0.0
        
        return dialogue_words / total_words
    
    def _count_question_generation(self, chapter_text: str) -> int:
        """Count question generation throughout the chapter."""
        
        total_questions = 0
        for pattern in self.question_patterns:
            questions = len(re.findall(pattern, chapter_text, re.IGNORECASE))
            total_questions += questions
        
        return total_questions
    
    def _analyze_surprise_factor(self, chapter_text: str) -> str:
        """Analyze the surprise/unpredictability factor."""
        
        surprise_count = 0
        for pattern in self.surprise_patterns:
            surprises = len(re.findall(pattern, chapter_text, re.IGNORECASE))
            surprise_count += surprises
        
        if surprise_count >= 5:
            return 'strong'
        elif surprise_count >= 2:
            return 'medium'
        else:
            return 'weak'
    
    def _calculate_engagement_score(self, hook_strength: str, momentum_maintenance: str,
                                  ending_propulsion: str, conflict_density: str,
                                  dialogue_ratio: float, question_rate: int,
                                  surprise_factor: str) -> float:
        """Calculate overall engagement score (1-10 scale)."""
        
        score = 0.0
        
        # Hook strength (0-2 points)
        hook_scores = {'strong': 2.0, 'medium': 1.2, 'weak': 0.5}
        score += hook_scores.get(hook_strength, 0)
        
        # Momentum maintenance (0-2.5 points)
        momentum_scores = {'strong': 2.5, 'medium': 1.5, 'weak': 0.5}
        score += momentum_scores.get(momentum_maintenance, 0)
        
        # Ending propulsion (0-2 points)
        ending_scores = {'strong': 2.0, 'medium': 1.2, 'weak': 0.3}
        score += ending_scores.get(ending_propulsion, 0)
        
        # Conflict density (0-1.5 points)
        conflict_scores = {'strong': 1.5, 'medium': 1.0, 'weak': 0.3}
        score += conflict_scores.get(conflict_density, 0)
        
        # Dialogue ratio (0-1 point)
        if 0.4 <= dialogue_ratio <= 0.7:  # Optimal range
            score += 1.0
        elif 0.3 <= dialogue_ratio <= 0.8:  # Good range
            score += 0.7
        else:
            score += 0.3
        
        # Question generation (0-1 point)
        genre_min_questions = self.genre_standards.get(self.target_genre, {}).get('min_question_rate', 3)
        if question_rate >= genre_min_questions + 2:
            score += 1.0
        elif question_rate >= genre_min_questions:
            score += 0.7
        else:
            score += 0.2
        
        # Surprise factor (0-1 point)
        surprise_scores = {'strong': 1.0, 'medium': 0.6, 'weak': 0.2}
        score += surprise_scores.get(surprise_factor, 0)
        
        return round(score, 1)
    
    def _generate_risk_flags(self, engagement_score: float, hook_strength: str,
                           momentum_maintenance: str, ending_propulsion: str,
                           conflict_density: str, dialogue_ratio: float,
                           question_rate: int) -> List[str]:
        """Generate risk flags based on engagement analysis."""
        
        flags = []
        
        if engagement_score <= 6.0:
            flags.append("Chapter may not maintain reader interest")
        
        if hook_strength == 'weak':
            flags.append("Weak opening may lose readers immediately")
        
        if momentum_maintenance == 'weak':
            flags.append("Chapter lacks momentum to sustain interest")
        
        if ending_propulsion == 'weak':
            flags.append("Chapter ending doesn't create forward momentum")
        
        if conflict_density == 'weak':
            flags.append("Chapter lacks tension to drive reading")
        
        if dialogue_ratio < 0.3:
            flags.append("Too much exposition - chapter may feel like info dump")
        
        if question_rate < 2:
            flags.append("Story events may be too predictable")
        
        return flags
    
    def _check_genre_compliance(self, conflict_density: str, question_rate: int,
                               chapter_text: str) -> str:
        """Check compliance with genre-specific engagement standards."""
        
        standards = self.genre_standards.get(self.target_genre, {})
        
        if not standards:
            return 'unknown_genre'
        
        compliance_score = 0
        total_checks = 0
        
        # Check conflict density
        min_conflict = standards.get('min_conflict_density', 3)
        conflict_scores = {'strong': 6, 'medium': 4, 'weak': 1}
        if conflict_scores.get(conflict_density, 0) >= min_conflict:
            compliance_score += 1
        total_checks += 1
        
        # Check question rate
        min_questions = standards.get('min_question_rate', 2)
        if question_rate >= min_questions:
            compliance_score += 1
        total_checks += 1
        
        # Check tension requirement
        if standards.get('required_tension', False):
            tension_indicators = ['danger', 'threat', 'risk', 'problem', 'trouble', 'conflict']
            has_tension = any(re.search(rf'\b{indicator}\b', chapter_text, re.IGNORECASE) 
                            for indicator in tension_indicators)
            if has_tension:
                compliance_score += 1
            total_checks += 1
        
        compliance_rate = compliance_score / total_checks if total_checks > 0 else 1.0
        
        if compliance_rate >= 0.8:
            return 'excellent'
        elif compliance_rate >= 0.6:
            return 'good'
        elif compliance_rate >= 0.4:
            return 'needs_improvement'
        else:
            return 'poor'
    
    def _generate_recommendations(self, hook_strength: str, momentum_maintenance: str,
                                ending_propulsion: str, conflict_density: str,
                                dialogue_ratio: float, question_rate: int,
                                surprise_factor: str) -> List[str]:
        """Generate specific recommendations for improving engagement."""
        
        recommendations = []
        
        if hook_strength == 'weak':
            recommendations.append("🚀 Strengthen opening: Start with immediate conflict, question, or tension")
        
        if momentum_maintenance == 'weak':
            recommendations.append("⚡ Improve momentum: Add more dialogue, action, and forward movement")
        
        if ending_propulsion == 'weak':
            recommendations.append("🎯 Enhance ending: Add cliffhanger, revelation, or unresolved tension")
        
        if conflict_density == 'weak':
            recommendations.append("⚔️ Increase conflict: Add tension, obstacles, or character disagreements")
        
        if dialogue_ratio < 0.3:
            recommendations.append("💬 Add dialogue: Convert exposition to character interaction")
        elif dialogue_ratio > 0.8:
            recommendations.append("📝 Balance dialogue: Add some action or description between conversations")
        
        if question_rate < 3:
            recommendations.append("❓ Create questions: Add mystery elements or unanswered complications")
        
        if surprise_factor == 'weak':
            recommendations.append("🎪 Add surprises: Include unexpected but logical developments")
        
        # Genre-specific recommendations
        if self.target_genre == 'thriller' and conflict_density != 'strong':
            recommendations.append("🔥 Thriller requirement: Increase tension and danger throughout")
        
        if self.target_genre == 'mystery' and question_rate < 4:
            recommendations.append("🔍 Mystery requirement: Add more questions and clues")
        
        return recommendations
    
    def _save_analysis(self, analysis: EngagementAnalysis):
        """Save engagement analysis to results file."""
        
        results_data = {}
        
        # Load existing results
        if self.results_path.exists():
            try:
                with open(self.results_path, 'r', encoding='utf-8') as f:
                    results_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        
        # Add new analysis
        chapter_key = f"chapter_{analysis.chapter_number:03d}"
        results_data[chapter_key] = asdict(analysis)
        results_data[chapter_key]['timestamp'] = datetime.now().isoformat()
        
        # Save updated results
        with open(self.results_path, 'w', encoding='utf-8') as f:
            json.dump(results_data, f, indent=2)
    
    def get_engagement_summary(self) -> Dict[str, Any]:
        """Get summary of engagement scores across all chapters."""
        
        if not self.results_path.exists():
            return {'status': 'no_data', 'chapters_analyzed': 0}
        
        try:
            with open(self.results_path, 'r', encoding='utf-8') as f:
                results_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return {'status': 'error', 'message': 'Unable to load results'}
        
        if not results_data:
            return {'status': 'no_data', 'chapters_analyzed': 0}
        
        chapters = list(results_data.values())
        
        # Calculate statistics
        scores = [chapter['engagement_score'] for chapter in chapters]
        avg_score = sum(scores) / len(scores) if scores else 0
        
        low_engagement_count = sum(1 for score in scores if score <= 6.0)
        risk_chapters = sum(1 for chapter in chapters if chapter['risk_flags'])
        
        # Find most common issues
        all_flags = []
        for chapter in chapters:
            all_flags.extend(chapter['risk_flags'])
        
        flag_counts = {}
        for flag in all_flags:
            flag_counts[flag] = flag_counts.get(flag, 0) + 1
        
        common_issues = sorted(flag_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            'status': 'success',
            'chapters_analyzed': len(chapters),
            'average_engagement_score': round(avg_score, 1),
            'low_engagement_chapters': low_engagement_count,
            'chapters_with_risks': risk_chapters,
            'common_issues': common_issues,
            'score_trend': 'improving' if len(scores) > 1 and scores[-1] > scores[0] else 'stable',
            'last_analysis': max(chapter.get('timestamp', '') for chapter in chapters) if chapters else ''
        }
    
    def run_engagement_test(self) -> Dict[str, Any]:
        """Test the engagement scoring system."""
        
        # High engagement test chapter
        high_engagement_chapter = """
        The gunshot shattered the morning silence, sending Sarah diving behind the nearest car.
        
        "Stay down!" Marcus shouted, his voice barely audible over the ringing in her ears.
        
        She pressed her back against the cold metal, her heart hammering against her ribs. 
        This wasn't supposed to happen. The informant had promised it would be safe.
        
        "Sarah, we need to move. Now." Marcus grabbed her arm, his eyes scanning the rooftops 
        where the shot had come from.
        
        But as they ran toward the alley, Sarah realized something that made her blood freeze.
        The gunshot had come from inside the building. Someone on their team was a traitor.
        
        "Marcus," she gasped, "we can't trust anyone."
        
        His expression told her he'd already figured that out. The question was: who?
        """
        
        # Low engagement test chapter  
        low_engagement_chapter = """
        Sarah woke up on Tuesday morning and made herself a cup of coffee. She had been
        working on the case for three weeks now, and the evidence was slowly coming together.
        The files were organized alphabetically on her desk, and she had created a timeline
        of events that stretched back six months.
        
        She reviewed the witness statements again, comparing them to the physical evidence
        that had been collected at the scene. The forensic team had done thorough work,
        documenting everything according to proper procedure.
        
        After finishing her coffee, Sarah decided to visit the crime scene again. She 
        drove across town, noting the morning traffic patterns. The weather was overcast
        but not threatening rain.
        
        At the scene, she took additional photographs and measurements, updating her notes
        with any new observations. The investigation was proceeding methodically.
        """
        
        try:
            # Test high engagement chapter
            high_analysis = self.analyze_chapter_engagement(high_engagement_chapter, 998)
            
            # Test low engagement chapter
            low_analysis = self.analyze_chapter_engagement(low_engagement_chapter, 999)
            
            return {
                'status': 'success',
                'high_engagement_score': high_analysis.engagement_score,
                'low_engagement_score': low_analysis.engagement_score,
                'score_difference': high_analysis.engagement_score - low_analysis.engagement_score,
                'high_risk_flags': len(high_analysis.risk_flags),
                'low_risk_flags': len(low_analysis.risk_flags),
                'test_passed': (high_analysis.engagement_score > low_analysis.engagement_score and
                              high_analysis.engagement_score >= 7.0 and
                              low_analysis.engagement_score <= 6.0)
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'test_passed': False
            }

# CLI Interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Reader Engagement Scorer")
    parser.add_argument("action", choices=["analyze", "summary", "test"], 
                       help="Action to perform")
    parser.add_argument("--chapter-file", help="Chapter file to analyze")
    parser.add_argument("--chapter-number", type=int, help="Chapter number")
    parser.add_argument("--text", help="Chapter text for direct analysis")
    parser.add_argument("--genre", default="thriller", help="Target genre for scoring")
    
    args = parser.parse_args()
    
    scorer = ReaderEngagementScorer(target_genre=args.genre)
    
    if args.action == "analyze" and (args.chapter_file or args.text) and args.chapter_number:
        if args.chapter_file:
            with open(args.chapter_file, 'r', encoding='utf-8') as f:
                chapter_text = f.read()
        else:
            chapter_text = args.text
        
        analysis = scorer.analyze_chapter_engagement(chapter_text, args.chapter_number)
        
        print(f"📊 Reader Engagement Analysis - Chapter {args.chapter_number}")
        print(f"Genre: {args.genre.title()}")
        print("=" * 60)
        print(f"🎯 Overall Engagement Score: {analysis.engagement_score}/10.0")
        print()
        
        print("📈 Component Scores:")
        print(f"  Hook Strength: {analysis.hook_strength.title()}")
        print(f"  Momentum Maintenance: {analysis.momentum_maintenance.title()}")
        print(f"  Ending Propulsion: {analysis.ending_propulsion.title()}")
        print(f"  Conflict Density: {analysis.conflict_density.title()}")
        print(f"  Dialogue Ratio: {analysis.dialogue_exposition_ratio:.1%}")
        print(f"  Question Generation: {analysis.question_generation_rate} questions")
        print(f"  Surprise Factor: {analysis.surprise_factor.title()}")
        print()
        
        print(f"🎭 Genre Compliance: {analysis.genre_compliance.title()}")
        
        if analysis.risk_flags:
            print(f"\n🚨 Risk Flags ({len(analysis.risk_flags)}):")
            for flag in analysis.risk_flags:
                print(f"  ⚠️ {flag}")
        
        if analysis.recommendations:
            print(f"\n💡 Recommendations ({len(analysis.recommendations)}):")
            for rec in analysis.recommendations:
                print(f"  {rec}")
        
        # Engagement assessment
        if analysis.engagement_score >= 8:
            print(f"\n✅ EXCELLENT: Page-turning compulsion achieved")
        elif analysis.engagement_score >= 7:
            print(f"\n✅ GOOD: Solid engagement maintained")
        elif analysis.engagement_score >= 6:
            print(f"\n⚠️ ADEQUATE: May lose some readers")
        else:
            print(f"\n❌ RISK: High probability of reader abandonment")
    
    elif args.action == "summary":
        summary = scorer.get_engagement_summary()
        
        if summary['status'] == 'no_data':
            print("No engagement data available. Analyze some chapters first.")
        elif summary['status'] == 'error':
            print(f"Error: {summary['message']}")
        else:
            print("📊 Engagement Summary")
            print("=" * 40)
            print(f"Chapters Analyzed: {summary['chapters_analyzed']}")
            print(f"Average Score: {summary['average_engagement_score']}/10.0")
            print(f"Low Engagement Chapters: {summary['low_engagement_chapters']}")
            print(f"Chapters with Risk Flags: {summary['chapters_with_risks']}")
            print(f"Score Trend: {summary['score_trend'].title()}")
            
            if summary['common_issues']:
                print(f"\nMost Common Issues:")
                for issue, count in summary['common_issues']:
                    print(f"  {count}x: {issue}")
    
    elif args.action == "test":
        results = scorer.run_engagement_test()
        
        print("🧪 Reader Engagement Scorer Test")
        print("=" * 40)
        print(f"Status: {results['status']}")
        print(f"Test Passed: {'✅ YES' if results['test_passed'] else '❌ NO'}")
        
        if results['status'] == 'success':
            print(f"\nHigh Engagement Chapter: {results['high_engagement_score']}/10.0")
            print(f"Low Engagement Chapter: {results['low_engagement_score']}/10.0")
            print(f"Score Difference: {results['score_difference']:.1f} points")
            print(f"High Chapter Risk Flags: {results['high_risk_flags']}")
            print(f"Low Chapter Risk Flags: {results['low_risk_flags']}")
        else:
            print(f"Error: {results.get('error', 'Unknown error')}")
    
    else:
        print("Please provide required arguments for the specified action")
        parser.print_help() 