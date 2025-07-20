#!/usr/bin/env python3
"""
Firestore Service Layer for Book Writing Automation System
Provides CRUD operations aligned with the commercial architecture schema.
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from google.api_core.exceptions import NotFound, PermissionDenied

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class UserProfile:
    """User profile data structure"""
    clerk_id: str
    email: str
    name: str
    subscription_tier: str = 'free'
    avatar_url: Optional[str] = None
    created_at: Optional[datetime] = None
    last_active: Optional[datetime] = None
    timezone: str = 'UTC'

@dataclass
class ProjectMetadata:
    """Project metadata structure"""
    project_id: str
    title: str
    owner_id: str
    collaborators: List[str]
    status: str = 'active'
    visibility: str = 'private'
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

@dataclass  
class DirectorNote:
    """Director note structure"""
    note_id: Optional[str]
    chapter_id: str
    content: str
    created_by: str
    created_at: Optional[datetime] = None
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    position: Optional[int] = None

@dataclass
class ChapterMetadata:
    """Chapter metadata structure"""
    word_count: int
    target_word_count: int
    created_by: str
    stage: str = 'draft'
    generation_time: float = 0.0
    retry_attempts: int = 0
    model_used: str = 'gpt-4o'
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class FirestoreService:
    """
    Comprehensive Firestore service for the book writing system.
    Handles all database operations with proper error handling and validation.
    """
    
    def __init__(self, project_id: Optional[str] = None):
        """Initialize Firestore client."""
        try:
            if project_id:
                self.db = firestore.Client(project=project_id)
            else:
                self.db = firestore.Client()
            logger.info("Firestore service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Firestore: {e}")
            raise
    
    # =====================================================================
    # USER OPERATIONS
    # =====================================================================
    
    async def create_user(self, user_data: Dict[str, Any]) -> bool:
        """Create a new user document."""
        try:
            user_id = user_data['profile']['clerk_id']
            
            # Set timestamps
            now = datetime.now(timezone.utc)
            user_data['profile']['created_at'] = now
            user_data['profile']['last_active'] = now
            
            # Set default values if not provided
            if 'usage' not in user_data:
                user_data['usage'] = {
                    'monthly_cost': 0.0,
                    'chapters_generated': 0,
                    'api_calls': 0,
                    'words_generated': 0,
                    'projects_created': 0,
                    'last_reset_date': now
                }
            
            if 'preferences' not in user_data:
                user_data['preferences'] = {
                    'default_genre': 'Fiction',
                    'default_word_count': 2000,
                    'quality_strictness': 'standard',
                    'auto_backup_enabled': True,
                    'collaboration_notifications': True,
                    'email_notifications': True,
                    'preferred_llm_model': 'gpt-4o'
                }
            
            if 'limits' not in user_data:
                user_data['limits'] = {
                    'monthly_cost_limit': 50.0,
                    'monthly_chapter_limit': 100,
                    'concurrent_projects_limit': 5,
                    'storage_limit_mb': 1000
                }
            
            # Save to Firestore
            doc_ref = self.db.collection('users').document(user_id)
            doc_ref.set(user_data)
            
            logger.info(f"User {user_id} created successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create user: {e}")
            return False
    
    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user document by ID."""
        try:
            doc_ref = self.db.collection('users').document(user_id)
            doc = doc_ref.get()
            
            if doc.exists:
                return doc.to_dict()
            return None
            
        except Exception as e:
            logger.error(f"Failed to get user {user_id}: {e}")
            return None
    
    async def update_user(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """Update user document."""
        try:
            doc_ref = self.db.collection('users').document(user_id)
            doc_ref.update(updates)
            
            logger.info(f"User {user_id} updated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update user {user_id}: {e}")
            return False
    
    # =====================================================================
    # PROJECT OPERATIONS
    # =====================================================================
    
    async def create_project(self, project_data: Dict[str, Any]) -> Optional[str]:
        """Create a new project document."""
        try:
            project_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            
            # Ensure required metadata
            if 'metadata' not in project_data:
                project_data['metadata'] = {}
            
            project_data['metadata'].update({
                'project_id': project_id,
                'created_at': now,
                'updated_at': now,
                'status': project_data['metadata'].get('status', 'active'),
                'visibility': project_data['metadata'].get('visibility', 'private')
            })
            
            # Initialize empty collections if not provided
            if 'references' not in project_data:
                project_data['references'] = {}
            
            if 'progress' not in project_data:
                project_data['progress'] = {
                    'chapters_completed': 0,
                    'current_word_count': 0,
                    'target_word_count': 0,
                    'completion_percentage': 0.0,
                    'last_chapter_generated': 0,
                    'quality_baseline': {
                        'prose': 0.0,
                        'character': 0.0,
                        'story': 0.0,
                        'emotion': 0.0,
                        'freshness': 0.0,
                        'engagement': 0.0
                    }
                }
            
            if 'story_continuity' not in project_data:
                project_data['story_continuity'] = {
                    'main_characters': [],
                    'active_plot_threads': [],
                    'world_building_elements': {},
                    'theme_tracking': {},
                    'timeline_events': [],
                    'character_relationships': {},
                    'settings_visited': [],
                    'story_arc_progress': 0.0,
                    'tone_consistency': {}
                }
            
            # Save to Firestore
            doc_ref = self.db.collection('projects').document(project_id)
            doc_ref.set(project_data)
            
            logger.info(f"Project {project_id} created successfully")
            return project_id
            
        except Exception as e:
            logger.error(f"Failed to create project: {e}")
            return None
    
    async def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get project document by ID."""
        try:
            doc_ref = self.db.collection('projects').document(project_id)
            doc = doc_ref.get()
            
            if doc.exists:
                return doc.to_dict()
            return None
            
        except Exception as e:
            logger.error(f"Failed to get project {project_id}: {e}")
            return None
    
    async def get_user_projects(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all projects for a user (owned or collaborator)."""
        try:
            projects = []
            
            # Get owned projects
            query = self.db.collection('projects').where(
                filter=FieldFilter('metadata.owner_id', '==', user_id)
            )
            owned_docs = query.stream()
            projects.extend([doc.to_dict() for doc in owned_docs])
            
            # Get collaborative projects
            query = self.db.collection('projects').where(
                filter=FieldFilter('metadata.collaborators', 'array_contains', user_id)
            )
            collab_docs = query.stream()
            projects.extend([doc.to_dict() for doc in collab_docs])
            
            return projects
            
        except Exception as e:
            logger.error(f"Failed to get projects for user {user_id}: {e}")
            return []
    
    async def update_project(self, project_id: str, updates: Dict[str, Any]) -> bool:
        """Update project document."""
        try:
            # Add update timestamp
            updates['metadata.updated_at'] = datetime.now(timezone.utc)
            
            doc_ref = self.db.collection('projects').document(project_id)
            doc_ref.update(updates)
            
            logger.info(f"Project {project_id} updated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update project {project_id}: {e}")
            return False
    
    async def delete_project(self, project_id: str) -> bool:
        """Delete project and all associated chapters."""
        try:
            batch = self.db.batch()
            
            # Delete all chapters in the project
            chapters_query = self.db.collection('chapters').where(
                filter=FieldFilter('project_id', '==', project_id)
            )
            chapter_docs = chapters_query.stream()
            for doc in chapter_docs:
                batch.delete(doc.reference)
            
            # Delete the project
            project_ref = self.db.collection('projects').document(project_id)
            batch.delete(project_ref)
            
            # Commit batch operation
            batch.commit()
            
            logger.info(f"Project {project_id} and associated data deleted successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete project {project_id}: {e}")
            return False
    
    # =====================================================================
    # CHAPTER OPERATIONS
    # =====================================================================
    
    async def create_chapter(self, chapter_data: Dict[str, Any]) -> Optional[str]:
        """Create a new chapter document."""
        try:
            chapter_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            
            # Ensure required fields
            chapter_data['chapter_id'] = chapter_id
            
            if 'metadata' not in chapter_data:
                chapter_data['metadata'] = {}
                
            chapter_data['metadata'].update({
                'created_at': now,
                'updated_at': now
            })
            
            # Initialize empty arrays if not provided
            if 'versions' not in chapter_data:
                chapter_data['versions'] = []
            
            if 'quality_scores' not in chapter_data:
                chapter_data['quality_scores'] = {}
                
            if 'context_data' not in chapter_data:
                chapter_data['context_data'] = {}
            
            # Save to Firestore
            doc_ref = self.db.collection('chapters').document(chapter_id)
            doc_ref.set(chapter_data)
            
            logger.info(f"Chapter {chapter_id} created successfully")
            return chapter_id
            
        except Exception as e:
            logger.error(f"Failed to create chapter: {e}")
            return None
    
    async def get_chapter(self, chapter_id: str) -> Optional[Dict[str, Any]]:
        """Get chapter document by ID."""
        try:
            doc_ref = self.db.collection('chapters').document(chapter_id)
            doc = doc_ref.get()
            
            if doc.exists:
                return doc.to_dict()
            return None
            
        except Exception as e:
            logger.error(f"Failed to get chapter {chapter_id}: {e}")
            return None
    
    async def get_project_chapters(self, project_id: str) -> List[Dict[str, Any]]:
        """Get all chapters for a project, ordered by chapter number."""
        try:
            query = self.db.collection('chapters').where(
                filter=FieldFilter('project_id', '==', project_id)
            ).order_by('chapter_number')
            
            docs = query.stream()
            chapters = [doc.to_dict() for doc in docs]
            
            return chapters
            
        except Exception as e:
            logger.error(f"Failed to get chapters for project {project_id}: {e}")
            return []
    
    async def update_chapter(self, chapter_id: str, updates: Dict[str, Any]) -> bool:
        """Update chapter document."""
        try:
            # Add update timestamp
            updates['metadata.updated_at'] = datetime.now(timezone.utc)
            
            doc_ref = self.db.collection('chapters').document(chapter_id)
            doc_ref.update(updates)
            
            logger.info(f"Chapter {chapter_id} updated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update chapter {chapter_id}: {e}")
            return False
    
    async def add_chapter_version(self, chapter_id: str, version_data: Dict[str, Any]) -> bool:
        """Add a new version to chapter history."""
        try:
            doc_ref = self.db.collection('chapters').document(chapter_id)
            
            # Get current chapter to determine next version number
            doc = doc_ref.get()
            if not doc.exists:
                logger.error(f"Chapter {chapter_id} not found")
                return False
            
            chapter_data = doc.to_dict()
            versions = chapter_data.get('versions', [])
            
            # Create new version
            version_data.update({
                'version_number': len(versions) + 1,
                'timestamp': datetime.now(timezone.utc)
            })
            
            # Update chapter with new version
            versions.append(version_data)
            doc_ref.update({
                'versions': versions,
                'metadata.updated_at': datetime.now(timezone.utc)
            })
            
            logger.info(f"Version added to chapter {chapter_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add version to chapter {chapter_id}: {e}")
            return False
    
    # =====================================================================
    # GENERATION JOB OPERATIONS
    # =====================================================================
    
    async def create_generation_job(self, job_data: Dict[str, Any]) -> Optional[str]:
        """Create a new generation job document."""
        try:
            job_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            
            job_data.update({
                'job_id': job_id,
                'created_at': now,
                'status': job_data.get('status', 'pending')
            })
            
            # Initialize progress if not provided
            if 'progress' not in job_data:
                job_data['progress'] = {
                    'current_step': 'Initializing',
                    'total_steps': 1,
                    'completed_steps': 0,
                    'percentage': 0.0
                }
            
            # Initialize results if not provided
            if 'results' not in job_data:
                job_data['results'] = {
                    'chapters_generated': [],
                    'total_cost': 0.0,
                    'total_tokens': 0,
                    'average_quality_score': 0.0,
                    'generation_time': 0.0
                }
            
            # Save to Firestore
            doc_ref = self.db.collection('generation_jobs').document(job_id)
            doc_ref.set(job_data)
            
            logger.info(f"Generation job {job_id} created successfully")
            return job_id
            
        except Exception as e:
            logger.error(f"Failed to create generation job: {e}")
            return None
    
    async def get_generation_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get generation job document by ID."""
        try:
            doc_ref = self.db.collection('generation_jobs').document(job_id)
            doc = doc_ref.get()
            
            if doc.exists:
                return doc.to_dict()
            return None
            
        except Exception as e:
            logger.error(f"Failed to get generation job {job_id}: {e}")
            return None
    
    async def update_generation_job(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """Update generation job document."""
        try:
            doc_ref = self.db.collection('generation_jobs').document(job_id)
            doc_ref.update(updates)
            
            logger.info(f"Generation job {job_id} updated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update generation job {job_id}: {e}")
            return False
    
    async def get_user_jobs(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get generation jobs for a user."""
        try:
            query = self.db.collection('generation_jobs').where(
                filter=FieldFilter('user_id', '==', user_id)
            ).order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit)
            
            docs = query.stream()
            jobs = [doc.to_dict() for doc in docs]
            
            return jobs
            
        except Exception as e:
            logger.error(f"Failed to get jobs for user {user_id}: {e}")
            return []
    
    # =====================================================================
    # USAGE TRACKING OPERATIONS
    # =====================================================================
    
    async def track_usage(self, user_id: str, usage_data: Dict[str, Any]) -> bool:
        """Track usage data for billing and quota enforcement."""
        try:
            now = datetime.now(timezone.utc)
            month_year = now.strftime('%Y-%m')
            tracking_id = f"{month_year}-{user_id}"
            
            doc_ref = self.db.collection('usage_tracking').document(tracking_id)
            doc = doc_ref.get()
            
            if doc.exists:
                # Update existing tracking document
                current_data = doc.to_dict()
                daily_key = now.strftime('%Y-%m-%d')
                
                # Update daily usage
                if 'daily_usage' not in current_data:
                    current_data['daily_usage'] = {}
                
                if daily_key not in current_data['daily_usage']:
                    current_data['daily_usage'][daily_key] = {
                        'api_calls': 0,
                        'cost': 0.0,
                        'chapters_generated': 0,
                        'words_generated': 0,
                        'tokens_used': 0
                    }
                
                # Add to daily totals
                for key, value in usage_data.items():
                    current_data['daily_usage'][daily_key][key] = \
                        current_data['daily_usage'][daily_key].get(key, 0) + value
                
                # Update monthly totals
                if 'monthly_totals' not in current_data:
                    current_data['monthly_totals'] = {
                        'total_cost': 0.0,
                        'total_api_calls': 0,
                        'total_chapters': 0,
                        'total_words': 0,
                        'total_tokens': 0
                    }
                
                for key, value in usage_data.items():
                    if key in ['cost']:
                        current_data['monthly_totals']['total_cost'] += value
                    elif key in ['api_calls']:
                        current_data['monthly_totals']['total_api_calls'] += value
                    elif key in ['chapters_generated']:
                        current_data['monthly_totals']['total_chapters'] += value
                    elif key in ['words_generated']:
                        current_data['monthly_totals']['total_words'] += value
                    elif key in ['tokens_used']:
                        current_data['monthly_totals']['total_tokens'] += value
                
                current_data['updated_at'] = now
                doc_ref.update(current_data)
                
            else:
                # Create new tracking document
                daily_key = now.strftime('%Y-%m-%d')
                new_data = {
                    'user_id': user_id,
                    'month_year': month_year,
                    'daily_usage': {
                        daily_key: usage_data
                    },
                    'monthly_totals': {
                        'total_cost': usage_data.get('cost', 0.0),
                        'total_api_calls': usage_data.get('api_calls', 0),
                        'total_chapters': usage_data.get('chapters_generated', 0),
                        'total_words': usage_data.get('words_generated', 0),
                        'total_tokens': usage_data.get('tokens_used', 0)
                    },
                    'created_at': now,
                    'updated_at': now
                }
                doc_ref.set(new_data)
            
            logger.info(f"Usage tracked for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to track usage for user {user_id}: {e}")
            return False
    
    # =====================================================================
    # UTILITY OPERATIONS
    # =====================================================================
    
    async def health_check(self) -> bool:
        """Check if Firestore is accessible."""
        try:
            # Try to read from a test collection
            test_ref = self.db.collection('_health_check').document('test')
            test_ref.set({'timestamp': datetime.now(timezone.utc)})
            doc = test_ref.get()
            test_ref.delete()
            
            return doc.exists
            
        except Exception as e:
            logger.error(f"Firestore health check failed: {e}")
            return False 