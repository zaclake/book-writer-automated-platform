#!/usr/bin/env python3
"""
Series Balance Autocheck
Automated series balance analysis using series-balance-guidelines.md rules.
"""

import re
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass, asdict

@dataclass
class SeriesElement:
    """Represents a series setup element found in text."""
    type: str
    content: str
    line_number: int
    word_count: int
    purpose: str  # future_setup, character_introduction, world_building, etc.
    enhancement_score: float  # How much it enhances current story (0-10)

@dataclass
class SeriesBalanceResult:
    """Results of series balance analysis."""
    chapter_number: int
    total_word_count: int
    series_setup_word_count: int
    series_content_percentage: float
    individual_story_percentage: float
    compliance_score: float
    series_elements: List[SeriesElement]
    standalone_satisfaction_score: float
    recommendations: List[str]
    passes_guidelines: bool

class SeriesBalanceAutocheck:
    """Automated series balance analysis and compliance checking."""
    
    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.state_dir = self.project_path / ".project-state"
        self.results_path = self.state_dir / "series-balance-results.json"
        
        # Series setup detection patterns
        self.series_setup_patterns = {
            'future_character_setup': [
                r'would\s+(?:become|prove|turn\s+out\s+to\s+be|later\s+be)',
                r'(?:someday|eventually|in\s+time|later)\s+(?:he|she|they|it)\s+would',
                r'(?:destined|meant)\s+to\s+(?:become|be|meet|face)',
                r'(?:little\s+did\s+(?:he|she|they)|unbeknownst\s+to)',
                r'(?:seeds\s+of|beginning\s+of|start\s+of)\s+(?:what\s+would|something)',
                r'(?:first\s+time|only\s+the\s+beginning|this\s+was\s+just\s+the\s+start)'
            ],
            'world_expansion_setup': [
                r'(?:distant|far\s+off|other|neighboring)\s+(?:cities|towns|countries|regions)',
                r'(?:rumors|stories|legends)\s+(?:spoke\s+of|told\s+of|mentioned)',
                r'(?:organization|agency|group|society)\s+(?:that\s+operated|known\s+for)',
                r'(?:broader|larger|wider)\s+(?:conspiracy|network|organization)',
                r'(?:elsewhere|meanwhile|in\s+other\s+places)',
                r'(?:ancient|old|forgotten)\s+(?:prophecies|legends|texts|knowledge)'
            ],
            'future_conflict_setup': [
                r'(?:this\s+wouldn\'t\s+be\s+the\s+last|more\s+trouble\s+was\s+coming)',
                r'(?:shadows\s+of|hints\s+of|signs\s+of)\s+(?:larger|greater|bigger)',
                r'(?:something\s+bigger|larger\s+forces|greater\s+powers)\s+at\s+work',
                r'(?:only\s+the\s+tip\s+of\s+the\s+iceberg|just\s+the\s+beginning)',
                r'(?:deeper|darker|more\s+complex)\s+(?:mystery|conspiracy|truth)',
                r'(?:new\s+enemies|fresh\s+challenges|different\s+threats)\s+(?:await|lurk)'
            ],
            'character_background_setup': [
                r'(?:past\s+that|history\s+that|secrets\s+that)\s+(?:would|might|could)',
                r'(?:skills|training|experience)\s+(?:would\s+prove|might\s+become)',
                r'(?:connections|relationships|ties)\s+to\s+(?:powerful|important|influential)',
                r'(?:family|bloodline|heritage)\s+(?:held|contained|carried)',
                r'(?:dormant|hidden|latent)\s+(?:abilities|powers|talents)',
                r'(?:mentor|teacher|guide)\s+who\s+(?:would|might|could)\s+(?:appear|return)'
            ],
            'sequel_baiting': [
                r'(?:to\s+be\s+continued|will\s+continue|story\s+continues)',
                r'(?:next\s+time|in\s+the\s+next|coming\s+soon)',
                r'(?:but\s+that\'s\s+another\s+story|that\'s\s+a\s+tale\s+for\s+another)',
                r'(?:tune\s+in|stay\s+tuned|don\'t\s+miss)',
                r'(?:will\s+return|be\s+back|see\s+you\s+next)',
                r'(?:adventure\s+awaits|journey\s+continues|saga\s+goes\s+on)'
            ]
        }
        
        # Enhancement vs. distraction indicators
        self.enhancement_indicators = [
            r'(?:deepened|enriched|enhanced|strengthened)\s+(?:understanding|relationship|character)',
            r'(?:revealed|showed|demonstrated)\s+(?:more\s+about|deeper\s+side)',
            r'(?:added|brought|provided)\s+(?:depth|complexity|nuance)',
            r'(?:natural|organic|seamless)\s+(?:extension|development|evolution)'
        ]
        
        self.distraction_indicators = [
            r'(?:suddenly|abruptly|out\s+of\s+nowhere)',
            r'(?:random|unrelated|tangential)\s+(?:mention|reference|discussion)',
            r'(?:forced|artificial|contrived)\s+(?:introduction|setup|connection)',
            r'(?:interrupted|disrupted|broke)\s+(?:flow|momentum|pacing)'
        ]
        
        # Ensure state directory exists
        self.state_dir.mkdir(exist_ok=True)
    
    def analyze_chapter(self, chapter_text: str, chapter_number: int) -> SeriesBalanceResult:
        """Analyze a chapter for series balance compliance."""
        
        # Calculate basic metrics
        total_words = len(chapter_text.split())
        
        # Detect series elements
        series_elements = self._detect_series_elements(chapter_text)
        
        # Calculate series content word count
        series_word_count = sum(element.word_count for element in series_elements)
        
        # Calculate percentages
        series_percentage = (series_word_count / total_words * 100) if total_words > 0 else 0
        individual_percentage = 100 - series_percentage
        
        # Calculate compliance score
        compliance_score = self._calculate_compliance_score(series_percentage, series_elements)
        
        # Calculate standalone satisfaction score
        standalone_score = self._calculate_standalone_satisfaction(chapter_text, series_elements)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(series_percentage, series_elements, standalone_score)
        
        # Determine if guidelines are met
        passes_guidelines = self._check_guidelines_compliance(series_percentage, compliance_score, standalone_score)
        
        result = SeriesBalanceResult(
            chapter_number=chapter_number,
            total_word_count=total_words,
            series_setup_word_count=series_word_count,
            series_content_percentage=series_percentage,
            individual_story_percentage=individual_percentage,
            compliance_score=compliance_score,
            series_elements=series_elements,
            standalone_satisfaction_score=standalone_score,
            recommendations=recommendations,
            passes_guidelines=passes_guidelines
        )
        
        # Save result
        self._save_result(result)
        
        return result
    
    def _detect_series_elements(self, text: str) -> List[SeriesElement]:
        """Detect series setup elements in the text."""
        elements = []
        lines = text.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue
            
            # Check each pattern category
            for element_type, patterns in self.series_setup_patterns.items():
                for pattern in patterns:
                    matches = re.finditer(pattern, line, re.IGNORECASE)
                    for match in matches:
                        # Extract context around the match
                        context = self._extract_context(line, match.start(), match.end())
                        word_count = len(context.split())
                        
                        # Calculate enhancement score
                        enhancement_score = self._calculate_enhancement_score(context)
                        
                        element = SeriesElement(
                            type=element_type,
                            content=context,
                            line_number=line_num,
                            word_count=word_count,
                            purpose=self._determine_purpose(element_type, context),
                            enhancement_score=enhancement_score
                        )
                        
                        elements.append(element)
        
        # Remove duplicates based on content similarity
        elements = self._deduplicate_elements(elements)
        
        return elements
    
    def _extract_context(self, line: str, start: int, end: int, context_length: int = 20) -> str:
        """Extract context around a pattern match."""
        words = line.split()
        match_text = line[start:end]
        
        # Find the word boundaries
        match_words = match_text.split()
        if not match_words:
            return match_text
        
        # Find starting word index
        start_word = 0
        for i, word in enumerate(words):
            if match_words[0].lower() in word.lower():
                start_word = max(0, i - context_length // 2)
                break
        
        # Extract context
        end_word = min(len(words), start_word + context_length)
        context_words = words[start_word:end_word]
        
        return ' '.join(context_words)
    
    def _calculate_enhancement_score(self, context: str) -> float:
        """Calculate how much a series element enhances vs. distracts from current story."""
        score = 5.0  # Neutral starting point
        
        # Check for enhancement indicators
        for pattern in self.enhancement_indicators:
            if re.search(pattern, context, re.IGNORECASE):
                score += 1.5
        
        # Check for distraction indicators
        for pattern in self.distraction_indicators:
            if re.search(pattern, context, re.IGNORECASE):
                score -= 2.0
        
        # Check for current story relevance
        current_story_indicators = [
            r'(?:current|present|immediate|now|today)',
            r'(?:here|this\s+(?:situation|moment|case|problem))',
            r'(?:facing|dealing\s+with|confronting|handling)'
        ]
        
        for pattern in current_story_indicators:
            if re.search(pattern, context, re.IGNORECASE):
                score += 1.0
        
        return max(0.0, min(10.0, score))
    
    def _determine_purpose(self, element_type: str, context: str) -> str:
        """Determine the purpose of a series element."""
        purpose_map = {
            'future_character_setup': 'character_development_setup',
            'world_expansion_setup': 'world_building_expansion',
            'future_conflict_setup': 'conflict_seeding',
            'character_background_setup': 'character_history_expansion',
            'sequel_baiting': 'future_book_promotion'
        }
        
        return purpose_map.get(element_type, 'unknown_purpose')
    
    def _deduplicate_elements(self, elements: List[SeriesElement]) -> List[SeriesElement]:
        """Remove duplicate series elements based on content similarity."""
        unique_elements = []
        
        for element in elements:
            is_duplicate = False
            for existing in unique_elements:
                # Check for content overlap
                overlap = self._calculate_content_overlap(element.content, existing.content)
                if overlap > 0.7:  # 70% overlap threshold
                    is_duplicate = True
                    # Keep the one with higher enhancement score
                    if element.enhancement_score > existing.enhancement_score:
                        unique_elements.remove(existing)
                        unique_elements.append(element)
                    break
            
            if not is_duplicate:
                unique_elements.append(element)
        
        return unique_elements
    
    def _calculate_content_overlap(self, content1: str, content2: str) -> float:
        """Calculate content overlap between two text snippets."""
        words1 = set(content1.lower().split())
        words2 = set(content2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union)
    
    def _calculate_compliance_score(self, series_percentage: float, elements: List[SeriesElement]) -> float:
        """Calculate compliance score based on series balance guidelines."""
        score = 10.0
        
        # Deduct for excessive series content
        if series_percentage > 5.0:
            score -= (series_percentage - 5.0) * 2.0  # Heavy penalty for exceeding 5%
        elif series_percentage > 3.0:
            score -= (series_percentage - 3.0) * 1.0  # Moderate penalty for exceeding 3%
        
        # Deduct for poor enhancement scores
        if elements:
            avg_enhancement = sum(e.enhancement_score for e in elements) / len(elements)
            if avg_enhancement < 5.0:
                score -= (5.0 - avg_enhancement)
        
        # Deduct for sequel baiting
        sequel_bait_count = sum(1 for e in elements if e.type == 'sequel_baiting')
        score -= sequel_bait_count * 2.0
        
        # Deduct for future setup without current story purpose
        low_purpose_count = sum(1 for e in elements if e.enhancement_score < 3.0)
        score -= low_purpose_count * 1.5
        
        return max(0.0, min(10.0, score))
    
    def _calculate_standalone_satisfaction(self, text: str, elements: List[SeriesElement]) -> float:
        """Calculate standalone reading satisfaction score."""
        score = 10.0
        
        # Check for story completion indicators
        completion_indicators = [
            r'(?:resolved|solved|concluded|finished|completed)',
            r'(?:finally|at\s+last|in\s+the\s+end)',
            r'(?:justice|peace|resolution|closure)',
            r'(?:happy|satisfied|content|fulfilled)',
            r'(?:understood|realized|learned|discovered)'
        ]
        
        completion_count = 0
        for pattern in completion_indicators:
            completion_count += len(re.findall(pattern, text, re.IGNORECASE))
        
        if completion_count < 3:
            score -= 2.0  # Insufficient completion indicators
        
        # Check for unresolved cliffhangers
        cliffhanger_indicators = [
            r'(?:to\s+be\s+continued|what\s+happens\s+next)',
            r'(?:but\s+suddenly|just\s+then|without\s+warning)$',
            r'(?:will\s+they|can\s+they|what\s+will)(?:\s+\w+){0,5}\?$',
            r'(?:the\s+mystery|the\s+question|the\s+answer)\s+(?:remains|waits)'
        ]
        
        cliffhanger_count = 0
        for pattern in cliffhanger_indicators:
            cliffhanger_count += len(re.findall(pattern, text, re.IGNORECASE))
        
        score -= cliffhanger_count * 1.5
        
        # Deduct for excessive series setup that doesn't enhance current story
        distracting_elements = [e for e in elements if e.enhancement_score < 4.0]
        score -= len(distracting_elements) * 0.5
        
        return max(0.0, min(10.0, score))
    
    def _generate_recommendations(self, series_percentage: float, elements: List[SeriesElement], 
                                standalone_score: float) -> List[str]:
        """Generate actionable recommendations for improving series balance."""
        recommendations = []
        
        # Series content percentage recommendations
        if series_percentage > 5.0:
            recommendations.append(f"🚨 CRITICAL: Series content exceeds 5% limit ({series_percentage:.1f}%) - remove or integrate better")
        elif series_percentage > 3.0:
            recommendations.append(f"⚠️ WARNING: Series content approaching limit ({series_percentage:.1f}%) - consider reducing")
        elif series_percentage > 7.0:
            recommendations.append(f"❌ MAJOR VIOLATION: Series content at {series_percentage:.1f}% - immediate reduction required")
        
        # Element-specific recommendations
        sequel_bait_elements = [e for e in elements if e.type == 'sequel_baiting']
        if sequel_bait_elements:
            recommendations.append(f"🎣 Remove {len(sequel_bait_elements)} sequel baiting elements - focus on current story completion")
        
        low_enhancement_elements = [e for e in elements if e.enhancement_score < 4.0]
        if low_enhancement_elements:
            recommendations.append(f"🎯 Improve {len(low_enhancement_elements)} series elements that don't enhance current story")
        
        # Standalone satisfaction recommendations
        if standalone_score < 7.0:
            recommendations.append(f"📖 Standalone satisfaction low ({standalone_score:.1f}/10) - strengthen current story resolution")
        
        if standalone_score < 5.0:
            recommendations.append("🏁 Critical: Current story feels incomplete - ensure full resolution before series considerations")
        
        # Positive reinforcement
        if series_percentage <= 3.0 and standalone_score >= 8.0:
            recommendations.append("✅ Excellent series balance - individual story prioritized appropriately")
        
        if not elements:
            recommendations.append("ℹ️ No series setup detected - pure standalone focus maintained")
        
        return recommendations
    
    def _check_guidelines_compliance(self, series_percentage: float, compliance_score: float, 
                                   standalone_score: float) -> bool:
        """Check if the chapter meets series balance guidelines."""
        # Core requirements from guidelines
        meets_percentage_limit = series_percentage <= 5.0
        meets_compliance_threshold = compliance_score >= 7.0
        meets_standalone_threshold = standalone_score >= 8.0
        
        return meets_percentage_limit and meets_compliance_threshold and meets_standalone_threshold
    
    def _save_result(self, result: SeriesBalanceResult):
        """Save analysis result to database."""
        results_data = {}
        
        # Load existing results
        if self.results_path.exists():
            try:
                with open(self.results_path, 'r', encoding='utf-8') as f:
                    results_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        
        # Add new result
        chapter_key = f"chapter_{result.chapter_number:03d}"
        results_data[chapter_key] = asdict(result)
        
        # Save updated results
        with open(self.results_path, 'w', encoding='utf-8') as f:
            json.dump(results_data, f, indent=2)
    
    def get_project_series_balance_summary(self) -> Dict[str, Any]:
        """Get overall project series balance summary."""
        if not self.results_path.exists():
            return {
                'chapters_analyzed': 0,
                'average_series_percentage': 0.0,
                'average_compliance_score': 0.0,
                'average_standalone_score': 0.0,
                'guideline_violations': 0,
                'total_series_elements': 0
            }
        
        try:
            with open(self.results_path, 'r', encoding='utf-8') as f:
                results_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return {'error': 'Unable to load results data'}
        
        if not results_data:
            return {'chapters_analyzed': 0}
        
        # Calculate summary statistics
        chapters = list(results_data.values())
        
        avg_series_pct = sum(c['series_content_percentage'] for c in chapters) / len(chapters)
        avg_compliance = sum(c['compliance_score'] for c in chapters) / len(chapters)
        avg_standalone = sum(c['standalone_satisfaction_score'] for c in chapters) / len(chapters)
        
        violations = sum(1 for c in chapters if not c['passes_guidelines'])
        total_elements = sum(len(c['series_elements']) for c in chapters)
        
        return {
            'chapters_analyzed': len(chapters),
            'average_series_percentage': avg_series_pct,
            'average_compliance_score': avg_compliance,
            'average_standalone_score': avg_standalone,
            'guideline_violations': violations,
            'total_series_elements': total_elements,
            'violation_rate': violations / len(chapters) if chapters else 0,
            'last_analysis': datetime.now().isoformat()
        }
    
    def generate_series_balance_report(self) -> str:
        """Generate comprehensive series balance report."""
        summary = self.get_project_series_balance_summary()
        
        if 'error' in summary:
            return f"Error generating report: {summary['error']}"
        
        if summary['chapters_analyzed'] == 0:
            return "No chapters analyzed yet for series balance."
        
        report = f"""# Series Balance Analysis Report
Generated: {datetime.now().isoformat()}

## Project Summary
- Chapters Analyzed: {summary['chapters_analyzed']}
- Average Series Content: {summary['average_series_percentage']:.1f}%
- Average Compliance Score: {summary['average_compliance_score']:.1f}/10.0
- Average Standalone Score: {summary['average_standalone_score']:.1f}/10.0
- Guideline Violations: {summary['guideline_violations']} ({summary['violation_rate']:.1%})
- Total Series Elements: {summary['total_series_elements']}

## Compliance Status
"""
        
        if summary['violation_rate'] == 0:
            report += "✅ **EXCELLENT**: All chapters comply with series balance guidelines\n"
        elif summary['violation_rate'] < 0.2:
            report += "✅ **GOOD**: Most chapters comply with guidelines\n"
        elif summary['violation_rate'] < 0.5:
            report += "⚠️ **NEEDS ATTENTION**: Several chapters violate guidelines\n"
        else:
            report += "❌ **CRITICAL**: Majority of chapters violate series balance guidelines\n"
        
        # Load detailed results for chapter breakdown
        if self.results_path.exists():
            with open(self.results_path, 'r', encoding='utf-8') as f:
                results_data = json.load(f)
            
            report += "\n## Chapter-by-Chapter Analysis\n"
            
            for chapter_key, result in sorted(results_data.items()):
                status = "✅" if result['passes_guidelines'] else "❌"
                report += f"""
### {status} Chapter {result['chapter_number']}
- Series Content: {result['series_content_percentage']:.1f}% (limit: 5.0%)
- Compliance Score: {result['compliance_score']:.1f}/10.0
- Standalone Score: {result['standalone_satisfaction_score']:.1f}/10.0
- Series Elements: {len(result['series_elements'])}

Recommendations:
"""
                for rec in result['recommendations']:
                    report += f"  - {rec}\n"
        
        return report

# CLI Interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Series Balance Autocheck")
    parser.add_argument("action", choices=["analyze", "summary", "report"], 
                       help="Action to perform")
    parser.add_argument("--chapter-file", help="Chapter file to analyze")
    parser.add_argument("--chapter-number", type=int, help="Chapter number")
    parser.add_argument("--output", help="Output file for report")
    
    args = parser.parse_args()
    
    autocheck = SeriesBalanceAutocheck()
    
    if args.action == "analyze" and args.chapter_file and args.chapter_number:
        try:
            with open(args.chapter_file, 'r', encoding='utf-8') as f:
                chapter_text = f.read()
            
            result = autocheck.analyze_chapter(chapter_text, args.chapter_number)
            
            print(f"Series Balance Analysis - Chapter {args.chapter_number}")
            print(f"Total Words: {result.total_word_count:,}")
            print(f"Series Content: {result.series_content_percentage:.1f}% ({result.series_setup_word_count} words)")
            print(f"Individual Story: {result.individual_story_percentage:.1f}%")
            print(f"Compliance Score: {result.compliance_score:.1f}/10.0")
            print(f"Standalone Score: {result.standalone_satisfaction_score:.1f}/10.0")
            print(f"Guidelines Compliance: {'✅ Pass' if result.passes_guidelines else '❌ Fail'}")
            
            if result.series_elements:
                print(f"\nSeries Elements Detected: {len(result.series_elements)}")
                for element in result.series_elements:
                    print(f"  - {element.type}: {element.content[:50]}... (Enhancement: {element.enhancement_score:.1f}/10)")
            
            if result.recommendations:
                print("\nRecommendations:")
                for rec in result.recommendations:
                    print(f"  {rec}")
                    
        except FileNotFoundError:
            print(f"Error: Chapter file not found: {args.chapter_file}")
    
    elif args.action == "summary":
        summary = autocheck.get_project_series_balance_summary()
        
        print("Series Balance Summary:")
        for key, value in summary.items():
            if key.endswith('_percentage') or key.endswith('_score'):
                print(f"  {key.replace('_', ' ').title()}: {value:.1f}")
            elif key == 'violation_rate':
                print(f"  {key.replace('_', ' ').title()}: {value:.1%}")
            else:
                print(f"  {key.replace('_', ' ').title()}: {value}")
    
    elif args.action == "report":
        report = autocheck.generate_series_balance_report()
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"Series balance report saved to {args.output}")
        else:
            print(report)
    
    else:
        print("Please provide required arguments for the specified action")
        parser.print_help() 