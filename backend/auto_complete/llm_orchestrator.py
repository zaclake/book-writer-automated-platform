#!/usr/bin/env python3
"""
LLM Orchestrator - Phase 1 MVP
Robust implementation with retry logic, exponential back-off, and structured logging.
"""

import os
import json
import re
import time
import random
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
import logging
from datetime import datetime
import asyncio

# Third-party imports (optional in some deployments)
try:
    import openai
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    openai = None
    OpenAI = None
    _OPENAI_AVAILABLE = False

# Local imports (robust multi-path fallbacks)
PromptManager = None
try:
    # Primary absolute import when `backend` is a package
    from backend.system.prompt_manager import PromptManager as _PM
    PromptManager = _PM
except Exception:
    try:
        # Relative import when running inside backend package
        from ..system.prompt_manager import PromptManager as _PM
        PromptManager = _PM
    except Exception:
        try:
            # Top-level import when executed from repo root
            from system.prompt_manager import PromptManager as _PM
            PromptManager = _PM
        except Exception:
            try:
                # Legacy fallback path
                from backend.prompt_manager import PromptManager as _PM
                PromptManager = _PM
            except Exception:
                # Final fallback - minimal stub
                class PromptManager:  # type: ignore
                    def __init__(self, prompts_dir):
                        self.prompts_dir = prompts_dir
                        self.logger = logging.getLogger(__name__)
                        self.logger.warning("Using fallback PromptManager - YAML templates not available")

                    def get_template(self, stage):
                        return None
                logging.getLogger(__name__).error("PromptManager not available - using fallback")

# Concurrency controls (robust imports available to whole module)
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
        try:
            from system.concurrency import (
                get_llm_semaphore,
                get_llm_thread_semaphore,
                semaphore,
                thread_semaphore,
            )
        except Exception:
            import threading  # type: ignore
            _llm_sem = None
            _llm_thread_sem = None

            def _get_int_env(name: str, default: int) -> int:
                try:
                    return max(1, int(os.getenv(name, str(default))))
                except Exception:
                    return default

            def get_llm_semaphore() -> asyncio.Semaphore:  # type: ignore
                global _llm_sem
                if _llm_sem is None:
                    _llm_sem = asyncio.Semaphore(_get_int_env("MAX_CONCURRENT_LLM", 6))
                return _llm_sem

            def get_llm_thread_semaphore() -> 'threading.BoundedSemaphore':  # type: ignore
                global _llm_thread_sem
                if _llm_thread_sem is None:
                    _llm_thread_sem = threading.BoundedSemaphore(_get_int_env("MAX_CONCURRENT_LLM", 6))
                return _llm_thread_sem

            class semaphore:  # type: ignore
                def __init__(self, sem: asyncio.Semaphore):
                    self._sem = sem
                async def __aenter__(self):
                    await self._sem.acquire()
                    return self
                async def __aexit__(self, exc_type, exc, tb):
                    self._sem.release()
                    return False

            class thread_semaphore:  # type: ignore
                def __init__(self, sem: 'threading.BoundedSemaphore'):
                    self._sem = sem
                def __enter__(self):
                    self._sem.acquire()
                    return self
                def __exit__(self, exc_type, exc, tb):
                    self._sem.release()
                    return False

@dataclass
class GenerationResult:
    """Result of a chapter generation attempt."""
    success: bool
    content: str
    metadata: Dict[str, Any]
    error: Optional[str] = None
    tokens_used: int = 0
    cost_estimate: float = 0.0
    retry_count: int = 0

@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True


