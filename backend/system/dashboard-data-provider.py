#!/usr/bin/env python3
"""
Dashboard Data Provider
Reads project state JSON files and provides structured data for the progress dashboard.
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import http.server
import socketserver
import urllib.parse

class DashboardDataProvider:
    """Provides structured data for the progress dashboard by reading state files."""
    
    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.state_dir = self.project_path / ".project-state"
        
        # State file paths
        self.files = {
            'chapter_progress': self.state_dir / "chapter-progress.json",
            'pattern_database': self.state_dir / "pattern-database.json",
            'quality_baselines': self.state_dir / "quality-baselines.json",
            'brutal_assessment': self.state_dir / "brutal-assessment-results.json",
            'research_citations': self.state_dir / "research-citations.json",
            'research_verifications': self.state_dir / "research-verifications.json",
            'series_balance': self.state_dir / "series-balance-results.json",
            'em_dash_violations': self.state_dir / "em-dash-violations.json",
            'continuous_audit': self.state_dir / "continuous-audit-results.json"
        }
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Compile all dashboard data from state files."""
        
        try:
            data = {
                'project_health': self._get_project_health(),
                'chapter_progress': self._get_chapter_progress(),
                'quality_metrics': self._get_quality_metrics(),
                'pattern_analysis': self._get_pattern_analysis(),
                'research_status': self._get_research_status(),
                'compliance_status': self._get_compliance_status(),
                'alerts': self._get_active_alerts(),
                'timestamp': datetime.now().isoformat(),
                'status': 'success'
            }
            
            return data
            
        except Exception as e:
            return {
                'error': str(e),
                'status': 'error',
                'timestamp': datetime.now().isoformat()
            }
    
    def _load_json_file(self, file_path: Path) -> Dict[str, Any]:
        """Safely load a JSON file, returning empty dict if not found or invalid."""
        try:
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError, PermissionError):
            pass
        return {}
    
    def _get_project_health(self) -> Dict[str, Any]:
        """Calculate overall project health score."""
        
        # Get continuous audit results
        audit_data = self._load_json_file(self.files['continuous_audit'])
        
        # Extract latest audit if available
        if audit_data:
            latest_key = max(audit_data.keys()) if audit_data else None
            if latest_key:
                latest_audit = audit_data[latest_key]
                health_score = latest_audit.get('project_health_score', 0)
            else:
                health_score = 0
        else:
            # Calculate basic health from available components
            health_components = []
            
            # Quality baselines contribution
            quality_data = self._load_json_file(self.files['quality_baselines'])
            if quality_data:
                avg_quality = sum(quality_data.values()) / len(quality_data) if quality_data else 5.0
                health_components.append(min(10.0, avg_quality))
            
            # Pattern freshness contribution
            pattern_data = self._load_json_file(self.files['pattern_database'])
            if pattern_data and 'freshness_score' in pattern_data:
                health_components.append(pattern_data['freshness_score'])
            
            # Compliance contribution
            compliance_score = self._calculate_compliance_score()
            health_components.append(compliance_score)
            
            health_score = sum(health_components) / len(health_components) if health_components else 0
        
        # Get chapter completion rate
        chapter_data = self._get_chapter_progress()
        completion_rate = chapter_data.get('completion_percentage', 0)
        
        return {
            'overall_score': round(health_score, 1),
            'completion_rate': completion_rate,
            'status': self._get_health_status(health_score),
            'trend': 'stable',  # Would need historical data to calculate
            'last_updated': datetime.now().isoformat()
        }
    
    def _get_chapter_progress(self) -> Dict[str, Any]:
        """Get chapter progress information."""
        
        chapter_data = self._load_json_file(self.files['chapter_progress'])
        
        if not chapter_data:
            # Try to infer from existing chapter files
            chapters_dir = self.project_path / "chapters"
            if chapters_dir.exists():
                chapter_files = list(chapters_dir.glob("chapter-*.md"))
                total_chapters = len(chapter_files)
                completed_chapters = 0
                
                # Basic completion detection (files > 1000 characters)
                for chapter_file in chapter_files:
                    try:
                        if chapter_file.stat().st_size > 1000:
                            completed_chapters += 1
                    except OSError:
                        pass
                
                chapter_data = {
                    'total_chapters': total_chapters,
                    'completed_chapters': completed_chapters,
                    'in_progress_chapters': 0,
                    'target_chapters': max(20, total_chapters)
                }
            else:
                chapter_data = {
                    'total_chapters': 0,
                    'completed_chapters': 0,
                    'in_progress_chapters': 0,
                    'target_chapters': 20
                }
        
        total = chapter_data.get('total_chapters', 0)
        completed = chapter_data.get('completed_chapters', 0)
        in_progress = chapter_data.get('in_progress_chapters', 0)
        target = chapter_data.get('target_chapters', 20)
        
        completion_percentage = (completed / target * 100) if target > 0 else 0
        
        # Calculate word count estimates
        avg_words_per_chapter = 4000
        estimated_word_count = completed * avg_words_per_chapter
        target_word_count = target * avg_words_per_chapter
        
        return {
            'total_chapters': total,
            'completed_chapters': completed,
            'in_progress_chapters': in_progress,
            'target_chapters': target,
            'completion_percentage': round(completion_percentage, 1),
            'estimated_word_count': estimated_word_count,
            'target_word_count': target_word_count,
            'chapters_remaining': target - completed
        }
    
    def _get_quality_metrics(self) -> Dict[str, Any]:
        """Get quality assessment metrics."""
        
        # Brutal assessment results
        brutal_data = self._load_json_file(self.files['brutal_assessment'])
        brutal_scores = []
        if brutal_data:
            for result in brutal_data.values():
                if isinstance(result, dict) and 'total_score' in result:
                    brutal_scores.append(result['total_score'])
        
        avg_brutal_score = sum(brutal_scores) / len(brutal_scores) if brutal_scores else 0
        
        # Quality baselines
        quality_data = self._load_json_file(self.files['quality_baselines'])
        baseline_scores = list(quality_data.values()) if quality_data else []
        avg_baseline = sum(baseline_scores) / len(baseline_scores) if baseline_scores else 0
        
        return {
            'brutal_assessment_average': round(avg_brutal_score, 1),
            'quality_baseline_average': round(avg_baseline, 1),
            'assessments_completed': len(brutal_scores),
            'quality_trend': 'improving',  # Would need historical analysis
            'compliance_rate': self._calculate_compliance_score() / 10.0
        }
    
    def _get_pattern_analysis(self) -> Dict[str, Any]:
        """Get pattern analysis data."""
        
        pattern_data = self._load_json_file(self.files['pattern_database'])
        
        if not pattern_data:
            return {
                'total_patterns': 0,
                'freshness_score': 0,
                'repetition_warnings': 0,
                'diversity_index': 0
            }
        
        return {
            'total_patterns': pattern_data.get('total_patterns', 0),
            'freshness_score': pattern_data.get('freshness_score', 0),
            'repetition_warnings': pattern_data.get('repetition_warnings', 0),
            'diversity_index': pattern_data.get('diversity_index', 0),
            'most_used_patterns': pattern_data.get('most_used_patterns', [])[:5]
        }
    
    def _get_research_status(self) -> Dict[str, Any]:
        """Get research tracking status."""
        
        citations_data = self._load_json_file(self.files['research_citations'])
        verifications_data = self._load_json_file(self.files['research_verifications'])
        
        citations_count = len(citations_data) if citations_data else 0
        verifications_count = len(verifications_data) if verifications_data else 0
        
        # Calculate verification rate
        verified_count = 0
        if verifications_data:
            for verification in verifications_data.values():
                if isinstance(verification, dict) and verification.get('expert_verified', False):
                    verified_count += 1
        
        verification_rate = (verified_count / verifications_count) if verifications_count > 0 else 0
        
        return {
            'citations_count': citations_count,
            'verifications_count': verifications_count,
            'verified_count': verified_count,
            'verification_rate': round(verification_rate, 2),
            'research_gaps': max(0, verifications_count - verified_count)
        }
    
    def _get_compliance_status(self) -> Dict[str, Any]:
        """Get compliance status across all systems."""
        
        # Em-dash violations
        em_dash_data = self._load_json_file(self.files['em_dash_violations'])
        em_dash_violations = 0
        if em_dash_data:
            for result in em_dash_data.values():
                if isinstance(result, dict):
                    em_dash_violations += result.get('violations_found', 0)
        
        # Series balance violations
        series_data = self._load_json_file(self.files['series_balance'])
        series_violations = 0
        if series_data:
            for result in series_data.values():
                if isinstance(result, dict) and not result.get('passes_guidelines', True):
                    series_violations += 1
        
        return {
            'em_dash_violations': em_dash_violations,
            'series_balance_violations': series_violations,
            'total_violations': em_dash_violations + series_violations,
            'compliance_percentage': self._calculate_compliance_score() * 10
        }
    
    def _calculate_compliance_score(self) -> float:
        """Calculate overall compliance score (0-10)."""
        
        try:
            score = 10.0
            
            # Get basic compliance data first
            em_dash_data = self._load_json_file(self.files['em_dash_violations'])
            em_dash_violations = 0
            if em_dash_data:
                for result in em_dash_data.values():
                    if isinstance(result, dict):
                        em_dash_violations += result.get('violations_found', 0)
            
            series_data = self._load_json_file(self.files['series_balance'])
            series_violations = 0
            if series_data:
                for result in series_data.values():
                    if isinstance(result, dict) and not result.get('passes_guidelines', True):
                        series_violations += 1
            
            total_violations = em_dash_violations + series_violations
            score -= min(5.0, total_violations * 0.5)
            
            # Research compliance
            citations_data = self._load_json_file(self.files['research_citations'])
            verifications_data = self._load_json_file(self.files['research_verifications'])
            
            verifications_count = len(verifications_data) if verifications_data else 0
            verified_count = 0
            if verifications_data:
                for verification in verifications_data.values():
                    if isinstance(verification, dict) and verification.get('expert_verified', False):
                        verified_count += 1
            
            verification_rate = (verified_count / verifications_count) if verifications_count > 0 else 1.0
            if verification_rate < 0.8:
                score -= (0.8 - verification_rate) * 5.0
            
            return max(0.0, score)
            
        except Exception:
            # Return a safe default if calculation fails
            return 5.0
    
    def _get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get active alerts that need attention."""
        
        alerts = []
        
        # Check compliance violations
        compliance = self._get_compliance_status()
        if compliance['em_dash_violations'] > 0:
            alerts.append({
                'type': 'error',
                'message': f"{compliance['em_dash_violations']} em-dash violations detected",
                'action': 'Run em-dash sentinel to locate and fix violations'
            })
        
        if compliance['series_balance_violations'] > 0:
            alerts.append({
                'type': 'warning',
                'message': f"{compliance['series_balance_violations']} series balance violations",
                'action': 'Review series balance autocheck results'
            })
        
        # Check research status
        research = self._get_research_status()
        if research['verification_rate'] < 0.8:
            alerts.append({
                'type': 'warning',
                'message': f"Research verification rate low: {research['verification_rate']:.1%}",
                'action': 'Complete expert verification for research elements'
            })
        
        # Check pattern freshness
        patterns = self._get_pattern_analysis()
        if patterns['freshness_score'] < 7.0:
            alerts.append({
                'type': 'info',
                'message': f"Pattern freshness low: {patterns['freshness_score']:.1f}/10",
                'action': 'Review pattern database for repetitive elements'
            })
        
        # Check project health
        health = self._get_project_health()
        if health['overall_score'] < 6.0:
            alerts.append({
                'type': 'error',
                'message': f"Project health critical: {health['overall_score']:.1f}/10",
                'action': 'Address quality issues and run continuous audit'
            })
        
        return alerts
    
    def _get_health_status(self, score: float) -> str:
        """Convert numeric health score to status string."""
        if score >= 8.5:
            return 'excellent'
        elif score >= 7.0:
            return 'good'
        elif score >= 5.0:
            return 'warning'
        else:
            return 'critical'
    
    def export_data_json(self, output_file: str = None) -> str:
        """Export dashboard data as JSON file."""
        
        data = self.get_dashboard_data()
        
        if output_file is None:
            output_file = str(self.project_path / "dashboard-data.json")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return output_file
    
    def serve_dashboard(self, port: int = 8080):
        """Serve the dashboard via HTTP server."""
        
        class DashboardRequestHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                self.data_provider = DashboardDataProvider()
                super().__init__(*args, **kwargs)
            
            def do_GET(self):
                if self.path == '/data.json' or self.path == '/dashboard-data.json':
                    # Serve live dashboard data
                    data = self.data_provider.get_dashboard_data()
                    
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    
                    json_data = json.dumps(data, indent=2)
                    self.wfile.write(json_data.encode('utf-8'))
                else:
                    # Serve static files
                    super().do_GET()
        
        os.chdir(self.project_path)
        
        with socketserver.TCPServer(("", port), DashboardRequestHandler) as httpd:
            print(f"Dashboard server running at http://localhost:{port}")
            print(f"Open http://localhost:{port}/tools/progress-dashboard.html")
            print(f"Data API available at http://localhost:{port}/data.json")
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\nShutting down dashboard server...")

# CLI Interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Dashboard Data Provider")
    parser.add_argument("action", choices=["data", "export", "serve"], 
                       help="Action to perform")
    parser.add_argument("--output", help="Output file for export")
    parser.add_argument("--port", type=int, default=8080, help="Port for HTTP server")
    parser.add_argument("--format", choices=["json", "pretty"], default="pretty",
                       help="Output format for data command")
    
    args = parser.parse_args()
    
    provider = DashboardDataProvider()
    
    if args.action == "data":
        data = provider.get_dashboard_data()
        
        if args.format == "json":
            print(json.dumps(data, indent=2))
        else:
            # Pretty print key metrics
            print("📚 Enhanced Writing System - Dashboard Data")
            print("=" * 50)
            
            if data.get('status') == 'error':
                print(f"❌ Error: {data.get('error')}")
            else:
                health = data['project_health']
                chapter = data['chapter_progress']
                quality = data['quality_metrics']
                
                print(f"🎯 Project Health: {health['overall_score']}/10 ({health['status']})")
                print(f"📖 Chapter Progress: {chapter['completed_chapters']}/{chapter['target_chapters']} ({chapter['completion_percentage']:.1f}%)")
                print(f"⚡ Quality Average: {quality['brutal_assessment_average']}/10")
                print(f"✅ Compliance Rate: {quality['compliance_rate']:.1%}")
                
                alerts = data['alerts']
                if alerts:
                    print(f"\n🚨 Active Alerts: {len(alerts)}")
                    for alert in alerts[:3]:  # Show first 3 alerts
                        print(f"  • {alert['message']}")
                else:
                    print("\n✅ No active alerts")
                
                print(f"\n🕒 Last Updated: {data['timestamp']}")
    
    elif args.action == "export":
        output_file = provider.export_data_json(args.output)
        print(f"Dashboard data exported to: {output_file}")
    
    elif args.action == "serve":
        provider.serve_dashboard(args.port)
    
    else:
        parser.print_help() 