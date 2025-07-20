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
            
            # Check if we're in development mode
            environment = os.getenv('ENVIRONMENT', 'production')
            if environment == 'development':
                logger.warning("Development mode: Falling back to local storage")
                _db_adapter = DatabaseAdapter(use_firestore=False)
            else:
                logger.error("Production mode: Database initialization failure is not recoverable")
                raise RuntimeError(f"Database initialization failed in production: {e}")
    
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

async def create_reference_file(reference_data: dict):
    """Create a new reference file."""
    db = get_database_adapter()
    
    # Validate required fields
    required_fields = ['name', 'content', 'project_id', 'created_by', 'file_type']
    missing_fields = [field for field in required_fields if field not in reference_data]
    
    if missing_fields:
        raise ValueError(f"Missing required fields: {missing_fields}")
    
    # Add default values
    reference_data.setdefault('created_at', datetime.now(timezone.utc))
    reference_data.setdefault('version', 1)
    reference_data.setdefault('size', len(reference_data.get('content', '')))
    
    if hasattr(db, 'firestore_service') and db.use_firestore:
        # Use Firestore service if available
        return await db.firestore_service.create_reference_file(reference_data)
    else:
        # Fallback for local storage (implement as needed)
        logger.warning("Reference file creation not implemented for local storage")
        return None 