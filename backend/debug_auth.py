#!/usr/bin/env python3
"""
Debug endpoint for authentication configuration
"""

import os
import logging
from fastapi import APIRouter, HTTPException
from typing import Dict, Any

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/debug/auth-config")
async def debug_auth_config() -> Dict[str, Any]:
    """
    Debug endpoint to check authentication configuration.
    Returns environment variable status without exposing sensitive values.
    """
    
    clerk_publishable_key = os.getenv('CLERK_PUBLISHABLE_KEY')
    clerk_secret_key = os.getenv('CLERK_SECRET_KEY')
    
    # Parse publishable key to construct JWKS URL
    jwks_url = None
    if clerk_publishable_key:
        if clerk_publishable_key.startswith('pk_test_') or clerk_publishable_key.startswith('pk_live_'):
            instance_id = clerk_publishable_key.split('_')[2] if len(clerk_publishable_key.split('_')) > 2 else 'unknown'
            if clerk_publishable_key.startswith('pk_live_'):
                jwks_url = f"https://clerk.{instance_id}.com/.well-known/jwks.json"
            else:
                jwks_url = f"https://clerk.{instance_id}.lcl.dev/.well-known/jwks.json"
    
    return {
        "environment": os.getenv('ENVIRONMENT', 'production'),
        "clerk_config": {
            "has_publishable_key": bool(clerk_publishable_key),
            "has_secret_key": bool(clerk_secret_key),
            "publishable_key_prefix": clerk_publishable_key[:20] + "..." if clerk_publishable_key else None,
            "jwks_url": jwks_url,
            "development_mode": os.getenv('ENVIRONMENT') == 'development'
        },
        "cors_origins": os.getenv('CORS_ORIGINS', '').split(',') if os.getenv('CORS_ORIGINS') else [],
        "timestamp": "2025-07-11T16:40:00Z"
    }

@router.get("/debug/test-auth")
async def test_auth_simple():
    """
    Simple test endpoint that doesn't require authentication.
    """
    return {
        "message": "Backend is accessible",
        "timestamp": "2025-07-11T16:40:00Z",
        "status": "ok"
    } 