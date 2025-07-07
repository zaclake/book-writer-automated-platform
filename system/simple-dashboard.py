#!/usr/bin/env python3
"""
Simple Dashboard Provider
Basic dashboard data without complex calculations.
"""

import json
import os
from pathlib import Path
from datetime import datetime

def get_simple_dashboard_data():
    """Get basic dashboard data."""
    
    project_path = Path(".")
    chapters_dir = project_path / "chapters"
    state_dir = project_path / ".project-state"
    
    # Basic chapter counting
    chapters_count = 0
    completed_chapters = 0
    if chapters_dir.exists():
        chapter_files = list(chapters_dir.glob("chapter-*.md"))
        chapters_count = len(chapter_files)
        
        # Count completed chapters (files > 1000 bytes)
        for chapter_file in chapter_files:
            try:
                if chapter_file.stat().st_size > 1000:
                    completed_chapters += 1
            except OSError:
                pass
    
    # Check state files existence
    state_files_exist = []
    if state_dir.exists():
        for file_name in ["pattern-database.json", "quality-baselines.json", "chapter-progress.json"]:
            file_path = state_dir / file_name
            state_files_exist.append(file_path.exists())
    
    system_health = sum(state_files_exist) / len(state_files_exist) * 10 if state_files_exist else 0
    
    return {
        'project_health': {
            'overall_score': round(system_health, 1),
            'status': 'good' if system_health > 6 else 'warning'
        },
        'chapter_progress': {
            'total_chapters': chapters_count,
            'completed_chapters': completed_chapters,
            'completion_percentage': round((completed_chapters / max(1, chapters_count)) * 100, 1)
        },
        'system_status': {
            'state_files_active': sum(state_files_exist),
            'total_state_files': len(state_files_exist),
            'systems_operational': sum(state_files_exist) > 0
        },
        'alerts': [] if system_health > 5 else ['System initialization may be needed'],
        'timestamp': datetime.now().isoformat(),
        'status': 'success'
    }

if __name__ == "__main__":
    data = get_simple_dashboard_data()
    print(json.dumps(data, indent=2)) 