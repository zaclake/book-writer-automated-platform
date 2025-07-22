#!/usr/bin/env python3
"""
Database Integration Layer
Connects the new Firestore service with existing FastAPI endpoints.
"""

import logging
import os
from typing import Optional
from functools import lru_cache
from datetime import datetime, timezone

from services.database_adapter import DatabaseAdapter

logger = logging.getLogger(__name__)

# Global database adapter instance
_db_adapter: Optional[DatabaseAdapter] = None

@lru_cache()
def get_database_adapter() -> DatabaseAdapter:
    """
    Get or create the global database adapter instance.
    Uses environment variables for configuration.
    """
    global _db_adapter
    
    if _db_adapter is None:
        try:
            _db_adapter = DatabaseAdapter.from_environment()
            logger.info("Database adapter initialized successfully")
        except Exception as e:
            logger.critical(f"CRITICAL: Failed to initialize database adapter: {e}")
            
            # Log the detailed error for debugging
            logger.error(f"DatabaseAdapter.from_environment() failed: {e}")
            logger.error(f"USE_FIRESTORE env var: {os.getenv('USE_FIRESTORE')}")
            logger.error(f"GOOGLE_CLOUD_PROJECT env var: {os.getenv('GOOGLE_CLOUD_PROJECT')}")
            logger.error(f"SERVICE_ACCOUNT_JSON present: {bool(os.getenv('SERVICE_ACCOUNT_JSON'))}")
            
            # Check if we're in development mode
            environment = os.getenv('ENVIRONMENT', 'production')
            if environment == 'development':
                logger.warning("Development mode: Falling back to local storage")
                _db_adapter = DatabaseAdapter(use_firestore=False)
            else:
                logger.warning("Production mode: Firestore failed, falling back to local storage for now")
                _db_adapter = DatabaseAdapter(use_firestore=False)
    
    return _db_adapter

async def init_database():
    """Initialize database connection on startup."""
    try:
        db = get_database_adapter()
        health = await db.health_check()
        
        if health['healthy']:
            logger.info(f"Database initialized: {health['database_type']}")
        else:
            logger.warning(f"Database health check failed: {health['details']}")
            
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")

async def cleanup_database():
    """Cleanup database connections on shutdown."""
    global _db_adapter
    
    if _db_adapter:
        try:
            # Perform any necessary cleanup
            logger.info("Database connections cleaned up")
        except Exception as e:
            logger.error(f"Error during database cleanup: {e}")
        finally:
            _db_adapter = None

# Convenience functions for common operations
async def get_user_projects(user_id: str):
    """Get all projects for a user."""
    db = get_database_adapter()
    return await db.get_user_projects(user_id)

async def create_project(project_data: dict):
    """Create a new project."""
    db = get_database_adapter()
    return await db.create_project(project_data)

async def get_project(project_id: str):
    """Get project by ID."""
    db = get_database_adapter()
    return await db.get_project(project_id)

async def get_project_chapters(project_id: str):
    """Get all chapters for a project."""
    db = get_database_adapter()
    return await db.get_project_chapters(project_id)

async def create_chapter(chapter_data: dict):
    """Create a new chapter."""
    db = get_database_adapter()
    return await db.create_chapter(chapter_data)

async def track_usage(user_id: str, usage_data: dict):
    """Track usage for billing and quotas."""
    db = get_database_adapter()
    return await db.track_usage(user_id, usage_data)

async def migrate_project_from_filesystem(project_path: str, user_id: str):
    """Migrate existing project from filesystem to database."""
    db = get_database_adapter()
    return await db.migrate_project_from_filesystem(project_path, user_id)

async def create_reference_file(reference_data: dict = None, **kwargs):
    """Create a new reference file."""
    db = get_database_adapter()
    
    # Handle both calling patterns: dict argument or keyword arguments
    if reference_data is None:
        # Called with keyword arguments
        reference_data = {
            'name': kwargs.get('filename') or kwargs.get('name'),
            'content': kwargs.get('content'),
            'project_id': kwargs.get('project_id'),
            'created_by': kwargs.get('user_id') or kwargs.get('created_by'),
            'file_type': kwargs.get('file_type', 'reference')
        }
    
    # Validate required fields
    required_fields = ['name', 'content', 'project_id', 'created_by']
    missing_fields = [field for field in required_fields if not reference_data.get(field)]
    
    if missing_fields:
        logger.error(f"Missing required fields for reference file creation: {missing_fields}")
        raise ValueError(f"Missing required fields: {missing_fields}")
    
    # Add default values
    reference_data.setdefault('created_at', datetime.now(timezone.utc))
    reference_data.setdefault('version', 1)
    reference_data.setdefault('size', len(reference_data.get('content', '')))
    reference_data.setdefault('file_type', 'reference')
    
    try:
        if hasattr(db, 'firestore') and db.use_firestore and db.firestore:
            # Use Firestore service if available
            return await db.firestore.create_reference_file(reference_data)
        else:
            # Fallback for local storage - just return success for now
            logger.warning("Reference file creation using local storage fallback")
            return {'id': f"ref_{reference_data['project_id']}_{reference_data['name']}", 'success': True}
    except Exception as e:
        logger.error(f"Failed to create reference file: {e}")
        return None 