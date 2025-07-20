"""
Services Package for Book Writing Automation System
Contains all service layer implementations for data operations.
"""

from .firestore_service import FirestoreService, UserProfile, ProjectMetadata, ChapterMetadata

__all__ = [
    'FirestoreService',
    'UserProfile', 
    'ProjectMetadata',
    'ChapterMetadata'
] 