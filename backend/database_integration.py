#!/usr/bin/env python3
"""
Database Integration Module
Provides database adapter instances for the application.
"""

import os
import logging
from services.database_adapter import DatabaseAdapter

logger = logging.getLogger(__name__)

def get_database_adapter():
    """
    Get a configured database adapter instance.
    
    Returns:
        DatabaseAdapter: Configured adapter instance
    """
    # Check environment variables
    use_firestore = os.getenv('USE_FIRESTORE', 'false').lower() == 'true'
    firestore_project_id = os.getenv('GOOGLE_CLOUD_PROJECT', 'writer-bloom')
    
    logger.info(f"Creating database adapter: use_firestore={use_firestore}, project_id={firestore_project_id}")
    
    # Create and return adapter
    adapter = DatabaseAdapter(
        use_firestore=use_firestore,
        firestore_project_id=firestore_project_id
    )
    
    return adapter 