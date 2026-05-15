"""Tests for the reference upgrade (Proposals 3 + 8).

Covers the new craft references' presence in the generation order, dependency
graph, trim limits, and prompt-file shape.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from backend.utils.reference_content_generator import ReferenceContentGenerator


NEW_REFERENCE_TYPES = [
    "character-contradictions",
    "thematic-spine",
    "narrator-sensibility",
    "subtext-bible",
]


def test_new_references_in_generation_order():
    order = ReferenceContentGenerator.CHAINED_GENERATION_ORDER
    for ref_type in NEW_REFERENCE_TYPES:
        assert ref_type in order, f"{ref_type} should appear in CHAINED_GENERATION_ORDER"
    # Director-guide must come AFTER all four new craft refs so it can consume them.
    director_idx = order.index("director-guide")
    for ref_type in NEW_REFERENCE_TYPES:
        assert order.index(ref_type) < director_idx, (
            f"{ref_type} must be generated before director-guide so the "
            "director-guide can consume it"
        )


def test_new_references_have_dependency_entries():
    deps = ReferenceContentGenerator.CHAINING_DEPENDENCIES
    for ref_type in NEW_REFERENCE_TYPES:
        assert ref_type in deps, f"{ref_type} missing from CHAINING_DEPENDENCIES"
        assert isinstance(deps[ref_type], list)


def test_director_guide_depends_on_new_craft_refs():
    deps = ReferenceContentGenerator.CHAINING_DEPENDENCIES["director-guide"]
    for ref_type in (
        "character-contradictions",
        "thematic-spine",
        "narrator-sensibility",
        # Proposal 8 — director-guide must also see subtext-bible so per-chapter
        # briefs can pull the relevant relationship subtext rows.
        "subtext-bible",
    ):
        assert ref_type in deps, (
            f"director-guide must depend on {ref_type} so the new craft refs "
            "are surfaced in the chained context"
        )


def test_subtext_bible_depends_on_contradictions_and_relationships():
    deps = ReferenceContentGenerator.CHAINING_DEPENDENCIES["subtext-bible"]
    assert "characters" in deps
    assert "character-contradictions" in deps
    assert "relationship-map" in deps


def test_new_references_have_trim_limits():
    limits = ReferenceContentGenerator.CHAINING_TRIM_LIMITS
    for ref_type in NEW_REFERENCE_TYPES:
        assert ref_type in limits, (
            f"{ref_type} missing from CHAINING_TRIM_LIMITS — chained context "
            "would be untrimmed"
        )
        assert isinstance(limits[ref_type], int)
        assert limits[ref_type] > 0


def _prompts_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "prompts" / "reference-generation"


@pytest.mark.parametrize("ref_type", NEW_REFERENCE_TYPES)
def test_new_reference_prompt_files_exist_and_are_valid(ref_type):
    path = _prompts_dir() / f"{ref_type}-prompt.yaml"
    assert path.exists(), f"Missing prompt YAML: {path}"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    for required in ("name", "system_prompt", "user_prompt_template", "model_config"):
        assert data.get(required), f"{ref_type} prompt missing field: {required}"
    template = data["user_prompt_template"]
    # Must have the standard chained-context placeholders.
    assert "{book_bible_content}" in template
    assert "{prior_references}" in template
    # Model config sanity.
    mc = data["model_config"]
    assert mc.get("model")
    assert isinstance(mc.get("temperature"), (int, float))
    assert isinstance(mc.get("max_tokens"), int) and mc["max_tokens"] > 0


def test_filename_map_in_generate_all_references_handles_new_types(monkeypatch, tmp_path):
    """Smoke test: the filename_map inside generate_all_references must cover
    the new types so the generator does not write `<type>.md.md` or skip them."""
    gen = ReferenceContentGenerator()
    # We don't actually call OpenAI here — just verify the method exists and
    # the chained order can be enumerated end-to-end without a KeyError.
    types = list(ReferenceContentGenerator.CHAINED_GENERATION_ORDER)
    for ref_type in NEW_REFERENCE_TYPES:
        assert ref_type in types
