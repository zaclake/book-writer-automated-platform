#!/usr/bin/env python3
"""
Tests for Publishing Router
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from datetime import datetime, timezone

from backend.main import app
from backend.models.firestore_models import PublishConfig, PublishFormat

# Test client
client = TestClient(app)

@pytest.fixture
def mock_user():
    """Mock authenticated user."""
    return {"user_id": "user123", "email": "test@example.com"}

@pytest.fixture
def sample_publish_config():
    """Sample publishing configuration."""
    return {
        "title": "Test Book",
        "author": "Test Author",
        "formats": ["epub", "pdf"],
        "dedication": "To my readers"
    }

@pytest.fixture
def mock_project():
    """Mock project data."""
    return {
        "metadata": {
            "owner_id": "user123",
            "collaborators": []
        },
        "title": "Test Book"
    }

class TestPublishRouter:
    """Test cases for publishing router."""
    
    def test_start_publish_job_success(self, mock_user, sample_publish_config, mock_project):
        """Test successful job submission."""
        with patch('backend.routers.publish_v2.get_current_user', return_value=mock_user), \
             patch('backend.routers.publish_v2.get_project', return_value=mock_project), \
             patch('backend.routers.publish_v2.get_job_processor') as mock_processor:
            
            # Mock job processor
            mock_proc_instance = Mock()
            mock_proc_instance.submit_job = AsyncMock(return_value="job123")
            mock_processor.return_value = mock_proc_instance
            
            response = client.post(
                "/v2/publish/project/project123",
                json=sample_publish_config
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["job_id"] == "job123"
            assert data["status"] == "submitted"
    
    def test_start_publish_job_unauthorized(self, sample_publish_config):
        """Test job submission without authentication."""
        with patch('backend.routers.publish_v2.get_current_user', side_effect=Exception("Unauthorized")):
            response = client.post(
                "/v2/publish/project/project123",
                json=sample_publish_config
            )
            
            assert response.status_code == 500  # Exception handling
    
    def test_start_publish_job_project_not_found(self, mock_user, sample_publish_config):
        """Test job submission for non-existent project."""
        with patch('backend.routers.publish_v2.get_current_user', return_value=mock_user), \
             patch('backend.routers.publish_v2.get_project', return_value=None):
            
            response = client.post(
                "/v2/publish/project/nonexistent",
                json=sample_publish_config
            )
            
            assert response.status_code == 404
            assert "not found" in response.json()["detail"]
    
    def test_start_publish_job_access_denied(self, mock_user, sample_publish_config):
        """Test job submission for project without access."""
        # Project owned by different user
        different_project = {
            "metadata": {
                "owner_id": "other_user",
                "collaborators": []
            }
        }
        
        with patch('backend.routers.publish_v2.get_current_user', return_value=mock_user), \
             patch('backend.routers.publish_v2.get_project', return_value=different_project):
            
            response = client.post(
                "/v2/publish/project/project123",
                json=sample_publish_config
            )
            
            assert response.status_code == 403
            assert "Access denied" in response.json()["detail"]
    
    def test_get_job_status_success(self, mock_user):
        """Test successful job status retrieval."""
        # Mock job data
        mock_job = Mock()
        mock_job.job_id = "job123"
        mock_job.status.value = "completed"
        mock_job.user_id = "user123"
        mock_job.created_at = datetime.now(timezone.utc)
        mock_job.started_at = datetime.now(timezone.utc)
        mock_job.completed_at = datetime.now(timezone.utc)
        mock_job.progress.current_step = "Completed"
        mock_job.progress.progress_percentage = 100.0
        mock_job.progress.last_update = datetime.now().isoformat()
        mock_job.result = {"epub_url": "https://example.com/book.epub"}
        
        with patch('backend.routers.publish_v2.get_current_user', return_value=mock_user), \
             patch('backend.routers.publish_v2.get_job_processor') as mock_processor:
            
            mock_proc_instance = Mock()
            mock_proc_instance.get_job.return_value = mock_job
            mock_processor.return_value = mock_proc_instance
            
            response = client.get("/v2/publish/job123")
            
            assert response.status_code == 200
            data = response.json()
            assert data["job_id"] == "job123"
            assert data["status"] == "completed"
            assert "result" in data
    
    def test_get_job_status_not_found(self, mock_user):
        """Test job status for non-existent job."""
        with patch('backend.routers.publish_v2.get_current_user', return_value=mock_user), \
             patch('backend.routers.publish_v2.get_job_processor') as mock_processor:
            
            mock_proc_instance = Mock()
            mock_proc_instance.get_job.return_value = None
            mock_processor.return_value = mock_proc_instance
            
            response = client.get("/v2/publish/nonexistent")
            
            assert response.status_code == 404
            assert "not found" in response.json()["detail"]
    
    def test_get_job_status_access_denied(self, mock_user):
        """Test job status access for job owned by different user."""
        # Mock job owned by different user
        mock_job = Mock()
        mock_job.job_id = "job123"
        mock_job.user_id = "other_user"
        
        with patch('backend.routers.publish_v2.get_current_user', return_value=mock_user), \
             patch('backend.routers.publish_v2.get_job_processor') as mock_processor:
            
            mock_proc_instance = Mock()
            mock_proc_instance.get_job.return_value = mock_job
            mock_processor.return_value = mock_proc_instance
            
            response = client.get("/v2/publish/job123")
            
            assert response.status_code == 403
            assert "Access denied" in response.json()["detail"]
    
    def test_get_project_publish_history_success(self, mock_user, mock_project):
        """Test successful project history retrieval."""
        mock_history = {
            "history": [
                {
                    "job_id": "job123",
                    "epub_url": "https://example.com/book.epub",
                    "created_at": "2024-01-01T00:00:00Z"
                }
            ],
            "latest": {
                "job_id": "job123",
                "epub_url": "https://example.com/book.epub"
            }
        }
        
        with patch('backend.routers.publish_v2.get_current_user', return_value=mock_user), \
             patch('backend.routers.publish_v2.get_project', return_value=mock_project), \
             patch('backend.routers.publish_v2.get_firestore_client') as mock_db:
            
            # Mock Firestore response
            mock_doc = Mock()
            mock_doc.get.return_value.exists = True
            mock_doc.get.return_value.to_dict.return_value = {"publishing": mock_history}
            mock_db.return_value.collection.return_value.document.return_value = mock_doc
            
            response = client.get("/v2/publish/project/project123/history")
            
            assert response.status_code == 200
            data = response.json()
            assert data["project_id"] == "project123"
            assert len(data["history"]) == 1
            assert data["latest"]["job_id"] == "job123"
    
    def test_get_project_publish_history_empty(self, mock_user, mock_project):
        """Test project history for project with no publishing history."""
        with patch('backend.routers.publish_v2.get_current_user', return_value=mock_user), \
             patch('backend.routers.publish_v2.get_project', return_value=mock_project), \
             patch('backend.routers.publish_v2.get_firestore_client') as mock_db:
            
            # Mock Firestore response with no publishing data
            mock_doc = Mock()
            mock_doc.get.return_value.exists = True
            mock_doc.get.return_value.to_dict.return_value = {}
            mock_db.return_value.collection.return_value.document.return_value = mock_doc
            
            response = client.get("/v2/publish/project/project123/history")
            
            assert response.status_code == 200
            data = response.json()
            assert data["project_id"] == "project123"
            assert data["history"] == []
            assert data["latest"] is None
    
    def test_save_publish_result_success(self, mock_user, mock_project):
        """Test successful result saving."""
        result_data = {
            "job_id": "job123",
            "project_id": "project123",
            "status": "completed",
            "config": {
                "title": "Test Book",
                "author": "Test Author",
                "formats": ["epub"]
            },
            "epub_url": "https://example.com/book.epub",
            "created_at": "2024-01-01T00:00:00Z",
            "completed_at": "2024-01-01T00:01:00Z"
        }
        
        with patch('backend.routers.publish_v2.get_current_user', return_value=mock_user), \
             patch('backend.routers.publish_v2.get_project', return_value=mock_project), \
             patch('backend.routers.publish_v2.get_firestore_client') as mock_db:
            
            # Mock Firestore operations
            mock_doc = Mock()
            mock_doc.get.return_value.exists = True
            mock_doc.get.return_value.to_dict.return_value = {"publishing": {"history": []}}
            mock_db.return_value.collection.return_value.document.return_value = mock_doc
            
            response = client.post(
                "/v2/publish/project/project123/save-result",
                json=result_data
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "saved"
            
            # Verify Firestore update was called
            mock_doc.update.assert_called_once()

@pytest.mark.asyncio
async def test_router_startup_shutdown():
    """Test router startup and shutdown events."""
    from backend.routers.publish_v2 import startup_event, shutdown_event
    
    with patch('backend.routers.publish_v2.get_job_processor') as mock_processor:
        mock_proc_instance = Mock()
        mock_proc_instance.start = AsyncMock()
        mock_proc_instance.shutdown = AsyncMock()
        mock_processor.return_value = mock_proc_instance
        
        # Test startup
        await startup_event()
        mock_proc_instance.start.assert_called_once()
        
        # Test shutdown
        await shutdown_event()
        mock_proc_instance.shutdown.assert_called_once() 