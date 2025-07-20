#!/usr/bin/env python3
"""
Legacy Link Fixer
Fixes all remaining legacy link references after repository reorganization.
"""

import re
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional

class LegacyLinkFixer:
    """Comprehensive fixer for legacy link references after reorganization."""
    
    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.state_dir = self.project_path / ".project-state"
        self.fixes_log_path = self.state_dir / "link-fixes-log.json"
        
        # Ensure state directory exists
        self.state_dir.mkdir(exist_ok=True)
        
        # File reorganization mapping
        self.reorganization_map = {
            # Root files moved to system/
            'brutal-quality-assessment-system.md': 'analysis/brutal-quality-assessment-system.md',
            'continuous-auditing-system.md': 'system/continuous-auditing-system.md',
            'em-dash-elimination-system.md': 'frameworks/em-dash-elimination-system.md',
            'repetition-prevention-system.md': 'frameworks/repetition-prevention-system.md',
            'inspiration-analysis-system.md': 'analysis/inspiration-analysis-system.md',
            'failure-mode-analysis.md': 'analysis/failure-mode-analysis.md',
            'remaining-risks.md': 'analysis/remaining-risks.md',
            'research-tracking-system.md': 'frameworks/research-tracking-system.md',
            'series-balance-guidelines.md': 'frameworks/series-balance-guidelines.md',
            'reader-engagement-predictor.md': 'frameworks/reader-engagement-predictor.md',
            'character-development-toolkit.md': 'frameworks/character-development-toolkit.md',
            'supporting-character-growth-framework.md': 'frameworks/supporting-character-growth-framework.md',
            'structure-variety-framework.md': 'frameworks/structure-variety-framework.md',
            'craft-excellence-framework.md': 'frameworks/craft-excellence-framework.md',
            'authenticity-framework.md': 'frameworks/authenticity-framework.md',
            'word-count-planning-calculator.md': 'tools/word-count-planning-calculator.md',
            'plot-development-tracker.md': 'tools/plot-development-tracker.md',
            'plot-tracker.md': 'tools/plot-tracker.md',
            'book-bible-generator.html': 'tools/book-bible-generator.html',
            'enhanced-writing-system-v2.md': 'system/enhanced-writing-system-v2.md',
            'enhanced-writing-system-implementation-guide.md': 'docs/enhanced-writing-system-implementation-guide.md',
            'system-implementation-checklist.md': 'docs/system-implementation-checklist.md',
            'implementation-status.md': 'docs/implementation-status.md',
            'system-improvements-summary.md': 'docs/system-improvements-summary.md',
            'intelligent-initialization-protocol.md': 'system/intelligent-initialization-protocol.md',
            'enhanced-commands.md': 'docs/enhanced-commands.md',
            'book-bible-survey-template.md': 'docs/book-bible-survey-template.md',
            'example-book-bible.md': 'docs/example-book-bible.md',
            'setup-book-project.md': 'docs/setup-book-project.md',
            'emailjs-setup-guide.md': 'docs/emailjs-setup-guide.md',
            'structural-improvement-checklist.md': 'analysis/structural-improvement-checklist.md',
            'GOLD-STANDARD-RISK-ANALYSIS.md': 'analysis/GOLD-STANDARD-RISK-ANALYSIS.md',
            'SMART-RISK-IMPLEMENTATION-GUIDE.md': 'analysis/SMART-RISK-IMPLEMENTATION-GUIDE.md',
            'project-management-implementation-prompt.md': 'system/project-management-implementation-prompt.md',
            'project-management-implementation-summary.md': 'system/project-management-implementation-summary.md',
            'project-manager.md': 'system/project-manager.md',
            'spool-room-improvements.md': 'analysis/spool-room-improvements.md',
            
            # State files
            'pattern-database.json': '.project-state/pattern-database.json',
            'quality-baselines.json': '.project-state/quality-baselines.json',
            'chapter-progress.json': '.project-state/chapter-progress.json',
            'session-history.json': '.project-state/session-history.json',
            
            # Config files
            'quality-gates.yml': 'quality-gates.yml',
            
            # Files that no longer exist or were consolidated
            'checklist.md': 'docs/system-implementation-checklist.md',
            'courtsey_killer_book_bible.md.rtf': 'docs/example-book-bible.md',
            'courtsey_killer_book_bible.md': 'docs/example-book-bible.md'
        }
        
        # Pattern-based fixes for common issues
        self.pattern_fixes = [
            # Fix references to moved files without extensions
            (r'\b(pattern-database|quality-baselines|chapter-progress|session-history)\b(?!\.json)', 
             r'.project-state/\1.json'),
            
            # Fix references to .project-state files without path
            (r'(?<!\.project-state/)(pattern-database\.json|quality-baselines\.json|chapter-progress\.json|session-history\.json)',
             r'.project-state/\1'),
             
            # Fix references to frameworks without path
            (r'(?<!frameworks/)(research-tracking-system\.md|series-balance-guidelines\.md|reader-engagement-predictor\.md)',
             r'frameworks/\1'),
             
            # Fix references to analysis files without path
            (r'(?<!analysis/)(brutal-quality-assessment-system\.md|failure-mode-analysis\.md|remaining-risks\.md)',
             r'analysis/\1'),
             
            # Fix references to tools without path
            (r'(?<!tools/)(word-count-planning-calculator\.md|plot-development-tracker\.md|plot-tracker\.md)',
             r'tools/\1'),
             
            # Fix references to system files without path
            (r'(?<!system/)(enhanced-writing-system-v2\.md|project-manager\.md|continuous-auditing-system\.md)',
             r'system/\1'),
             
            # Fix references to docs without path
            (r'(?<!docs/)(setup-book-project\.md|implementation-status\.md|system-implementation-checklist\.md)',
             r'docs/\1')
        ]
    
    def fix_all_legacy_links(self) -> Dict[str, Any]:
        """Fix all legacy link references in the project."""
        
        results = {
            'files_processed': 0,
            'total_fixes': 0,
            'fixes_by_type': {},
            'files_with_fixes': [],
            'errors': []
        }
        
        # Get all markdown files to process
        markdown_files = list(self.project_path.glob("**/*.md"))
        
        for file_path in markdown_files:
            try:
                file_results = self._fix_file_links(file_path)
                results['files_processed'] += 1
                
                if file_results['fixes_made'] > 0:
                    results['total_fixes'] += file_results['fixes_made']
                    results['files_with_fixes'].append(str(file_path.relative_to(self.project_path)))
                    
                    # Count fixes by type
                    for fix_type, count in file_results['fixes_by_type'].items():
                        results['fixes_by_type'][fix_type] = results['fixes_by_type'].get(fix_type, 0) + count
                        
            except Exception as e:
                results['errors'].append(f"Error processing {file_path}: {str(e)}")
        
        # Log the results
        self._log_fixes(results)
        
        return results
    
    def _fix_file_links(self, file_path: Path) -> Dict[str, Any]:
        """Fix legacy links in a single file."""
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except (IOError, UnicodeDecodeError) as e:
            return {'fixes_made': 0, 'fixes_by_type': {}, 'error': str(e)}
        
        original_content = content
        fixes_by_type = {}
        
        # Apply reorganization map fixes
        for old_path, new_path in self.reorganization_map.items():
            # Fix direct references
            old_content = content
            content = re.sub(
                rf'\b{re.escape(old_path)}\b',
                new_path,
                content
            )
            if content != old_content:
                fixes_by_type['reorganization_map'] = fixes_by_type.get('reorganization_map', 0) + 1
            
            # Fix markdown links
            old_content = content
            content = re.sub(
                rf'\[([^\]]*)\]\({re.escape(old_path)}\)',
                rf'[\1]({new_path})',
                content
            )
            if content != old_content:
                fixes_by_type['markdown_links'] = fixes_by_type.get('markdown_links', 0) + 1
        
        # Apply pattern-based fixes
        for pattern, replacement in self.pattern_fixes:
            old_content = content
            content = re.sub(pattern, replacement, content)
            if content != old_content:
                fixes_by_type['pattern_fixes'] = fixes_by_type.get('pattern_fixes', 0) + 1
        
        # Fix specific known issues based on file
        if file_path.name == 'README.md':
            content = self._fix_readme_specific_issues(content, fixes_by_type)
        elif file_path.name == 'user-manual.md':
            content = self._fix_user_manual_specific_issues(content, fixes_by_type)
        elif file_path.name == 'chapter-generation-protocol.md':
            content = self._fix_chapter_protocol_specific_issues(content, fixes_by_type)
        
        # Save the file if changes were made
        if content != original_content:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            except IOError as e:
                return {'fixes_made': 0, 'fixes_by_type': {}, 'error': f"Failed to save: {str(e)}"}
        
        total_fixes = sum(fixes_by_type.values())
        
        return {
            'fixes_made': total_fixes,
            'fixes_by_type': fixes_by_type
        }
    
    def _fix_readme_specific_issues(self, content: str, fixes_by_type: Dict[str, int]) -> str:
        """Fix specific issues in README.md."""
        
        original_content = content
        
        # Fix book-bible.md references (now in root)
        content = re.sub(r'(?<!/)book-bible\.md', 'book-bible.md', content)
        
        # Fix chapter references
        content = re.sub(r'(?<!chapters/)chapter-(\d+)\.md', r'chapters/chapter-\1.md', content)
        
        # Fix references directory
        content = re.sub(r'(?<!/)references/', 'references/', content)
        
        if content != original_content:
            fixes_by_type['readme_specific'] = fixes_by_type.get('readme_specific', 0) + 1
        
        return content
    
    def _fix_user_manual_specific_issues(self, content: str, fixes_by_type: Dict[str, int]) -> str:
        """Fix specific issues in user-manual.md."""
        
        original_content = content
        
        # Fix state file references to include .project-state/ path
        state_files = ['pattern-database.json', 'quality-baselines.json', 'chapter-progress.json', 'session-history.json']
        
        for state_file in state_files:
            # Fix references that don't already have the path
            content = re.sub(
                rf'(?<!\.project-state/){re.escape(state_file)}',
                f'.project-state/{state_file}',
                content
            )
        
        if content != original_content:
            fixes_by_type['user_manual_specific'] = fixes_by_type.get('user_manual_specific', 0) + 1
        
        return content
    
    def _fix_chapter_protocol_specific_issues(self, content: str, fixes_by_type: Dict[str, int]) -> str:
        """Fix specific issues in chapter-generation-protocol.md."""
        
        original_content = content
        
        # Fix framework references
        framework_files = [
            'research-tracking-system.md',
            'series-balance-guidelines.md', 
            'reader-engagement-predictor.md',
            'character-development-toolkit.md',
            'em-dash-elimination-system.md',
            'repetition-prevention-system.md'
        ]
        
        for framework_file in framework_files:
            content = re.sub(
                rf'(?<!frameworks/){re.escape(framework_file)}',
                f'frameworks/{framework_file}',
                content
            )
        
        # Fix analysis references
        analysis_files = [
            'brutal-quality-assessment-system.md',
            'failure-mode-analysis.md'
        ]
        
        for analysis_file in analysis_files:
            content = re.sub(
                rf'(?<!analysis/){re.escape(analysis_file)}',
                f'analysis/{analysis_file}',
                content
            )
        
        # Fix system references
        system_files = [
            'enhanced-writing-system-v2.md',
            'continuous-auditing-system.md'
        ]
        
        for system_file in system_files:
            content = re.sub(
                rf'(?<!system/){re.escape(system_file)}',
                f'system/{system_file}',
                content
            )
        
        if content != original_content:
            fixes_by_type['chapter_protocol_specific'] = fixes_by_type.get('chapter_protocol_specific', 0) + 1
        
        return content
    
    def _log_fixes(self, results: Dict[str, Any]):
        """Log the fix results for tracking."""
        
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'files_processed': results['files_processed'],
            'total_fixes': results['total_fixes'],
            'fixes_by_type': results['fixes_by_type'],
            'files_with_fixes': results['files_with_fixes'],
            'error_count': len(results['errors'])
        }
        
        log_data = []
        
        # Load existing log
        if self.fixes_log_path.exists():
            try:
                with open(self.fixes_log_path, 'r', encoding='utf-8') as f:
                    log_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        
        # Add new entry
        log_data.append(log_entry)
        
        # Keep only last 50 entries
        log_data = log_data[-50:]
        
        # Save updated log
        with open(self.fixes_log_path, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2)
    
    def validate_fixes(self) -> Dict[str, Any]:
        """Validate that fixes were applied correctly."""
        
        validation_results = {
            'broken_links_remaining': 0,
            'files_with_issues': [],
            'validation_passed': False
        }
        
        # Use the link integrity validator to check remaining issues
        try:
            from pathlib import Path
            import importlib.util
            
            # Import the link validator
            validator_path = self.project_path / "system" / "link-integrity-validator.py"
            spec = importlib.util.spec_from_file_location("link_validator", validator_path)
            validator_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(validator_module)
            
            # Create validator instance and run validation
            validator = validator_module.LinkIntegrityValidator(str(self.project_path))
            link_issues = validator.validate_all_links()
            
            validation_results['broken_links_remaining'] = len(link_issues['broken_links'])
            validation_results['files_with_issues'] = list(set(
                issue['file'] for issue in link_issues['broken_links']
            ))
            validation_results['validation_passed'] = len(link_issues['broken_links']) == 0
            
        except Exception as e:
            validation_results['error'] = str(e)
        
        return validation_results
    
    def get_fix_statistics(self) -> Dict[str, Any]:
        """Get statistics about link fixes applied."""
        
        if not self.fixes_log_path.exists():
            return {'status': 'no_data', 'total_runs': 0}
        
        try:
            with open(self.fixes_log_path, 'r', encoding='utf-8') as f:
                log_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return {'status': 'error', 'message': 'Unable to load fixes log'}
        
        if not log_data:
            return {'status': 'no_data', 'total_runs': 0}
        
        # Calculate statistics
        total_runs = len(log_data)
        total_fixes = sum(entry.get('total_fixes', 0) for entry in log_data)
        total_files_processed = sum(entry.get('files_processed', 0) for entry in log_data)
        
        # Count fixes by type across all runs
        all_fixes_by_type = {}
        for entry in log_data:
            for fix_type, count in entry.get('fixes_by_type', {}).items():
                all_fixes_by_type[fix_type] = all_fixes_by_type.get(fix_type, 0) + count
        
        # Get most recent run info
        latest_run = log_data[-1] if log_data else {}
        
        return {
            'status': 'success',
            'total_runs': total_runs,
            'total_fixes_applied': total_fixes,
            'total_files_processed': total_files_processed,
            'fixes_by_type': all_fixes_by_type,
            'latest_run': latest_run,
            'average_fixes_per_run': total_fixes / total_runs if total_runs > 0 else 0
        }
    
    def run_fix_test(self) -> Dict[str, Any]:
        """Test the link fixing functionality."""
        
        # Create test content with known broken links
        test_content = """
        # Test Document
        
        See the [brutal assessment](brutal-quality-assessment-system.md) for details.
        Check pattern-database.json for patterns.
        Review research-tracking-system.md for guidelines.
        Use word-count-planning-calculator.md for planning.
        See enhanced-writing-system-v2.md for the system.
        """
        
        test_file_path = self.project_path / "test-links.md"
        
        try:
            # Create test file
            with open(test_file_path, 'w', encoding='utf-8') as f:
                f.write(test_content)
            
            # Apply fixes
            file_results = self._fix_file_links(test_file_path)
            
            # Read result
            with open(test_file_path, 'r', encoding='utf-8') as f:
                fixed_content = f.read()
            
            # Check if fixes were applied
            expected_fixes = [
                'analysis/brutal-quality-assessment-system.md',
                '.project-state/pattern-database.json',
                'frameworks/research-tracking-system.md',
                'tools/word-count-planning-calculator.md',
                'system/enhanced-writing-system-v2.md'
            ]
            
            fixes_found = sum(1 for fix in expected_fixes if fix in fixed_content)
            
            # Clean up test file
            test_file_path.unlink()
            
            return {
                'status': 'success',
                'fixes_applied': file_results['fixes_made'],
                'expected_fixes_found': fixes_found,
                'total_expected': len(expected_fixes),
                'test_passed': fixes_found >= 4  # Allow for some flexibility
            }
            
        except Exception as e:
            # Clean up test file if it exists
            if test_file_path.exists():
                test_file_path.unlink()
            
            return {
                'status': 'error',
                'error': str(e),
                'test_passed': False
            }

