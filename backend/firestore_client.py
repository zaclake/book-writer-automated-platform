#!/usr/bin/env python3
"""
Firestore Client for Auto-Complete Book Backend
Handles persistent storage of job state and project data.
"""

import json
import logging
import os
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import asdict
from concurrent.futures import ThreadPoolExecutor

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FirestoreClient:
    """
    Firestore client for persistent storage.
    Simplified version that can work with or without actual Firestore.
    """
    
    def __init__(self, use_firestore: bool = False):
        self.use_firestore = use_firestore
        self.local_storage_path = "./local_storage"
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # Create local storage directory
        os.makedirs(self.local_storage_path, exist_ok=True)
        
        if use_firestore:
            try:
                # Try to import and initialize Firestore
                from google.cloud import firestore
                self.db = firestore.Client()
                logger.info("Firestore client initialized")
            except ImportError:
                logger.warning("Firestore not available, using local storage")
                self.use_firestore = False
            except Exception as e:
                logger.error(f"Failed to initialize Firestore: {e}")
                self.use_firestore = False
        else:
            logger.info("Using local file storage")
    
    def _get_local_file_path(self, collection: str, document_id: str) -> str:
        """Get local file path for document storage."""
        collection_dir = os.path.join(self.local_storage_path, collection)
        os.makedirs(collection_dir, exist_ok=True)
        return os.path.join(collection_dir, f"{document_id}.json")
    
    def _save_local_file(self, file_path: str, data: Dict[str, Any]) -> bool:
        """Save data to local file (blocking operation for thread pool)."""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            return True
        except Exception as e:
            logger.error(f"Failed to save local file {file_path}: {e}")
            return False
    
    def _load_local_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Load data from local file (blocking operation for thread pool)."""
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return None
        except Exception as e:
            logger.error(f"Failed to load local file {file_path}: {e}")
            return None
    
    async def save_job(self, job_id: str, job_data: Dict[str, Any]) -> bool:
        """
        Save job data to storage.
        
        Args:
            job_id: Job identifier
            job_data: Job data to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Add timestamp
            job_data['updated_at'] = datetime.utcnow().isoformat()
            
            if self.use_firestore:
                # Save to Firestore (run in thread pool)
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    self.executor,
                    lambda: self.db.collection('jobs').document(job_id).set(job_data)
                )
            else:
                # Save to local file (run in thread pool)
                file_path = self._get_local_file_path('jobs', job_id)
                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(
                    self.executor,
                    self._save_local_file,
                    file_path,
                    job_data
                )
                if not success:
                    return False
            
            logger.info(f"Job {job_id} saved successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save job {job_id}: {e}")
            return False
    
    async def load_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Load job data from storage.
        
        Args:
            job_id: Job identifier
            
        Returns:
            Job data or None if not found
        """
        try:
            if self.use_firestore:
                # Load from Firestore (run in thread pool)
                loop = asyncio.get_event_loop()
                doc = await loop.run_in_executor(
                    self.executor,
                    lambda: self.db.collection('jobs').document(job_id).get()
                )
                if doc.exists:
                    return doc.to_dict()
            else:
                # Load from local file (run in thread pool)
                file_path = self._get_local_file_path('jobs', job_id)
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    self.executor,
                    self._load_local_file,
                    file_path
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to load job {job_id}: {e}")
            return None
    
    async def list_user_jobs(self, user_id: str, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        """
        List jobs for a specific user.
        
        Args:
            user_id: User identifier
            limit: Maximum number of jobs to return
            offset: Number of jobs to skip
            
        Returns:
            List of job data
        """
        try:
            jobs = []
            
            if self.use_firestore:
                # Query Firestore
                query = self.db.collection('jobs').where('user_id', '==', user_id)
                query = query.order_by('created_at', direction=firestore.Query.DESCENDING)
                query = query.limit(limit).offset(offset)
                
                docs = query.stream()
                for doc in docs:
                    job_data = doc.to_dict()
                    job_data['job_id'] = doc.id
                    jobs.append(job_data)
            else:
                # Load from local files
                jobs_dir = os.path.join(self.local_storage_path, 'jobs')
                if os.path.exists(jobs_dir):
                    job_files = sorted(os.listdir(jobs_dir), reverse=True)
                    
                    for job_file in job_files[offset:offset + limit]:
                        if job_file.endswith('.json'):
                            job_id = job_file[:-5]  # Remove .json extension
                            job_data = await self.load_job(job_id)
                            if job_data and job_data.get('user_id') == user_id:
                                job_data['job_id'] = job_id
                                jobs.append(job_data)
            
            return jobs
            
        except Exception as e:
            logger.error(f"Failed to list jobs for user {user_id}: {e}")
            return []
    
    async def delete_job(self, job_id: str) -> bool:
        """
        Delete job from storage.
        
        Args:
            job_id: Job identifier
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if self.use_firestore:
                # Delete from Firestore
                doc_ref = self.db.collection('jobs').document(job_id)
                doc_ref.delete()
            else:
                # Delete local file
                file_path = self._get_local_file_path('jobs', job_id)
                if os.path.exists(file_path):
                    os.remove(file_path)
            
            logger.info(f"Job {job_id} deleted successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete job {job_id}: {e}")
            return False
    
    async def save_project_data(self, project_id: str, project_data: Dict[str, Any]) -> bool:
        """
        Save project data to storage.
        
        Args:
            project_id: Project identifier
            project_data: Project data to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Add timestamp
            project_data['updated_at'] = datetime.utcnow().isoformat()
            
            if self.use_firestore:
                # Save to Firestore
                doc_ref = self.db.collection('projects').document(project_id)
                doc_ref.set(project_data)
            else:
                # Save to local file
                file_path = self._get_local_file_path('projects', project_id)
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(project_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Project {project_id} saved successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save project {project_id}: {e}")
            return False
    
    async def load_project_data(self, project_id: str) -> Optional[Dict[str, Any]]:
        """
        Load project data from storage.
        
        Args:
            project_id: Project identifier
            
        Returns:
            Project data or None if not found
        """
        try:
            if self.use_firestore:
                # Load from Firestore
                doc_ref = self.db.collection('projects').document(project_id)
                doc = doc_ref.get()
                if doc.exists:
                    return doc.to_dict()
            else:
                # Load from local file
                file_path = self._get_local_file_path('projects', project_id)
                if os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        return json.load(f)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to load project {project_id}: {e}")
            return None
    
    async def cleanup_old_jobs(self, max_age_days: int = 7) -> int:
        """
        Clean up old jobs from storage.
        
        Args:
            max_age_days: Maximum age of jobs to keep
            
        Returns:
            Number of jobs cleaned up
        """
        try:
            cleaned_count = 0
            cutoff_date = datetime.utcnow().timestamp() - (max_age_days * 24 * 60 * 60)
            
            if self.use_firestore:
                # Query old jobs from Firestore
                query = self.db.collection('jobs').where('created_at', '<', datetime.fromtimestamp(cutoff_date))
                docs = query.stream()
                
                for doc in docs:
                    doc.reference.delete()
                    cleaned_count += 1
            else:
                # Clean up local files
                jobs_dir = os.path.join(self.local_storage_path, 'jobs')
                if os.path.exists(jobs_dir):
                    for job_file in os.listdir(jobs_dir):
                        if job_file.endswith('.json'):
                            file_path = os.path.join(jobs_dir, job_file)
                            file_stat = os.stat(file_path)
                            
                            if file_stat.st_mtime < cutoff_date:
                                os.remove(file_path)
                                cleaned_count += 1
            
            logger.info(f"Cleaned up {cleaned_count} old jobs")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup old jobs: {e}")
            return 0
    
    async def get_storage_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics.
        
        Returns:
            Storage statistics
        """
        try:
            stats = {
                'storage_type': 'firestore' if self.use_firestore else 'local',
                'total_jobs': 0,
                'total_projects': 0,
                'storage_size_mb': 0
            }
            
            if self.use_firestore:
                # Count Firestore documents
                jobs_count = len(list(self.db.collection('jobs').stream()))
                projects_count = len(list(self.db.collection('projects').stream()))
                
                stats['total_jobs'] = jobs_count
                stats['total_projects'] = projects_count
            else:
                # Count local files
                jobs_dir = os.path.join(self.local_storage_path, 'jobs')
                projects_dir = os.path.join(self.local_storage_path, 'projects')
                
                if os.path.exists(jobs_dir):
                    stats['total_jobs'] = len([f for f in os.listdir(jobs_dir) if f.endswith('.json')])
                
                if os.path.exists(projects_dir):
                    stats['total_projects'] = len([f for f in os.listdir(projects_dir) if f.endswith('.json')])
                
                # Calculate storage size
                total_size = 0
                for root, dirs, files in os.walk(self.local_storage_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        total_size += os.path.getsize(file_path)
                
                stats['storage_size_mb'] = round(total_size / (1024 * 1024), 2)
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get storage stats: {e}")
            return {'error': str(e)}

# Global client instance
firestore_client = FirestoreClient(use_firestore=False)  # Start with local storage 