#!/usr/bin/env python3
"""
Simple Auth Service
Provides low-cost email/password auth with session tokens.
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

from google.cloud.firestore_v1.base_query import FieldFilter

from .firestore_service import FirestoreService

logger = logging.getLogger(__name__)

AUTH_USERS_COLLECTION = "auth_users"
AUTH_SESSIONS_COLLECTION = "auth_sessions"
SESSION_TTL_DAYS = 30


class SimpleAuthService:
    """Auth service backed by Firestore or local JSON storage."""

    def __init__(self):
        self.firestore = FirestoreService()
        self.use_firestore = bool(getattr(self.firestore, "available", False) and getattr(self.firestore, "db", None))
        self.db = getattr(self.firestore, "db", None) if self.use_firestore else None

        self.local_storage_path = Path("./local_storage")
        self.local_storage_path.mkdir(exist_ok=True)
        self._local_users_path = self.local_storage_path / "auth_users.json"
        self._local_sessions_path = self.local_storage_path / "auth_sessions.json"

    def _normalize_email(self, email: str) -> str:
        return (email or "").strip().lower()

    def _hash_password(self, password: str, salt: Optional[bytes] = None) -> Dict[str, str]:
        if salt is None:
            salt = secrets.token_bytes(16)
        derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
        return {
            "password_hash": base64.b64encode(derived).decode("utf-8"),
            "password_salt": base64.b64encode(salt).decode("utf-8"),
        }

    def _verify_password(self, password: str, salt_b64: str, hash_b64: str) -> bool:
        try:
            salt = base64.b64decode(salt_b64)
            expected = base64.b64decode(hash_b64)
            derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
            return hmac.compare_digest(derived, expected)
        except Exception:
            return False

    def _load_local(self, path: Path) -> Dict[str, Dict]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_local(self, path: Path, payload: Dict[str, Dict]) -> None:
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    def _ensure_user_profile(self, user_id: str, email: str, name: str) -> None:
        if not self.use_firestore:
            return
        try:
            user_doc = self.db.collection("users").document(user_id).get()
            if user_doc.exists:
                return

            now = datetime.now(timezone.utc)
            profile_payload = {
                "profile": {
                    "clerk_id": user_id,
                    "email": email,
                    "name": name,
                    "subscription_tier": "free",
                    "avatar_url": None,
                    "created_at": now,
                    "last_active": now,
                    "timezone": "UTC",
                },
                "usage": {
                    "monthly_cost": 0.0,
                    "chapters_generated": 0,
                    "api_calls": 0,
                    "words_generated": 0,
                    "projects_created": 0,
                    "last_reset_date": now,
                },
                "preferences": {
                    "default_genre": "Fiction",
                    "default_word_count": 2000,
                    "quality_strictness": "standard",
                    "auto_backup_enabled": True,
                    "collaboration_notifications": True,
                    "email_notifications": True,
                    "preferred_llm_model": "gpt-4.1",
                },
                "limits": {
                    "monthly_cost_limit": 50.0,
                    "monthly_chapter_limit": 100,
                    "concurrent_projects_limit": 5,
                    "storage_limit_mb": 1000,
                },
            }
            self.db.collection("users").document(user_id).set(profile_payload)
        except Exception as e:
            logger.warning(f"Failed to create user profile for {user_id}: {e}")

    def create_user(self, email: str, password: str, name: str) -> Dict[str, str]:
        normalized_email = self._normalize_email(email)
        if not normalized_email:
            raise ValueError("Email is required")
        if not password:
            raise ValueError("Password is required")

        if self.use_firestore:
            existing = (
                self.db.collection(AUTH_USERS_COLLECTION)
                .where(filter=FieldFilter("email", "==", normalized_email))
                .limit(1)
                .get()
            )
            if existing:
                raise ValueError("Email already registered")
            user_id = str(uuid.uuid4())
            password_payload = self._hash_password(password)
            now = datetime.now(timezone.utc)
            auth_payload = {
                "user_id": user_id,
                "email": normalized_email,
                "name": name.strip() if name else "",
                "password_hash": password_payload["password_hash"],
                "password_salt": password_payload["password_salt"],
                "created_at": now,
                "last_login": now,
            }
            self.db.collection(AUTH_USERS_COLLECTION).document(user_id).set(auth_payload)
            self._ensure_user_profile(user_id, normalized_email, auth_payload["name"])
            return {"user_id": user_id, "email": normalized_email, "name": auth_payload["name"]}

        users = self._load_local(self._local_users_path)
        for record in users.values():
            if record.get("email") == normalized_email:
                raise ValueError("Email already registered")
        user_id = str(uuid.uuid4())
        password_payload = self._hash_password(password)
        users[user_id] = {
            "user_id": user_id,
            "email": normalized_email,
            "name": name.strip() if name else "",
            "password_hash": password_payload["password_hash"],
            "password_salt": password_payload["password_salt"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_login": datetime.now(timezone.utc).isoformat(),
        }
        self._save_local(self._local_users_path, users)
        return {"user_id": user_id, "email": normalized_email, "name": users[user_id]["name"]}

    def authenticate_user(self, email: str, password: str) -> Optional[Dict[str, str]]:
        normalized_email = self._normalize_email(email)
        if not normalized_email or not password:
            return None

        if self.use_firestore:
            matches = (
                self.db.collection(AUTH_USERS_COLLECTION)
                .where(filter=FieldFilter("email", "==", normalized_email))
                .limit(1)
                .get()
            )
            if not matches:
                return None
            auth_doc = matches[0].to_dict()
            if not self._verify_password(password, auth_doc["password_salt"], auth_doc["password_hash"]):
                return None
            user_id = auth_doc["user_id"]
            self.db.collection(AUTH_USERS_COLLECTION).document(user_id).update(
                {"last_login": datetime.now(timezone.utc)}
            )
            self._ensure_user_profile(user_id, auth_doc.get("email", normalized_email), auth_doc.get("name", ""))
            return {"user_id": user_id, "email": auth_doc.get("email", normalized_email), "name": auth_doc.get("name", "")}

        users = self._load_local(self._local_users_path)
        for record in users.values():
            if record.get("email") == normalized_email:
                if self._verify_password(password, record["password_salt"], record["password_hash"]):
                    record["last_login"] = datetime.now(timezone.utc).isoformat()
                    users[record["user_id"]] = record
                    self._save_local(self._local_users_path, users)
                    return {"user_id": record["user_id"], "email": record.get("email", normalized_email), "name": record.get("name", "")}
                return None
        return None

    def create_session(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=SESSION_TTL_DAYS)

        if self.use_firestore:
            payload = {
                "token": token,
                "user_id": user_id,
                "created_at": now,
                "expires_at": expires_at,
            }
            self.db.collection(AUTH_SESSIONS_COLLECTION).document(token).set(payload)
            return token

        sessions = self._load_local(self._local_sessions_path)
        sessions[token] = {
            "token": token,
            "user_id": user_id,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        self._save_local(self._local_sessions_path, sessions)
        return token

    def get_session(self, token: str) -> Optional[Dict[str, str]]:
        if not token:
            return None

        if self.use_firestore:
            doc = self.db.collection(AUTH_SESSIONS_COLLECTION).document(token).get()
            if not doc.exists:
                return None
            data = doc.to_dict()
            expires_at = data.get("expires_at")
            if expires_at and isinstance(expires_at, datetime) and expires_at < datetime.now(timezone.utc):
                self.db.collection(AUTH_SESSIONS_COLLECTION).document(token).delete()
                return None
            return {"token": token, "user_id": data.get("user_id")}

        sessions = self._load_local(self._local_sessions_path)
        data = sessions.get(token)
        if not data:
            return None
        try:
            expires_at = datetime.fromisoformat(data.get("expires_at"))
            if expires_at < datetime.now(timezone.utc):
                sessions.pop(token, None)
                self._save_local(self._local_sessions_path, sessions)
                return None
        except Exception:
            pass
        return {"token": token, "user_id": data.get("user_id")}

    def revoke_session(self, token: str) -> None:
        if not token:
            return
        if self.use_firestore:
            self.db.collection(AUTH_SESSIONS_COLLECTION).document(token).delete()
            return
        sessions = self._load_local(self._local_sessions_path)
        if token in sessions:
            sessions.pop(token, None)
            self._save_local(self._local_sessions_path, sessions)

    def get_user_profile(self, user_id: str) -> Optional[Dict[str, str]]:
        if not user_id:
            return None
        if self.use_firestore:
            doc = self.db.collection("users").document(user_id).get()
            if not doc.exists:
                return None
            data = doc.to_dict() or {}
            return data.get("profile", {})
        return None
