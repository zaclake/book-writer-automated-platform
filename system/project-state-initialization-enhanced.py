#!/usr/bin/env python3
"""
Enhanced Project State Initialization
Ensures 'Initialize my book project' command recreates .project-state/ directory after project clearing.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

# Import the base project initialization
import importlib.util
spec = importlib.util.spec_from_file_location(
    "project_initialization", 
    Path(__file__).parent / "project-initialization.py"
)
init_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(init_module)
ProjectInitializer = init_module.ProjectInitializer

class EnhancedProjectStateInitializer:
    """Enhanced project state initialization with post-clearing recovery."""
    
    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.state_dir = self.project_path / ".project-state"
        self.base_initializer = ProjectInitializer(project_path)
        
        # Initialization tracking
        self.init_log_path = self.state_dir / "initialization-log.json"
        
        # Post-clearing detection patterns
        self.clearing_indicators = [
            "project cleared",
            "project cleared and backed up",
            "current project cleared",
            "workspace cleared"
        ]
    
    def initialize_book_project(self, force_recreate: bool = False) -> Dict[str, Any]:
        """Enhanced 'Initialize my book project' implementation."""
        
        result = {
            'initialization_status': 'unknown',
            'state_directory_created': False,
            'files_created': [],
            'files_updated': [],
            'post_clearing_recovery': False,
            'errors': [],
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            # Check if this is a post-clearing scenario
            is_post_clearing = self._detect_post_clearing_scenario()
            result['post_clearing_recovery'] = is_post_clearing
            
            # Determine initialization approach
            if not self.state_dir.exists() or force_recreate or is_post_clearing:
                # Full initialization needed
                init_result = self._perform_full_initialization()
                result.update(init_result)
                result['initialization_status'] = 'full_initialization'
                
            elif self._is_state_incomplete():
                # Partial repair needed
                repair_result = self._perform_state_repair()
                result.update(repair_result)
                result['initialization_status'] = 'repair_performed'
                
            else:
                # State appears complete, verify integrity
                verify_result = self._verify_state_integrity()
                result.update(verify_result)
                result['initialization_status'] = 'verification_only'
            
            # Log the initialization
            self._log_initialization(result)
            
            # Update user manual integration if needed
            self._ensure_user_manual_integration()
            
        except Exception as e:
            result['errors'].append(f"Initialization failed: {str(e)}")
            result['initialization_status'] = 'failed'
        
        return result
    
    def _detect_post_clearing_scenario(self) -> bool:
        """Detect if this is a post-project-clearing scenario."""
        
        # Check for backup directories (indicates recent clearing)
        backup_dirs = list(self.project_path.glob("*backup*"))
        if backup_dirs:
            # Check if backup is recent (within last hour)
            for backup_dir in backup_dirs:
                if backup_dir.is_dir():
                    backup_time = backup_dir.stat().st_mtime
                    current_time = datetime.now().timestamp()
                    if (current_time - backup_time) < 3600:  # 1 hour
                        return True
        
        # Check for clearing indicators in recent logs
        potential_log_files = [
            self.project_path / "notes" / "initialization-summary.md",
            self.project_path / "session-log.txt",
            self.project_path / "project-log.txt"
        ]
        
        for log_file in potential_log_files:
            if log_file.exists():
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        content = f.read().lower()
                        if any(indicator in content for indicator in self.clearing_indicators):
                            return True
                except (IOError, UnicodeDecodeError):
                    continue
        
        # Check if state directory is missing but other project files exist
        if (not self.state_dir.exists() and 
            (self.project_path / "book-bible.md").exists() and
            (self.project_path / "chapters").exists()):
            return True
        
        return False
    
    def _is_state_incomplete(self) -> bool:
        """Check if state directory exists but is incomplete."""
        
        if not self.state_dir.exists():
            return True
        
        required_files = [
            "pattern-database.json",
            "quality-baselines.json", 
            "chapter-progress.json",
            "session-history.json"
        ]
        
        for file_name in required_files:
            file_path = self.state_dir / file_name
            if not file_path.exists():
                return True
            
            # Check if file is empty or invalid JSON
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content:
                        return True
                    json.loads(content)  # Validate JSON
            except (IOError, json.JSONDecodeError):
                return True
        
        return False
    
    def _perform_full_initialization(self) -> Dict[str, Any]:
        """Perform full project state initialization."""
        
        result = {
            'state_directory_created': False,
            'files_created': [],
            'files_updated': [],
            'errors': []
        }
        
        # Use base initializer for core functionality
        base_success = self.base_initializer.initialize_project_state()
        
        if base_success:
            result['state_directory_created'] = True
            result['files_created'] = [
                "pattern-database.json",
                "quality-baselines.json", 
                "chapter-progress.json",
                "session-history.json"
            ]
            
            # Add enhanced state files specific to enhanced system
            enhanced_files = self._create_enhanced_state_files()
            result['files_created'].extend(enhanced_files)
            
        else:
            result['errors'].append("Base project initialization failed")
        
        return result
    
    def _perform_state_repair(self) -> Dict[str, Any]:
        """Repair incomplete state directory."""
        
        result = {
            'state_directory_created': False,
            'files_created': [],
            'files_updated': [],
            'errors': []
        }
        
        # Ensure state directory exists
        if not self.state_dir.exists():
            self.state_dir.mkdir(exist_ok=True)
            result['state_directory_created'] = True
        
        # Repair missing or corrupted files
        repair_success = self.base_initializer.repair_state_files()
        
        if repair_success:
            # Files were repaired, list what would have been fixed
            verification = self.base_initializer.verify_state_integrity()
            for filename, is_valid in verification.items():
                if is_valid:  # Now valid after repair
                    result['files_updated'].append(filename)
        
        # Add enhanced state files
        enhanced_files = self._create_enhanced_state_files()
        result['files_created'].extend(enhanced_files)
        
        return result
    
    def _verify_state_integrity(self) -> Dict[str, Any]:
        """Verify the integrity of existing state."""
        
        result = {
            'state_directory_created': False,
            'files_created': [],
            'files_updated': [],
            'errors': []
        }
        
        # Use base verifier
        verification = self.base_initializer.verify_state_integrity()
        
        if not all(verification.values()):
            # Some files are invalid, attempt repair
            repair_result = self._perform_state_repair()
            result.update(repair_result)
        
        return result
    
    def _create_enhanced_state_files(self) -> List[str]:
        """Create enhanced state files for the improved system."""
        
        enhanced_files = []
        
        # Create engagement scores file if it doesn't exist
        engagement_file = self.state_dir / "engagement-scores.json"
        if not engagement_file.exists():
            with open(engagement_file, 'w', encoding='utf-8') as f:
                json.dump({}, f, indent=2)
            enhanced_files.append("engagement-scores.json")
        
        # Create research verification log if it doesn't exist
        research_file = self.state_dir / "research-verification-log.json"
        if not research_file.exists():
            with open(research_file, 'w', encoding='utf-8') as f:
                json.dump([], f, indent=2)
            enhanced_files.append("research-verification-log.json")
        
        # Create series balance enforcement log if it doesn't exist
        series_file = self.state_dir / "series-balance-enforcement.json"
        if not series_file.exists():
            with open(series_file, 'w', encoding='utf-8') as f:
                json.dump([], f, indent=2)
            enhanced_files.append("series-balance-enforcement.json")
        
        # Create link fixes log if it doesn't exist
        links_file = self.state_dir / "link-fixes-log.json"
        if not links_file.exists():
            with open(links_file, 'w', encoding='utf-8') as f:
                json.dump([], f, indent=2)
            enhanced_files.append("link-fixes-log.json")
        
        return enhanced_files
    
    def _log_initialization(self, result: Dict[str, Any]):
        """Log the initialization result for tracking."""
        
        # Ensure state directory exists
        if not self.state_dir.exists():
            return
        
        log_entry = {
            'timestamp': result['timestamp'],
            'initialization_status': result['initialization_status'],
            'post_clearing_recovery': result['post_clearing_recovery'],
            'files_created_count': len(result['files_created']),
            'files_updated_count': len(result['files_updated']),
            'error_count': len(result['errors']),
            'success': result['initialization_status'] not in ['failed', 'unknown']
        }
        
        log_data = []
        
        # Load existing log
        if self.init_log_path.exists():
            try:
                with open(self.init_log_path, 'r', encoding='utf-8') as f:
                    log_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        
        # Add new entry
        log_data.append(log_entry)
        
        # Keep only last 50 entries
        log_data = log_data[-50:]
        
        # Save updated log
        try:
            with open(self.init_log_path, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, indent=2)
        except IOError:
            pass  # Don't fail initialization due to logging issues
    
    def _ensure_user_manual_integration(self):
        """Ensure user manual properly documents the enhanced initialization."""
        
        user_manual_path = self.project_path / "user-manual.md"
        
        if not user_manual_path.exists():
            return
        
        try:
            with open(user_manual_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check if enhanced initialization is documented
            if "post-clearing recovery" not in content.lower():
                # Add documentation note
                enhanced_section = """

