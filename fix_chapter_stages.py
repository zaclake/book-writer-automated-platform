#!/usr/bin/env python3
"""
Fix existing chapters with invalid stage values.
Updates any chapters with stage='ai_generated' to stage='draft'.
"""

import asyncio
import sys
import os

# Add the backend directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from backend.database_integration import get_database_adapter

async def fix_chapter_stages():
    """Fix all chapters with invalid stage values."""
    
    print("🔧 Starting chapter stage fix...")
    
    try:
        # Get database adapter
        db = get_database_adapter()
        
        if not db.use_firestore:
            print("❌ This script requires Firestore to be enabled")
            return
        
        # Get all projects first
        print("📂 Fetching all projects...")
        # Note: We'll need to implement a way to get all projects
        # For now, let's focus on the specific project from the logs
        project_id = "b036751f-90ba-49e0-9614-3b41642e3954"
        
        print(f"🔍 Checking project: {project_id}")
        
        # Get chapters for this project
        chapters = await db.firestore.get_project_chapters(project_id)
        
        fixed_count = 0
        for chapter in chapters:
            chapter_id = chapter.get('chapter_id')
            chapter_number = chapter.get('chapter_number')
            metadata = chapter.get('metadata', {})
            current_stage = metadata.get('stage')
            
            if current_stage == 'ai_generated':
                print(f"🔧 Fixing chapter {chapter_number} (ID: {chapter_id})")
                
                # Update the metadata
                metadata['stage'] = 'draft'
                chapter['metadata'] = metadata
                
                # Update in database
                await db.firestore.update_chapter(chapter_id, chapter)
                fixed_count += 1
                print(f"✅ Fixed chapter {chapter_number}")
        
        print(f"🎉 Fixed {fixed_count} chapters")
        
    except Exception as e:
        print(f"❌ Error fixing chapters: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(fix_chapter_stages()) 