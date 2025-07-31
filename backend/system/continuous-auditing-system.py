#!/usr/bin/env python3
"""
Continuous Auditing System
Automated auditing and monitoring for writing quality and project health.
"""

import json
import time
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import subprocess
import threading
import re

@dataclass
class AuditResult:
    """Represents the result of an audit run."""
    audit_type: str
    timestamp: str
    status: str
    score: float
    issues_found: int
    recommendations: List[str]
    details: Dict[str, Any]

@dataclass
class ProjectHealth:
    """Represents overall project health metrics."""
    overall_score: float
    pattern_freshness: float
    quality_consistency: float
    brutal_assessment_avg: float
    chapters_completed: int
    last_audit: str
    trend: str  # improving, stable, declining
    risk_level: str  # low, medium, high, critical

class ContinuousAuditingSystem:
    """Manages continuous auditing and project health monitoring."""
    
    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.state_dir = self.project_path / ".project-state"
        self.audit_log_path = self.state_dir / "audit-log.json"
        self.health_report_path = self.state_dir / "project-health.json"
        
        # Audit configuration
        self.config = {
            'audit_frequency_hours': 24,
            'chapter_trigger_count': 3,  # Run audit every N chapters
            'quality_threshold': 8.0,
            'brutal_threshold': 85.0,
            'pattern_threshold': 7.0
        }
        
        # Ensure state directory exists
        self.state_dir.mkdir(exist_ok=True)
        
        # Initialize audit log
        self._initialize_audit_log()
        
        # Setup scheduler
        self._setup_scheduler()
    
    def _initialize_audit_log(self):
        """Initialize audit log if it doesn't exist."""
        if not self.audit_log_path.exists():
            initial_log = {
                'metadata': {
                    'created': datetime.now().isoformat(),
                    'last_updated': datetime.now().isoformat(),
                    'total_audits': 0
                },
                'audits': [],
                'health_history': []
            }
            
            with open(self.audit_log_path, 'w', encoding='utf-8') as f:
                json.dump(initial_log, f, indent=2)
    
    def _setup_scheduler(self):
        """Setup the audit scheduler (simplified without external dependencies)."""
        # Simple timer-based approach
        pass
    
    def start_monitoring(self):
        """Start the continuous monitoring system."""
        print("🔍 Starting Continuous Auditing System...")
        print(f"📅 Scheduled audits every {self.config['audit_frequency_hours']} hours")
        print(f"📊 Chapter trigger: every {self.config['chapter_trigger_count']} chapters")
        
        # Run initial audit
        self.run_full_audit()
        
        # Start simple timer-based monitoring
        def run_monitoring():
            last_audit_time = datetime.now()
            while True:
                time.sleep(3600)  # Check every hour
                
                # Check if it's time for scheduled audit
                if datetime.now() - last_audit_time >= timedelta(hours=self.config['audit_frequency_hours']):
                    print(f"⏰ Running scheduled audit at {datetime.now()}")
                    self.run_full_audit()
                    last_audit_time = datetime.now()
                
                # Check trigger conditions
                self._check_trigger_conditions()
        
        monitor_thread = threading.Thread(target=run_monitoring, daemon=True)
        monitor_thread.start()
        
        print("✅ Continuous auditing system is now running")
        return monitor_thread
    
    def run_full_audit(self) -> Dict[str, AuditResult]:
        """Run a complete audit of the project."""
        print("🔍 Running full project audit...")
        
        audit_results = {}
        
        # 1. Pattern Database Audit
        audit_results['pattern_analysis'] = self._audit_pattern_database()
        
        # 2. Brutal Assessment Audit
        audit_results['brutal_assessment'] = self._audit_brutal_assessment()
        
        # 3. Quality Consistency Audit
        audit_results['quality_consistency'] = self._audit_quality_consistency()
        
        # 4. Project Progress Audit
        audit_results['project_progress'] = self._audit_project_progress()
        
        # 5. Risk Assessment
        audit_results['risk_assessment'] = self._audit_project_risks()
        
        # Update project health
        health = self._calculate_project_health(audit_results)
        self._save_project_health(health)
        
        # Log audit results
        self._log_audit_results(audit_results)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(audit_results, health)
        
        print(f"✅ Full audit completed - Overall Health: {health.overall_score:.1f}/10.0")
        
        return audit_results
    
    def _audit_pattern_database(self) -> AuditResult:
        """Audit pattern database for freshness and variety."""
        try:
            # Run pattern database analysis
            result = subprocess.run([
                'python3', 'system/pattern-database-engine.py', 'summary'
            ], capture_output=True, text=True, cwd=self.project_path)
            
            if result.returncode == 0:
                # Parse summary results
                output_lines = result.stdout.strip().split('\n')
                chapters_tracked = 0
                patterns_tracked = 0
                freshness_score = 10.0
                
                for line in output_lines:
                    if 'Chapters tracked:' in line:
                        chapters_tracked = int(line.split(':')[1].strip())
                    elif 'Overall freshness score:' in line:
                        freshness_score = float(line.split(':')[1].split('/')[0].strip())
                
                issues = []
                if freshness_score < self.config['pattern_threshold']:
                    issues.append(f"Pattern freshness below threshold: {freshness_score}")
                
                return AuditResult(
                    audit_type="pattern_analysis",
                    timestamp=datetime.now().isoformat(),
                    status="completed",
                    score=freshness_score,
                    issues_found=len(issues),
                    recommendations=issues,
                    details={
                        'chapters_tracked': chapters_tracked,
                        'patterns_tracked': patterns_tracked,
                        'freshness_score': freshness_score
                    }
                )
            else:
                return AuditResult(
                    audit_type="pattern_analysis",
                    timestamp=datetime.now().isoformat(),
                    status="failed",
                    score=0.0,
                    issues_found=1,
                    recommendations=["Pattern database audit failed"],
                    details={'error': result.stderr}
                )
                
        except Exception as e:
            return AuditResult(
                audit_type="pattern_analysis",
                timestamp=datetime.now().isoformat(),
                status="error",
                score=0.0,
                issues_found=1,
                recommendations=[f"Pattern audit error: {str(e)}"],
                details={'exception': str(e)}
            )
    
    def _audit_brutal_assessment(self) -> AuditResult:
        """Audit chapters using brutal assessment system."""
        try:
            chapters_dir = self.project_path / "chapters"
            chapter_files = list(chapters_dir.glob("chapter-*.md"))
            
            if not chapter_files:
                return AuditResult(
                    audit_type="brutal_assessment",
                    timestamp=datetime.now().isoformat(),
                    status="no_chapters",
                    score=0.0,
                    issues_found=0,
                    recommendations=["No chapters found to assess"],
                    details={}
                )
            
            total_score = 0.0
            failed_chapters = []
            issues = []
            
            for chapter_file in chapter_files:
                try:
                    result = subprocess.run([
                        'python3', 'system/brutal_assessment_scorer.py', 'assess',
                        '--chapter-file', str(chapter_file)
                    ], capture_output=True, text=True, cwd=self.project_path)
                    
                    if result.returncode == 0:
                        output = result.stdout
                        # Parse score from output
                        for line in output.split('\n'):
                            if 'Overall Score:' in line:
                                score = float(line.split(':')[1].split('/')[0].strip())
                                total_score += score
                                
                                if score < self.config['brutal_threshold']:
                                    failed_chapters.append({
                                        'file': chapter_file.name,
                                        'score': score
                                    })
                                break
                    else:
                        issues.append(f"Failed to assess {chapter_file.name}")
                        
                except Exception as e:
                    issues.append(f"Error assessing {chapter_file.name}: {str(e)}")
            
            avg_score = total_score / len(chapter_files) if chapter_files else 0.0
            
            if failed_chapters:
                issues.extend([f"{ch['file']}: {ch['score']:.1f}/100" for ch in failed_chapters])
            
            return AuditResult(
                audit_type="brutal_assessment",
                timestamp=datetime.now().isoformat(),
                status="completed",
                score=avg_score,
                issues_found=len(failed_chapters),
                recommendations=issues,
                details={
                    'chapters_assessed': len(chapter_files),
                    'average_score': avg_score,
                    'failed_chapters': failed_chapters
                }
            )
            
        except Exception as e:
            return AuditResult(
                audit_type="brutal_assessment",
                timestamp=datetime.now().isoformat(),
                status="error",
                score=0.0,
                issues_found=1,
                recommendations=[f"Brutal assessment error: {str(e)}"],
                details={'exception': str(e)}
            )
    
    def _audit_quality_consistency(self) -> AuditResult:
        """Audit quality consistency across chapters."""
        try:
            # Load quality baselines if available
            baselines_file = self.state_dir / "quality-baselines.json"
            
            if not baselines_file.exists():
                return AuditResult(
                    audit_type="quality_consistency",
                    timestamp=datetime.now().isoformat(),
                    status="no_baselines",
                    score=5.0,
                    issues_found=0,
                    recommendations=["Quality baselines not established"],
                    details={}
                )
            
            with open(baselines_file, 'r', encoding='utf-8') as f:
                baselines = json.load(f)
            
            quality_history = baselines.get('chapter_quality_history', {})
            
            if len(quality_history) < 2:
                return AuditResult(
                    audit_type="quality_consistency",
                    timestamp=datetime.now().isoformat(),
                    status="insufficient_data",
                    score=7.0,
                    issues_found=0,
                    recommendations=["Need more chapters for consistency analysis"],
                    details={'chapters_analyzed': len(quality_history)}
                )
            
            # Calculate consistency metrics
            scores = list(quality_history.values())
            avg_score = sum(scores) / len(scores)
            score_variance = max(scores) - min(scores)
            
            issues = []
            if score_variance > 2.0:
                issues.append(f"High quality variance: {score_variance:.1f} points")
            
            if avg_score < self.config['quality_threshold']:
                issues.append(f"Average quality below threshold: {avg_score:.1f}")
            
            consistency_score = max(0.0, 10.0 - score_variance)
            
            return AuditResult(
                audit_type="quality_consistency",
                timestamp=datetime.now().isoformat(),
                status="completed",
                score=consistency_score,
                issues_found=len(issues),
                recommendations=issues,
                details={
                    'chapters_analyzed': len(quality_history),
                    'average_score': avg_score,
                    'score_variance': score_variance,
                    'consistency_score': consistency_score
                }
            )
            
        except Exception as e:
            return AuditResult(
                audit_type="quality_consistency",
                timestamp=datetime.now().isoformat(),
                status="error",
                score=0.0,
                issues_found=1,
                recommendations=[f"Quality consistency error: {str(e)}"],
                details={'exception': str(e)}
            )
    
    def _audit_project_progress(self) -> AuditResult:
        """Audit overall project progress and milestones."""
        try:
            progress_file = self.state_dir / "chapter-progress.json"
            
            if not progress_file.exists():
                return AuditResult(
                    audit_type="project_progress",
                    timestamp=datetime.now().isoformat(),
                    status="no_progress_data",
                    score=5.0,
                    issues_found=0,
                    recommendations=["Project progress tracking not initialized"],
                    details={}
                )
            
            with open(progress_file, 'r', encoding='utf-8') as f:
                progress = json.load(f)
            
            metadata = progress.get('metadata', {})
            chapters_completed = metadata.get('chapters_completed', 0)
            total_planned = metadata.get('total_chapters_planned', 0)
            current_word_count = metadata.get('current_word_count', 0)
            target_word_count = metadata.get('target_word_count', 0)
            
            issues = []
            
            # Check progress rate
            if total_planned > 0:
                completion_rate = chapters_completed / total_planned
                if completion_rate < 0.1:
                    issues.append("Very low completion rate")
                elif completion_rate < 0.3:
                    issues.append("Low completion rate")
            
            # Check word count progress
            if target_word_count > 0:
                word_progress = current_word_count / target_word_count
                if word_progress < 0.5 and chapters_completed > total_planned * 0.5:
                    issues.append("Word count behind schedule")
            
            # Calculate progress score
            progress_score = min(10.0, (chapters_completed / max(1, total_planned)) * 10)
            
            return AuditResult(
                audit_type="project_progress",
                timestamp=datetime.now().isoformat(),
                status="completed",
                score=progress_score,
                issues_found=len(issues),
                recommendations=issues,
                details={
                    'chapters_completed': chapters_completed,
                    'total_planned': total_planned,
                    'completion_rate': chapters_completed / max(1, total_planned),
                    'word_count_progress': current_word_count / max(1, target_word_count)
                }
            )
            
        except Exception as e:
            return AuditResult(
                audit_type="project_progress",
                timestamp=datetime.now().isoformat(),
                status="error",
                score=0.0,
                issues_found=1,
                recommendations=[f"Progress audit error: {str(e)}"],
                details={'exception': str(e)}
            )
    
    def _audit_project_risks(self) -> AuditResult:
        """Audit project risks and potential issues."""
        try:
            issues = []
            risk_score = 10.0
            
            # Check for common risk indicators
            
            # 1. Backup freshness
            backups_dir = self.project_path / "backups"
            if backups_dir.exists():
                backup_dirs = [d for d in backups_dir.iterdir() if d.is_dir()]
                if backup_dirs:
                    latest_backup = max(backup_dirs, key=lambda d: d.stat().st_mtime)
                    backup_age = datetime.now() - datetime.fromtimestamp(latest_backup.stat().st_mtime)
                    
                    if backup_age > timedelta(days=7):
                        issues.append("Backup older than 7 days")
                        risk_score -= 1.0
                else:
                    issues.append("No project backups found")
                    risk_score -= 2.0
            
            # 2. File integrity
            essential_files = ['README.md', 'user-manual.md', 'quality-gates.yml']
            for file_name in essential_files:
                if not (self.project_path / file_name).exists():
                    issues.append(f"Missing essential file: {file_name}")
                    risk_score -= 1.0
            
            # 3. State directory integrity
            required_state_files = [
                'pattern-database.json',
                'quality-baselines.json',
                'chapter-progress.json'
            ]
            
            for file_name in required_state_files:
                state_file = self.state_dir / file_name
                if not state_file.exists():
                    issues.append(f"Missing state file: {file_name}")
                    risk_score -= 0.5
            
            # 4. Chapter consistency
            chapters_dir = self.project_path / "chapters"
            if chapters_dir.exists():
                chapter_files = list(chapters_dir.glob("chapter-*.md"))
                if len(chapter_files) > 0:
                    # Check for chapter numbering gaps
                    chapter_numbers = []
                    for chapter_file in chapter_files:
                        match = re.search(r'chapter-(\d+)', chapter_file.name)
                        if match:
                            chapter_numbers.append(int(match.group(1)))
                    
                    if chapter_numbers:
                        chapter_numbers.sort()
                        for i in range(1, max(chapter_numbers) + 1):
                            if i not in chapter_numbers:
                                issues.append(f"Missing chapter {i}")
                                risk_score -= 0.5
            
            risk_level = "low"
            if risk_score < 6.0:
                risk_level = "critical"
            elif risk_score < 7.5:
                risk_level = "high"
            elif risk_score < 9.0:
                risk_level = "medium"
            
            return AuditResult(
                audit_type="risk_assessment",
                timestamp=datetime.now().isoformat(),
                status="completed",
                score=risk_score,
                issues_found=len(issues),
                recommendations=issues,
                details={
                    'risk_level': risk_level,
                    'risk_factors': len(issues)
                }
            )
            
        except Exception as e:
            return AuditResult(
                audit_type="risk_assessment",
                timestamp=datetime.now().isoformat(),
                status="error",
                score=0.0,
                issues_found=1,
                recommendations=[f"Risk assessment error: {str(e)}"],
                details={'exception': str(e)}
            )
    
    def _calculate_project_health(self, audit_results: Dict[str, AuditResult]) -> ProjectHealth:
        """Calculate overall project health from audit results."""
        # Weight different audit categories
        weights = {
            'pattern_analysis': 0.2,
            'brutal_assessment': 0.3,
            'quality_consistency': 0.25,
            'project_progress': 0.15,
            'risk_assessment': 0.1
        }
        
        total_weighted_score = 0.0
        total_weight = 0.0
        
        for audit_type, result in audit_results.items():
            if audit_type in weights:
                weight = weights[audit_type]
                total_weighted_score += result.score * weight
                total_weight += weight
        
        overall_score = total_weighted_score / total_weight if total_weight > 0 else 0.0
        
        # Determine trend (simplified - would use historical data in practice)
        trend = "stable"
        if overall_score >= 8.5:
            trend = "improving"
        elif overall_score < 6.0:
            trend = "declining"
        
        # Determine risk level
        risk_result = audit_results.get('risk_assessment')
        risk_level = risk_result.details.get('risk_level', 'medium') if risk_result else 'medium'
        
        # Get project progress info
        progress_result = audit_results.get('project_progress')
        chapters_completed = 0
        if progress_result and progress_result.details:
            chapters_completed = progress_result.details.get('chapters_completed', 0)
        
        return ProjectHealth(
            overall_score=overall_score,
            pattern_freshness=audit_results.get('pattern_analysis', AuditResult('', '', '', 0.0, 0, [], {})).score,
            quality_consistency=audit_results.get('quality_consistency', AuditResult('', '', '', 0.0, 0, [], {})).score,
            brutal_assessment_avg=audit_results.get('brutal_assessment', AuditResult('', '', '', 0.0, 0, [], {})).score,
            chapters_completed=chapters_completed,
            last_audit=datetime.now().isoformat(),
            trend=trend,
            risk_level=risk_level
        )
    
    def _save_project_health(self, health: ProjectHealth):
        """Save project health to file."""
        with open(self.health_report_path, 'w', encoding='utf-8') as f:
            json.dump(asdict(health), f, indent=2)
    
    def _log_audit_results(self, audit_results: Dict[str, AuditResult]):
        """Log audit results to audit log."""
        # Load existing log
        with open(self.audit_log_path, 'r', encoding='utf-8') as f:
            log = json.load(f)
        
        # Add new audit results
        audit_entry = {
            'timestamp': datetime.now().isoformat(),
            'results': {k: asdict(v) for k, v in audit_results.items()}
        }
        
        log['audits'].append(audit_entry)
        log['metadata']['total_audits'] += 1
        log['metadata']['last_updated'] = datetime.now().isoformat()
        
        # Save updated log
        with open(self.audit_log_path, 'w', encoding='utf-8') as f:
            json.dump(log, f, indent=2)
    
    def _generate_recommendations(self, audit_results: Dict[str, AuditResult], 
                                health: ProjectHealth) -> List[str]:
        """Generate actionable recommendations based on audit results."""
        recommendations = []
        
        # Collect all issues from audit results
        all_issues = []
        for result in audit_results.values():
            all_issues.extend(result.recommendations)
        
        # Prioritize recommendations based on health score
        if health.overall_score < 6.0:
            recommendations.append("🚨 CRITICAL: Overall project health is poor - immediate action required")
        elif health.overall_score < 7.5:
            recommendations.append("⚠️ WARNING: Project health below standards - review needed")
        
        # Add specific recommendations
        if health.pattern_freshness < 7.0:
            recommendations.append("🎨 Improve pattern freshness - vary descriptions and metaphors")
        
        if health.brutal_assessment_avg < 85.0:
            recommendations.append("📈 Focus on chapter quality - brutal assessment scores need improvement")
        
        if health.quality_consistency < 8.0:
            recommendations.append("🎯 Work on consistency - maintain quality standards across chapters")
        
        if health.risk_level in ['high', 'critical']:
            recommendations.append("🛡️ Address project risks - check backups and file integrity")
        
        return recommendations
    
    def _run_scheduled_audit(self):
        """Run a scheduled audit."""
        print(f"⏰ Running scheduled audit at {datetime.now()}")
        self.run_full_audit()
    
    def _check_trigger_conditions(self):
        """Check if trigger conditions are met for immediate audit."""
        try:
            progress_file = self.state_dir / "chapter-progress.json"
            if progress_file.exists():
                with open(progress_file, 'r', encoding='utf-8') as f:
                    progress = json.load(f)
                
                chapters_completed = progress.get('metadata', {}).get('chapters_completed', 0)
                
                # Check if we've hit the chapter trigger
                if chapters_completed > 0 and chapters_completed % self.config['chapter_trigger_count'] == 0:
                    # Check if we haven't audited recently
                    if self.audit_log_path.exists():
                        with open(self.audit_log_path, 'r', encoding='utf-8') as f:
                            log = json.load(f)
                        
                        if log['audits']:
                            last_audit = datetime.fromisoformat(log['audits'][-1]['timestamp'])
                            if datetime.now() - last_audit > timedelta(hours=1):
                                print(f"📊 Chapter trigger reached ({chapters_completed} chapters) - running audit")
                                self.run_full_audit()
                    else:
                        print(f"📊 Chapter trigger reached ({chapters_completed} chapters) - running audit")
                        self.run_full_audit()
        except Exception as e:
            print(f"Error checking trigger conditions: {e}")
    
    def get_health_summary(self) -> Optional[ProjectHealth]:
        """Get current project health summary."""
        if self.health_report_path.exists():
            with open(self.health_report_path, 'r', encoding='utf-8') as f:
                health_data = json.load(f)
                return ProjectHealth(**health_data)
        return None

