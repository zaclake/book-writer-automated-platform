#!/usr/bin/env python3
"""
Story Intake Service
Handles clarifying questions and story refinement for paste-idea flow.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from backend.auto_complete.llm_orchestrator import LLMOrchestrator, RetryConfig, GenerationResult


class StoryClarifyResponse(BaseModel):
    questions: List[Dict[str, str]]
    mode: str
    round_index: int


class StoryRefineResponse(BaseModel):
    refined_content: str
    summary: str
    followup_questions: List[Dict[str, str]]


class StoryIntakeService:
    """Generate clarifying questions and refined story briefs."""

    def __init__(self, user_id: Optional[str] = None):
        self.orchestrator = LLMOrchestrator(
            retry_config=RetryConfig(max_retries=2),
            user_id=user_id
        )

    async def generate_questions(
        self,
        idea: str,
        mode: str = "brief",
        previous_answers: Optional[Dict[str, str]] = None,
        round_index: int = 1
    ) -> StoryClarifyResponse:
        if not idea or not idea.strip():
            raise ValueError("Idea text is required.")

        max_questions = 5 if mode == "brief" else 8
        prior_answer_block = ""
        if previous_answers:
            formatted = "\n".join([f"- {k}: {v}" for k, v in previous_answers.items() if v])
            if formatted:
                prior_answer_block = f"\n\nPRIOR ANSWERS:\n{formatted}"

        system_prompt = (
            "You are a story development editor. Ask clarifying questions that maximize story clarity.\n"
            "Keep the list short and high-impact. Avoid yes/no questions.\n"
            "Do not ask about information already provided.\n"
            "Return STRICT JSON only."
        )

        user_prompt = (
            f"STORY IDEA:\n{idea.strip()}\n"
            f"{prior_answer_block}\n\n"
            f"MODE: {mode}\n"
            f"ROUND: {round_index}\n\n"
            f"Return JSON with up to {max_questions} questions:\n"
            "{\n"
            '  "questions": [\n'
            '    {"id": "q1", "question": "...", "why": "..."}\n'
            "  ]\n"
            "}\n"
        )

        result = await self._generate_json(system_prompt, user_prompt)
        questions = result.get("questions", [])
        return StoryClarifyResponse(questions=questions, mode=mode, round_index=round_index)

    async def refine_story(
        self,
        idea: str,
        answers: Dict[str, str],
        mode: str = "brief"
    ) -> StoryRefineResponse:
        if not idea or not idea.strip():
            raise ValueError("Idea text is required.")

        answers_block = "\n".join([f"- {k}: {v}" for k, v in answers.items() if v])

        system_prompt = (
            "You are a story architect turning raw notes into a clean story brief.\n"
            "Use ONLY the provided information. Do not invent missing facts.\n"
            "Do not include placeholders or filler (no TBD, unknown, or bracketed guesses).\n"
            "Omit sections that cannot be supported by provided inputs.\n"
            "If the inputs include specific beats, outline, or script cues, preserve them as non-negotiables.\n"
            "Return STRICT JSON only."
        )

        user_prompt = (
            "STORY IDEA:\n"
            f"{idea.strip()}\n\n"
            "CLARIFICATIONS:\n"
            f"{answers_block if answers_block else 'None'}\n\n"
            f"MODE: {mode}\n\n"
            "Return JSON:\n"
            "{\n"
            '  "summary": "1-3 sentence crisp summary",\n'
            '  "refined_content": "Markdown story brief ready for book bible (include script/non-negotiables if provided)",\n'
            '  "followup_questions": [\n'
            '    {"id": "f1", "question": "...", "why": "..."}\n'
            "  ]\n"
            "}\n"
        )

        result = await self._generate_json(system_prompt, user_prompt)
        summary = result.get("summary", "").strip()
        refined_content = result.get("refined_content", "").strip()
        followup_questions = result.get("followup_questions", []) or []

        if not summary or not refined_content:
            raise ValueError("Refinement returned incomplete content.")

        return StoryRefineResponse(
            refined_content=refined_content,
            summary=summary,
            followup_questions=followup_questions
        )

    async def _generate_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        response = await self.orchestrator._make_api_call(
            messages=messages,
            temperature=0.3,
            max_tokens=1600,
            response_format={"type": "json_object"}
        )
        content = ""
        if hasattr(response, "output_text"):
            content = response.output_text
        elif hasattr(response, "choices"):
            content = response.choices[0].message.content
        try:
            import json
            return json.loads(content)
        except Exception as e:
            raise ValueError(f"Failed to parse JSON response: {e}")