## Enhanced Project State Initialization

The "Initialize my book project" command now includes:

- **Post-clearing recovery**: Automatically detects and recovers from project clearing
- **State integrity verification**: Ensures all state files are valid and complete
- **Enhanced state files**: Creates additional tracking files for improved functionality
- **Repair capabilities**: Fixes corrupted or missing state files automatically

State files created:
- `.project-state/pattern-database.json` - Writing pattern tracking
- `.project-state/quality-baselines.json` - Quality standard tracking  
- `.project-state/chapter-progress.json` - Chapter completion tracking
- `.project-state/session-history.json` - Writing session history
- `.project-state/engagement-scores.json` - Reader engagement analysis
- `.project-state/research-verification-log.json` - Research verification tracking
- `.project-state/series-balance-enforcement.json` - Series balance compliance
- `.project-state/link-fixes-log.json` - Link integrity maintenance
"""
                
                # Insert after existing project state section
                if ".project-state/" in content:
                    insert_point = content.find(".project-state/")
                    # Find end of that section
                    next_section = content.find("\n## ", insert_point)
                    if next_section != -1:
                        content = content[:next_section] + enhanced_section + content[next_section:]
                    else:
                        content += enhanced_section
                else:
                    content += enhanced_section
                
                # Save updated user manual
                with open(user_manual_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                    
        except (IOError, UnicodeDecodeError):
            pass  # Don't fail initialization due to documentation issues
    
    def get_initialization_statistics(self) -> Dict[str, Any]:
        """Get statistics about project initialization history."""
        
        if not self.init_log_path.exists():
            return {'status': 'no_data', 'total_initializations': 0}
        
        try:
            with open(self.init_log_path, 'r', encoding='utf-8') as f:
                log_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return {'status': 'error', 'message': 'Unable to load initialization log'}
        
        if not log_data:
            return {'status': 'no_data', 'total_initializations': 0}
        
        # Calculate statistics
        total_inits = len(log_data)
        successful_inits = sum(1 for entry in log_data if entry.get('success', False))
        post_clearing_recoveries = sum(1 for entry in log_data if entry.get('post_clearing_recovery', False))
        
        # Count by status
        status_counts = {}
        for entry in log_data:
            status = entry.get('initialization_status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            'status': 'success',
            'total_initializations': total_inits,
            'successful_initializations': successful_inits,
            'success_rate': successful_inits / total_inits if total_inits > 0 else 0,
            'post_clearing_recoveries': post_clearing_recoveries,
            'status_distribution': status_counts,
            'latest_initialization': log_data[-1]['timestamp'] if log_data else None
        }
    
    def run_initialization_test(self) -> Dict[str, Any]:
        """Test the enhanced initialization system."""
        
        try:
            # Test 1: Normal initialization
            result1 = self.initialize_book_project()
            
            # Test 2: Force recreation
            result2 = self.initialize_book_project(force_recreate=True)
            
            # Test 3: Verify state exists
            state_exists = self.state_dir.exists()
            required_files_exist = all(
                (self.state_dir / file).exists() 
                for file in ["pattern-database.json", "quality-baselines.json", 
                           "chapter-progress.json", "session-history.json"]
            )
            
            return {
                'status': 'success',
                'normal_init_successful': result1['initialization_status'] != 'failed',
                'force_recreate_successful': result2['initialization_status'] != 'failed',
                'state_directory_exists': state_exists,
                'required_files_exist': required_files_exist,
                'test_passed': all([
                    result1['initialization_status'] != 'failed',
                    result2['initialization_status'] != 'failed',
                    state_exists,
                    required_files_exist
                ])
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
    
    parser = argparse.ArgumentParser(description="Enhanced Project State Initializer")
    parser.add_argument("action", choices=["init", "stats", "test"], 
                       help="Action to perform")
    parser.add_argument("--force", action="store_true", 
                       help="Force recreation of state directory")
    
    args = parser.parse_args()
    
    initializer = EnhancedProjectStateInitializer()
    
    if args.action == "init":
        print("🚀 Initializing book project...")
        result = initializer.initialize_book_project(force_recreate=args.force)
        
        print(f"✅ Initialization completed")
        print(f"Status: {result['initialization_status']}")
        print(f"State Directory Created: {'YES' if result['state_directory_created'] else 'NO'}")
        print(f"Post-Clearing Recovery: {'YES' if result['post_clearing_recovery'] else 'NO'}")
        
        if result['files_created']:
            print(f"\nFiles Created ({len(result['files_created'])}):")
            for file_name in result['files_created']:
                print(f"  📄 {file_name}")
        
        if result['files_updated']:
            print(f"\nFiles Updated ({len(result['files_updated'])}):")
            for file_name in result['files_updated']:
                print(f"  📝 {file_name}")
        
        if result['errors']:
            print(f"\n❌ Errors:")
            for error in result['errors']:
                print(f"  {error}")
    
    elif args.action == "stats":
        stats = initializer.get_initialization_statistics()
        
        if stats['status'] == 'no_data':
            print("No initialization statistics available.")
        elif stats['status'] == 'error':
            print(f"Error: {stats['message']}")
        else:
            print("📊 Project Initialization Statistics")
            print("=" * 45)
            print(f"Total Initializations: {stats['total_initializations']}")
            print(f"Successful Initializations: {stats['successful_initializations']}")
            print(f"Success Rate: {stats['success_rate']:.1%}")
            print(f"Post-Clearing Recoveries: {stats['post_clearing_recoveries']}")
            
            if stats['status_distribution']:
                print(f"\nInitialization Types:")
                for status, count in stats['status_distribution'].items():
                    print(f"  {status.replace('_', ' ').title()}: {count}")
            
            if stats['latest_initialization']:
                print(f"\nLatest: {stats['latest_initialization']}")
    
    elif args.action == "test":
        results = initializer.run_initialization_test()
        
        print("🧪 Enhanced Project State Initialization Test")
        print("=" * 50)
        print(f"Status: {results['status']}")
        print(f"Test Passed: {'✅ YES' if results['test_passed'] else '❌ NO'}")
        
        if results['status'] == 'success':
            print(f"Normal Initialization: {'✅' if results['normal_init_successful'] else '❌'}")
            print(f"Force Recreate: {'✅' if results['force_recreate_successful'] else '❌'}")
            print(f"State Directory Exists: {'✅' if results['state_directory_exists'] else '❌'}")
            print(f"Required Files Exist: {'✅' if results['required_files_exist'] else '❌'}")
        else:
            print(f"Error: {results.get('error', 'Unknown error')}")
    
    else:
        print("Please specify an action")
        parser.print_help() 