# CLI Interface
if __name__ == "__main__":
    import argparse
    import re
    
    parser = argparse.ArgumentParser(description="Continuous Auditing System")
    parser.add_argument("action", choices=["start", "audit", "status", "health"], 
                       help="Action to perform")
    parser.add_argument("--project-path", default=".", 
                       help="Path to project directory")
    parser.add_argument("--daemon", action="store_true",
                       help="Run as daemon process")
    
    args = parser.parse_args()
    
    auditor = ContinuousAuditingSystem(args.project_path)
    
    if args.action == "start":
        if args.daemon:
            print("🔄 Starting continuous auditing daemon...")
            thread = auditor.start_monitoring()
            try:
                # Keep main thread alive
                while True:
                    time.sleep(60)
            except KeyboardInterrupt:
                print("\n🛑 Stopping continuous auditing system...")
        else:
            print("🔍 Running single audit cycle...")
            auditor.run_full_audit()
    
    elif args.action == "audit":
        auditor.run_full_audit()
    
    elif args.action == "status":
        health = auditor.get_health_summary()
        if health:
            print(f"📊 Project Health Summary:")
            print(f"  Overall Score: {health.overall_score:.1f}/10.0")
            print(f"  Pattern Freshness: {health.pattern_freshness:.1f}/10.0")
            print(f"  Quality Consistency: {health.quality_consistency:.1f}/10.0")
            print(f"  Brutal Assessment Avg: {health.brutal_assessment_avg:.1f}/100")
            print(f"  Chapters Completed: {health.chapters_completed}")
            print(f"  Trend: {health.trend}")
            print(f"  Risk Level: {health.risk_level}")
            print(f"  Last Audit: {health.last_audit}")
        else:
            print("No health data available - run an audit first")
    
    elif args.action == "health":
        health = auditor.get_health_summary()
        if health:
            print(json.dumps(asdict(health), indent=2))
        else:
            print("{}") 