#!/usr/bin/env python3
"""
Firestore Client Compatibility Layer
Provides backward compatibility for existing code while migrating to new architecture.
"""

import json
import logging
import os
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
from fastapi.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)

class FirestoreClientCompat:
    """
    Compatibility wrapper that bridges old firestore_client calls to new database_adapter.
    This allows existing code to continue working while we gradually migrate.
    """
    
    def __init__(self, use_firestore: bool = False):
        self.use_firestore = use_firestore
        self.local_storage_path = "./local_storage"
        
        # Import the new database adapter
        try:
            from backend.database_integration import get_database_adapter
            self.get_db = get_database_adapter
        except ImportError as e:
            try:
                # Fallback for when running from backend directory
                from database_integration import get_database_adapter
                self.get_db = get_database_adapter
            except ImportError as e2:
                raise ImportError(f"Failed to import database_integration from both backend.database_integration and database_integration: {e}, {e2}")
        
        # Create local storage directory
        os.makedirs(self.local_storage_path, exist_ok=True)
    
    async def save_job(self, job_id: str, job_data: Dict[str, Any]) -> bool:
        """Save job data - compatibility wrapper."""
        try:
            logger.info(f"🔍 [COMPAT] save_job called for {job_id}")
            
            if self.get_db:
                db = self.get_db()
                logger.info(f"🔍 [COMPAT] Database adapter: use_firestore={db.use_firestore}")
                
                if db.use_firestore:
                    logger.info(f"🔥 [COMPAT] Using Firestore for job {job_id}")
                    try:
                        # Convert old format to new format
                        new_job_data = {
                            "job_id": job_id,
                            "job_type": "auto_complete_book",  # Default type
                            "project_id": job_data.get("project_id", ""),
                            "user_id": job_data.get("user_id", ""),
                            "status": job_data.get("status", "pending"),
                            "progress": job_data.get("progress", {}),
                            "auto_complete_data": job_data.get("book_completion_job", {})
                        }
                        # Use the async Firestore save operation directly
                        result = await self._save_to_firestore_async(db, new_job_data)
                        logger.info(f"🔥 [COMPAT] Firestore save result: {result is not None}")
                        return result is not None
                    except Exception as e:
                        logger.error(f"🔥 [COMPAT] Firestore save failed: {e}, falling back to local storage")
                        # Fall back to local storage if Firestore fails
                else:
                    logger.warning(f"⚠️ [COMPAT] Firestore not enabled, falling back to local storage")
            else:
                logger.warning(f"⚠️ [COMPAT] No database adapter available")
            
            # Fallback to local storage
            logger.info(f"💾 [COMPAT] Using local storage for job {job_id}")
            return self._save_local_job(job_id, job_data)
            
        except Exception as e:
            logger.error(f"Failed to save job {job_id}: {e}")
            return False
    
    async def load_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Load job data - compatibility wrapper."""
        try:
            if self.get_db:
                db = self.get_db()
                if db.use_firestore:
                    job_data = await db.firestore.get_generation_job(job_id)
                    if job_data:
                        # Convert new format back to old format for compatibility
                        return {
                            "job_id": job_data.get("job_id"),
                            "project_id": job_data.get("project_id"),
                            "user_id": job_data.get("user_id"),
                            "status": job_data.get("status"),
                            "progress": job_data.get("progress", {}),
                            "book_completion_job": job_data.get("auto_complete_data", {})
                        }
            
            # Fallback to local storage
            return self._load_local_job(job_id)
            
        except Exception as e:
            logger.error(f"Failed to load job {job_id}: {e}")
            return None
    
    async def list_user_jobs(self, user_id: str, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        """List user jobs - compatibility wrapper."""
        try:
            if self.get_db:
                db = self.get_db()
                if db.use_firestore and hasattr(db, 'firestore_service'):
                    jobs = await db.firestore_service.get_user_jobs(user_id, limit + offset)
                    # Apply offset
                    return jobs[offset:offset+limit] if jobs else []
            
            # Fallback to empty list
            return []
            
        except Exception as e:
            logger.error(f"Failed to list jobs for user {user_id}: {e}")
            return []
    
    async def save_project_data(self, project_id: str, project_data: Dict[str, Any]) -> bool:
        """Save project data - compatibility wrapper."""
        try:
            if self.get_db:
                db = self.get_db()
                if db.use_firestore:
                    # This would need the user_id to create a proper project
                    # For now, just log that this needs migration
                    logger.warning(f"save_project_data({project_id}) needs migration to new v2 API")
                    return True
            
            return True  # Fallback success
            
        except Exception as e:
            logger.error(f"Failed to save project {project_id}: {e}")
            return False
    
    async def load_project_data(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Load project data - compatibility wrapper."""
        try:
            if self.get_db:
                db = self.get_db()
                if db.use_firestore:
                    project = await db.firestore.get_project(project_id)
                    if project:
                        # Convert new format to old format
                        return {
                            "project_id": project_id,
                            "title": project.get("metadata", {}).get("title", ""),
                            "book_bible": project.get("book_bible", {}).get("content", ""),
                            "settings": project.get("settings", {})
                        }
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to load project {project_id}: {e}")
            return None
    
    async def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage stats - compatibility wrapper."""
        return {
            "total_projects": 0,
            "total_chapters": 0,
            "total_size_mb": 0
        }
    
    async def cleanup_old_jobs(self, max_age_days: int = 7) -> int:
        """Cleanup old jobs - compatibility wrapper."""
        logger.info(f"Cleanup old jobs (compatibility mode) - would clean jobs older than {max_age_days} days")
        return 0
    
    def _save_local_job(self, job_id: str, job_data: Dict[str, Any]) -> bool:
        """Save job to local storage."""
        try:
            job_data['updated_at'] = datetime.utcnow().isoformat()
            jobs_dir = os.path.join(self.local_storage_path, 'jobs')
            os.makedirs(jobs_dir, exist_ok=True)
            
            with open(os.path.join(jobs_dir, f"{job_id}.json"), 'w', encoding='utf-8') as f:
                json.dump(job_data, f, indent=2, ensure_ascii=False, default=str)
            return True
        except Exception as e:
            logger.error(f"Failed to save local job {job_id}: {e}")
            return False
    
    def _load_local_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Load job from local storage."""
        try:
            job_file = os.path.join(self.local_storage_path, 'jobs', f"{job_id}.json")
            if os.path.exists(job_file):
                with open(job_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return None
        except Exception as e:
            logger.error(f"Failed to load local job {job_id}: {e}")
            return None
    
    async def _save_to_firestore_async(self, db, job_data: Dict[str, Any]) -> Optional[str]:
        """Async Firestore save operation."""
        try:
            result = await db.firestore.create_generation_job(job_data)
            return result
        except Exception as e:
            logger.error(f"Firestore async save failed: {e}")
            raise  # Re-raise to trigger fallback

# Create global instance for compatibility
firestore_client = FirestoreClientCompat(use_firestore=False)

# Update based on environment
def initialize_firestore_client():
    """Initialize the global firestore_client based on environment."""
    global firestore_client
    use_firestore = os.getenv('USE_FIRESTORE', 'false').lower() == 'true'
    firestore_client = FirestoreClientCompat(use_firestore=use_firestore)
    
    if use_firestore:
        logger.info("✅ Firestore client compatibility layer initialized")
    else:
        logger.info("✅ Local storage compatibility layer initialized")

# Initialize on import
initialize_firestore_client() 