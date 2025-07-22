#!/usr/bin/env python3
"""
Database Integration Module
Provides database adapter instances and convenience functions for the application.
"""

import os
import logging
from typing import Dict, List, Optional, Any
from services.database_adapter import DatabaseAdapter

logger = logging.getLogger(__name__)

# Global adapter instance
_adapter = None

def get_database_adapter():
    """
    Get a configured database adapter instance.
    
    Returns:
        DatabaseAdapter: Configured adapter instance
    """
    global _adapter
    if _adapter is None:
        # Check environment variables
        use_firestore = os.getenv('USE_FIRESTORE', 'false').lower() == 'true'
        firestore_project_id = os.getenv('GOOGLE_CLOUD_PROJECT', 'writer-bloom')
        
        logger.info(f"Creating database adapter: use_firestore={use_firestore}, project_id={firestore_project_id}")
        
        # Create and return adapter
        _adapter = DatabaseAdapter(
            use_firestore=use_firestore,
            firestore_project_id=firestore_project_id
        )
    
    return _adapter

# =====================================================================
# CONVENIENCE WRAPPER FUNCTIONS
# =====================================================================

async def get_user_projects(user_id: str) -> List[Dict[str, Any]]:
    """Get all projects for a user."""
    adapter = get_database_adapter()
    return await adapter.get_user_projects(user_id)

async def create_project(project_data: Dict[str, Any]) -> Optional[str]:
    """Create a new project."""
    adapter = get_database_adapter()
    return await adapter.create_project(project_data)

async def get_project(project_id: str) -> Optional[Dict[str, Any]]:
    """Get a project by ID."""
    adapter = get_database_adapter()
    return await adapter.get_project(project_id)

async def get_project_chapters(project_id: str) -> List[Dict[str, Any]]:
    """Get all chapters for a project."""
    adapter = get_database_adapter()
    return await adapter.get_project_chapters(project_id)

async def create_chapter(chapter_data: Dict[str, Any]) -> Optional[str]:
    """Create a new chapter."""
    adapter = get_database_adapter()
    return await adapter.create_chapter(chapter_data)

async def track_usage(user_id: str, usage_data: Dict[str, Any]) -> bool:
    """Track user usage statistics."""
    adapter = get_database_adapter()
    return await adapter.track_usage(user_id, usage_data)

async def create_reference_file(project_id: str, filename: str, content: str, user_id: str) -> Optional[str]:
    """Create a reference file for a project."""
    # For now, just log this as the method might not be fully implemented
    logger.info(f"Creating reference file {filename} for project {project_id}")
    # This is a placeholder - in a full implementation, this would store the reference file
    return f"ref_{project_id}_{filename}"

async def migrate_project_from_filesystem(project_path: str, user_id: str) -> Optional[str]:
    """Migrate a project from filesystem to database."""
    adapter = get_database_adapter()
    return await adapter.migrate_project_from_filesystem(project_path, user_id) 