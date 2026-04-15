#!/usr/bin/env python3
"""
Title Recommendation Service
Generates recommended book titles using OpenAI based on project materials.
"""

import os
import json
import logging
import asyncio
from typing import Dict, Any, Optional, List

from openai import OpenAI

# Concurrency controls (robust import across environments)
try:
    from backend.system.concurrency import (
        get_llm_semaphore,
        get_llm_thread_semaphore,
        semaphore,
        thread_semaphore,
    )
except Exception:
    try:
        from ..system.concurrency import (
            get_llm_semaphore,
            get_llm_thread_semaphore,
            semaphore,
            thread_semaphore,
        )
    except Exception:
        from system.concurrency import (
            get_llm_semaphore,
            get_llm_thread_semaphore,
            semaphore,
            thread_semaphore,
        )

logger = logging.getLogger(__name__)


class TitleRecommendationService:
    """Service for generating title recommendations via OpenAI."""

    def __init__(self, user_id: Optional[str] = None):
        self.openai_client = None
        self.billable_client = False
        openai_api_key = os.getenv("OPENAI_API_KEY")
        enable_billing = os.getenv("ENABLE_CREDITS_BILLING", "false").lower() == "true"

        if openai_api_key:
            if user_id and enable_billing:
                try:
                    from backend.services.billable_client import BillableOpenAIClient
                    self.openai_client = BillableOpenAIClient(user_id)
                    self.billable_client = True
                except Exception:
                    self.openai_client = OpenAI(api_key=openai_api_key)
                    self.billable_client = False
            else:
                self.openai_client = OpenAI(api_key=openai_api_key)
                self.billable_client = False
        else:
            logger.warning("OPENAI_API_KEY not found. Title recommendations disabled.")

    def is_available(self) -> bool:
        return self.openai_client is not None

    def _build_reference_digest(self, reference_files: Dict[str, str]) -> str:
        if not reference_files:
            return ""
        preferred_tokens = [
            "characters",
            "world",
            "setting",
            "themes",
            "motifs",
            "outline",
            "plot",
            "style",
            "voice",
            "target-audience",
            "audience",
        ]
        selected: List[str] = []
        for name, content in reference_files.items():
            if not content:
                continue
            lowered = str(name).lower()
            if any(token in lowered for token in preferred_tokens):
                selected.append(f"{name}: {content[:500]}")
            if len(selected) >= 5:
                break
        if not selected:
            for name, content in reference_files.items():
                if content:
                    selected.append(f"{name}: {content[:350]}")
                if len(selected) >= 3:
                    break
        return "\n".join(selected)

    def _extract_json_payload(self, raw_text: str) -> Optional[Any]:
        try:
            return json.loads(raw_text)
        except Exception:
            pass
        trimmed = raw_text.strip()
        bracket_start = trimmed.find("[")
        bracket_end = trimmed.rfind("]")
        if bracket_start != -1 and bracket_end != -1 and bracket_end > bracket_start:
            try:
                return json.loads(trimmed[bracket_start: bracket_end + 1])
            except Exception:
                return None
        obj_start = trimmed.find("{")
        obj_end = trimmed.rfind("}")
        if obj_start != -1 and obj_end != -1 and obj_end > obj_start:
            try:
                return json.loads(trimmed[obj_start: obj_end + 1])
            except Exception:
                return None
        return None

    async def generate_recommendations(
        self,
        book_bible_content: str,
        reference_files: Dict[str, str],
        vector_context: Optional[str],
        current_title: Optional[str],
        max_results: int = 6
    ) -> List[Dict[str, str]]:
        if not self.openai_client:
            raise RuntimeError("OpenAI client not available")

        bible_excerpt = (book_bible_content or "")[:1600]
        references_digest = self._build_reference_digest(reference_files or {})
        vector_block = f"\nVECTOR MEMORY:\n{vector_context}" if vector_context else ""
        current_title = (current_title or "").strip()

        system_msg = (
            "You are a senior publishing editor and market strategist. "
            "Generate compelling, production-ready book title recommendations grounded strictly in the provided materials. "
            "Avoid placeholders, clichés, or titles that suggest details not present in the context. "
            "Return valid JSON only."
        )

        user_msg = (
            f"Current title (do not repeat unless instructed): {current_title or 'None'}\n\n"
            "BOOK BIBLE (excerpt):\n"
            f"{bible_excerpt}\n\n"
            "REFERENCE FILES (snippets):\n"
            f"{references_digest}\n\n"
            f"{vector_block}\n\n"
            "Task:\n"
            f"- Produce {max_results} distinct title recommendations.\n"
            "- Each title must be 2-8 words, avoid spoilers, and align with genre/tone.\n"
            "- Provide a 1-2 sentence rationale per title citing concrete story cues.\n"
            "- Output JSON only in this format:\n"
            "{\n"
            '  "recommendations": [\n'
            '    {"title": "Title Here", "rationale": "Reason grounded in the materials."}\n'
            "  ]\n"
            "}"
        )

        model_name = os.getenv("DEFAULT_AI_MODEL", "gpt-4o")
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg}
        ]

        if self.billable_client:
            async with semaphore(get_llm_semaphore()):
                billable_response = await self.openai_client.chat_completions_create(
                    model=model_name,
                    messages=messages,
                    temperature=0.6,
                    max_tokens=800
                )
                response = billable_response.response
        else:
            import functools
            with thread_semaphore(get_llm_thread_semaphore()):
                response = await asyncio.to_thread(
                    functools.partial(
                        self.openai_client.chat.completions.create,
                        model=model_name,
                        messages=messages,
                        temperature=0.6,
                        max_tokens=800,
                        timeout=120
                    )
                )

        content = response.choices[0].message.content or ""
        payload = self._extract_json_payload(content) or {}
        if isinstance(payload, list):
            recommendations = payload
        else:
            recommendations = payload.get("recommendations", [])

        cleaned: List[Dict[str, str]] = []
        seen = set()
        for item in recommendations:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            rationale = str(item.get("rationale", "")).strip()
            if not title or not rationale:
                continue
            if current_title and title.lower() == current_title.lower():
                continue
            key = title.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append({"title": title, "rationale": rationale})
            if len(cleaned) >= max_results:
                break

        if not cleaned:
            raise RuntimeError("No valid title recommendations returned from OpenAI.")

        return cleaned
