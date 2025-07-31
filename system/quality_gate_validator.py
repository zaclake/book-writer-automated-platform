#!/usr/bin/env python3
"""
Quality Gate Validator
Parses quality-gates.yml and provides quality assessment functionality.
"""

import yaml
import json
from pathlib import Path
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass

@dataclass
class QualityScore:
    """Represents a quality assessment score."""
    category: str
    score: float
    minimum_required: float
    target: float
    passed: bool
    sub_scores: Dict[str, float] = None
    notes: List[str] = None

class QualityGateValidator:
    """Validates chapters against quality gate configuration."""
    
    def __init__(self, config_path: str = "quality-gates.yml"):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """Load quality gates configuration from YAML."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Quality gates config not found: {self.config_path}")
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in quality gates config: {e}")
    
    def get_quality_categories(self) -> Dict[str, Dict]:
        """Get all quality categories and their thresholds."""
        return self.config.get('quality_categories', {})
    
    def get_success_criteria(self) -> Dict[str, float]:
        """Get overall success criteria."""
        return self.config.get('success_criteria', {})
    
    def get_critical_failures(self) -> List[Dict]:
        """Get critical failure conditions."""
        return self.config.get('critical_failures', {}).get('automatic_failures', [])
    
    def validate_word_count(self, word_count: int) -> QualityScore:
        """Validate chapter word count against requirements."""
        compliance = self.config['enhanced_system_compliance']['requirements']['word_count_verification']
        target_range = compliance['target_range_words']
        variance = compliance['acceptable_variance']
        
        min_words = target_range[0] - variance
        max_words = target_range[1] + variance
        target_words = sum(target_range) // 2
        
        # Calculate score based on how close to target
        if min_words <= word_count <= max_words:
            # Perfect score if within range
            distance_from_target = abs(word_count - target_words)
            max_distance = variance
            score = 10.0 - (distance_from_target / max_distance) * 2.0
            score = max(8.0, score)  # Minimum 8.0 if within range
        else:
            # Score decreases with distance outside range
            if word_count < min_words:
                variance_pct = ((min_words - word_count) / target_words) * 100
            else:
                variance_pct = ((word_count - max_words) / target_words) * 100
            
            if variance_pct <= 5:
                score = 7.0
            elif variance_pct <= 10:
                score = 6.0
            elif variance_pct <= 20:
                score = 4.0
            elif variance_pct <= 30:
                score = 2.0
            else:
                score = 0.0
        
        return QualityScore(
            category="word_count",
            score=score,
            minimum_required=compliance['minimum'],
            target=10.0,
            passed=score >= compliance['minimum'],
            notes=[f"Word count: {word_count} (target: {target_range[0]}-{target_range[1]})"]
        )
    
    def check_critical_failures(self, chapter_text: str, metadata: Dict = None) -> List[str]:
        """Check for critical failure conditions."""
        failures = []
        
        # Check for em-dash usage
        if '—' in chapter_text:
            failures.append("EM-DASH USAGE (—) - Automatic failure")
        
        # Check word count if metadata provided
        if metadata and 'word_count' in metadata:
            word_count = metadata['word_count']
            target_range = self.config['enhanced_system_compliance']['requirements']['word_count_verification']['target_range_words']
            target = sum(target_range) // 2
            variance_pct = abs(word_count - target) / target * 100
            
            if variance_pct > 30:
                failures.append("Word count more than 30% off target")
        
        # Check for series contamination if metadata provided
        if metadata and 'series_content_percentage' in metadata:
            if metadata['series_content_percentage'] > 10:
                failures.append("Series setup exceeds 10% of content")
        
        return failures
    
    def calculate_brutal_assessment_score(self, scores: Dict[str, float]) -> Tuple[float, str]:
        """Calculate brutal assessment score from category scores."""
        brutal_config = self.config['brutal_assessment']
        categories = brutal_config['categories']
        
        total_weighted_score = 0.0
        total_weight = 0.0
        
        # Map quality category scores to brutal assessment categories
        category_mapping = {
            'structural_integrity': ['story_function', 'enhanced_system_compliance'],
            'character_development': ['character_authenticity'],
            'technical_authenticity': ['enhanced_system_compliance'],
            'prose_quality': ['prose_quality'],
            'market_viability': ['reader_engagement', 'emotional_impact'],
            'execution_quality': ['pattern_freshness']
        }
        
        for brutal_cat, weight_info in categories.items():
            weight = weight_info['weight']
            
            # Average scores from mapped categories
            if brutal_cat in category_mapping:
                mapped_scores = [scores.get(cat, 8.0) for cat in category_mapping[brutal_cat]]
                avg_score = sum(mapped_scores) / len(mapped_scores)
            else:
                avg_score = 8.0  # Default if no mapping
            
            # Convert 10-point scale to 100-point scale
            brutal_score = avg_score * 10
            
            total_weighted_score += brutal_score * weight
            total_weight += weight
        
        final_score = total_weighted_score / total_weight if total_weight > 0 else 0
        
        # Determine assessment level
        scale = brutal_config['scoring_scale']
        if scale['publication_ready'][0] <= final_score <= scale['publication_ready'][1]:
            level = "Publication Ready"
        elif scale['professional_quality'][0] <= final_score <= scale['professional_quality'][1]:
            level = "Professional Quality"
        elif scale['solid_foundation'][0] <= final_score <= scale['solid_foundation'][1]:
            level = "Solid Foundation"
        elif scale['major_revision_required'][0] <= final_score <= scale['major_revision_required'][1]:
            level = "Major Revision Required"
        elif scale['serious_problems'][0] <= final_score <= scale['serious_problems'][1]:
            level = "Serious Problems"
        else:
            level = "Not Ready"
        
        return final_score, level
    
    def assess_overall_quality(self, category_scores: Dict[str, float]) -> Dict[str, Any]:
        """Perform overall quality assessment."""
        success_criteria = self.get_success_criteria()
        
        # Check individual category requirements
        category_results = {}
        overall_passed = True
        
        for category, score in category_scores.items():
            if category in ['pattern_freshness', 'reader_engagement']:
                minimum = success_criteria.get(f"{category}_minimum", 7.0)
            else:
                minimum = success_criteria.get("all_other_categories_minimum", 8.0)
            
            passed = score >= minimum
            category_results[category] = {
                'score': score,
                'minimum_required': minimum,
                'passed': passed
            }
            
            if not passed:
                overall_passed = False
        
        # Calculate brutal assessment
        brutal_score, brutal_level = self.calculate_brutal_assessment_score(category_scores)
        brutal_passed = brutal_score >= success_criteria.get("brutal_assessment_minimum", 8.5) * 10
        
        if not brutal_passed:
            overall_passed = False
        
        # Calculate weighted overall score
        weights = {cat: info.get('weight', 0.1) for cat, info in self.get_quality_categories().items()}
        total_weighted = sum(score * weights.get(cat, 0.1) for cat, score in category_scores.items())
        total_weight = sum(weights.get(cat, 0.1) for cat in category_scores.keys())
        overall_score = total_weighted / total_weight if total_weight > 0 else 0
        
        return {
            'overall_score': overall_score,
            'overall_passed': overall_passed,
            'category_results': category_results,
            'brutal_assessment': {
                'score': brutal_score,
                'level': brutal_level,
                'passed': brutal_passed
            },
            'success_threshold': success_criteria.get("minimum_passing_score", 8.0),
            'excellence_threshold': success_criteria.get("target_excellence_score", 8.5),
            'publication_threshold': success_criteria.get("publication_ready_score", 9.0)
        }
    
    def get_processing_order(self) -> List[str]:
        """Get the order in which quality gates should be processed."""
        return self.config.get('processing_order', [])
    
    def validate_config(self) -> List[str]:
        """Validate the quality gates configuration."""
        errors = []
        
        # Check required sections
        required_sections = [
            'quality_categories', 
            'enhanced_system_compliance',
            'series_balance',
            'brutal_assessment',
            'success_criteria'
        ]
        
        for section in required_sections:
            if section not in self.config:
                errors.append(f"Missing required section: {section}")
        
        # Check quality categories have required fields
        if 'quality_categories' in self.config:
            for category, config in self.config['quality_categories'].items():
                required_fields = ['minimum_score', 'target_score', 'weight']
                for field in required_fields:
                    if field not in config:
                        errors.append(f"Category {category} missing required field: {field}")
        
        return errors
    
    def export_summary(self) -> Dict[str, Any]:
        """Export a summary of the quality gate configuration."""
        return {
            'metadata': self.config.get('metadata', {}),
            'total_categories': len(self.get_quality_categories()),
            'success_criteria': self.get_success_criteria(),
            'critical_failure_count': len(self.get_critical_failures()),
            'processing_order': self.get_processing_order(),
            'configuration_valid': len(self.validate_config()) == 0
        }

# CLI Interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Quality Gate Validator")
    parser.add_argument("action", choices=["validate", "summary", "assess", "word-count"], 
                       help="Action to perform")
    parser.add_argument("--config", default="quality-gates.yml", 
                       help="Path to quality gates config file")
    parser.add_argument("--word-count", type=int, 
                       help="Word count to validate")
    parser.add_argument("--scores", 
                       help="JSON string of category scores for assessment")
    parser.add_argument("--chapter-file", 
                       help="Chapter file to check for critical failures")
    
    args = parser.parse_args()
    
    try:
        validator = QualityGateValidator(args.config)
        
        if args.action == "validate":
            errors = validator.validate_config()
            if errors:
                print("❌ Configuration validation errors:")
                for error in errors:
                    print(f"  - {error}")
                exit(1)
            else:
                print("✅ Quality gates configuration is valid")
        
        elif args.action == "summary":
            summary = validator.export_summary()
            print("Quality Gates Configuration Summary:")
            print(f"  Version: {summary['metadata'].get('version', 'Unknown')}")
            print(f"  Categories: {summary['total_categories']}")
            print(f"  Critical failures: {summary['critical_failure_count']}")
            print(f"  Valid config: {'✅ Yes' if summary['configuration_valid'] else '❌ No'}")
            print(f"  Minimum passing score: {summary['success_criteria'].get('minimum_passing_score', 8.0)}")
        
        elif args.action == "word-count" and args.word_count:
            result = validator.validate_word_count(args.word_count)
            status = "✅ Pass" if result.passed else "❌ Fail"
            print(f"Word Count Assessment: {status}")
            print(f"  Score: {result.score:.1f}/10.0")
            print(f"  Required: {result.minimum_required}+")
            for note in result.notes:
                print(f"  {note}")
        
        elif args.action == "assess" and args.scores:
            scores = json.loads(args.scores)
            assessment = validator.assess_overall_quality(scores)
            
            status = "✅ Pass" if assessment['overall_passed'] else "❌ Fail"
            print(f"Overall Quality Assessment: {status}")
            print(f"  Overall Score: {assessment['overall_score']:.1f}/10.0")
            print(f"  Brutal Assessment: {assessment['brutal_assessment']['score']:.1f}/100 ({assessment['brutal_assessment']['level']})")
            
            print("\nCategory Results:")
            for category, result in assessment['category_results'].items():
                status = "✅" if result['passed'] else "❌"
                print(f"  {status} {category}: {result['score']:.1f} (min: {result['minimum_required']})")
        
        else:
            print("Please provide required arguments for the specified action")
            parser.print_help()
    
    except Exception as e:
        print(f"❌ Error: {e}")
        exit(1) 