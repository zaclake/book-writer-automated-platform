#!/usr/bin/env python3
"""
Users Router V2 - Enhanced User Management
Handles user profiles, preferences, and onboarding with Clerk integration.
"""

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict, Any, Optional
import logging
from datetime import datetime, timezone

# Robust imports that work from both repo root and backend directory
try:
    from backend.models.firestore_models import (
        User, UserProfile, UserPreferences, UserUsage, UserLimits
    )
    from backend.services.firestore_service import FirestoreService
    from backend.auth_middleware import ClerkAuthMiddleware
except ImportError:
    # Fallback when running from backend directory
    from models.firestore_models import (
        User, UserProfile, UserPreferences, UserUsage, UserLimits
    )
    from services.firestore_service import FirestoreService
    from auth_middleware import ClerkAuthMiddleware

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v2/users", tags=["users-v2"])

# Initialize services
auth_middleware = ClerkAuthMiddleware()
firestore_service = FirestoreService()
security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current authenticated user."""
    return auth_middleware.verify_token(credentials)

@router.get("/profile")
async def get_user_profile(current_user: Dict[str, str] = Depends(get_current_user)):
    """Get user profile information."""
    try:
        user_id = current_user["user_id"]
        
        # Try to get existing user from Firestore
        user_data = await firestore_service.get_user(user_id)
        
        if not user_data:
            # Create default user profile if it doesn't exist
            default_profile = UserProfile(
                clerk_id=user_id,
                email=current_user.get("email", ""),
                name=current_user.get("first_name", "") + " " + current_user.get("last_name", ""),
                created_at=datetime.now(timezone.utc),
                last_active=datetime.now(timezone.utc)
            )
            
            default_user = User(
                profile=default_profile,
                usage=UserUsage(),
                preferences=UserPreferences(),
                limits=UserLimits()
            )
            
            # Save default user to Firestore
            await firestore_service.create_user(default_user.dict())
            return default_profile.dict()
        
        return user_data.get("profile", {})
        
    except Exception as e:
        logger.error(f"Error getting user profile for {current_user['user_id']}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user profile"
        )

@router.put("/profile")
async def update_user_profile(
    profile_data: Dict[str, Any],
    current_user: Dict[str, str] = Depends(get_current_user)
):
    """Update user profile information."""
    try:
        user_id = current_user["user_id"]
        
        # Get existing user data
        user_data = await firestore_service.get_user(user_id)
        
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found"
            )
        
        # Validate profile data
        if "preferred_word_count" in profile_data:
            word_count = profile_data["preferred_word_count"]
            if word_count is not None and (word_count < 500 or word_count > 10000):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Preferred word count must be between 500 and 10000"
                )
        
        # Update profile data
        current_profile = user_data.get("profile", {})
        current_profile.update(profile_data)
        current_profile["last_active"] = datetime.now(timezone.utc)
        
        # Save updated profile
        await firestore_service.update_user(user_id, {"profile": current_profile})
        
        return {"success": True, "message": "Profile updated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user profile for {current_user['user_id']}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user profile"
        )

@router.get("/preferences")
async def get_user_preferences(current_user: Dict[str, str] = Depends(get_current_user)):
    """Get user preferences."""
    try:
        user_id = current_user["user_id"]
        user_data = await firestore_service.get_user(user_id)
        
        if not user_data:
            return UserPreferences().dict()
        
        return user_data.get("preferences", UserPreferences().dict())
        
    except Exception as e:
        logger.error(f"Error getting user preferences for {current_user['user_id']}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user preferences"
        )

@router.put("/preferences")
async def update_user_preferences(
    preferences_data: Dict[str, Any],
    current_user: Dict[str, str] = Depends(get_current_user)
):
    """Update user preferences."""
    try:
        user_id = current_user["user_id"]
        
        # Get existing user data
        user_data = await firestore_service.get_user(user_id)
        
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Update preferences
        current_preferences = user_data.get("preferences", {})
        current_preferences.update(preferences_data)
        
        # Save updated preferences
        await firestore_service.update_user(user_id, {"preferences": current_preferences})
        
        return {"success": True, "message": "Preferences updated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user preferences for {current_user['user_id']}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user preferences"
        )

@router.get("/usage")
async def get_user_usage(current_user: Dict[str, str] = Depends(get_current_user)):
    """Get user usage statistics."""
    try:
        user_id = current_user["user_id"]
        user_data = await firestore_service.get_user(user_id)
        
        if not user_data:
            return UserUsage().dict()
        
        return user_data.get("usage", UserUsage().dict())
        
    except Exception as e:
        logger.error(f"Error getting user usage for {current_user['user_id']}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user usage"
        )

@router.post("/onboarding")
async def complete_onboarding(
    onboarding_data: Dict[str, Any],
    current_user: Dict[str, str] = Depends(get_current_user)
):
    """Complete user onboarding with purpose and involvement level."""
    try:
        user_id = current_user["user_id"]
        
        # Get or create user data
        user_data = await firestore_service.get_user(user_id)
        if not user_data:
            # Create new user
            default_profile = UserProfile(
                clerk_id=user_id,
                email=current_user.get("email", ""),
                name=current_user.get("first_name", "") + " " + current_user.get("last_name", ""),
                created_at=datetime.now(timezone.utc),
                last_active=datetime.now(timezone.utc)
            )
            
            user_data = User(
                profile=default_profile,
                usage=UserUsage(),
                preferences=UserPreferences(),
                limits=UserLimits()
            ).dict()
        
        # Update preferences with onboarding data
        preferences = user_data.get("preferences", {})
        if "purpose" in onboarding_data:
            preferences["purpose"] = onboarding_data["purpose"]
        if "involvement_level" in onboarding_data:
            preferences["involvement_level"] = onboarding_data["involvement_level"]
        if "writing_experience" in onboarding_data:
            preferences["writing_experience"] = onboarding_data["writing_experience"]
        if "genre_preference" in onboarding_data:
            preferences["default_genre"] = onboarding_data["genre_preference"]
        
        # Mark onboarding as completed
        preferences["onboarding_completed"] = True
        preferences["onboarding_completed_at"] = datetime.now(timezone.utc)
        
        # Update user data
        user_data["preferences"] = preferences
        
        # Save to Firestore
        if user_data.get("profile", {}).get("created_at"):
            await firestore_service.update_user(user_id, user_data)
        else:
            await firestore_service.create_user(user_data)
        
        return {"success": True, "message": "Onboarding completed successfully"}
        
    except Exception as e:
        logger.error(f"Error completing onboarding for {current_user['user_id']}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete onboarding"
        ) 