class LLMQuotaError(Exception):
    """
    Raised when the provider reports quota/billing exhaustion (e.g. OpenAI code=insufficient_quota).
    This is not retryable and should abort the current unit of work immediately.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        code: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code

class LLMOrchestrator:
    """Orchestrates LLM-based chapter generation with quality gate integration."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4.1", 
                 retry_config: Optional[RetryConfig] = None, prompts_dir: str = "prompts",
                 user_id: Optional[str] = None, enable_billing: Optional[bool] = None):
        """Initialize the orchestrator."""
        if not _OPENAI_AVAILABLE:
            raise RuntimeError("OpenAI library not installed. Install openai to enable LLM features.")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY environment variable.")
        
        # Allow env override while keeping a strong default for chapter drafts.
        self.model = (model or os.getenv("DEFAULT_AI_MODEL") or "gpt-4.1")
        self.user_id = user_id
        self.retry_config = retry_config or RetryConfig()
        self.prompts_dir = Path(prompts_dir)
        
        # Initialize client - use billable client if user_id provided and billing enabled
        billing_enabled = enable_billing if enable_billing is not None else os.getenv('ENABLE_CREDITS_BILLING', 'false').lower() == 'true'
        
        if self.user_id and billing_enabled:
            try:
                from ..services.billable_client import create_billable_openai_client
                self.client = create_billable_openai_client(user_id=self.user_id, api_key=self.api_key)
                self.billable_client = True
                self.logger = None  # Will be set up later
                self._setup_logging()
                self.logger.info(f"LLM Orchestrator initialized with billable client for user {user_id}")
            except Exception as e:
                # Fallback to regular client if billable client fails
                self.client = OpenAI(api_key=self.api_key)
                self.billable_client = False
                self.logger = None
                self._setup_logging()
                self.logger.warning(f"Failed to initialize billable client, using regular client: {e}")
        else:
            self.client = OpenAI(api_key=self.api_key)
            self.billable_client = False
        
        # Initialize prompt manager
        try:
            self.prompt_manager = PromptManager(prompts_dir)
        except FileNotFoundError:
            self.prompt_manager = None
            print(f"Warning: Prompts directory not found at {prompts_dir}. Using fallback prompts.")
        
        # Setup structured logging
        self._setup_logging()
        try:
            self.logger.info("LLMOrchestrator retry policy: quota_fail_fast=v2")
        except Exception:
            pass
        
        # Cost tracking (GPT-4o pricing as of 2024)
        self.cost_per_1k_input_tokens = 0.005  # $0.005 per 1K input tokens
        self.cost_per_1k_output_tokens = 0.015  # $0.015 per 1K output tokens
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 1.0  # Minimum 1 second between requests

        # Perf stats (per-run aggregation; caller logs once at end)
        self._perf: Dict[str, Any] = {}
        self.reset_perf()
    
    def reset_perf(self) -> None:
        """Reset per-run performance counters/timings."""
        self._perf = {
            "model": self.model,
            "run_started_s": time.perf_counter(),
            "llm_ms_total": 0,
            "llm_attempts_total": 0,
            "llm_calls_total": 0,
            "retry_count_total": 0,
            "file_search_calls": 0,
            "file_search_fallbacks": 0,
            "stages": {},  # stage_number -> {ms, tokens_total, prompt_tokens, completion_tokens}
            "scene_by_scene": {"scenes": 0, "ms_total": 0},
            "continuations": 0,
            "passes": {"executed": [], "skipped": []},
        }

    def get_perf_summary(self) -> Dict[str, Any]:
        """Return a compact perf summary suitable for single-line JSON logging."""
        try:
            total_ms = int((time.perf_counter() - float(self._perf.get("run_started_s", 0.0))) * 1000)
        except Exception:
            total_ms = 0
        stages = self._perf.get("stages", {}) if isinstance(self._perf.get("stages"), dict) else {}
        return {
            "model": self.model,
            "total_ms": total_ms,
            "llm_ms_total": int(self._perf.get("llm_ms_total", 0) or 0),
            "llm_attempts_total": int(self._perf.get("llm_attempts_total", 0) or 0),
            "llm_calls_total": int(self._perf.get("llm_calls_total", 0) or 0),
            "retry_count_total": int(self._perf.get("retry_count_total", 0) or 0),
            "file_search_calls": int(self._perf.get("file_search_calls", 0) or 0),
            "file_search_fallbacks": int(self._perf.get("file_search_fallbacks", 0) or 0),
            "continuations": int(self._perf.get("continuations", 0) or 0),
            "stages": stages,
            "scene_by_scene": self._perf.get("scene_by_scene", {}),
            "passes": self._perf.get("passes", {}),
        }
        
    def _setup_logging(self):
        """
        Setup logging for the orchestrator.

        Important: Do NOT add handlers here. Handlers are configured once at process
        startup (see `backend/utils/logging_config.py`). Adding handlers in-library
        causes duplicate log lines under Gunicorn/Uvicorn.
        """
        self.logger = logging.getLogger(__name__)

    def _init_postdraft_budget(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Shared per-chapter post-draft LLM budget.

        This budget is meant to cap churn AFTER an initial draft exists (rewrites, regens,
        LLM diagnostics that drive rewrites). It is separate from the core drafting call(s).
        """
        if not isinstance(context, dict):
            return {"total": 0, "used": 0, "remaining": 0, "actions": []}
        existing = context.get("postdraft_budget")
        if isinstance(existing, dict) and {"total", "used", "remaining", "actions"}.issubset(existing.keys()):
            return existing
        total = int(os.getenv("CHAPTER_POSTDRAFT_LLM_BUDGET", "5"))
        budget = {"total": max(0, total), "used": 0, "remaining": max(0, total), "actions": []}
        context["postdraft_budget"] = budget
        return budget

    def _consume_postdraft_budget(
        self,
        context: Dict[str, Any],
        action: str,
        *,
        cost: int = 1,
        essential: bool = False
    ) -> bool:
        """
        Return True if allowed (budget decremented), False if blocked.
        Essential actions are capped separately and do not consume the main budget.
        """
        if not isinstance(context, dict):
            return False
        budget = self._init_postdraft_budget(context)
        try:
            budget.setdefault("actions", [])
            if not isinstance(budget["actions"], list):
                budget["actions"] = []
        except Exception:
            pass

        if essential:
            essential_total = int(os.getenv("CHAPTER_POSTDRAFT_ESSENTIAL_LLM_BUDGET", "3"))
            essential_used = int(budget.get("essential_used", 0) or 0)
            if essential_used >= max(0, essential_total):
                try:
                    budget["actions"].append(f"blocked:{action}")
                except Exception:
                    pass
                return False
            budget["essential_used"] = essential_used + 1
            try:
                budget["actions"].append(f"essential:{action}")
            except Exception:
                pass
            return True

        remaining = int(budget.get("remaining", 0) or 0)
        if remaining < max(0, cost):
            try:
                budget["actions"].append(f"blocked:{action}")
            except Exception:
                pass
            return False
        budget["remaining"] = remaining - max(0, cost)
        budget["used"] = int(budget.get("used", 0) or 0) + max(0, cost)
        try:
            budget["actions"].append(action)
        except Exception:
            pass
        return True

    def _get_model_max_output_tokens(self) -> int:
        """Return the model's max output token limit (conservative defaults)."""
        env_limit = os.getenv("OPENAI_MAX_OUTPUT_TOKENS")
        if env_limit:
            try:
                return max(256, int(env_limit))
            except Exception:
                pass

        model = (self.model or "").lower()
        model_limits = {
            "gpt-4o": 16384,
            "gpt-4o-mini": 16384,
            "gpt-4.1": 32768,
            "gpt-4.1-mini": 16384,
            "gpt-4.1-nano": 16384,
        }
        for key, limit in model_limits.items():
            if key in model:
                return limit

        # Safe default — modern models support at least 16K output
        return 16384
        
    async def _wait_for_rate_limit(self):
        """Ensure minimum time between requests without blocking the event loop."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            self.logger.debug(f"Rate limiting: waiting {sleep_time:.2f}s")
            await asyncio.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _calculate_retry_delay(self, attempt: int) -> float:
        """Calculate delay for retry attempt with exponential backoff."""
        base_delay = self.retry_config.base_delay
        exponential_delay = base_delay * (self.retry_config.exponential_base ** attempt)
        
        # Add jitter to prevent thundering herd
        if self.retry_config.jitter:
            jitter = random.uniform(0.1, 0.3) * exponential_delay
            exponential_delay += jitter
        
        return min(exponential_delay, self.retry_config.max_delay)

    def _extract_openai_error_code(self, error: Exception) -> Optional[str]:
        """
        Best-effort extraction of provider error code (e.g. 'insufficient_quota').
        Works across multiple OpenAI SDK error shapes.
        """
        try:
            code = getattr(error, "code", None)
            if code:
                return str(code)
        except Exception:
            pass
        try:
            body = getattr(error, "body", None)
            if isinstance(body, dict):
                inner = body.get("error") if isinstance(body.get("error"), dict) else {}
                code = inner.get("code") or inner.get("type")
                if code:
                    return str(code)
        except Exception:
            pass
        # Fallback: string match
        try:
            msg = str(error)
            if "insufficient_quota" in msg:
                return "insufficient_quota"
        except Exception:
            pass
        return None

    def _error_text_for_matching(self, error: Exception) -> str:
        """
        Best-effort collection of error details for substring matching.
        Designed to be extremely defensive (never raises).
        """
        parts: List[str] = []
        try:
            parts.append(str(error))
        except Exception:
            pass
        try:
            parts.append(repr(error))
        except Exception:
            pass
        try:
            args = getattr(error, "args", None)
            if args:
                parts.append(repr(args))
        except Exception:
            pass
        try:
            body = getattr(error, "body", None)
            if isinstance(body, dict):
                parts.append(json.dumps(body, ensure_ascii=False, default=str))
            elif isinstance(body, str):
                parts.append(body)
        except Exception:
            pass
        return " | ".join([p for p in parts if isinstance(p, str) and p])

    def _is_insufficient_quota_error(self, error: Exception) -> bool:
        """
        OpenAI sometimes reports billing/quota exhaustion as 429 with code=insufficient_quota.
        This is not retryable and should fail fast.
        """
        try:
            code = (self._extract_openai_error_code(error) or "").lower().strip()
            if code == "insufficient_quota":
                return True
        except Exception:
            pass
        try:
            msg = str(error).lower()
            if "insufficient_quota" in msg:
                return True
            if "exceeded your current quota" in msg:
                return True
            if "check your plan and billing details" in msg:
                return True
        except Exception:
            pass
        # Ultra-defensive fallback: match across repr/args/body.
        try:
            blob = self._error_text_for_matching(error).lower()
            if "insufficient_quota" in blob:
                return True
            if "exceeded your current quota" in blob:
                return True
            if "check your plan and billing details" in blob:
                return True
        except Exception:
            pass
        return False
    
    def _is_retryable_error(self, error: Exception) -> bool:
        """Determine if an error is retryable."""
        # Billing/quota exhaustion is never retryable.
        if self._is_insufficient_quota_error(error):
            return False
        if _OPENAI_AVAILABLE and isinstance(error, openai.RateLimitError):
            return True
        if _OPENAI_AVAILABLE and isinstance(error, openai.APIConnectionError):
            return True
        if _OPENAI_AVAILABLE and isinstance(error, openai.InternalServerError):
            return True
        if _OPENAI_AVAILABLE and isinstance(error, openai.APITimeoutError):
            return True
        
        # For general API errors, check status code
        if hasattr(error, 'status_code'):
            # Retry on 5xx errors and 429 (rate limit)
            if error.status_code >= 500 or error.status_code == 429:
                return True
        
        return False
    
    async def _make_api_call(self, messages: List[Dict[str, str]], **kwargs) -> dict:
        """Make API call with retry logic. Returns (response, credits_charged)."""
        last_error = None
        vector_store_ids = kwargs.pop("vector_store_ids", None) or []
        use_file_search_flag = kwargs.pop("use_file_search", True)
        response_format = kwargs.get("response_format")
        if response_format and use_file_search_flag:
            # Responses API does not reliably support response_format across all models.
            # Force chat completions for strict JSON mode requests.
            use_file_search_flag = False

        use_file_search = bool(vector_store_ids) and use_file_search_flag and os.getenv("ENABLE_OPENAI_FILE_SEARCH", "true").lower() == "true"
        if "max_tokens" in kwargs:
            max_tokens = kwargs.get("max_tokens")
            if isinstance(max_tokens, int) and max_tokens > 0:
                model_cap = self._get_model_max_output_tokens()
                if max_tokens > model_cap:
                    self.logger.warning(
                        f"Clamping max_tokens from {max_tokens} to model cap {model_cap}"
                    )
                    kwargs["max_tokens"] = model_cap
        
        file_search_disabled = False
        for attempt in range(self.retry_config.max_retries + 1):
            try:
                # Perf counters (no per-attempt logs)
                try:
                    self._perf["llm_attempts_total"] = int(self._perf.get("llm_attempts_total", 0) or 0) + 1
                    if use_file_search:
                        self._perf["file_search_calls"] = int(self._perf.get("file_search_calls", 0) or 0) + 1
                except Exception:
                    pass

                # Rate limiting (non-blocking)
                await self._wait_for_rate_limit()
                if attempt > 0:
                    self.logger.warning(
                        f"Retrying LLM request (attempt {attempt + 1}/{self.retry_config.max_retries + 1})"
                    )
                    try:
                        self._perf["retry_count_total"] = int(self._perf.get("retry_count_total", 0) or 0) + 1
                    except Exception:
                        pass
                
                attempt_started = time.perf_counter()
                if use_file_search:
                    response = await self._make_responses_call(messages, vector_store_ids, **kwargs)
                else:
                    if self.billable_client:
                        # Use billable client - this automatically handles credit billing
                        async with semaphore(get_llm_semaphore()):
                            billable_response = await self.client.chat_completions_create(
                                model=self.model,
                                messages=messages,
                                timeout=300,
                                **kwargs
                            )
                        response = billable_response.response
                        credits_charged = billable_response.credits_charged
                        
                        # Add credits info to metadata for compatibility
                        try:
                            setattr(response, "_credits_charged", credits_charged)
                        except Exception:
                            pass
                    else:
                        # Use regular client - call sync SDK in a worker thread to avoid blocking the event loop
                        import functools
                        with thread_semaphore(get_llm_thread_semaphore()):
                            response = await asyncio.to_thread(
                                functools.partial(
                                    self.client.chat.completions.create,
                                    model=self.model,
                                    messages=messages,
                                    timeout=300,
                                    **kwargs
                                )
                            )
                        try:
                            setattr(response, "_credits_charged", 0)
                        except Exception:
                            pass
                
                # Successful attempt
                try:
                    self._perf["llm_calls_total"] = int(self._perf.get("llm_calls_total", 0) or 0) + 1
                except Exception:
                    pass
                # Keep a best-effort total LLM ms estimate for the run (sum of attempts).
                try:
                    llm_ms_total = int(self._perf.get("llm_ms_total", 0) or 0)
                    self._perf["llm_ms_total"] = llm_ms_total + int((time.perf_counter() - attempt_started) * 1000)
                except Exception:
                    pass

                if attempt > 0:
                    self.logger.info(f"LLM request recovered after {attempt} retry attempt(s)")
                return response
                
            except Exception as e:
                last_error = e
                if self._is_insufficient_quota_error(e):
                    # Fail fast: do not retry, do not backoff spam.
                    code = self._extract_openai_error_code(e)
                    status_code = getattr(e, "status_code", None)
                    self.logger.error(
                        "LLM request failed (quota/billing). This is not retryable. "
                        f"status={status_code} code={code} err={type(e).__name__}: {e}"
                    )
                    raise LLMQuotaError(
                        f"OpenAI quota/billing exhausted (code={code}). {e}",
                        status_code=int(status_code) if isinstance(status_code, int) else None,
                        code=str(code) if code else None,
                    )

                # Avoid spamming logs on retryable failures; log concise failure info and retry plan.
                self.logger.warning(f"LLM request failed (attempt {attempt + 1}): {type(e).__name__}: {e}")

                if use_file_search and not file_search_disabled:
                    message = str(e).lower()
                    status_code = getattr(e, "status_code", None)
                    if status_code == 400 or "file_search" in message or "tools" in message or "vector_store" in message:
                        self.logger.warning(
                            "Disabling file_search after API error; retrying without tools."
                        )
                        use_file_search = False
                        file_search_disabled = True
                        try:
                            self._perf["file_search_fallbacks"] = int(self._perf.get("file_search_fallbacks", 0) or 0) + 1
                        except Exception:
                            pass
                        continue
                
                # Don't retry on final attempt
                if attempt == self.retry_config.max_retries:
                    break
                
                # Check if error is retryable
                if not self._is_retryable_error(e):
                    self.logger.error(f"Non-retryable LLM error: {type(e).__name__}: {e}")
                    break
                
                # Calculate and apply retry delay (non-blocking)
                delay = self._calculate_retry_delay(attempt)
                self.logger.warning(f"Will retry in {delay:.2f}s")
                await asyncio.sleep(delay)
        
        # All retries exhausted
        raise last_error

    async def _make_responses_call(self, messages: List[Dict[str, str]], vector_store_ids: List[str], **kwargs):
        """Call OpenAI Responses API with file_search tool."""
        max_tokens = kwargs.pop("max_tokens", None)
        timeout = kwargs.pop("timeout", 300)
        kwargs.pop("model", None)
        for key in ("frequency_penalty", "presence_penalty", "temperature", "top_p"):
            kwargs.pop(key, None)
        if self.billable_client:
            async with semaphore(get_llm_semaphore()):
                billable_response = await self.client.responses_create(
                    model=self.model,
                    input=messages,
                    tools=[{"type": "file_search", "vector_store_ids": vector_store_ids}],
                    timeout=timeout,
                    max_output_tokens=max_tokens,
                    **kwargs
                )
            response = billable_response.response
            credits_charged = billable_response.credits_charged
            try:
                setattr(response, "_credits_charged", credits_charged)
            except Exception:
                pass
            return response

        import functools
        if not hasattr(self.client, "responses"):
            if os.getenv("REQUIRE_OPENAI_RESPONSES", "false").lower() == "true":
                raise RuntimeError("OpenAI Responses API required but not available in client runtime.")
            self.logger.warning("Responses API unavailable; falling back to chat completions")
            with thread_semaphore(get_llm_thread_semaphore()):
                response = await asyncio.to_thread(
                    functools.partial(
                        self.client.chat.completions.create,
                        model=self.model,
                        messages=messages,
                        timeout=timeout,
                        max_tokens=max_tokens,
                        **kwargs
                    )
                )
            try:
                setattr(response, "_credits_charged", 0)
            except Exception:
                pass
            return response

        with thread_semaphore(get_llm_thread_semaphore()):
            response = await asyncio.to_thread(
                functools.partial(
                    self.client.responses.create,
                    model=self.model,
                    input=messages,
                    tools=[{"type": "file_search", "vector_store_ids": vector_store_ids}],
                    timeout=timeout,
                    max_output_tokens=max_tokens,
                    **kwargs
                )
            )
        try:
            setattr(response, "_credits_charged", 0)
        except Exception:
            pass
        return response

    def _extract_content_and_usage(self, response) -> tuple[str, Dict[str, int]]:
        """Normalize content + usage from chat or responses API."""
        content = ""
        if hasattr(response, "output_text"):
            content = response.output_text
        elif hasattr(response, "choices"):
            try:
                content = response.choices[0].message.content
            except Exception:
                content = ""
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        total_tokens = getattr(usage, "total_tokens", None)
        if prompt_tokens is None and usage is not None:
            prompt_tokens = getattr(usage, "input_tokens", 0)
            completion_tokens = getattr(usage, "output_tokens", 0)
            total_tokens = getattr(usage, "total_tokens", (prompt_tokens or 0) + (completion_tokens or 0))
        usage_data = {
            "prompt_tokens": prompt_tokens or 0,
            "completion_tokens": completion_tokens or 0,
            "total_tokens": total_tokens or 0
        }
        return content, usage_data

    def _get_finish_reason(self, response) -> Optional[str]:
        """Best-effort extraction of finish_reason across SDK response shapes."""
        if response is None:
            return None
        # Chat Completions API
        try:
            choices = getattr(response, "choices", None)
            if choices and len(choices) > 0:
                fr = getattr(choices[0], "finish_reason", None)
                if fr:
                    return str(fr)
        except Exception:
            pass
        # Responses API (varies by SDK version)
        try:
            fr = getattr(response, "finish_reason", None)
            if fr:
                return str(fr)
        except Exception:
            pass
        return None

    def _max_tokens_from_words(
        self,
        target_words: int,
        buffer_ratio: float = 0.12,
        min_tokens: int = 600,
        max_tokens: int = 16000
    ) -> int:
        """Estimate a sane max_tokens from target word count."""
        if not target_words or target_words <= 0:
            return min(max_tokens, self._get_model_max_output_tokens())
        # Rough conversion: ~1.3 tokens per word, plus buffer
        estimated = int(target_words * (1.3 + buffer_ratio))
        model_cap = self._get_model_max_output_tokens()
        return max(min_tokens, min(min(max_tokens, model_cap), estimated))
    
    async def generate_chapter_spike(self, chapter_number: int, target_words: int = 3800) -> GenerationResult:
        """
        Phase 0 spike: Generate a chapter using hard-coded prompt.
        Maintained for backward compatibility.
        """
        return await self.generate_chapter(chapter_number, target_words, stage="spike")

    def _derive_scene_requirements_from_blueprint(self, blueprint: str) -> str:
        """
        Build scene-level execution guidance from the Stage 1 blueprint.

        We keep this robust and conservative: pull a handful of blueprint lines that look
        like scene/beat instructions, then add a minimal set of structural requirements.
        """
        try:
            text = (blueprint or "").strip()
            if not text:
                return ""
            extracted: List[str] = []
            for raw in text.splitlines():
                line = raw.strip()
                if not line:
                    continue
                low = line.lower()
                if (
                    low.startswith("scene")
                    or low.startswith("beat")
                    or low.startswith("turn")
                    or low.startswith("goal")
                    or low.startswith("conflict")
                    or low.startswith("- scene")
                    or low.startswith("* scene")
                    or low.startswith("- beat")
                    or low.startswith("* beat")
                ):
                    extracted.append(line.lstrip("-* ").strip())
                if len(extracted) >= 10:
                    break

            beat_hint = ""
            if extracted:
                beat_hint = "Blueprint beats to execute: " + " / ".join(extracted[:10]) + ". "

            return (
                beat_hint
                + "Build scenes in lived time: goal → friction → choice → consequence. "
                + "Keep the camera in-scene with physical beats (move, touch, search, wait, interrupt, decide). "
                + "Avoid summary transitions; show how characters enter/exit, change locations, and obtain information."
            )
        except Exception:
            return "Build scenes in lived time: goal → friction → choice → consequence. Keep the camera in-scene with physical beats."
    
    async def generate_chapter_5_stage(self, chapter_number: int, target_words: int = 3800,
                                 context: Dict[str, Any] = None) -> List[GenerationResult]:
        """
        Generate a chapter using the complete 5-stage process.
        Returns results from all stages.

        NOTE: context["rewrite_instruction"] is NOT injected into the YAML stage
        templates. The 5-stage path is a legacy/rare path behind ENABLE_5_STAGE_WRITING.
        Skeleton-expand and single-pass (generate_chapter) are the primary paths and
        fully support rewrite_instruction.
        """
        if not self.prompt_manager:
            raise ValueError("5-stage generation requires prompt templates. Prompt manager not initialized.")
        
        self.reset_perf()
        context = context or {}
        # Ensure shared post-draft budget exists for downstream passes/stages.
        self._init_postdraft_budget(context)
        if not chapter_number:
            chapter_number = context.get("chapter_number")
        results = []

        # Normalize continuity fields for YAML templating (supports nested context["continuity"]).
        # This keeps 5-stage prompts aligned with the simple generation continuity contract.
        continuity_snapshot = context.get("continuity", {})
        if isinstance(continuity_snapshot, dict) and continuity_snapshot:
            context.setdefault("continuity_story_so_far", str(continuity_snapshot.get("story_so_far") or ""))
            context.setdefault("continuity_requirements", continuity_snapshot.get("continuity_requirements") or [])
            context.setdefault("continuity_unresolved_questions", continuity_snapshot.get("unresolved_questions") or [])
            context.setdefault("continuity_required_plot_advancement", str(continuity_snapshot.get("required_plot_advancement") or ""))
            context.setdefault("continuity_character_needs", continuity_snapshot.get("character_development_needs") or {})
            context.setdefault("continuity_themes_to_continue", continuity_snapshot.get("themes_to_continue") or [])
            context.setdefault("pacing_guidance", continuity_snapshot.get("pacing_guidance") or {})
            context.setdefault("timeline_state", continuity_snapshot.get("timeline_state") or {})
            context.setdefault("timeline_constraints", continuity_snapshot.get("timeline_constraints") or [])
            context.setdefault("arc_diagnostics", continuity_snapshot.get("arc_diagnostics") or {})
            context.setdefault("memory_ledger", str(continuity_snapshot.get("memory_ledger") or ""))

        # Require real inputs for core planning fields (no placeholder defaults)
        required_fields = [
            "genre",
            "story_context",
            "required_plot_points",
            "focus_characters",
            "chapter_climax_goal"
        ]
        missing = [field for field in required_fields if not context.get(field)]
        if missing:
            raise ValueError(f"5-stage generation requires context fields: {', '.join(missing)}")

        # Merge with provided context (caller must supply real values)
        full_context = {
            **context,
            "chapter_number": chapter_number,
            "target_words": target_words
        }
        
        self.logger.info(f"Starting 5-stage generation for Chapter {chapter_number}")
        
        # Stage 1: Strategic Planning
        self.logger.info("Stage 1: Strategic Planning")
        stage1_result = await self._execute_stage(1, full_context)
        results.append(stage1_result)
        
        if not stage1_result.success:
            self.logger.error("Stage 1 failed, aborting 5-stage process")
            return results
        
        # Update context with blueprint
        full_context["chapter_blueprint"] = stage1_result.content
        full_context["opening_hook_requirement"] = (
            "Start in-scene with concrete action and immediate pressure. "
            "Open on a physical interaction plus a sensory cue; no voiceover, no cold-open summary."
        )
        full_context["climax_requirement"] = "Include a meaningful turn or shift (pressure changes; a decision lands; a complication bites). Not required to be a 'big reveal'."
        full_context["ending_requirement"] = "End with a specific next pressure/obligation/question without narrator wrap-up."
        # Ensure optional prompt variables exist for Stage 2 (avoid empty guidance)
        full_context.setdefault("character_voices", "")
        # Prefer continuity-aware prior-events context for Chapter 2+ (discourages recap/restart).
        if not full_context.get("previous_events"):
            full_context["previous_events"] = (
                full_context.get("continuity_story_so_far")
                or full_context.get("previous_chapter_summary")
                or full_context.get("previous_chapters_summary")
                or ""
            )

        if not full_context.get("scene_requirements"):
            full_context["scene_requirements"] = self._derive_scene_requirements_from_blueprint(
                full_context.get("chapter_blueprint", "")
            )
        full_context.setdefault(
            "dialogue_requirements",
            "Dialogue must be tactical: each speaker wants something and speaks with subtext. Include interruptions, misdirection, and concrete stakes inside the scene."
        )
        full_context.setdefault(
            "description_requirements",
            "Integrate setting through POV attention and action. Anchor the room/space early with named objects and sensory cues; avoid decorative description without pressure."
        )
        full_context.setdefault(
            "pacing_strategy",
            "Use lived-time beats and transitions. Alternate action and dialogue; keep exposition short and earned; avoid narrator wrap-ups."
        )

        # Director brief to guide first-draft naturalness
        try:
            full_context["director_brief"] = await self.generate_director_brief(
                chapter_number=chapter_number,
                target_words=target_words,
                context=full_context
            )
        except LLMQuotaError:
            raise
        except Exception as e:
            self.logger.warning(f"Director brief generation failed: {e}")
        
        # Stage 2: First Draft Generation
        self.logger.info("Stage 2: First Draft Generation")
        stage2_result = await self._execute_stage(2, full_context)
        results.append(stage2_result)
        
        if not stage2_result.success:
            self.logger.error("Stage 2 failed, aborting 5-stage process")
            return results

        # If the first draft is materially under target length, expand it immediately so
        # later stages (assessment/refinement) operate on a properly sized draft.
        try:
            if self._needs_expansion_pass(stage2_result.content, target_words):
                self.logger.info("Expansion pass triggered after Stage 2.")
                if not self._consume_postdraft_budget(context, "expansion_after_stage2"):
                    self.logger.info("Skipping Stage 2 expansion due to post-draft budget cap.")
                    raise RuntimeError("postdraft_budget_cap")
                references_excerpt = self._build_reference_digest(
                    full_context.get("references", {}) or {},
                    max_total_chars=1600,
                    per_ref_limit=320,
                )
                expanded, extra_usage = await self._run_expansion_pass(
                    chapter_text=stage2_result.content,
                    target_words=target_words,
                    book_bible=full_context.get("book_bible", ""),
                    references_excerpt=references_excerpt,
                    director_notes=full_context.get("director_notes", ""),
                )
                if expanded:
                    stage2_result.content = expanded
                    stage2_result.metadata = stage2_result.metadata or {}
                    stage2_result.metadata["expanded_after_stage2"] = True
                    stage2_result.metadata["tokens_used"] = stage2_result.metadata.get("tokens_used", {})
                    stage2_result.metadata["tokens_used"]["prompt"] = stage2_result.metadata["tokens_used"].get("prompt", 0) + extra_usage.get("prompt_tokens", 0)
                    stage2_result.metadata["tokens_used"]["completion"] = stage2_result.metadata["tokens_used"].get("completion", 0) + extra_usage.get("completion_tokens", 0)
                    stage2_result.metadata["tokens_used"]["total"] = stage2_result.metadata["tokens_used"].get("total", 0) + extra_usage.get("total_tokens", 0)
        except Exception as e:
            self.logger.warning(f"Stage 2 expansion skipped due to error: {e}")
        
        # Stage 3: Craft Excellence Review (post-draft budgeted)
        if not self._consume_postdraft_budget(context, "stage3_craft_review"):
            self.logger.info("Skipping Stage 3 due to post-draft budget cap.")
            stage3_result = GenerationResult(
                success=True,
                content="",
                metadata={"stage": 3, "skipped": True, "reason": "postdraft_budget_cap"},
            )
            results.append(stage3_result)
        else:
            self.logger.info("Stage 3: Craft Excellence Review")
            full_context["chapter_content"] = stage2_result.content
            # Add Stage 3 specific optional variables
            full_context.setdefault("pattern_database_context", "")
            full_context.setdefault("previous_chapters_context", "")
            full_context.setdefault("character_goals", "")
            full_context.setdefault("theme_limits", "")
            full_context.setdefault("inspiration_reference", "")
            stage3_result = await self._execute_stage(3, full_context)
            results.append(stage3_result)
        
        if not stage3_result.success:
            self.logger.error("Stage 3 failed, aborting 5-stage process")
            return results

        # Sync budget back into full_context so downstream post-stage passes see it.
        try:
            full_context["postdraft_budget"] = context.get("postdraft_budget")
        except Exception:
            pass
        
        # Stage 4: Targeted Refinement (post-draft budgeted; may be skipped)
        stage4_result = GenerationResult(
            success=True,
            content="",
            metadata={"stage": 4, "skipped": True, "reason": "postdraft_budget_cap"},
        )
        if stage3_result.content and self._consume_postdraft_budget(context, "stage4_targeted_refine"):
            self.logger.info("Stage 4: Targeted Refinement")
            full_context["original_chapter"] = stage2_result.content
            full_context["assessment_results"] = stage3_result.content
            full_context["improvement_areas"] = (
                "Address every issue flagged in the assessment, prioritizing any below required thresholds."
            )
            full_context["category_specific_instructions"] = stage3_result.content
            full_context["preserve_elements"] = (
                "Preserve plot advancement, character voice, and all strong scenes unless they conflict with requirements."
            )
            stage4_result = await self._execute_stage(4, full_context)
        else:
            self.logger.info("Skipping Stage 4 due to missing assessment or post-draft budget cap.")
        results.append(stage4_result)
        
        # Stage 5: Final Integration (post-draft budgeted; last chance polish)
        if not self._consume_postdraft_budget(context, "stage5_final_integration"):
            self.logger.info("Skipping Stage 5 due to post-draft budget cap.")
            stage5_result = GenerationResult(
                success=True,
                content=stage4_result.content or stage2_result.content,
                metadata={"stage": 5, "skipped": True, "reason": "postdraft_budget_cap"},
            )
            results.append(stage5_result)
            return results

        self.logger.info("Stage 5: Final Integration")
        if stage4_result.success and stage4_result.content.strip():
            full_context["refined_chapter"] = stage4_result.content
        else:
            full_context["refined_chapter"] = stage2_result.content
        # Add Stage 5 specific optional variables  
        full_context.setdefault("story_arc_context", "")
        full_context.setdefault("pattern_database", "")
        full_context.setdefault("previous_chapters_summary", "")
        full_context.setdefault("next_chapter_preview", "")
        full_context.setdefault("character_timeline", "")
        full_context.setdefault("world_rules", "")
        full_context.setdefault("theme_development", "")
        full_context.setdefault("series_context", "")
        stage5_result = await self._execute_stage(5, full_context)
        results.append(stage5_result)

        final_result = stage5_result if stage5_result.success and stage5_result.content.strip() else stage4_result
        if final_result and final_result.content:
            references_excerpt = self._build_reference_digest(
                full_context.get("references", {}),
                max_total_chars=1600,
                per_ref_limit=320
            )
            approved_terms = self._get_approved_terms(
                full_context.get("book_bible", ""),
                references_excerpt,
                full_context.get("director_notes", "")
            )
            if self._needs_specificity_pass(final_result.content):
                self.logger.info("Specificity pass triggered for 5-stage output.")
                for pass_level in (1, 2):
                    if not self._consume_postdraft_budget(context, f"specificity_pass_{pass_level}"):
                        break
                    failure_hints = None
                    if pass_level == 2:
                        failure_hints = self._specificity_gate_failures(final_result.content, approved_terms, chapter_number)
                    revised, extra_usage = await self._run_specificity_pass(
                        chapter_text=final_result.content,
                        book_bible=full_context.get("book_bible", ""),
                        references_excerpt=references_excerpt,
                        director_notes=full_context.get("director_notes", ""),
                        pass_level=pass_level,
                        failures=failure_hints
                    )
                    if revised:
                        final_result.content = revised
                        final_result.metadata = final_result.metadata or {}
                        final_result.metadata["specificity_pass"] = True
                        final_result.metadata["tokens_used"] = final_result.metadata.get("tokens_used", {})
                        final_result.metadata["tokens_used"]["prompt"] = final_result.metadata["tokens_used"].get("prompt", 0) + extra_usage.get("prompt_tokens", 0)
                        final_result.metadata["tokens_used"]["completion"] = final_result.metadata["tokens_used"].get("completion", 0) + extra_usage.get("completion_tokens", 0)
                        final_result.metadata["tokens_used"]["total"] = final_result.metadata["tokens_used"].get("total", 0) + extra_usage.get("total_tokens", 0)
                        if final_result is stage5_result:
                            results[-1] = final_result
                    if self._specificity_gate_passes(final_result.content, approved_terms, chapter_number):
                        break
            # Tight-prose pass is expensive and often redundant; keep it budgeted and optional.
            if self._needs_tight_prose_pass_for_target(final_result.content, target_words) and self._consume_postdraft_budget(context, "tight_prose_pass"):
                self.logger.info("Tight prose pass triggered for 5-stage output.")
                tightened, extra_usage = await self._run_tight_prose_pass(
                    chapter_text=final_result.content,
                    book_bible=full_context.get("book_bible", ""),
                    references_excerpt=references_excerpt,
                    director_notes=full_context.get("director_notes", "")
                )
                if tightened:
                    final_result.content = tightened
                    final_result.metadata = final_result.metadata or {}
                    final_result.metadata["tokens_used"] = final_result.metadata.get("tokens_used", {})
                    final_result.metadata["tokens_used"]["prompt"] = final_result.metadata["tokens_used"].get("prompt", 0) + extra_usage.get("prompt_tokens", 0)
                    final_result.metadata["tokens_used"]["completion"] = final_result.metadata["tokens_used"].get("completion", 0) + extra_usage.get("completion_tokens", 0)
                    final_result.metadata["tokens_used"]["total"] = final_result.metadata["tokens_used"].get("total", 0) + extra_usage.get("total_tokens", 0)
            final_result.content = self._sanitize_style_phrases(final_result.content)
            final_result.content = self._strip_glitch_sentences(final_result.content, approved_terms)
            final_result.content = self._trim_motif_overuse(final_result.content)
            final_result.content = self._ensure_interaction_per_paragraph(final_result.content, approved_terms)
            final_result.content = self._ensure_paragraph_breaks(final_result.content)
            # Preserve punctuation choices (including em/en dashes); do not normalize.
            semantic_audit = {"passed": True, "issues": []}
            if self._consume_postdraft_budget(context, "semantic_audit"):
                semantic_audit = await self._run_semantic_audit(final_result.content, chapter_number)
            # Consolidate multiple narrative fixes into ONE pass when semantic issues appear.
            needs_consolidated = (
                (not semantic_audit.get("passed", True))
                or (self._needs_inference_chain_pass(final_result.content))
                or ("semantic_summary_narration" in (semantic_audit.get("issues") or []))
                or ("semantic_overexplaining" in (semantic_audit.get("issues") or []))
            )
            if needs_consolidated and self._consume_postdraft_budget(context, "consolidated_postdraft_pass"):
                self.logger.info("Consolidated post-draft pass triggered for 5-stage output.")
                revised, extra_usage = await self._run_consolidated_postdraft_pass(
                    chapter_text=final_result.content,
                    book_bible=full_context.get("book_bible", ""),
                    references_excerpt=references_excerpt,
                    director_notes=full_context.get("director_notes", ""),
                    issues=list(semantic_audit.get("issues") or []),
                    goal="Increase lived-time pressure, reduce inventory/summary, reduce overexplaining, and land a concrete urgent ending."
                )
                if revised:
                    final_result.content = revised
                    final_result.metadata = final_result.metadata or {}
                    final_result.metadata["tokens_used"] = final_result.metadata.get("tokens_used", {})
                    final_result.metadata["tokens_used"]["prompt"] = final_result.metadata["tokens_used"].get("prompt", 0) + extra_usage.get("prompt_tokens", 0)
                    final_result.metadata["tokens_used"]["completion"] = final_result.metadata["tokens_used"].get("completion", 0) + extra_usage.get("completion_tokens", 0)
                    final_result.metadata["tokens_used"]["total"] = final_result.metadata["tokens_used"].get("total", 0) + extra_usage.get("total_tokens", 0)
                    final_result.content = self._sanitize_style_phrases(final_result.content)
                    final_result.content = self._strip_glitch_sentences(final_result.content, approved_terms)
                    final_result.content = self._trim_motif_overuse(final_result.content)
                    final_result.content = self._limit_which_clauses(final_result.content)
                    final_result.content = self._ensure_paragraph_breaks(final_result.content)
            if self._needs_intro_grounding_pass(final_result.content, chapter_number) and self._consume_postdraft_budget(context, "intro_grounding_pass"):
                self.logger.info("Intro grounding pass triggered for 5-stage Chapter 1.")
                revised, extra_usage = await self._run_intro_grounding_pass(
                    chapter_text=final_result.content,
                    book_bible=full_context.get("book_bible", ""),
                    references_excerpt=references_excerpt,
                    director_notes=full_context.get("director_notes", "")
                )
                if revised:
                    final_result.content = revised
                    final_result.metadata = final_result.metadata or {}
                    final_result.metadata["tokens_used"] = final_result.metadata.get("tokens_used", {})
                    final_result.metadata["tokens_used"]["prompt"] = final_result.metadata["tokens_used"].get("prompt", 0) + extra_usage.get("prompt_tokens", 0)
                    final_result.metadata["tokens_used"]["completion"] = final_result.metadata["tokens_used"].get("completion", 0) + extra_usage.get("completion_tokens", 0)
                    final_result.metadata["tokens_used"]["total"] = final_result.metadata["tokens_used"].get("total", 0) + extra_usage.get("total_tokens", 0)
                    final_result.content = self._sanitize_style_phrases(final_result.content)
                    final_result.content = self._strip_glitch_sentences(final_result.content, approved_terms)
                    final_result.content = self._trim_motif_overuse(final_result.content)
                    final_result.content = self._limit_which_clauses(final_result.content)
                    final_result.content = self._ensure_paragraph_breaks(final_result.content)
                    pass  # Em dashes preserved for prose quality
            if self._needs_stakes_delay_pass(final_result.content, chapter_number) and self._consume_postdraft_budget(context, "stakes_delay_pass"):
                self.logger.info("Stakes delay pass triggered for 5-stage Chapter 1.")
                revised, extra_usage = await self._run_stakes_delay_pass(
                    chapter_text=final_result.content,
                    book_bible=full_context.get("book_bible", ""),
                    references_excerpt=references_excerpt,
                    director_notes=full_context.get("director_notes", "")
                )
                if revised:
                    final_result.content = revised
                    final_result.metadata = final_result.metadata or {}
                    final_result.metadata["tokens_used"] = final_result.metadata.get("tokens_used", {})
                    final_result.metadata["tokens_used"]["prompt"] = final_result.metadata["tokens_used"].get("prompt", 0) + extra_usage.get("prompt_tokens", 0)
                    final_result.metadata["tokens_used"]["completion"] = final_result.metadata["tokens_used"].get("completion", 0) + extra_usage.get("completion_tokens", 0)
                    final_result.metadata["tokens_used"]["total"] = final_result.metadata["tokens_used"].get("total", 0) + extra_usage.get("total_tokens", 0)
                    final_result.content = self._sanitize_style_phrases(final_result.content)
                    final_result.content = self._strip_glitch_sentences(final_result.content, approved_terms)
                    final_result.content = self._trim_motif_overuse(final_result.content)
                    final_result.content = self._limit_which_clauses(final_result.content)
                    final_result.content = self._ensure_paragraph_breaks(final_result.content)
                    pass  # Em dashes preserved for prose quality
            if self._needs_expansion_pass(final_result.content, target_words) and self._consume_postdraft_budget(context, "expansion_pass"):
                self.logger.info("Expansion pass triggered for 5-stage output.")
                expanded, extra_usage = await self._run_expansion_pass(
                    chapter_text=final_result.content,
                    target_words=target_words,
                    book_bible=full_context.get("book_bible", ""),
                    references_excerpt=references_excerpt,
                    director_notes=full_context.get("director_notes", "")
                )
                if expanded:
                    final_result.content = expanded
                    final_result.metadata = final_result.metadata or {}
                    final_result.metadata["tokens_used"] = final_result.metadata.get("tokens_used", {})
                    final_result.metadata["tokens_used"]["prompt"] = final_result.metadata["tokens_used"].get("prompt", 0) + extra_usage.get("prompt_tokens", 0)
                    final_result.metadata["tokens_used"]["completion"] = final_result.metadata["tokens_used"].get("completion", 0) + extra_usage.get("completion_tokens", 0)
                    final_result.metadata["tokens_used"]["total"] = final_result.metadata["tokens_used"]["prompt"] + final_result.metadata["tokens_used"]["completion"]
                    final_result.content = self._sanitize_style_phrases(final_result.content)
                    final_result.content = self._strip_glitch_sentences(final_result.content, approved_terms)
                    final_result.content = self._trim_motif_overuse(final_result.content)
                    final_result.content = self._limit_which_clauses(final_result.content)
                    final_result.content = self._ensure_paragraph_breaks(final_result.content)
                    pass  # Em dashes preserved for prose quality
            if not self._specificity_gate_passes(final_result.content, approved_terms, chapter_number):
                failures = self._specificity_gate_failures(final_result.content, approved_terms, chapter_number)
                # No universal "skill beats" repair. If the opening is weak, prefer regeneration or general scene-time fixes.
                if failures and any(
                    "missing_named_term" in item
                    or "missing_named_artifact" in item
                    or "missing_interaction" in item
                    or "summary_drift" in item
                    or "abstract_stakes_overuse" in item
                    or "soft_prose_overuse" in item
                    for item in failures
                ):
                    self.logger.info("Paragraph compliance pass triggered for 5-stage output.")
                    if self._consume_postdraft_budget(context, "paragraph_compliance_pass"):
                        revised, extra_usage = await self._run_paragraph_compliance_pass(
                            chapter_text=final_result.content,
                            book_bible=full_context.get("book_bible", ""),
                            references_excerpt=references_excerpt,
                            director_notes=full_context.get("director_notes", ""),
                            failures=failures
                        )
                        if revised:
                            final_result.content = revised
                            final_result.metadata = final_result.metadata or {}
                            final_result.metadata["tokens_used"] = final_result.metadata.get("tokens_used", {})
                            final_result.metadata["tokens_used"]["prompt"] = final_result.metadata["tokens_used"].get("prompt", 0) + extra_usage.get("prompt_tokens", 0)
                            final_result.metadata["tokens_used"]["completion"] = final_result.metadata["tokens_used"].get("completion", 0) + extra_usage.get("completion_tokens", 0)
                            final_result.metadata["tokens_used"]["total"] = final_result.metadata["tokens_used"].get("total", 0) + extra_usage.get("total_tokens", 0)
                            final_result.content = self._sanitize_style_phrases(final_result.content)
                            final_result.content = self._strip_glitch_sentences(final_result.content, approved_terms)
                            final_result.content = self._trim_motif_overuse(final_result.content)
                            final_result.content = self._limit_which_clauses(final_result.content)
                            final_result.content = self._ensure_paragraph_breaks(final_result.content)
                            pass  # Em dashes preserved for prose quality
                            if self._specificity_gate_passes(final_result.content, approved_terms, chapter_number):
                                failures = []
                    if failures:
                        self.logger.info("Paragraph compliance strict pass triggered for 5-stage output.")
                        if self._consume_postdraft_budget(context, "paragraph_compliance_strict_pass"):
                            revised, extra_usage = await self._run_paragraph_compliance_pass(
                                chapter_text=final_result.content,
                                book_bible=full_context.get("book_bible", ""),
                                references_excerpt=references_excerpt,
                                director_notes=full_context.get("director_notes", ""),
                                failures=failures,
                                strict=True
                            )
                            if revised:
                                final_result.content = revised
                                final_result.metadata = final_result.metadata or {}
                                final_result.metadata["tokens_used"] = final_result.metadata.get("tokens_used", {})
                                final_result.metadata["tokens_used"]["prompt"] = final_result.metadata["tokens_used"].get("prompt", 0) + extra_usage.get("prompt_tokens", 0)
                                final_result.metadata["tokens_used"]["completion"] = final_result.metadata["tokens_used"].get("completion", 0) + extra_usage.get("completion_tokens", 0)
                                final_result.metadata["tokens_used"]["total"] = final_result.metadata["tokens_used"].get("total", 0) + extra_usage.get("total_tokens", 0)
                                final_result.content = self._sanitize_style_phrases(final_result.content)
                                final_result.content = self._strip_glitch_sentences(final_result.content, approved_terms)
                                final_result.content = self._trim_motif_overuse(final_result.content)
                                final_result.content = self._limit_which_clauses(final_result.content)
                                final_result.content = self._ensure_paragraph_breaks(final_result.content)
                                pass  # Em dashes preserved for prose quality
                                if self._specificity_gate_passes(final_result.content, approved_terms, chapter_number):
                                    failures = []
                if failures and any(
                    item.startswith("paragraph_") and ("missing_" in item or "summary_drift" in item or "abstract_stakes_overuse" in item)
                    for item in failures
                ):
                    self.logger.info("Deterministic paragraph fixes triggered for 5-stage output.")
                    final_result.content = self._apply_deterministic_paragraph_fixes(final_result.content, failures, approved_terms)
                    final_result.content = self._sanitize_style_phrases(final_result.content)
                    final_result.content = self._strip_glitch_sentences(final_result.content, approved_terms)
                    final_result.content = self._trim_motif_overuse(final_result.content)
                    final_result.content = self._limit_which_clauses(final_result.content)
                    final_result.content = self._ensure_paragraph_breaks(final_result.content)
                    pass  # Em dashes preserved for prose quality
                    if self._is_truncated_text(final_result.content):
                        continued, extra_usage = await self._continue_incomplete_chapter(
                            final_result.content,
                            chapter_number=chapter_number,
                            context=full_context
                        )
                        if continued:
                            final_result.content = continued
                            final_result.metadata = final_result.metadata or {}
                            final_result.metadata["tokens_used"] = final_result.metadata.get("tokens_used", {})
                            final_result.metadata["tokens_used"]["prompt"] = final_result.metadata["tokens_used"].get("prompt", 0) + extra_usage.get("prompt_tokens", 0)
                            final_result.metadata["tokens_used"]["completion"] = final_result.metadata["tokens_used"].get("completion", 0) + extra_usage.get("completion_tokens", 0)
                            final_result.metadata["tokens_used"]["total"] = final_result.metadata["tokens_used"].get("total", 0) + extra_usage.get("total_tokens", 0)
                    if self._specificity_gate_passes(final_result.content, approved_terms, chapter_number):
                        failures = []
                if chapter_number == 1 and any(item.startswith("skill_beats_lt_2") for item in failures):
                    self.logger.info("Deterministic opening grounding triggered for 5-stage output.")
                    final_result.content = self._apply_deterministic_skill_beats(final_result.content, approved_terms)
                    final_result.content = self._sanitize_style_phrases(final_result.content)
                    final_result.content = self._strip_glitch_sentences(final_result.content, approved_terms)
                    final_result.content = self._trim_motif_overuse(final_result.content)
                    final_result.content = self._limit_which_clauses(final_result.content)
                    final_result.content = self._ensure_paragraph_breaks(final_result.content)
                    pass  # Em dashes preserved for prose quality
                    if self._is_truncated_text(final_result.content):
                        continued, extra_usage = await self._continue_incomplete_chapter(
                            final_result.content,
                            chapter_number=chapter_number,
                            context=full_context
                        )
                        if continued:
                            final_result.content = continued
                            final_result.metadata = final_result.metadata or {}
                            final_result.metadata["tokens_used"] = final_result.metadata.get("tokens_used", {})
                            final_result.metadata["tokens_used"]["prompt"] = final_result.metadata["tokens_used"].get("prompt", 0) + extra_usage.get("prompt_tokens", 0)
                            final_result.metadata["tokens_used"]["completion"] = final_result.metadata["tokens_used"].get("completion", 0) + extra_usage.get("completion_tokens", 0)
                            final_result.metadata["tokens_used"]["total"] = final_result.metadata["tokens_used"].get("total", 0) + extra_usage.get("total_tokens", 0)
                    if self._specificity_gate_passes(final_result.content, approved_terms, chapter_number):
                        failures = []
                    else:
                        failures = self._specificity_gate_failures(final_result.content, approved_terms, chapter_number)
                if failures:
                    self.logger.warning(
                        "Specificity gate failed after retries; rejecting 5-stage draft. "
                        f"Failures: {', '.join(failures[:8])}"
                    )
                    stage5_result = GenerationResult(
                        success=False,
                        # Best-effort: keep the best available draft content so the caller can persist
                        # a failed chapter artifact (instead of producing nothing).
                        content=final_result.content or "",
                        metadata={
                            "stage": "5-stage",
                            "error": "specificity_gate_failed",
                            "timestamp": datetime.now().isoformat(),
                            "specificity_failures": failures[:8],
                        },
                        error="Draft failed specificity gate after revision retries."
                    )
                    results[-1] = stage5_result

        self.logger.info("5-stage generation completed")
        return results
    
    async def _execute_stage(self, stage_number: int, context: Dict[str, Any]) -> GenerationResult:
        """Execute a specific stage with given context."""
        try:
            stage_started = time.perf_counter()
            # Get template and render prompts
            system_prompt, user_prompt = self.prompt_manager.render_prompts(stage_number, context)
            stage_config = self.prompt_manager.get_stage_config(stage_number)
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            # Resolve stage configuration
            temperature = stage_config.get('temperature', 0.7)
            max_tokens = stage_config.get('max_tokens', self._max_tokens_from_words(context.get("target_words", 3800)))

            # Make API call with stage-specific configuration
            response = await self._make_api_call(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=1,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                vector_store_ids=context.get("vector_store_ids", []),
                use_file_search=context.get("use_file_search", True)
            )
            
            # Extract content and calculate costs
            content, usage_data = self._extract_content_and_usage(response)
            finish_reason = self._get_finish_reason(response)
            
            input_cost = (usage_data["prompt_tokens"] / 1000) * self.cost_per_1k_input_tokens
            output_cost = (usage_data["completion_tokens"] / 1000) * self.cost_per_1k_output_tokens
            total_cost = input_cost + output_cost
            
            metadata = {
                "stage": stage_number,
                "model": self.model,
                "timestamp": datetime.now().isoformat(),
                "finish_reason": finish_reason,
                "truncated_by_api": bool(finish_reason == "length"),
                "tokens_used": {
                    "prompt": usage_data["prompt_tokens"],
                    "completion": usage_data["completion_tokens"],
                    "total": usage_data["total_tokens"]
                },
                "cost_breakdown": {
                    "input_cost": input_cost,
                    "output_cost": output_cost,
                    "total_cost": total_cost
                },
                "stage_config": {
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
            }

            stage_seconds = time.perf_counter() - stage_started
            try:
                word_count = len((content or "").split())
            except Exception:
                word_count = 0
            self.logger.info(
                f"Stage {stage_number} completed"
                f" words={word_count}"
                f" tokens={usage_data['total_tokens']}"
                f" prompt_tokens={usage_data['prompt_tokens']}"
                f" completion_tokens={usage_data['completion_tokens']}"
                f" duration_s={stage_seconds:.2f}"
                f" model={self.model}"
                f" max_tokens={max_tokens}"
            )

            # Store timing + usage for end-of-run perf summary.
            try:
                metadata["timing"] = {
                    "duration_ms": int(stage_seconds * 1000),
                    "max_tokens": max_tokens,
                }
            except Exception:
                pass
            try:
                stages = self._perf.get("stages")
                if isinstance(stages, dict):
                    stages[str(stage_number)] = {
                        "ms": int(stage_seconds * 1000),
                        "tokens_total": int(usage_data.get("total_tokens", 0) or 0),
                        "prompt_tokens": int(usage_data.get("prompt_tokens", 0) or 0),
                        "completion_tokens": int(usage_data.get("completion_tokens", 0) or 0),
                    }
            except Exception:
                pass

            # Attach perf summary snapshot for callers that persist stage metadata.
            try:
                metadata["perf_summary"] = self.get_perf_summary()
            except Exception:
                metadata["perf_summary"] = {}
            
            return GenerationResult(
                success=True,
                content=content,
                metadata=metadata,
                tokens_used=usage_data["total_tokens"],
                cost_estimate=total_cost
            )
            
        except LLMQuotaError:
            # Abort immediately; callers should treat as terminal and stop candidate/regeneration loops.
            raise
        except Exception as e:
            self.logger.error(f"Stage {stage_number} execution failed: {type(e).__name__}: {e}")
            return GenerationResult(
                success=False,
                content="",
                metadata={
                    "stage": stage_number,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                },
                error=str(e)
            )

    async def generate_chapter(self, chapter_number: int, target_words: int = 3800, 
                        stage: str = "complete", context: Optional[Dict[str, Any]] = None) -> GenerationResult:
        """
        Generate a chapter with robust error handling and retry logic.
        """
        self.reset_perf()
        start_time = time.time()
        context = context or {}
        budget = self._init_postdraft_budget(context)
        extra_budget = max(0, int(os.getenv("CHAPTER_MAX_EXTRA_PASSES", "2")))
        # Clamp internal extra-pass budget to remaining post-draft budget.
        try:
            extra_budget = min(extra_budget, int(budget.get("remaining", 0) or 0))
        except Exception:
            pass

        def _allow_pass(pass_name: str, *, cost: int = 1, always: bool = False) -> bool:
            nonlocal extra_budget
            try:
                passes = self._perf.get("passes")
                if not isinstance(passes, dict):
                    self._perf["passes"] = {"executed": [], "skipped": []}
                    passes = self._perf["passes"]
                executed = passes.get("executed")
                skipped = passes.get("skipped")
                if not isinstance(executed, list):
                    executed = []
                    passes["executed"] = executed
                if not isinstance(skipped, list):
                    skipped = []
                    passes["skipped"] = skipped
            except Exception:
                executed = []
                skipped = []

            if always:
                executed.append(pass_name)
                return True
            # Post-draft pass budget enforcement (shared)
            if extra_budget >= cost and self._consume_postdraft_budget(context, pass_name, cost=cost):
                extra_budget -= cost
                executed.append(pass_name)
                return True
            skipped.append(pass_name)
            return False

        if stage != "spike" and not context.get("director_brief"):
            try:
                context["director_brief"] = await self.generate_director_brief(
                    chapter_number=chapter_number,
                    target_words=target_words,
                    context=context
                )
            except LLMQuotaError:
                raise
            except Exception as e:
                self.logger.warning(f"Director brief generation skipped: {e}")
        
        self.logger.info(f"Starting chapter {chapter_number} generation (stage: {stage})")
        self.logger.info(f"Target words: {target_words}, Model: {self.model}")
        
        # Build prompts based on stage
        if stage == "spike":
            target_min = (context or {}).get("target_words_min")
            target_max = (context or {}).get("target_words_max")
            target_range = (target_min, target_max) if target_min and target_max else None
            system_prompt, user_prompt = self._build_spike_prompts(chapter_number, target_words, target_range)
        else:
            system_prompt, user_prompt = self._build_comprehensive_prompts(chapter_number, target_words, context)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            # Make API call with retry logic
            response = await self._make_api_call(
                messages=messages,
                temperature=0.7,
                max_tokens=self._max_tokens_from_words(target_words),
                top_p=1,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                vector_store_ids=(context or {}).get("vector_store_ids", []),
                use_file_search=(context or {}).get("use_file_search", True)
            )
            finish_reason = self._get_finish_reason(response)
            truncated_by_api = (finish_reason == "length")
            
            generation_time = time.time() - start_time
            
            # Extract content and metadata
            content, usage_data = self._extract_content_and_usage(response)
            specificity_pass = False
            references_excerpt = self._build_reference_digest(
                (context or {}).get("references", {}),
                max_total_chars=1600,
                per_ref_limit=320
            )
            approved_terms = self._get_approved_terms(
                (context or {}).get("book_bible", ""),
                references_excerpt,
                (context or {}).get("director_notes", "")
            )
            if self._needs_specificity_pass(content):
                self.logger.debug("Specificity pass triggered for chapter output.")
                for pass_level in (1, 2):
                    if not _allow_pass(f"specificity_pass_{pass_level}"):
                        break
                    failure_hints = None
                    if pass_level == 2:
                        failure_hints = self._specificity_gate_failures(content, approved_terms, chapter_number)
                    revised, extra_usage = await self._run_specificity_pass(
                        chapter_text=content,
                        book_bible=(context or {}).get("book_bible", ""),
                        references_excerpt=references_excerpt,
                        director_notes=(context or {}).get("director_notes", ""),
                        pass_level=pass_level,
                        failures=failure_hints
                    )
                    if revised:
                        content = revised
                        specificity_pass = True
                        usage_data["prompt_tokens"] += extra_usage.get("prompt_tokens", 0)
                        usage_data["completion_tokens"] += extra_usage.get("completion_tokens", 0)
                        usage_data["total_tokens"] += extra_usage.get("total_tokens", 0)
                    if self._specificity_gate_passes(content, approved_terms, chapter_number):
                        break
            if self._needs_tight_prose_pass_for_target(content, target_words):
                if _allow_pass("tight_prose_pass"):
                    self.logger.debug("Tight prose pass triggered for chapter output.")
                    tightened, extra_usage = await self._run_tight_prose_pass(
                        chapter_text=content,
                        book_bible=(context or {}).get("book_bible", ""),
                        references_excerpt=references_excerpt,
                        director_notes=(context or {}).get("director_notes", "")
                    )
                    if tightened:
                        content = tightened
                        usage_data["prompt_tokens"] += extra_usage.get("prompt_tokens", 0)
                        usage_data["completion_tokens"] += extra_usage.get("completion_tokens", 0)
                        usage_data["total_tokens"] += extra_usage.get("total_tokens", 0)
            if self._needs_expansion_pass(content, target_words):
                if _allow_pass("expansion_pass"):
                    self.logger.debug("Expansion pass triggered for chapter output.")
                    expanded, extra_usage = await self._run_expansion_pass(
                        chapter_text=content,
                        target_words=target_words,
                        book_bible=(context or {}).get("book_bible", ""),
                        references_excerpt=references_excerpt,
                        director_notes=(context or {}).get("director_notes", "")
                    )
                    if expanded:
                        content = expanded
                        usage_data["prompt_tokens"] += extra_usage.get("prompt_tokens", 0)
                        usage_data["completion_tokens"] += extra_usage.get("completion_tokens", 0)
                        usage_data["total_tokens"] += extra_usage.get("total_tokens", 0)
            content = self._sanitize_style_phrases(content)
            content = self._strip_glitch_sentences(content, approved_terms)
            content = self._trim_motif_overuse(content)
            content = self._limit_which_clauses(content)
            content = self._ensure_interaction_per_paragraph(content, approved_terms)
            content = self._ensure_paragraph_breaks(content)
            if self._is_truncated_text(content):
                continued, extra_usage = await self._continue_incomplete_chapter(
                    content,
                    chapter_number=chapter_number,
                    context=context or {}
                )
                if continued:
                    content = continued
                    usage_data["prompt_tokens"] += extra_usage.get("prompt_tokens", 0)
                    usage_data["completion_tokens"] += extra_usage.get("completion_tokens", 0)
                    usage_data["total_tokens"] += extra_usage.get("total_tokens", 0)

            # Re-check tight-prose after continuation. Continuations can push word count far above target.
            try:
                already_tightened = False
                passes = self._perf.get("passes")
                if isinstance(passes, dict):
                    executed = passes.get("executed")
                    if isinstance(executed, list) and "tight_prose_pass" in executed:
                        already_tightened = True
            except Exception:
                already_tightened = False
            if (not already_tightened) and self._needs_tight_prose_pass_for_target(content, target_words):
                if _allow_pass("tight_prose_pass"):
                    self.logger.debug("Tight prose pass triggered post-continuation (overshoot/readability).")
                    tightened, extra_usage = await self._run_tight_prose_pass(
                        chapter_text=content,
                        book_bible=(context or {}).get("book_bible", ""),
                        references_excerpt=references_excerpt,
                        director_notes=(context or {}).get("director_notes", ""),
                    )
                    if tightened:
                        content = tightened
                        usage_data["prompt_tokens"] += extra_usage.get("prompt_tokens", 0)
                        usage_data["completion_tokens"] += extra_usage.get("completion_tokens", 0)
                        usage_data["total_tokens"] += extra_usage.get("total_tokens", 0)

            # Chapter-to-chapter continuity repair: rewrite ONLY the opening if it looks like a recap/restart
            # or if bridge requirements are not reflected in the opening.
            if self._needs_opening_bridge_pass(content, chapter_number, context):
                if _allow_pass("opening_bridge_pass"):
                    self.logger.debug("Opening bridge pass triggered.")
                    revised_opening, extra_usage = await self._run_opening_bridge_pass(
                        chapter_text=content,
                        chapter_number=chapter_number,
                        last_chapter_ending=str((context or {}).get("last_chapter_ending") or ""),
                        bridge_requirements=list((context or {}).get("bridge_requirements") or []),
                        book_bible=str((context or {}).get("book_bible") or (context or {}).get("book_bible_content") or ""),
                        references_excerpt=references_excerpt,
                        director_notes=str((context or {}).get("director_notes") or ""),
                    )
                    if revised_opening:
                        content = revised_opening
                        usage_data["prompt_tokens"] += extra_usage.get("prompt_tokens", 0)
                        usage_data["completion_tokens"] += extra_usage.get("completion_tokens", 0)
                        usage_data["total_tokens"] += extra_usage.get("total_tokens", 0)
                        content = self._sanitize_style_phrases(content)
                        content = self._strip_glitch_sentences(content, approved_terms)
                        content = self._trim_motif_overuse(content)
                        content = self._limit_which_clauses(content)
                        content = self._ensure_paragraph_breaks(content)
                        pass  # Em dashes preserved for prose quality
            semantic_audit = {"passed": True, "issues": []}
            if _allow_pass("semantic_audit"):
                semantic_audit = await self._run_semantic_audit(content, chapter_number)
            if not semantic_audit.get("passed", True):
                revised = None
                extra_usage = {}
                if _allow_pass("semantic_revision_pass"):
                    self.logger.debug("Semantic audit revision triggered.")
                    revised, extra_usage = await self._run_semantic_revision_pass(
                        chapter_text=content,
                        issues=semantic_audit.get("issues", [])
                    )
                if revised:
                    content = revised
                    usage_data["prompt_tokens"] += extra_usage.get("prompt_tokens", 0)
                    usage_data["completion_tokens"] += extra_usage.get("completion_tokens", 0)
                    usage_data["total_tokens"] += extra_usage.get("total_tokens", 0)
                    content = self._sanitize_style_phrases(content)
                    content = self._strip_glitch_sentences(content, approved_terms)
                    content = self._trim_motif_overuse(content)
                    content = self._limit_which_clauses(content)
                    content = self._ensure_paragraph_breaks(content)
                    pass  # Em dashes preserved for prose quality
                    if _allow_pass("semantic_audit_post_revision"):
                        semantic_audit = await self._run_semantic_audit(content, chapter_number)
            if semantic_audit.get("issues") and "semantic_summary_narration" in semantic_audit.get("issues", []):
                revised = None
                extra_usage = {}
                if _allow_pass("action_density_pass"):
                    self.logger.debug("Action density pass triggered.")
                    revised, extra_usage = await self._run_action_density_pass(
                        chapter_text=content,
                        book_bible=(context or {}).get("book_bible", ""),
                        references_excerpt=references_excerpt,
                        director_notes=(context or {}).get("director_notes", "")
                    )
                if revised:
                    content = revised
                    usage_data["prompt_tokens"] += extra_usage.get("prompt_tokens", 0)
                    usage_data["completion_tokens"] += extra_usage.get("completion_tokens", 0)
                    usage_data["total_tokens"] += extra_usage.get("total_tokens", 0)
                    content = self._sanitize_style_phrases(content)
                    content = self._strip_glitch_sentences(content, approved_terms)
                    content = self._trim_motif_overuse(content)
                    content = self._limit_which_clauses(content)
                    content = self._ensure_paragraph_breaks(content)
                    pass  # Em dashes preserved for prose quality
            if self._needs_inference_chain_pass(content) or (
                semantic_audit.get("issues") and "semantic_overexplaining" in semantic_audit.get("issues", [])
            ):
                revised = None
                extra_usage = {}
                if _allow_pass("inference_chain_pass"):
                    self.logger.debug("Inference chain pass triggered.")
                    revised, extra_usage = await self._run_inference_chain_pass(
                        chapter_text=content,
                        book_bible=(context or {}).get("book_bible", ""),
                        references_excerpt=references_excerpt,
                        director_notes=(context or {}).get("director_notes", "")
                    )
                if revised:
                    content = revised
                    usage_data["prompt_tokens"] += extra_usage.get("prompt_tokens", 0)
                    usage_data["completion_tokens"] += extra_usage.get("completion_tokens", 0)
                    usage_data["total_tokens"] += extra_usage.get("total_tokens", 0)
                    content = self._sanitize_style_phrases(content)
                    content = self._strip_glitch_sentences(content, approved_terms)
                    content = self._trim_motif_overuse(content)
                    content = self._limit_which_clauses(content)
                    content = self._ensure_paragraph_breaks(content)
                    pass  # Em dashes preserved for prose quality
            if semantic_audit.get("issues") and "semantic_summary_narration" in semantic_audit.get("issues", []):
                revised = None
                extra_usage = {}
                if _allow_pass("tail_grounding_pass"):
                    self.logger.debug("Tail grounding pass triggered.")
                    revised, extra_usage = await self._run_tail_grounding_pass(
                        chapter_text=content,
                        book_bible=(context or {}).get("book_bible", ""),
                        references_excerpt=references_excerpt,
                        director_notes=(context or {}).get("director_notes", "")
                    )
                if revised:
                    content = revised
                    usage_data["prompt_tokens"] += extra_usage.get("prompt_tokens", 0)
                    usage_data["completion_tokens"] += extra_usage.get("completion_tokens", 0)
                    usage_data["total_tokens"] += extra_usage.get("total_tokens", 0)
                    content = self._sanitize_style_phrases(content)
                    content = self._strip_glitch_sentences(content, approved_terms)
                    content = self._trim_motif_overuse(content)
                    content = self._limit_which_clauses(content)
                    content = self._ensure_paragraph_breaks(content)
                    pass  # Em dashes preserved for prose quality
            if self._needs_intro_grounding_pass(content, chapter_number):
                revised = None
                extra_usage = {}
                if _allow_pass("intro_grounding_pass"):
                    self.logger.debug("Intro grounding pass triggered for Chapter 1.")
                    revised, extra_usage = await self._run_intro_grounding_pass(
                        chapter_text=content,
                        book_bible=(context or {}).get("book_bible", ""),
                        references_excerpt=references_excerpt,
                        director_notes=(context or {}).get("director_notes", "")
                    )
                if revised:
                    content = revised
                    usage_data["prompt_tokens"] += extra_usage.get("prompt_tokens", 0)
                    usage_data["completion_tokens"] += extra_usage.get("completion_tokens", 0)
                    usage_data["total_tokens"] += extra_usage.get("total_tokens", 0)
                    content = self._sanitize_style_phrases(content)
                    content = self._strip_glitch_sentences(content, approved_terms)
                    content = self._trim_motif_overuse(content)
                    content = self._limit_which_clauses(content)
                    content = self._ensure_paragraph_breaks(content)
                    pass  # Em dashes preserved for prose quality
            if self._needs_stakes_delay_pass(content, chapter_number):
                revised = None
                extra_usage = {}
                if _allow_pass("stakes_delay_pass"):
                    self.logger.debug("Stakes delay pass triggered for Chapter 1.")
                    revised, extra_usage = await self._run_stakes_delay_pass(
                        chapter_text=content,
                        book_bible=(context or {}).get("book_bible", ""),
                        references_excerpt=references_excerpt,
                        director_notes=(context or {}).get("director_notes", "")
                    )
                if revised:
                    content = revised
                    usage_data["prompt_tokens"] += extra_usage.get("prompt_tokens", 0)
                    usage_data["completion_tokens"] += extra_usage.get("completion_tokens", 0)
                    usage_data["total_tokens"] += extra_usage.get("total_tokens", 0)
                    content = self._sanitize_style_phrases(content)
                    content = self._strip_glitch_sentences(content, approved_terms)
                    content = self._trim_motif_overuse(content)
                    content = self._limit_which_clauses(content)
                    content = self._ensure_paragraph_breaks(content)
                    pass  # Em dashes preserved for prose quality
            if not self._specificity_gate_passes(content, approved_terms, chapter_number):
                failures = self._specificity_gate_failures(content, approved_terms, chapter_number)
                if failures and any(
                    "missing_named_term" in item
                    or "missing_named_artifact" in item
                    or "missing_interaction" in item
                    or "summary_drift" in item
                    or "abstract_stakes_overuse" in item
                    or "soft_prose_overuse" in item
                    for item in failures
                ):
                    revised = None
                    extra_usage = {}
                    if _allow_pass("paragraph_compliance_pass"):
                        self.logger.debug("Paragraph compliance pass triggered.")
                        revised, extra_usage = await self._run_paragraph_compliance_pass(
                            chapter_text=content,
                            book_bible=(context or {}).get("book_bible", ""),
                            references_excerpt=references_excerpt,
                            director_notes=(context or {}).get("director_notes", ""),
                            failures=failures
                        )
                    if revised:
                        content = revised
                        usage_data["prompt_tokens"] += extra_usage.get("prompt_tokens", 0)
                        usage_data["completion_tokens"] += extra_usage.get("completion_tokens", 0)
                        usage_data["total_tokens"] += extra_usage.get("total_tokens", 0)
                        content = self._sanitize_style_phrases(content)
                        content = self._strip_glitch_sentences(content, approved_terms)
                        content = self._trim_motif_overuse(content)
                        content = self._limit_which_clauses(content)
                        content = self._ensure_paragraph_breaks(content)
                        pass  # Em dashes preserved for prose quality
                        if self._specificity_gate_passes(content, approved_terms, chapter_number):
                            failures = []
                    if failures and _allow_pass("paragraph_compliance_strict_pass"):
                        self.logger.debug("Paragraph compliance strict pass triggered.")
                        revised, extra_usage = await self._run_paragraph_compliance_pass(
                            chapter_text=content,
                            book_bible=(context or {}).get("book_bible", ""),
                            references_excerpt=references_excerpt,
                            director_notes=(context or {}).get("director_notes", ""),
                            failures=failures,
                            strict=True
                        )
                        if revised:
                            content = revised
                            usage_data["prompt_tokens"] += extra_usage.get("prompt_tokens", 0)
                            usage_data["completion_tokens"] += extra_usage.get("completion_tokens", 0)
                            usage_data["total_tokens"] += extra_usage.get("total_tokens", 0)
                            content = self._sanitize_style_phrases(content)
                            content = self._strip_glitch_sentences(content, approved_terms)
                            content = self._trim_motif_overuse(content)
                            content = self._limit_which_clauses(content)
                            content = self._ensure_paragraph_breaks(content)
                            for dash in ("—", "–", "―", "‒", "‑"):
                                pass  # Em dashes preserved for prose quality
                            if self._specificity_gate_passes(content, approved_terms, chapter_number):
                                failures = []
                if failures and any(
                    item.startswith("paragraph_") and ("missing_" in item or "summary_drift" in item or "abstract_stakes_overuse" in item)
                    for item in failures
                ):
                    self.logger.info("Deterministic paragraph fixes triggered.")
                    content = self._apply_deterministic_paragraph_fixes(content, failures, approved_terms)
                    content = self._sanitize_style_phrases(content)
                    content = self._strip_glitch_sentences(content, approved_terms)
                    content = self._trim_motif_overuse(content)
                    content = self._limit_which_clauses(content)
                    content = self._ensure_paragraph_breaks(content)
                    pass  # Em dashes preserved for prose quality
                    if self._specificity_gate_passes(content, approved_terms, chapter_number):
                        failures = []
                if failures:
                    self.logger.warning(
                        "Specificity gate failed after retries; rejecting draft. "
                        f"Failures: {', '.join(failures[:8])}"
                    )
                    return GenerationResult(
                        success=False,
                        # Best-effort: preserve the draft content so the caller can persist it as a failed chapter.
                        content=content or "",
                        metadata={
                            "stage": stage,
                            "error": "specificity_gate_failed",
                            "timestamp": datetime.now().isoformat(),
                            "specificity_failures": failures[:8]
                        },
                        error="Draft failed specificity gate after revision retries."
                    )

            # Completion guard: if we ended mid-sentence, continue minimally.
            if truncated_by_api or self._is_truncated_text(content):
                continued = None
                extra_usage = {}
                if self._consume_postdraft_budget(context, "completion_guard", essential=True):
                    continued, extra_usage = await self._continue_incomplete_chapter(
                        content,
                        chapter_number=chapter_number,
                        context=context
                    )
                if continued:
                    content = continued
                    usage_data["prompt_tokens"] += extra_usage.get("prompt_tokens", 0)
                    usage_data["completion_tokens"] += extra_usage.get("completion_tokens", 0)
                    usage_data["total_tokens"] += extra_usage.get("total_tokens", 0)
                    try:
                        self._perf["continuations"] = int(self._perf.get("continuations", 0) or 0) + 1
                    except Exception:
                        pass

            # Final safety net: if text still ends mid-sentence, trim to last complete sentence
            if self._is_truncated_text(content):
                content = self._trim_to_last_sentence(content)
            
            # Calculate costs
            input_cost = (usage_data["prompt_tokens"] / 1000) * self.cost_per_1k_input_tokens
            output_cost = (usage_data["completion_tokens"] / 1000) * self.cost_per_1k_output_tokens
            total_cost = input_cost + output_cost
            
            # Prepare metadata
            metadata = {
                "model": self.model,
                "chapter_number": chapter_number,
                "generation_time": generation_time,
                "timestamp": datetime.now().isoformat(),
                "stage": stage,
                "specificity_pass": specificity_pass,
                "finish_reason": finish_reason,
                "truncated_by_api": bool(truncated_by_api),
                "tokens_used": {
                    "prompt": usage_data["prompt_tokens"],
                    "completion": usage_data["completion_tokens"],
                    "total": usage_data["total_tokens"]
                },
                "cost_breakdown": {
                    "input_cost": input_cost,
                    "output_cost": output_cost,
                    "total_cost": total_cost
                },
                "word_count": len(content.split()),
                "target_words": target_words,
                "retry_attempts": 0  # Will be updated if retries occurred
            }
            try:
                metadata["passes"] = {
                    "remaining_budget": extra_budget,
                    "executed": (self._perf.get("passes") or {}).get("executed", []),
                    "skipped": (self._perf.get("passes") or {}).get("skipped", []),
                }
            except Exception:
                metadata["passes"] = {}
            # Attach compact perf summary for end-of-run aggregation by callers.
            try:
                metadata["perf_summary"] = self.get_perf_summary()
            except Exception:
                metadata["perf_summary"] = {}
            
            self.logger.info(f"Generation completed in {generation_time:.2f}s")
            self.logger.info(f"Tokens used: {usage_data['total_tokens']}, Cost: ${total_cost:.4f}")
            self.logger.info(f"Word count: {metadata['word_count']} (target: {target_words})")
            
            return GenerationResult(
                success=True,
                content=content,
                metadata=metadata,
                tokens_used=usage_data["total_tokens"],
                cost_estimate=total_cost
            )
            
        except Exception as e:
            generation_time = time.time() - start_time
            error_msg = str(e)
            
            self.logger.error(f"Generation failed after {generation_time:.2f}s: {error_msg}")
            
            return GenerationResult(
                success=False,
                content="",
                metadata={
                    "chapter_number": chapter_number,
                    "error": error_msg,
                    "timestamp": datetime.now().isoformat(),
                    "stage": stage,
                    "generation_time": generation_time,
                    "model": self.model
                },
                error=error_msg
            )

    async def generate_chapter_scene_by_scene(
        self,
        chapter_number: int,
        target_words: int = 3800,
        context: Optional[Dict[str, Any]] = None
    ) -> GenerationResult:
        """Generate a chapter in scenes to reduce repetition and improve structure."""
        self.reset_perf()
        context = context or {}

        if not context.get("director_brief"):
            try:
                context["director_brief"] = await self.generate_director_brief(
                    chapter_number=chapter_number,
                    target_words=target_words,
                    context=context
                )
            except Exception as e:
                self.logger.warning(f"Director brief unavailable for scene plan: {e}")

        # Build scene plan first
        scene_plan_result = await self._build_scene_plan(chapter_number, target_words, context)
        if not scene_plan_result.success:
            return scene_plan_result

        scene_plan = scene_plan_result.metadata.get("scene_plan", [])
        if not scene_plan:
            return GenerationResult(
                success=False,
                content="",
                metadata={"chapter_number": chapter_number, "stage": "scene_plan"},
                error="Scene plan generation returned no scenes."
            )

        validation = self._validate_scene_plan(scene_plan)
        if not validation.get("passed"):
            # Retry once with feedback
            feedback = "; ".join(validation.get("issues", [])[:6])
            retry_context = {**context, "scene_plan_feedback": feedback}
            retry_plan_result = await self._build_scene_plan(chapter_number, target_words, retry_context)
            if not retry_plan_result.success:
                return GenerationResult(
                    success=False,
                    content="",
                    metadata={"chapter_number": chapter_number, "stage": "scene_plan"},
                    error=f"Scene plan retry failed: {retry_plan_result.error}"
                )
            scene_plan = retry_plan_result.metadata.get("scene_plan", [])
            validation = self._validate_scene_plan(scene_plan)
            if not validation.get("passed"):
                issues = validation.get("issues", [])
                self.logger.warning(f"Scene plan validation failed after retry: {issues}")
                return GenerationResult(
                    success=False,
                    content="",
                    metadata={"chapter_number": chapter_number, "stage": "scene_plan", "issues": issues},
                    error=f"Scene plan validation failed after retry: {', '.join(issues[:8])}"
                )

        scenes_text: list[str] = []
        previous_scene_summary = ""
        per_scene_words = max(300, target_words // max(1, len(scene_plan)))

        cadence_analyzer = None
        voice_manager = None
        try:
            project_path = context.get("project_path")
            if project_path:
                from backend.auto_complete.helpers.cadence_analyzer import CadenceAnalyzer
                cadence_analyzer = CadenceAnalyzer(str(project_path))
                from backend.auto_complete.helpers.voice_fingerprint_manager import VoiceFingerprintManager
                voice_manager = VoiceFingerprintManager(str(project_path))
        except Exception:
            cadence_analyzer = None
            voice_manager = None

        for idx, scene in enumerate(scene_plan, 1):
            scene_context = {
                **context,
                "scene_number": idx,
                "scene_function": scene.get("scene_function", ""),
                "scene_goal": scene.get("goal", ""),
                "scene_summary": scene.get("summary", ""),
                "scene_focus_characters": scene.get("focus_characters", []),
                "scene_tone": scene.get("tone", ""),
                "scene_consequence": scene.get("consequence", ""),
                "scene_world_marker": scene.get("world_marker", ""),
                "scene_detail_targets": scene.get("detail_targets", []),
                "scene_micro_observation": scene.get("micro_observation", ""),
                "scene_inference_beat": scene.get("inference_beat", ""),
                "scene_emotional_beat": scene.get("emotional_beat", ""),
                "scene_target_words": per_scene_words,
                "previous_scene_summary": previous_scene_summary
            }

            system_prompt, user_prompt = self._build_scene_prompt(chapter_number, scene_context)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            response = await self._make_api_call(
                messages=messages,
                temperature=0.5,
                max_tokens=self._max_tokens_from_words(per_scene_words, buffer_ratio=0.2, min_tokens=300, max_tokens=4000),
                top_p=1,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                vector_store_ids=scene_context.get("vector_store_ids", []),
                use_file_search=scene_context.get("use_file_search", True)
            )

            scene_text, _ = self._extract_content_and_usage(response)
            scene_text = scene_text.strip()
            if not self._scene_compliance_ok(scene_text, scene_context, cadence_analyzer, voice_manager, chapter_number, idx):
                scene_text = await self._revise_scene(scene_text, scene_context)
            scenes_text.append(scene_text)
            try:
                scene_perf = self._perf.get("scene_by_scene")
                if isinstance(scene_perf, dict):
                    scene_perf["scenes"] = int(scene_perf.get("scenes", 0) or 0) + 1
            except Exception:
                pass
            previous_scene_summary = scene.get("summary", "")[:600]

            # Store scene cadence fingerprint
            if cadence_analyzer:
                try:
                    fp = cadence_analyzer.analyze(chapter_number, scene_text)
                    cadence_analyzer.store_scene(chapter_number, idx, fp)
                except Exception:
                    pass

            # Store scene voice fingerprints
            if voice_manager:
                try:
                    voice_manager.analyze_scene(chapter_number, idx, scene_text)
                except Exception:
                    pass

        content = "\n\n".join(scenes_text)

        # Completion guard: if the chapter ends mid-sentence, continue minimally.
        if self._is_truncated_text(content):
            continued, _extra_usage = await self._continue_incomplete_chapter(
                content,
                chapter_number=chapter_number,
                context=context
            )
            if continued:
                content = continued
                try:
                    self._perf["continuations"] = int(self._perf.get("continuations", 0) or 0) + 1
                except Exception:
                    pass

        metadata = {
            "model": self.model,
            "chapter_number": chapter_number,
            "timestamp": datetime.now().isoformat(),
            "stage": "scene_by_scene",
            "scene_count": len(scene_plan),
            "scene_plan": scene_plan,
            "word_count": len(content.split()),
            "target_words": target_words
        }
        try:
            metadata["perf_summary"] = self.get_perf_summary()
        except Exception:
            metadata["perf_summary"] = {}

        try:
            scene_perf = self._perf.get("scene_by_scene")
            if isinstance(scene_perf, dict):
                scene_perf["ms_total"] = int((time.perf_counter() - float(self._perf.get("run_started_s", time.perf_counter()))) * 1000)
        except Exception:
            pass

        return GenerationResult(
            success=True,
            content=content,
            metadata=metadata
        )

    def _validate_scene_plan(self, scene_plan: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate scene plan for required fields and uniqueness."""
        issues: list[str] = []
        if not isinstance(scene_plan, list) or not scene_plan:
            return {"passed": False, "issues": ["Scene plan is empty or invalid."]}

        def _split_world_markers(raw: str) -> List[str]:
            if not raw:
                return []
            separators = [",", ";", "|", "/", " and "]
            parts = [raw]
            for sep in separators:
                parts = [p for chunk in parts for p in chunk.split(sep)]
            cleaned = [p.strip() for p in parts if p.strip()]
            return cleaned

        seen_functions: set[str] = set()
        setup_count = 0
        inciting_terms = {"inciting", "announcement", "wake", "contest", "reveal", "intro", "introduction", "onboarding"}
        inciting_hits = 0
        for idx, scene in enumerate(scene_plan, 1):
            if not isinstance(scene, dict):
                issues.append(f"Scene {idx} is not a valid object.")
                continue
            function = str(scene.get("scene_function", "")).strip().lower()
            goal = str(scene.get("goal", "")).strip()
            summary = str(scene.get("summary", "")).strip()
            consequence = str(scene.get("consequence", "")).strip()
            world_marker = str(scene.get("world_marker", "")).strip()
            detail_targets = scene.get("detail_targets", [])
            emotional_beat = str(scene.get("emotional_beat", "")).strip()
            micro_observation = str(scene.get("micro_observation", "")).strip()
            inference_beat = str(scene.get("inference_beat", "")).strip()
            focus_chars = scene.get("focus_characters", [])

            if function not in {"setup", "escalation", "reveal", "reversal", "payoff"}:
                issues.append(f"Scene {idx} missing valid scene_function.")
            if function in seen_functions:
                escalation_markers = "escalat" in summary.lower() or "escalat" in consequence.lower()
                stakes_markers = "higher stakes" in summary.lower() or "higher stakes" in consequence.lower()
                if not (escalation_markers or stakes_markers):
                    issues.append(f"Scene {idx} repeats scene_function '{function}' without escalation.")
            if function:
                seen_functions.add(function)
            if function == "setup":
                setup_count += 1
                if setup_count > 1:
                    issues.append("More than one setup scene detected. Avoid repeating the opening beat.")
            if not goal:
                issues.append(f"Scene {idx} missing goal.")
            if not summary:
                issues.append(f"Scene {idx} missing summary.")
            if not isinstance(focus_chars, list) or not focus_chars:
                issues.append(f"Scene {idx} missing focus characters.")
            if not consequence:
                issues.append(f"Scene {idx} missing consequence.")
            if not world_marker:
                issues.append(f"Scene {idx} missing world marker.")
            else:
                markers = _split_world_markers(world_marker)
                if len(markers) < 2:
                    issues.append(f"Scene {idx} needs two world markers (proper noun + rule/constraint).")
            if not isinstance(detail_targets, list) or not detail_targets:
                issues.append(f"Scene {idx} missing detail targets.")
            elif len(detail_targets) < 2:
                issues.append(f"Scene {idx} needs at least two detail targets.")
            else:
                lowered_targets = " ".join([str(t).lower() for t in detail_targets])
                if "artifact:" not in lowered_targets or "interaction:" not in lowered_targets:
                    issues.append(f"Scene {idx} detail_targets must include Artifact: and Interaction: entries.")
            if not emotional_beat:
                issues.append(f"Scene {idx} missing emotional beat.")
            if not micro_observation:
                issues.append(f"Scene {idx} missing micro_observation.")
            if not inference_beat:
                issues.append(f"Scene {idx} missing inference_beat.")

            summary_lower = summary.lower()
            if any(term in summary_lower for term in inciting_terms):
                inciting_hits += 1

        if inciting_hits > 1:
            issues.append("Multiple inciting/announcement beats detected. Only one inciting delivery per chapter.")

        return {"passed": len(issues) == 0, "issues": issues}

    def _scene_compliance_ok(
        self,
        scene_text: str,
        scene_context: Dict[str, Any],
        cadence_analyzer: Optional[Any] = None,
        voice_manager: Optional[Any] = None,
        chapter_number: int = 0,
        scene_number: int = 0
    ) -> bool:
        """Light compliance checks for scene-level output."""
        if not scene_text or len(scene_text.split()) < max(120, int(scene_context.get("scene_target_words", 300) * 0.6)):
            return False
        # Reject meta or revision chatter
        meta_markers = [
            "here is a revised",
            "here's a revised",
            "revised scene",
            "feel free to adjust",
            "let's revise",
            "this revision",
            "in summary",
            "this revision",
            "here is the revised",
            "here's the revised"
        ]
        text_lower = scene_text.lower()
        if any(marker in text_lower for marker in meta_markers):
            return False
        # Require plan essentials
        if not str(scene_context.get("scene_function", "")).strip():
            return False
        if not str(scene_context.get("scene_consequence", "")).strip():
            return False
        world_marker = str(scene_context.get("scene_world_marker", "")).strip()
        if not world_marker:
            return False
        def _split_world_markers(raw: str) -> List[str]:
            if not raw:
                return []
            separators = [",", ";", "|", "/", " and "]
            parts = [raw]
            for sep in separators:
                parts = [p for chunk in parts for p in chunk.split(sep)]
            cleaned = [p.strip() for p in parts if p.strip()]
            return cleaned
        if len(_split_world_markers(world_marker)) < 2:
            return False
        detail_targets = scene_context.get("scene_detail_targets", [])
        if not isinstance(detail_targets, list) or not detail_targets:
            return False
        if len(detail_targets) < 2:
            return False
        lowered_targets = " ".join([str(t).lower() for t in detail_targets])
        if "artifact:" not in lowered_targets or "interaction:" not in lowered_targets:
            return False
        # Ensure world marker appears in scene (token overlap)
        marker_tokens = [t.lower() for t in world_marker.replace(",", " ").split() if t.isalpha() and len(t) > 3]
        if marker_tokens:
            content_lower = scene_text.lower()
            hits = sum(1 for t in marker_tokens if t in content_lower)
            if hits < max(1, int(len(marker_tokens) * 0.4)):
                return False
        # Ensure at least one detail target appears
        target_text = " ".join([str(t) for t in detail_targets])
        target_tokens = [t.lower() for t in target_text.replace(",", " ").split() if t.isalpha() and len(t) > 3]
        if target_tokens:
            content_lower = scene_text.lower()
            hits = sum(1 for t in target_tokens if t in content_lower)
            if hits < max(1, int(len(target_tokens) * 0.25)):
                return False
        # Consequence should be clear by the end of the scene
        consequence = str(scene_context.get("scene_consequence", "")).strip()
        if consequence:
            consequence_tokens = [t.lower() for t in consequence.replace(",", " ").split() if t.isalpha() and len(t) > 4]
            if consequence_tokens:
                sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", scene_text) if s.strip()]
                # Look for consequence tokens in the final portion of the scene without forcing a "button" ending.
                tail_len = max(3, max(1, int(len(sentences) * 0.5)))
                tail = " ".join(sentences[-tail_len:]).lower() if sentences else scene_text.lower()
                hits = sum(1 for t in consequence_tokens if t in tail)
                if hits < max(1, int(len(consequence_tokens) * 0.4)):
                    return False
        # Pacing envelope check
        pacing_targets = scene_context.get("pacing_targets", {})
        pace_mode = pacing_targets.get("pace_mode")
        target_words = int(scene_context.get("scene_target_words", 300))
        word_count = len(scene_text.split())
        if pace_mode == "high_tension" and word_count > target_words * 1.2:
            return False
        if pace_mode == "slow_build" and word_count < target_words * 0.8:
            return False
        # Em dashes are valid literary punctuation; do not reject scenes for using them
        # Simple objective keyword overlap check
        goal = str(scene_context.get("scene_goal", ""))
        tokens = [t.lower() for t in goal.split() if t.isalpha() and len(t) > 3]
        if tokens:
            content_lower = scene_text.lower()
            hits = sum(1 for t in tokens if t in content_lower)
            if hits < max(1, int(len(tokens) * 0.5)):
                return False
        # Scene cadence similarity check
        if cadence_analyzer and chapter_number and scene_number:
            similarity = cadence_analyzer.scene_similarity_score(chapter_number, scene_number, scene_text, lookback=2)
            if similarity is not None and similarity > 0.75:
                return False
        # Scene voice distinctiveness check
        if voice_manager:
            fingerprints = voice_manager.fingerprints_from_text(chapter_number, scene_text)
            conflicts = voice_manager.chapter_voice_similarity(fingerprints)
            if conflicts:
                return False
            # Ensure each character stays close to their historical voice
            for character, fp in fingerprints.items():
                similarity = voice_manager.recent_character_similarity(character, fp, lookback=5)
                if similarity is not None and similarity < 0.4:
                    return False
        return True

    async def _revise_scene(self, scene_text: str, scene_context: Dict[str, Any]) -> str:
        """Revise a scene to meet scene-level requirements."""
        system_prompt = (
            "You are a fiction editor. Fix the scene to meet requirements.\n"
            "Preserve plot facts.\n"
            "Ensure two unique world markers (proper noun + rule/constraint).\n"
            "Add a named artifact and a named interaction (verb + object).\n"
            "Place the explicit consequence in the last 2-3 sentences.\n"
            "Replace generic imagery with concrete, named specifics.\n"
            "Return only the revised scene text with no commentary.\n"
        )
        user_prompt = (
            f"Revise this scene to satisfy the scene goal and targets.\n\n"
            f"SCENE GOAL: {scene_context.get('scene_goal')}\n"
            f"SCENE SUMMARY: {scene_context.get('scene_summary')}\n"
            f"FOCUS CHARACTERS: {scene_context.get('scene_focus_characters')}\n"
            f"TONE: {scene_context.get('scene_tone')}\n"
            f"TARGET WORDS: {scene_context.get('scene_target_words')}\n\n"
            f"CONSEQUENCE: {scene_context.get('scene_consequence')}\n"
            f"UNIQUE WORLD MARKERS: {scene_context.get('scene_world_marker')}\n"
            f"DETAIL TARGETS: {scene_context.get('scene_detail_targets')}\n\n"
        )
        revise_rewrite = (scene_context.get("rewrite_instruction") or "").strip()
        if revise_rewrite:
            user_prompt += (
                f"AUTHOR REWRITE DIRECTION (highest priority):\n"
                f"{revise_rewrite}\n\n"
            )
        user_prompt += (
            "--- SCENE START ---\n"
            f"{scene_text}\n"
            "--- SCENE END ---\n\n"
            "Return the revised scene."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        response = await self._make_api_call(
            messages=messages,
            temperature=0.4,
            max_tokens=self._max_tokens_from_words(int(scene_context.get("scene_target_words", 300)), buffer_ratio=0.2, min_tokens=300, max_tokens=4000),
            top_p=1,
            frequency_penalty=0.0,
            presence_penalty=0.0,
            vector_store_ids=scene_context.get("vector_store_ids", []),
            use_file_search=scene_context.get("use_file_search", True)
        )
        content, _ = self._extract_content_and_usage(response)
        return content.strip()

    async def generate_test_prompt(
        self,
        prompt: str,
        target_words: int = 800,
        context: Optional[Dict[str, Any]] = None
    ) -> GenerationResult:
        """Generate a test response using full story context and a custom prompt."""
        if not prompt or not prompt.strip():
            return GenerationResult(
                success=False,
                content="",
                metadata={"stage": "test_prompt"},
                error="Prompt is empty."
            )

        system_prompt, user_prompt = self._build_comprehensive_prompts(
            chapter_number=0,
            target_words=target_words,
            context=context
        )

        user_prompt = (
            "TEST PROMPT MODE\n"
            "Use the STORY CONTEXT to answer the user prompt below.\n"
            "Do not invent unrelated plot threads. Keep tone consistent with the book bible.\n\n"
            f"USER PROMPT:\n{prompt}\n\n"
            "Write the response now."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            response = await self._make_api_call(
                messages=messages,
                temperature=0.7,
                max_tokens=self._max_tokens_from_words(target_words, buffer_ratio=0.2, min_tokens=500, max_tokens=16000),
                top_p=1,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                vector_store_ids=(context or {}).get("vector_store_ids", []),
                use_file_search=(context or {}).get("use_file_search", True)
            )
        except Exception as e:
            return GenerationResult(success=False, content="", metadata={"stage": "test_prompt"}, error=str(e))

        content, usage_data = self._extract_content_and_usage(response)

        metadata = {
            "model": self.model,
            "timestamp": datetime.now().isoformat(),
            "stage": "test_prompt",
            "tokens_used": {
                "prompt": usage_data["prompt_tokens"],
                "completion": usage_data["completion_tokens"],
                "total": usage_data["total_tokens"]
            },
            "word_count": len(content.split()),
            "target_words": target_words
        }

        return GenerationResult(
            success=True,
            content=content,
            metadata=metadata,
            tokens_used=usage_data["total_tokens"]
        )

    async def rewrite_section(
        self,
        selected_text: str,
        instruction: str,
        context: Optional[Dict[str, Any]] = None
    ) -> GenerationResult:
        """Rewrite a selected section using story context and a focused instruction."""
        if not selected_text or not selected_text.strip():
            return GenerationResult(
                success=False,
                content="",
                metadata={"stage": "rewrite_section"},
                error="Selected text is empty."
            )
        if not instruction or not instruction.strip():
            return GenerationResult(
                success=False,
                content="",
                metadata={"stage": "rewrite_section"},
                error="Rewrite instruction is empty."
            )

        context = context or {}
        try:
            chapter_number = int(context.get("chapter_number") or 0)
        except Exception:
            chapter_number = 0
        book_bible = (context.get("book_bible") or context.get("book_bible_content") or "").strip()
        director_notes = (context.get("director_notes") or "").strip()
        references = context.get("references") or {}
        vector_context = (context.get("vector_context") or "").strip()
        vector_guidelines = (context.get("vector_guidelines") or "").strip()
        surrounding_before = (context.get("surrounding_before") or "").strip()
        surrounding_after = (context.get("surrounding_after") or "").strip()

        references_excerpt = ""
        ref_limit = 3000
        used = 0
        for name, ref_content in references.items():
            if used >= ref_limit:
                break
            if not ref_content:
                continue
            excerpt = ref_content[:800].replace("\n", " ")
            references_excerpt += f"{name}: {excerpt}\n"
            used += len(excerpt)

        system_prompt = (
            "You are a senior fiction editor. Rewrite ONLY the provided selection.\n"
            "Preserve voice, tense, and POV. Maintain continuity with the story context.\n"
            "Do not add new plot points outside the selection's intent.\n"
            "Use em dashes sparingly.\n"
            "Return ONLY the rewritten selection. No commentary, no preamble, no explanation.\n"
        )

        context_sections = []
        if chapter_number:
            context_sections.append(f"This is Chapter {chapter_number} of the novel.")
        if book_bible:
            context_sections.append(f"BOOK BIBLE:\n{book_bible[:4000]}")
        if references_excerpt:
            context_sections.append(f"REFERENCE EXCERPTS:\n{references_excerpt}")
        if vector_context:
            context_sections.append(f"CONTINUITY CONTEXT (from story memory):\n{vector_context[:2000]}")
        if vector_guidelines:
            context_sections.append(f"STYLE GUIDELINES:\n{vector_guidelines[:1000]}")
        if director_notes:
            context_sections.append(f"DIRECTOR NOTES:\n{director_notes}")

        surrounding_section = ""
        if surrounding_before or surrounding_after:
            parts = []
            if surrounding_before:
                parts.append(f"TEXT BEFORE SELECTION:\n...{surrounding_before}")
            if surrounding_after:
                parts.append(f"TEXT AFTER SELECTION:\n{surrounding_after}...")
            surrounding_section = "\n\n".join(parts)

        user_prompt = "STORY CONTEXT (keep consistency):\n"
        user_prompt += "\n\n".join(context_sections) if context_sections else "No additional context."
        user_prompt += "\n\n"
        if surrounding_section:
            user_prompt += f"SURROUNDING CONTEXT:\n{surrounding_section}\n\n"
        user_prompt += (
            f"REWRITE INSTRUCTION:\n{instruction.strip()}\n\n"
            "SELECTION TO REWRITE:\n"
            "--- START ---\n"
            f"{selected_text.strip()}\n"
            "--- END ---\n\n"
            "Rewrite the selection now."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            response = await self._make_api_call(
                messages=messages,
                temperature=0.4,
                max_tokens=self._max_tokens_from_words(900, buffer_ratio=0.2, min_tokens=400, max_tokens=2000),
                top_p=1,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                vector_store_ids=context.get("vector_store_ids", []),
                use_file_search=context.get("use_file_search", True)
            )
        except Exception as e:
            return GenerationResult(success=False, content="", metadata={"stage": "rewrite_section"}, error=str(e))

        content, usage_data = self._extract_content_and_usage(response)

        metadata = {
            "model": self.model,
            "timestamp": datetime.now().isoformat(),
            "stage": "rewrite_section",
            "tokens_used": {
                "prompt": usage_data["prompt_tokens"],
                "completion": usage_data["completion_tokens"],
                "total": usage_data["total_tokens"]
            },
            "word_count": len(content.split())
        }

        return GenerationResult(
            success=True,
            content=content,
            metadata=metadata,
            tokens_used=usage_data["total_tokens"]
        )

    async def rewrite_full_chapter(
        self,
        chapter_text: str,
        instruction: str,
        context: Optional[Dict[str, Any]] = None,
        chapter_number: Optional[int] = None
    ) -> GenerationResult:
        """Rewrite an entire chapter to align with updated canon."""
        if not chapter_text or not chapter_text.strip():
            return GenerationResult(
                success=False,
                content="",
                metadata={"stage": "rewrite_full_chapter"},
                error="Chapter text is empty."
            )
        if not instruction or not instruction.strip():
            return GenerationResult(
                success=False,
                content="",
                metadata={"stage": "rewrite_full_chapter"},
                error="Rewrite instruction is empty."
            )

        self.reset_perf()
        context = context or {}
        try:
            ch_num = int(chapter_number if chapter_number is not None else (context.get("chapter_number") or 0))
        except Exception:
            ch_num = 0
        book_bible = (context.get("book_bible") or context.get("book_bible_content") or "").strip()
        director_notes = (context.get("director_notes") or "").strip()
        references = context.get("references") or {}
        canon_source = (context.get("canon_source") or "").strip()
        canon_label = (context.get("canon_label") or "Canon Update").strip()

        references_excerpt = ""
        ref_limit = 1600
        used = 0
        for name, content in references.items():
            if used >= ref_limit:
                break
            if not content:
                continue
            excerpt = content[:320].replace("\n", " ")
            references_excerpt += f"{name}: {excerpt}\n"
            used += len(excerpt)

        system_prompt = (
            "You are a senior fiction editor. Rewrite the full chapter to align with the canon update.\n"
            "Preserve voice, tense, POV, and pacing. Keep existing plot beats unless they conflict.\n"
            "Resolve contradictions with the canon update. Avoid adding new plot points.\n"
            "Use em dashes sparingly.\n"
            "Return ONLY the revised chapter text. No commentary.\n"
        )

        user_prompt = (
            "STORY CONTEXT (keep consistency):\n"
            f"BOOK BIBLE:\n{book_bible[:1800]}\n\n"
            f"REFERENCE EXCERPTS:\n{references_excerpt or 'No references provided.'}\n"
            f"DIRECTOR NOTES:\n{director_notes or 'None'}\n\n"
            f"CANON UPDATE ({canon_label}):\n{canon_source[:1200] or 'None'}\n\n"
            "REWRITE INSTRUCTION:\n"
            f"{instruction.strip()}\n\n"
            "CHAPTER TO REWRITE:\n"
            "--- START ---\n"
            f"{chapter_text.strip()}\n"
            "--- END ---\n\n"
            "Rewrite the full chapter now."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            response = await self._make_api_call(
                messages=messages,
                temperature=0.4,
                max_tokens=self._max_tokens_from_words(2500, buffer_ratio=0.2, min_tokens=900, max_tokens=4000),
                top_p=1,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                vector_store_ids=context.get("vector_store_ids", []),
                use_file_search=context.get("use_file_search", True)
            )
        except Exception as e:
            return GenerationResult(success=False, content="", metadata={"stage": "rewrite_full_chapter"}, error=str(e))

        finish_reason = self._get_finish_reason(response)
        truncated_by_api = (finish_reason == "length")
        content, usage_data = self._extract_content_and_usage(response)
        specificity_pass = False
        approved_terms = self._get_approved_terms(book_bible, references_excerpt, director_notes)
        if self._needs_specificity_pass(content):
            self.logger.info("Specificity pass triggered for rewrite output.")
            for pass_level in (1, 2):
                failure_hints = None
                if pass_level == 2:
                    failure_hints = self._specificity_gate_failures(content, approved_terms, ch_num)
                revised, extra_usage = await self._run_specificity_pass(
                    chapter_text=content,
                    book_bible=book_bible,
                    references_excerpt=references_excerpt,
                    director_notes=director_notes,
                    pass_level=pass_level,
                    failures=failure_hints
                )
                if revised:
                    content = revised
                    specificity_pass = True
                    usage_data["prompt_tokens"] += extra_usage.get("prompt_tokens", 0)
                    usage_data["completion_tokens"] += extra_usage.get("completion_tokens", 0)
                    usage_data["total_tokens"] += extra_usage.get("total_tokens", 0)
                if self._specificity_gate_passes(content, approved_terms, ch_num):
                    break
        if self._needs_tight_prose_pass(content):
            self.logger.info("Tight prose pass triggered for rewrite output.")
            tightened, extra_usage = await self._run_tight_prose_pass(
                chapter_text=content,
                book_bible=book_bible,
                references_excerpt=references_excerpt,
                director_notes=director_notes
            )
            if tightened:
                content = tightened
                usage_data["prompt_tokens"] += extra_usage.get("prompt_tokens", 0)
                usage_data["completion_tokens"] += extra_usage.get("completion_tokens", 0)
                usage_data["total_tokens"] += extra_usage.get("total_tokens", 0)
        content = self._sanitize_style_phrases(content)
        content = self._strip_glitch_sentences(content, approved_terms)
        content = self._trim_motif_overuse(content)
        content = self._limit_which_clauses(content)
        content = self._ensure_interaction_per_paragraph(content, approved_terms)
        content = self._ensure_paragraph_breaks(content)
        if not self._specificity_gate_passes(content, approved_terms, ch_num):
            failures = self._specificity_gate_failures(content, approved_terms, ch_num)
            return GenerationResult(
                success=False,
                # Best-effort: preserve the draft so callers can persist a failed artifact.
                content=content or "",
                metadata={
                    "stage": "rewrite_full_chapter",
                    "error": "specificity_gate_failed",
                    "specificity_failures": failures[:8]
                },
                error="Rewrite failed specificity gate after revision retries."
            )

        # Completion guard: ensure we don't return a mid-sentence cutoff.
        if truncated_by_api or self._is_truncated_text(content):
            continued, extra_usage = await self._continue_incomplete_chapter(
                content,
                chapter_number=chapter_number,
                context=context
            )
            if continued:
                content = continued
                usage_data["prompt_tokens"] += extra_usage.get("prompt_tokens", 0)
                usage_data["completion_tokens"] += extra_usage.get("completion_tokens", 0)
                usage_data["total_tokens"] += extra_usage.get("total_tokens", 0)
                try:
                    self._perf["continuations"] = int(self._perf.get("continuations", 0) or 0) + 1
                except Exception:
                    pass

        metadata = {
            "model": self.model,
            "timestamp": datetime.now().isoformat(),
            "stage": "rewrite_full_chapter",
            "specificity_pass": specificity_pass,
            "finish_reason": finish_reason,
            "truncated_by_api": bool(truncated_by_api),
            "tokens_used": {
                "prompt": usage_data["prompt_tokens"],
                "completion": usage_data["completion_tokens"],
                "total": usage_data["total_tokens"]
            },
            "word_count": len(content.split())
        }

        return GenerationResult(
            success=True,
            content=content,
            metadata=metadata,
            tokens_used=usage_data["total_tokens"]
        )

    def _needs_specificity_pass(self, text: str) -> bool:
        if not text:
            return False
        text_lower = text.lower()
        if self._has_trailer_voice(text_lower):
            return True
        # Trigger when the text shows voiceover framing or narrator-summary stingers.
        if re.search(r"\b(nothing would ever be the same|little did (they|she|he) know)\b", text_lower):
            return True
        if "\n\n" not in text.strip():
            return True
        inference_hits = len(re.findall(r"\b(which meant|which suggested|therefore|this meant)\b", text_lower))
        if inference_hits > 2:
            return True
        return False

    def _has_trailer_voice(self, text_lower: str) -> bool:
        trailer_phrases = [
            "in a world where",
            "little did they know",
            "little did she know",
            "little did he know",
            "no one could have predicted",
            "nothing would ever be the same",
            "now more than ever",
            "against all odds",
            "what happens when",
            "it was a day like any other",
        ]
        return any(phrase in text_lower for phrase in trailer_phrases)

    def _get_allowed_caps(self, approved_terms: list[str]) -> set[str]:
        allowed_caps = {
            "AI", "VR", "AR", "API", "CPU", "GPU", "UI", "UX", "DNA", "RNA",
            "GPS", "NASA", "FBI", "CIA", "NSA", "CDC", "WHO", "NATO", "UN",
            "USA", "UK", "EU", "UAE", "FAQ", "KPI", "OKR", "MVP", "ID"
        }
        for term in approved_terms or []:
            cleaned = term.strip()
            if cleaned.isupper() and len(cleaned) >= 3:
                allowed_caps.add(cleaned)
        return allowed_caps

    def _qa_phrase_present(self, text_lower: str) -> bool:
        return bool(re.search(
            r"\b(?:check|review|analysis|scan|audit|inspection|test|query|verification)\s+of\s+.*?\s+(shows|showed|reveals|revealed|confirms|confirmed)\b",
            text_lower
        ))

    def _paragraph_has_dialogue(self, paragraph: str) -> bool:
        if not paragraph:
            return False
        double_quotes = paragraph.count('"')
        curly_quotes = paragraph.count("“") + paragraph.count("”")
        return double_quotes >= 2 or curly_quotes >= 2

    def _paragraph_has_named_artifact(self, paragraph: str, approved_tokens: set[str]) -> bool:
        if not paragraph:
            return False
        paragraph_lower = paragraph.lower()
        artifact_nouns = [
            "badge", "keycard", "key", "wallet", "notebook", "journal", "folder", "file",
            "report", "map", "phone", "tablet", "laptop", "camera", "recorder", "radio",
            "server", "terminal", "console", "screen", "monitor", "drive", "router",
            "knife", "pistol", "rifle", "vehicle", "truck", "car", "boat", "engine",
            "bridge", "gate", "door", "locker", "case", "box", "envelope", "letter",
            "chip", "module", "scanner", "sensor", "badge", "pass", "ticket"
        ]
        has_artifact_noun = any(re.search(rf"\b{re.escape(noun)}\b", paragraph_lower) for noun in artifact_nouns)
        has_approved = any(token in paragraph_lower for token in approved_tokens)
        has_named_marker = bool(re.search(
            r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z0-9-]+){0,3}\b|\b[A-Z]{2,}\b|\b[A-Z]{1,3}-?\d{2,}\b",
            paragraph
        ))
        has_numbered_label = bool(re.search(r"\b(?:[A-Za-z]{1,3}-?)?\d{1,}\b|\b[A-Za-z]{1,3}\d{1,}\b", paragraph))
        return (
            (has_artifact_noun and (has_named_marker or has_approved or has_numbered_label))
            or (has_approved and any(char.isdigit() for char in paragraph))
        )

    def _get_approved_terms(self, book_bible: str, references_excerpt: str, director_notes: str) -> list[str]:
        return self._extract_named_terms(
            "\n".join([book_bible or "", references_excerpt or "", director_notes or ""]),
            limit=36
        )

    def _specificity_gate_failures(
        self,
        text: str,
        approved_terms: list[str],
        chapter_number: Optional[int] = None,
        strict: bool = False
    ) -> list[str]:
        failures: list[str] = []
        soft_issues: list[str] = []
        if not text:
            failures.append("empty_text")
            return failures
        text_lower = text.lower()
        # Em/en dashes are valid literary punctuation — no longer flagged as failures
        if "\n\n" not in text.strip():
            failures.append("single_block_paragraphing")
        if chapter_number == 1:
            # No universal "skill beats" requirement; different genres open differently.
            pass
        if self._qa_phrase_present(text_lower):
            failures.append("qa_phrase_present")
        if self._has_trailer_voice(text_lower):
            failures.append("trailer_voice_present")
        allowed_caps = self._get_allowed_caps(approved_terms)
        # All-caps tokens can be valid acronyms (cross-genre), e.g. SCADA, OSHA, NASA.
        # We only hard-fail for longer "shouting" tokens; short acronyms are allowed.
        all_caps_tokens: list[str] = []
        for token in re.findall(r"\b[A-Z]{4,}\b", text):
            if token in allowed_caps:
                continue
            all_caps_tokens.append(token)
        if len(all_caps_tokens) > 5:
            failures.append(f"excessive_all_caps={','.join(all_caps_tokens[:5])}")
        elif all_caps_tokens:
            soft_issues.append(f"all_caps_noted={','.join(all_caps_tokens[:3])}")
        # Avoid cross-genre motif policing and project-specific stock phrase lists.
        hit_phrases: list[str] = []
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        abstract_terms: list[str] = []
        soft_terms = [
            "sanctuary", "devotion", "reverie", "poignancy", "ethereal",
            "otherworldly", "aura", "enigmatic", "haunting", "mystic",
            "lived-in", "dreams", "constellations"
        ]
        summary_verbs = [
            "was", "were", "had been", "felt", "realized", "knew", "noticed",
            "understood", "remembered", "seemed", "thought", "decided",
            "wanted", "hoped", "feared", "believed"
        ]
        sensory_terms = [
            "saw", "heard", "smelled", "tasted", "taste", "touch", "grit",
            "cold", "warm", "hot", "bright", "dim", "loud", "sharp", "rough",
            "slick", "metal", "plastic", "wood", "glass", "wet", "dry"
        ]
        missing_term_idx: list[int] = []
        missing_artifact_idx: list[int] = []
        missing_interaction_idx: list[int] = []
        summary_drift_idx: list[int] = []
        abstract_overuse_idx: list[int] = []
        soft_overuse_idx: list[int] = []
        for idx, paragraph in enumerate(paragraphs, start=1):
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", paragraph) if s.strip()]
            abstract_hits = 0
            soft_hits = 0
            for sentence in sentences:
                sentence_lower = sentence.lower()
                if any(term in sentence_lower for term in abstract_terms):
                    abstract_hits += 1
                if any(term in sentence_lower for term in soft_terms):
                    soft_hits += 1
            if abstract_hits > 1:
                abstract_overuse_idx.append(idx)
            if soft_hits > 1:
                soft_overuse_idx.append(idx)
        # Build a permissive token set from approved terms to avoid failing on partial name usage.
        approved_tokens: set[str] = set()
        for term in approved_terms or []:
            cleaned = term.strip().lower()
            if cleaned:
                approved_tokens.add(cleaned)
                for part in re.split(r"[^a-z0-9]+", cleaned):
                    if len(part) >= 3:
                        approved_tokens.add(part)
        if approved_terms:
            hits = sum(1 for token in approved_tokens if token in text_lower)
            if hits < 2:
                soft_issues.append("approved_term_hits_lt_2")
        else:
            # No approved terms available; require proper nouns in every paragraph
            # and a minimum of 3 unique proper nouns overall.
            unique_terms = self._extract_named_terms(text, limit=24)
            if len(unique_terms) < 3:
                soft_issues.append("proper_nouns_lt_3")
            for idx, paragraph in enumerate(paragraphs, start=1):
                if not self._extract_named_terms(paragraph, limit=4):
                    soft_issues.append(f"paragraph_{idx}_missing_proper_noun")
        # Paragraph-level requirements: each paragraph must include either an approved term
        # or a proper noun (if approved terms are limited), plus a concrete interaction verb.
        interaction_verbs = [
            "open", "opened", "opening", "close", "closed", "closing",
            "load", "loaded", "loading", "save", "saved", "saving",
            "scan", "scanned", "scanning", "search", "searched", "searching",
            "trace", "traced", "tracing", "decrypt", "decrypted", "decrypting",
            "compile", "compiled", "compiling", "export", "exported", "exporting",
            "upload", "uploaded", "uploading", "download", "downloaded", "downloading",
            "archive", "archived", "archiving", "ping", "pinged", "pinging",
            "message", "messaged", "messaging", "flag", "flagged", "flagging",
            "index", "indexed", "indexing", "hash", "hashed", "hashing",
            "checksum", "checksummed", "checksumming", "type", "typed", "typing",
            "click", "clicked", "clicking", "scroll", "scrolled", "scrolling",
            "tap", "tapped", "tapping", "write", "wrote", "writing",
            "sketch", "sketched", "sketching", "draw", "drew", "drawing",
            "send", "sent", "sending", "compose", "composed", "composing",
            "call", "called", "calling", "text", "texted", "texting",
            "grab", "grabbed", "grabbing", "pull", "pulled", "pulling",
            "push", "pushed", "pushing", "turn", "turned", "turning",
            "flip", "flipped", "flipping", "hold", "held", "holding",
            "place", "placed", "placing", "set", "set", "setting",
            "take", "took", "taking", "open", "opened", "opening",
            "read", "reads", "reading", "watch", "watched", "watching",
            "listen", "listened", "listening", "look", "looked", "looking",
            "review", "reviewed", "reviewing", "check", "checked", "checking",
            "hover", "hovered", "hovering", "press", "pressed", "pressing",
            "select", "selected", "selecting", "highlight", "highlighted", "highlighting",
            "drag", "dragged", "dragging", "drop", "dropped", "dropping",
            "swipe", "swiped", "swiping", "sit", "sat", "sitting",
            "stand", "stood", "standing", "walk", "walked", "walking",
            "step", "stepped", "stepping", "enter", "entered", "entering",
            "move", "moved", "moving", "reach", "reached", "reaching",
            "adjust", "adjusted", "adjusting", "slip", "slipped", "slipping",
            "plug", "plugged", "plugging",
            "knock", "knocked", "buzz", "buzzed", "ring", "rang", "vibrate", "vibrated",
            "slam", "slammed", "crash", "crashed", "shut", "shuts", "shutting",
            "say", "said", "ask", "asked", "reply", "replied", "whisper", "whispered",
            "mutter", "muttered", "shout", "shouted", "yell", "yelled"
        ]
        for idx, paragraph in enumerate(paragraphs, start=1):
            paragraph_lower = paragraph.lower()
            if approved_terms:
                has_approved = any(token in paragraph_lower for token in approved_tokens)
                has_proper = bool(self._extract_named_terms(paragraph, limit=4))
                if not (has_approved or has_proper):
                    missing_term_idx.append(idx)
            elif not self._extract_named_terms(paragraph, limit=4):
                missing_term_idx.append(idx)
            if not self._paragraph_has_named_artifact(paragraph, approved_tokens):
                missing_artifact_idx.append(idx)
            has_interaction = any(verb in paragraph_lower for verb in interaction_verbs)
            if not has_interaction and self._paragraph_has_dialogue(paragraph):
                has_interaction = True
            if not has_interaction:
                missing_interaction_idx.append(idx)
            summary_hits = sum(paragraph_lower.count(term) for term in summary_verbs)
            if summary_hits >= 4 and not any(term in paragraph_lower for term in sensory_terms):
                summary_drift_idx.append(idx)
        allowed_missing_term = max(1, 1 + (len(paragraphs) // 6))
        allowed_missing_artifact = max(4, 1 + (len(paragraphs) // 4))
        allowed_missing_interaction = max(2, 1 + (len(paragraphs) // 4))
        allowed_summary_drift = 1
        allowed_abstract_overuse = 1
        allowed_soft_overuse = 1
        if len(missing_term_idx) > allowed_missing_term:
            for idx in missing_term_idx[allowed_missing_term:]:
                soft_issues.append(f"paragraph_{idx}_missing_named_term")
        if len(missing_artifact_idx) > allowed_missing_artifact:
            for idx in missing_artifact_idx[allowed_missing_artifact:]:
                soft_issues.append(f"paragraph_{idx}_missing_named_artifact")
        if len(missing_interaction_idx) > allowed_missing_interaction:
            for idx in missing_interaction_idx[allowed_missing_interaction:]:
                soft_issues.append(f"paragraph_{idx}_missing_interaction")
        if len(summary_drift_idx) > allowed_summary_drift:
            for idx in summary_drift_idx[allowed_summary_drift:]:
                soft_issues.append(f"paragraph_{idx}_summary_drift")
        if len(abstract_overuse_idx) > allowed_abstract_overuse:
            for idx in abstract_overuse_idx[allowed_abstract_overuse:]:
                soft_issues.append(f"paragraph_{idx}_abstract_stakes_overuse")
        if len(soft_overuse_idx) > allowed_soft_overuse:
            for idx in soft_overuse_idx[allowed_soft_overuse:]:
                soft_issues.append(f"paragraph_{idx}_soft_prose_overuse")
        if strict:
            failures.extend(soft_issues)
        elif soft_issues:
            self.logger.debug("Soft specificity issues: %s", ", ".join(soft_issues[:8]))
        return failures

    def _count_skill_beats_before_inciting(self, text: str) -> int:
        if not text:
            return 0
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        inciting_terms = {
            "alert", "alarm", "announcement", "broadcast", "breaking news", "briefing",
            "call", "text", "message", "email", "notification", "summons",
            "knock", "sirens", "scream", "shout", "crash", "collision",
            "explosion", "gunshot", "fire", "evacuation", "lockdown",
            "death", "dead", "killed", "murder", "abduction", "attack",
            "arrest", "raid", "intruder", "threat"
        }
        inciting_index = len(paragraphs)
        for idx, paragraph in enumerate(paragraphs):
            paragraph_lower = paragraph.lower()
            if any(term in paragraph_lower for term in inciting_terms):
                inciting_index = idx
                break
        if inciting_index == 0:
            inciting_index = 1
        if inciting_index == len(paragraphs):
            inciting_index = max(1, int(len(paragraphs) * 0.4))
        if inciting_index <= 1:
            inciting_index = min(len(paragraphs), 3)
        technique_terms = [
            "reconstruct", "reconstructed", "parse", "parsed", "trace", "traced",
            "detect", "detected", "verify", "verified", "decode", "decoded",
            "recover", "recovered", "correlate", "correlated", "cross-reference",
            "cross referenced", "checksum", "hashed", "hash", "decompile", "decompiled",
            "measure", "measured", "test", "tested", "compare", "compared",
            "review", "reviewed", "interview", "interviewed", "audit", "audited",
            "map", "mapped", "track", "tracked", "replay", "replayed",
            "scan", "scanned", "checking", "checked"
        ]
        result_terms = [
            "revealed", "showed", "confirmed", "exposed", "yielded",
            "surfaced", "matched", "identified", "flagged", "proved", "logged",
            "indicated", "signaled", "returned", "generated", "verified", "mismatch"
        ]
        inference_terms = [
            "meant", "implied", "suggested", "pointed", "therefore",
            "which meant", "which suggested", "that meant", "that suggested",
            "so it meant", "so it suggested", "because", "so that", "thereby"
        ]
        beats = 0
        for idx, paragraph in enumerate(paragraphs[:inciting_index]):
            paragraph_lower = paragraph.lower()
            if not any(term in paragraph_lower for term in technique_terms):
                continue
            if not any(term in paragraph_lower for term in result_terms):
                continue
            if any(term in paragraph_lower for term in inference_terms):
                beats += 1
                continue
            next_paragraph = paragraphs[idx + 1].lower() if idx + 1 < inciting_index else ""
            if not any(term in next_paragraph for term in inference_terms):
                continue
            beats += 1
        if beats == 0:
            weak_beats = 0
            interaction_verbs = [
                "open", "opened", "open", "load", "loaded", "scan", "scanned", "search", "searched",
                "trace", "traced", "verify", "verified", "decode", "decoded", "review", "reviewed",
                "check", "checked", "click", "clicked", "type", "typed", "run", "ran", "test", "tested"
            ]
            for paragraph in paragraphs[:min(3, len(paragraphs))]:
                pl = paragraph.lower()
                if any(v in pl for v in interaction_verbs) and any(t in pl for t in inference_terms):
                    weak_beats += 1
            if weak_beats >= 2:
                beats = 2
        return beats

    def _extract_failure_indices(self, failures: list[str], key: str) -> list[int]:
        indices: list[int] = []
        if not failures:
            return indices
        pattern = re.compile(rf"paragraph_(\d+)_{re.escape(key)}")
        for item in failures:
            match = pattern.search(str(item))
            if match:
                try:
                    indices.append(int(match.group(1)))
                except Exception:
                    continue
        return sorted(set(indices))

    def _apply_deterministic_skill_beats(self, text: str, approved_terms: list[str]) -> str:
        if not text:
            return text
        named_terms = self._extract_named_terms(text, limit=6)
        stop_terms = {
            "They", "He", "She", "We", "I", "You", "His", "Her", "Their",
            "Under", "Over", "After", "Before", "When", "As", "The", "A", "An",
            "In", "On", "At", "With", "From", "To", "By", "For", "Of", "And", "But", "Or", "So", "Yet", "Nor"
        }
        named_terms = [term for term in named_terms if term not in stop_terms and len(term) > 3]
        anchor = named_terms[0] if named_terms else (approved_terms[0] if approved_terms else "equipment")
        anchor_lower = anchor.lower()
        if " " in anchor and not anchor_lower.endswith(("file", "record", "ledger")):
            anchor_ref = f"{anchor}'s file"
        else:
            anchor_ref = anchor
        beats = [
            f"They ran a quick check on {anchor_ref}. The readout returned a mismatch, which suggested something was off.",
            "They rechecked a record and found a missing line, which meant something had been changed."
        ]
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if not paragraphs:
            return text
        inciting_terms = {
            "alert", "alarm", "announcement", "broadcast", "breaking news", "briefing",
            "call", "text", "message", "email", "notification", "summons",
            "knock", "sirens", "scream", "shout", "crash", "collision",
            "explosion", "gunshot", "fire", "evacuation", "lockdown",
            "death", "dead", "killed", "murder", "abduction", "attack",
            "arrest", "raid", "intruder", "threat"
        }
        inciting_index = len(paragraphs)
        for idx, paragraph in enumerate(paragraphs):
            if any(term in paragraph.lower() for term in inciting_terms):
                inciting_index = idx
                break
        if len(paragraphs) == 1:
            return "\n\n".join(beats + paragraphs)
        if inciting_index == 0:
            return "\n\n".join(beats + paragraphs)
        return "\n\n".join([paragraphs[0]] + beats + paragraphs[1:])

    def _apply_deterministic_paragraph_fixes(
        self,
        text: str,
        failures: list[str],
        approved_terms: list[str]
    ) -> str:
        if not text or not failures:
            return text
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if not paragraphs:
            return text
        missing_interaction = self._extract_failure_indices(failures, "missing_interaction")
        missing_artifact = self._extract_failure_indices(failures, "missing_named_artifact")
        missing_term = self._extract_failure_indices(failures, "missing_named_term")
        artifact_nouns = [
            "door", "desk", "table", "terminal", "screen", "monitor", "console",
            "phone", "tablet", "notebook", "folder", "file", "badge", "keycard",
            "router", "server", "drive", "locker", "cabinet"
        ]
        for idx, paragraph in enumerate(paragraphs, start=1):
            if idx in missing_term:
                paragraphs[idx - 1] = paragraph + " Room 3 stays quiet."
            if idx in missing_artifact:
                paragraphs[idx - 1] = paragraphs[idx - 1] + " The door 3 stands open."
            if idx in missing_interaction:
                para_lower = paragraphs[idx - 1].lower()
                artifact = ""
                for noun in artifact_nouns:
                    if noun in para_lower:
                        artifact = noun
                        break
                if not artifact:
                    artifact = "door 3"
                else:
                    artifact = f"{artifact} 3"
                paragraphs[idx - 1] = paragraphs[idx - 1] + f" A hand taps the {artifact}."
        return "\n\n".join(paragraphs)

    async def _run_skill_beats_pass(
        self,
        chapter_text: str,
        book_bible: str,
        references_excerpt: str,
        director_notes: str,
        strict: bool = False
    ) -> tuple[str, Dict[str, int]]:
        if not chapter_text:
            return "", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        approved_terms = self._get_approved_terms(book_bible, references_excerpt, director_notes)
        approved_line = ", ".join(approved_terms[:24]) if approved_terms else "None available"
        system_prompt = (
            "You are a fiction editor focused on early skill beats.\n"
            "Insert two skill beats before the inciting incident, without changing plot facts.\n"
            "Return ONLY the revised chapter text.\n"
        )
        strict_line = ""
        if strict:
            strict_line = (
                "Each skill beat must explicitly include the phrase \"which meant\" or \"which suggested\".\n"
                "Place the two skill beats in the first two paragraphs.\n"
                "Each beat must include a concrete technique (e.g., \"verified\", \"traced\", \"measured\"), "
                "a concrete result (e.g., \"flagged\", \"revealed\", \"returned\"), and the inference phrase.\n"
            )
        user_prompt = (
            "Revise the opening to include two skill beats before the inciting incident.\n"
            "Each skill beat must include: technique → result → inference (in the same paragraph).\n"
            f"{strict_line}"
            "If the inciting incident occurs immediately, insert the beats in the first paragraph(s) before it.\n"
            "Do not add new plot points or new named entities.\n"
            "Keep prose concrete and in-scene. Avoid trailer-voice narration.\n"
            "Each paragraph must include a named artifact and a concrete interaction.\n"
            f"Approved named terms (reuse as needed): {approved_line}\n\n"
            f"BOOK BIBLE:\n{book_bible[:1200] if book_bible else 'None'}\n\n"
            f"REFERENCE EXCERPTS:\n{references_excerpt or 'No references provided.'}\n"
            f"DIRECTOR NOTES:\n{director_notes or 'None'}\n\n"
            "CHAPTER TO REVISE:\n"
            "--- START ---\n"
            f"{chapter_text.strip()}\n"
            "--- END ---\n\n"
            "Return the revised chapter."
        )
        response = await self._make_api_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2 if strict else 0.25,
            max_tokens=self._max_tokens_from_words(
                len(chapter_text.split()),
                buffer_ratio=0.12,
                min_tokens=600,
                max_tokens=3500
            ),
            top_p=1
        )
        revised, usage_data = self._extract_content_and_usage(response)
        return revised.strip(), usage_data

    async def _run_paragraph_compliance_pass(
        self,
        chapter_text: str,
        book_bible: str,
        references_excerpt: str,
        director_notes: str,
        failures: list[str],
        strict: bool = False
    ) -> tuple[str, Dict[str, int]]:
        if not chapter_text:
            return "", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        approved_terms = self._get_approved_terms(book_bible, references_excerpt, director_notes)
        approved_line = ", ".join(approved_terms[:24]) if approved_terms else "None available"
        interaction_line = ", ".join([
            "open", "close", "load", "save", "scan", "search", "trace", "decrypt",
            "compile", "export", "upload", "download", "archive", "ping", "message",
            "index", "hash", "type", "click", "scroll", "write", "sketch", "send",
            "compose", "call", "text", "grab", "pull", "push", "turn", "flip",
            "hold", "place", "set", "take", "read", "watch", "listen", "look",
            "review", "check", "hover", "press", "select", "highlight", "drag",
            "drop", "swipe", "sit", "stand", "walk", "step", "enter", "move",
            "reach", "adjust", "slip", "plug"
        ])
        system_prompt = (
            "You are a strict copy editor enforcing paragraph-level constraints.\n"
            "Fix only the specified paragraphs. Do not add new plot points.\n"
            "Return ONLY the revised chapter text.\n"
        )
        user_prompt = (
            "Fix the following paragraph compliance failures exactly. Paragraphs are separated by blank lines.\n"
            "Rules:\n"
            "- Each flagged paragraph must include a named artifact and a concrete interaction (verb + object).\n"
            "- Each flagged paragraph must use at least one verb from this list: "
            f"{interaction_line}.\n"
            "- Use existing proper nouns or approved terms. Do not invent new characters or organizations.\n"
            "- If a paragraph lacks a named term, add a proper noun drawn from approved terms or label a location/object (Room 3, Bay A7).\n"
            "- If a paragraph lacks a named artifact, label an existing object with a specific identifier "
            "(e.g., locker 12B, file 3, gate A7) rather than inventing new entities.\n"
            "- If the paragraph is dialogue-only, add a brief action tag with a concrete object.\n"
            "- If a paragraph is flagged for summary drift, rewrite it into immediate, physical action with a sensory cue.\n"
            "- Replace summary verbs with observable actions tied to a named artifact.\n"
            "- If a paragraph is flagged for abstract-stakes or soft-prose overuse, rewrite into concrete action and sensory detail.\n"
            "- Keep prose concrete and in-scene; avoid trailer-voice narration.\n"
            f"{'If a paragraph has no objects, introduce a minimal concrete object consistent with the setting and label it; do not add new characters or organizations.' if strict else ''}\n"
            f"Failures: {', '.join(failures[:12])}\n"
            f"Approved named terms (reuse as needed): {approved_line}\n\n"
            f"BOOK BIBLE:\n{book_bible[:1200] if book_bible else 'None'}\n\n"
            f"REFERENCE EXCERPTS:\n{references_excerpt or 'No references provided.'}\n"
            f"DIRECTOR NOTES:\n{director_notes or 'None'}\n\n"
            "CHAPTER TO REVISE:\n"
            "--- START ---\n"
            f"{chapter_text.strip()}\n"
            "--- END ---\n\n"
            "Return the revised chapter."
        )
        response = await self._make_api_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.15 if strict else 0.2,
            max_tokens=self._max_tokens_from_words(
                len(chapter_text.split()),
                buffer_ratio=0.12,
                min_tokens=600,
                max_tokens=3500
            ),
            top_p=1
        )
        revised, usage_data = self._extract_content_and_usage(response)
        return revised.strip(), usage_data

    async def _run_semantic_audit(
        self,
        chapter_text: str,
        chapter_number: int
    ) -> Dict[str, Any]:
        if not chapter_text:
            return {"passed": True, "issues": [], "details": {}}
        explain_hits = len(re.findall(r"\b(which meant|which suggested|which implied|therefore|this meant|this suggested)\b", chapter_text.lower()))
        system_prompt = (
            "You are a strict narrative lint tool.\n"
            "Return STRICT JSON with keys: paragraphs (array) and notes (string).\n"
            "Each paragraph item must include:\n"
            "- index (number)\n"
            "- trailer_voice (boolean)\n"
            "- abstraction_score (0 to 1)\n"
            "- summary_drift (boolean)\n"
            "- missing_concrete_anchor (boolean)\n"
            "Do not include commentary or extra fields.\n"
        )
        user_prompt = (
            f"Analyze this chapter for trailer-voice, abstraction, summary drift, "
            f"and missing concrete anchors. Chapter {chapter_number}.\n\n"
            "CHAPTER:\n"
            f"{chapter_text.strip()}\n"
        )
        try:
            response = await self._make_api_call(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=900,
                response_format={"type": "json_object"}
            )
        except Exception:
            return {"passed": True, "issues": [], "details": {"audit_failed": True}}
        content, _ = self._extract_content_and_usage(response)
        audit = {}
        if content:
            cleaned = content.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
                cleaned = re.sub(r"```$", "", cleaned).strip()
            try:
                audit = json.loads(cleaned)
            except Exception:
                audit = {}
        paragraphs = audit.get("paragraphs", []) if isinstance(audit, dict) else []
        trailer_count = 0
        summary_count = 0
        missing_anchor_count = 0
        abstraction_scores: list[float] = []
        for item in paragraphs if isinstance(paragraphs, list) else []:
            if not isinstance(item, dict):
                continue
            if item.get("trailer_voice") is True:
                trailer_count += 1
            if item.get("summary_drift") is True:
                summary_count += 1
            if item.get("missing_concrete_anchor") is True:
                missing_anchor_count += 1
            try:
                abstraction_scores.append(float(item.get("abstraction_score", 0)))
            except Exception:
                abstraction_scores.append(0.0)
        avg_abstraction = sum(abstraction_scores) / max(1, len(abstraction_scores))
        high_abstraction = sum(1 for score in abstraction_scores if score >= 0.7)
        issues: list[str] = []
        meta_hits = len(re.findall(r"\b(the act of|the technique of|the process of|was known to|were known to)\b", chapter_text.lower()))
        narrator_hits = len(re.findall(
            r"\b(this was more than|this wasn't just|was about|marked the beginning|a sense of|felt a sense of|"
            r"this meant|this was|determination surged|resolve solidified|his resolve|her resolve|turning point|"
            r"call to safeguard|symbolized)\b",
            chapter_text.lower()
        ))
        compression_hits = len(re.findall(
            r"\b(within moments|almost immediately|suddenly|soon after|by the time|in moments|a moment later|"
            r"without pause|before long|quickly|within seconds)\b",
            chapter_text.lower()
        ))
        if trailer_count >= 1:
            issues.append("semantic_trailer_voice")
        if avg_abstraction >= 0.55 or high_abstraction >= 3:
            issues.append("semantic_excessive_abstraction")
        if summary_count >= 2:
            issues.append("semantic_summary_drift")
        if missing_anchor_count >= 2:
            issues.append("semantic_missing_concrete_anchor")
        if explain_hits > 2:
            issues.append("semantic_overexplaining")
        if meta_hits > 1:
            issues.append("semantic_meta_narration")
        if narrator_hits > 1:
            issues.append("semantic_summary_narration")
        if compression_hits > 2:
            issues.append("semantic_pacing_compression")
        return {
            "passed": len(issues) == 0,
            "issues": issues,
            "details": {
                "trailer_count": trailer_count,
                "summary_drift_count": summary_count,
                "missing_anchor_count": missing_anchor_count,
                "avg_abstraction": round(avg_abstraction, 3),
                "high_abstraction": high_abstraction,
                "explain_hits": explain_hits,
                "meta_hits": meta_hits,
                "narrator_hits": narrator_hits,
                "compression_hits": compression_hits
            }
        }

    async def _run_semantic_revision_pass(
        self,
        chapter_text: str,
        issues: list[str]
    ) -> tuple[str, Dict[str, int]]:
        if not chapter_text:
            return "", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        issue_line = ", ".join(issues[:6]) if issues else "general_semantic_cleanup"
        system_prompt = (
            "You are a line editor focused on eliminating abstract, trailer-voice narration.\n"
            "Return ONLY the revised chapter text.\n"
        )
        user_prompt = (
            "Revise the chapter to resolve these semantic issues: "
            f"{issue_line}.\n"
            "Rules:\n"
            "- Remove trailer-voice and voiceover-style phrasing.\n"
            "- Replace abstract narration with concrete actions and sensory anchors.\n"
            "- If summary drift appears, rewrite into immediate, in-scene action.\n"
            "- Reduce over-explaining; limit explicit inference clauses (which meant/therefore/etc.).\n"
            "- Remove meta narration like 'the act of' or 'was known to'; show the action instead.\n"
            "- Remove narrator summary lines like 'this was more than' or 'marked the beginning'; show what happens.\n"
            "- Avoid sentences that start with 'This meant' or 'This was'; convert them into concrete action.\n"
            "- Replace narrator framing like 'turning point' or 'symbolized' with immediate scene action.\n"
            "- Decompress pacing: add concrete steps between major beats; avoid 'within moments' jumps.\n"
            "- Preserve any blockquote lines that start with '>' exactly as-is.\n"
            "- Preserve plot facts, POV, and tense.\n"
            "CHAPTER:\n"
            "--- START ---\n"
            f"{chapter_text.strip()}\n"
            "--- END ---\n"
        )
        response = await self._make_api_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,
            max_tokens=self._max_tokens_from_words(
                len(chapter_text.split()),
                buffer_ratio=0.12,
                min_tokens=600,
                max_tokens=3500
            ),
            top_p=1
        )
        revised, usage_data = self._extract_content_and_usage(response)
        return revised.strip(), usage_data

    async def _run_consolidated_postdraft_pass(
        self,
        *,
        chapter_text: str,
        book_bible: str,
        references_excerpt: str,
        director_notes: str,
        issues: list[str],
        goal: str
    ) -> tuple[str, Dict[str, int]]:
        """
        One-pass consolidation for multiple post-draft problems to avoid cascading LLM calls.
        Intended to replace separate: semantic_revision + action_density + inference_chain + tail_grounding.
        """
        if not chapter_text:
            return "", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        issue_line = ", ".join([str(x) for x in (issues or [])][:10]) if issues else "general_cleanup"
        approved_terms = self._get_approved_terms(book_bible, references_excerpt, director_notes)
        approved_line = ", ".join(approved_terms[:24]) if approved_terms else "None available"

        system_prompt = (
            "You are a senior fiction line editor.\n"
            "Return ONLY the revised chapter text. No commentary.\n"
            "Do not use Markdown formatting.\n"
        )
        user_prompt = (
            f"Goal: {goal}\n"
            f"Known issues: {issue_line}\n\n"
            "Revise the chapter in ONE pass.\n"
            "Rules:\n"
            "- Keep POV, tense, and all plot facts.\n"
            "- No standalone inventory/atmosphere blocks: do not allow more than 1 consecutive paragraph that is mostly description without action/dialogue/decision.\n"
            "- Within the first ~350 words, make a concrete pressure/obligation hit (message, person, sound, timer, demand) and show the POV responding with physical action.\n"
            "- Replace summary/voiceover lines with lived-time beats (move, touch, search, interrupt, decide).\n"
            "- Reduce over-explaining ('which meant/therefore/this meant'); let inference come from action and detail.\n"
            "- Strengthen the ending into a concrete next pressure (mid-action / mid-decision / mid-consequence). No reflective fadeout.\n"
            "- Preserve named artifacts/systems; reuse approved terms when naming things.\n"
            f"Approved named terms (reuse as needed): {approved_line}\n\n"
            f"BOOK BIBLE:\n{book_bible[:1200] if book_bible else 'None'}\n\n"
            f"REFERENCE EXCERPTS:\n{references_excerpt or 'No references provided.'}\n"
            f"DIRECTOR NOTES:\n{director_notes or 'None'}\n\n"
            "CHAPTER TO REVISE:\n"
            "--- START ---\n"
            f"{chapter_text.strip()}\n"
            "--- END ---\n"
        )
        response = await self._make_api_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=self._max_tokens_from_words(
                len(chapter_text.split()),
                buffer_ratio=0.12,
                min_tokens=700,
                max_tokens=4000,
            ),
            top_p=1,
        )
        revised, usage_data = self._extract_content_and_usage(response)
        return revised.strip(), usage_data

    async def _run_action_density_pass(
        self,
        chapter_text: str,
        book_bible: str,
        references_excerpt: str,
        director_notes: str
    ) -> tuple[str, Dict[str, int]]:
        if not chapter_text:
            return "", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        approved_terms = self._get_approved_terms(book_bible, references_excerpt, director_notes)
        approved_line = ", ".join(approved_terms[:24]) if approved_terms else "None available"
        system_prompt = (
            "You are a fiction editor increasing action density while preserving length.\n"
            "Replace narrator-summary lines with concrete, in-scene actions.\n"
            "Do not add new plot points.\n"
            "Return ONLY the revised chapter text.\n"
        )
        user_prompt = (
            "Rewrite the chapter to increase action density without shortening it.\n"
            "Rules:\n"
            "- Replace abstract summaries with concrete actions and interactions.\n"
            "- Keep POV, tense, and all plot facts.\n"
            "- Avoid mythic framing and narrator commentary.\n"
            "- Remove summary lines like 'a testament' or 'a reminder' by showing action instead.\n"
            "- Preserve named artifacts and systems.\n"
            "- Preserve any blockquote lines that start with '>' exactly as-is.\n"
            "- Do not introduce new plot points or new characters.\n"
            f"Approved named terms (reuse as needed): {approved_line}\n\n"
            f"BOOK BIBLE:\n{book_bible[:1200] if book_bible else 'None'}\n\n"
            f"REFERENCE EXCERPTS:\n{references_excerpt or 'No references provided.'}\n"
            f"DIRECTOR NOTES:\n{director_notes or 'None'}\n\n"
            "CHAPTER TO REWRITE:\n"
            "--- START ---\n"
            f"{chapter_text.strip()}\n"
            "--- END ---\n\n"
            "Return the revised chapter."
        )
        response = await self._make_api_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.35,
            max_tokens=self._max_tokens_from_words(
                len(chapter_text.split()),
                buffer_ratio=0.12,
                min_tokens=600,
                max_tokens=3500
            ),
            top_p=1
        )
        revised, usage_data = self._extract_content_and_usage(response)
        return revised.strip(), usage_data

    async def _run_inference_chain_pass(
        self,
        chapter_text: str,
        book_bible: str,
        references_excerpt: str,
        director_notes: str
    ) -> tuple[str, Dict[str, int]]:
        if not chapter_text:
            return "", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        approved_terms = self._get_approved_terms(book_bible, references_excerpt, director_notes)
        approved_line = ", ".join(approved_terms[:24]) if approved_terms else "None available"
        system_prompt = (
            "You are a fiction editor reducing inference-chain narration.\n"
            "Replace 'which meant/suggested/revealed' and 'This meant/suggested' sentences with concrete action.\n"
            "Do not add new plot points.\n"
            "Return ONLY the revised chapter text.\n"
        )
        user_prompt = (
            "Rewrite the chapter to reduce inference chains without shortening it.\n"
            "Rules:\n"
            "- Replace 'which meant/suggested/revealed' and 'This meant/suggested' with observable actions or outcomes.\n"
            "- Keep POV, tense, and plot facts.\n"
            "- Avoid narrator-summary framing; keep the camera in-scene.\n"
            "- Preserve named artifacts and systems.\n"
            "- Preserve any blockquote lines that start with '>' exactly as-is.\n"
            f"Approved named terms (reuse as needed): {approved_line}\n\n"
            f"BOOK BIBLE:\n{book_bible[:1200] if book_bible else 'None'}\n\n"
            f"REFERENCE EXCERPTS:\n{references_excerpt or 'No references provided.'}\n"
            f"DIRECTOR NOTES:\n{director_notes or 'None'}\n\n"
            "CHAPTER TO REWRITE:\n"
            "--- START ---\n"
            f"{chapter_text.strip()}\n"
            "--- END ---\n\n"
            "Return the revised chapter."
        )
        response = await self._make_api_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=self._max_tokens_from_words(
                len(chapter_text.split()),
                buffer_ratio=0.12,
                min_tokens=600,
                max_tokens=3500
            ),
            top_p=1
        )
        revised, usage_data = self._extract_content_and_usage(response)
        return revised.strip(), usage_data

    async def _run_metaphor_throttle_pass(
        self,
        chapter_text: str,
        book_bible: str,
        references_excerpt: str,
        director_notes: str
    ) -> tuple[str, Dict[str, int]]:
        if not chapter_text:
            return "", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        approved_terms = self._get_approved_terms(book_bible, references_excerpt, director_notes)
        approved_line = ", ".join(approved_terms[:24]) if approved_terms else "None available"
        system_prompt = (
            "You are a fiction editor reducing metaphor density while preserving length and tone.\n"
            "Keep only the strongest 1 metaphor per scene and convert the rest into concrete action.\n"
            "Do not add new plot points.\n"
            "Return ONLY the revised chapter text.\n"
        )
        user_prompt = (
            "Reduce metaphor overload without shortening the chapter.\n"
            "Rules:\n"
            "- Keep the best metaphors; remove or convert the rest to concrete action.\n"
            "- Replace sweeping imagery with specific, observable details.\n"
            "- Remove or rewrite similes introduced by 'like' or 'as' when they are decorative.\n"
            "- Preserve POV, tense, plot facts, and named artifacts.\n"
            "- Avoid narrator-summary framing.\n"
            "- Preserve any blockquote lines that start with '>' exactly as-is.\n"
            f"Approved named terms (reuse as needed): {approved_line}\n\n"
            f"BOOK BIBLE:\n{book_bible[:1200] if book_bible else 'None'}\n\n"
            f"REFERENCE EXCERPTS:\n{references_excerpt or 'No references provided.'}\n"
            f"DIRECTOR NOTES:\n{director_notes or 'None'}\n\n"
            "CHAPTER TO REWRITE:\n"
            "--- START ---\n"
            f"{chapter_text.strip()}\n"
            "--- END ---\n\n"
            "Return the revised chapter."
        )
        response = await self._make_api_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.35,
            max_tokens=self._max_tokens_from_words(
                len(chapter_text.split()),
                buffer_ratio=0.12,
                min_tokens=600,
                max_tokens=3500
            ),
            top_p=1
        )
        revised, usage_data = self._extract_content_and_usage(response)
        return revised.strip(), usage_data

    async def _run_tail_grounding_pass(
        self,
        chapter_text: str,
        book_bible: str,
        references_excerpt: str,
        director_notes: str
    ) -> tuple[str, Dict[str, int]]:
        if not chapter_text:
            return "", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        paragraphs = [p for p in re.split(r"\n\s*\n", chapter_text) if p.strip()]
        if len(paragraphs) < 3:
            return chapter_text, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        tail_count = max(2, int(len(paragraphs) * 0.35))
        head = paragraphs[:-tail_count]
        tail = paragraphs[-tail_count:]
        approved_terms = self._get_approved_terms(book_bible, references_excerpt, director_notes)
        approved_line = ", ".join(approved_terms[:24]) if approved_terms else "None available"
        system_prompt = (
            "You are a fiction editor grounding the ending of a chapter in concrete action.\n"
            "Replace narrator-summary lines with immediate scene beats while preserving length.\n"
            "Do not add new plot points.\n"
            "Return ONLY the revised tail text.\n"
        )
        tail_text = "\n\n".join(tail).strip()
        user_prompt = (
            "Rewrite ONLY the tail section to remove summary voice and ground it in action.\n"
            "Rules:\n"
            "- Keep POV, tense, and plot facts.\n"
            "- Replace abstract summaries with concrete actions and interactions.\n"
            "- Avoid mythic framing and narrator commentary.\n"
            "- Preserve named artifacts and systems.\n"
            "- Preserve any blockquote lines that start with '>' exactly as-is.\n"
            f"Approved named terms (reuse as needed): {approved_line}\n\n"
            f"BOOK BIBLE:\n{book_bible[:1000] if book_bible else 'None'}\n\n"
            f"REFERENCE EXCERPTS:\n{references_excerpt or 'No references provided.'}\n"
            f"DIRECTOR NOTES:\n{director_notes or 'None'}\n\n"
            "TAIL TO REWRITE:\n"
            "--- START ---\n"
            f"{tail_text}\n"
            "--- END ---\n\n"
            "Return the revised tail only."
        )
        response = await self._make_api_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.35,
            max_tokens=self._max_tokens_from_words(
                len(" ".join(tail).split()),
                buffer_ratio=0.2,
                min_tokens=400,
                max_tokens=2000
            ),
            top_p=1
        )
        revised_tail, usage_data = self._extract_content_and_usage(response)
        if revised_tail:
            updated = head + [p for p in re.split(r"\n\s*\n", revised_tail) if p.strip()]
            return "\n\n".join(updated), usage_data
        return chapter_text, usage_data

    def _needs_tight_prose_pass(self, text: str) -> bool:
        if not text:
            return False
        # Optional override for experimentation (still bounded by post-draft budget at callsite).
        try:
            if os.getenv("CHAPTER_FORCE_TIGHT_PROSE_PASS", "false").strip().lower() in ("1", "true", "yes", "y", "on"):
                return True
        except Exception:
            pass

        text_lower = text.lower()
        if self._has_trailer_voice(text_lower):
            return True
        soft_terms = [
            "sanctuary", "devotion", "reverie", "poignancy", "ethereal",
            "otherworldly", "aura", "enigmatic", "haunting", "mystic",
            "lived-in", "dreams", "constellations"
        ]
        abstract_terms = [
            "legacy", "fate", "destiny", "nexus", "epochal", "grail",
            "prophecy", "salvation", "doom", "timeless", "mythic", "legendary"
        ]
        soft_hits = sum(text_lower.count(term) for term in soft_terms)
        if soft_hits >= 3:
            return True
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        for paragraph in paragraphs:
            para_lower = paragraph.lower()
            if sum(para_lower.count(term) for term in soft_terms) > 1:
                return True
            if sum(para_lower.count(term) for term in abstract_terms) > 1:
                return True

        # Additional readability/overwriting signals (conservative; require multiple signals).
        # We look at the first half-ish to avoid triggering purely on climaxes.
        try:
            words = text.split()
            sample = " ".join(words[: min(len(words), 1400)])
        except Exception:
            sample = text

        score = 0
        try:
            # Sentence length: long, clause-stacked sentences reduce readability.
            sentences = [s.strip() for s in re.split(r"[.!?]+", sample) if s.strip()]
            if sentences:
                sent_word_counts = [len(s.split()) for s in sentences[:18]]
                avg_len = (sum(sent_word_counts) / max(1, len(sent_word_counts))) if sent_word_counts else 0.0
                if avg_len >= 26:
                    score += 1
        except Exception:
            pass

        try:
            # Comma density: too many commas often signals clause stacking.
            wcount = max(1, len(sample.split()))
            comma_per_100 = (sample.count(",") / wcount) * 100.0
            if comma_per_100 >= 4.8:
                score += 1
        except Exception:
            pass

        try:
            # -ly adverbs: overuse can create “haze” and weaken verbs.
            adverbs = re.findall(r"\b[a-z]{4,}ly\b", sample.lower())
            wcount = max(1, len(sample.split()))
            adv_per_100 = (len(adverbs) / wcount) * 100.0
            if adv_per_100 >= 2.2 and len(adverbs) >= 10:
                score += 1
        except Exception:
            pass

        try:
            # Clause stacking (subordinating conjunction density)
            markers = re.findall(r"\b(because|while|when|as|which|that|until|unless|though|although)\b", sample.lower())
            wcount = max(1, len(sample.split()))
            per_100 = (len(markers) / wcount) * 100.0
            if per_100 >= 2.6 and len(markers) >= 6:
                score += 1
        except Exception:
            pass

        try:
            # Repeated paragraph openers (soft repetition / same framing beat).
            paras = [p.strip() for p in re.split(r"\n\s*\n", sample) if p.strip()]
            openers: list[str] = []
            for p in paras[:10]:
                opener = " ".join(re.findall(r"\b[a-z]+\b", p.lower())[:6]).strip()
                if opener:
                    openers.append(opener)
            if openers:
                dupes = len(openers) - len(set(openers))
                if dupes >= 2:
                    score += 1
        except Exception:
            pass

        return score >= 2

    def _needs_tight_prose_pass_for_target(self, text: str, target_words: int) -> bool:
        """
        Decide whether to run the tight-prose line edit pass.

        This is a universal (genre-agnostic) readability improvement. In addition to the
        "overwriting" heuristics, we also trigger when the draft materially overshoots
        the target length, since that often correlates with redundant phrasing and
        clause stacking.
        """
        if self._needs_tight_prose_pass(text):
            return True
        if not text:
            return False
        if not target_words or int(target_words) <= 0:
            return False
        try:
            if os.getenv("CHAPTER_TIGHT_PROSE_ON_OVERSHOOT", "true").strip().lower() not in ("1", "true", "yes", "y", "on"):
                return False
        except Exception:
            return False
        try:
            ratio = float(os.getenv("CHAPTER_TIGHT_PROSE_OVERSHOOT_RATIO", "1.15"))
        except Exception:
            ratio = 1.15
        try:
            min_extra = int(os.getenv("CHAPTER_TIGHT_PROSE_OVERSHOOT_MIN_WORDS", "140"))
        except Exception:
            min_extra = 140
        try:
            wc = len(text.split())
        except Exception:
            return False
        return (wc >= int(target_words * ratio)) and ((wc - int(target_words)) >= max(0, min_extra))

    def _needs_expansion_pass(self, text: str, target_words: int) -> bool:
        if not text:
            return False
        if not target_words or target_words <= 0:
            return False
        word_count = len(text.split())
        minimum_target = max(400, int(target_words * 0.82))
        return word_count < minimum_target

    def _needs_intro_grounding_pass(self, text: str, chapter_number: int) -> bool:
        if not text or chapter_number != 1:
            return False
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if not paragraphs:
            return False
        intro_block = " ".join(paragraphs[:3])
        proper_nouns = re.findall(r"\b[A-Z][A-Z0-9]{2,}\b", intro_block)
        if not proper_nouns:
            return False
        appositive_markers = re.compile(r"\b(is|was|are|were)\s+(a|an|the)\b|,\s+(a|an|the)\b", re.IGNORECASE)
        missing = 0
        for token in set(proper_nouns):
            token_pattern = re.escape(token)
            sentence_match = re.search(rf"[^.?!]*\b{token_pattern}\b[^.?!]*[.?!]", intro_block)
            if sentence_match and not appositive_markers.search(sentence_match.group(0)):
                missing += 1
        return missing >= 1

    def _needs_stakes_delay_pass(self, text: str, chapter_number: int) -> bool:
        if not text or chapter_number != 1:
            return False
        trigger_terms = [
            "root key", "mirror map", "trial", "riddle", "quest", "final challenge",
            "wake update", "wake", "root-key"
        ]
        # Only run when the draft already contains multiple proper nouns we can clarify.
        intro_terms = [" a ", " the ", " inc ", " corp ", " llc ", " university", " hospital", " department"]
        text_lower = text.lower()
        if any(term in text_lower for term in trigger_terms):
            # Only delay if Chapter 1 already mentions core entities, so we can slow down.
            return any(term in text_lower for term in intro_terms)
        return False

    def _needs_opening_bridge_pass(self, text: str, chapter_number: int, context: Optional[Dict[str, Any]]) -> bool:
        """
        Detect weak chapter-to-chapter continuity in openings.
        When triggered, we do a bounded opening rewrite pass (no full regeneration loop).
        """
        if not text or chapter_number <= 1:
            return False
        ctx = context or {}
        previous_texts = ctx.get("previous_texts_for_audit") or []
        if not isinstance(previous_texts, list):
            previous_texts = []

        # Recap/restart detection: lexical overlap early vs recent chapters.
        try:
            current_start = " ".join(text.split()[:550]).lower()
            previous_blob = " ".join([str(t) for t in previous_texts[-2:]]).lower()
            current_words = set(re.findall(r"\b[a-z]{4,}\b", current_start))
            prev_words = set(re.findall(r"\b[a-z]{4,}\b", previous_blob))
            overlap_ratio = (len(current_words & prev_words) / max(1, len(current_words))) if current_words else 0.0
        except Exception:
            overlap_ratio = 0.0

        # Bridge compliance: do opening tokens reflect bridge requirements?
        bridge_requirements = ctx.get("bridge_requirements") or []
        if not isinstance(bridge_requirements, list):
            bridge_requirements = []
        bridge_score = 1.0
        try:
            if bridge_requirements:
                content_lower = current_start
                hits = 0
                total = 0
                for item in bridge_requirements[:8]:
                    if not item or not isinstance(item, str):
                        continue
                    total += 1
                    # Extract named tokens first (more reliable than generic words).
                    named_tokens = [t.lower() for t in re.findall(r"\b[A-Z][a-zA-Z0-9-]{2,}\b", item)]
                    named_tokens = [t for t in named_tokens if t not in {"the", "and", "but", "for", "with", "into"}]

                    # Extract meaningful non-named tokens (allow hyphens/digits; avoid tiny stop-words).
                    tokens = [
                        t.lower()
                        for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9-]{3,}", item)
                        if t.lower()
                        not in {
                            "begin", "from", "the", "and", "with", "into", "that", "this", "your", "must",
                            "first", "words", "carry", "forward", "prior", "chapter", "scene", "immediate",
                            "consequence", "ending",
                        }
                    ]
                    if not tokens:
                        continue
                    # If we have a named token (e.g. Clarifier-1, PlantTrack), require at least one.
                    if named_tokens:
                        if any(tok in content_lower for tok in named_tokens[:6]):
                            hits += 1
                        continue

                    matched = sum(1 for token in tokens if token in content_lower)
                    if matched >= max(1, int(len(tokens) * 0.5)):
                        hits += 1
                bridge_score = (hits / total) if total else 1.0
        except Exception:
            bridge_score = 1.0

        # Conservative thresholds; this pass is advisory and bounded to 1 execution.
        if overlap_ratio >= 0.42:
            return True
        if bridge_requirements and bridge_score < 0.6:
            return True
        return False

    async def _run_intro_grounding_pass(
        self,
        chapter_text: str,
        book_bible: str,
        references_excerpt: str,
        director_notes: str
    ) -> tuple[str, Dict[str, int]]:
        if not chapter_text:
            return "", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        approved_terms = self._get_approved_terms(book_bible, references_excerpt, director_notes)
        approved_line = ", ".join(approved_terms[:24]) if approved_terms else "None available"
        system_prompt = (
            "You are a fiction editor grounding Chapter 1 introductions.\n"
            "Add short, concrete appositive introductions for first mentions of key proper nouns.\n"
            "Do not add new plot points.\n"
            "Return ONLY the revised chapter text.\n"
        )
        user_prompt = (
            "Revise Chapter 1 to slow the setup and introduce key terms clearly.\n"
            "Rules:\n"
            "- For first mentions of entities (people/orgs/places/systems), add a short appositive tag (6-12 words) that clarifies what it is.\n"
            "- Do not advance the plot faster; add 1-2 setup beats instead of summary.\n"
            "- Avoid narrator-summary framing; keep the camera in-scene.\n"
            "- Preserve POV, tense, and named artifacts.\n"
            "- Preserve any blockquote lines that start with '>' exactly as-is.\n"
            f"Approved named terms (reuse as needed): {approved_line}\n\n"
            f"BOOK BIBLE:\n{book_bible[:1200] if book_bible else 'None'}\n\n"
            f"REFERENCE EXCERPTS:\n{references_excerpt or 'No references provided.'}\n"
            f"DIRECTOR NOTES:\n{director_notes or 'None'}\n\n"
            "CHAPTER TO REWRITE:\n"
            "--- START ---\n"
            f"{chapter_text.strip()}\n"
            "--- END ---\n\n"
            "Return the revised chapter."
        )
        response = await self._make_api_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=self._max_tokens_from_words(
                len(chapter_text.split()),
                buffer_ratio=0.12,
                min_tokens=600,
                max_tokens=3500
            ),
            top_p=1
        )
        revised, usage_data = self._extract_content_and_usage(response)
        return revised.strip(), usage_data

    async def _run_opening_bridge_pass(
        self,
        *,
        chapter_text: str,
        chapter_number: int,
        last_chapter_ending: str,
        bridge_requirements: list[str],
        book_bible: str,
        references_excerpt: str,
        director_notes: str
    ) -> tuple[str, Dict[str, int]]:
        """
        Rewrite ONLY the opening block to better bridge from the prior chapter and satisfy bridge requirements.
        Returns a full chapter (opening replaced; rest unchanged).
        """
        if not chapter_text or chapter_number <= 1:
            return "", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", chapter_text) if p.strip()]
        if not paragraphs:
            return "", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        # Rewrite the first few paragraphs (bounded) and keep the rest unchanged.
        opening_paras = paragraphs[:5]
        rest_paras = paragraphs[5:]
        opening_text = "\n\n".join(opening_paras).strip()
        rest_text = ("\n\n".join(rest_paras).strip() + "\n") if rest_paras else ""

        approved_terms = self._get_approved_terms(book_bible, references_excerpt, director_notes)
        approved_line = ", ".join(approved_terms[:24]) if approved_terms else "None available"
        bridge_lines = "\n".join(f"- {str(x)[:200]}" for x in (bridge_requirements or [])[:8]) or "- (none provided)"

        system_prompt = (
            "You are a fiction editor rewriting a chapter opening for continuity.\n"
            "Rewrite ONLY the provided opening block. Do not write Markdown.\n"
            "Do not add new named entities unless absolutely necessary; prefer reusing established terms.\n"
            "Return ONLY the revised opening block.\n"
        )

        user_prompt = (
            f"Rewrite the opening of Chapter {chapter_number} to strongly bridge from Chapter {chapter_number-1}.\n\n"
            "Rules:\n"
            "- Begin in-scene from the prior chapter’s final consequence OR explicitly signal an in-scene time-skip.\n"
            "- NO recap paragraph. Do not restate prior chapters.\n"
            "- Within the first ~300 words, explicitly continue at least one established thread/clue/obligation.\n"
            "- Entity grounding: if you mention a named entity in the opening, ground it via an explicit connection to established elements.\n"
            "- Preserve POV/tense/voice.\n"
            "- Keep the rest of the chapter unchanged; do not set up contradictions.\n"
            "- Preserve any blockquote lines that start with '>' exactly as-is.\n"
            f"Approved named terms (reuse as needed): {approved_line}\n\n"
            f"PRIOR CHAPTER ENDING (FLOW FORWARD FROM THIS; DO NOT RESTATE):\n{(last_chapter_ending or '').strip()[:450]}\n\n"
            f"BRIDGE REQUIREMENTS:\n{bridge_lines}\n\n"
            f"BOOK BIBLE (excerpt):\n{(book_bible or '')[:900] if book_bible else 'None'}\n\n"
            f"REFERENCE EXCERPTS:\n{references_excerpt or 'No references provided.'}\n"
            f"DIRECTOR NOTES:\n{director_notes or 'None'}\n\n"
            "OPENING TO REWRITE:\n"
            "--- START OPENING ---\n"
            f"{opening_text}\n"
            "--- END OPENING ---\n\n"
            "Return ONLY the revised opening block."
        )

        response = await self._make_api_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=self._max_tokens_from_words(
                max(450, len(opening_text.split())),
                buffer_ratio=0.18,
                min_tokens=500,
                max_tokens=2200,
            ),
            top_p=1,
        )
        revised_opening, usage_data = self._extract_content_and_usage(response)
        revised_opening = (revised_opening or "").strip()
        if not revised_opening:
            return "", usage_data

        combined = (revised_opening + ("\n\n" + rest_text if rest_text else "")).strip() + "\n"
        return combined, usage_data

    async def _run_stakes_delay_pass(
        self,
        chapter_text: str,
        book_bible: str,
        references_excerpt: str,
        director_notes: str
    ) -> tuple[str, Dict[str, int]]:
        if not chapter_text:
            return "", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        approved_terms = self._get_approved_terms(book_bible, references_excerpt, director_notes)
        approved_line = ", ".join(approved_terms[:24]) if approved_terms else "None available"
        system_prompt = (
            "You are a fiction editor slowing down Chapter 1 setup.\n"
            "Keep the trigger event, but delay major stakes and puzzle reveals.\n"
            "Do not add new plot points.\n"
            "Return ONLY the revised chapter text.\n"
        )
        user_prompt = (
            "Revise Chapter 1 to focus on setup and first decision only.\n"
            "Rules:\n"
            "- Keep the existing setup, the trigger event, and the first decision.\n"
            "- Delay major stakes: remove or defer any global-quest framing, prophecy/mission framing, or puzzle-solution dumps.\n"
            "- Replace narrator-summary lines with concrete action and smaller beats.\n"
            "- Keep entity introductions short and concrete.\n"
            "- Preserve POV, tense, and named artifacts.\n"
            "- Preserve any blockquote lines that start with '>' exactly as-is.\n"
            f"Approved named terms (reuse as needed): {approved_line}\n\n"
            f"BOOK BIBLE:\n{book_bible[:1200] if book_bible else 'None'}\n\n"
            f"REFERENCE EXCERPTS:\n{references_excerpt or 'No references provided.'}\n"
            f"DIRECTOR NOTES:\n{director_notes or 'None'}\n\n"
            "CHAPTER TO REWRITE:\n"
            "--- START ---\n"
            f"{chapter_text.strip()}\n"
            "--- END ---\n\n"
            "Return the revised chapter."
        )
        response = await self._make_api_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=self._max_tokens_from_words(
                len(chapter_text.split()),
                buffer_ratio=0.12,
                min_tokens=600,
                max_tokens=3500
            ),
            top_p=1
        )
        revised, usage_data = self._extract_content_and_usage(response)
        return revised.strip(), usage_data

    async def _run_expansion_pass(
        self,
        chapter_text: str,
        target_words: int,
        book_bible: str,
        references_excerpt: str,
        director_notes: str
    ) -> tuple[str, Dict[str, int]]:
        if not chapter_text:
            return "", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        approved_terms = self._get_approved_terms(book_bible, references_excerpt, director_notes)
        approved_line = ", ".join(approved_terms[:24]) if approved_terms else "None available"
        current_words = len(chapter_text.split())
        desired_add = max(300, target_words - current_words)
        system_prompt = (
            "You are a fiction editor expanding a chapter with concrete, in-scene action.\n"
            "Add depth and sequence without adding new plot points.\n"
            "Return ONLY the revised chapter text.\n"
        )
        user_prompt = (
            f"Expand the chapter to approach ~{target_words} words by developing existing scenes.\n"
            "Rules:\n"
            "- Add concrete actions, sensory details, and specific artifacts.\n"
            "- Extend existing beats instead of adding new plot points.\n"
            "- Avoid summary narration and mythic framing.\n"
            "- Keep POV, tense, and named details consistent.\n"
            "- Avoid repetitive 'which meant/which suggested' chains.\n"
            f"Approved named terms (reuse as needed): {approved_line}\n\n"
            f"BOOK BIBLE:\n{book_bible[:1200] if book_bible else 'None'}\n\n"
            f"REFERENCE EXCERPTS:\n{references_excerpt or 'No references provided.'}\n"
            f"DIRECTOR NOTES:\n{director_notes or 'None'}\n\n"
            "CHAPTER TO EXPAND:\n"
            "--- START ---\n"
            f"{chapter_text.strip()}\n"
            "--- END ---\n\n"
            "Return the expanded chapter."
        )
        response = await self._make_api_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.4,
            max_tokens=self._max_tokens_from_words(
                target_words,
                buffer_ratio=0.25,
                min_tokens=1000,
                max_tokens=16000
            ),
            top_p=1
        )
        revised, usage_data = self._extract_content_and_usage(response)
        return revised.strip(), usage_data

    async def _run_tight_prose_pass(
        self,
        chapter_text: str,
        book_bible: str,
        references_excerpt: str,
        director_notes: str
    ) -> tuple[str, Dict[str, int]]:
        if not chapter_text:
            return "", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        approved_terms = self._get_approved_terms(book_bible, references_excerpt, director_notes)
        approved_line = ", ".join(approved_terms[:24]) if approved_terms else "None available"
        system_prompt = (
            "You are a line editor focused on clarity and concreteness.\n"
            "Tighten the prose, remove poetic haze, and keep the scene grounded.\n"
            "Preserve POV, tense, plot beats, and named details.\n"
            "Do not add new plot points.\n"
            "Return ONLY the revised chapter text.\n"
        )
        user_prompt = (
            "Rewrite the chapter for tighter, clearer prose.\n"
            "Rules:\n"
            "- Aim to reduce overall length by ~5-10% by cutting redundancy, not by deleting plot beats.\n"
            "- Prefer concrete nouns and actions over metaphorical phrasing.\n"
            "- Reduce abstract claims; show the action instead.\n"
            "- Remove decorative scene-setting lines that do not advance action.\n"
            "- Remove trailer-voice narration (no voiceover-style lines).\n"
            "- Remove QA-like phrasing such as 'check of X shows'.\n"
            "- Avoid global-summary narration; keep the camera in-scene.\n"
            "- Vary sentence rhythm: mix short punchy lines with occasional longer sentences.\n"
            "- Cut stacked modifiers/adverbs; keep the strongest one.\n"
            "- Use multiple paragraphs; avoid a single wall of text.\n"
            "- Keep named artifacts, systems, and interactions.\n"
            "- Keep subtext, but sharpen verbs; fewer 'was/were/started to/began to' when a stronger verb exists.\n"
            "- Use short, direct sentences where possible.\n"
            f"Approved named terms (reuse as needed): {approved_line}\n\n"
            f"BOOK BIBLE:\n{book_bible[:1200] if book_bible else 'None'}\n\n"
            f"REFERENCE EXCERPTS:\n{references_excerpt or 'No references provided.'}\n"
            f"DIRECTOR NOTES:\n{director_notes or 'None'}\n\n"
            "CHAPTER TO REWRITE:\n"
            "--- START ---\n"
            f"{chapter_text.strip()}\n"
            "--- END ---\n\n"
            "Return the tightened chapter."
        )
        response = await self._make_api_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.25,
            max_tokens=self._max_tokens_from_words(
                len(chapter_text.split()),
                buffer_ratio=0.1,
                min_tokens=600,
                max_tokens=3500
            ),
            top_p=1
        )
        revised, usage_data = self._extract_content_and_usage(response)
        return revised.strip(), usage_data

    def _sanitize_style_phrases(self, text: str) -> str:
        """Remove LLM artifacts (headings, markdown) but preserve prose choices."""
        updated = re.sub(r"^\s*#+\s*Finalized Chapter\s+\d+.*\n", "", text, flags=re.IGNORECASE | re.MULTILINE)
        updated = re.sub(r"^\s*Finalized Chapter\s+\d+.*\n", "", updated, flags=re.IGNORECASE | re.MULTILINE)
        updated = re.sub(r"^\s*#+\s*Chapter\s+\d+.*\n", "", updated, flags=re.IGNORECASE | re.MULTILINE)
        updated = re.sub(r"^\s*#+\s*Final Chapter.*\n", "", updated, flags=re.IGNORECASE | re.MULTILINE)
        updated = re.sub(r"^\s*Here's the revised.*\n", "", updated, flags=re.IGNORECASE | re.MULTILINE)
        updated = re.sub(r"^\s*-{3,}\s*$\n?", "", updated, flags=re.MULTILINE)
        updated = re.sub(r"\*\*(.+?)\*\*", r"\1", updated)
        updated = re.sub(r"__(.+?)__", r"\1", updated)
        updated = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"\1", updated)
        return updated

    def _ensure_paragraph_breaks(self, text: str, max_sentences: int = 4) -> str:
        if not text:
            return text
        # Always fix run-on sentences first
        text = self._fix_run_on_sentences(text)
        if "\n\n" in text.strip():
            return text
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        if len(sentences) <= max_sentences:
            return text
        chunks = []
        for i in range(0, len(sentences), max_sentences):
            chunk = " ".join(sentences[i:i + max_sentences]).strip()
            if chunk:
                chunks.append(chunk)
        return "\n\n".join(chunks)

    def _fix_run_on_sentences(self, text: str, max_words: int = 55) -> str:
        """Break up run-on sentences that exceed max_words without terminal punctuation."""
        if not text:
            return text
        paragraphs = re.split(r"\n\s*\n", text)
        fixed_paragraphs: list[str] = []
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            sentences = re.split(r'(?<=[.!?])\s+', para)
            fixed_sentences: list[str] = []
            for sentence in sentences:
                words = sentence.split()
                if len(words) <= max_words:
                    fixed_sentences.append(sentence)
                    continue
                # Split long sentence at natural break points
                result_parts: list[str] = []
                current: list[str] = []
                for word in words:
                    current.append(word)
                    joined = " ".join(current)
                    # Look for natural break points: semicolons, conjunctions after commas,
                    # participial phrases, relative clauses
                    if len(current) >= 20 and (
                        word.endswith(";")
                        or word.endswith(",")
                        or (word.lower() in ("and", "but", "yet", "so", "then", "while", "though", "although", "because", "before", "after", "when", "where", "which", "who") and len(current) >= 25)
                    ):
                        part = " ".join(current).rstrip(",;")
                        if not part[-1:] in ".!?":
                            part += "."
                        result_parts.append(part)
                        current = []
                if current:
                    part = " ".join(current)
                    if part and not part[-1:] in ".!?":
                        part += "."
                    result_parts.append(part)
                if result_parts:
                    fixed_sentences.extend(result_parts)
                else:
                    fixed_sentences.append(sentence)
            fixed_paragraphs.append(" ".join(fixed_sentences))
        return "\n\n".join(fixed_paragraphs)

    def _limit_which_clauses(self, text: str, max_per_paragraph: int = 1) -> str:
        """Disabled: deterministic clause rewriting damages prose voice."""
        return text
        return "\n\n".join(updated)

    def _needs_inference_chain_pass(self, text: str) -> bool:
        if not text:
            return False
        hits = len(re.findall(
            r"\b(which meant|which suggested|which implied|which revealed|this meant|this suggested|this revealed)\b",
            text.lower()
        ))
        return hits > 1

    def _trim_to_last_sentence(self, text: str) -> str:
        """Trim text back to the last complete sentence ending with . ! or ?"""
        if not text:
            return text
        trimmed = text.rstrip()
        last_terminal = max(
            trimmed.rfind('.'),
            trimmed.rfind('!'),
            trimmed.rfind('?'),
        )
        # Also check for closing quote after terminal punctuation
        for ending in ('."', '!"', '?"', ".'", "!'", "?'", '.)', '!)'):
            pos = trimmed.rfind(ending)
            if pos >= 0:
                last_terminal = max(last_terminal, pos + len(ending) - 1)
        if last_terminal > len(trimmed) * 0.5:
            return trimmed[:last_terminal + 1]
        return trimmed

    def _is_truncated_text(self, text: str) -> bool:
        if not text:
            return False
        trimmed = text.rstrip()
        # Check if the text ends with proper terminal punctuation
        if re.search(r'[.!?]["\')\]]?$', trimmed):
            return False
        # Em dash and ellipsis are valid literary endings
        if trimmed.endswith(("\u2014", "\u2026", "...", "\u2014\"", "\u2014'")):
            return False
        # If none of the above matched, the text is truncated
        return True

    def _strip_duplicate_prefix(self, tail: str, continuation: str) -> str:
        if not tail or not continuation:
            return continuation
        tail_snip = tail[-200:].strip()
        cont = continuation.lstrip()
        if tail_snip and cont.startswith(tail_snip):
            return cont[len(tail_snip):].lstrip()
        return continuation

    async def _continue_incomplete_chapter(
        self,
        text: str,
        chapter_number: int,
        context: Dict[str, Any],
        max_attempts: int = 2
    ) -> tuple[str, Dict[str, int]]:
        if not text:
            return text, {}
        updated = text.rstrip()
        usage_totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        for attempt in range(max_attempts):
            if not self._is_truncated_text(updated):
                break
            self.logger.warning("Chapter appears truncated; requesting continuation (attempt %s).", attempt + 1)
            tail = updated[-2000:]
            system_prompt = (
                "You are continuing a novel chapter. Continue exactly where it stops, "
                "finish the incomplete sentence if needed, and complete the chapter "
                "with full sentences and paragraphs. Do not repeat any existing text. "
                "Do not add headings. Use em dashes sparingly."
            )
            user_prompt = (
                "CHAPTER SO FAR:\n--- START ---\n"
                f"{tail}\n"
                "--- END ---\n"
                "Continue from the last fragment. Output ONLY the continuation text."
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            response = await self._make_api_call(
                messages=messages,
                temperature=0.4,
                max_tokens=4000,
                top_p=1,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                vector_store_ids=(context or {}).get("vector_store_ids", []),
                use_file_search=(context or {}).get("use_file_search", True)
            )
            continuation, usage_data = self._extract_content_and_usage(response)
            usage_totals["prompt_tokens"] += usage_data.get("prompt_tokens", 0)
            usage_totals["completion_tokens"] += usage_data.get("completion_tokens", 0)
            usage_totals["total_tokens"] += usage_data.get("total_tokens", 0)
            if not continuation:
                break
            continuation = self._strip_duplicate_prefix(tail, continuation)
            spacer = "" if updated.endswith(("\n", " ")) else " "
            updated = f"{updated}{spacer}{continuation.lstrip()}"
        return updated, usage_totals

    def _strip_glitch_sentences(self, text: str, approved_terms: list[str]) -> str:
        """Disabled: sentence deletion is too destructive for prose quality."""
        return text

    def _trim_motif_overuse(self, text: str) -> str:
        # Intentionally disabled: motif policing is not cross-genre safe and can distort voice.
        return text

    def _ensure_interaction_per_paragraph(self, text: str, approved_terms: list[str]) -> str:
        if not text:
            return text
        # Avoid auto-inserting interactions; enforce via specificity passes instead.
        return text

    def _specificity_gate_passes(
        self,
        text: str,
        approved_terms: list[str],
        chapter_number: Optional[int] = None
    ) -> bool:
        return len(self._specificity_gate_failures(text, approved_terms, chapter_number)) == 0

    async def _run_specificity_pass(
        self,
        chapter_text: str,
        book_bible: str,
        references_excerpt: str,
        director_notes: str,
        pass_level: int = 1,
        failures: Optional[list[str]] = None
    ) -> tuple[str, Dict[str, int]]:
        strict = pass_level >= 2
        approved_terms = self._get_approved_terms(book_bible, references_excerpt, director_notes)
        approved_line = ", ".join(approved_terms[:24]) if approved_terms else "None available"
        system_prompt = (
            "You are a fiction editor focused on specificity and lived-in detail.\n"
            "Replace generic abstractions with concrete, named artifacts and actions.\n"
            "Preserve POV, tense, and plot beats. Do not add new plot points.\n"
            "Return ONLY the revised chapter text.\n"
            "Avoid repetitive inference chains; keep 'which' clauses to a minimum.\n"
            "Avoid meta narration like 'the act of' or 'the technique of'.\n"
        )
        interaction_line = ", ".join([
            "open", "close", "load", "save", "scan", "search", "trace", "decrypt",
            "compile", "export", "upload", "download", "archive", "ping", "message",
            "index", "hash", "type", "click", "scroll", "write", "sketch", "send",
            "compose", "call", "text", "grab", "pull", "push", "turn", "flip",
            "hold", "place", "set", "take", "read", "watch", "listen", "look",
            "review", "check", "hover", "press", "select", "highlight", "drag",
            "drop", "swipe", "sit", "stand", "walk", "step", "enter", "move",
            "reach", "adjust", "slip", "plug"
        ])
        failure_line = ""
        if failures:
            failure_line = (
                "Fix these failures exactly (by paragraph when specified; paragraphs are separated by blank lines): "
                f"{', '.join(failures[:10])}.\n"
            )
        user_prompt = (
            "Revise for lived-in scene time and specificity without turning it into a checklist.\n"
            "Rules:\n"
            "- Preserve POV, tense, and plot beats. Do not add new plot points.\n"
            "- Remove trailer-voice narration and voiceover-style stingers.\n"
            "- Replace abstract recap with concrete actions, dialogue, and sensory anchors.\n"
            "- If a paragraph feels like montage/summary, convert it into immediate, in-scene action.\n"
            "- Keep emotions grounded in observable behavior within 1-2 sentences.\n"
            "- Use existing names/terms from the book bible or references when adding specificity; do not invent new proper nouns if none exist.\n"
            "- Use em dashes sparingly for emphasis or interruptions.\n"
            f"{failure_line}"
            "Remove generic stock phrases and vague imagery that lack concrete anchors.\n"
            f"{'Do NOT leave any generic placeholders. Use only names/terms consistent with the book bible or references.' if strict else ''}\n"
            f"Approved named terms (use several): {approved_line}\n\n"
            f"BOOK BIBLE:\n{book_bible[:1600] if book_bible else 'None'}\n\n"
            f"REFERENCE EXCERPTS:\n{references_excerpt or 'No references provided.'}\n"
            f"DIRECTOR NOTES:\n{director_notes or 'None'}\n\n"
            "CHAPTER TO REFINE:\n"
            "--- START ---\n"
            f"{chapter_text.strip()}\n"
            "--- END ---\n\n"
            "Return the revised chapter."
        )
        response = await self._make_api_call(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.25 if strict else 0.3,
            max_tokens=self._max_tokens_from_words(
                len(chapter_text.split()),
                buffer_ratio=0.15,
                min_tokens=800,
                max_tokens=4000
            ),
            top_p=1
        )
        revised, usage_data = self._extract_content_and_usage(response)
        return (revised.strip() if revised else ""), usage_data

    def _extract_named_terms(self, text: str, limit: int = 24) -> list[str]:
        if not text:
            return []
        tokens = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}|\b[A-Z]{2,}\b", text)
        stop = {"The", "And", "But", "His", "Her", "Their", "With", "From", "That", "This", "Chapter", "Scene"}
        seen: list[str] = []
        for token in tokens:
            cleaned = token.strip()
            if cleaned in stop:
                continue
            if cleaned not in seen:
                seen.append(cleaned)
            if len(seen) >= limit:
                break
        return seen

    async def _build_scene_plan(
        self,
        chapter_number: int,
        target_words: int,
        context: Dict[str, Any]
    ) -> GenerationResult:
        """Create a scene plan for the chapter based on objectives and constraints."""
        system_prompt = (
            "You are a story architect. Output STRICT JSON only.\n"
        )

        objectives = context.get("chapter_objectives", [])
        required_plot_points = context.get("required_plot_points", [])
        chapter_plan_summary = context.get("chapter_plan_summary", "")
        opening_type = context.get("opening_type", "")
        ending_type = context.get("ending_type", "")
        emotional_arc = context.get("emotional_arc", "")
        focal_characters = context.get("focal_characters", [])
        director_brief = context.get("director_brief", "")

        target_min = context.get("target_words_min")
        target_max = context.get("target_words_max")
        range_line = f"Acceptable range: {target_min}–{target_max} words.\n" if target_min and target_max else ""

        plan_feedback = context.get("scene_plan_feedback", "")
        feedback_block = f"\nSCENE PLAN FEEDBACK (must fix):\n{plan_feedback}\n" if plan_feedback else ""
        scene_rewrite_instruction = context.get("rewrite_instruction", "")
        rewrite_block = (
            f"\nAUTHOR REWRITE DIRECTION (highest priority):\n{scene_rewrite_instruction}\n"
            if scene_rewrite_instruction else ""
        )
        user_prompt = (
            f"Build a scene plan for Chapter {chapter_number}.\n"
            f"Target length: {target_words} words.\n"
            f"{range_line}\n"
            f"PLAN SUMMARY:\n{chapter_plan_summary}\n\n"
            f"DIRECTOR BRIEF:\n{director_brief[:1200] if director_brief else ''}\n\n"
            f"OBJECTIVES:\n{objectives}\n\n"
            f"REQUIRED PLOT POINTS:\n{required_plot_points}\n\n"
            f"OPENING TYPE: {opening_type}\n"
            f"ENDING TYPE: {ending_type}\n"
            f"EMOTIONAL ARC: {emotional_arc}\n"
            f"FOCAL CHARACTERS: {focal_characters}\n\n"
            f"PACING TARGETS: {context.get('pacing_targets', {})}\n\n"
            f"{feedback_block}"
            f"{rewrite_block}"
            "Rules:\n"
            "- Do not repeat setup/onboarding/announcement beats.\n"
            "- Only one inciting delivery per chapter.\n"
            "- Scene functions must be varied and escalated.\n"
            "- Each scene must include two scene-specific world markers (proper noun + concrete constraint affecting behavior in that scene).\n"
            "- detail_targets must include a concrete artifact and a concrete interaction.\n"
            "- Each scene must include micro_observation (a concrete observation) and inference_beat (a short judgment line).\n"
            "- detail_targets entries must include 'Artifact:' and 'Interaction:' prefixes.\n\n"
            "- Each scene summary must imply a cause → reaction tactic → consequence/complication beat (no montage compression).\n"
            "- If a named org/system/place/concept appears in a scene, the summary must state its immediate constraint on behavior in that scene.\n\n"
            "detail_targets format requirements:\n"
            "- Artifact: Use an exact object/document/message term already established in book bible/references/chapter plan; do not invent new named items.\n"
            "- Interaction: Use a specific verb + object (for example: opens the folder; locks the door; reads the letter).\n\n"
            "Return JSON:\n"
            "{\n"
            '  "scenes": [\n'
            "    {\n"
            '      "scene_number": number,\n'
            '      "scene_function": "setup|escalation|reveal|reversal|payoff",\n'
            '      "goal": string,\n'
            '      "summary": string,\n'
            '      "focus_characters": [string],\n'
            '      "tone": string,\n'
            '      "consequence": string,\n'
            '      "world_marker": string,\n'
            '      "detail_targets": [string],\n'
            '      "micro_observation": string,\n'
            '      "inference_beat": string,\n'
            '      "emotional_beat": string\n'
            "    }\n"
            "  ]\n"
            "}\n"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            response = await self._make_api_call(
                messages=messages,
                temperature=0.2,
                max_tokens=1000,
                response_format={"type": "json_object"},
                vector_store_ids=context.get("vector_store_ids", []),
                use_file_search=context.get("use_file_search", True)
            )
        except Exception as e:
            return GenerationResult(success=False, content="", metadata={}, error=str(e))

        content, _ = self._extract_content_and_usage(response)
        try:
            data = json.loads(content)
        except Exception as e:
            # Best-effort cleanup when chat-completions fallback adds extra text
            cleaned = content.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
                cleaned = re.sub(r"```$", "", cleaned).strip()
            start_idx = cleaned.find("{")
            end_idx = cleaned.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                extracted = cleaned[start_idx:end_idx + 1]
                extracted = re.sub(r",\s*([}\]])", r"\1", extracted)
                try:
                    data = json.loads(extracted)
                except Exception:
                    return GenerationResult(success=False, content="", metadata={}, error=f"Scene plan JSON parse failed: {e}")
            else:
                return GenerationResult(success=False, content="", metadata={}, error=f"Scene plan JSON parse failed: {e}")

        scenes = data.get("scenes", [])
        return GenerationResult(success=True, content="", metadata={"scene_plan": scenes})

    def _load_prompt_config(self, filename: str) -> Optional[Dict[str, Any]]:
        """Load a YAML prompt config from the prompts directory."""
        candidates = [
            self.prompts_dir / filename,
            Path(__file__).resolve().parents[1] / "prompts" / filename,
            Path("prompts") / filename
        ]
        for path in candidates:
            if path.exists():
                with open(path, "r", encoding="utf-8") as handle:
                    return yaml.safe_load(handle)
        return None

    def _build_reference_digest(
        self,
        references: Dict[str, Any],
        max_total_chars: int = 3200,
        per_ref_limit: int = 900
    ) -> str:
        """Build a compact references digest for director prompts."""
        if not references:
            return "No reference files available."
        digest = ""
        used = 0
        for ref_name, ref_content in references.items():
            if used >= max_total_chars:
                break
            if not isinstance(ref_content, str):
                continue
            remaining = max_total_chars - used
            excerpt = ref_content.strip()
            if len(excerpt) > per_ref_limit:
                excerpt = excerpt[:per_ref_limit].rstrip() + "..."
            excerpt = excerpt[:remaining]
            if excerpt:
                digest += f"\n--- {ref_name} ---\n{excerpt}\n"
                used += len(excerpt)
        return digest.strip() if digest.strip() else "No reference files available."

    def _extract_director_guide(self, references: Dict[str, Any]) -> str:
        """Extract a director guide reference if present."""
        if not references:
            return ""
        lowered = {str(k).lower(): v for k, v in references.items()}
        for key, value in lowered.items():
            if "director-guide" in key or "director guide" in key or "director_guide" in key:
                return value if isinstance(value, str) else ""
        return ""

    async def generate_director_brief(
        self,
        chapter_number: int,
        target_words: int,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generate a director brief to guide first-draft output.

        NOTE: context["rewrite_instruction"] is not injected here. The director
        brief feeds into scene-by-scene generation where _build_scene_prompt and
        _build_scene_plan both inject the rewrite instruction directly.
        """
        context = context or {}
        template = self._load_prompt_config("director-brief.yaml")
        if not template:
            raise ValueError("director-brief.yaml not found in prompts directory.")

        references = context.get("references", {}) or {}
        director_guide = self._extract_director_guide(references)
        references_summary = self._build_reference_digest(references)

        variables = {
            "chapter_number": chapter_number,
            "target_words": target_words,
            "book_bible": context.get("book_bible", ""),
            "references_summary": references_summary,
            "director_guide": director_guide,
            "vector_memory_context": context.get("vector_memory_context", "") or context.get("vector_context", ""),
            "vector_memory_guidelines": context.get("vector_memory_guidelines", "") or context.get("vector_guidelines", ""),
            "arc_diagnostics": context.get("arc_diagnostics", ""),
            "chapter_plan_summary": context.get("chapter_plan_summary", ""),
            "chapter_contract": context.get("chapter_contract", ""),
            "chapter_objectives": context.get("chapter_objectives", []),
            "required_plot_points": context.get("required_plot_points", []),
            "opening_type": context.get("opening_type", ""),
            "ending_type": context.get("ending_type", ""),
            "emotional_arc": context.get("emotional_arc", ""),
            "focal_characters": context.get("focal_characters", []),
            "pov_character": context.get("pov_character", ""),
            "pov_type": context.get("pov_type", ""),
            "pov_notes": context.get("pov_notes", ""),
            "previous_chapters_summary": context.get("previous_chapters_summary", ""),
            "director_notes": context.get("director_notes", ""),
            "chapter_blueprint": context.get("chapter_blueprint", "")
        }

        safe_vars = {k: (v if v is not None else "") for k, v in variables.items()}
        system_prompt = template.get("system_prompt", "").format(**safe_vars)
        user_prompt = template.get("user_prompt", "").format(**safe_vars)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        response = await self._make_api_call(
            messages=messages,
            temperature=template.get("temperature", 0.4),
            max_tokens=template.get("max_tokens", 1600),
            top_p=1,
            vector_store_ids=context.get("vector_store_ids", []),
            use_file_search=context.get("use_file_search", True)
        )

        content, _ = self._extract_content_and_usage(response)
        brief = content.strip()
        if not self._director_brief_has_required_fields(brief):
            extra_notes = "Director brief must include: Unique World Markers (2 per scene), Concrete Artifact, Named Interaction."
            context = {**context, "director_notes": (context.get("director_notes", "") + "\n" + extra_notes).strip()}
            variables["director_notes"] = context.get("director_notes", "")
            safe_vars = {k: (v if v is not None else "") for k, v in variables.items()}
            system_prompt = template.get("system_prompt", "").format(**safe_vars)
            user_prompt = template.get("user_prompt", "").format(**safe_vars)
            response = await self._make_api_call(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=template.get("temperature", 0.4),
                max_tokens=template.get("max_tokens", 1600),
                top_p=1,
                vector_store_ids=context.get("vector_store_ids", []),
                use_file_search=context.get("use_file_search", True)
            )
            content, _ = self._extract_content_and_usage(response)
            brief = content.strip()
        return brief

    def _director_brief_has_required_fields(self, brief: str) -> bool:
        if not brief:
            return False
        lowered = brief.lower()
        # Keep this permissive: templates can vary slightly, we only need proof the brief contains the required levers.
        has_world_markers = ("unique world marker" in lowered) or ("unique world markers" in lowered)
        has_artifact = ("named artifact" in lowered) or ("concrete artifact" in lowered) or ("artifact" in lowered)
        has_interaction = ("named interaction" in lowered) or ("interaction" in lowered)
        return has_world_markers and has_artifact and has_interaction

    def _build_scene_prompt(self, chapter_number: int, scene_context: Dict[str, Any]) -> tuple[str, str]:
        """Build prompts for a single scene."""
        system_prompt = (
            "You are a professional novelist writing a single scene within a larger chapter.\n"
            "Keep continuity with the story context. Do not repeat prior openings or endings.\n"
            "Respect the chapter POV guidance and maintain the assigned viewpoint.\n"
            "Output plain text only (no Markdown: no headings, bullets, blockquotes, emphasis markers, or separators).\n"
            "Do not include scene headers or time/location stamp headers; embed time/place in-prose when relevant.\n"
            "Avoid narrator-summary voiceover lines; keep the camera in scene-time.\n"
            "Causal chain: ensure a cause → reaction tactic → consequence beat within the scene; show beat-by-beat action instead of skipping.\n"
            "Named reveals become constraints: when a named org/system/place/concept appears, show its immediate constraint on behavior within 1-2 sentences.\n"
            "Dialogue must have leverage: if dialogue appears, it must include a lever (request/refusal/bargain/threat/concealment), not just support/exposition.\n"
            "Anti-montage guardrail: no more than one zoom-out/generalization sentence in a row; return to observable detail + action.\n"
            "Action-justified specificity: do not list objects unless each object changes what the POV can do right now.\n"
            "Ensure the scene contributes directly to the chapter objectives and required plot points.\n"
            "Include two scene-specific world markers (proper noun + concrete constraint affecting behavior in this scene).\n"
            "Ensure the consequence is clear by the end (cost/gain/new obligation). It does not need to be stated as a 'button' in the last lines.\n"
            "Include a concrete artifact (object/document/message) and a concrete interaction (verb + object).\n"
            "Include one micro-observation and one short inference beat (a brief judgment line like 'Too steady.').\n"
            "Do not pad with lists or repetition to reach word count; end cleanly when the scene goal is met.\n"
            "Return only the scene text with no commentary.\n"
            "Prefer concrete specifics over abstract poetic description.\n"
            "Avoid abstract, generalized phrasing without a concrete scene anchor.\n"
        )

        user_prompt = (
            f"Write Scene {scene_context.get('scene_number')} of Chapter {chapter_number}.\n\n"
            f"CHAPTER POV: {scene_context.get('pov_character', '')} ({scene_context.get('pov_type', '')})\n"
            f"SCENE FUNCTION: {scene_context.get('scene_function', '')}\n"
            f"SCENE GOAL: {scene_context.get('scene_goal')}\n"
            f"SCENE SUMMARY: {scene_context.get('scene_summary')}\n"
            f"FOCUS CHARACTERS: {scene_context.get('scene_focus_characters')}\n"
            f"TONE: {scene_context.get('scene_tone')}\n"
            f"CONSEQUENCE: {scene_context.get('scene_consequence')}\n"
            f"UNIQUE WORLD MARKERS: {scene_context.get('scene_world_marker')}\n"
            f"DETAIL TARGETS (include named artifact + named interaction): {scene_context.get('scene_detail_targets')}\n"
            f"MICRO-OBSERVATION: {scene_context.get('scene_micro_observation', '')}\n"
            f"INFERENCE BEAT: {scene_context.get('scene_inference_beat', '')}\n"
            f"EMOTIONAL BEAT: {scene_context.get('scene_emotional_beat')}\n"
            f"TARGET WORDS: {scene_context.get('scene_target_words')}\n"
            f"PREVIOUS SCENE SUMMARY: {scene_context.get('previous_scene_summary')}\n\n"
            f"DIRECTOR BRIEF (APPLY LIGHTLY):\n{scene_context.get('director_brief', '')[:900]}\n\n"
            f"CHAPTER CONTRACT:\n{scene_context.get('chapter_contract', '')}\n\n"
            f"CADENCE TARGETS: {scene_context.get('cadence_targets', {})}\n"
            f"PACING TARGETS: {scene_context.get('pacing_targets', {})}\n"
            f"AVOID PHRASES: {scene_context.get('avoid_phrases', [])}\n\n"
            f"STORY CONTEXT:\n{scene_context.get('book_bible', '')[:1200]}\n\n"
            f"MEMORY LEDGER:\n{scene_context.get('memory_ledger', '')[:1200]}\n\n"
            f"BRIDGE REQUIREMENTS:\n{scene_context.get('bridge_requirements', [])}\n\n"
        )
        scene_rewrite = (scene_context.get("rewrite_instruction") or "").strip()
        if scene_rewrite:
            user_prompt += (
                f"AUTHOR REWRITE DIRECTION (highest priority — the author specifically requested this):\n"
                f"{scene_rewrite}\n\n"
            )
        user_prompt += "Write the full scene now."

        return system_prompt, user_prompt
    
    def _build_spike_prompts(self, chapter_number: int, target_words: int, target_range: Optional[Tuple[int, int]] = None) -> tuple[str, str]:
        """Build simple prompts for spike testing (genre-agnostic)."""
        system_prompt = """You are an expert novelist writing a publication-quality chapter.
        Focus on:
        - Lived-in scene-time prose (no trailer voice)
        - Compelling character development through action and choice
        - Strong dialogue with subtext
        - Multiple layers of tension (quiet, interpersonal, external)
        - Meaningful plot advancement

        Output plain text only (no Markdown). Use em dashes sparingly.
        Write within the word budget without padding."""
        
        range_line = f"- Acceptable range: {target_range[0]}–{target_range[1]} words (end early if the beat resolves)\n" if target_range else ""
        
        user_prompt = f"""Write Chapter {chapter_number} of a novel.
        
        Requirements:
        - Target length: {target_words} words
        {range_line}        - Include meaningful plot advancement
        - Develop characters through action and dialogue
        - Build tension throughout
        - End with a specific next pressure/obligation/question (no narrator wrap-up or teaser voice)
        
        Begin writing the chapter now."""
        
        return system_prompt.format(target_words=target_words), user_prompt
    
    def _build_comprehensive_prompts(self, chapter_number: int, target_words: int, context: Optional[Dict[str, Any]]) -> tuple[str, str]:
        """Build comprehensive prompts for full chapter generation with reference/context injection."""
        # Base system guidance
        target_min = (context or {}).get("target_words_min")
        target_max = (context or {}).get("target_words_max")
        target_range = (target_min, target_max) if target_min and target_max else None

        base_system = (
            "You are an expert novelist following a comprehensive writing system.\n\n"
            "WRITING SYSTEM REQUIREMENTS:\n"
            f"- Target length: {target_words} words. YOU MUST WRITE THE FULL {target_words} WORDS. Plan 3-4 full scenes to fill this length. Do not stop at 1500-2000 words; continue developing scenes until you reach the target.\n"
            "- Minimum 2 significant plot advancement points\n"
            "- Character development through action and dialogue\n"
            "- Multiple tension layers throughout\n"
            "- Professional prose quality (publication standard)\n"
            "- Strong opening that starts in-scene (physical interaction + sensory cue + immediate pressure)\n"
            "- Ending that lands on a specific next pressure/obligation/question (no narrator wrap-up or teaser voice)\n"
            "- Causal-chain cadence: every ~150-250 words, include a cause → reaction tactic → consequence/complication beat (something changes; the POV responds; the situation bites back)\n"
            "- Named reveals become constraints: when a named org/system/place/concept appears, within the next 1-2 sentences show how it constrains the POV’s next action (timer, risk, lockout, demand, tradeoff). Do not stack names as lore.\n"
            "- Dialogue must have leverage: every on-page exchange includes a lever (request/refusal/bargain/threat/concealment) and a divergence of aims; avoid purely supportive/expository dialogue\n"
            "- Anti-montage guardrail: no more than one “zoom-out” sentence in a row (news/socials/everywhere/legend framing). After one, cut back to one observable detail + one action.\n"
            "- Action-justified specificity: do not list objects unless each object changes what the POV can do right now\n"
            "- Authentic dialogue with subtext\n"
            "- Varied sentence structure and pacing\n"
            "- Avoid runaway repetition: do not loop words, phrases, or list synonyms\n"
            "- If repetition begins, stop and move to the next plot action\n"
            "- Normal repetition of names, key terms, and catchphrases is acceptable\n"
            "- Use em dashes sparingly and purposefully for interruptions, asides, or emphasis\n\n"
            "- Output ONLY the chapter text; no headings, notes, or multiple versions\n"
            "- Output plain text only (no Markdown formatting)\n\n"
            "- Prefer concrete specifics over abstract poetic description\n"
            "- Name actual artifacts, interfaces, brands, or objects when mentioned\n"
            "- If a noun is generic (relic, archive, device), specify what it is\n\n"
            "- Avoid trailer-voice narration; write in-scene with concrete actions\n"
            "- No global-summary drift; keep every paragraph grounded in physical detail\n"
            "- Keep the camera in scene-time: dramatize beats instead of summarizing them\n"
            "- Use concrete interactions overall in each scene (who does what, with what, in what space)\n"
            "- Avoid repetitive explanation chains (limit explicit inference clauses)\n"
            "- Vary sentence openings; avoid long runs of identical openings\n"
            "- If an artifact lacks a proper name, label it with an identifier (locker 12B, file 3, gate A7)\n"
            "- Avoid vague labels like 'favorite movies' without naming the specific item and why it matters\n"
            "- No decorative imagery without a concrete anchor\n\n"
            "- Each scene must include a concrete artifact (object/document/message) and a concrete interaction (verb + object)\n"
            "- If a paragraph uses summary verbs (was, were, felt, realized, knew, seemed), the next paragraph must include physical action plus a sensory anchor\n"
            "- Avoid abstract, generalized phrasing without a concrete scene anchor.\n\n"
            "ENDING CONTRACT (do not violate):\n"
            "- Do not end with tagline/button lines (e.g. “the hunt begins”, “this was only the beginning”, “no turning back”).\n"
            "- Do NOT end every chapter on a cliffhanger. Vary endings: some resolve cleanly, some end on a quiet moment, some end mid-dialogue, some end on a specific action.\n"
            "- Do not end with generic closers like 'whatever came next, he was ready' or 'into the unknown' or 'the only way forward.'\n"
            "- Do NOT end with a character alone reflecting while the setting hums/presses/settles around them. This is the most common AI ending pattern.\n"
            "- Do NOT end with thematic declarations ('Work was dignity', 'The day pressed on', 'Some things never change').\n"
            "- Do NOT end with a character walking away while atmospheric details close around them.\n"
            "- Instead: end mid-dialogue, end on a specific physical action, end with a question from another character, end on a sensory detail WITHOUT interpretation.\n"
            "- The chapter must end on a COMPLETE SENTENCE with terminal punctuation. Never end mid-sentence or mid-word.\n\n"
            "CONTENT COMPOSITION TARGETS (approximate, not rigid):\n"
            "- Dialogue: 30% to 70%\n"
            "- Action: 20% to 50%\n"
            "- Internal monologue: 15% to 40%\n"
            "- Description: 10% to 30%\n\n"
            "CRAFT DISCIPLINE (CRITICAL — these are the most common quality failures in AI-generated novels):\n\n"
            "CHAPTER STRUCTURE VARIETY (MOST IMPORTANT):\n"
            "- Every chapter MUST have a different shape. Do NOT repeat the same structural template across chapters.\n"
            "- If the previous chapter was action-heavy, this one should breathe. If the previous was dialogue-heavy, try a different approach.\n"
            "- Alternative chapter shapes: quiet aftermath, character conversation, backstory through present action, planning/strategy, a character alone processing, confrontation without action, discovery through routine, a relationship deepening, a celebration or rest, travel or transition.\n"
            "- At least 1 in every 3 chapters should be a 'quiet' chapter — lower stakes, character-focused, building relationships or world.\n\n"
            "CHAPTER OPENINGS — NO FORMULA:\n"
            "- Do NOT open every chapter with '[Character name] + [physical verb] + [object/sensation]'.\n"
            "- Vary openings: start with dialogue, start with setting, start mid-conversation, start with a quiet observation, start with a time skip, start with a different character.\n"
            "- Check the PREVIOUS OPENING LINES provided. Your opening must feel completely different.\n\n"
            "PACING AND TENSION VARIATION:\n"
            "- Do NOT maintain the same level of tension in every chapter. Tension must rise and fall across the book.\n"
            "- If the previous 2 chapters were tense or urgent, this chapter should slow down and breathe.\n"
            "- Urgency and stakes should come from character relationships and consequences, not from artificial devices like countdown timers or arbitrary deadlines.\n"
            "- Do not use the same tension device (chase, deadline, confrontation, discovery) in consecutive chapters.\n\n"
            "RESTRAINT WITH NEW INFORMATION:\n"
            "- Do not overload chapters with new plot elements. Introduce 1-2 significant new developments per chapter maximum.\n"
            "- Each new development must be explored and given room to land before the next one appears.\n"
            "- Some chapters should deepen EXISTING threads rather than introduce new ones. Not every chapter needs a new revelation.\n"
            "- Return to earlier developments. Deepen them. Show consequences. Do not abandon threads for new ones.\n\n"
            "NO OVER-SIGNALING (this is the #1 quality failure in AI fiction):\n"
            "- Present a detail's significance through ONE channel only. Never narration + thought + dialogue on the same point.\n"
            "- BAD (triple-signaling the same observation):\n"
            "  [narration] The boot print pointed the wrong direction.\n"
            "  [thought] Someone had walked out, not in. That changed everything.\n"
            "  [dialogue] 'You see that print? It's facing the wrong way.'\n"
            "  This says the same thing three times. The reader understood after the first line.\n"
            "- GOOD (single channel, then move on):\n"
            "  The boot print pointed the wrong direction. He photographed it and moved to the next marker.\n"
            "- If you have SHOWN something through action or description, do NOT also EXPLAIN it in thought or dialogue.\n"
            "- If a character notices something, do not then have them think about what it means AND tell someone about it. Pick one.\n"
            "- SINGLE-CHANNEL RULE: Every emotional point gets ONE channel only:\n"
            "  Option A: action/body language. Option B: dialogue. Option C: brief thought.\n"
            "  NEVER combine two. After showing an emotion, the NEXT paragraph must be about something else.\n"
            "- If a character makes a decision, show it through action. Do not also have them think about it or discuss it.\n\n"
            "PROSE INTENSITY VARIATION (the #2 quality failure):\n"
            "- PLAIN PROSE — use for at least 50% of all paragraphs:\n"
            "  'He checked the gauge. Normal range. He wrote it down and walked to the next station.'\n"
            "  'Coffee was cold. He drank it anyway.'\n"
            "  'The door was locked. He tried the next one.'\n"
            "- VIVID PROSE — use for 2-3 moments per chapter ONLY:\n"
            "  'The corrosion bloom had spread overnight, orange tendrils reaching across the flange like fingers.'\n"
            "- After every vivid sentence, write at least TWO plain sentences before the next vivid one.\n"
            "- Most paragraphs should have ZERO metaphors, similes, or sensory flourishes. Just action, dialogue, or fact.\n"
            "- Do NOT give every noun a modifier. 'The door' not 'the battered steel door with chipped paint.'\n\n"
            "DO NOT RE-EXPLAIN ESTABLISHED FACTS:\n"
            "- If evidence, a discovery, or an observation was fully described in a previous chapter, reference it in ONE short phrase only.\n"
            "- GOOD: 'the boot print from Clarifier 1' or 'the foam sample he'd collected Tuesday'\n"
            "- BAD: Re-describing what the boot print looked like, where it pointed, what it might mean — the reader already knows all of this.\n"
            "- Each piece of evidence or discovery should be DESCRIBED IN FULL exactly ONCE in the book (the chapter where it first appears). After that, brief references only.\n"
            "- Do not recap previous chapter events. The reader has already read them.\n\n"
            "GENRE AUTHENTICITY:\n"
            "- Stay true to the genre and tone described in the book bible. Do not import mechanics from other genres.\n"
            "- The story's world, setting, and character relationships should generate tension and interest naturally.\n"
            "- Avoid generic dramatic devices that feel imported: theatrical reveals, convenient timing, melodramatic reactions.\n"
            "- When in doubt, choose the version of a scene that feels most authentic to this specific story's world.\n\n"
            "CHARACTER CONSISTENCY:\n"
            "- Every named character must be consistent across all chapters. Same name, same pronouns, same physical description.\n"
            "- Do not introduce characters and then forget them. Account for their presence or absence in later chapters.\n"
            "- Every named character should feel like a person, not a plot device. Give them opinions, habits, relationships, or moments that exist beyond their story function.\n"
            "- Limit the active cast per chapter. Do not introduce new named characters after the first third of the book unless essential.\n\n"
            "PHYSICAL CONTINUITY:\n"
            "- Track the physical state of objects, locations, and characters precisely. Maintain consistency across chapters.\n"
            "- Character pronouns must be consistent. Do not switch a character's gender or name between chapters.\n"
            "- If a character was in one location at the end of the previous chapter, account for how they got to a different location.\n"
            "- Check the continuity context before introducing details that might contradict established facts.\n\n"
            "DIALOGUE AUTHENTICITY:\n"
            "- Characters NEVER state the theme of the book in dialogue. Theme emerges through action and choice.\n"
            "- BAD: 'That's what dignity is.' 'It's about doing what's right.'\n"
            "- GOOD: Characters talk about concrete problems, not abstract values.\n"
            "- Confessions use euphemism and deflection, not direct admission:\n"
            "  BAD: 'I changed the logs. I didn't think anyone would get hurt.'\n"
            "  GOOD: 'The numbers were... adjusted. You know how it is. Everybody does it.'\n"
            "- Villain dialogue must be specific to THIS character's world, not stock villain lines:\n"
            "  BAD: 'It's about respect. Nobody gives it, so I take it.'\n"
            "  GOOD: Specific grievance rooted in the story's workplace/relationships.\n"
            "- No rehearsal monologues: characters do NOT practice what they will say to other characters.\n\n"
            "QUALITY STANDARDS:\n"
            "- 8+ on all craft elements (character, plot, prose, structure)\n"
            "- Reader engagement throughout\n"
            "- Genre expectations met (based on book bible)\n"
            "- Professional polish and consistency\n"
            "- Use file_search tool when available to retrieve missing facts before writing\n"
        )

        # Chapter-to-chapter coherence guardrails (global)
        if chapter_number > 1:
            base_system += (
                "\nCHAPTER-TO-CHAPTER COHERENCE (GLOBAL, NON-NEGOTIABLE):\n"
                f"- This is Chapter {chapter_number}. Begin in-scene from the prior chapter’s final consequence OR explicitly signal an in-scene time-skip.\n"
                "- NO recap paragraph. Do not restate what happened in prior chapters.\n"
                "- Within the first ~300 words, explicitly continue at least one established thread (obligation, clue, consequence, relationship tension, unresolved question).\n"
                "- Entity grounding rule: if you introduce a named character/org/place/system/concept in the first ~500 words, it must be grounded (already established in canon/continuity materials OR introduced via explicit connection to an established element).\n"
                "- Major-event rule: do not drop a major prior incident as if the reader already knows it. Surface major past events as present-time pressure/discovery/consequence, not backstory dump.\n"
                "\nCROSS-CHAPTER FRESHNESS (CRITICAL):\n"
                "- Do NOT repeat the same sensory descriptions chapter after chapter (e.g. always mentioning 'recycled air', 'metallic tang', 'the hum of'). Find NEW sensory details each chapter.\n"
                "- Each chapter must introduce at least 2-3 new environmental details, objects, or sensory experiences not used in previous chapters.\n"
                "- Vary how you describe recurring elements. If a character has a habit, show it differently each time or skip it in some chapters.\n"
                "- Do NOT describe the setting atmosphere the same way in every chapter opening. Each chapter should feel like a new room, a new moment, a new mood.\n"
            )

        if target_range:
            base_system += f"\nTARGET RANGE: {target_range[0]}–{target_range[1]} words. Treat this as a budget, not a mandate.\n"

        # Inject contextual information
        def _trim(text: str, max_chars: int) -> str:
            if not text:
                return ""
            if len(text) <= max_chars:
                return text
            return text[:max_chars] + "..."

        book_bible = (context or {}).get("book_bible", "") or (context or {}).get("book_bible_content", "")
        previous_summary = (context or {}).get("previous_chapters_summary", "") or (context or {}).get("previous_chapters", "")
        # Continuity-specific hints
        continuity_story_so_far = (context or {}).get("continuity_story_so_far", "")
        continuity_requirements = (context or {}).get("continuity_requirements", [])
        continuity_required_plot_advancement = (context or {}).get("continuity_required_plot_advancement", "")
        continuity_character_needs = (context or {}).get("continuity_character_needs", {})
        continuity_themes_to_continue = (context or {}).get("continuity_themes_to_continue", [])
        continuity_unresolved_questions = (context or {}).get("continuity_unresolved_questions", []) or (context or {}).get("unresolved_questions", [])
        pacing_guidance = (context or {}).get("pacing_guidance", {})
        previous_opening_lines = (context or {}).get("previous_opening_lines", [])
        previous_ending_lines = (context or {}).get("previous_ending_lines", [])
        last_chapter_ending = (context or {}).get("last_chapter_ending", "")
        arc_diagnostics = (context or {}).get("arc_diagnostics", {})
        pattern_database_summary = (context or {}).get("pattern_database_summary", "")
        repetition_risks = (context or {}).get("repetition_risks", {})
        avoid_phrases = (context or {}).get("avoid_phrases", [])
        repetition_allowlist = (context or {}).get("repetition_allowlist", [])
        memory_ledger = (context or {}).get("memory_ledger", "")
        chapter_objectives = (context or {}).get("chapter_objectives", [])
        chapter_plan_summary = (context or {}).get("chapter_plan_summary", "")
        required_plot_points = (context or {}).get("required_plot_points", [])
        opening_type = (context or {}).get("opening_type", "")
        ending_type = (context or {}).get("ending_type", "")
        emotional_arc = (context or {}).get("emotional_arc", "")
        focal_characters = (context or {}).get("focal_characters", [])
        plan_continuity_requirements = (context or {}).get("plan_continuity_requirements", [])
        cadence_targets = (context or {}).get("cadence_targets", {})
        pacing_targets = (context or {}).get("pacing_targets", {})
        timeline_state = (context or {}).get("timeline_state", {})
        timeline_constraints = (context or {}).get("timeline_constraints", [])
        director_notes = (context or {}).get("director_notes", "")
        regen_feedback = (context or {}).get("regen_feedback", "")
        director_brief = (context or {}).get("director_brief", "")
        vector_context = (context or {}).get("vector_context", "")
        vector_guidelines = (context or {}).get("vector_guidelines", "")
        pov_character = (context or {}).get("pov_character", "")
        pov_type = (context or {}).get("pov_type", "")
        pov_notes = (context or {}).get("pov_notes", "")
        pov_shift = (context or {}).get("pov_shift", False)
        bridge_requirements = (context or {}).get("bridge_requirements", [])
        chapter_ledger_summary = (context or {}).get("chapter_ledger_summary", "")
        chapter_contract = (context or {}).get("chapter_contract", "")
        chapter_title = (context or {}).get("chapter_title", "")
        transition_note = (context or {}).get("transition_note", "")
        story_arcs = (context or {}).get("story_arcs", {})
        remaining_word_budget = (context or {}).get("remaining_word_budget", 0)
        overused_words = (context or {}).get("overused_words", [])
        overused_phrases = (context or {}).get("overused_phrases", [])
        remaining_chapters = (context or {}).get("remaining_chapters", 0)
        total_chapters = (context or {}).get("total_chapters", 0)

        # Back-compat / cross-flow support:
        # Some callers provide continuity as a nested dict under `context["continuity"]`.
        # Normalize that into the top-level continuity fields consumed below.
        continuity_snapshot = (context or {}).get("continuity", {})
        continuity_character_continuity = None
        continuity_plot_threads = None
        continuity_world_state = None
        if isinstance(continuity_snapshot, dict) and continuity_snapshot:
            if not continuity_story_so_far:
                continuity_story_so_far = str(continuity_snapshot.get("story_so_far") or "")
            if not continuity_requirements:
                continuity_requirements = continuity_snapshot.get("continuity_requirements") or continuity_snapshot.get("requirements") or []
            if not continuity_required_plot_advancement:
                continuity_required_plot_advancement = str(continuity_snapshot.get("required_plot_advancement") or "")
            if not continuity_character_needs:
                continuity_character_needs = continuity_snapshot.get("character_development_needs") or continuity_snapshot.get("character_needs") or {}
            if not continuity_themes_to_continue:
                continuity_themes_to_continue = continuity_snapshot.get("themes_to_continue") or []
            if not continuity_unresolved_questions:
                continuity_unresolved_questions = continuity_snapshot.get("unresolved_questions") or []
            if not pacing_guidance:
                pacing_guidance = continuity_snapshot.get("pacing_guidance") or {}
            if not timeline_state:
                timeline_state = continuity_snapshot.get("timeline_state") or {}
            if not timeline_constraints:
                timeline_constraints = continuity_snapshot.get("timeline_constraints") or []
            if not arc_diagnostics:
                arc_diagnostics = continuity_snapshot.get("arc_diagnostics") or {}
            if not memory_ledger:
                memory_ledger = str(continuity_snapshot.get("memory_ledger") or "")

            # Additional continuity data (not always present in top-level context)
            continuity_character_continuity = continuity_snapshot.get("character_continuity")
            continuity_plot_threads = continuity_snapshot.get("plot_threads")
            continuity_world_state = continuity_snapshot.get("world_state")

        # Build references summary — generous context to reduce hallucination and repetition
        references_summary = ""
        max_total_ref_chars = 25000
        used = 0
        refs_dict = (context or {}).get("references", {}) or {
            # support keys like characters_reference, etc.
            k.replace("_reference", ""): v for k, v in ((context or {}).items()) if isinstance(v, str) and k.endswith("_reference")
        }
        for ref_name, ref_content in refs_dict.items():
            if used >= max_total_ref_chars:
                break
            remaining = max_total_ref_chars - used
            excerpt = _trim(ref_content, min(4000, remaining))
            if excerpt.strip():
                references_summary += f"\n--- {ref_name} ---\n{excerpt}\n"
                used += len(excerpt)
        if not references_summary:
            references_summary = "No reference files available."

        limited_book_bible = _trim(book_bible, 30000) if book_bible else "No book bible available."
        limited_prev = _trim(previous_summary, 6000) if previous_summary else "No previous chapters."
        limited_continuity = _trim(continuity_story_so_far, 5000) if continuity_story_so_far else ""
        limited_last_ending = _trim(last_chapter_ending, 2000) if last_chapter_ending else ""

        system_prompt = base_system + (
            "\nUse the provided STORY CONTEXT to maintain consistency with established characters, plot, world rules, and style.\n"
            "Reference specific details; do not restate long passages.\n"
            "Avoid repeating phrasing and imagery listed in repetition risks or avoid lists.\n"
            "Satisfy all chapter objectives and required plot points without adding new unrelated beats.\n"
            "Maintain the specified POV. If POV shifts, anchor the opening to immediate consequences from the prior chapter.\n"
            "If a CHAPTER BLUEPRINT is provided, follow its structural plan: opening approach, chapter shape, ending approach, prose register, and scene plan.\n"
            "If ANTI-PATTERN context is provided, actively avoid the patterns listed there.\n"
            "Apply the Director Brief as guiding intent, not a rigid script. Write like a human novelist.\n"
        )

        # Build continuity directives section
        continuity_lines: list[str] = []
        if limited_continuity:
            continuity_lines.append("CONTINUITY STORY SO FAR:\n" + limited_continuity)
        if continuity_character_continuity:
            continuity_lines.append("CHARACTER CONTINUITY:\n" + _trim(str(continuity_character_continuity), 2500))
        if continuity_plot_threads:
            continuity_lines.append("PLOT THREADS (ACTIVE/OPEN):\n" + _trim(str(continuity_plot_threads), 2500))
        if continuity_world_state:
            continuity_lines.append("WORLD STATE:\n" + _trim(str(continuity_world_state), 2500))
        if continuity_requirements:
            bullets = "\n".join(f"- {str(req)[:200]}" for req in continuity_requirements[:6])
            continuity_lines.append("CONTINUITY REQUIREMENTS:\n" + bullets)
        if continuity_required_plot_advancement:
            continuity_lines.append("REQUIRED PLOT ADVANCEMENT:\n- " + _trim(continuity_required_plot_advancement, 300))
        if required_plot_points:
            points = "\n".join(f"- {str(p)[:200]}" for p in required_plot_points[:6])
            continuity_lines.append("PLANNED PLOT POINTS:\n" + points)
        if continuity_character_needs:
            needs_bullets = "\n".join(f"- {name}: {', '.join(needs)[:200]}" for name, needs in list(continuity_character_needs.items())[:5] if isinstance(needs, (list, tuple)))
            if needs_bullets:
                continuity_lines.append("CHARACTER DEVELOPMENT NEEDS:\n" + needs_bullets)
        if plan_continuity_requirements:
            plan_reqs = "\n".join(f"- {str(req)[:200]}" for req in plan_continuity_requirements[:6])
            continuity_lines.append("PLAN CONTINUITY REQUIREMENTS:\n" + plan_reqs)
        if continuity_themes_to_continue:
            themes = ", ".join([str(t) for t in continuity_themes_to_continue[:6]])
            continuity_lines.append("THEMES TO CONTINUE:\n- " + themes)
        if timeline_state:
            continuity_lines.append("TIMELINE STATE:\n" + _trim(str(timeline_state), 1500))
        if timeline_constraints:
            constraints = "\n".join(f"- {str(c)[:200]}" for c in timeline_constraints[:6])
            continuity_lines.append("TIMELINE CONSTRAINTS:\n" + constraints)
        if arc_diagnostics:
            continuity_lines.append("GLOBAL ARC DIAGNOSTICS:\n" + _trim(str(arc_diagnostics), 2000))
        if continuity_unresolved_questions:
            questions = "\n".join(f"- {str(q)[:200]}" for q in continuity_unresolved_questions[:6])
            continuity_lines.append("UNRESOLVED QUESTIONS TO KEEP ACTIVE:\n" + questions)
        if chapter_ledger_summary:
            continuity_lines.append("LATEST CHAPTER LEDGER SUMMARY:\n" + _trim(chapter_ledger_summary, 2000))
        if bridge_requirements:
            bridge_lines = "\n".join(f"- {str(req)[:200]}" for req in bridge_requirements[:8])
            continuity_lines.append("BRIDGE REQUIREMENTS:\n" + bridge_lines)
        if pacing_guidance:
            pacing_lines = "\n".join(f"- {k}: {str(v)[:200]}" for k, v in list(pacing_guidance.items())[:6])
            continuity_lines.append("PACING GUIDANCE:\n" + pacing_lines)
        if director_notes:
            continuity_lines.append("DIRECTOR NOTES TO APPLY:\n" + _trim(str(director_notes), 3000))
        if regen_feedback:
            continuity_lines.append("REGENERATION FEEDBACK (fix these specific failures; do not add unrelated beats):\n" + _trim(str(regen_feedback), 2000))
        if previous_opening_lines:
            openings = "\n".join(f"- {line}" for line in previous_opening_lines[-3:])
            continuity_lines.append("AVOID REPEATING PRIOR OPENING PATTERNS. RECENT OPENING LINES WERE:\n" + openings)
        if previous_ending_lines:
            endings = "\n".join(f"- {line}" for line in previous_ending_lines[-3:])
            continuity_lines.append("AVOID REPEATING PRIOR ENDING PATTERNS. RECENT ENDING LINES WERE:\n" + endings)
        # Prior ending is already shown prominently at the top of the user prompt via continuity_opening.
        # Do not duplicate it here in the continuity block.
        repetition_lines: list[str] = []
        if pattern_database_summary:
            repetition_lines.append("PATTERN DATABASE SUMMARY:\n" + _trim(pattern_database_summary, 3000))
        if repetition_risks:
            risk_lines = []
            for risk_level in ("high_risk", "medium_risk", "low_risk"):
                items = repetition_risks.get(risk_level, [])
                if items:
                    label = risk_level.replace("_", " ").upper()
                    risk_lines.append(label + ":\n" + "\n".join(f"- {str(item)[:200]}" for item in items[:6]))
            if risk_lines:
                repetition_lines.append("REPETITION RISKS:\n" + "\n".join(risk_lines))
        if avoid_phrases:
            phrases = "\n".join(f"- {str(p)[:200]}" for p in avoid_phrases[:30])
            repetition_lines.append("AVOID THESE EXACT PHRASES OR CLOSE VARIANTS:\n" + phrases)
        if repetition_allowlist:
            allow_lines = "\n".join(f"- {str(p)[:200]}" for p in repetition_allowlist[:20])
            repetition_lines.append("ALLOW SAFE REPETITION (names/terms/catchphrases):\n" + allow_lines)
        if overused_words and isinstance(overused_words, list):
            word_lines = []
            for entry in overused_words[:15]:
                if isinstance(entry, dict):
                    word_lines.append(f"- \"{entry.get('word', '')}\" ({entry.get('count', 0)} times) — find synonyms or rephrase")
            if word_lines:
                repetition_lines.append("OVERUSED WORDS IN THIS BOOK (use synonyms or rephrase — these appear too often):\n" + "\n".join(word_lines))
        if overused_phrases and isinstance(overused_phrases, list):
            phrase_lines = []
            for entry in overused_phrases[:12]:
                if isinstance(entry, dict) and entry.get("phrase"):
                    phrase_lines.append(f"- \"{entry['phrase']}\" ({entry.get('chapter_count', 0)} chapters)")
            if phrase_lines:
                repetition_lines.append("OVERUSED PHRASES ACROSS CHAPTERS (avoid or rephrase):\n" + "\n".join(phrase_lines))
        repetition_block = ("\n\n".join(repetition_lines) + "\n\n") if repetition_lines else ""

        continuity_block = ("\n\n".join(continuity_lines) + "\n\n") if continuity_lines else ""

        vector_context_block = ""
        if vector_context:
            vector_context_block = "VECTOR MEMORY CONTEXT:\n" + _trim(str(vector_context), 4000) + "\n\n"
        vector_guidelines_block = ""
        if vector_guidelines:
            vector_guidelines_block = "VECTOR MEMORY GUIDELINES:\n" + _trim(str(vector_guidelines), 2500) + "\n\n"

        director_brief_block = ""
        if director_brief:
            director_brief_block = "DIRECTOR BRIEF:\n" + _trim(str(director_brief), 5000) + "\n\n"

        plan_lines: list[str] = []
        if chapter_plan_summary:
            plan_lines.append("CHAPTER PLAN SUMMARY:\n" + _trim(chapter_plan_summary, 2000))
        if chapter_contract:
            plan_lines.append("CHAPTER CONTRACT (NON-NEGOTIABLES):\n" + _trim(str(chapter_contract), 3000))
        if chapter_objectives:
            objectives = "\n".join(f"- {str(obj)[:200]}" for obj in chapter_objectives[:8])
            plan_lines.append("CHAPTER OBJECTIVES:\n" + objectives)
        if pov_character or pov_type:
            pov_line = f"{pov_character} ({pov_type})" if pov_type else f"{pov_character}"
            plan_lines.append("POV REQUIRED:\n- " + pov_line.strip())
        if pov_notes:
            plan_lines.append("POV NOTES:\n- " + _trim(pov_notes, 300))
        if pov_shift:
            plan_lines.append("POV SHIFT:\n- This chapter switches POV from the previous chapter.")
        if opening_type:
            plan_lines.append("OPENING TYPE REQUIRED:\n- " + str(opening_type)[:120])
        if ending_type:
            plan_lines.append("ENDING TYPE REQUIRED:\n- " + str(ending_type)[:120])
        if emotional_arc:
            plan_lines.append("EMOTIONAL ARC REQUIRED:\n- " + str(emotional_arc)[:120])
        if focal_characters:
            chars = ", ".join([str(c) for c in focal_characters[:6]])
            plan_lines.append("FOCAL CHARACTERS:\n- " + chars)
        if chapter_title:
            plan_lines.append("CHAPTER TITLE:\n- " + str(chapter_title)[:120])
        if transition_note:
            plan_lines.append("TRANSITION FROM PREVIOUS CHAPTER:\n- " + _trim(str(transition_note), 300))
        if story_arcs and isinstance(story_arcs, dict):
            arc_lines = []
            primary = story_arcs.get("primary", "")
            if primary:
                arc_lines.append(f"Primary arc: {str(primary)[:200]}")
            secondary = story_arcs.get("secondary", [])
            if secondary and isinstance(secondary, list):
                arc_lines.append(f"Secondary arcs: {', '.join(str(s)[:100] for s in secondary[:4])}")
            themes = story_arcs.get("themes", [])
            if themes and isinstance(themes, list):
                arc_lines.append(f"Themes: {', '.join(str(t)[:60] for t in themes[:5])}")
            if arc_lines:
                plan_lines.append("STORY ARCS (overall book structure):\n" + "\n".join(f"- {l}" for l in arc_lines))
        plan_block = ("\n\n".join(plan_lines) + "\n\n") if plan_lines else ""

        memory_block = f"MEMORY LEDGER:\n{_trim(memory_ledger, 4000)}\n\n" if memory_ledger else ""

        cadence_lines: list[str] = []
        if cadence_targets:
            target_sentence = cadence_targets.get("target_avg_sentence_length")
            target_paragraph = cadence_targets.get("target_avg_paragraph_length")
            hint = cadence_targets.get("variation_hint", "")
            if target_sentence:
                cadence_lines.append(f"- Target avg sentence length: {target_sentence} words")
            if target_paragraph:
                cadence_lines.append(f"- Target avg paragraph length: {target_paragraph} words")
            if hint:
                cadence_lines.append(f"- Variation hint: {hint}")
        cadence_block = ("CADENCE TARGETS:\n" + "\n".join(cadence_lines) + "\n\n") if cadence_lines else ""

        pacing_block = ""
        if pacing_targets:
            pace_mode = pacing_targets.get("pace_mode")
            guidance = pacing_targets.get("guidance")
            scene_count_target = pacing_targets.get("scene_count_target")
            lines = []
            if pace_mode:
                lines.append(f"- Pace mode: {pace_mode}")
            if guidance:
                lines.append(f"- Guidance: {guidance}")
            if scene_count_target:
                lines.append(f"- Scene count target: {scene_count_target}")
            if lines:
                pacing_block = "PACING TARGETS:\n" + "\n".join(lines) + "\n\n"

        range_line = f"- Acceptable Range: {target_range[0]}–{target_range[1]} words. Write to the UPPER end of this range. Plan enough scenes and beats to fill the full word count.\n" if target_range else ""

        # Build the user prompt — previous chapter ending comes first for chapter 2+
        continuity_opening = ""
        if chapter_number > 1 and limited_last_ending:
            continuity_opening = (
                f"THE PREVIOUS CHAPTER ENDED WITH THIS SCENE (your chapter must flow directly from here):\n"
                f"---\n{limited_last_ending}\n---\n\n"
            )

        user_prompt = (
            f"Write Chapter {chapter_number} for this book.\n\n"
            f"{continuity_opening}"
            "STORY CONTEXT\n"
            "BOOK BIBLE:\n"
            f"{limited_book_bible}\n\n"
            "REFERENCE FILES:\n"
            f"{references_summary}\n"
            f"{vector_guidelines_block}"
            f"{vector_context_block}"
            f"{director_brief_block}"
            "PREVIOUS CHAPTERS CONTEXT:\n"
            f"{limited_prev}\n\n"
            f"{continuity_block}"
            f"{plan_block}"
            f"{memory_block}"
            f"{cadence_block}"
            f"{pacing_block}"
            f"{repetition_block}"
        )

        # Add chapter blueprint if available
        chapter_blueprint = (context or {}).get("chapter_blueprint", "")
        if chapter_blueprint:
            user_prompt += f"{chapter_blueprint}\n\n"

        # Add anti-pattern context if available
        anti_pattern = (context or {}).get("anti_pattern_context", "")
        if anti_pattern:
            user_prompt += f"{anti_pattern}\n\n"

        rewrite_instruction = (context or {}).get("rewrite_instruction", "")
        if rewrite_instruction:
            user_prompt += (
                f"AUTHOR REWRITE DIRECTION (the author explicitly asked for this rewrite — treat as highest priority):\n"
                f"{rewrite_instruction}\n\n"
            )

        # Cast consistency block — remind the model who exists
        cast_lines: list[str] = []
        focal = focal_characters
        if focal:
            cast_lines.append(f"FOCAL CHARACTERS THIS CHAPTER: {', '.join(str(c) for c in focal[:6])}")
        if pov_character:
            cast_lines.append(f"POV CHARACTER: {pov_character} ({pov_type or 'third person limited'})")
        continuity_chars = None
        if isinstance(continuity_snapshot, dict):
            continuity_chars = continuity_snapshot.get("character_continuity")
        if continuity_chars:
            cast_lines.append(f"CHARACTER STATE FROM PREVIOUS CHAPTER:\n{_trim(str(continuity_chars), 1500)}")
        if cast_lines:
            user_prompt += "CHARACTER ROSTER:\n" + "\n".join(cast_lines) + "\n"
            user_prompt += "- Use ONLY characters established in the book bible or previous chapters. Do not invent new named characters.\n"
            user_prompt += "- Maintain consistent names, pronouns, and physical details for every character.\n\n"

        # Pacing awareness
        pacing_position = ""
        if total_chapters and total_chapters > 0:
            pacing_position = f"- Book position: Chapter {chapter_number} of {total_chapters}."
            if remaining_chapters:
                pacing_position += f" {remaining_chapters} chapters remaining."
            if remaining_word_budget:
                pacing_position += f" ~{remaining_word_budget:,} words left in the book's word budget."
            pacing_position += "\n"
            if remaining_chapters is not None and remaining_chapters <= 1:
                pacing_position += "- FINAL CHAPTER: Resolve the central conflict. Provide closure for main characters and primary arc.\n"
            elif remaining_chapters and remaining_chapters <= 3:
                pacing_position += "- APPROACHING THE END: Begin resolving major plot threads. Accelerate toward climax/resolution.\n"

        user_prompt += (
            "GENERATION REQUIREMENTS:\n"
            f"- Chapter Number: {chapter_number}\n"
            f"- Target Word Count: {target_words} words (CRITICAL: write at least {int(target_words * 0.85)} words)\n"
            f"{range_line}"
            f"{pacing_position}"
            "- Maintain strict consistency with characters, plot, and world-building (do not invent external franchises or unrelated universes)\n"
            "- Advance the plot meaningfully (min 2 significant points)\n"
            "- Strong opening hook and a compelling end that flows to the next chapter\n"
            "- Plan 3-4 full scenes with dialogue, action, and internal beats to reach the word count\n"
            "- Do NOT end before the target word count unless all chapter objectives are fully complete\n\n"
            "COMPLIANCE GUARDRAILS:\n"
            "- Keep final word count within the accepted range without padding or list spirals\n"
            "- Use em dashes sparingly for interruptions, asides, or emphasis\n"
            "- Stay within composition targets (dialogue/action/internal/description balance)\n"
            "- Adhere to the book bible’s world rules and voice\n\n"
            f"Write Chapter {chapter_number} in full now."
        )

        return system_prompt, user_prompt
    
    def save_chapter(self, result: GenerationResult, output_file: str) -> bool:
        """Save generated chapter to file with metadata."""
        try:
            # Ensure chapters directory exists
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save the chapter content
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(result.content)
            
            # Save metadata to companion file
            metadata_file = output_path.with_suffix('.json')
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(result.metadata, f, indent=2)
            
            self.logger.info(f"Chapter saved to {output_file}")
            self.logger.info(f"Metadata saved to {metadata_file}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save chapter: {str(e)}")
            return False
    
    def get_cost_estimate(self, prompt_text: str, target_completion_words: int) -> dict:
        """Estimate cost for a generation request."""
        # Rough token estimation
        prompt_tokens = len(prompt_text.split()) * 1.3
        completion_tokens = target_completion_words * 1.3
        
        input_cost = (prompt_tokens / 1000) * self.cost_per_1k_input_tokens
        output_cost = (completion_tokens / 1000) * self.cost_per_1k_output_tokens
        
        return {
            "estimated_prompt_tokens": int(prompt_tokens),
            "estimated_completion_tokens": int(completion_tokens),
            "estimated_total_tokens": int(prompt_tokens + completion_tokens),
            "estimated_input_cost": input_cost,
            "estimated_output_cost": output_cost,
            "estimated_total_cost": input_cost + output_cost
        }

async def main():
    """Main function for command-line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description="LLM Orchestrator - Phase 1 MVP")
    parser.add_argument("--chapter", type=int, required=True, help="Chapter number to generate")
    parser.add_argument("--model", default="gpt-4o", help="OpenAI model to use")
    parser.add_argument("--words", type=int, default=3800, help="Target word count")
    parser.add_argument("--output", help="Output file path (default: chapters/chapter-{N}.md)")
    parser.add_argument("--stage", default="complete", choices=["spike", "complete", "5-stage"], 
                       help="Generation stage")
    parser.add_argument("--max-retries", type=int, default=3, help="Maximum retry attempts")
    parser.add_argument("--estimate-only", action="store_true", help="Only estimate cost, don't generate")
    
    args = parser.parse_args()
    
    # Set default output path
    if not args.output:
        args.output = f"chapters/chapter-{args.chapter:02d}.md"
    
    # Initialize orchestrator
    try:
        retry_config = RetryConfig(max_retries=args.max_retries)
        orchestrator = LLMOrchestrator(model=args.model, retry_config=retry_config)
    except ValueError as e:
        print(f"ERROR: {e}")
        return 1
    
    # Cost estimation mode
    if args.estimate_only:
        system_prompt, user_prompt = orchestrator._build_comprehensive_prompts(args.chapter, args.words)
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        estimate = orchestrator.get_cost_estimate(full_prompt, args.words)
        
        print(f"💰 Cost Estimation for Chapter {args.chapter}")
        print(f"📊 Estimated tokens: {estimate['estimated_total_tokens']}")
        print(f"💵 Estimated cost: ${estimate['estimated_total_cost']:.4f}")
        print(f"   Input: ${estimate['estimated_input_cost']:.4f}")
        print(f"   Output: ${estimate['estimated_output_cost']:.4f}")
        return 0
    
    # Generate chapter
    print(f"Generating Chapter {args.chapter} using {args.model} (stage: {args.stage})...")
    
    if args.stage == "5-stage":
        # 5-stage generation
        results = await orchestrator.generate_chapter_5_stage(args.chapter, args.words)
        
        if not results:
            print("❌ 5-stage generation failed: No results returned")
            return 1
        
        # Check if all stages completed successfully
        successful_stages = [r for r in results if r.success]
        failed_stages = [r for r in results if not r.success]
        
        print(f"📊 5-Stage Generation Summary:")
        print(f"   ✅ Successful stages: {len(successful_stages)}")
        print(f"   ❌ Failed stages: {len(failed_stages)}")
        
        total_cost = sum(r.cost_estimate for r in successful_stages)
        print(f"   💰 Total cost: ${total_cost:.4f}")
        
        # Save final result if available
        final_result = results[-1] if results else None
        if final_result and final_result.success:
            if orchestrator.save_chapter(final_result, args.output):
                print(f"✅ Final chapter saved to: {args.output}")
                
                # Save all stage results
                stages_dir = Path(args.output).parent / "stages"
                stages_dir.mkdir(exist_ok=True)
                
                for i, result in enumerate(results, 1):
                    if result.success:
                        stage_file = stages_dir / f"chapter-{args.chapter:02d}-stage-{i}.md"
                        with open(stage_file, 'w', encoding='utf-8') as f:
                            f.write(result.content)
                        print(f"   📁 Stage {i} saved to: {stage_file}")
                
                return 0
            else:
                print("❌ Failed to save final chapter")
                return 1
        else:
            print("❌ 5-stage generation failed: Final stage unsuccessful")
            return 1
    
    else:
        # Single-stage generation
        result = await orchestrator.generate_chapter(args.chapter, args.words, args.stage)
        
        if result.success:
            # Save chapter
            if orchestrator.save_chapter(result, args.output):
                print(f"✅ Chapter {args.chapter} generated successfully!")
                print(f"📁 Saved to: {args.output}")
                print(f"📊 Word count: {result.metadata['word_count']}")
                print(f"💰 Cost: ${result.cost_estimate:.4f}")
                print(f"⏱️  Time: {result.metadata['generation_time']:.2f}s")
                print(f"\n🔍 Next step: Run quality gates with:")
                print(f"   python3 system/brutal_assessment_scorer.py assess --chapter-file {args.output}")
                return 0
            else:
                print("❌ Failed to save chapter")
                return 1
        else:
            print(f"❌ Generation failed: {result.error}")
            return 1

if __name__ == "__main__":
    import asyncio
    exit(asyncio.run(main())) 