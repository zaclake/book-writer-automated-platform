#!/usr/bin/env python3
"""
Test script to debug import issues in the backend
"""

import sys
import os
sys.path.insert(0, 'backend')

print("=== Testing Backend Imports ===")

try:
    print("1. Testing basic FastAPI imports...")
    from fastapi import FastAPI, APIRouter
    print("✅ FastAPI imports successful")
except Exception as e:
    print(f"❌ FastAPI imports failed: {e}")
    exit(1)

try:
    print("2. Testing models imports...")
    from backend.models.firestore_models import (
        Project, CreateProjectRequest, UpdateProjectRequest, 
        ProjectListResponse, ProjectMetadata, ProjectSettings,
        BookBible, ReferenceFile, BookLengthTier
    )
    print("✅ Models imports successful")
except Exception as e:
    print(f"❌ Models imports failed: {e}")
    print(f"Error details: {type(e).__name__}: {e}")

try:
    print("3. Testing database_integration imports...")
    from backend.database_integration import (
        get_user_projects, create_project, get_project,
        migrate_project_from_filesystem, track_usage,
        get_database_adapter, create_reference_file
    )
    print("✅ Database integration imports successful")
except Exception as e:
    print(f"❌ Database integration imports failed: {e}")
    print(f"Error details: {type(e).__name__}: {e}")

try:
    print("4. Testing auth_middleware imports...")
    from backend.auth_middleware import get_current_user
    print("✅ Auth middleware imports successful")
except Exception as e:
    print(f"❌ Auth middleware imports failed: {e}")
    print(f"Error details: {type(e).__name__}: {e}")

try:
    print("5. Testing router imports...")
    from backend.routers import projects_v2, chapters_v2, users_v2
    print("✅ Router imports successful")
    print(f"Projects router: {projects_v2}")
    print(f"Chapters router: {chapters_v2}")
    print(f"Users router: {users_v2}")
except Exception as e:
    print(f"❌ Router imports failed: {e}")
    print(f"Error details: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

print("=== Test Complete ===") 