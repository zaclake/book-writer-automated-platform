#!/usr/bin/env python3
"""
Em-Dash Sentinel
Lightweight regex check that fails if em-dashes (—) appear outside quoted text.
Zero-tolerance punctuation compliance for Enhanced Writing System v2.0.
"""

import re
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass, asdict

@dataclass
class EmDashViolation:
    """Represents an em-dash violation found in text."""
    line_number: int
    column_position: int
    context: str
    violation_type: str  # narrative, dialogue, action, description
    surrounding_text: str
    replacement_suggestion: str

@dataclass
class EmDashScanResult:
    """Results of em-dash scanning and analysis."""
    file_path: str
    total_lines: int
    violations_found: int
    violations: List[EmDashViolation]
    compliance_status: str  # PASS, FAIL, WARNING
    scan_timestamp: str
    recommendations: List[str]

class EmDashSentinel:
    """Lightweight em-dash detection and compliance checking."""
    
    # Em-dash character variants to detect
    EM_DASH_PATTERNS = [
        r'—',          # Unicode em-dash (U+2014)
        r'–',          # En-dash (U+2013) - often confused with em-dash
        r'\u2014',     # Unicode em-dash explicit
        r'\u2013',     # Unicode en-dash explicit
        r'&mdash;',    # HTML entity
        r'&ndash;',    # HTML entity for en-dash
    ]
    
    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.state_dir = self.project_path / ".project-state"
        self.results_path = self.state_dir / "em-dash-violations.json"
        
        # Quote detection patterns for context analysis
        self.quote_patterns = [
            r'"[^"]*"',                    # Double quotes
            r"'[^']*'",                    # Single quotes
            r'[\u201c][^\u201d]*[\u201d]',  # Smart double quotes
            r'[\u2018][^\u2019]*[\u2019]',  # Smart single quotes
            r'""".*?"""',                  # Triple quotes
            r"'''.*?'''",                  # Triple single quotes
        ]
        
        # Common replacement suggestions
        self.replacement_map = {
            'explanation': 'colon (:)',
            'parenthetical': 'commas (,)',
            'strong_break': 'period (.)',
            'connection': 'semicolon (;)',
            'list_introduction': 'colon (:)',
            'aside': 'parentheses ()',
        }
        
        # Ensure state directory exists
        self.state_dir.mkdir(exist_ok=True)
    
    def scan_text(self, text: str, file_path: str = "text_input") -> EmDashScanResult:
        """Scan text for em-dash violations."""
        lines = text.split('\n')
        violations = []
        
        for line_num, line in enumerate(lines, 1):
            line_violations = self._scan_line(line, line_num)
            violations.extend(line_violations)
        
        # Determine compliance status
        if violations:
            compliance_status = "FAIL"
        else:
            compliance_status = "PASS"
        
        # Generate recommendations
        recommendations = self._generate_recommendations(violations)
        
        result = EmDashScanResult(
            file_path=file_path,
            total_lines=len(lines),
            violations_found=len(violations),
            violations=violations,
            compliance_status=compliance_status,
            scan_timestamp=datetime.now().isoformat(),
            recommendations=recommendations
        )
        
        # Save result
        self._save_result(result)
        
        return result
    
    def scan_file(self, file_path: str) -> EmDashScanResult:
        """Scan a file for em-dash violations."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            return self.scan_text(text, file_path)
        except FileNotFoundError:
            # Return empty result with error status
            return EmDashScanResult(
                file_path=file_path,
                total_lines=0,
                violations_found=0,
                violations=[],
                compliance_status="ERROR",
                scan_timestamp=datetime.now().isoformat(),
                recommendations=[f"File not found: {file_path}"]
            )
        except Exception as e:
            return EmDashScanResult(
                file_path=file_path,
                total_lines=0,
                violations_found=0,
                violations=[],
                compliance_status="ERROR",
                scan_timestamp=datetime.now().isoformat(),
                recommendations=[f"Error reading file: {str(e)}"]
            )
    
    def _scan_line(self, line: str, line_number: int) -> List[EmDashViolation]:
        """Scan a single line for em-dash violations."""
        violations = []
        
        # Find all quoted text segments
        quoted_segments = self._find_quoted_segments(line)
        
        # Create a mask of quoted positions
        quoted_positions = set()
        for start, end in quoted_segments:
            quoted_positions.update(range(start, end))
        
        # Check each em-dash pattern
        for pattern in self.EM_DASH_PATTERNS:
            for match in re.finditer(pattern, line):
                start_pos = match.start()
                end_pos = match.end()
                
                # Check if the em-dash is outside quoted text
                if not self._is_in_quoted_text(start_pos, quoted_positions):
                    # This is a violation
                    violation = self._create_violation(
                        line, line_number, start_pos, end_pos, match.group()
                    )
                    violations.append(violation)
        
        return violations
    
    def _find_quoted_segments(self, line: str) -> List[Tuple[int, int]]:
        """Find all quoted text segments in a line."""
        segments = []
        
        for pattern in self.quote_patterns:
            for match in re.finditer(pattern, line):
                segments.append((match.start(), match.end()))
        
        # Sort segments by start position and merge overlapping ones
        segments.sort()
        merged = []
        for start, end in segments:
            if merged and start <= merged[-1][1]:
                # Overlapping segment, merge
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        
        return merged
    
    def _is_in_quoted_text(self, position: int, quoted_positions: set) -> bool:
        """Check if a position is within quoted text."""
        return position in quoted_positions
    
    def _create_violation(self, line: str, line_number: int, start_pos: int, 
                         end_pos: int, matched_text: str) -> EmDashViolation:
        """Create a violation object with context and suggestions."""
        # Extract context around the violation
        context_start = max(0, start_pos - 30)
        context_end = min(len(line), end_pos + 30)
        context = line[context_start:context_end]
        
        # Determine violation type based on context
        violation_type = self._classify_violation_type(line, start_pos)
        
        # Generate replacement suggestion
        replacement_suggestion = self._suggest_replacement(line, start_pos, violation_type)
        
        # Get surrounding text for better context
        surrounding_start = max(0, start_pos - 50)
        surrounding_end = min(len(line), end_pos + 50)
        surrounding_text = line[surrounding_start:surrounding_end]
        
        return EmDashViolation(
            line_number=line_number,
            column_position=start_pos + 1,  # 1-indexed for user display
            context=context,
            violation_type=violation_type,
            surrounding_text=surrounding_text,
            replacement_suggestion=replacement_suggestion
        )
    
    def _classify_violation_type(self, line: str, position: int) -> str:
        """Classify the type of em-dash violation based on context."""
        # Look at text before and after the em-dash
        before_text = line[:position].strip().lower()
        after_text = line[position + 1:].strip().lower()
        
        # Check for common patterns
        if any(word in before_text for word in ['contains', 'includes', 'shows', 'reveals']):
            return 'explanation'
        
        if any(word in after_text for word in ['a', 'an', 'the', 'which', 'who', 'that']):
            return 'parenthetical'
        
        if before_text.endswith('.') or after_text.startswith('the ') or after_text.startswith('it '):
            return 'strong_break'
        
        if any(word in before_text for word in ['and', 'but', 'yet', 'however']):
            return 'connection'
        
        # Default classification
        return 'narrative'
    
    def _suggest_replacement(self, line: str, position: int, violation_type: str) -> str:
        """Suggest appropriate replacement punctuation."""
        base_suggestion = self.replacement_map.get(violation_type, 'period (.)')
        
        # Analyze specific context for more precise suggestions
        before_text = line[:position].strip()
        after_text = line[position + 1:].strip()
        
        # Specific suggestions based on context
        if violation_type == 'explanation':
            if after_text.startswith(('a ', 'an ', 'the ', 'this ', 'that ')):
                return 'colon (:) for introducing explanation'
            else:
                return 'comma (,) for parenthetical information'
        
        elif violation_type == 'parenthetical':
            return 'commas (,) to set off parenthetical information'
        
        elif violation_type == 'strong_break':
            if before_text.endswith(('.', '!', '?')):
                return 'period (.) for sentence break'
            else:
                return 'semicolon (;) for related thoughts'
        
        elif violation_type == 'connection':
            return 'semicolon (;) to connect related clauses'
        
        # Create a specific replacement example
        example_before = before_text[-20:] if len(before_text) > 20 else before_text
        example_after = after_text[:20] if len(after_text) > 20 else after_text
        
        if violation_type == 'explanation':
            return f'{base_suggestion} → "{example_before}: {example_after}"'
        elif violation_type == 'parenthetical':
            return f'{base_suggestion} → "{example_before}, {example_after}"'
        else:
            return f'{base_suggestion} → "{example_before}. {example_after.capitalize()}"'
    
    def _generate_recommendations(self, violations: List[EmDashViolation]) -> List[str]:
        """Generate actionable recommendations based on violations found."""
        recommendations = []
        
        if not violations:
            recommendations.append("✅ EXCELLENT: No em-dash violations found - text complies with Enhanced Writing System standards")
            return recommendations
        
        # Count violation types
        violation_types = {}
        for violation in violations:
            violation_types[violation.violation_type] = violation_types.get(violation.violation_type, 0) + 1
        
        recommendations.append(f"🚨 CRITICAL: {len(violations)} em-dash violations found - immediate correction required")
        
        # Type-specific recommendations
        if 'explanation' in violation_types:
            count = violation_types['explanation']
            recommendations.append(f"📝 Replace {count} explanatory em-dash{'es' if count > 1 else ''} with colons (:)")
        
        if 'parenthetical' in violation_types:
            count = violation_types['parenthetical']
            recommendations.append(f"🔗 Replace {count} parenthetical em-dash{'es' if count > 1 else ''} with commas (,)")
        
        if 'strong_break' in violation_types:
            count = violation_types['strong_break']
            recommendations.append(f"⏹️ Replace {count} break em-dash{'es' if count > 1 else ''} with periods (.)")
        
        if 'connection' in violation_types:
            count = violation_types['connection']
            recommendations.append(f"🔗 Replace {count} connecting em-dash{'es' if count > 1 else ''} with semicolons (;)")
        
        # Priority recommendations
        recommendations.append("🎯 PRIORITY: Focus on most frequent violation type first for efficient correction")
        recommendations.append("📖 REFERENCE: See em-dash-elimination-system.md for detailed replacement strategies")
        recommendations.append("🔍 VERIFICATION: Re-scan after corrections to ensure complete compliance")
        
        return recommendations
    
    def _save_result(self, result: EmDashScanResult):
        """Save scan result to database."""
        results_data = {}
        
        # Load existing results
        if self.results_path.exists():
            try:
                with open(self.results_path, 'r', encoding='utf-8') as f:
                    results_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        
        # Add new result
        timestamp_key = datetime.now().isoformat()
        results_data[timestamp_key] = asdict(result)
        
        # Keep only last 50 results to prevent file bloat
        if len(results_data) > 50:
            sorted_keys = sorted(results_data.keys())
            for old_key in sorted_keys[:-50]:
                del results_data[old_key]
        
        # Save updated results
        with open(self.results_path, 'w', encoding='utf-8') as f:
            json.dump(results_data, f, indent=2)
    
    def get_compliance_status(self, file_path: str) -> Dict[str, Any]:
        """Get current compliance status for a file."""
        if not self.results_path.exists():
            return {'status': 'UNKNOWN', 'message': 'No scan results available'}
        
        try:
            with open(self.results_path, 'r', encoding='utf-8') as f:
                results_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return {'status': 'ERROR', 'message': 'Unable to read scan results'}
        
        # Find most recent result for this file
        file_results = []
        for timestamp, result in results_data.items():
            if result['file_path'] == file_path:
                file_results.append((timestamp, result))
        
        if not file_results:
            return {'status': 'UNKNOWN', 'message': 'No scan results for this file'}
        
        # Get most recent result
        file_results.sort(reverse=True)
        latest_timestamp, latest_result = file_results[0]
        
        return {
            'status': latest_result['compliance_status'],
            'violations': latest_result['violations_found'],
            'last_scan': latest_timestamp,
            'recommendations': latest_result['recommendations']
        }
    
    def scan_multiple_files(self, file_patterns: List[str]) -> Dict[str, EmDashScanResult]:
        """Scan multiple files matching patterns."""
        results = {}
        
        for pattern in file_patterns:
            # Handle glob patterns
            if '*' in pattern:
                files = list(self.project_path.glob(pattern))
            else:
                files = [Path(pattern)]
            
            for file_path in files:
                if file_path.is_file() and file_path.suffix in ['.md', '.txt', '.rst']:
                    result = self.scan_file(str(file_path))
                    results[str(file_path)] = result
        
        return results
    
    def generate_compliance_report(self, scan_results: Dict[str, EmDashScanResult]) -> str:
        """Generate comprehensive compliance report."""
        if not scan_results:
            return "No files scanned for em-dash compliance."
        
        total_files = len(scan_results)
        compliant_files = sum(1 for r in scan_results.values() if r.compliance_status == 'PASS')
        violation_files = sum(1 for r in scan_results.values() if r.compliance_status == 'FAIL')
        total_violations = sum(r.violations_found for r in scan_results.values())
        
        report = f"""# Em-Dash Compliance Report
