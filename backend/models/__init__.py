"""
Models Package for Book Writing Automation System
Contains all Pydantic models for data validation and serialization.
"""

from .firestore_models import *

__all__ = [
    # User models
    'User', 'UserProfile', 'UserUsage', 'UserPreferences', 'UserLimits',
    
    # Project models  
    'Project', 'ProjectMetadata', 'BookBible', 'ReferenceFile', 'ProjectReferences',
    'ProjectSettings', 'QualityBaseline', 'ProjectProgress', 'StoryContinuity',
    
    # Chapter models
    'Chapter', 'ChapterMetadata', 'QualityScores', 'ChapterVersion', 'ContextData',
    
    # Generation job models
    'GenerationJob', 'JobProgress', 'JobConfig', 'AutoCompleteData', 'JobResults',
    
    # Request/Response models
    'CreateProjectRequest', 'UpdateProjectRequest', 'CreateChapterRequest',
    'ProjectListResponse', 'ChapterListResponse',
    
    # Enums
    'SubscriptionTier', 'ProjectStatus', 'ProjectVisibility', 'ChapterStage',
    'JobStatus', 'JobType'
] 