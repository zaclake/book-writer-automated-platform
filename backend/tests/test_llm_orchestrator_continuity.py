#!/usr/bin/env python3
"""
Regression tests for continuity prompt wiring.
"""

from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig


def test_build_comprehensive_prompts_consumes_nested_continuity():
    orchestrator = LLMOrchestrator(retry_config=RetryConfig(max_retries=1), user_id="test-user", enable_billing=False)

    context = {
        "book_bible": "Book bible here.",
        "references": {},
        "continuity": {
            "story_so_far": "Chapter 1 ended with Nero discovering a body under Clarifier 1.",
            "continuity_requirements": ["Continue from the discovery. No recap paragraph."],
            "unresolved_questions": ["Who put him there?"],
            "timeline_state": {"day": "Monday", "time": "late morning"},
            "plot_threads": {"sabotage": "suspected"},
            "world_state": {"location": "Hickory Creek plant"},
        },
        "last_chapter_ending": "Nero called code blue and stared at the body.",
    }

    system_prompt, user_prompt = orchestrator._build_comprehensive_prompts(2, 2000, context)

    assert "CONTINUITY STORY SO FAR" in user_prompt
    assert "Nero discovering a body" in user_prompt
    assert "BEGIN IN-SCENE FROM THIS PRIOR ENDING" in user_prompt
    assert "Nero called code blue" in user_prompt
