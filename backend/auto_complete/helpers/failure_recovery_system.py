#!/usr/bin/env python3
"""
Failure Recovery System
Comprehensive failure recovery with chapter rollback and context restoration.
"""

import json
import shutil
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, asdict
from enum import Enum
import hashlib
import gzip

class RecoveryAction(Enum):
    """Types of recovery actions."""
    ROLLBACK_CHAPTER = "rollback_chapter"
    ROLLBACK_MULTIPLE_CHAPTERS = "rollback_multiple_chapters"
    RESTORE_CONTEXT = "restore_context"
    RESTORE_STATE = "restore_state"
    REPAIR_CORRUPTION = "repair_corruption"
    EMERGENCY_RESET = "emergency_reset"

class FailureSeverity(Enum):
    """Severity levels for failures."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    CATASTROPHIC = "catastrophic"

@dataclass
class RecoveryPoint:
    """Represents a recovery point in the generation process."""
    timestamp: str
    chapter_number: int
    total_chapters: int
    total_word_count: int
    quality_scores: List[float]
    context_hash: str
    state_hash: str
    file_checksums: Dict[str, str]
    metadata: Dict[str, Any]

@dataclass
class FailureEvent:
    """Represents a failure event requiring recovery."""
    timestamp: str
    chapter_number: int
    failure_type: str
    error_message: str
    severity: FailureSeverity
    context_snapshot: Dict[str, Any]
    recovery_actions_taken: List[str]
    recovery_success: bool
    recovery_duration: Optional[float] = None

class FailureRecoverySystem:
    """
    Comprehensive failure recovery system with rollback capabilities.
    
    Features:
    - Automatic recovery point creation
    - Chapter rollback and context restoration
    - State integrity verification
    - Corruption detection and repair
    - Emergency recovery procedures
    """
    
    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.state_dir = self.project_path / ".project-state"
        self.chapters_dir = self.project_path / "chapters"
        self.recovery_dir = self.state_dir / "recovery"
        
        # Recovery tracking files
        self.recovery_points_file = self.recovery_dir / "recovery-points.json"
        self.failure_log_file = self.recovery_dir / "failure-log.json"
        self.recovery_log_file = self.recovery_dir / "recovery-log.json"
        
        # Create recovery directory
        self.recovery_dir.mkdir(exist_ok=True)
        
        # Load recovery data
        self.recovery_points: List[RecoveryPoint] = self._load_recovery_points()
        self.failure_log: List[FailureEvent] = self._load_failure_log()
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
    
    def _load_recovery_points(self) -> List[RecoveryPoint]:
        """Load recovery points from file."""
        if not self.recovery_points_file.exists():
            return []
        
        try:
            with open(self.recovery_points_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return [RecoveryPoint(**point) for point in data]
        except (json.JSONDecodeError, KeyError, ValueError):
            return []
    
    def _load_failure_log(self) -> List[FailureEvent]:
        """Load failure log from file."""
        if not self.failure_log_file.exists():
            return []
        
        try:
            with open(self.failure_log_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            events = []
            for event_data in data:
                event_data['severity'] = FailureSeverity(event_data['severity'])
                events.append(FailureEvent(**event_data))
            
            return events
        except (json.JSONDecodeError, KeyError, ValueError):
            return []
    
    def _save_recovery_points(self):
        """Save recovery points to file."""
        data = [asdict(point) for point in self.recovery_points]
        with open(self.recovery_points_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _save_failure_log(self):
        """Save failure log to file."""
        data = []
        for event in self.failure_log:
            event_data = asdict(event)
            event_data['severity'] = event.severity.value
            data.append(event_data)
        
        with open(self.failure_log_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def create_recovery_point(self, chapter_number: int, context_data: Dict[str, Any] = None) -> RecoveryPoint:
        """Create a recovery point for the current state."""
        try:
            # Calculate current metrics
            total_chapters = len(list(self.chapters_dir.glob("chapter-*.md")))
            total_word_count = self._calculate_total_word_count()
            quality_scores = self._get_quality_scores()
            
            # Create state snapshots
            context_hash = self._calculate_context_hash(context_data)
            state_hash = self._calculate_state_hash()
            file_checksums = self._calculate_file_checksums()
            
            # Create recovery point
            recovery_point = RecoveryPoint(
                timestamp=datetime.now().isoformat(),
                chapter_number=chapter_number,
                total_chapters=total_chapters,
                total_word_count=total_word_count,
                quality_scores=quality_scores,
                context_hash=context_hash,
                state_hash=state_hash,
                file_checksums=file_checksums,
                metadata={
                    "generation_method": "auto_complete",
                    "project_path": str(self.project_path),
                    "context_quality": self._assess_context_quality(context_data)
                }
            )
            
            # Save state backup
            self._create_state_backup(recovery_point)
            
            # Add to recovery points (keep last 20)
            self.recovery_points.append(recovery_point)
            if len(self.recovery_points) > 20:
                self._cleanup_old_recovery_points()
            
            self._save_recovery_points()
            
            self.logger.info(f"Recovery point created for chapter {chapter_number}")
            return recovery_point
            
        except Exception as e:
            self.logger.error(f"Failed to create recovery point: {e}")
            raise
    
    def _create_state_backup(self, recovery_point: RecoveryPoint):
        """Create a backup of the current state."""
        backup_dir = self.recovery_dir / f"backup-{recovery_point.timestamp.replace(':', '-')}"
        backup_dir.mkdir(exist_ok=True)
        
        # Backup chapters
        if self.chapters_dir.exists():
            chapters_backup = backup_dir / "chapters"
            shutil.copytree(self.chapters_dir, chapters_backup, dirs_exist_ok=True)
        
        # Backup state files
        state_backup = backup_dir / "state"
        state_backup.mkdir(exist_ok=True)
        
        for state_file in self.state_dir.glob("*.json"):
            if state_file.name != "recovery":
                shutil.copy2(state_file, state_backup)
    
    def analyze_failure(self, chapter_number: int, error_message: str, 
                       context_data: Dict[str, Any] = None) -> FailureEvent:
        """Analyze a failure and determine recovery strategy."""
        severity = self._assess_failure_severity(error_message, context_data)
        
        failure_event = FailureEvent(
            timestamp=datetime.now().isoformat(),
            chapter_number=chapter_number,
            failure_type=self._classify_failure_type(error_message),
            error_message=error_message,
            severity=severity,
            context_snapshot=context_data or {},
            recovery_actions_taken=[],
            recovery_success=False
        )
        
        self.failure_log.append(failure_event)
        self._save_failure_log()
        
        self.logger.warning(f"Failure analyzed: {failure_event.failure_type} (severity: {severity.value})")
        
        return failure_event
    
    def execute_recovery(self, failure_event: FailureEvent, recovery_actions: List[RecoveryAction]) -> bool:
        """Execute recovery actions for a failure."""
        recovery_start = datetime.now()
        success = True
        
        try:
            for action in recovery_actions:
                if action == RecoveryAction.ROLLBACK_CHAPTER:
                    success &= self._rollback_chapter(failure_event.chapter_number)
                elif action == RecoveryAction.ROLLBACK_MULTIPLE_CHAPTERS:
                    success &= self._rollback_multiple_chapters(failure_event.chapter_number)
                elif action == RecoveryAction.RESTORE_CONTEXT:
                    success &= self._restore_context(failure_event.chapter_number)
                elif action == RecoveryAction.RESTORE_STATE:
                    success &= self._restore_state(failure_event.chapter_number)
                elif action == RecoveryAction.REPAIR_CORRUPTION:
                    success &= self._repair_corruption()
                elif action == RecoveryAction.EMERGENCY_RESET:
                    success &= self._emergency_reset()
                
                failure_event.recovery_actions_taken.append(action.value)
            
            recovery_duration = (datetime.now() - recovery_start).total_seconds()
            failure_event.recovery_duration = recovery_duration
            failure_event.recovery_success = success
            
            self._save_failure_log()
            
            if success:
                self.logger.info(f"Recovery completed successfully in {recovery_duration:.2f}s")
            else:
                self.logger.error(f"Recovery failed after {recovery_duration:.2f}s")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Recovery execution failed: {e}")
            failure_event.recovery_success = False
            return False
    
    def _rollback_chapter(self, chapter_number: int) -> bool:
        """Rollback a specific chapter to the previous state."""
        try:
            # Find the most recent recovery point before this chapter
            recovery_point = self._find_recovery_point_before_chapter(chapter_number)
            if not recovery_point:
                self.logger.error(f"No recovery point found before chapter {chapter_number}")
                return False
            
            # Remove the failed chapter file
            chapter_file = self.chapters_dir / f"chapter-{chapter_number:02d}.md"
            if chapter_file.exists():
                chapter_file.unlink()
                self.logger.info(f"Removed failed chapter {chapter_number}")
            
            # Restore context to the recovery point
            self._restore_context_from_recovery_point(recovery_point)
            
            # Update state tracking
            self._update_state_after_rollback(recovery_point)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Chapter rollback failed: {e}")
            return False
    
    def _rollback_multiple_chapters(self, from_chapter: int, num_chapters: int = 2) -> bool:
        """Rollback multiple chapters due to cascading failures."""
        try:
            rollback_to_chapter = max(1, from_chapter - num_chapters)
            
            # Find recovery point
            recovery_point = self._find_recovery_point_before_chapter(rollback_to_chapter + 1)
            if not recovery_point:
                self.logger.error(f"No recovery point found for multi-chapter rollback")
                return False
            
            # Remove chapters from rollback point onwards
            for chapter_num in range(rollback_to_chapter + 1, from_chapter + 1):
                chapter_file = self.chapters_dir / f"chapter-{chapter_num:02d}.md"
                if chapter_file.exists():
                    chapter_file.unlink()
                    self.logger.info(f"Removed chapter {chapter_num} in multi-chapter rollback")
            
            # Restore state
            self._restore_state_from_recovery_point(recovery_point)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Multi-chapter rollback failed: {e}")
            return False
    
    def _restore_context(self, chapter_number: int) -> bool:
        """Restore context state for a specific chapter."""
        try:
            recovery_point = self._find_recovery_point_before_chapter(chapter_number)
            if not recovery_point:
                return False
            
            return self._restore_context_from_recovery_point(recovery_point)
            
        except Exception as e:
            self.logger.error(f"Context restoration failed: {e}")
            return False
    
    def _restore_state(self, chapter_number: int) -> bool:
        """Restore complete state to a previous recovery point."""
        try:
            recovery_point = self._find_recovery_point_before_chapter(chapter_number)
            if not recovery_point:
                return False
            
            return self._restore_state_from_recovery_point(recovery_point)
            
        except Exception as e:
            self.logger.error(f"State restoration failed: {e}")
            return False
    
    def _repair_corruption(self) -> bool:
        """Repair corrupted state files."""
        try:
            # Check for corrupted files
            corrupted_files = self._detect_corrupted_files()
            
            if not corrupted_files:
                return True
            
            # Find the most recent recovery point
            if not self.recovery_points:
                self.logger.error("No recovery points available for corruption repair")
                return False
            
            latest_recovery = self.recovery_points[-1]
            
            # Restore corrupted files from backup
            for file_path in corrupted_files:
                if self._restore_file_from_backup(file_path, latest_recovery):
                    self.logger.info(f"Repaired corrupted file: {file_path}")
                else:
                    self.logger.error(f"Failed to repair corrupted file: {file_path}")
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Corruption repair failed: {e}")
            return False
    
    def _emergency_reset(self) -> bool:
        """Emergency reset to the last known good state."""
        try:
            if not self.recovery_points:
                self.logger.error("No recovery points available for emergency reset")
                return False
            
            # Find the most stable recovery point (highest quality)
            best_recovery = max(self.recovery_points, 
                              key=lambda rp: rp.metadata.get('context_quality', 0))
            
            # Restore to this point
            return self._restore_state_from_recovery_point(best_recovery)
            
        except Exception as e:
            self.logger.error(f"Emergency reset failed: {e}")
            return False
    
    def _find_recovery_point_before_chapter(self, chapter_number: int) -> Optional[RecoveryPoint]:
        """Find the most recent recovery point before a specific chapter."""
        valid_points = [rp for rp in self.recovery_points if rp.chapter_number < chapter_number]
        
        if not valid_points:
            return None
        
        return max(valid_points, key=lambda rp: rp.chapter_number)
    
    def _restore_context_from_recovery_point(self, recovery_point: RecoveryPoint) -> bool:
        """Restore context from a recovery point."""
        try:
            backup_dir = self._find_backup_dir(recovery_point)
            if not backup_dir:
                return False
            
            # Restore context files
            context_files = [
                "chapter-contexts.json",
                "character-states.json",
                "plot-threads.json",
                "world-state.json"
            ]
            
            for file_name in context_files:
                source_file = backup_dir / "state" / file_name
                target_file = self.state_dir / file_name
                
                if source_file.exists():
                    shutil.copy2(source_file, target_file)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Context restoration failed: {e}")
            return False
    
    def _restore_state_from_recovery_point(self, recovery_point: RecoveryPoint) -> bool:
        """Restore complete state from a recovery point."""
        try:
            backup_dir = self._find_backup_dir(recovery_point)
            if not backup_dir:
                return False
            
            # Restore chapters
            chapters_backup = backup_dir / "chapters"
            if chapters_backup.exists():
                # Remove current chapters
                if self.chapters_dir.exists():
                    shutil.rmtree(self.chapters_dir)
                
                # Restore from backup
                shutil.copytree(chapters_backup, self.chapters_dir)
            
            # Restore state files
            state_backup = backup_dir / "state"
            if state_backup.exists():
                for backup_file in state_backup.glob("*.json"):
                    target_file = self.state_dir / backup_file.name
                    shutil.copy2(backup_file, target_file)
            
            return True
            
        except Exception as e:
            self.logger.error(f"State restoration failed: {e}")
            return False
    
    def _find_backup_dir(self, recovery_point: RecoveryPoint) -> Optional[Path]:
        """Find the backup directory for a recovery point."""
        backup_timestamp = recovery_point.timestamp.replace(':', '-')
        backup_dir = self.recovery_dir / f"backup-{backup_timestamp}"
        
        if backup_dir.exists():
            return backup_dir
        
        # Try to find closest backup
        for backup_dir in self.recovery_dir.glob("backup-*"):
            if backup_dir.name.endswith(backup_timestamp[:16]):  # Match date/time prefix
                return backup_dir
        
        return None
    
    def _assess_failure_severity(self, error_message: str, context_data: Dict[str, Any] = None) -> FailureSeverity:
        """Assess the severity of a failure."""
        error_lower = error_message.lower()
        
        # Catastrophic failures
        if any(keyword in error_lower for keyword in ['corruption', 'fatal', 'system error']):
            return FailureSeverity.CATASTROPHIC
        
        # Critical failures
        if any(keyword in error_lower for keyword in ['critical', 'cannot continue', 'state lost']):
            return FailureSeverity.CRITICAL
        
        # High severity
        if any(keyword in error_lower for keyword in ['context error', 'multiple failures', 'cascading']):
            return FailureSeverity.HIGH
        
        # Medium severity
        if any(keyword in error_lower for keyword in ['quality gate', 'consistency', 'timeout']):
            return FailureSeverity.MEDIUM
        
        # Low severity
        return FailureSeverity.LOW
    
    def _classify_failure_type(self, error_message: str) -> str:
        """Classify the type of failure."""
        error_lower = error_message.lower()
        
        if 'quality' in error_lower:
            return 'quality_failure'
        elif 'context' in error_lower:
            return 'context_failure'
        elif 'timeout' in error_lower:
            return 'timeout_failure'
        elif 'api' in error_lower:
            return 'api_failure'
        elif 'corruption' in error_lower:
            return 'corruption_failure'
        else:
            return 'unknown_failure'
    
    def _calculate_total_word_count(self) -> int:
        """Calculate total word count of all chapters."""
        total = 0
        if self.chapters_dir.exists():
            for chapter_file in self.chapters_dir.glob("chapter-*.md"):
                try:
                    with open(chapter_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        total += len(content.split())
                except Exception:
                    pass
        return total
    
    def _get_quality_scores(self) -> List[float]:
        """Get quality scores for all chapters."""
        # This would integrate with the quality assessment system
        # For now, return empty list
        return []
    
    def _calculate_context_hash(self, context_data: Dict[str, Any] = None) -> str:
        """Calculate hash of context data."""
        if not context_data:
            return ""
        
        context_str = json.dumps(context_data, sort_keys=True)
        return hashlib.md5(context_str.encode()).hexdigest()
    
    def _calculate_state_hash(self) -> str:
        """Calculate hash of current state."""
        state_files = []
        for state_file in self.state_dir.glob("*.json"):
            if state_file.name != "recovery":
                try:
                    with open(state_file, 'r', encoding='utf-8') as f:
                        state_files.append(f.read())
                except Exception:
                    pass
        
        combined_state = "".join(sorted(state_files))
        return hashlib.md5(combined_state.encode()).hexdigest()
    
    def _calculate_file_checksums(self) -> Dict[str, str]:
        """Calculate checksums for all important files."""
        checksums = {}
        
        # Chapter files
        if self.chapters_dir.exists():
            for chapter_file in self.chapters_dir.glob("chapter-*.md"):
                try:
                    with open(chapter_file, 'rb') as f:
                        content = f.read()
                        checksums[str(chapter_file.relative_to(self.project_path))] = hashlib.md5(content).hexdigest()
                except Exception:
                    pass
        
        # State files
        for state_file in self.state_dir.glob("*.json"):
            if state_file.name != "recovery":
                try:
                    with open(state_file, 'rb') as f:
                        content = f.read()
                        checksums[str(state_file.relative_to(self.project_path))] = hashlib.md5(content).hexdigest()
                except Exception:
                    pass
        
        return checksums
    
    def _assess_context_quality(self, context_data: Dict[str, Any] = None) -> float:
        """Assess the quality of context data."""
        if not context_data:
            return 0.0
        
        # Simple quality assessment based on context completeness
        quality_score = 0.0
        
        if 'character_continuity' in context_data:
            quality_score += 2.0
        if 'plot_threads' in context_data:
            quality_score += 2.0
        if 'world_state' in context_data:
            quality_score += 1.0
        if 'story_so_far' in context_data:
            quality_score += 1.0
        
        return min(quality_score, 10.0)
    
    def _detect_corrupted_files(self) -> List[Path]:
        """Detect corrupted files in the project."""
        corrupted_files = []
        
        for file_path in self.state_dir.glob("*.json"):
            if file_path.name != "recovery":
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        json.load(f)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    corrupted_files.append(file_path)
        
        return corrupted_files
    
    def _restore_file_from_backup(self, file_path: Path, recovery_point: RecoveryPoint) -> bool:
        """Restore a specific file from backup."""
        try:
            backup_dir = self._find_backup_dir(recovery_point)
            if not backup_dir:
                return False
            
            backup_file = backup_dir / "state" / file_path.name
            if backup_file.exists():
                shutil.copy2(backup_file, file_path)
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"File restoration failed: {e}")
            return False
    
    def _cleanup_old_recovery_points(self):
        """Clean up old recovery points and their backups."""
        # Keep only the most recent 20 recovery points
        self.recovery_points = sorted(self.recovery_points, key=lambda rp: rp.timestamp)[-20:]
        
        # Clean up old backup directories
        existing_backups = list(self.recovery_dir.glob("backup-*"))
        valid_timestamps = {rp.timestamp.replace(':', '-') for rp in self.recovery_points}
        
        for backup_dir in existing_backups:
            backup_timestamp = backup_dir.name.replace('backup-', '')
            if backup_timestamp not in valid_timestamps:
                shutil.rmtree(backup_dir)
    
    def _update_state_after_rollback(self, recovery_point: RecoveryPoint):
        """Update state tracking after a rollback."""
        # This would update the auto-completion state to reflect the rollback
        # Implementation would depend on the specific state structure
        pass
    
    def get_recovery_status(self) -> Dict[str, Any]:
        """Get current recovery system status."""
        return {
            "recovery_points_count": len(self.recovery_points),
            "last_recovery_point": self.recovery_points[-1].timestamp if self.recovery_points else None,
            "failure_events_count": len(self.failure_log),
            "recent_failures": [
                {
                    "timestamp": event.timestamp,
                    "chapter": event.chapter_number,
                    "type": event.failure_type,
                    "severity": event.severity.value,
                    "recovery_success": event.recovery_success
                }
                for event in self.failure_log[-5:]  # Last 5 failures
            ],
            "recovery_statistics": {
                "total_recoveries": len([e for e in self.failure_log if e.recovery_actions_taken]),
                "successful_recoveries": len([e for e in self.failure_log if e.recovery_success]),
                "average_recovery_time": self._calculate_average_recovery_time()
            }
        }
    
    def _calculate_average_recovery_time(self) -> Optional[float]:
        """Calculate average recovery time."""
        recovery_times = [e.recovery_duration for e in self.failure_log 
                         if e.recovery_duration is not None]
        
        if not recovery_times:
            return None
        
        return sum(recovery_times) / len(recovery_times)
    
    def suggest_recovery_actions(self, failure_event: FailureEvent) -> List[RecoveryAction]:
        """Suggest recovery actions based on failure analysis."""
        actions = []
        
        if failure_event.severity == FailureSeverity.CATASTROPHIC:
            actions.append(RecoveryAction.EMERGENCY_RESET)
        elif failure_event.severity == FailureSeverity.CRITICAL:
            actions.extend([
                RecoveryAction.ROLLBACK_MULTIPLE_CHAPTERS,
                RecoveryAction.RESTORE_STATE
            ])
        elif failure_event.severity == FailureSeverity.HIGH:
            actions.extend([
                RecoveryAction.ROLLBACK_CHAPTER,
                RecoveryAction.RESTORE_CONTEXT
            ])
        elif failure_event.severity == FailureSeverity.MEDIUM:
            actions.append(RecoveryAction.RESTORE_CONTEXT)
        else:  # LOW
            actions.append(RecoveryAction.ROLLBACK_CHAPTER)
        
        # Add corruption repair if needed
        if 'corruption' in failure_event.error_message.lower():
            actions.insert(0, RecoveryAction.REPAIR_CORRUPTION)
        
        return actions 