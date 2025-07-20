#!/usr/bin/env python3
"""
Link Integrity Validator
Checks for broken file references in markdown documentation.
"""

import re
import os
from pathlib import Path
from typing import List, Dict, Tuple, Set
from dataclasses import dataclass

@dataclass
class LinkIssue:
    """Represents a broken link or reference issue."""
    file_path: str
    line_number: int
    link_text: str
    issue_type: str
    suggestion: str = None

class LinkIntegrityValidator:
    """Validates file references and links in markdown documentation."""
    
    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.issues: List[LinkIssue] = []
        self.file_map: Dict[str, Path] = {}
        self.markdown_files: List[Path] = []
        
        # Build file map and find markdown files
        self._build_file_map()
        self._find_markdown_files()
    
    def _build_file_map(self):
        """Build a map of all files in the project for reference checking."""
        for file_path in self.project_path.rglob("*"):
            if file_path.is_file() and not self._should_ignore_file(file_path):
                # Map filename to full path
                filename = file_path.name
                relative_path = file_path.relative_to(self.project_path)
                
                # Store both exact filename and relative path
                self.file_map[filename] = relative_path
                self.file_map[str(relative_path)] = relative_path
                
                # Also store without extension for markdown files
                if filename.endswith('.md'):
                    name_without_ext = filename[:-3]
                    self.file_map[name_without_ext] = relative_path
    
    def _find_markdown_files(self):
        """Find all markdown files to check."""
        self.markdown_files = list(self.project_path.rglob("*.md"))
        self.markdown_files = [f for f in self.markdown_files if not self._should_ignore_file(f)]
    
    def _should_ignore_file(self, file_path: Path) -> bool:
        """Check if file should be ignored during validation."""
        ignore_patterns = [
            '.git',
            '.project-state',
            'backups',
            '__pycache__',
            '.DS_Store',
            'node_modules'
        ]
        
        path_str = str(file_path)
        return any(pattern in path_str for pattern in ignore_patterns)
    
    def validate_all_links(self) -> List[LinkIssue]:
        """Validate links in all markdown files."""
        self.issues = []
        
        for md_file in self.markdown_files:
            self._validate_file_links(md_file)
        
        return self.issues
    
    def _validate_file_links(self, file_path: Path):
        """Validate links in a specific markdown file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
        except Exception as e:
            self.issues.append(LinkIssue(
                file_path=str(file_path.relative_to(self.project_path)),
                line_number=0,
                link_text="",
                issue_type="file_read_error",
                suggestion=f"Cannot read file: {e}"
            ))
            return
        
        for line_num, line in enumerate(lines, 1):
            self._check_line_for_issues(file_path, line_num, line)
    
    def _check_line_for_issues(self, file_path: Path, line_num: int, line: str):
        """Check a single line for link issues."""
        # Pattern for markdown file references
        md_patterns = [
            r'`([^`]+\.md)`',  # Backtick references: `file.md`
            r'\[([^\]]+)\]\(([^)]+\.md)\)',  # Markdown links: [text](file.md)
            r'(\w+[-\w]*\.md)',  # Direct references: filename.md
            r'`([^`]+/[^`]+\.md)`',  # Path references: `path/file.md`
        ]
        
        # Pattern for system file references
        system_patterns = [
            r'`([^`]+\.py)`',  # Python files: `script.py`
            r'`([^`]+\.yml)`',  # YAML files: `config.yml`
            r'`([^`]+\.yaml)`',  # YAML files: `config.yaml`
            r'`([^`]+\.json)`',  # JSON files: `data.json`
            r'`([^`]+\.html)`',  # HTML files: `page.html`
        ]
        
        all_patterns = md_patterns + system_patterns
        
        for pattern in all_patterns:
            matches = re.finditer(pattern, line)
            for match in matches:
                if len(match.groups()) == 1:
                    # Single group patterns
                    referenced_file = match.group(1)
                elif len(match.groups()) == 2:
                    # Markdown link patterns [text](file)
                    referenced_file = match.group(2)
                else:
                    continue
                
                self._validate_reference(file_path, line_num, line, referenced_file, match.group(0))
    
    def _validate_reference(self, file_path: Path, line_num: int, line: str, 
                          referenced_file: str, full_match: str):
        """Validate a specific file reference."""
        # Clean up the reference
        referenced_file = referenced_file.strip()
        
        # Skip external URLs
        if referenced_file.startswith(('http://', 'https://', 'ftp://', 'mailto:')):
            return
        
        # Check if file exists
        if not self._file_exists(referenced_file):
            # Try to find a suggestion
            suggestion = self._find_suggestion(referenced_file)
            
            self.issues.append(LinkIssue(
                file_path=str(file_path.relative_to(self.project_path)),
                line_number=line_num,
                link_text=full_match,
                issue_type="broken_reference",
                suggestion=suggestion
            ))
    
    def _file_exists(self, referenced_file: str) -> bool:
        """Check if a referenced file exists."""
        # Direct path check
        full_path = self.project_path / referenced_file
        if full_path.exists():
            return True
        
        # Check in file map
        if referenced_file in self.file_map:
            return True
        
        # Check filename only
        filename = Path(referenced_file).name
        if filename in self.file_map:
            return True
        
        return False
    
    def _find_suggestion(self, referenced_file: str) -> str:
        """Find a suggested correct path for a broken reference."""
        filename = Path(referenced_file).name
        
        # Look for exact filename matches
        if filename in self.file_map:
            correct_path = self.file_map[filename]
            return f"Found at: {correct_path}"
        
        # Look for similar filenames
        filename_lower = filename.lower()
        for mapped_file, path in self.file_map.items():
            if mapped_file.lower() == filename_lower:
                return f"Case mismatch? Found: {path}"
        
        # Look for files with similar names (without extension)
        name_without_ext = Path(referenced_file).stem
        for mapped_file, path in self.file_map.items():
            if Path(mapped_file).stem == name_without_ext:
                return f"Similar file: {path}"
        
        # Look for partial matches
        for mapped_file, path in self.file_map.items():
            if name_without_ext in mapped_file or mapped_file in name_without_ext:
                return f"Possible match: {path}"
        
        return "No similar file found"
    
    def generate_report(self) -> str:
        """Generate a comprehensive report of link issues."""
        if not self.issues:
            return "✅ No link integrity issues found!"
        
        report = f"📋 Link Integrity Report\n"
        report += f"Found {len(self.issues)} issues:\n\n"
        
        # Group issues by type
        issues_by_type = {}
        for issue in self.issues:
            if issue.issue_type not in issues_by_type:
                issues_by_type[issue.issue_type] = []
            issues_by_type[issue.issue_type].append(issue)
        
        for issue_type, issues in issues_by_type.items():
            report += f"## {issue_type.replace('_', ' ').title()} ({len(issues)} issues)\n\n"
            
            for issue in issues:
                report += f"**{issue.file_path}:{issue.line_number}**\n"
                report += f"- Link: `{issue.link_text}`\n"
                if issue.suggestion:
                    report += f"- Suggestion: {issue.suggestion}\n"
                report += "\n"
        
        return report
    
    def fix_common_issues(self) -> Dict[str, int]:
        """Automatically fix common link issues."""
        fixes_applied = {
            'relocated_files': 0,
            'case_corrections': 0,
            'path_updates': 0
        }
        
        # Common file relocations after reorganization
        relocations = {
            'word-count-planning-calculator.md': 'tools/word-count-planning-calculator.md',
            'character-development-toolkit.md': 'frameworks/character-development-toolkit.md',
            'research-tracking-system.md': 'frameworks/research-tracking-system.md',
            'plot-tracker.md': 'tools/plot-tracker.md',
            'series-balance-guidelines.md': 'tools/series-balance-guidelines.md',
            'enhanced-writing-system-v2.md': 'system/enhanced-writing-system-v2.md',
            'brutal-quality-assessment-system.md': 'analysis/brutal-quality-assessment-system.md',
            'project-manager.md': 'system/project-manager.md',
            'intelligent-initialization-protocol.md': 'system/intelligent-initialization-protocol.md'
        }
        
        for md_file in self.markdown_files:
            try:
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                original_content = content
                
                # Apply relocations
                for old_ref, new_ref in relocations.items():
                    # Update various reference patterns
                    patterns = [
                        (f'`{old_ref}`', f'`{new_ref}`'),
                        (f'`{old_ref} ', f'`{new_ref} '),
                        (f']({old_ref})', f']({new_ref})'),
                        (f' {old_ref} ', f' {new_ref} '),
                        (f'**{old_ref}**', f'**{new_ref}**'),
                    ]
                    
                    for old_pattern, new_pattern in patterns:
                        if old_pattern in content:
                            content = content.replace(old_pattern, new_pattern)
                            fixes_applied['relocated_files'] += content.count(new_pattern) - original_content.count(new_pattern)
                
                # Write back if changes were made
                if content != original_content:
                    with open(md_file, 'w', encoding='utf-8') as f:
                        f.write(content)
                        
            except Exception as e:
                print(f"Error processing {md_file}: {e}")
        
        return fixes_applied
    
    def get_statistics(self) -> Dict[str, int]:
        """Get validation statistics."""
        return {
            'total_markdown_files': len(self.markdown_files),
            'total_files_mapped': len(self.file_map),
            'total_issues': len(self.issues),
            'broken_references': len([i for i in self.issues if i.issue_type == 'broken_reference']),
            'file_read_errors': len([i for i in self.issues if i.issue_type == 'file_read_error'])
        }

# CLI Interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Link Integrity Validator")
    parser.add_argument("action", choices=["validate", "report", "fix", "stats"], 
                       help="Action to perform")
    parser.add_argument("--project-path", default=".", 
                       help="Path to project directory")
    parser.add_argument("--output", 
                       help="Output file for report")
    
    args = parser.parse_args()
    
    validator = LinkIntegrityValidator(args.project_path)
    
    if args.action == "validate":
        issues = validator.validate_all_links()
        if issues:
            print(f"❌ Found {len(issues)} link integrity issues")
            for issue in issues[:10]:  # Show first 10
                print(f"  {issue.file_path}:{issue.line_number} - {issue.link_text}")
            if len(issues) > 10:
                print(f"  ... and {len(issues) - 10} more")
            exit(1)
        else:
            print("✅ All links are valid")
    
    elif args.action == "report":
        issues = validator.validate_all_links()
        report = validator.generate_report()
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"Report written to {args.output}")
        else:
            print(report)
    
    elif args.action == "fix":
        print("🔧 Applying automatic fixes...")
        fixes = validator.fix_common_issues()
        
        print("Fixes applied:")
        for fix_type, count in fixes.items():
            print(f"  {fix_type.replace('_', ' ').title()}: {count}")
        
        # Re-validate after fixes
        issues = validator.validate_all_links()
        print(f"\nRemaining issues: {len(issues)}")
    
    elif args.action == "stats":
        validator.validate_all_links()
        stats = validator.get_statistics()
        
        print("Link Integrity Statistics:")
        for key, value in stats.items():
            print(f"  {key.replace('_', ' ').title()}: {value}") 