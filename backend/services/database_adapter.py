#!/usr/bin/env python3
"""
Database Adapter for Book Writing Automation System
Bridges existing file-based operations with Firestore service layer.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Union
from pathlib import Path

from .firestore_service import FirestoreService

logger = logging.getLogger(__name__)

class DatabaseAdapter:
    """
    Adapter class that provides a unified interface for data operations.
    Can work with both Firestore and local file storage for development.
    """
    
    def __init__(self, use_firestore: bool = True, firestore_project_id: Optional[str] = None):
        """Initialize the database adapter."""
        self.use_firestore = use_firestore
        self.local_storage_path = Path("./local_storage")
        
        if use_firestore:
            try:
                self.firestore = FirestoreService(project_id=firestore_project_id)
                # Check if Firestore is actually available
                if hasattr(self.firestore, 'available') and not self.firestore.available:
                    logger.warning("Firestore service initialized but not available, falling back to local storage")
                    self.use_firestore = False
                else:
                    logger.info("Database adapter initialized with Firestore")
            except Exception as e:
                logger.error(f"Failed to initialize Firestore, falling back to local storage: {e}")
                self.use_firestore = False
                self.firestore = None
        else:
            self.firestore = None
            logger.info("Database adapter initialized with local storage")
        
        # Ensure local storage directory exists
        self.local_storage_path.mkdir(exist_ok=True)
    
    # =====================================================================
    # MIGRATION HELPERS - Bridge old file operations to new schema
    # =====================================================================
    
    async def migrate_project_from_filesystem(self, project_path: str, user_id: str) -> Optional[str]:
        """
        Migrate an existing project from filesystem to Firestore.
        Handles current .project-meta.json and directory structure.
        """
        try:
            project_dir = Path(project_path)
            if not project_dir.exists():
                logger.error(f"Project directory not found: {project_path}")
                return None
            
            # Load existing project metadata
            meta_file = project_dir / ".project-meta.json"
            if meta_file.exists():
                with open(meta_file, 'r', encoding='utf-8') as f:
                    old_meta = json.load(f)
            else:
                old_meta = {}
            
            # Read book bible
            book_bible_content = ""
            book_bible_file = project_dir / "book-bible.md"
            if book_bible_file.exists():
                with open(book_bible_file, 'r', encoding='utf-8') as f:
                    book_bible_content = f.read()
            
            # Read reference files
            references = {}
            references_dir = project_dir / "references"
            if references_dir.exists():
                for ref_file in references_dir.glob("*.md"):
                    ref_name = ref_file.stem
                    try:
                        with open(ref_file, 'r', encoding='utf-8') as f:
                            references[ref_name] = {
                                'content': f.read(),
                                'last_modified': datetime.now(timezone.utc),
                                'modified_by': user_id
                            }
                    except Exception as e:
                        logger.warning(f"Failed to read reference file {ref_file}: {e}")
            
            # Create new project structure
            project_data = {
                'metadata': {
                    'title': old_meta.get('projectName', 'Migrated Project'),
                    'owner_id': user_id,
                    'collaborators': [],
                    'status': 'active',
                    'visibility': 'private'
                },
                'book_bible': {
                    'content': book_bible_content,
                    'last_modified': datetime.now(timezone.utc),
                    'modified_by': user_id,
                    'version': 1,
                    'word_count': len(book_bible_content.split())
                },
                'references': references,
                'settings': {
                    'genre': old_meta.get('genre', 'Fiction'),
                    'target_chapters': old_meta.get('totalChaptersPlanned', 25),
                    'word_count_per_chapter': 2000,
                    'target_audience': 'General',
                    'writing_style': 'Professional',
                    'quality_gates_enabled': True,
                    'auto_completion_enabled': False
                }
            }
            
            # Create project in Firestore
            if self.use_firestore:
                project_id = await self.firestore.create_project(project_data)
                if project_id:
                    logger.info(f"Project migrated successfully: {project_id}")
                    
                    # Migrate chapters
                    await self._migrate_chapters_from_filesystem(project_dir, project_id, user_id)
                    
                    return project_id
            else:
                # Save to local storage for development
                project_id = str(uuid.uuid4())
                project_data['metadata']['project_id'] = project_id
                
                projects_dir = self.local_storage_path / "projects"
                projects_dir.mkdir(exist_ok=True)
                
                with open(projects_dir / f"{project_id}.json", 'w', encoding='utf-8') as f:
                    json.dump(project_data, f, indent=2, default=str)
                
                return project_id
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to migrate project: {e}")
            return None
    
    async def _migrate_chapters_from_filesystem(self, project_dir: Path, project_id: str, user_id: str):
        """Migrate chapters from filesystem to Firestore."""
        try:
            chapters_dir = project_dir / "chapters"
            if not chapters_dir.exists():
                return
            
            for chapter_file in chapters_dir.glob("chapter-*.md"):
                try:
                    # Extract chapter number
                    chapter_num_str = chapter_file.stem.split('-')[1]
                    chapter_number = int(chapter_num_str)
                    
                    # Read chapter content
                    with open(chapter_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Look for corresponding JSON metadata
                    json_file = chapter_file.with_suffix('.json')
                    metadata = {}
                    if json_file.exists():
                        with open(json_file, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                    
                    # Create chapter document
                    chapter_data = {
                        'project_id': project_id,
                        'chapter_number': chapter_number,
                        'content': content,
                        'metadata': {
                            'word_count': len(content.split()),
                            'target_word_count': metadata.get('target_words', 2000),
                            'created_by': user_id,
                            'stage': metadata.get('stage', 'complete'),
                            'generation_time': metadata.get('generation_time', 0.0),
                            'retry_attempts': metadata.get('retry_attempts', 0),
                            'model_used': metadata.get('model', 'gpt-4o'),
                            'tokens_used': metadata.get('tokens_used', {}),
                            'cost_breakdown': metadata.get('cost_breakdown', {})
                        }
                    }
                    
                    if self.use_firestore:
                        chapter_id = await self.firestore.create_chapter(chapter_data)
                        if chapter_id:
                            logger.info(f"Chapter {chapter_number} migrated successfully")
                    
                except Exception as e:
                    logger.error(f"Failed to migrate chapter {chapter_file}: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to migrate chapters: {e}")
    
    # =====================================================================
    # UNIFIED DATA OPERATIONS
    # =====================================================================
    
    async def get_user_projects(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all projects for a user."""
        if self.use_firestore:
            return await self.firestore.get_user_projects(user_id)
        else:
            # Local storage implementation
            projects = []
            projects_dir = self.local_storage_path / "projects"
            if projects_dir.exists():
                for project_file in projects_dir.glob("*.json"):
                    try:
                        with open(project_file, 'r', encoding='utf-8') as f:
                            project_data = json.load(f)
                        
                        # Check if user has access
                        owner_id = project_data.get('metadata', {}).get('owner_id')
                        collaborators = project_data.get('metadata', {}).get('collaborators', [])
                        
                        if owner_id == user_id or user_id in collaborators:
                            projects.append(project_data)
                    except Exception as e:
                        logger.error(f"Failed to load project {project_file}: {e}")
            
            return projects
    
    async def create_project(self, project_data: Dict[str, Any]) -> Optional[str]:
        """Create a new project."""
        if self.use_firestore:
            return await self.firestore.create_project(project_data)
        else:
            # Local storage implementation
            import uuid
            project_id = str(uuid.uuid4())
            project_data['metadata']['project_id'] = project_id
            
            projects_dir = self.local_storage_path / "projects"
            projects_dir.mkdir(exist_ok=True)
            
            try:
                with open(projects_dir / f"{project_id}.json", 'w', encoding='utf-8') as f:
                    json.dump(project_data, f, indent=2, default=str)
                return project_id
            except Exception as e:
                logger.error(f"Failed to create project locally: {e}")
                return None
    
    async def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get project by ID."""
        if self.use_firestore:
            return await self.firestore.get_project(project_id)
        else:
            # Local storage implementation
            project_file = self.local_storage_path / "projects" / f"{project_id}.json"
            if project_file.exists():
                try:
                    with open(project_file, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except Exception as e:
                    logger.error(f"Failed to load project {project_id}: {e}")
            return None
    
    async def get_project_chapters(self, project_id: str) -> List[Dict[str, Any]]:
        """Get all chapters for a project."""
        if self.use_firestore:
            return await self.firestore.get_project_chapters(project_id)
        else:
            # Local storage implementation - simplified for now
            chapters = []
            chapters_dir = self.local_storage_path / "chapters"
            if chapters_dir.exists():
                for chapter_file in chapters_dir.glob("*.json"):
                    try:
                        with open(chapter_file, 'r', encoding='utf-8') as f:
                            chapter_data = json.load(f)
                        
                        if chapter_data.get('project_id') == project_id:
                            chapters.append(chapter_data)
                    except Exception as e:
                        logger.error(f"Failed to load chapter {chapter_file}: {e}")
            
            # Sort by chapter number
            chapters.sort(key=lambda x: x.get('chapter_number', 0))
            return chapters
    
    async def create_chapter(self, chapter_data: Dict[str, Any]) -> Optional[str]:
        """Create a new chapter."""
        if self.use_firestore:
            return await self.firestore.create_chapter(chapter_data)
        else:
            # Local storage implementation
            import uuid
            chapter_id = str(uuid.uuid4())
            chapter_data['chapter_id'] = chapter_id
            
            chapters_dir = self.local_storage_path / "chapters"
            chapters_dir.mkdir(exist_ok=True)
            
            try:
                with open(chapters_dir / f"{chapter_id}.json", 'w', encoding='utf-8') as f:
                    json.dump(chapter_data, f, indent=2, default=str)
                return chapter_id
            except Exception as e:
                logger.error(f"Failed to create chapter locally: {e}")
                return None
    
    async def track_usage(self, user_id: str, usage_data: Dict[str, Any]) -> bool:
        """Track usage for billing and quotas."""
        if self.use_firestore:
            return await self.firestore.track_usage(user_id, usage_data)
        else:
            # Local storage implementation - simplified
            usage_dir = self.local_storage_path / "usage"
            usage_dir.mkdir(exist_ok=True)
            
            now = datetime.now(timezone.utc)
            month_year = now.strftime('%Y-%m')
            usage_file = usage_dir / f"{month_year}-{user_id}.json"
            
            try:
                if usage_file.exists():
                    with open(usage_file, 'r', encoding='utf-8') as f:
                        current_data = json.load(f)
                else:
                    current_data = {
                        'user_id': user_id,
                        'month_year': month_year,
                        'monthly_totals': {}
                    }
                
                # Update totals (simplified)
                for key, value in usage_data.items():
                    current_data['monthly_totals'][key] = \
                        current_data['monthly_totals'].get(key, 0) + value
                
                current_data['updated_at'] = now.isoformat()
                
                with open(usage_file, 'w', encoding='utf-8') as f:
                    json.dump(current_data, f, indent=2, default=str)
                
                return True
            except Exception as e:
                logger.error(f"Failed to track usage locally: {e}")
                return False
    
    # =====================================================================
    # REFERENCE FILE OPERATIONS
    # =====================================================================
    
    async def create_reference_file(self, reference_data: Dict[str, Any]) -> Optional[str]:
        """Create a reference file."""
        if self.use_firestore:
            return await self.firestore.create_reference_file(reference_data)
        else:
            # Local storage fallback
            try:
                project_id = reference_data.get('project_id')
                filename = reference_data.get('filename', 'untitled.md')
                content = reference_data.get('content', '')
                
                if not project_id:
                    logger.error("project_id is required for reference file creation")
                    return None
                
                # Create project references directory
                project_refs_dir = self.local_storage_path / 'projects' / project_id / 'references'
                project_refs_dir.mkdir(parents=True, exist_ok=True)
                
                # Write content to file
                ref_file_path = project_refs_dir / filename
                with open(ref_file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                # Create metadata file
                metadata = {
                    'reference_id': str(uuid.uuid4()),
                    'filename': filename,
                    'created_by': reference_data.get('created_by', ''),
                    'created_at': datetime.now(timezone.utc).isoformat(),
                    'file_size': len(content),
                    'word_count': len(content.split())
                }
                
                meta_file_path = project_refs_dir / f"{filename}.meta.json"
                with open(meta_file_path, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2)
                
                logger.info(f"Reference file {filename} created locally for project {project_id}")
                return metadata['reference_id']
                
            except Exception as e:
                logger.error(f"Failed to create reference file locally: {e}")
                return None

    # =====================================================================
    # HEALTH CHECK
    # =====================================================================
    
    async def health_check(self) -> Dict[str, Any]:
        """Check database health."""
        if self.use_firestore:
            firestore_healthy = await self.firestore.health_check()
            return {
                'database_type': 'firestore',
                'healthy': firestore_healthy,
                'details': 'Firestore connection successful' if firestore_healthy else 'Firestore connection failed'
            }
        else:
            local_healthy = self.local_storage_path.exists()
            return {
                'database_type': 'local_storage',
                'healthy': local_healthy,
                'details': f'Local storage at {self.local_storage_path}'
            }
    
    # =====================================================================
    # CONFIGURATION
    # =====================================================================
    
    @classmethod
    def from_environment(cls) -> 'DatabaseAdapter':
        """Create database adapter from environment variables."""
        use_firestore = os.getenv('USE_FIRESTORE', 'true').lower() == 'true'
        firestore_project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
        
        return cls(
            use_firestore=use_firestore,
            firestore_project_id=firestore_project_id
        ) 