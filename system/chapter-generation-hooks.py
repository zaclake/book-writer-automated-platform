#!/usr/bin/env python3
"""
Chapter Generation Integration Hooks
Automated pattern database integration for chapter generation protocol.
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

# Import our pattern database engine
sys.path.append(str(Path(__file__).parent))

# Import with proper filename (has hyphens, not underscores)
import importlib.util
spec = importlib.util.spec_from_file_location(
    "pattern_database_engine", 
    Path(__file__).parent / "pattern-database-engine.py"
)
pattern_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pattern_module)
PatternDatabaseEngine = pattern_module.PatternDatabase

class ChapterGenerationHooks:
    """Integration hooks for pattern database in chapter generation workflow."""
    
    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.pattern_engine = PatternDatabaseEngine(project_path)
        self.hooks_log_path = self.project_path / ".project-state" / "generation-hooks.log"
        
        # Ensure log directory exists
        self.hooks_log_path.parent.mkdir(exist_ok=True)
    
    def log_hook_action(self, action: str, details: str = ""):
        """Log hook actions for debugging and verification."""
        timestamp = datetime.now().isoformat()
        log_entry = f"{timestamp} - {action}"
        if details:
            log_entry += f": {details}"
        
        with open(self.hooks_log_path, 'a', encoding='utf-8') as f:
            f.write(log_entry + "\n")
    
    def phase1_pattern_database_load(self) -> Dict[str, Any]:
        """Phase 1, Step 16: Load pattern database for context."""
        
        try:
            # Load current pattern database
            patterns = self.pattern_engine.get_pattern_summary()
            
            # Log the loading action
            self.log_hook_action(
                "phase1_pattern_load", 
                f"Loaded {patterns['total_patterns']} patterns, freshness: {patterns['freshness_score']:.1f}"
            )
            
            return {
                'status': 'success',
                'patterns_loaded': patterns['total_patterns'],
                'freshness_score': patterns['freshness_score'],
                'repetition_warnings': patterns.get('repetition_warnings', 0),
                'most_used_patterns': patterns.get('most_used_patterns', [])[:10],
                'recommendations': self._generate_pattern_recommendations(patterns)
            }
            
        except Exception as e:
            self.log_hook_action("phase1_pattern_load_error", str(e))
            return {
                'status': 'error',
                'error': str(e),
                'fallback_action': 'Continue with basic pattern awareness'
            }
    
    def stage5_pattern_database_update(self, chapter_text: str, chapter_number: int) -> Dict[str, Any]:
        """Stage 5: Update pattern database with new chapter content."""
        
        try:
            # Analyze and add patterns from the new chapter
            analysis = self.pattern_engine.analyze_chapter(chapter_text, chapter_number)
            
            # Log the update action
            self.log_hook_action(
                "stage5_pattern_update", 
                f"Chapter {chapter_number}: Added {analysis['new_patterns_added']} patterns, "
                f"freshness score now {analysis['updated_freshness_score']:.1f}"
            )
            
            return {
                'status': 'success',
                'chapter_number': chapter_number,
                'new_patterns_added': analysis['new_patterns_added'],
                'updated_freshness_score': analysis['updated_freshness_score'],
                'repetition_warnings': analysis.get('repetition_warnings', []),
                'pattern_categories': analysis.get('pattern_categories', {}),
                'recommendations': analysis.get('recommendations', [])
            }
            
        except Exception as e:
            self.log_hook_action("stage5_pattern_update_error", str(e))
            return {
                'status': 'error',
                'error': str(e),
                'fallback_action': 'Manual pattern review recommended'
            }
    
    def stage3_pattern_freshness_check(self, chapter_text: str, chapter_number: int) -> Dict[str, Any]:
        """Stage 3F: Check pattern freshness during craft excellence review."""
        
        try:
            # Get freshness analysis for current chapter
            freshness_analysis = self.pattern_engine.check_chapter_freshness(chapter_text, chapter_number)
            
            # Determine if freshness meets 7+ requirement
            freshness_score = freshness_analysis.get('freshness_score', 0)
            passes_requirement = freshness_score >= 7.0
            
            self.log_hook_action(
                "stage3_freshness_check", 
                f"Chapter {chapter_number}: Freshness score {freshness_score:.1f}/10, "
                f"{'PASS' if passes_requirement else 'FAIL'}"
            )
            
            return {
                'status': 'success',
                'chapter_number': chapter_number,
                'freshness_score': freshness_score,
                'passes_requirement': passes_requirement,
                'requirement_threshold': 7.0,
                'repetitive_patterns': freshness_analysis.get('repetitive_patterns', []),
                'overused_elements': freshness_analysis.get('overused_elements', []),
                'recommendations': freshness_analysis.get('recommendations', []),
                'requires_refinement': not passes_requirement
            }
            
        except Exception as e:
            self.log_hook_action("stage3_freshness_check_error", str(e))
            return {
                'status': 'error',
                'error': str(e),
                'fallback_action': 'Manual freshness review required'
            }
    
    def stage4_pattern_freshness_refinement(self, chapter_text: str, chapter_number: int) -> Dict[str, Any]:
        """Stage 4: Refine patterns if freshness < 7."""
        
        try:
            # Get specific suggestions for improving freshness
            refinement_suggestions = self.pattern_engine.get_freshness_refinement_suggestions(
                chapter_text, chapter_number
            )
            
            self.log_hook_action(
                "stage4_pattern_refinement", 
                f"Chapter {chapter_number}: Generated {len(refinement_suggestions.get('suggestions', []))} refinement suggestions"
            )
            
            return {
                'status': 'success',
                'chapter_number': chapter_number,
                'current_freshness': refinement_suggestions.get('current_freshness', 0),
                'target_freshness': 7.0,
                'specific_suggestions': refinement_suggestions.get('suggestions', []),
                'problematic_patterns': refinement_suggestions.get('problematic_patterns', []),
                'alternative_approaches': refinement_suggestions.get('alternatives', []),
                'voice_preservation_notes': refinement_suggestions.get('voice_notes', [])
            }
            
        except Exception as e:
            self.log_hook_action("stage4_pattern_refinement_error", str(e))
            return {
                'status': 'error',
                'error': str(e),
                'fallback_action': 'Manual pattern refinement required'
            }
    
    def _generate_pattern_recommendations(self, patterns: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on current pattern state."""
        
        recommendations = []
        
        freshness_score = patterns.get('freshness_score', 0)
        if freshness_score < 7.0:
            recommendations.append(f"⚠️ Pattern freshness low ({freshness_score:.1f}/10) - focus on description variety")
        
        repetition_warnings = patterns.get('repetition_warnings', 0)
        if repetition_warnings > 3:
            recommendations.append(f"🔄 {repetition_warnings} repetition warnings - review overused patterns")
        
        total_patterns = patterns.get('total_patterns', 0)
        if total_patterns > 500:
            recommendations.append("📊 Large pattern database - excellent variety foundation")
        elif total_patterns < 50:
            recommendations.append("📝 Building pattern database - focus on diverse descriptions")
        
        most_used = patterns.get('most_used_patterns', [])
        if most_used:
            top_pattern = most_used[0] if isinstance(most_used[0], dict) else {'pattern': str(most_used[0]), 'count': 'unknown'}
            if isinstance(top_pattern, dict) and top_pattern.get('count', 0) > 5:
                recommendations.append(f"🎯 Most used pattern: '{top_pattern.get('pattern', 'N/A')}' - consider alternatives")
        
        return recommendations
    
    def get_integration_status(self) -> Dict[str, Any]:
        """Get current integration status and health."""
        
        try:
            # Check pattern database health
            pattern_status = self.pattern_engine.get_pattern_summary()
            
            # Check recent hook activity
            recent_logs = []
            if self.hooks_log_path.exists():
                with open(self.hooks_log_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    recent_logs = lines[-10:]  # Last 10 log entries
            
            return {
                'status': 'operational',
                'pattern_database_health': {
                    'total_patterns': pattern_status['total_patterns'],
                    'freshness_score': pattern_status['freshness_score'],
                    'last_updated': pattern_status.get('last_updated', 'never')
                },
                'recent_activity': len(recent_logs),
                'hooks_available': [
                    'phase1_pattern_database_load',
                    'stage3_pattern_freshness_check', 
                    'stage4_pattern_freshness_refinement',
                    'stage5_pattern_database_update'
                ],
                'integration_complete': True
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'integration_complete': False
            }
    
    def run_integration_test(self) -> Dict[str, Any]:
        """Test all integration hooks with sample data."""
        
        test_results = {}
        sample_chapter = """
        The detective walked into the dimly lit room. The shadows danced across the walls
        like ghostly figures from another realm. His weathered hands trembled slightly as
        he examined the evidence scattered across the desk.
        
        "This case," he muttered, "is more complex than I initially thought."
        
        The morning sun slanted through the venetian blinds, casting precise geometric 
        patterns on the hardwood floor. Each stripe of light revealed another clue,
        another piece of the puzzle that had been tormenting him for weeks.
        """
        
        # Test Phase 1 loading
        try:
            phase1_result = self.phase1_pattern_database_load()
            test_results['phase1_load'] = {
                'status': phase1_result['status'],
                'success': phase1_result['status'] == 'success'
            }
        except Exception as e:
            test_results['phase1_load'] = {'status': 'error', 'error': str(e), 'success': False}
        
        # Test Stage 3 freshness check
        try:
            stage3_result = self.stage3_pattern_freshness_check(sample_chapter, 999)
            test_results['stage3_freshness'] = {
                'status': stage3_result['status'],
                'freshness_score': stage3_result.get('freshness_score', 0),
                'success': stage3_result['status'] == 'success'
            }
        except Exception as e:
            test_results['stage3_freshness'] = {'status': 'error', 'error': str(e), 'success': False}
        
        # Test Stage 4 refinement
        try:
            stage4_result = self.stage4_pattern_freshness_refinement(sample_chapter, 999)
            test_results['stage4_refinement'] = {
                'status': stage4_result['status'],
                'suggestions_count': len(stage4_result.get('specific_suggestions', [])),
                'success': stage4_result['status'] == 'success'
            }
        except Exception as e:
            test_results['stage4_refinement'] = {'status': 'error', 'error': str(e), 'success': False}
        
        # Test Stage 5 update
        try:
            stage5_result = self.stage5_pattern_database_update(sample_chapter, 999)
            test_results['stage5_update'] = {
                'status': stage5_result['status'],
                'patterns_added': stage5_result.get('new_patterns_added', 0),
                'success': stage5_result['status'] == 'success'
            }
        except Exception as e:
            test_results['stage5_update'] = {'status': 'error', 'error': str(e), 'success': False}
        
        # Overall test status
        all_success = all(result.get('success', False) for result in test_results.values())
        
        return {
            'overall_status': 'success' if all_success else 'partial_failure',
            'tests_passed': sum(1 for result in test_results.values() if result.get('success', False)),
            'total_tests': len(test_results),
            'detailed_results': test_results,
            'integration_ready': all_success
        }

# CLI Interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Chapter Generation Pattern Database Hooks")
    parser.add_argument("action", choices=["test", "status", "phase1", "stage3", "stage4", "stage5"], 
                       help="Action to perform")
    parser.add_argument("--chapter-file", help="Chapter file for analysis")
    parser.add_argument("--chapter-number", type=int, help="Chapter number")
    parser.add_argument("--text", help="Chapter text for direct analysis")
    
    args = parser.parse_args()
    
    hooks = ChapterGenerationHooks()
    
    if args.action == "test":
        results = hooks.run_integration_test()
        print(f"Integration Test Results:")
        print(f"Status: {results['overall_status']}")
        print(f"Tests Passed: {results['tests_passed']}/{results['total_tests']}")
        print(f"Integration Ready: {results['integration_ready']}")
        
        for test_name, result in results['detailed_results'].items():
            status = "✅" if result['success'] else "❌"
            print(f"  {status} {test_name}: {result['status']}")
    
    elif args.action == "status":
        status = hooks.get_integration_status()
        print("Pattern Database Integration Status:")
        print(f"Status: {status['status']}")
        print(f"Integration Complete: {status['integration_complete']}")
        if 'pattern_database_health' in status:
            health = status['pattern_database_health']
            print(f"Pattern Database:")
            print(f"  Total Patterns: {health['total_patterns']}")
            print(f"  Freshness Score: {health['freshness_score']:.1f}/10")
            print(f"  Last Updated: {health['last_updated']}")
        print(f"Recent Activity: {status.get('recent_activity', 0)} log entries")
    
    elif args.action == "phase1":
        result = hooks.phase1_pattern_database_load()
        print("Phase 1 Pattern Database Load:")
        print(json.dumps(result, indent=2))
    
    elif args.action == "stage3" and (args.chapter_file or args.text) and args.chapter_number:
        if args.chapter_file:
            with open(args.chapter_file, 'r', encoding='utf-8') as f:
                chapter_text = f.read()
        else:
            chapter_text = args.text
        
        result = hooks.stage3_pattern_freshness_check(chapter_text, args.chapter_number)
        print(f"Stage 3 Pattern Freshness Check - Chapter {args.chapter_number}:")
        print(json.dumps(result, indent=2))
    
    elif args.action == "stage4" and (args.chapter_file or args.text) and args.chapter_number:
        if args.chapter_file:
            with open(args.chapter_file, 'r', encoding='utf-8') as f:
                chapter_text = f.read()
        else:
            chapter_text = args.text
        
        result = hooks.stage4_pattern_freshness_refinement(chapter_text, args.chapter_number)
        print(f"Stage 4 Pattern Refinement - Chapter {args.chapter_number}:")
        print(json.dumps(result, indent=2))
    
    elif args.action == "stage5" and (args.chapter_file or args.text) and args.chapter_number:
        if args.chapter_file:
            with open(args.chapter_file, 'r', encoding='utf-8') as f:
                chapter_text = f.read()
        else:
            chapter_text = args.text
        
        result = hooks.stage5_pattern_database_update(chapter_text, args.chapter_number)
        print(f"Stage 5 Pattern Database Update - Chapter {args.chapter_number}:")
        print(json.dumps(result, indent=2))
    
    else:
        print("Please provide required arguments for the specified action")
        parser.print_help() 