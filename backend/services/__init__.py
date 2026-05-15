"""
Services Package for Book Writing Automation System
Contains all service layer implementations for data operations.
"""

# Firestore service depends on google-cloud-firestore. In environments where
# that isn't installed (e.g. local test harnesses for craft services like
# bible_enrichment that don't need Firestore), don't fail the whole package
# import — just leave the names unset and let downstream imports report a
# clear error.
try:
    from .firestore_service import FirestoreService, UserProfile, ProjectMetadata, ChapterMetadata  # noqa: F401
    __all__ = [
        'FirestoreService',
        'UserProfile',
        'ProjectMetadata',
        'ChapterMetadata',
    ]
except Exception as _firestore_import_err:  # pragma: no cover - environment-specific
    import logging as _logging
    _logging.getLogger(__name__).debug(
        "google-cloud-firestore not available; firestore_service exports skipped: %s",
        _firestore_import_err,
    )
    __all__ = []
