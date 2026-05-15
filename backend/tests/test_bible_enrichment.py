"""Tests for the Bible Enrichment service (Proposal 6)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock

import pytest

from backend.services.bible_enrichment import (
    EnrichmentAnswer,
    EnrichmentPromptRegistry,
    EnrichmentResult,
    EnrichmentRunner,
    QUESTION_IDS,
    enrichment_result_from_dict,
    merge_bible_with_enrichment,
)


@pytest.fixture
def registry() -> EnrichmentPromptRegistry:
    return EnrichmentPromptRegistry()


def test_registry_loads_all_questions(registry):
    qs = registry.questions
    assert set(qs.keys()) == set(QUESTION_IDS)
    for qid, q in qs.items():
        assert q.system_prompt
        assert q.user_prompt_template
        assert q.question_text
        assert q.short_label


def test_registry_resolves_known_genres(registry):
    assert registry.resolve_exemplar("Literary fiction").slug == "literary"
    assert registry.resolve_exemplar("THRILLER").slug == "thriller"
    assert registry.resolve_exemplar("sci-fi").slug == "scifi"
    assert registry.resolve_exemplar("rom-com").slug == "romance"
    assert registry.resolve_exemplar("epic fantasy").slug == "fantasy"
    assert registry.resolve_exemplar("WWII historical fiction").slug == "historical"


def test_registry_falls_back_to_default(registry):
    assert registry.resolve_exemplar("esoteric experimental nonfiction").slug == "default"
    assert registry.resolve_exemplar("").slug == "default"


def test_anti_cliche_prompt_loaded(registry):
    anti = registry.anti_cliche
    assert anti.system_prompt
    assert "STRICT JSON" in anti.system_prompt or "verdict" in anti.system_prompt.lower()
    assert anti.user_prompt_template


def _make_response(text: str):
    """Mimic the shape of an OpenAI Responses API result the runner expects."""

    class _Msg:
        def __init__(self, content: str):
            self.content = content

    class _Choice:
        def __init__(self, content: str):
            self.message = _Msg(content)

    class _Resp:
        def __init__(self, content: str):
            self.choices = [_Choice(content)]
            self.output_text = content

    return _Resp(text)


class _FakeOrchestrator:
    """Records calls to _make_api_call and returns scripted responses."""

    def __init__(self, responses: List[str]):
        self._responses = list(responses)
        self.calls: List[Dict[str, Any]] = []

    async def _make_api_call(self, **kwargs):  # noqa: D401, SLF001
        self.calls.append(kwargs)
        if not self._responses:
            return _make_response("")
        return _make_response(self._responses.pop(0))


@pytest.mark.asyncio
async def test_user_answers_are_preserved_without_llm_calls(registry):
    fake = _FakeOrchestrator(responses=[])
    runner = EnrichmentRunner(registry=registry, llm_orchestrator=fake)
    result = await runner.run(
        project_id="p1",
        bible="A 1200-word book bible.",
        genre="literary",
        user_answers={qid: f"user wrote {qid}" for qid in QUESTION_IDS},
    )
    assert len(fake.calls) == 0
    assert len(result.answers) == len(QUESTION_IDS)
    for qid in QUESTION_IDS:
        ans = result.answers[qid]
        assert ans.source == "user"
        assert ans.attempts == 0
        assert ans.answer == f"user wrote {qid}"


@pytest.mark.asyncio
async def test_skipped_questions_trigger_autofill(registry):
    # 5 questions × 2 calls per question (autofill + anti-cliché). All
    # anti-cliché responses are SPECIFIC so no regenerate happens.
    autofill_text = (
        "A specific, concrete, non-generic answer that references the bible "
        "and includes named characters."
    )
    specific_verdict = json.dumps(
        {"verdict": "SPECIFIC", "reason": "ok", "sharper_instruction": ""}
    )
    responses: List[str] = []
    for _ in QUESTION_IDS:
        responses.append(autofill_text)
        responses.append(specific_verdict)
    fake = _FakeOrchestrator(responses=responses)
    runner = EnrichmentRunner(registry=registry, llm_orchestrator=fake)
    result = await runner.run(
        project_id="p2",
        bible="A bible long enough to qualify, with content.",
        genre="literary",
        skipped=list(QUESTION_IDS),
    )
    assert len(fake.calls) == 2 * len(QUESTION_IDS)
    for qid in QUESTION_IDS:
        ans = result.answers[qid]
        assert ans.source == "auto"
        assert ans.attempts == 1  # no regenerate
        assert ans.anti_cliche_verdict == "SPECIFIC"
        assert "specific" in ans.answer.lower()


@pytest.mark.asyncio
async def test_generic_answer_triggers_one_regenerate(registry):
    """When the evaluator flags GENERIC, we regenerate exactly once."""
    qid = "reader_feeling"
    generic_first = "Hopeful and inspired."
    sharper_second = (
        "Specifically tied to the closing image of Ruth in the school parking "
        "lot at dusk; relief edged with grief."
    )
    generic_verdict = json.dumps(
        {
            "verdict": "GENERIC",
            "reason": "Could fit any book in this genre.",
            "sharper_instruction": "Reference the school closure and Ruth.",
        }
    )
    fake = _FakeOrchestrator(
        responses=[generic_first, generic_verdict, sharper_second]
    )
    runner = EnrichmentRunner(registry=registry, llm_orchestrator=fake)
    answer = await runner.autofill_question(
        question_id=qid,
        bible="Ruth, 31 years at the school, votes in three weeks.",
        genre="literary",
    )
    # Three calls total: first autofill, evaluator, regenerate. (No second
    # evaluator pass — we only regenerate once and accept the second answer.)
    assert len(fake.calls) == 3
    assert answer.attempts == 2
    assert answer.anti_cliche_verdict == "GENERIC"
    assert answer.answer == sharper_second
    # Confirm the third call carried the sharper instruction.
    third_call_messages = fake.calls[2]["messages"]
    assert any(
        "RETRY INSTRUCTION FROM EDITOR" in m.get("content", "")
        for m in third_call_messages
    )


@pytest.mark.asyncio
async def test_evaluator_failure_does_not_block(registry):
    """If the evaluator throws, the answer is treated as SPECIFIC."""

    class _RaisingOrchestrator:
        def __init__(self):
            self.calls = 0

        async def _make_api_call(self, **kwargs):  # noqa: SLF001
            self.calls += 1
            if self.calls == 1:
                return _make_response("Concrete answer with names.")
            raise RuntimeError("evaluator boom")

    raising = _RaisingOrchestrator()
    runner = EnrichmentRunner(registry=registry, llm_orchestrator=raising)
    answer = await runner.autofill_question(
        question_id="protagonist_lie",
        bible="A bible.",
        genre="thriller",
    )
    assert answer.source == "auto"
    assert answer.attempts == 1
    assert answer.anti_cliche_verdict == "SPECIFIC"
    assert "evaluator_unavailable" in (answer.anti_cliche_reason or "")


@pytest.mark.asyncio
async def test_autofill_failure_records_error(registry):
    class _FailingOrchestrator:
        async def _make_api_call(self, **kwargs):  # noqa: SLF001
            raise RuntimeError("openai outage")

    runner = EnrichmentRunner(registry=registry, llm_orchestrator=_FailingOrchestrator())
    result = await runner.run(
        project_id="p3",
        bible="A reasonably long bible body for testing.",
        genre="thriller",
        skipped=["reader_feeling"],
    )
    ans = result.answers["reader_feeling"]
    assert ans.source == "auto"
    assert ans.attempts == 0
    assert "autofill_failed" in (ans.anti_cliche_reason or "")
    assert ans.answer == ""


def test_compose_appendix_renders_in_question_order(registry):
    answers = {
        "clear_scenes": EnrichmentAnswer(
            question_id="clear_scenes",
            question_text="What three scenes do you already see clearly in your head?",
            short_label="Three vivid scenes",
            answer="1. Scene A. 2. Scene B. 3. Scene C.",
            source="user",
            attempts=0,
        ),
        "reader_feeling": EnrichmentAnswer(
            question_id="reader_feeling",
            question_text="What do you want the reader to feel at the end of this book?",
            short_label="Reader feeling at the end",
            answer="Held breath after a door closing.",
            source="auto",
            attempts=1,
            anti_cliche_verdict="SPECIFIC",
        ),
    }
    result = EnrichmentResult(project_id="p", genre="literary", answers=answers)
    appendix = EnrichmentRunner.compose_appendix(result)
    # reader_feeling must come before clear_scenes (canonical order).
    assert appendix.index("Reader feeling at the end") < appendix.index("Three vivid scenes")
    assert "Author Intent (Bible Enrichment)" in appendix
    # Provenance JSON included.
    assert '"source": "user"' in appendix
    assert '"source": "auto"' in appendix


def test_merge_is_idempotent(registry):
    bible = "# My Book\n\nSome content."
    answers = {
        "reader_feeling": EnrichmentAnswer(
            question_id="reader_feeling",
            question_text="What do you want the reader to feel at the end of this book?",
            short_label="Reader feeling at the end",
            answer="Specific feeling.",
            source="user",
            attempts=0,
        )
    }
    result = EnrichmentResult(project_id="p", genre="literary", answers=answers)
    merged_once = merge_bible_with_enrichment(bible, result)
    merged_twice = merge_bible_with_enrichment(merged_once, result)
    assert merged_once == merged_twice
    assert merged_once.count("# Author Intent (Bible Enrichment)") == 1


def test_merge_with_empty_enrichment_returns_bible():
    bible = "# Whatever"
    assert merge_bible_with_enrichment(bible, None) == bible
    empty = EnrichmentResult(project_id="p", genre="literary")
    assert merge_bible_with_enrichment(bible, empty) == bible


def test_round_trip_serialization():
    answer = EnrichmentAnswer(
        question_id="reader_feeling",
        question_text="What do you want the reader to feel at the end of this book?",
        short_label="Reader feeling at the end",
        answer="A specific delayed feeling.",
        source="auto",
        attempts=2,
        anti_cliche_verdict="GENERIC",
        anti_cliche_reason="Was hedged.",
        anti_cliche_sharper_instruction="Cite the named character.",
        model="gpt-5.5",
        elapsed_ms=2300,
        generated_at="2024-01-01T00:00:00+00:00",
    )
    result = EnrichmentResult(
        project_id="p1",
        genre="literary",
        answers={"reader_feeling": answer},
        completed_at="2024-01-01T00:00:01+00:00",
    )
    payload = result.to_dict()
    rehydrated = enrichment_result_from_dict(payload)
    assert rehydrated.project_id == "p1"
    assert rehydrated.answers["reader_feeling"].answer == answer.answer
    assert rehydrated.answers["reader_feeling"].anti_cliche_verdict == "GENERIC"
    assert rehydrated.answers["reader_feeling"].attempts == 2
