#!/usr/bin/env python3
"""
Firestore Service Layer for Book Writing Automation System
Provides CRUD operations aligned with the commercial architecture schema.
"""

import logging
import os
import uuid
import json
import tempfile
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from google.api_core.exceptions import NotFound, PermissionDenied
from google.oauth2 import service_account
from google.cloud import storage

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
        """Initialize Firestore client with proper credential handling."""
        self.db = None
        self.available = False
        environment = os.getenv('ENVIRONMENT', 'production')
        
        try:
            # Try to initialize Firestore with proper credential handling
            credentials = None
            
            # Method 1: SERVICE_ACCOUNT_JSON environment variable (for Railway)
            service_account_json = os.getenv('SERVICE_ACCOUNT_JSON')
            if service_account_json:
                try:
                    logger.info("Attempting to initialize Firestore with SERVICE_ACCOUNT_JSON")
                    service_account_info = json.loads(service_account_json)
                    credentials = service_account.Credentials.from_service_account_info(service_account_info)
                    
                    # Use project_id from service account if not provided
                    if not project_id:
                        project_id = service_account_info.get('project_id')
                    
                    if project_id:
                        self.db = firestore.Client(project=project_id, credentials=credentials)
                    else:
                        self.db = firestore.Client(credentials=credentials)
                        
                    logger.info(f"✅ Firestore initialized successfully with SERVICE_ACCOUNT_JSON (project: {project_id})")
                    self.available = True
                    return
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse SERVICE_ACCOUNT_JSON: {e}")
                except Exception as e:
                    logger.error(f"Failed to initialize Firestore with SERVICE_ACCOUNT_JSON: {e}")
            
            # Method 2: GOOGLE_APPLICATION_CREDENTIALS file path
            creds_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
            if creds_path and os.path.exists(creds_path):
                try:
                    logger.info(f"Attempting to initialize Firestore with credentials file: {creds_path}")
                    credentials = service_account.Credentials.from_service_account_file(creds_path)
                    
                    if project_id:
                        self.db = firestore.Client(project=project_id, credentials=credentials)
                    else:
                        self.db = firestore.Client(credentials=credentials)
                    
                    logger.info(f"✅ Firestore initialized successfully with credentials file")
                    self.available = True
                    return
                except Exception as e:
                    logger.error(f"Failed to initialize Firestore with credentials file: {e}")
            
            # Method 3: Try default credentials (for local development or GCP environment)
            try:
                logger.info("Attempting to initialize Firestore with default credentials")
                if project_id:
                    self.db = firestore.Client(project=project_id)
                else:
                    # Try to get project_id from environment
                    project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
                    if project_id:
                        self.db = firestore.Client(project=project_id)
                    else:
                        self.db = firestore.Client()
                
                logger.info("✅ Firestore initialized successfully with default credentials")
                self.available = True
                return
            except Exception as e:
                logger.error(f"Failed to initialize Firestore with default credentials: {e}")
            
            # If we get here, all methods failed
            raise Exception("All Firestore initialization methods failed")
            
        except Exception as e:
            logger.error(f"Failed to initialize Firestore: {e}")
            
            # In production without credentials, create a fallback mode
            if environment == 'production':
                logger.warning("⚠️ Firestore unavailable in production - using fallback mode")
                logger.warning("To enable Firestore, set SERVICE_ACCOUNT_JSON environment variable with your service account JSON")
                self.db = None
                self.available = False
            else:
                # In development, fail fast to surface configuration issues
                logger.error("❌ Firestore initialization failed in development mode")
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
        """Create a new project document under user collection."""
        try:
            project_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            
            # Ensure required metadata
            if 'metadata' not in project_data:
                project_data['metadata'] = {}
                
            # Extract user_id from metadata (must be provided)
            user_id = project_data['metadata'].get('owner_id')
            if not user_id:
                raise ValueError("owner_id is required in project metadata")
            
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
            
            # Save to user-scoped collection
            doc_ref = self.db.collection('users').document(user_id)\
                             .collection('projects').document(project_id)
            doc_ref.set(project_data)
            
            logger.info(f"Project {project_id} created successfully for user {user_id}")
            return project_id
            
        except Exception as e:
            logger.error(f"Failed to create project: {e}")
            return None
    
    async def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get project document by ID (searches across all users for backwards compatibility)."""
        try:
            # First try to find the project by searching across users
            # This is less efficient but maintains backwards compatibility
            users_ref = self.db.collection('users')
            users = users_ref.stream()
            
            for user_doc in users:
                user_id = user_doc.id
                project_ref = self.db.collection('users').document(user_id)\
                                   .collection('projects').document(project_id)
                project_doc = project_ref.get()
                
                if project_doc.exists:
                    project_data = project_doc.to_dict()
                    project_data['id'] = project_id  # Add document ID as 'id' field
                    return project_data
            
            # If not found in user-scoped collections, try the old root collection
            # for backwards compatibility during migration
            doc_ref = self.db.collection('projects').document(project_id)
            doc = doc_ref.get()
            
            if doc.exists:
                project_data = doc.to_dict()
                project_data['id'] = project_id  # Add document ID as 'id' field
                return project_data
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get project {project_id}: {e}")
            return None
    
    async def get_user_project(self, user_id: str, project_id: str) -> Optional[Dict[str, Any]]:
        """Get project document by user ID and project ID (more efficient)."""
        try:
            doc_ref = self.db.collection('users').document(user_id)\
                             .collection('projects').document(project_id)
            doc = doc_ref.get()
            
            if doc.exists:
                project_data = doc.to_dict()
                project_data['id'] = project_id  # Add document ID as 'id' field
                return project_data
            return None
            
        except Exception as e:
            logger.error(f"Failed to get project {project_id} for user {user_id}: {e}")
            return None
    
    async def get_user_projects(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all projects for a user from user-scoped collection."""
        try:
            projects = []
            
            # Get projects from user-scoped collection
            projects_ref = self.db.collection('users').document(user_id)\
                                  .collection('projects')
            project_docs = projects_ref.stream()
            
            # Include document ID as 'id' field for each project
            for doc in project_docs:
                project_data = doc.to_dict()
                project_data['id'] = doc.id  # Add document ID as 'id' field
                projects.append(project_data)
            
            # For backwards compatibility, also check old root collection for user's projects
            # during migration period
            try:
                query = self.db.collection('projects').where(
                    filter=FieldFilter('metadata.owner_id', '==', user_id)
                )
                legacy_docs = query.stream()
                
                # Add legacy projects that aren't already in the new structure
                for doc in legacy_docs:
                    legacy_project = doc.to_dict()
                    legacy_project['id'] = doc.id  # Add document ID as 'id' field
                    project_id = legacy_project.get('metadata', {}).get('project_id')
                    if project_id and not any(p.get('metadata', {}).get('project_id') == project_id for p in projects):
                        projects.append(legacy_project)
                        
            except Exception as e:
                logger.warning(f"Failed to fetch legacy projects for user {user_id}: {e}")
            
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
        """Delete project and all associated data (chapters, references, etc.)."""
        try:
            batch = self.db.batch()
            
            # Delete all chapters in the project
            chapters_query = self.db.collection('chapters').where(
                filter=FieldFilter('project_id', '==', project_id)
            )
            chapter_docs = chapters_query.stream()
            chapter_count = 0
            for doc in chapter_docs:
                batch.delete(doc.reference)
                chapter_count += 1
            
            # Delete all reference files in the project
            references_query = self.db.collection('references').where(
                filter=FieldFilter('project_id', '==', project_id)
            )
            reference_docs = references_query.stream()
            reference_count = 0
            for doc in reference_docs:
                batch.delete(doc.reference)
                reference_count += 1
            
            # Check for user-specific project documents and delete them
            users_ref = self.db.collection('users')
            users = users_ref.stream()
            user_project_count = 0
            
            for user_doc in users:
                user_id = user_doc.id
                user_project_ref = self.db.collection('users').document(user_id)\
                                       .collection('projects').document(project_id)
                user_project_doc = user_project_ref.get()
                
                if user_project_doc.exists:
                    batch.delete(user_project_ref)
                    user_project_count += 1
            
            # Delete the main project document
            project_ref = self.db.collection('projects').document(project_id)
            batch.delete(project_ref)
            
            # Commit batch operation
            batch.commit()
            
            logger.info(f"Project {project_id} deleted successfully: {chapter_count} chapters, {reference_count} references, {user_project_count} user-project docs, 1 main project doc")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete project {project_id}: {e}")
            return False
    
    # =====================================================================
    # CHAPTER OPERATIONS
    # =====================================================================
    
    async def create_chapter(self, chapter_data: Dict[str, Any], user_id: Optional[str] = None) -> Optional[str]:
        """Create a new chapter document under user/project structure with uniqueness enforcement."""
        try:
            chapter_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            
            # Get project_id and validate inputs
            project_id = chapter_data.get('project_id')
            if not project_id:
                raise ValueError("project_id is required for chapter creation")
                
            chapter_number = chapter_data.get('chapter_number')
            if not chapter_number:
                raise ValueError("chapter_number is required for chapter creation")
            
            # Use provided user_id or fall back to scanning (avoid O(N-users) when possible)
            if not user_id:
                # Fall back to finding the user (expensive but necessary for legacy)
                users_ref = self.db.collection('users')
                users = users_ref.stream()
                
                for user_doc in users:
                    temp_user_id = user_doc.id
                    project_ref = self.db.collection('users').document(temp_user_id)\
                                       .collection('projects').document(project_id)
                    project_doc = project_ref.get()
                    
                    if project_doc.exists:
                        user_id = temp_user_id
                        break
                
                # If still not found, try to get user from chapter metadata
                if not user_id:
                    user_id = chapter_data.get('metadata', {}).get('created_by')
                    if not user_id:
                        raise ValueError(f"Cannot determine user_id for project {project_id}")
            
            # Ensure required fields - standardize on 'id' field for consistency
            chapter_data['id'] = chapter_id
            
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
            
            # Use transaction to enforce uniqueness of (project_id, chapter_number)
            chapters_ref = self.db.collection('users').document(user_id)\
                                  .collection('projects').document(project_id)\
                                  .collection('chapters')
            
            @firestore.transactional
            def create_chapter_transaction(transaction):
                # Check if chapter with same chapter_number already exists
                existing_query = chapters_ref.where(
                    filter=FieldFilter('chapter_number', '==', chapter_number)
                )
                existing_docs = list(existing_query.stream())
                
                if existing_docs:
                    raise ValueError(f"Chapter {chapter_number} already exists in project {project_id}")
                
                # Create the new chapter document
                new_chapter_ref = chapters_ref.document(chapter_id)
                transaction.set(new_chapter_ref, chapter_data)
                return chapter_id
            
            # Execute transaction
            transaction = self.db.transaction()
            result_chapter_id = create_chapter_transaction(transaction)
            
            logger.info(f"Chapter {chapter_id} created successfully for project {project_id} (user {user_id}) with enforced uniqueness")
            return result_chapter_id
            
        except Exception as e:
            logger.error(f"Failed to create chapter: {e}")
            return None
    
    async def get_chapter(self, chapter_id: str, user_id: Optional[str] = None, project_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get chapter document by ID from user-scoped collections."""
        try:
            # If user_id and project_id are provided, use direct path (MUCH faster)
            if user_id and project_id:
                chapter_ref = self.db.collection('users').document(user_id)\
                                     .collection('projects').document(project_id)\
                                     .collection('chapters').document(chapter_id)
                
                chapter_doc = chapter_ref.get()
                if chapter_doc.exists:
                    chapter_data = chapter_doc.to_dict()
                    chapter_data['id'] = chapter_id  # Add the document ID
                    return chapter_data
            
            # If no direct path info, fall back to scanning (expensive but necessary for legacy)
            users_ref = self.db.collection('users')
            users = users_ref.stream()
            
            for user_doc in users:
                temp_user_id = user_doc.id
                projects_ref = self.db.collection('users').document(temp_user_id).collection('projects')
                projects = projects_ref.stream()
                
                for project_doc in projects:
                    temp_project_id = project_doc.id
                    chapter_ref = self.db.collection('users').document(temp_user_id)\
                                         .collection('projects').document(temp_project_id)\
                                         .collection('chapters').document(chapter_id)
                    
                    chapter_doc = chapter_ref.get()
                    if chapter_doc.exists:
                        chapter_data = chapter_doc.to_dict()
                        chapter_data['id'] = chapter_id  # Add the document ID
                        return chapter_data
            
            # Fallback to legacy root collection for backwards compatibility
            doc_ref = self.db.collection('chapters').document(chapter_id)
            doc = doc_ref.get()
            
            if doc.exists:
                chapter_data = doc.to_dict()
                chapter_data['id'] = chapter_id  # Add the document ID
                return chapter_data
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get chapter {chapter_id}: {e}")
            return None
    
    async def get_project_chapters(self, project_id: str) -> List[Dict[str, Any]]:
        """Get all chapters for a project from user-scoped collections."""
        try:
            chapters = []
            
            # Find the user who owns this project and get chapters
            users_ref = self.db.collection('users')
            users = users_ref.stream()
            
            for user_doc in users:
                user_id = user_doc.id
                project_ref = self.db.collection('users').document(user_id)\
                                   .collection('projects').document(project_id)
                project_doc = project_ref.get()
                
                if project_doc.exists:
                    # Found the project, now get its chapters
                    chapters_ref = self.db.collection('users').document(user_id)\
                                          .collection('projects').document(project_id)\
                                          .collection('chapters')
                    
                    # Order by chapter_number if available
                    try:
                        query = chapters_ref.order_by('chapter_number')
                        docs = query.stream()
                    except Exception:
                        # If no index for chapter_number, just get all chapters
                        docs = chapters_ref.stream()
                    
                    # Include document ID in the returned data
                    chapters = []
                    for doc in docs:
                        chapter_data = doc.to_dict()
                        chapter_data['id'] = doc.id  # Add the document ID
                        chapters.append(chapter_data)
                    break
            
            # For backwards compatibility during migration, also check old root collection
            if not chapters:
                try:
                    query = self.db.collection('chapters').where(
                        filter=FieldFilter('project_id', '==', project_id)
                    ).order_by('chapter_number')
                    
                    docs = query.stream()
                    # Include document ID in the returned data
                    chapters = []
                    for doc in docs:
                        chapter_data = doc.to_dict()
                        chapter_data['id'] = doc.id  # Add the document ID
                        chapters.append(chapter_data)
                    
                except Exception as e:
                    logger.warning(f"Failed to get chapters from legacy collection for project {project_id}: {e}")
            
            return chapters
            
        except Exception as e:
            logger.error(f"Failed to get chapters for project {project_id}: {e}")
            return []
    
    async def update_chapter(self, chapter_id: str, updates: Dict[str, Any], user_id: Optional[str] = None, project_id: Optional[str] = None) -> bool:
        """Update chapter document in user-scoped collections."""
        try:
            # Add update timestamp
            updates['metadata.updated_at'] = datetime.now(timezone.utc)
            
            # If user_id and project_id are provided, use direct path (MUCH faster)
            if user_id and project_id:
                chapter_ref = self.db.collection('users').document(user_id)\
                                     .collection('projects').document(project_id)\
                                     .collection('chapters').document(chapter_id)
                
                chapter_doc = chapter_ref.get()
                if chapter_doc.exists:
                    # Use transaction for atomic updates
                    @firestore.transactional
                    def update_chapter_transaction(transaction):
                        # Re-read chapter within transaction
                        doc = chapter_ref.get(transaction=transaction)
                        if not doc.exists:
                            raise Exception(f"Chapter {chapter_id} no longer exists")
                        
                        # Apply updates atomically
                        transaction.update(chapter_ref, updates)
                        return True
                    
                    # Execute transaction
                    transaction = self.db.transaction()
                    success = update_chapter_transaction(transaction)
                    
                    if success:
                        logger.info(f"Chapter {chapter_id} updated successfully in user-scoped collection")
                    return success
            
            # If no direct path info, fall back to scanning (expensive but necessary for legacy)
            users_ref = self.db.collection('users')
            users = users_ref.stream()
            
            chapter_updated = False
            for user_doc in users:
                temp_user_id = user_doc.id
                projects_ref = self.db.collection('users').document(temp_user_id).collection('projects')
                projects = projects_ref.stream()
                
                for project_doc in projects:
                    temp_project_id = project_doc.id
                    chapter_ref = self.db.collection('users').document(temp_user_id)\
                                         .collection('projects').document(temp_project_id)\
                                         .collection('chapters').document(chapter_id)
                    
                    chapter_doc = chapter_ref.get()
                    if chapter_doc.exists:
                        # Use transaction for atomic updates
                        @firestore.transactional
                        def update_chapter_transaction(transaction):
                            doc = chapter_ref.get(transaction=transaction)
                            if not doc.exists:
                                raise Exception(f"Chapter {chapter_id} no longer exists")
                            transaction.update(chapter_ref, updates)
                            return True
                        
                        transaction = self.db.transaction()
                        success = update_chapter_transaction(transaction)
                        
                        if success:
                            logger.info(f"Chapter {chapter_id} updated successfully in user-scoped collection")
                            chapter_updated = True
                        break
                
                if chapter_updated:
                    break
            
            # If not found in user-scoped collections, try legacy root collection
            if not chapter_updated:
                doc_ref = self.db.collection('chapters').document(chapter_id)
                doc = doc_ref.get()
                if doc.exists:
                    # Use transaction for atomic updates
                    @firestore.transactional
                    def update_legacy_chapter_transaction(transaction):
                        doc = doc_ref.get(transaction=transaction)
                        if not doc.exists:
                            raise Exception(f"Chapter {chapter_id} no longer exists")
                        transaction.update(doc_ref, updates)
                        return True
                    
                    transaction = self.db.transaction()
                    success = update_legacy_chapter_transaction(transaction)
                    
                    if success:
                        logger.info(f"Chapter {chapter_id} updated successfully in legacy collection")
                        chapter_updated = True
            
            return chapter_updated
            
        except Exception as e:
            logger.error(f"Failed to update chapter {chapter_id}: {e}")
            return False
    
    async def add_chapter_version(self, chapter_id: str, version_data: Dict[str, Any], user_id: Optional[str] = None, project_id: Optional[str] = None) -> bool:
        """Add a new version to chapter history in user-scoped collections."""
        try:
            chapter_ref = None
            chapter_data = None
            
            # If user_id and project_id are provided, use direct path (MUCH faster)
            if user_id and project_id:
                chapter_ref = self.db.collection('users').document(user_id)\
                                     .collection('projects').document(project_id)\
                                     .collection('chapters').document(chapter_id)
                
                chapter_doc = chapter_ref.get()
                if chapter_doc.exists:
                    chapter_data = chapter_doc.to_dict()
            
            # If no direct path info or chapter not found, fall back to scanning
            if not chapter_ref or not chapter_data:
                users_ref = self.db.collection('users')
                users = users_ref.stream()
                
                for user_doc in users:
                    temp_user_id = user_doc.id
                    projects_ref = self.db.collection('users').document(temp_user_id).collection('projects')
                    projects = projects_ref.stream()
                    
                    for project_doc in projects:
                        temp_project_id = project_doc.id
                        temp_chapter_ref = self.db.collection('users').document(temp_user_id)\
                                                  .collection('projects').document(temp_project_id)\
                                                  .collection('chapters').document(chapter_id)
                        
                        chapter_doc = temp_chapter_ref.get()
                        if chapter_doc.exists:
                            chapter_ref = temp_chapter_ref
                            chapter_data = chapter_doc.to_dict()
                            break
                    
                    if chapter_ref:
                        break
                
                # If not found in user-scoped collections, try legacy root collection
                if not chapter_ref:
                    temp_doc_ref = self.db.collection('chapters').document(chapter_id)
                    doc = temp_doc_ref.get()
                    if doc.exists:
                        chapter_ref = temp_doc_ref
                        chapter_data = doc.to_dict()
            
            if not chapter_ref or not chapter_data:
                logger.error(f"Chapter {chapter_id} not found")
                return False
            
            # Use transaction to prevent race conditions
            @firestore.transactional
            def update_chapter_version_transaction(transaction):
                # Re-read the chapter within the transaction
                chapter_doc = chapter_ref.get(transaction=transaction)
                if not chapter_doc.exists:
                    raise Exception(f"Chapter {chapter_id} no longer exists")
                
                current_data = chapter_doc.to_dict()
                versions = current_data.get('versions', [])
                
                # Check document size limit (approximate)
                import sys
                current_size = sys.getsizeof(str(current_data))
                version_size = sys.getsizeof(str(version_data))
                
                # Firestore limit is 1MB (1048576 bytes), leave some buffer
                if current_size + version_size > 900000:  # 900KB buffer
                    logger.warning(f"Chapter {chapter_id} approaching size limit. Current: {current_size} bytes")
                    # Could implement version archival here in the future
                
                # Create new version with correct version number
                new_version = version_data.copy()
                version_number = len(versions) + 1
                new_version.update({
                    'version_number': version_number,
                    'timestamp': datetime.now(timezone.utc)
                })
                
                # MIGRATION: Store in sub-collection to avoid 1 MiB limit
                # Create version document in sub-collection
                version_ref = chapter_ref.collection('versions').document(str(version_number))
                transaction.set(version_ref, new_version)
                
                # Only keep latest 3 versions in main document for backwards compatibility
                # and quick access, store rest in sub-collection
                if len(versions) >= 3:
                    # Move oldest version from main doc to sub-collection (if not already there)
                    oldest_version = versions.pop(0)
                    if 'version_number' in oldest_version:
                        old_version_ref = chapter_ref.collection('versions').document(str(oldest_version['version_number']))
                        transaction.set(old_version_ref, oldest_version)
                
                # Add new version to main document versions array (keeping last 3)
                versions.append(new_version)
                
                # Update chapter metadata and version count
                transaction.update(chapter_ref, {
                    'versions': versions,
                    'metadata.updated_at': datetime.now(timezone.utc),
                    'metadata.total_versions': version_number,  # Track total count
                    'metadata.latest_version': version_number
                })
                
                return True
            
            # Execute the transaction
            transaction = self.db.transaction()
            success = update_chapter_version_transaction(transaction)
            
            if success:
                logger.info(f"Version added to chapter {chapter_id}")
            return success
            
        except Exception as e:
            logger.error(f"Failed to add version to chapter {chapter_id}: {e}")
            return False
    
    async def get_chapter_versions(self, chapter_id: str, user_id: Optional[str] = None, project_id: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get all versions for a chapter, including from sub-collections."""
        try:
            chapter_ref = None
            
            # Find the chapter reference
            if user_id and project_id:
                chapter_ref = self.db.collection('users').document(user_id)\
                                     .collection('projects').document(project_id)\
                                     .collection('chapters').document(chapter_id)
                
                if not chapter_ref.get().exists:
                    chapter_ref = None
            
            # If no direct path or not found, scan for it
            if not chapter_ref:
                # Implementation similar to other methods - scan users/projects
                users_ref = self.db.collection('users')
                users = users_ref.stream()
                
                for user_doc in users:
                    temp_user_id = user_doc.id
                    projects_ref = self.db.collection('users').document(temp_user_id).collection('projects')
                    projects = projects_ref.stream()
                    
                    for project_doc in projects:
                        temp_project_id = project_doc.id
                        temp_chapter_ref = self.db.collection('users').document(temp_user_id)\
                                                  .collection('projects').document(temp_project_id)\
                                                  .collection('chapters').document(chapter_id)
                        
                        if temp_chapter_ref.get().exists:
                            chapter_ref = temp_chapter_ref
                            break
                    
                    if chapter_ref:
                        break
                
                # Try legacy collection if not found
                if not chapter_ref:
                    temp_ref = self.db.collection('chapters').document(chapter_id)
                    if temp_ref.get().exists:
                        chapter_ref = temp_ref
            
            if not chapter_ref:
                return []
            
            # Get versions from main document
            chapter_doc = chapter_ref.get()
            chapter_data = chapter_doc.to_dict() if chapter_doc.exists else {}
            main_versions = chapter_data.get('versions', [])
            
            # Get versions from sub-collection
            versions_ref = chapter_ref.collection('versions')
            if limit:
                versions_query = versions_ref.order_by('version_number', direction=firestore.Query.DESCENDING).limit(limit)
            else:
                versions_query = versions_ref.order_by('version_number', direction=firestore.Query.DESCENDING)
            
            sub_versions = []
            for version_doc in versions_query.stream():
                version_data = version_doc.to_dict()
                sub_versions.append(version_data)
            
            # Combine and deduplicate versions (sub-collection takes precedence)
            all_versions = {}
            
            # Add main document versions
            for version in main_versions:
                version_num = version.get('version_number')
                if version_num:
                    all_versions[version_num] = version
            
            # Add sub-collection versions (override main doc versions)
            for version in sub_versions:
                version_num = version.get('version_number')
                if version_num:
                    all_versions[version_num] = version
            
            # Sort by version number descending and return
            sorted_versions = sorted(all_versions.values(), key=lambda x: x.get('version_number', 0), reverse=True)
            
            if limit:
                return sorted_versions[:limit]
            return sorted_versions
            
        except Exception as e:
            logger.error(f"Failed to get versions for chapter {chapter_id}: {e}")
            return []
    
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
    
    async def create_cover_art_job(self, job_data: Dict[str, Any]) -> Optional[str]:
        """Create a new cover art job document."""
        try:
            job_id = job_data.get('job_id')
            if not job_id:
                job_id = str(uuid.uuid4())
                job_data['job_id'] = job_id
            
            # Set timestamps
            now = datetime.now(timezone.utc)
            job_data['created_at'] = now
            if 'updated_at' not in job_data:
                job_data['updated_at'] = now
            
            # Save to Firestore
            doc_ref = self.db.collection('cover_art_jobs').document(job_id)
            doc_ref.set(job_data)
            
            logger.info(f"Cover art job {job_id} created successfully")
            return job_id
            
        except Exception as e:
            logger.error(f"Failed to create cover art job: {e}")
            return None
    
    async def get_cover_art_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get cover art job document by ID."""
        try:
            doc_ref = self.db.collection('cover_art_jobs').document(job_id)
            doc = doc_ref.get()
            
            if doc.exists:
                return doc.to_dict()
            return None
            
        except Exception as e:
            logger.error(f"Failed to get cover art job {job_id}: {e}")
            return None
    
    async def update_cover_art_job(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """Update cover art job document."""
        try:
            updates['updated_at'] = datetime.now(timezone.utc)
            doc_ref = self.db.collection('cover_art_jobs').document(job_id)
            doc_ref.update(updates)
            
            logger.info(f"Cover art job {job_id} updated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update cover art job {job_id}: {e}")
            return False
    
    async def get_user_cover_art_jobs(self, user_id: str, project_id: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Get cover art jobs for a user, optionally filtered by project."""
        try:
            query = self.db.collection('cover_art_jobs').where(
                filter=FieldFilter('user_id', '==', user_id)
            )
            
            if project_id:
                query = query.where(filter=FieldFilter('project_id', '==', project_id))
                
            query = query.order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit)
            
            docs = query.stream()
            jobs = []
            for doc in docs:
                job_data = doc.to_dict()
                job_data['id'] = doc.id
                jobs.append(job_data)
            
            return jobs
            
        except Exception as e:
            logger.error(f"Failed to get user cover art jobs: {e}")
            return []

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
    # REFERENCE FILE OPERATIONS
    # =====================================================================
    
    async def create_reference_file(self, reference_data: Dict[str, Any]) -> Optional[str]:
        """Create a reference file document under user/project structure."""
        try:
            reference_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            
            project_id = reference_data.get('project_id')
            if not project_id:
                raise ValueError("project_id is required for reference file creation")
            
            # Find the user who owns this project
            user_id = None
            users_ref = self.db.collection('users')
            users = users_ref.stream()
            
            for user_doc in users:
                temp_user_id = user_doc.id
                project_ref = self.db.collection('users').document(temp_user_id)\
                                   .collection('projects').document(project_id)
                project_doc = project_ref.get()
                
                if project_doc.exists:
                    user_id = temp_user_id
                    break
            
            # If not found in user-scoped collections, try to get user from reference data
            if not user_id:
                user_id = reference_data.get('created_by')
                if not user_id:
                    raise ValueError(f"Cannot determine user_id for project {project_id}")
            
            # Prepare reference file data
            ref_file_data = {
                'reference_id': reference_id,
                'project_id': project_id,
                'filename': reference_data.get('filename', 'untitled.md'),
                'content': reference_data.get('content', ''),
                'created_by': reference_data.get('created_by', ''),
                'file_type': reference_data.get('file_type', 'reference'),
                'created_at': now,
                'updated_at': now,
                'last_modified': reference_data.get('last_modified', now),
                'modified_by': reference_data.get('created_by', ''),
                'size': len(reference_data.get('content', '')),
                'metadata': {
                    'word_count': len(reference_data.get('content', '').split()),
                    'line_count': len(reference_data.get('content', '').splitlines()),
                    'is_auto_generated': reference_data.get('is_auto_generated', False)
                }
            }
            
            # Save as subcollection under user/project structure
            doc_ref = self.db.collection('users').document(user_id)\
                             .collection('projects').document(project_id)\
                             .collection('reference_files').document(reference_id)
            doc_ref.set(ref_file_data)
            
            logger.info(f"Reference file {reference_data.get('filename')} created successfully for project {project_id} (user {user_id})")
            return reference_id
            
        except Exception as e:
            logger.error(f"Failed to create reference file: {e}")
            return None
    
    async def get_project_reference_files(self, project_id: str) -> List[Dict[str, Any]]:
        """Get all reference files for a project from user-scoped collections."""
        try:
            reference_files = []
            
            # Find the user who owns this project and get reference files
            users_ref = self.db.collection('users')
            users = users_ref.stream()
            
            for user_doc in users:
                user_id = user_doc.id
                project_ref = self.db.collection('users').document(user_id)\
                                   .collection('projects').document(project_id)
                project_doc = project_ref.get()
                
                if project_doc.exists:
                    # Found the project, now get its reference files
                    refs_ref = self.db.collection('users').document(user_id)\
                                      .collection('projects').document(project_id)\
                                      .collection('reference_files')
                    
                    query = refs_ref.order_by('created_at')
                    docs = query.stream()
                    reference_files = [doc.to_dict() for doc in docs]
                    break
            
            return reference_files
            
        except Exception as e:
            logger.error(f"Failed to get reference files for project {project_id}: {e}")
            return []
    
    async def update_reference_file(self, project_id: str, reference_id: str, updates: Dict[str, Any]) -> bool:
        """Update a reference file."""
        try:
            # Add update timestamp
            updates['updated_at'] = datetime.now(timezone.utc)
            
            doc_ref = self.db.collection('projects')\
                             .document(project_id)\
                             .collection('reference_files')\
                             .document(reference_id)
            doc_ref.update(updates)
            
            logger.info(f"Reference file {reference_id} updated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update reference file {reference_id}: {e}")
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