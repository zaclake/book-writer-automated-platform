#!/usr/bin/env python3
"""
Regression tests for deterministic chapter ordering when Firestore cannot order_by.
"""

import pytest
from unittest.mock import MagicMock


@pytest.mark.asyncio
async def test_get_project_chapters_sorted_when_orderby_fails():
    from backend.services.firestore_service import FirestoreService

    service = FirestoreService()

    # Build a fake Firestore chain:
    # db.collection('users').stream() -> [user_doc]
    # project_doc.exists -> True
    # chapters_ref.order_by('chapter_number') -> raises (simulate missing index)
    # chapters_ref.stream() -> docs out of order
    user_doc = MagicMock()
    user_doc.id = "u1"

    project_doc = MagicMock()
    project_doc.exists = True

    doc2 = MagicMock()
    doc2.id = "c2"
    doc2.to_dict.return_value = {"chapter_number": 2, "content": "two"}
    doc1 = MagicMock()
    doc1.id = "c1"
    doc1.to_dict.return_value = {"chapter_number": 1, "content": "one"}
    doc3 = MagicMock()
    doc3.id = "c3"
    doc3.to_dict.return_value = {"chapter_number": 3, "content": "three"}

    chapters_ref = MagicMock()
    chapters_ref.order_by.side_effect = Exception("missing index")
    chapters_ref.stream.return_value = [doc2, doc1, doc3]

    # Stitch the reference chain
    projects_collection = MagicMock()
    projects_collection.document.return_value.get.return_value = project_doc
    projects_collection.document.return_value.collection.return_value.document.return_value.get.return_value = project_doc

    # users/u1/projects/<project_id>/chapters -> chapters_ref
    user_doc_ref = MagicMock()
    user_doc_ref.collection.return_value.document.return_value.get.return_value = project_doc
    user_doc_ref.collection.return_value.document.return_value.collection.return_value = chapters_ref

    users_collection = MagicMock()
    users_collection.stream.return_value = [user_doc]
    users_collection.document.return_value = user_doc_ref

    db = MagicMock()
    db.collection.return_value = users_collection
    db.collection.side_effect = lambda name: users_collection if name == "users" else MagicMock()

    service.db = db

    chapters = await service.get_project_chapters("p1")
    assert [int(c.get("chapter_number") or 0) for c in chapters] == [1, 2, 3]
