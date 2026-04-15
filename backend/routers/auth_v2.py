#!/usr/bin/env python3
"""
Auth Router V2 - Simple email/password auth with sessions.
"""

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Dict
import logging

try:
    from backend.services.simple_auth_service import SimpleAuthService
except Exception:
    from services.simple_auth_service import SimpleAuthService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v2/auth", tags=["auth-v2"])
security = HTTPBearer(auto_error=False)
auth_service = SimpleAuthService()


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=6, max_length=128)
    name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=6, max_length=128)


@router.post("/register")
async def register_user(payload: RegisterRequest):
    try:
        if "@" not in payload.email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email")
        user = auth_service.create_user(payload.email, payload.password, payload.name)
        session_token = auth_service.create_session(user["user_id"])
        return {
            "user": {
                "id": user["user_id"],
                "email": user["email"],
                "name": user.get("name", ""),
            },
            "session_token": session_token,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Registration failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed",
        )


@router.post("/login")
async def login_user(payload: LoginRequest):
    try:
        if "@" not in payload.email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email")
        user = auth_service.authenticate_user(payload.email, payload.password)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        session_token = auth_service.create_session(user["user_id"])
        return {
            "user": {
                "id": user["user_id"],
                "email": user.get("email", ""),
                "name": user.get("name", ""),
            },
            "session_token": session_token,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed",
        )


@router.get("/me")
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing session token")

    session = auth_service.get_session(credentials.credentials)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")

    profile = auth_service.get_user_profile(session["user_id"]) or {}
    return {
        "user": {
            "id": session["user_id"],
            "email": profile.get("email", ""),
            "name": profile.get("name", ""),
        }
    }


@router.post("/logout")
async def logout_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing session token")

    auth_service.revoke_session(credentials.credentials)
    return {"success": True}
