#!/usr/bin/env python3
"""
Intelligent Retry System
Analyzes failure reasons and implements smart retry strategies with context improvements.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import re
import math


class FailureType(Enum):
    """Types of failures that can occur during chapter generation."""
    QUALITY_GATE_FAILURE = "quality_gate_failure"
    GENERATION_TIMEOUT = "generation_timeout"
    API_ERROR = "api_error"
    CONTEXT_ERROR = "context_error"
    CONTENT_POLICY_VIOLATION = "content_policy_violation"
    INSUFFICIENT_QUALITY = "insufficient_quality"
    REPETITION_DETECTED = "repetition_detected"
    CONSISTENCY_ERROR = "consistency_error"
    WORD_COUNT_FAILURE = "word_count_failure"
    CRITICAL_FAILURE = "critical_failure"
    UNKNOWN_ERROR = "unknown_error"


class RetryStrategy(Enum):
    """Different retry strategies."""
    IMMEDIATE = "immediate"
    LINEAR_BACKOFF = "linear_backoff"
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    ADAPTIVE = "adaptive"
    CONTEXT_IMPROVEMENT = "context_improvement"


@dataclass
class RetryAttempt:
    """Represents a single retry attempt."""
    attempt_number: int
    failure_type: FailureType
    failure_reason: str
    strategy_used: RetryStrategy
    context_modifications: Dict[str, Any]
    timestamp: datetime
    delay_seconds: float
    success: bool
    quality_score: Optional[float] = None
    improvement_applied: Optional[str] = None


@dataclass
class RetryHistory:
    """History of retry attempts for a chapter."""
    chapter_number: int
    original_failure: str
    attempts: List[RetryAttempt]
    total_attempts: int
    successful_attempt: Optional[int]
    final_outcome: str
    total_time_seconds: float
    context_evolution: List[Dict[str, Any]]


class IntelligentRetrySystem:
    """
    Intelligent retry system that learns from failures and adapts retry strategies.
    
    Features:
    - Failure analysis and classification
    - Adaptive retry strategies based on failure type
    - Context improvement suggestions
    - Retry pattern learning
    - Success rate tracking
    """
    
    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.state_dir = self.project_path / ".project-state"
        self.retry_history_file = self.state_dir / "retry-history.json"
        self.retry_patterns_file = self.state_dir / "retry-patterns.json"
        
        # Ensure directories exist
        self.state_dir.mkdir(exist_ok=True)
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        self._setup_logging()
        
        # Load retry history and patterns
        self.retry_history: Dict[int, RetryHistory] = self._load_retry_history()
        self.retry_patterns: Dict[str, Any] = self._load_retry_patterns()
        
        # Configuration
        self.max_retries = 3
        self.base_delay_seconds = 5
        self.max_delay_seconds = 300
        self.quality_improvement_threshold = 5.0
    
    def _setup_logging(self):
        """Set up logging for the retry system."""
        log_dir = self.project_path / "logs"
        log_dir.mkdir(exist_ok=True)
        
        handler = logging.FileHandler(log_dir / f"retry_system_{datetime.now().strftime('%Y%m%d')}.log")
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
    
    def _load_retry_history(self) -> Dict[int, RetryHistory]:
        """Load retry history from file."""
        if not self.retry_history_file.exists():
            return {}
        
        try:
            with open(self.retry_history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            history = {}
            for chapter_str, history_data in data.items():
                chapter_num = int(chapter_str)
                
                # Convert datetime strings back to datetime objects
                attempts = []
                for attempt_data in history_data['attempts']:
                    attempt_data['timestamp'] = datetime.fromisoformat(attempt_data['timestamp'])
                    attempt_data['failure_type'] = FailureType(attempt_data['failure_type'])
                    attempt_data['strategy_used'] = RetryStrategy(attempt_data['strategy_used'])
                    attempts.append(RetryAttempt(**attempt_data))
                
                history_data['attempts'] = attempts
                history[chapter_num] = RetryHistory(**history_data)
            
            return history
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.logger.error(f"Failed to load retry history: {e}")
            return {}
    
    def _load_retry_patterns(self) -> Dict[str, Any]:
        """Load learned retry patterns from file."""
        if not self.retry_patterns_file.exists():
            return self._initialize_default_patterns()
        
        try:
            with open(self.retry_patterns_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, KeyError) as e:
            self.logger.error(f"Failed to load retry patterns: {e}")
            return self._initialize_default_patterns()
    
    def _initialize_default_patterns(self) -> Dict[str, Any]:
        """Initialize default retry patterns."""
        return {
            "failure_type_strategies": {
                "quality_gate_failure": "context_improvement",
                "generation_timeout": "exponential_backoff",
                "api_error": "exponential_backoff",
                "context_error": "context_improvement",
                "content_policy_violation": "context_improvement",
                "insufficient_quality": "context_improvement",
                "repetition_detected": "context_improvement",
                "consistency_error": "context_improvement",
                "word_count_failure": "adaptive",
                "critical_failure": "immediate",
                "unknown_error": "adaptive"
            },
            "success_rates": {},
            "average_improvements": {},
            "context_modifications": {
                "quality_improvements": [
                    "focus on character development",
                    "enhance dialogue quality",
                    "improve scene description",
                    "strengthen plot advancement",
                    "refine pacing"
                ],
                "repetition_fixes": [
                    "avoid previous descriptions",
                    "use different sentence structures",
                    "vary vocabulary choices",
                    "change narrative perspective"
                ],
                "consistency_fixes": [
                    "maintain character voice",
                    "preserve timeline consistency",
                    "ensure plot coherence",
                    "respect established facts"
                ]
            },
            "learning_data": {
                "total_retries": 0,
                "successful_retries": 0,
                "pattern_effectiveness": {}
            }
        }
    
    def _save_retry_history(self):
        """Save retry history to file."""
        try:
            data = {}
            for chapter_num, history in self.retry_history.items():
                history_dict = asdict(history)
                
                # Convert datetime objects to strings
                for attempt in history_dict['attempts']:
                    attempt['timestamp'] = attempt['timestamp'].isoformat() if isinstance(attempt['timestamp'], datetime) else attempt['timestamp']
                    attempt['failure_type'] = attempt['failure_type'].value if hasattr(attempt['failure_type'], 'value') else attempt['failure_type']
                    attempt['strategy_used'] = attempt['strategy_used'].value if hasattr(attempt['strategy_used'], 'value') else attempt['strategy_used']
                
                data[str(chapter_num)] = history_dict
            
            with open(self.retry_history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            self.logger.error(f"Failed to save retry history: {e}")
    
    def _save_retry_patterns(self):
        """Save learned retry patterns to file."""
        try:
            with open(self.retry_patterns_file, 'w', encoding='utf-8') as f:
                json.dump(self.retry_patterns, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"Failed to save retry patterns: {e}")
    
    def analyze_failure(self, chapter_number: int, error_message: str, 
                       quality_result: Optional[Dict[str, Any]] = None) -> FailureType:
        """Analyze failure reason and classify the failure type."""
        
        error_lower = error_message.lower()
        
        # Check for specific failure patterns
        if "quality gate" in error_lower or "quality threshold" in error_lower:
            return FailureType.QUALITY_GATE_FAILURE
        
        if "timeout" in error_lower or "time out" in error_lower:
            return FailureType.GENERATION_TIMEOUT
        
        if "api" in error_lower and ("error" in error_lower or "failed" in error_lower):
            return FailureType.API_ERROR
        
        if "context" in error_lower or "prompt" in error_lower:
            return FailureType.CONTEXT_ERROR
        
        if "policy" in error_lower or "content filter" in error_lower:
            return FailureType.CONTENT_POLICY_VIOLATION
        
        if "word count" in error_lower:
            return FailureType.WORD_COUNT_FAILURE
        
        if "repetition" in error_lower or "duplicate" in error_lower:
            return FailureType.REPETITION_DETECTED
        
        if "consistency" in error_lower or "continuity" in error_lower:
            return FailureType.CONSISTENCY_ERROR
        
        if "critical" in error_lower or "fatal" in error_lower:
            return FailureType.CRITICAL_FAILURE
        
        # Analyze quality result if available
        if quality_result:
            overall_score = quality_result.get('overall_score', 0)
            if overall_score < 50:
                return FailureType.INSUFFICIENT_QUALITY
        
        return FailureType.UNKNOWN_ERROR
    
    def determine_retry_strategy(self, failure_type: FailureType, 
                               attempt_number: int) -> RetryStrategy:
        """Determine the best retry strategy based on failure type and attempt number."""
        
        # Get learned strategy for this failure type
        default_strategy = self.retry_patterns["failure_type_strategies"].get(
            failure_type.value, "adaptive"
        )
        
        # Adaptive strategy selection based on attempt number
        if attempt_number >= 3:
            # For later attempts, always use context improvement
            return RetryStrategy.CONTEXT_IMPROVEMENT
        elif attempt_number == 1:
            # First retry uses the default strategy
            return RetryStrategy(default_strategy)
        else:
            # Second retry might escalate strategy
            if default_strategy == "immediate":
                return RetryStrategy.LINEAR_BACKOFF
            elif default_strategy == "linear_backoff":
                return RetryStrategy.CONTEXT_IMPROVEMENT
            else:
                return RetryStrategy(default_strategy)
    
    def calculate_retry_delay(self, strategy: RetryStrategy, attempt_number: int, 
                            failure_type: FailureType) -> float:
        """Calculate delay before retry based on strategy."""
        
        if strategy == RetryStrategy.IMMEDIATE:
            return 0.0
        
        elif strategy == RetryStrategy.LINEAR_BACKOFF:
            return self.base_delay_seconds * attempt_number
        
        elif strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            delay = self.base_delay_seconds * (2 ** (attempt_number - 1))
            return min(delay, self.max_delay_seconds)
        
        elif strategy == RetryStrategy.ADAPTIVE:
            # Adaptive delay based on failure type
            if failure_type in [FailureType.API_ERROR, FailureType.GENERATION_TIMEOUT]:
                return self.base_delay_seconds * (1.5 ** attempt_number)
            else:
                return self.base_delay_seconds
        
        elif strategy == RetryStrategy.CONTEXT_IMPROVEMENT:
            # Longer delay for context improvement to allow processing
            return self.base_delay_seconds * 2
        
        return self.base_delay_seconds
    
    def improve_context_for_retry(self, original_context: Dict[str, Any], 
                                failure_type: FailureType, attempt_number: int,
                                quality_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Improve context based on failure analysis."""
        
        improved_context = original_context.copy()
        modifications = {}
        
        # Add retry-specific metadata
        improved_context["retry_attempt"] = attempt_number
        improved_context["failure_type"] = failure_type.value
        improved_context["retry_guidance"] = self._generate_retry_guidance(failure_type, quality_result)
        
        # Specific improvements based on failure type
        if failure_type == FailureType.QUALITY_GATE_FAILURE:
            modifications.update(self._improve_quality_context(improved_context, quality_result))
        
        elif failure_type == FailureType.REPETITION_DETECTED:
            modifications.update(self._improve_repetition_context(improved_context))
        
        elif failure_type == FailureType.CONSISTENCY_ERROR:
            modifications.update(self._improve_consistency_context(improved_context))
        
        elif failure_type == FailureType.WORD_COUNT_FAILURE:
            modifications.update(self._improve_word_count_context(improved_context, quality_result))
        
        elif failure_type == FailureType.INSUFFICIENT_QUALITY:
            modifications.update(self._improve_general_quality_context(improved_context, quality_result))
        
        # Apply modifications
        improved_context.update(modifications)
        
        # Add context improvement tracking
        improved_context["context_modifications"] = modifications
        improved_context["improvement_strategy"] = failure_type.value
        
        return improved_context
    
    def _generate_retry_guidance(self, failure_type: FailureType, 
                               quality_result: Optional[Dict[str, Any]]) -> str:
        """Generate specific guidance for retry attempts."""
        
        guidance_map = {
            FailureType.QUALITY_GATE_FAILURE: "Focus on improving overall quality and meeting assessment criteria",
            FailureType.REPETITION_DETECTED: "Avoid repetitive language and vary sentence structures",
            FailureType.CONSISTENCY_ERROR: "Maintain consistency with previous chapters and character development",
            FailureType.WORD_COUNT_FAILURE: "Adjust content length to meet target word count requirements",
            FailureType.INSUFFICIENT_QUALITY: "Enhance writing quality, character development, and plot advancement",
            FailureType.CONTEXT_ERROR: "Improve context understanding and narrative flow",
            FailureType.CONTENT_POLICY_VIOLATION: "Ensure content complies with content policies",
            FailureType.API_ERROR: "Technical retry due to API issues",
            FailureType.GENERATION_TIMEOUT: "Simplify generation requirements to avoid timeout",
            FailureType.CRITICAL_FAILURE: "Address critical system issues before retry"
        }
        
        base_guidance = guidance_map.get(failure_type, "General retry attempt")
        
        # Add specific guidance based on quality results
        if quality_result and 'brutal_assessment' in quality_result:
            brutal_data = quality_result['brutal_assessment']
            category_scores = brutal_data.get('category_scores', {})
            
            low_scoring_categories = [
                category for category, score in category_scores.items() 
                if score < 7.0
            ]
            
            if low_scoring_categories:
                base_guidance += f". Focus specifically on: {', '.join(low_scoring_categories)}"
        
        return base_guidance
    
    def _improve_quality_context(self, context: Dict[str, Any], 
                               quality_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Improve context for quality-related failures."""
        improvements = {}
        
        if quality_result and 'brutal_assessment' in quality_result:
            brutal_data = quality_result['brutal_assessment']
            category_scores = brutal_data.get('category_scores', {})
            
            # Identify weakest areas
            weakest_category = min(category_scores.items(), key=lambda x: x[1])
            
            if weakest_category[0] == 'prose_quality':
                improvements["focus_area"] = "prose_enhancement"
                improvements["specific_guidance"] = "Enhance language mastery, narrative flow, and theme integration"
            
            elif weakest_category[0] == 'character_development':
                improvements["focus_area"] = "character_development"
                improvements["specific_guidance"] = "Strengthen character voices, development arcs, and relationships"
            
            elif weakest_category[0] == 'structural_integrity':
                improvements["focus_area"] = "structure_improvement"
                improvements["specific_guidance"] = "Improve plot advancement, pacing, and chapter structure"
            
            # Add quality threshold pressure
            improvements["quality_pressure"] = "elevated"
            improvements["minimum_acceptable_score"] = quality_result.get('overall_score', 0) + self.quality_improvement_threshold
        
        return improvements
    
    def _improve_repetition_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Improve context to avoid repetition."""
        return {
            "repetition_avoidance": "strict",
            "vocabulary_variation": "required",
            "sentence_structure_diversity": "emphasized",
            "description_freshness": "mandatory",
            "avoid_previous_patterns": True
        }
    
    def _improve_consistency_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Improve context for consistency issues."""
        return {
            "consistency_check": "strict",
            "character_voice_maintenance": "required",
            "timeline_verification": "enabled",
            "fact_checking": "enhanced",
            "continuity_emphasis": "high"
        }
    
    def _improve_word_count_context(self, context: Dict[str, Any], 
                                  quality_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Improve context for word count issues."""
        improvements = {}
        
        if quality_result:
            current_word_count = quality_result.get('word_count', 0)
            target_words = context.get('target_words', 3800)
            
            if current_word_count < target_words * 0.8:
                improvements["length_guidance"] = "expand_content"
                improvements["expansion_focus"] = "dialogue, description, and character development"
            elif current_word_count > target_words * 1.2:
                improvements["length_guidance"] = "condense_content"
                improvements["condensation_focus"] = "concise language while maintaining quality"
            
            improvements["target_word_count"] = target_words
            improvements["word_count_priority"] = "high"
        
        return improvements
    
    def _improve_general_quality_context(self, context: Dict[str, Any],
                                       quality_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Improve context for general quality issues."""
        return {
            "quality_enhancement": "comprehensive",
            "writing_standards": "elevated",
            "craft_focus": "excellence",
            "reader_engagement": "prioritized",
            "professional_polish": "required"
        }
    
    def should_retry(self, chapter_number: int, failure_type: FailureType, 
                    attempt_number: int) -> bool:
        """Determine if a retry should be attempted."""
        
        # Never retry critical failures
        if failure_type == FailureType.CRITICAL_FAILURE:
            return False
        
        # Check maximum retry limit
        if attempt_number >= self.max_retries:
            return False
        
        # Check for specific failure types that shouldn't be retried
        if failure_type == FailureType.CONTENT_POLICY_VIOLATION and attempt_number >= 2:
            return False
        
        # Learn from past successes
        if chapter_number in self.retry_history:
            history = self.retry_history[chapter_number]
            if history.final_outcome == "failed" and len(history.attempts) >= self.max_retries:
                return False
        
        return True
    
    def record_retry_attempt(self, chapter_number: int, attempt: RetryAttempt):
        """Record a retry attempt in the history."""
        
        if chapter_number not in self.retry_history:
            self.retry_history[chapter_number] = RetryHistory(
                chapter_number=chapter_number,
                original_failure="",
                attempts=[],
                total_attempts=0,
                successful_attempt=None,
                final_outcome="in_progress",
                total_time_seconds=0.0,
                context_evolution=[]
            )
        
        history = self.retry_history[chapter_number]
        history.attempts.append(attempt)
        history.total_attempts += 1
        
        if attempt.success:
            history.successful_attempt = attempt.attempt_number
            history.final_outcome = "success"
        
        # Update learning data
        self._update_learning_data(attempt)
        
        # Save updated history
        self._save_retry_history()
        self._save_retry_patterns()
    
    def _update_learning_data(self, attempt: RetryAttempt):
        """Update learning data based on retry attempt results."""
        learning_data = self.retry_patterns["learning_data"]
        
        learning_data["total_retries"] += 1
        
        if attempt.success:
            learning_data["successful_retries"] += 1
            
            # Update success rates for this failure type and strategy
            key = f"{attempt.failure_type.value}_{attempt.strategy_used.value}"
            if key not in learning_data["pattern_effectiveness"]:
                learning_data["pattern_effectiveness"][key] = {"successes": 0, "attempts": 0}
            
            learning_data["pattern_effectiveness"][key]["successes"] += 1
        
        # Update attempt count for this pattern
        key = f"{attempt.failure_type.value}_{attempt.strategy_used.value}"
        if key in learning_data["pattern_effectiveness"]:
            learning_data["pattern_effectiveness"][key]["attempts"] += 1
    
    def get_retry_statistics(self) -> Dict[str, Any]:
        """Get comprehensive retry statistics."""
        
        total_retries = 0
        successful_retries = 0
        failure_type_counts = {}
        strategy_effectiveness = {}
        
        for history in self.retry_history.values():
            total_retries += history.total_attempts
            
            if history.final_outcome == "success":
                successful_retries += 1
            
            for attempt in history.attempts:
                failure_type = attempt.failure_type.value
                strategy = attempt.strategy_used.value
                
                failure_type_counts[failure_type] = failure_type_counts.get(failure_type, 0) + 1
                
                strategy_key = f"{failure_type}_{strategy}"
                if strategy_key not in strategy_effectiveness:
                    strategy_effectiveness[strategy_key] = {"attempts": 0, "successes": 0}
                
                strategy_effectiveness[strategy_key]["attempts"] += 1
                if attempt.success:
                    strategy_effectiveness[strategy_key]["successes"] += 1
        
        # Calculate success rates
        for key, data in strategy_effectiveness.items():
            data["success_rate"] = data["successes"] / data["attempts"] if data["attempts"] > 0 else 0
        
        overall_success_rate = successful_retries / len(self.retry_history) if self.retry_history else 0
        
        return {
            "overall_stats": {
                "total_chapters_with_retries": len(self.retry_history),
                "total_retry_attempts": total_retries,
                "successful_recoveries": successful_retries,
                "overall_success_rate": overall_success_rate
            },
            "failure_type_distribution": failure_type_counts,
            "strategy_effectiveness": strategy_effectiveness,
            "learning_insights": self._generate_learning_insights(strategy_effectiveness)
        }
    
    def _generate_learning_insights(self, strategy_effectiveness: Dict[str, Any]) -> List[str]:
        """Generate insights from retry patterns."""
        insights = []
        
        # Find most effective strategies
        best_strategies = sorted(
            strategy_effectiveness.items(),
            key=lambda x: x[1]["success_rate"],
            reverse=True
        )[:3]
        
        if best_strategies:
            insights.append(f"Most effective retry strategy: {best_strategies[0][0]} with {best_strategies[0][1]['success_rate']:.1%} success rate")
        
        # Find problematic failure types
        failure_rates = {}
        for key, data in strategy_effectiveness.items():
            failure_type = key.split('_')[0]
            if failure_type not in failure_rates:
                failure_rates[failure_type] = {"attempts": 0, "successes": 0}
            failure_rates[failure_type]["attempts"] += data["attempts"]
            failure_rates[failure_type]["successes"] += data["successes"]
        
        for failure_type, data in failure_rates.items():
            success_rate = data["successes"] / data["attempts"] if data["attempts"] > 0 else 0
            if success_rate < 0.5 and data["attempts"] >= 3:
                insights.append(f"Low success rate for {failure_type}: {success_rate:.1%}")
        
        return insights
    
    def recommend_improvements(self, chapter_number: int) -> List[str]:
        """Recommend improvements based on retry history."""
        recommendations = []
        
        if chapter_number in self.retry_history:
            history = self.retry_history[chapter_number]
            
            # Analyze common failure patterns
            failure_types = [attempt.failure_type for attempt in history.attempts]
            most_common_failure = max(set(failure_types), key=failure_types.count) if failure_types else None
            
            if most_common_failure:
                recommendations.append(f"Primary issue: {most_common_failure.value}")
                
                # Specific recommendations based on failure type
                if most_common_failure == FailureType.QUALITY_GATE_FAILURE:
                    recommendations.append("Consider strengthening the chapter outline before generation")
                    recommendations.append("Review quality gate thresholds for appropriateness")
                
                elif most_common_failure == FailureType.REPETITION_DETECTED:
                    recommendations.append("Implement stronger pattern avoidance in context")
                    recommendations.append("Consider expanding vocabulary guidelines")
                
                elif most_common_failure == FailureType.CONSISTENCY_ERROR:
                    recommendations.append("Enhance character and plot continuity checks")
                    recommendations.append("Review previous chapters for consistency requirements")
        
        return recommendations


# CLI Interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Intelligent Retry System")
    parser.add_argument("action", choices=["stats", "analyze", "recommend", "test"], 
                       help="Action to perform")
    parser.add_argument("--project-path", default=".", help="Path to project directory")
    parser.add_argument("--chapter", type=int, help="Chapter number for analysis")
    parser.add_argument("--error-message", help="Error message to analyze")
    
    args = parser.parse_args()
    
    retry_system = IntelligentRetrySystem(args.project_path)
    
    if args.action == "stats":
        stats = retry_system.get_retry_statistics()
        print("📊 Retry System Statistics:")
        print(f"  Total chapters with retries: {stats['overall_stats']['total_chapters_with_retries']}")
        print(f"  Total retry attempts: {stats['overall_stats']['total_retry_attempts']}")
        print(f"  Successful recoveries: {stats['overall_stats']['successful_recoveries']}")
        print(f"  Overall success rate: {stats['overall_stats']['overall_success_rate']:.1%}")
        
        if stats['learning_insights']:
            print("\n🧠 Learning Insights:")
            for insight in stats['learning_insights']:
                print(f"  • {insight}")
    
    elif args.action == "analyze" and args.error_message:
        failure_type = retry_system.analyze_failure(
            args.chapter or 1, 
            args.error_message
        )
        strategy = retry_system.determine_retry_strategy(failure_type, 1)
        delay = retry_system.calculate_retry_delay(strategy, 1, failure_type)
        
        print("🔍 Failure Analysis:")
        print(f"  Failure Type: {failure_type.value}")
        print(f"  Recommended Strategy: {strategy.value}")
        print(f"  Suggested Delay: {delay} seconds")
        print(f"  Should Retry: {'Yes' if retry_system.should_retry(args.chapter or 1, failure_type, 1) else 'No'}")
    
    elif args.action == "recommend" and args.chapter:
        recommendations = retry_system.recommend_improvements(args.chapter)
        print(f"💡 Recommendations for Chapter {args.chapter}:")
        if recommendations:
            for rec in recommendations:
                print(f"  • {rec}")
        else:
            print("  No specific recommendations available.")
    
    elif args.action == "test":
        # Test the failure analysis with common error messages
        test_errors = [
            "Quality gate failure: Overall score 75.2 below threshold 80.0",
            "Generation timeout after 300 seconds",
            "API rate limit exceeded",
            "Context too long for model",
            "Content policy violation detected",
            "Word count 2100 is 45% below target 3800",
            "Repetition detected in descriptions",
            "Character consistency error with previous chapters"
        ]
        
        print("🧪 Testing Failure Analysis:")
        for i, error in enumerate(test_errors, 1):
            failure_type = retry_system.analyze_failure(i, error)
            strategy = retry_system.determine_retry_strategy(failure_type, 1)
            print(f"  {i}. {error}")
            print(f"     → {failure_type.value} → {strategy.value}")
    
    else:
        print("Please provide required arguments for the specified action")
        parser.print_help() 