Generated: {datetime.now().isoformat()}

## Summary
- Files Scanned: {total_files}
- Compliant Files: {compliant_files} ({compliant_files/total_files:.1%})
- Violation Files: {violation_files} ({violation_files/total_files:.1%})
- Total Violations: {total_violations}

## Compliance Status
"""
        
        if violation_files == 0:
            report += "✅ **EXCELLENT**: All files pass em-dash compliance check\n"
        elif violation_files <= total_files * 0.2:
            report += "✅ **GOOD**: Most files comply with em-dash standards\n"
        elif violation_files <= total_files * 0.5:
            report += "⚠️ **NEEDS ATTENTION**: Several files have em-dash violations\n"
        else:
            report += "❌ **CRITICAL**: Majority of files violate em-dash standards\n"
        
        report += "\n## File-by-File Analysis\n"
        
        for file_path, result in sorted(scan_results.items()):
            status = "✅" if result.compliance_status == 'PASS' else "❌"
            report += f"""
### {status} {file_path}
- Status: {result.compliance_status}
- Violations: {result.violations_found}
- Lines Scanned: {result.total_lines}
"""
            
            if result.violations:
                report += "Violations found:\n"
                for violation in result.violations[:5]:  # Show first 5 violations
                    report += f"  - Line {violation.line_number}: {violation.violation_type} → {violation.replacement_suggestion}\n"
                
                if len(result.violations) > 5:
                    report += f"  ... and {len(result.violations) - 5} more violations\n"
        
        return report
    
    def quick_check(self, text: str) -> bool:
        """Quick boolean check for em-dash compliance."""
        for pattern in self.EM_DASH_PATTERNS:
            if re.search(pattern, text):
                # Found em-dash, check if it's in quotes
                quoted_segments = self._find_quoted_segments(text)
                quoted_positions = set()
                for start, end in quoted_segments:
                    quoted_positions.update(range(start, end))
                
                for match in re.finditer(pattern, text):
                    if not self._is_in_quoted_text(match.start(), quoted_positions):
                        return False  # Found em-dash outside quotes
        
        return True  # No violations found

# CLI Interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Em-Dash Sentinel - Zero-tolerance em-dash compliance checker")
    parser.add_argument("action", choices=["scan", "check", "report", "status"], 
                       help="Action to perform")
    parser.add_argument("--file", help="File to scan")
    parser.add_argument("--pattern", nargs='+', help="File patterns to scan")
    parser.add_argument("--text", help="Text to check directly")
    parser.add_argument("--output", help="Output file for report")
    
    args = parser.parse_args()
    
    sentinel = EmDashSentinel()
    
    if args.action == "scan" and args.file:
        result = sentinel.scan_file(args.file)
        
        print(f"Em-Dash Scan Results: {args.file}")
        print(f"Status: {result.compliance_status}")
        print(f"Violations: {result.violations_found}")
        print(f"Lines Scanned: {result.total_lines}")
        
        if result.violations:
            print(f"\nViolations Found:")
            for violation in result.violations:
                print(f"  Line {violation.line_number}: {violation.violation_type}")
                print(f"    Context: {violation.context}")
                print(f"    Suggestion: {violation.replacement_suggestion}")
                print()
        
        if result.recommendations:
            print("Recommendations:")
            for rec in result.recommendations:
                print(f"  {rec}")
    
    elif args.action == "check" and args.text:
        compliant = sentinel.quick_check(args.text)
        print(f"Em-dash compliance: {'✅ PASS' if compliant else '❌ FAIL'}")
    
    elif args.action == "report" and args.pattern:
        scan_results = sentinel.scan_multiple_files(args.pattern)
        report = sentinel.generate_compliance_report(scan_results)
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"Compliance report saved to {args.output}")
        else:
            print(report)
    
    elif args.action == "status" and args.file:
        status = sentinel.get_compliance_status(args.file)
        print(f"Compliance Status for {args.file}:")
        for key, value in status.items():
            print(f"  {key.replace('_', ' ').title()}: {value}")
    
    else:
        print("Please provide required arguments for the specified action")
        parser.print_help() 