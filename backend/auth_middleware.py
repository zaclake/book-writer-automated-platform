#!/usr/bin/env python3
"""
Authentication Middleware for Auto-Complete Book Backend.
Supports optional lightweight sessions for per-user project isolation.
"""

import logging
from typing import Dict, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

# Anonymous user for unauthenticated requests
ANONYMOUS_USER = {
    "user_id": "anonymous-user",
    "email": "anonymous@localhost",
    "first_name": "Anonymous",
    "last_name": "User"
}

try:
    from backend.services.simple_auth_service import SimpleAuthService
except Exception:
    from services.simple_auth_service import SimpleAuthService


class SimpleAuthMiddleware:
    """
    Lightweight authentication middleware.
    Uses session tokens when present; falls back to anonymous user otherwise.
    """

    def __init__(self):
        self.auth_service = SimpleAuthService()
        logger.info("Auth middleware initialized (anonymous fallback enabled)")

    def verify_token(self, credentials: Optional[HTTPAuthorizationCredentials]) -> Dict[str, str]:
        """
        Validate session token if provided; return anonymous user when missing.
        """
        if not credentials or not credentials.credentials:
            logger.debug("No auth token provided; using anonymous user")
            return ANONYMOUS_USER.copy()

        session = self.auth_service.get_session(credentials.credentials)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session"
            )

        user_profile = self.auth_service.get_user_profile(session["user_id"]) or {}
        full_name = (user_profile.get("name") or "").strip()
        first_name = full_name.split(" ")[0] if full_name else ""
        last_name = " ".join(full_name.split(" ")[1:]) if full_name else ""

        return {
            "user_id": session["user_id"],
            "email": user_profile.get("email", ""),
            "first_name": first_name or user_profile.get("first_name", ""),
            "last_name": last_name or user_profile.get("last_name", "")
        }

    def get_user_permissions(self, user_info: Dict[str, str]) -> Dict[str, bool]:
        """
        Returns full permissions for authenticated/anonymous users.
        """
        return {
            "can_create_jobs": True,
            "can_view_own_jobs": True,
            "can_control_own_jobs": True,
            "can_delete_own_jobs": True,
            "can_access_api": True,
            "can_view_all_jobs": True,
            "can_control_all_jobs": True,
            "can_delete_all_jobs": True,
            "can_access_admin": True
        }

    def validate_user_access(self, user_info: Dict[str, str], resource_user_id: str) -> bool:
        """
        Basic access check for user-owned resources.
        """
        return user_info.get("user_id") == resource_user_id or user_info.get("user_id") == "anonymous-user"

# Global middleware instance
auth_middleware = SimpleAuthMiddleware()

# Security scheme for FastAPI (kept for API compatibility but auto_error=False)
security = HTTPBearer(auto_error=False)

async def verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Dict[str, str]:
    """
    FastAPI dependency - returns authenticated or anonymous user.
    """
    return auth_middleware.verify_token(credentials)

async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Dict[str, str]:
    """
    FastAPI dependency - returns user with permissions.
    """
    user_info = auth_middleware.verify_token(credentials)
    user_info["permissions"] = auth_middleware.get_user_permissions(user_info)
    return user_info

def require_permission(permission: str):
    """
    Decorator - returns user with permissions (no deny logic).
    """
    async def permission_dependency(user: Dict[str, str] = None) -> Dict[str, str]:
        user_info = ANONYMOUS_USER.copy()
        user_info["permissions"] = auth_middleware.get_user_permissions(user_info)
        return user_info

    return permission_dependency