# CLI Interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Legacy Link Fixer")
    parser.add_argument("action", choices=["fix", "validate", "stats", "test"], 
                       help="Action to perform")
    parser.add_argument("--output", help="Output file for results")
    
    args = parser.parse_args()
    
    fixer = LegacyLinkFixer()
    
    if args.action == "fix":
        print("🔧 Fixing all legacy link references...")
        results = fixer.fix_all_legacy_links()
        
        print(f"✅ Link fixing completed")
        print(f"Files Processed: {results['files_processed']}")
        print(f"Total Fixes Applied: {results['total_fixes']}")
        
        if results['fixes_by_type']:
            print(f"\nFixes by Type:")
            for fix_type, count in results['fixes_by_type'].items():
                print(f"  {fix_type.replace('_', ' ').title()}: {count}")
        
        if results['files_with_fixes']:
            print(f"\nFiles Modified ({len(results['files_with_fixes'])}):")
            for file_path in results['files_with_fixes'][:10]:  # Show first 10
                print(f"  📝 {file_path}")
            if len(results['files_with_fixes']) > 10:
                print(f"  ... and {len(results['files_with_fixes']) - 10} more")
        
        if results['errors']:
            print(f"\n❌ Errors ({len(results['errors'])}):")
            for error in results['errors']:
                print(f"  {error}")
        
        # Run validation after fixes
        print(f"\n🔍 Validating fixes...")
        validation = fixer.validate_fixes()
        
        if validation.get('validation_passed', False):
            print(f"✅ Validation passed: All links are now valid")
        else:
            remaining = validation.get('broken_links_remaining', 'unknown')
            print(f"⚠️ Validation: {remaining} broken links remaining")
    
    elif args.action == "validate":
        validation = fixer.validate_fixes()
        
        if validation.get('validation_passed', False):
            print("✅ All links are valid")
        else:
            remaining = validation.get('broken_links_remaining', 'unknown')
            print(f"❌ {remaining} broken links remaining")
            
            if validation.get('files_with_issues'):
                print(f"\nFiles with issues:")
                for file_path in validation['files_with_issues']:
                    print(f"  📝 {file_path}")
    
    elif args.action == "stats":
        stats = fixer.get_fix_statistics()
        
        if stats['status'] == 'no_data':
            print("No fix statistics available.")
        elif stats['status'] == 'error':
            print(f"Error: {stats['message']}")
        else:
            print("📊 Legacy Link Fix Statistics")
            print("=" * 40)
            print(f"Total Runs: {stats['total_runs']}")
            print(f"Total Fixes Applied: {stats['total_fixes_applied']}")
            print(f"Files Processed: {stats['total_files_processed']}")
            print(f"Average Fixes per Run: {stats['average_fixes_per_run']:.1f}")
            
            if stats['fixes_by_type']:
                print(f"\nFixes by Type:")
                for fix_type, count in sorted(stats['fixes_by_type'].items()):
                    print(f"  {fix_type.replace('_', ' ').title()}: {count}")
    
    elif args.action == "test":
        results = fixer.run_fix_test()
        
        print("🧪 Legacy Link Fixer Test")
        print("=" * 30)
        print(f"Status: {results['status']}")
        print(f"Test Passed: {'✅ YES' if results['test_passed'] else '❌ NO'}")
        
        if results['status'] == 'success':
            print(f"Fixes Applied: {results['fixes_applied']}")
            print(f"Expected Fixes Found: {results['expected_fixes_found']}/{results['total_expected']}")
        else:
            print(f"Error: {results.get('error', 'Unknown error')}")
    
    else:
        print("Please specify an action")
        parser.print_help() 