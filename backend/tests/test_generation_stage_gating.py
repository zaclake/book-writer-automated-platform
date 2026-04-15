import pytest


def test_normalize_stage_defaults_to_complete():
    from backend.utils.generation_stage import normalize_stage

    assert normalize_stage(None) == "complete"
    assert normalize_stage("") == "complete"
    assert normalize_stage("simple") == "complete"
    assert normalize_stage("  SIMPLE  ") == "complete"
    assert normalize_stage("complete") == "complete"
    assert normalize_stage("spike") == "spike"


def test_5_stage_is_gated_by_env(monkeypatch: pytest.MonkeyPatch):
    from backend.utils.generation_stage import resolve_generation_stage

    monkeypatch.setenv("ENABLE_5_STAGE_WRITING", "false")
    res = resolve_generation_stage("5-stage")
    assert res.requested == "5-stage"
    assert res.effective == "complete"
    assert res.allow_5_stage is False

    monkeypatch.setenv("ENABLE_5_STAGE_WRITING", "true")
    res2 = resolve_generation_stage("5-stage")
    assert res2.requested == "5-stage"
    assert res2.effective == "5-stage"
    assert res2.allow_5_stage is True


def test_unknown_stage_falls_back_to_complete(monkeypatch: pytest.MonkeyPatch):
    from backend.utils.generation_stage import resolve_generation_stage

    monkeypatch.setenv("ENABLE_5_STAGE_WRITING", "false")
    res = resolve_generation_stage("not-a-real-stage")
    assert res.requested == "complete"
    assert res.effective == "complete"

