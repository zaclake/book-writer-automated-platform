#!/usr/bin/env python3
"""
Project Initialization Script
Sets up .project-state directory with all required tracking files.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

class ProjectInitializer:
    """Handles project state directory initialization and file creation."""
    
    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.state_dir = self.project_path / ".project-state"
        
    def initialize_project_state(self) -> bool:
        """Initialize complete .project-state directory with all required files."""
        try:
            # Create state directory
            self.state_dir.mkdir(exist_ok=True)
            
            # Initialize all required state files
            self._create_pattern_database()
            self._create_quality_baselines()
            self._create_chapter_progress()
            self._create_session_history()
            self._create_book_completion_state()
            
            print("✅ Project state directory initialized successfully")
            print(f"📁 Created: {self.state_dir}")
            print("📄 Files created:")
            print("   - pattern-database.json")
            print("   - quality-baselines.json") 
            print("   - chapter-progress.json")
            print("   - session-history.json")
            print("   - book-completion-state.json")
            
            return True
            
        except Exception as e:
            print(f"❌ Error initializing project state: {e}")
            return False
    
    def _create_pattern_database(self):
        """Create initial pattern database file."""
        pattern_db = {
            "metadata": {
                "created": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "chapter_count": 0,
                "total_patterns": 0
            },
            "physical_descriptions": {
                "characters": {},
                "settings": {},
                "objects": {},
                "sensory": {
                    "visual": [],
                    "auditory": [],
                    "tactile": [],
                    "olfactory": [],
                    "gustatory": []
                }
            },
            "language_patterns": {
                "metaphors": [],
                "similes": [],
                "adjective_combinations": [],
                "sentence_structures": [],
                "paragraph_structures": [],
                "dialogue_tags": [],
                "transitions": []
            },
            "emotional_expressions": {
                "character_reactions": {},
                "internal_monologue": {},
                "conflict_expressions": [],
                "resolution_techniques": []
            },
            "action_sequences": {
                "movement_descriptions": [],
                "pacing_patterns": [],
                "choreography": [],
                "tension_building": []
            },
            "chapter_summaries": {},
            "repetition_flags": []
        }
        
        with open(self.state_dir / "pattern-database.json", 'w', encoding='utf-8') as f:
            json.dump(pattern_db, f, indent=2, ensure_ascii=False)
    
    def _create_quality_baselines(self):
        """Create quality baselines and character voice tracking file."""
        quality_baselines = {
            "metadata": {
                "created": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "project_quality_target": 8.5,
                "chapter_count": 0
            },
            "quality_thresholds": {
                "prose_quality": {"minimum": 8.0, "target": 8.5},
                "character_authenticity": {"minimum": 8.0, "target": 8.5},
                "story_function": {"minimum": 8.0, "target": 8.5},
                "emotional_impact": {"minimum": 8.0, "target": 8.5},
                "pattern_freshness": {"minimum": 7.0, "target": 8.0},
                "reader_engagement": {"minimum": 7.0, "target": 8.0},
                "structural_integrity": {"minimum": 8.0, "target": 8.5},
                "brutal_assessment": {"minimum": 8.5, "target": 9.0}
            },
            "character_voice_baselines": {},
            "style_consistency_metrics": {
                "sentence_length_variance": {"min": 5, "max": 50, "avg_target": 18},
                "paragraph_length_variance": {"min": 1, "max": 8, "avg_target": 4},
                "dialogue_to_narrative_ratio": {"min": 0.3, "max": 0.7, "target": 0.4},
                "description_density": {"min": 0.15, "max": 0.35, "target": 0.25}
            },
            "chapter_quality_history": {},
            "quality_improvement_trends": {},
            "baseline_calibration": {
                "last_calibrated": datetime.now().isoformat(),
                "calibration_source": "Enhanced Writing System v2.0",
                "brutal_assessment_correlation": 0.95
            }
        }
        
        with open(self.state_dir / "quality-baselines.json", 'w', encoding='utf-8') as f:
            json.dump(quality_baselines, f, indent=2, ensure_ascii=False)
    
    def _create_chapter_progress(self):
        """Create chapter completion and milestone tracking file."""
        chapter_progress = {
            "metadata": {
                "created": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "total_chapters_planned": 0,
                "chapters_completed": 0,
                "current_word_count": 0,
                "target_word_count": 0,
                "auto_completion_enabled": False,
                "book_completion_job_id": None
            },
            "chapter_status": {},
            "milestone_tracking": {
                "plot_points": {},
                "character_arcs": {},
                "theme_development": {},
                "world_building": {},
                "research_requirements": {}
            },
            "word_count_progression": {},
            "quality_gate_results": {},
            "revision_history": {},
            "completion_dates": {},
            "writing_velocity": {
                "words_per_session": [],
                "chapters_per_week": [],
                "quality_scores_over_time": []
            },
            "next_actions": [],
            "blocked_items": [],
            "auto_completion_integration": {
                "last_auto_completed_chapter": 0,
                "auto_completion_failures": [],
                "manual_interventions": [],
                "quality_gate_overrides": []
            }
        }
        
        with open(self.state_dir / "chapter-progress.json", 'w', encoding='utf-8') as f:
            json.dump(chapter_progress, f, indent=2, ensure_ascii=False)
    
    def _create_session_history(self):
        """Create session history and project metadata file."""
        session_history = {
            "metadata": {
                "created": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "total_sessions": 0,
                "total_writing_time": 0
            },
            "sessions": [],
            "project_stats": {
                "most_productive_session": None,
                "average_session_length": 0,
                "average_words_per_session": 0,
                "quality_trend": "stable",
                "last_backup": None
            },
            "system_usage": {
                "patterns_detected": 0,
                "quality_checks_run": 0,
                "brutal_assessments": 0,
                "continuous_audits": 0,
                "research_verifications": 0
            },
            "project_health": {
                "pattern_freshness_score": 10.0,
                "quality_consistency": 10.0,
                "plot_advancement_rate": 0.0,
                "character_development_rate": 0.0,
                "overall_health_score": 10.0
            }
        }
        
        with open(self.state_dir / "session-history.json", 'w', encoding='utf-8') as f:
            json.dump(session_history, f, indent=2, ensure_ascii=False)
    
    def _create_book_completion_state(self):
        """Create book-level auto-completion state tracking file."""
        book_completion_state = {
            "metadata": {
                "created": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "schema_version": "1.0",
                "auto_completion_enabled": True
            },
            "book_completion_job": {
                "job_id": None,
                "status": "not_started",
                "start_time": None,
                "estimated_completion_time": None,
                "pause_time": None,
                "resume_time": None,
                "completion_time": None,
                "current_chapter": 0,
                "total_chapters_planned": 0,
                "chapters_completed": 0,
                "user_initiated": False,
                "auto_pause_on_failure": True,
                "max_retry_attempts": 3,
                "context_improvement_enabled": True
            },
            "chapter_generation_queue": {
                "pending_chapters": [],
                "current_chapter": None,
                "completed_chapters": [],
                "failed_chapters": [],
                "skipped_chapters": []
            },
            "quality_gate_configuration": {
                "enabled": True,
                "minimum_pass_score": 80,
                "brutal_assessment_threshold": 75,
                "engagement_score_threshold": 7.0,
                "word_count_tolerance": 0.15,
                "auto_retry_on_failure": True,
                "max_retries_per_chapter": 3,
                "quality_improvement_iterations": 2
            },
            "sequential_chapter_tracking": {
                "chapter_dependencies": {},
                "context_continuity": {
                    "character_states": {},
                    "plot_threads": {},
                    "world_state": {},
                    "timeline_position": {}
                },
                "chapter_flow": [],
                "completion_triggers": {
                    "word_count_target_reached": False,
                    "plot_resolution_achieved": False,
                    "character_arcs_completed": False,
                    "manual_completion_requested": False
                }
            },
            "progress_tracking": {
                "overall_completion_percentage": 0.0,
                "current_phase": "not_started",
                "chapters_progress": {},
                "word_count_progression": {},
                "quality_scores_progression": {},
                "estimated_time_remaining": None,
                "velocity_metrics": {
                    "avg_chapter_generation_time": None,
                    "avg_quality_assessment_time": None,
                    "avg_retry_time": None,
                    "success_rate": 1.0
                }
            },
            "failure_recovery": {
                "recovery_enabled": True,
                "checkpoint_frequency": "after_each_chapter",
                "last_successful_checkpoint": None,
                "recovery_attempts": [],
                "context_restoration_points": {},
                "rollback_capability": True
            },
            "user_control": {
                "pause_requested": False,
                "resume_requested": False,
                "stop_requested": False,
                "manual_intervention_required": False,
                "user_review_required": False,
                "notification_preferences": {
                    "chapter_completion": True,
                    "quality_failures": True,
                    "book_completion": True,
                    "error_alerts": True
                }
            },
            "context_management": {
                "previous_chapters_summary": "",
                "character_development_continuity": {},
                "plot_advancement_tracking": {},
                "theme_consistency": {},
                "world_building_continuity": {},
                "research_integration": {}
            },
            "completion_criteria": {
                "target_word_count": 80000,
                "minimum_word_count": 70000,
                "maximum_word_count": 90000,
                "target_chapter_count": 20,
                "minimum_chapter_count": 18,
                "maximum_chapter_count": 25,
                "plot_resolution_required": True,
                "character_arc_completion_required": True,
                "quality_threshold_maintained": True
            },
            "auto_completion_log": {
                "session_logs": [],
                "chapter_generation_logs": [],
                "quality_assessment_logs": [],
                "error_logs": [],
                "context_management_logs": []
            }
        }
        
        with open(self.state_dir / "book-completion-state.json", 'w', encoding='utf-8') as f:
            json.dump(book_completion_state, f, indent=2, ensure_ascii=False)
    
    def verify_state_integrity(self) -> Dict[str, bool]:
        """Verify all state files exist and are valid JSON."""
        required_files = [
            "pattern-database.json",
            "quality-baselines.json", 
            "chapter-progress.json",
            "session-history.json",
            "book-completion-state.json"
        ]
        
        results = {}
        
        for filename in required_files:
            file_path = self.state_dir / filename
            try:
                if file_path.exists():
                    with open(file_path, 'r', encoding='utf-8') as f:
                        json.load(f)  # Verify valid JSON
                    results[filename] = True
                else:
                    results[filename] = False
            except (json.JSONDecodeError, IOError):
                results[filename] = False
        
        return results
    
    def repair_state_files(self) -> bool:
        """Repair or recreate missing/corrupted state files."""
        verification = self.verify_state_integrity()
        repaired = []
        
        for filename, is_valid in verification.items():
            if not is_valid:
                if filename == "pattern-database.json":
                    self._create_pattern_database()
                elif filename == "quality-baselines.json":
                    self._create_quality_baselines()
                elif filename == "chapter-progress.json":
                    self._create_chapter_progress()
                elif filename == "session-history.json":
                    self._create_session_history()
                elif filename == "book-completion-state.json":
                    self._create_book_completion_state()
                
                repaired.append(filename)
        
        if repaired:
            print(f"🔧 Repaired state files: {', '.join(repaired)}")
            return True
        else:
            print("✅ All state files are valid")
            return False
    
    def get_state_summary(self) -> Dict[str, Any]:
        """Get summary of current project state."""
        verification = self.verify_state_integrity()
        
        summary = {
            "state_directory_exists": self.state_dir.exists(),
            "files_status": verification,
            "all_files_valid": all(verification.values()),
            "missing_files": [f for f, valid in verification.items() if not valid],
            "last_check": datetime.now().isoformat()
        }
        
        # Try to load basic stats from files
        try:
            if verification.get("chapter-progress.json"):
                with open(self.state_dir / "chapter-progress.json", 'r') as f:
                    progress = json.load(f)
                    summary["chapters_completed"] = progress["metadata"]["chapters_completed"]
                    summary["current_word_count"] = progress["metadata"]["current_word_count"]
        except:
            pass
        
        try:
            if verification.get("pattern-database.json"):
                with open(self.state_dir / "pattern-database.json", 'r') as f:
                    patterns = json.load(f)
                    summary["patterns_tracked"] = patterns["metadata"]["total_patterns"]
                    summary["chapters_analyzed"] = patterns["metadata"]["chapter_count"]
        except:
            pass
        
        return summary

# CLI Interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Project State Initialization")
    parser.add_argument("action", choices=["init", "verify", "repair", "summary"], 
                       help="Action to perform")
    parser.add_argument("--project-path", default=".", 
                       help="Path to project directory")
    
    args = parser.parse_args()
    
    initializer = ProjectInitializer(args.project_path)
    
    if args.action == "init":
        success = initializer.initialize_project_state()
        exit(0 if success else 1)
    
    elif args.action == "verify":
        results = initializer.verify_state_integrity()
        print("State file verification:")
        for filename, is_valid in results.items():
            status = "✅ Valid" if is_valid else "❌ Missing/Invalid"
            print(f"  {filename}: {status}")
        
        all_valid = all(results.values())
        print(f"\nOverall status: {'✅ All files valid' if all_valid else '❌ Issues detected'}")
        exit(0 if all_valid else 1)
    
    elif args.action == "repair":
        initializer.repair_state_files()
        
        # Verify after repair
        results = initializer.verify_state_integrity()
        all_valid = all(results.values())
        exit(0 if all_valid else 1)
    
    elif args.action == "summary":
        summary = initializer.get_state_summary()
        print("Project State Summary:")
        print(f"  State directory: {'✅ Exists' if summary['state_directory_exists'] else '❌ Missing'}")
        print(f"  All files valid: {'✅ Yes' if summary['all_files_valid'] else '❌ No'}")
        
        if summary.get('missing_files'):
            print(f"  Missing files: {', '.join(summary['missing_files'])}")
        
        if 'chapters_completed' in summary:
            print(f"  Chapters completed: {summary['chapters_completed']}")
            print(f"  Current word count: {summary['current_word_count']:,}")
        
        if 'patterns_tracked' in summary:
            print(f"  Patterns tracked: {summary['patterns_tracked']}")
            print(f"  Chapters analyzed: {summary['chapters_analyzed']}") 