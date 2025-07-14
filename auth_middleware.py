#!/usr/bin/env python3
"""
Authentication Middleware for Auto-Complete Book Backend
Handles Clerk JWT token validation and user authentication.
"""

import os
import logging
import requests
from typing import Dict, Optional
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ClerkAuthMiddleware:
    """
    Clerk JWT authentication middleware.
    Validates JWT tokens and extracts user information.
    """
    
    def __init__(self):
        self.clerk_secret_key = os.getenv('CLERK_SECRET_KEY')
        # Hardcoded fallback for publishable key (safe to expose)
        self.clerk_publishable_key = os.getenv('CLERK_PUBLISHABLE_KEY') or 'pk_live_Y2xlcmsud3JpdGVyYmxvb20uY29tJA'
        self.clerk_jwt_issuer = os.getenv('CLERK_JWT_ISSUER')
        self.development_mode = os.getenv('ENVIRONMENT') == 'development'
        
        # Initialize JWKS client for Clerk
        self.jwks_client = None
        if self.clerk_publishable_key:
            # Extract the instance ID from the publishable key
            if self.clerk_publishable_key.startswith('pk_test_') or self.clerk_publishable_key.startswith('pk_live_'):
                # For newer Clerk versions, use the instance-specific JWKS URL
                jwks_url = f"https://clerk.{self.clerk_publishable_key.split('_')[2]}.lcl.dev/.well-known/jwks.json"
                if self.clerk_publishable_key.startswith('pk_live_'):
                    jwks_url = f"https://clerk.{self.clerk_publishable_key.split('_')[2]}.com/.well-known/jwks.json"
                self.jwks_client = PyJWKClient(jwks_url)
                logger.info(f"Initialized JWKS client with URL: {jwks_url}")
        
        if not self.clerk_publishable_key and not self.development_mode:
            logger.critical("CRITICAL: Backend started without CLERK_PUBLISHABLE_KEY - all authenticated routes will fail with 500")
            logger.critical("Please set CLERK_PUBLISHABLE_KEY environment variable or set ENVIRONMENT=development")
        elif not self.clerk_publishable_key:
            logger.warning("CLERK_PUBLISHABLE_KEY not set - authentication will be disabled in development mode")
    
    def verify_token(self, credentials: Optional[HTTPAuthorizationCredentials]) -> Dict[str, str]:
        """
        Verify JWT token and extract user information.
        
        Args:
            credentials: HTTP authorization credentials
            
        Returns:
            User information dictionary
            
        Raises:
            HTTPException: If token is invalid or expired
        """
        # Development mode bypass - allow requests without credentials
        if self.development_mode:
            logger.info("Development mode: bypassing authentication")
            return {
                "user_id": "dev-user-123",
                "email": "dev@example.com",
                "first_name": "Dev",
                "last_name": "User"
            }
        
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        token = credentials.credentials
        
        if not self.jwks_client:
            logger.error("JWKS client not available - CLERK_PUBLISHABLE_KEY missing or invalid")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication service not properly configured: CLERK_PUBLISHABLE_KEY missing or invalid"
            )
        
        try:
            # Get the signing key from JWKS
            # Dynamically build JWKS client from token issuer (safer than relying on env var)
            # First decode header & issuer claim without verification
            unverified_payload = jwt.decode(token, options={"verify_signature": False})
            issuer = unverified_payload.get("iss")
            if issuer and issuer.startswith("https://"):
                jwks_url_dynamic = f"{issuer}/.well-known/jwks.json"
                try:
                    # Cache per issuer to avoid repeated network calls
                    if not hasattr(self, "_jwks_cache"):
                        self._jwks_cache = {}
                    if jwks_url_dynamic not in self._jwks_cache:
                        self._jwks_cache[jwks_url_dynamic] = PyJWKClient(jwks_url_dynamic)
                    dynamic_client = self._jwks_cache[jwks_url_dynamic]
                    signing_key = dynamic_client.get_signing_key_from_jwt(token)
                except Exception as e:
                    logger.warning(f"Dynamic JWKS fetch failed: {e}; falling back to static client")
                    signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            else:
                signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            
            # Decode JWT token using the public key
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                options={"verify_exp": True, "verify_aud": False}
            )
            
            # Extract user information
            user_info = {
                "user_id": payload.get("sub"),
                "email": payload.get("email"),
                "first_name": payload.get("given_name"),
                "last_name": payload.get("family_name"),
                "session_id": payload.get("sid"),
                "issued_at": payload.get("iat"),
                "expires_at": payload.get("exp")
            }
            
            # Validate required fields
            if not user_info["user_id"]:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token: missing user ID"
                )
            
            logger.info(f"User authenticated: {user_info['user_id']}")
            return user_info
            
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception as e:
            logger.error(f"Token verification failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication failed",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    def get_user_permissions(self, user_info: Dict[str, str]) -> Dict[str, bool]:
        """
        Get user permissions based on user information.
        
        Args:
            user_info: User information from token
            
        Returns:
            Permissions dictionary
        """
        # Basic permissions for all authenticated users
        permissions = {
            "can_create_jobs": True,
            "can_view_own_jobs": True,
            "can_control_own_jobs": True,
            "can_delete_own_jobs": True,
            "can_access_api": True
        }
        
        # Add admin permissions if needed
        # This could be extended to check user roles from Clerk
        admin_users = os.getenv('ADMIN_USERS', '').split(',')
        if user_info.get('email') in admin_users:
            permissions.update({
                "can_view_all_jobs": True,
                "can_control_all_jobs": True,
                "can_delete_all_jobs": True,
                "can_access_admin": True
            })
        
        return permissions
    
    def validate_user_access(self, user_info: Dict[str, str], resource_user_id: str) -> bool:
        """
        Validate if user has access to a specific resource.
        
        Args:
            user_info: User information from token
            resource_user_id: User ID that owns the resource
            
        Returns:
            True if user has access, False otherwise
        """
        # User can access their own resources
        if user_info.get('user_id') == resource_user_id:
            return True
        
        # Check if user has admin permissions
        permissions = self.get_user_permissions(user_info)
        if permissions.get('can_view_all_jobs', False):
            return True
        
        return False

# Global middleware instance
auth_middleware = ClerkAuthMiddleware()

# Security scheme for FastAPI
security = HTTPBearer(auto_error=False)

async def verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Dict[str, str]:
    """
    FastAPI dependency for token verification.
    
    Args:
        credentials: HTTP authorization credentials
        
    Returns:
        User information dictionary
    """
    return auth_middleware.verify_token(credentials)

async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Dict[str, str]:
    """
    FastAPI dependency for getting current user.
    
    Args:
        credentials: HTTP authorization credentials
        
    Returns:
        User information dictionary with permissions
    """
    user_info = auth_middleware.verify_token(credentials)
    user_info['permissions'] = auth_middleware.get_user_permissions(user_info)
    return user_info

def require_permission(permission: str):
    """
    Decorator to require specific permission.
    
    Args:
        permission: Required permission name
        
    Returns:
        Dependency function
    """
    async def permission_dependency(user: Dict[str, str] = None) -> Dict[str, str]:
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )
        
        permissions = user.get('permissions', {})
        if not permissions.get(permission, False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {permission}"
            )
        
        return user
    
    return permission_dependency 