#!/usr/bin/env python3
"""
Series Balance Enforcer
Implements quantitative <5% series content checking and enforcement.
"""

import re
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional

# Import the series balance autocheck
import importlib.util
spec = importlib.util.spec_from_file_location(
    "series_balance_autocheck", 
    Path(__file__).parent / "series-balance-autocheck.py"
)
balance_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(balance_module)
SeriesBalanceAutocheck = balance_module.SeriesBalanceAutocheck

class SeriesBalanceEnforcer:
    """Enforces series balance guidelines with automated checking and blocking."""
    
    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.state_dir = self.project_path / ".project-state"
        self.enforcement_log_path = self.state_dir / "series-balance-enforcement.json"
        self.autocheck = SeriesBalanceAutocheck(project_path)
        
        # Ensure state directory exists
        self.state_dir.mkdir(exist_ok=True)
        
        # Enforcement thresholds
        self.SERIES_CONTENT_LIMIT = 5.0  # Maximum 5% series content
        self.WARNING_THRESHOLD = 3.0     # Warning at 3%
        self.CRITICAL_THRESHOLD = 7.0    # Critical failure at 7%
        
        # Quality gate integration
        self.MINIMUM_STANDALONE_SCORE = 8.0
        self.MINIMUM_COMPLIANCE_SCORE = 7.0
    
    def enforce_series_balance(self, chapter_text: str, chapter_number: int) -> Dict[str, Any]:
        """Enforce series balance requirements with pass/fail determination."""
        
        # Run automated series balance analysis
        analysis = self.autocheck.analyze_chapter(chapter_text, chapter_number)
        
        # Determine enforcement result
        enforcement_result = {
            'chapter_number': chapter_number,
            'series_content_percentage': analysis.series_content_percentage,
            'individual_story_percentage': analysis.individual_story_percentage,
            'compliance_score': analysis.compliance_score,
            'standalone_satisfaction_score': analysis.standalone_satisfaction_score,
            'passes_enforcement': analysis.passes_guidelines,
            'enforcement_level': self._determine_enforcement_level(analysis),
            'violations': self._extract_violations(analysis),
            'enforcement_actions': self._determine_enforcement_actions(analysis),
            'blocking_issues': self._identify_blocking_issues(analysis),
            'timestamp': datetime.now().isoformat()
        }
        
        # Log enforcement action
        self._log_enforcement(enforcement_result)
        
        return enforcement_result
    
    def _determine_enforcement_level(self, analysis) -> str:
        """Determine the level of enforcement action required."""
        
        series_pct = analysis.series_content_percentage
        standalone_score = analysis.standalone_satisfaction_score
        compliance_score = analysis.compliance_score
        
        # Critical violations that block chapter acceptance
        if series_pct >= self.CRITICAL_THRESHOLD:
            return 'BLOCK'
        
        # Major violations that require immediate attention
        if (series_pct > self.SERIES_CONTENT_LIMIT or 
            standalone_score < self.MINIMUM_STANDALONE_SCORE or
            compliance_score < self.MINIMUM_COMPLIANCE_SCORE):
            return 'FAIL'
        
        # Minor violations that issue warnings
        if series_pct >= self.WARNING_THRESHOLD:
            return 'WARNING'
        
        # Acceptable levels
        return 'PASS'
    
    def _extract_violations(self, analysis) -> List[Dict[str, Any]]:
        """Extract specific violations from the analysis."""
        
        violations = []
        
        # Series content percentage violation
        if analysis.series_content_percentage > self.SERIES_CONTENT_LIMIT:
            violation_severity = 'critical' if analysis.series_content_percentage >= self.CRITICAL_THRESHOLD else 'major'
            violations.append({
                'type': 'series_content_excess',
                'severity': violation_severity,
                'current_value': analysis.series_content_percentage,
                'limit': self.SERIES_CONTENT_LIMIT,
                'excess': analysis.series_content_percentage - self.SERIES_CONTENT_LIMIT,
                'description': f"Series content at {analysis.series_content_percentage:.1f}% exceeds {self.SERIES_CONTENT_LIMIT}% limit"
            })
        
        # Standalone satisfaction violation
        if analysis.standalone_satisfaction_score < self.MINIMUM_STANDALONE_SCORE:
            violations.append({
                'type': 'standalone_satisfaction_low',
                'severity': 'major',
                'current_value': analysis.standalone_satisfaction_score,
                'minimum': self.MINIMUM_STANDALONE_SCORE,
                'deficit': self.MINIMUM_STANDALONE_SCORE - analysis.standalone_satisfaction_score,
                'description': f"Standalone satisfaction score {analysis.standalone_satisfaction_score:.1f}/10 below required {self.MINIMUM_STANDALONE_SCORE}/10"
            })
        
        # Compliance score violation
        if analysis.compliance_score < self.MINIMUM_COMPLIANCE_SCORE:
            violations.append({
                'type': 'compliance_score_low',
                'severity': 'major',
                'current_value': analysis.compliance_score,
                'minimum': self.MINIMUM_COMPLIANCE_SCORE,
                'deficit': self.MINIMUM_COMPLIANCE_SCORE - analysis.compliance_score,
                'description': f"Compliance score {analysis.compliance_score:.1f}/10 below required {self.MINIMUM_COMPLIANCE_SCORE}/10"
            })
        
        # Series element violations
        if hasattr(analysis, 'series_elements'):
            sequel_bait_count = sum(1 for element in analysis.series_elements if element.type == 'sequel_baiting')
            if sequel_bait_count > 0:
                violations.append({
                    'type': 'sequel_baiting_detected',
                    'severity': 'major',
                    'current_value': sequel_bait_count,
                    'limit': 0,
                    'description': f"{sequel_bait_count} sequel baiting elements detected (forbidden)"
                })
        
        return violations
    
    def _determine_enforcement_actions(self, analysis) -> List[str]:
        """Determine specific enforcement actions required."""
        
        actions = []
        series_pct = analysis.series_content_percentage
        
        # Actions based on enforcement level
        enforcement_level = self._determine_enforcement_level(analysis)
        
        if enforcement_level == 'BLOCK':
            actions.extend([
                "❌ BLOCK CHAPTER: Critical series balance violation",
                "🚨 Immediate revision required before acceptance",
                f"📉 Reduce series content from {series_pct:.1f}% to below {self.SERIES_CONTENT_LIMIT}%",
                "🔄 Re-run enforcement check after revision"
            ])
        
        elif enforcement_level == 'FAIL':
            actions.extend([
                "⚠️ FAIL QUALITY GATE: Major series balance violation",
                "📝 Revision required before chapter completion",
                "🎯 Focus on individual story resolution"
            ])
            
            if series_pct > self.SERIES_CONTENT_LIMIT:
                actions.append(f"📉 Reduce series content from {series_pct:.1f}% to below {self.SERIES_CONTENT_LIMIT}%")
            
            if analysis.standalone_satisfaction_score < self.MINIMUM_STANDALONE_SCORE:
                actions.append(f"📖 Improve standalone satisfaction from {analysis.standalone_satisfaction_score:.1f} to {self.MINIMUM_STANDALONE_SCORE}+")
        
        elif enforcement_level == 'WARNING':
            actions.extend([
                "⚠️ WARNING: Series content approaching limit",
                f"📊 Current: {series_pct:.1f}%, Limit: {self.SERIES_CONTENT_LIMIT}%",
                "👀 Monitor future chapters to prevent violation"
            ])
        
        else:  # PASS
            actions.extend([
                "✅ PASS: Series balance guidelines met",
                f"📊 Series content: {series_pct:.1f}% (within {self.SERIES_CONTENT_LIMIT}% limit)",
                f"📖 Standalone satisfaction: {analysis.standalone_satisfaction_score:.1f}/10"
            ])
        
        # Add specific recommendations from analysis
        if hasattr(analysis, 'recommendations'):
            actions.extend([f"💡 {rec}" for rec in analysis.recommendations])
        
        return actions
    
    def _identify_blocking_issues(self, analysis) -> List[str]:
        """Identify issues that would block chapter acceptance."""
        
        blocking_issues = []
        
        # Critical series content excess
        if analysis.series_content_percentage >= self.CRITICAL_THRESHOLD:
            blocking_issues.append(f"Series content at {analysis.series_content_percentage:.1f}% far exceeds {self.SERIES_CONTENT_LIMIT}% limit")
        
        # Major series content violation
        elif analysis.series_content_percentage > self.SERIES_CONTENT_LIMIT:
            blocking_issues.append(f"Series content at {analysis.series_content_percentage:.1f}% exceeds {self.SERIES_CONTENT_LIMIT}% limit")
        
        # Insufficient standalone satisfaction
        if analysis.standalone_satisfaction_score < self.MINIMUM_STANDALONE_SCORE:
            blocking_issues.append(f"Standalone satisfaction {analysis.standalone_satisfaction_score:.1f}/10 below required {self.MINIMUM_STANDALONE_SCORE}/10")
        
        # Low compliance score
        if analysis.compliance_score < self.MINIMUM_COMPLIANCE_SCORE:
            blocking_issues.append(f"Compliance score {analysis.compliance_score:.1f}/10 below required {self.MINIMUM_COMPLIANCE_SCORE}/10")
        
        # Guidelines non-compliance
        if not analysis.passes_guidelines:
            blocking_issues.append("Chapter fails series balance guidelines compliance")
        
        return blocking_issues
    
    def _log_enforcement(self, enforcement_result: Dict[str, Any]):
        """Log enforcement action for tracking and analysis."""
        
        log_data = []
        
        # Load existing log
        if self.enforcement_log_path.exists():
            try:
                with open(self.enforcement_log_path, 'r', encoding='utf-8') as f:
                    log_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        
        # Add new entry
        log_data.append(enforcement_result)
        
        # Keep only last 100 entries
        log_data = log_data[-100:]
        
        # Save updated log
        with open(self.enforcement_log_path, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2)
    
    def get_enforcement_statistics(self) -> Dict[str, Any]:
        """Get enforcement statistics and trends."""
        
        if not self.enforcement_log_path.exists():
            return {'status': 'no_data', 'total_enforcements': 0}
        
        try:
            with open(self.enforcement_log_path, 'r', encoding='utf-8') as f:
                log_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return {'status': 'error', 'message': 'Unable to load enforcement log'}
        
        if not log_data:
            return {'status': 'no_data', 'total_enforcements': 0}
        
        # Calculate statistics
        total_enforcements = len(log_data)
        
        # Count by enforcement level
        level_counts = {}
        violation_counts = {}
        
        for entry in log_data:
            level = entry.get('enforcement_level', 'UNKNOWN')
            level_counts[level] = level_counts.get(level, 0) + 1
            
            for violation in entry.get('violations', []):
                vtype = violation.get('type', 'unknown')
                violation_counts[vtype] = violation_counts.get(vtype, 0) + 1
        
        # Calculate series content statistics
        series_percentages = [entry.get('series_content_percentage', 0) for entry in log_data]
        avg_series_content = sum(series_percentages) / len(series_percentages) if series_percentages else 0
        
        # Calculate compliance rates
        passes = sum(1 for entry in log_data if entry.get('passes_enforcement', False))
        compliance_rate = passes / total_enforcements if total_enforcements > 0 else 0
        
        # Recent trend (last 10 entries)
        recent_entries = log_data[-10:] if len(log_data) >= 10 else log_data
        recent_avg = sum(entry.get('series_content_percentage', 0) for entry in recent_entries) / len(recent_entries) if recent_entries else 0
        
        return {
            'status': 'success',
            'total_enforcements': total_enforcements,
            'compliance_rate': compliance_rate,
            'average_series_content': avg_series_content,
            'recent_average_series_content': recent_avg,
            'enforcement_level_counts': level_counts,
            'violation_type_counts': violation_counts,
            'trend': 'improving' if recent_avg < avg_series_content else 'stable',
            'last_enforcement': log_data[-1]['timestamp'] if log_data else None
        }
    
    def generate_enforcement_report(self) -> str:
        """Generate comprehensive enforcement report."""
        
        stats = self.get_enforcement_statistics()
        
        if stats['status'] == 'no_data':
            return "No enforcement data available. No chapters have been checked yet."
        
        if stats['status'] == 'error':
            return f"Error generating report: {stats['message']}"
        
        report = f"""# Series Balance Enforcement Report
Generated: {datetime.now().isoformat()}

## Summary Statistics
- Total Enforcements: {stats['total_enforcements']}
- Compliance Rate: {stats['compliance_rate']:.1%}
- Average Series Content: {stats['average_series_content']:.1f}%
- Recent Average: {stats['recent_average_series_content']:.1f}%
- Trend: {stats['trend'].title()}

## Enforcement Levels
"""
        
        for level, count in sorted(stats['enforcement_level_counts'].items()):
            percentage = (count / stats['total_enforcements']) * 100
            status_emoji = {
                'PASS': '✅',
                'WARNING': '⚠️', 
                'FAIL': '❌',
                'BLOCK': '🚨'
            }.get(level, '❓')
            
            report += f"- {status_emoji} {level}: {count} ({percentage:.1f}%)\n"
        
        if stats['violation_type_counts']:
            report += "\n## Most Common Violations\n"
            sorted_violations = sorted(stats['violation_type_counts'].items(), key=lambda x: x[1], reverse=True)
            
            for violation_type, count in sorted_violations[:5]:
                violation_name = violation_type.replace('_', ' ').title()
                report += f"- {violation_name}: {count} occurrences\n"
        
        # Add enforcement guidance
        report += f"""

## Enforcement Standards
- Maximum Series Content: {self.SERIES_CONTENT_LIMIT}%
- Warning Threshold: {self.WARNING_THRESHOLD}%
- Critical Threshold: {self.CRITICAL_THRESHOLD}%
- Minimum Standalone Score: {self.MINIMUM_STANDALONE_SCORE}/10
- Minimum Compliance Score: {self.MINIMUM_COMPLIANCE_SCORE}/10

## Compliance Status
"""
        
        if stats['compliance_rate'] >= 0.9:
            report += "✅ **EXCELLENT**: High compliance with series balance guidelines\n"
        elif stats['compliance_rate'] >= 0.7:
            report += "✅ **GOOD**: Most chapters meet series balance requirements\n"
        elif stats['compliance_rate'] >= 0.5:
            report += "⚠️ **NEEDS ATTENTION**: Several chapters violate series balance\n"
        else:
            report += "❌ **CRITICAL**: Majority of chapters fail series balance enforcement\n"
        
        return report
    
    def run_enforcement_test(self) -> Dict[str, Any]:
        """Test the enforcement system with sample chapters."""
        
        # High series content chapter (should fail)
        high_series_chapter = """
        This was just the beginning of Sarah's journey. In future books, she would face 
        even greater challenges as she developed her detective skills. The organization 
        she was about to encounter would become central to the entire series.
        
        Little did she know that this case would introduce her to characters who would 
        become her closest allies in later adventures. The mentor she was destined to 
        meet was already working behind the scenes.
        
        As Sarah closed the file, she had no idea that her investigation would eventually 
        uncover a conspiracy spanning multiple books. This was only the tip of the iceberg.
        
        The seeds of future conflicts were already being planted, setting up storylines 
        that would unfold across the next several volumes of her adventures.
        
        "Detective Martinez," her captain said, "this case is more important than you know. 
        It's connected to something bigger - something that will define your entire career."
        
        But that's a story for another book. For now, Sarah had a murder to solve, though 
        the implications would stretch far beyond this single case.
        """
        
        # Balanced chapter (should pass)
        balanced_chapter = """
        Detective Sarah Martinez walked into the crime scene with purpose. The victim 
        lay sprawled across the kitchen floor, a pool of blood expanding beneath his head.
        
        "What do we know?" she asked Officer Chen, who was securing the perimeter.
        
        "Neighbor called it in around 3 AM. Heard shouting, then a crash. When we 
        arrived, the front door was open and we found him like this."
        
        Sarah knelt beside the body, careful not to disturb the evidence. The wound 
        appeared to be from a blunt instrument - possibly the marble bookend lying 
        nearby, now stained with blood.
        
        "Any signs of forced entry?" she asked, scanning the room for clues.
        
        "None. Either he knew his attacker, or they had a key."
        
        As she examined the scene, Sarah noticed something odd. The victim's wedding 
        ring was missing, but his expensive watch remained untouched. This wasn't 
        a robbery gone wrong - this was personal.
        
        "Get me everything on the victim," she told Chen. "Family, friends, enemies. 
        Someone wanted this man dead, and I'm going to find out who."
        """
        
        try:
            # Test high series content chapter
            high_series_result = self.enforce_series_balance(high_series_chapter, 997)
            
            # Test balanced chapter
            balanced_result = self.enforce_series_balance(balanced_chapter, 998)
            
            return {
                'status': 'success',
                'high_series_enforcement_level': high_series_result['enforcement_level'],
                'high_series_percentage': high_series_result['series_content_percentage'],
                'high_series_passes': high_series_result['passes_enforcement'],
                'balanced_enforcement_level': balanced_result['enforcement_level'],
                'balanced_percentage': balanced_result['series_content_percentage'],
                'balanced_passes': balanced_result['passes_enforcement'],
                'test_passed': (not high_series_result['passes_enforcement'] and 
                              balanced_result['passes_enforcement'] and
                              high_series_result['series_content_percentage'] > balanced_result['series_content_percentage'])
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
    
    parser = argparse.ArgumentParser(description="Series Balance Enforcer")
    parser.add_argument("action", choices=["enforce", "stats", "report", "test"], 
                       help="Action to perform")
    parser.add_argument("--chapter-file", help="Chapter file to enforce")
    parser.add_argument("--chapter-number", type=int, help="Chapter number")
    parser.add_argument("--text", help="Chapter text for direct enforcement")
    parser.add_argument("--output", help="Output file for report")
    
    args = parser.parse_args()
    
    enforcer = SeriesBalanceEnforcer()
    
    if args.action == "enforce" and (args.chapter_file or args.text) and args.chapter_number:
        if args.chapter_file:
            with open(args.chapter_file, 'r', encoding='utf-8') as f:
                chapter_text = f.read()
        else:
            chapter_text = args.text
        
        result = enforcer.enforce_series_balance(chapter_text, args.chapter_number)
        
        print(f"🔒 Series Balance Enforcement - Chapter {args.chapter_number}")
        print("=" * 60)
        
        # Show enforcement result
        enforcement_level = result['enforcement_level']
        status_emojis = {'PASS': '✅', 'WARNING': '⚠️', 'FAIL': '❌', 'BLOCK': '🚨'}
        status_emoji = status_emojis.get(enforcement_level, '❓')
        
        print(f"{status_emoji} Enforcement Level: {enforcement_level}")
        print(f"📊 Series Content: {result['series_content_percentage']:.1f}% (limit: {enforcer.SERIES_CONTENT_LIMIT}%)")
        print(f"📖 Standalone Score: {result['standalone_satisfaction_score']:.1f}/10")
        print(f"✅ Compliance Score: {result['compliance_score']:.1f}/10")
        print(f"🎯 Passes Guidelines: {'YES' if result['passes_enforcement'] else 'NO'}")
        
        # Show violations
        if result['violations']:
            print(f"\n🚨 Violations ({len(result['violations'])}):")
            for violation in result['violations']:
                severity_emoji = {'critical': '🚨', 'major': '❌', 'minor': '⚠️'}.get(violation['severity'], '❓')
                print(f"  {severity_emoji} {violation['description']}")
        
        # Show blocking issues
        if result['blocking_issues']:
            print(f"\n🛑 Blocking Issues:")
            for issue in result['blocking_issues']:
                print(f"  🛑 {issue}")
        
        # Show enforcement actions
        if result['enforcement_actions']:
            print(f"\n📋 Required Actions:")
            for action in result['enforcement_actions']:
                print(f"  {action}")
    
    elif args.action == "stats":
        stats = enforcer.get_enforcement_statistics()
        
        if stats['status'] == 'no_data':
            print("No enforcement statistics available.")
        elif stats['status'] == 'error':
            print(f"Error: {stats['message']}")
        else:
            print("📊 Series Balance Enforcement Statistics")
            print("=" * 50)
            print(f"Total Enforcements: {stats['total_enforcements']}")
            print(f"Compliance Rate: {stats['compliance_rate']:.1%}")
            print(f"Average Series Content: {stats['average_series_content']:.1f}%")
            print(f"Recent Average: {stats['recent_average_series_content']:.1f}%")
            print(f"Trend: {stats['trend'].title()}")
            
            if stats['enforcement_level_counts']:
                print(f"\nEnforcement Level Distribution:")
                for level, count in sorted(stats['enforcement_level_counts'].items()):
                    percentage = (count / stats['total_enforcements']) * 100
                    print(f"  {level}: {count} ({percentage:.1f}%)")
    
    elif args.action == "report":
        report = enforcer.generate_enforcement_report()
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"Enforcement report saved to: {args.output}")
        else:
            print(report)
    
    elif args.action == "test":
        results = enforcer.run_enforcement_test()
        
        print("🧪 Series Balance Enforcement Test")
        print("=" * 40)
        print(f"Status: {results['status']}")
        print(f"Test Passed: {'✅ YES' if results['test_passed'] else '❌ NO'}")
        
        if results['status'] == 'success':
            print(f"\nHigh Series Content Chapter:")
            print(f"  Level: {results['high_series_enforcement_level']}")
            print(f"  Series %: {results['high_series_percentage']:.1f}%")
            print(f"  Passes: {'YES' if results['high_series_passes'] else 'NO'}")
            
            print(f"\nBalanced Chapter:")
            print(f"  Level: {results['balanced_enforcement_level']}")
            print(f"  Series %: {results['balanced_percentage']:.1f}%")
            print(f"  Passes: {'YES' if results['balanced_passes'] else 'NO'}")
        else:
            print(f"Error: {results.get('error', 'Unknown error')}")
    
    else:
        print("Please provide required arguments for the specified action")
        parser.print_help() 