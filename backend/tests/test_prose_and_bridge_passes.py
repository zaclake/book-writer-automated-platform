import os

import pytest


def _mk_orchestrator():
    # Ensure init doesn't fail due to missing API key in tests.
    os.environ.setdefault("OPENAI_API_KEY", "test-key")
    from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig

    return LLMOrchestrator(retry_config=RetryConfig(max_retries=0), prompts_dir="prompts")


def test_tight_prose_pass_force_env(monkeypatch: pytest.MonkeyPatch):
    orch = _mk_orchestrator()
    monkeypatch.setenv("CHAPTER_FORCE_TIGHT_PROSE_PASS", "true")
    assert orch._needs_tight_prose_pass("Some text.") is True


def test_tight_prose_pass_triggers_on_overwriting_signals(monkeypatch: pytest.MonkeyPatch):
    orch = _mk_orchestrator()
    monkeypatch.setenv("CHAPTER_FORCE_TIGHT_PROSE_PASS", "false")

    # Long, comma-stacked sentences + adverbs should trip >=2 signals.
    text = (
        "He carefully, quietly, deliberately moved through the corridor, steadily listening, "
        "watching, considering every possible outcome, and thinking about the implications, "
        "because the night, inevitably, felt different.\n\n"
        "She slowly, carefully, methodically turned the handle, silently counting, "
        "and then, naturally, paused, because everything, strangely, seemed wrong."
    )
    assert orch._needs_tight_prose_pass(text) is True


def test_tight_prose_pass_triggers_on_length_overshoot(monkeypatch: pytest.MonkeyPatch):
    orch = _mk_orchestrator()
    monkeypatch.setenv("CHAPTER_FORCE_TIGHT_PROSE_PASS", "false")
    monkeypatch.setenv("CHAPTER_TIGHT_PROSE_ON_OVERSHOOT", "true")
    monkeypatch.setenv("CHAPTER_TIGHT_PROSE_OVERSHOOT_RATIO", "1.15")
    monkeypatch.setenv("CHAPTER_TIGHT_PROSE_OVERSHOOT_MIN_WORDS", "20")

    # Intentionally bland text (should not trip prose heuristics),
    # but is far above target words so overshoot logic should trigger.
    text = ("word " * 220).strip()
    assert orch._needs_tight_prose_pass(text) is False
    assert orch._needs_tight_prose_pass_for_target(text, 120) is True


def test_opening_bridge_pass_tokenization_handles_hyphens_and_caps(monkeypatch: pytest.MonkeyPatch):
    orch = _mk_orchestrator()
    monkeypatch.setenv("CHAPTER_FORCE_TIGHT_PROSE_PASS", "false")

    # Bridge requirements include hyphenated/proper noun tokens that must be detectable.
    ctx = {
        "previous_texts_for_audit": ["prior chapter text about Headworks and Clarifier-1"],
        "bridge_requirements": [
            "Carry forward the clue from Clarifier-1 and Headworks.",
            "Begin from the immediate consequence of the prior ending: Access denied on PlantTrack."
        ],
    }

    # Opening doesn't mention those tokens; should trigger via bridge_score < 0.6.
    opening = "Nero woke late and stared at the ceiling. The day was grey. He drank coffee."
    assert orch._needs_opening_bridge_pass(opening, 2, ctx) is True

    # Opening DOES mention bridge tokens; should not trigger on bridge_score (overlap ratio is low here).
    opening2 = "At Clarifier-1, Nero watched the rail and checked PlantTrack, still locked out."
    assert orch._needs_opening_bridge_pass(opening2, 2, ctx) is False


def test_specificity_gate_allows_common_acronyms():
    orch = _mk_orchestrator()
    # Provide approved terms so the gate doesn't fall into "no approved terms" branch.
    approved = ["Nero", "Headworks", "Clarifier"]
    text = (
        "Nero checked the SCADA panel in the Headworks office and wrote down the reading.\n\n"
        "At Clarifier 1, he pocketed the tag and walked back to the rail."
    )
    failures = orch._specificity_gate_failures(text, approved, chapter_number=2)
    assert not any(f.startswith("unexpected_all_caps=") for f in failures)

