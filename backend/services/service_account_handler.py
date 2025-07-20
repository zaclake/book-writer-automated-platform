#!/usr/bin/env python3
"""
Service Account Handler for Railway Deployment
Handles the SERVICE_ACCOUNT_JSON environment variable for Firestore authentication.
"""

import os
import json
import tempfile
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def setup_service_account_credentials():
    """
    Set up Firestore service account credentials for Railway deployment.
    
    Railway doesn't support file uploads, so we pass the service account JSON
    as an environment variable and write it to a temporary file.
    """
    try:
        # Check if we're using Firestore
        use_firestore = os.getenv('USE_FIRESTORE', 'false').lower() == 'true'
        if not use_firestore:
            logger.info("Firestore not enabled, skipping service account setup")
            return
        
        # Check if GOOGLE_APPLICATION_CREDENTIALS is already set to a file
        existing_creds = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        if existing_creds and os.path.isfile(existing_creds):
            logger.info(f"Using existing service account file: {existing_creds}")
            return
        
        # Get service account JSON from environment variable
        service_account_json = os.getenv('SERVICE_ACCOUNT_JSON')
        if not service_account_json:
            logger.warning("SERVICE_ACCOUNT_JSON environment variable not found. Firestore may not work properly.")
            return
        
        # Parse the JSON to validate it
        try:
            service_account_data = json.loads(service_account_json)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in SERVICE_ACCOUNT_JSON: {e}")
            return
        
        # Create a temporary file for the service account
        # In Railway, we'll write to /app which is writable
        app_dir = Path("/app")
        if app_dir.exists() and app_dir.is_dir():
            # Railway deployment
            credentials_file = app_dir / "service-account-key.json"
        else:
            # Local development
            credentials_file = Path("./service-account-key.json")
        
        # Write the service account JSON to file
        with open(credentials_file, 'w', encoding='utf-8') as f:
            json.dump(service_account_data, f, indent=2)
        
        # Set the environment variable to point to our file
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(credentials_file)
        
        logger.info(f"✅ Service account credentials set up at: {credentials_file}")
        
        # Verify the project ID matches
        project_id = service_account_data.get('project_id')
        expected_project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
        
        if project_id and expected_project_id and project_id != expected_project_id:
            logger.warning(f"Project ID mismatch: service account has '{project_id}' but GOOGLE_CLOUD_PROJECT is '{expected_project_id}'")
        elif project_id:
            logger.info(f"✅ Service account configured for project: {project_id}")
        
    except Exception as e:
        logger.error(f"Failed to set up service account credentials: {e}")
        # Don't raise - we want the app to start even if Firestore setup fails

def cleanup_service_account_credentials():
    """Clean up temporary service account file on shutdown."""
    try:
        credentials_file = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        if credentials_file and os.path.isfile(credentials_file):
            # Only delete if it's our temporary file
            if 'service-account-key.json' in credentials_file:
                os.remove(credentials_file)
                logger.info(f"✅ Cleaned up service account file: {credentials_file}")
    except Exception as e:
        logger.error(f"Failed to cleanup service account file: {e}") 