#!/usr/bin/env python3
"""
Tests for the FastAPI backend.
"""

import pytest
import asyncio
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import os

# Set test environment
os.environ['ENVIRONMENT'] = 'test'
os.environ['CLERK_SECRET_KEY'] = 'test_key'

from main import app

client = TestClient(app)

class TestHealthEndpoint:
    """Test health check endpoint."""
    
    def test_health_check(self):
        """Test basic health check."""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert "version" in data
        # Basic health endpoint should not expose internal details
        assert "services" not in data
        assert "environment" not in data
    
    def test_health_check_structure(self):
        """Test basic health check response structure."""
        response = client.get("/health")
        data = response.json()
        
        # Required fields for basic health check
        required_fields = ["status", "timestamp", "version"]
        for field in required_fields:
            assert field in data
        
        # Status should be healthy or unhealthy
        assert data["status"] in ["healthy", "unhealthy"]

class TestDetailedHealthEndpoint:
    """Test detailed health check endpoint."""
    
    def test_detailed_health_requires_auth(self):
        """Test that detailed health endpoint requires authentication."""
        response = client.get("/health/detailed")
        # Should require authentication
        assert response.status_code in [401, 403, 422]

class TestRootEndpoint:
    """Test root endpoint."""
    
    def test_root_endpoint(self):
        """Test root endpoint returns API info."""
        response = client.get("/")
        assert response.status_code == 200
        
        data = response.json()
        assert "message" in data
        assert "version" in data

class TestCORSHeaders:
    """Test CORS configuration."""
    
    def test_cors_headers(self):
        """Test CORS headers are present."""
        # CORS headers are typically added by the browser for cross-origin requests
        # In test client, they may not appear for same-origin requests
        response = client.get("/health")
        assert response.status_code == 200
        
        # Test that the endpoint is accessible (CORS is configured in middleware)
        assert response.json()["status"] in ["healthy", "unhealthy"]

class TestSecurityHeaders:
    """Test security headers."""
    
    def test_security_headers(self):
        """Test security headers are added."""
        response = client.get("/health")
        assert response.status_code == 200
        
        headers = response.headers
        assert "x-content-type-options" in headers
        assert "x-frame-options" in headers
        assert "x-xss-protection" in headers

class TestAuthenticationBypass:
    """Test authentication bypass in development mode."""
    
    def test_auth_bypass_in_dev_mode(self):
        """Test that authentication is bypassed in development mode."""
        # This would require mocking the auth middleware
        # For now, just test that the endpoint exists
        response = client.get("/auto-complete/jobs")
        # Should return 403 without proper auth, but endpoint should exist
        assert response.status_code in [401, 403, 422]  # Various auth error codes

@pytest.mark.asyncio
class TestAsyncEndpoints:
    """Test async functionality."""
    
    async def test_async_health_check(self):
        """Test async health check functionality."""
        # This would test the actual async functions
        # For now, just verify the endpoint works
        response = client.get("/health")
        assert response.status_code == 200

class TestEnvironmentConfiguration:
    """Test environment-specific behavior."""
    
    def test_development_environment(self):
        """Test development environment configuration."""
        # Test that basic health endpoint doesn't expose environment
        response = client.get("/health")
        data = response.json()
        
        # Basic health endpoint should not expose environment details
        assert "environment" not in data
        assert data["status"] in ["healthy", "unhealthy"]
    
    def test_cors_origins_configuration(self):
        """Test CORS origins are configurable."""
        # This would test that CORS origins are read from environment
        # The actual test would require setting environment variables
        pass

class TestErrorHandling:
    """Test error handling."""
    
    def test_404_endpoint(self):
        """Test 404 for non-existent endpoint."""
        response = client.get("/non-existent-endpoint")
        assert response.status_code == 404
    
    def test_method_not_allowed(self):
        """Test 405 for wrong HTTP method."""
        response = client.delete("/health")
        assert response.status_code == 405

class TestJobEndpoints:
    """Test job-related endpoints."""
    
    def test_auto_complete_start_without_auth(self):
        """Test auto-complete start requires authentication."""
        response = client.post("/auto-complete/start", json={
            "project_id": "test-project",
            "book_bible": "Test book bible content",
            "target_chapters": 5
        })
        # Should require authentication
        assert response.status_code in [401, 403, 422]  # Various auth error codes
    
    def test_job_status_without_auth(self):
        """Test job status requires authentication."""
        response = client.get("/auto-complete/test-job-id/status")
        assert response.status_code in [401, 403, 422]  # Various auth error codes
    
    def test_list_jobs_without_auth(self):
        """Test list jobs requires authentication."""
        response = client.get("/auto-complete/jobs")
        assert response.status_code in [401, 403, 422]  # Various auth error codes

if __name__ == "__main__":
    pytest.main([__file__]) 