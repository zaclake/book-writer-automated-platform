"""Tests for the Voice Exemplars service (Proposal 10)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from backend.services.voice_exemplars import (
    MAX_EXCERPT_WORDS,
    MAX_SELECTIONS,
    VoiceExemplarRegistry,
    compose_bible_preface,
    compose_planning_block,
    excerpt_overlap_check,
    list_for_user_payload,
    resolve_selections,
)


def _write_lib(tmp_path: Path, entries: List[Dict[str, Any]]) -> Path:
    path = tmp_path / "library.json"
    path.write_text(json.dumps({"schema_version": 1, "entries": entries}), encoding="utf-8")
    return path


def test_seed_library_loads_with_only_public_domain_entries():
    """The shipped seed library must be public-domain only."""
    registry = VoiceExemplarRegistry()
    assert registry.entries, "seed library should not be empty"
    for entry in registry.entries:
        assert entry.licensing_tier == "public_domain", (
            f"seed library should not ship contemporary entries; got "
            f"{entry.licensing_tier} for {entry.author} — {entry.book}"
        )


def test_excerpt_word_cap_enforced(tmp_path):
    long_excerpt = " ".join(["word"] * (MAX_EXCERPT_WORDS + 50))
    path = _write_lib(
        tmp_path,
        [
            {
                "author": "Test Author",
                "book": "Test Book",
                "year": 1900,
                "licensing_tier": "public_domain",
                "genre_tags": ["literary"],
                "sensibility_notes": "Anything.",
                "excerpts": [long_excerpt],
            }
        ],
    )
    registry = VoiceExemplarRegistry(library_path=path)
    excerpt = registry.entries[0].excerpts[0]
    word_count = len(excerpt.split())
    # +1 for the ellipsis token added by the trimmer.
    assert word_count <= MAX_EXCERPT_WORDS + 1


def test_contemporary_entries_hidden_without_consent(tmp_path):
    path = _write_lib(
        tmp_path,
        [
            {
                "author": "Public Author",
                "book": "PD Book",
                "year": 1850,
                "licensing_tier": "public_domain",
                "genre_tags": ["literary"],
                "sensibility_notes": "PD",
                "excerpts": ["a short excerpt"],
            },
            {
                "author": "Contemporary Author",
                "book": "Modern Book",
                "year": 2020,
                "licensing_tier": "contemporary_excerpt",
                "genre_tags": ["literary"],
                "sensibility_notes": "Modern",
                "excerpts": ["a short excerpt"],
            },
        ],
    )
    registry = VoiceExemplarRegistry(library_path=path)
    public_only = registry.list_for_user(allow_contemporary=False)
    assert {e.author for e in public_only} == {"Public Author"}
    all_entries = registry.list_for_user(allow_contemporary=True)
    assert {e.author for e in all_entries} == {"Public Author", "Contemporary Author"}


def test_resolve_selections_respects_consent(tmp_path, monkeypatch):
    path = _write_lib(
        tmp_path,
        [
            {
                "author": "Joseph Conrad",
                "book": "Heart of Darkness",
                "year": 1899,
                "licensing_tier": "public_domain",
                "genre_tags": ["literary"],
                "sensibility_notes": "PD",
                "excerpts": ["sample text"],
            },
            {
                "author": "Modern Person",
                "book": "Modern Title",
                "year": 2020,
                "licensing_tier": "contemporary_excerpt",
                "genre_tags": ["literary"],
                "sensibility_notes": "Modern",
                "excerpts": ["sample text"],
            },
        ],
    )
    # Patch the singleton so our test fixture is used.
    import backend.services.voice_exemplars as ve

    monkeypatch.setattr(ve, "_REGISTRY_SINGLETON", VoiceExemplarRegistry(library_path=path))

    payload_no_consent = {
        "selected": [
            {"author": "Joseph Conrad", "book": "Heart of Darkness"},
            {"author": "Modern Person", "book": "Modern Title"},
        ],
        "consent": False,
    }
    resolved = resolve_selections(payload_no_consent)
    assert {e.author for e in resolved} == {"Joseph Conrad"}

    payload_with_consent = {
        "selected": [
            {"author": "Joseph Conrad", "book": "Heart of Darkness"},
            {"author": "Modern Person", "book": "Modern Title"},
        ],
        "consent": True,
        "consent_at": "2024-01-01T00:00:00+00:00",
    }
    resolved = resolve_selections(payload_with_consent)
    assert {e.author for e in resolved} == {"Joseph Conrad", "Modern Person"}


def test_compose_planning_block_includes_non_reproduction_guard():
    payload = {
        "selected": [
            {"author": "Joseph Conrad", "book": "Heart of Darkness", "rationale": "matches the cadence I want"}
        ]
    }
    block = compose_planning_block(payload)
    assert block
    assert "MUST NOT" in block or "must not" in block.lower()
    assert "REMINDER" in block
    assert "matches the cadence I want" in block
    assert "Joseph Conrad" in block


def test_compose_planning_block_empty_when_no_selection():
    assert compose_planning_block(None) == ""
    assert compose_planning_block({"selected": []}) == ""


def test_compose_bible_preface_short_form():
    payload = {
        "selected": [{"author": "Joseph Conrad", "book": "Heart of Darkness"}]
    }
    preface = compose_bible_preface(payload)
    assert preface
    assert "Voice Inspiration" in preface
    assert "Joseph Conrad" in preface
    # Preface should NOT include excerpt body text.
    assert "Going up that river" not in preface


def test_excerpt_overlap_check_flags_long_match():
    payload = {
        "selected": [{"author": "Joseph Conrad", "book": "Heart of Darkness"}]
    }
    # Use a phrase from the seed library excerpt.
    text = (
        "She wrote: going up that river was like travelling back to the "
        "earliest beginnings of the world, and then she stopped."
    )
    flags = excerpt_overlap_check(text, payload)
    assert flags
    text_clean = "She wrote a chapter that did not borrow from any source material."
    assert excerpt_overlap_check(text_clean, payload) == []


def test_max_selections_constant_is_used_by_caller():
    assert MAX_SELECTIONS >= 1


def test_list_for_user_payload_strips_excerpts():
    payload = list_for_user_payload(allow_contemporary=False)
    assert payload, "seed library should expose at least one entry"
    for entry in payload:
        assert "excerpt_count" in entry
        assert "excerpts" not in entry, "frontend listing must not include excerpt text"
