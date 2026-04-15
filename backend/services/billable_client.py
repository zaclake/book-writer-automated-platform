#!/usr/bin/env python3
"""
Billable Client Wrappers
Wraps OpenAI and Replicate SDKs to automatically handle credit billing for all AI model calls.
"""

import os
import logging
import asyncio
import time
from typing import Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass
from datetime import datetime, timezone

# AI SDK imports
try:
    import openai
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    openai = None
    OpenAI = None
    _OPENAI_AVAILABLE = False

try:
    import replicate
    _REPLICATE_AVAILABLE = True
except ImportError:
    replicate = None
    _REPLICATE_AVAILABLE = False

# Internal imports
from .pricing_registry import get_pricing_registry
from .credits_service import get_credits_service, InsufficientCreditsError

logger = logging.getLogger(__name__)
_RESPONSES_FALLBACK_LOGGED = False
_DROP_TOOLS_LOGGED = False


def _openai_error_code(err: Exception) -> Optional[str]:
    """Best-effort extraction of OpenAI error code/type."""
    try:
        code = getattr(err, "code", None)
        if code:
            return str(code)
    except Exception:
        pass
    try:
        body = getattr(err, "body", None)
        if isinstance(body, dict):
            inner = body.get("error") if isinstance(body.get("error"), dict) else {}
            code = inner.get("code") or inner.get("type")
            if code:
                return str(code)
    except Exception:
        pass
    try:
        msg = str(err)
        if "insufficient_quota" in msg:
            return "insufficient_quota"
    except Exception:
        pass
    return None


def _is_insufficient_quota(err: Exception) -> bool:
    try:
        code = (_openai_error_code(err) or "").lower().strip()
        if code == "insufficient_quota":
            return True
    except Exception:
        pass
    try:
        msg = str(err).lower()
        return ("insufficient_quota" in msg) or ("exceeded your current quota" in msg) or ("check your plan and billing details" in msg)
    except Exception:
        return False


def _error_blob(err: Exception) -> str:
    parts = []
    try:
        parts.append(str(err))
    except Exception:
        pass
    try:
        parts.append(repr(err))
    except Exception:
        pass
    try:
        args = getattr(err, "args", None)
        if args:
            parts.append(repr(args))
    except Exception:
        pass
    try:
        body = getattr(err, "body", None)
        if isinstance(body, dict):
            import json as _json
            parts.append(_json.dumps(body, ensure_ascii=False, default=str))
        elif isinstance(body, str):
            parts.append(body)
    except Exception:
        pass
    return " | ".join([p for p in parts if isinstance(p, str) and p])


def _is_insufficient_quota_v2(err: Exception) -> bool:
    if _is_insufficient_quota(err):
        return True
    try:
        blob = _error_blob(err).lower()
        return ("insufficient_quota" in blob) or ("exceeded your current quota" in blob) or ("check your plan and billing details" in blob)
    except Exception:
        return False

@dataclass
class BillableResponse:
    """Response from a billable AI service call."""
    response: Any
    credits_charged: int
    raw_cost_usd: float
    transaction_id: Optional[str] = None
    provider: str = None
    model: str = None
    usage_data: Optional[Dict[str, Any]] = None
    calculation_details: Optional[Dict[str, Any]] = None

class CreditsDisabledError(Exception):
    """Raised when credits system is disabled but a billable operation is attempted."""
    pass

class BillableOpenAIClient:
    """
    Billable wrapper for OpenAI client that automatically deducts credits.
    Drop-in replacement for OpenAI client with credit billing.
    """
    
    def __init__(self, user_id: str, api_key: Optional[str] = None, 
                 pricing_registry=None, credits_service=None, 
                 enable_billing: bool = None):
        """
        Initialize billable OpenAI client.
        
        Args:
            user_id: User ID for billing
            api_key: OpenAI API key (defaults to env var)
            pricing_registry: Pricing registry instance
            credits_service: Credits service instance
            enable_billing: Whether to enable billing (defaults to env var)
        """
        self.user_id = user_id
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        
        # Get service instances
        self.pricing_registry = pricing_registry or get_pricing_registry()
        self.credits_service = credits_service or get_credits_service()
        
        # Check if billing is enabled
        enable_billing_env = os.getenv('ENABLE_CREDITS_BILLING', 'false').lower()
        self.billing_enabled = enable_billing if enable_billing is not None else enable_billing_env == 'true'
        
        # Initialize OpenAI client
        if not _OPENAI_AVAILABLE:
            raise RuntimeError("OpenAI library not available. Install with: pip install openai")
        
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY environment variable.")
        
        self.client = OpenAI(api_key=self.api_key)
        
        # Check service availability
        if self.billing_enabled:
            if not self.pricing_registry or not self.pricing_registry.is_available():
                logger.warning("Pricing registry not available - credits billing disabled")
                self.billing_enabled = False
            
            if not self.credits_service or not self.credits_service.is_available():
                logger.warning("Credits service not available - credits billing disabled")
                self.billing_enabled = False
        
        logger.info(f"BillableOpenAIClient initialized for user {user_id}, billing_enabled: {self.billing_enabled}")
    
    async def _bill_for_usage(self, model: str, usage_data: Dict[str, Any], 
                             operation: str) -> Tuple[int, str, Dict[str, Any]]:
        """
        Bill user for AI usage.
        
        Args:
            model: Model name used
            usage_data: Usage data from API response
            operation: Description of operation
            
        Returns:
            Tuple of (credits_charged, transaction_id, calculation_details)
        """
        if not self.billing_enabled:
            return 0, None, {}
        
        try:
            # Calculate credits required
            calculation = self.pricing_registry.calculate_credits('openai', model, usage_data)
            credits_required = calculation.credits
            
            if credits_required <= 0:
                # Expected when pricing is missing or billing is intentionally disabled.
                logger.debug(f"Zero credits calculated for {model} usage: {usage_data}")
                return 0, None, calculation.calculation_details
            
            # Deduct credits
            transaction = await self.credits_service.deduct_credits(
                user_id=self.user_id,
                amount=credits_required,
                reason=f"openai_{operation}",
                meta={
                    'provider': 'openai',
                    'model': model,
                    'operation': operation,
                    'usage': usage_data,
                    'calculation_details': calculation.calculation_details
                }
            )
            
            if not transaction:
                raise RuntimeError("Failed to deduct credits for OpenAI usage")
            
            logger.info(f"Billed {credits_required} credits for {model} {operation} (user: {self.user_id})")
            return credits_required, transaction.txn_id, calculation.calculation_details
            
        except InsufficientCreditsError as e:
            logger.warning(f"Credits limit bypassed for user {self.user_id}: {e}")
            return 0, None, calculation.calculation_details
        except Exception as e:
            logger.error(f"Failed to bill for OpenAI usage: {e}")
            raise RuntimeError(f"Billing failed: {e}")
    
    async def _provisional_bill(self, model: str, estimated_usage: Dict[str, Any],
                              operation: str) -> Optional[str]:
        """
        Create provisional billing for long-running operations.
        
        Returns:
            Transaction ID for provisional debit
        """
        if not self.billing_enabled:
            return None
        
        try:
            # Calculate estimated credits
            calculation = self.pricing_registry.estimate_credits('openai', model, estimated_usage)
            credits_estimated = calculation.credits
            
            if credits_estimated <= 0:
                return None
            
            # Create provisional debit
            transaction = await self.credits_service.provisional_debit(
                user_id=self.user_id,
                amount=credits_estimated,
                reason=f"openai_{operation}_provisional",
                meta={
                    'provider': 'openai',
                    'model': model,
                    'operation': operation,
                    'estimated_usage': estimated_usage,
                    'calculation_details': calculation.calculation_details
                }
            )
            
            if transaction:
                logger.info(f"Created provisional debit of {credits_estimated} credits for {model} {operation}")
                return transaction.txn_id
            
            return None
            
        except InsufficientCreditsError as e:
            logger.warning(f"Credits limit bypassed for provisional billing: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to create provisional billing: {e}")
            return None
    
    async def _finalize_provisional_bill(self, provisional_txn_id: str, model: str,
                                       actual_usage: Dict[str, Any]) -> int:
        """
        Finalize provisional billing with actual usage.
        
        Returns:
            Actual credits charged
        """
        if not self.billing_enabled or not provisional_txn_id:
            return 0
        
        try:
            # Calculate actual credits
            calculation = self.pricing_registry.calculate_credits('openai', model, actual_usage)
            actual_credits = calculation.credits
            
            # Finalize provisional debit
            success = await self.credits_service.finalize_provisional_debit(
                user_id=self.user_id,
                txn_id=provisional_txn_id,
                final_amount=actual_credits
            )
            
            if success:
                logger.info(f"Finalized provisional billing: {actual_credits} credits charged")
                return actual_credits
            else:
                logger.error("Failed to finalize provisional billing")
                return 0
                
        except Exception as e:
            logger.error(f"Failed to finalize provisional billing: {e}")
            # Try to void the provisional debit
            await self.credits_service.void_provisional_debit(
                user_id=self.user_id,
                txn_id=provisional_txn_id,
                reason=f"finalization_failed: {str(e)}"
            )
            return 0
    
    async def _void_provisional_bill(self, provisional_txn_id: str, reason: str = "operation_failed"):
        """Void a provisional billing."""
        if self.billing_enabled and provisional_txn_id:
            await self.credits_service.void_provisional_debit(
                user_id=self.user_id,
                txn_id=provisional_txn_id,
                reason=reason
            )
    
    # Wrapper methods for OpenAI client
    
    async def chat_completions_create(self, **kwargs) -> BillableResponse:
        """
        Create chat completion with automatic billing.
        """
        model = kwargs.pop('model', 'gpt-4o')
        response = None
        usage_data: Dict[str, Any] = {}
        
        try:
            # Make API call
            start_time = time.time()
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=model,
                **kwargs
            )
            duration = time.time() - start_time
            
            # Extract usage data
            usage_data = {
                'prompt_tokens': response.usage.prompt_tokens,
                'completion_tokens': response.usage.completion_tokens,
                'total_tokens': response.usage.total_tokens
            }
            
            # Bill for usage
            credits_charged, txn_id, calc_details = await self._bill_for_usage(
                model=model,
                usage_data=usage_data,
                operation='chat_completion'
            )
            
            logger.info(f"OpenAI chat completion: {usage_data['total_tokens']} tokens, "
                       f"{credits_charged} credits, {duration:.2f}s")
            
            return BillableResponse(
                response=response,
                credits_charged=credits_charged,
                raw_cost_usd=calc_details.get('raw_cost_usd', 0),
                transaction_id=txn_id,
                provider='openai',
                model=model,
                usage_data=usage_data,
                calculation_details=calc_details
            )
            
        except InsufficientCreditsError as e:
            logger.warning(f"Credits limit bypassed for user {self.user_id}: {e}")
            return BillableResponse(
                response=response,
                credits_charged=0,
                raw_cost_usd=0,
                transaction_id=None,
                provider='openai',
                model=model,
                usage_data=usage_data,
                calculation_details={}
            )
        except Exception as e:
            logger.error(f"OpenAI chat completion failed: {e}")
            raise

    async def responses_create(self, **kwargs) -> BillableResponse:
        """
        Create a Responses API call with automatic billing.
        """
        model = kwargs.pop('model', 'gpt-4o')
        response = None
        usage_data: Dict[str, Any] = {}

        try:
            if not hasattr(self.client, "responses"):
                if os.getenv("REQUIRE_OPENAI_RESPONSES", "false").lower() == "true":
                    raise RuntimeError("OpenAI Responses API required but not available in client runtime.")
                global _RESPONSES_FALLBACK_LOGGED
                if not _RESPONSES_FALLBACK_LOGGED:
                    logger.warning("Responses API unavailable; falling back to chat completions")
                    _RESPONSES_FALLBACK_LOGGED = True
                input_messages = kwargs.pop("input", None)
                if input_messages is None:
                    input_messages = kwargs.pop("messages", None)
                if input_messages is None:
                    raise ValueError("Responses fallback requires input or messages")
                if isinstance(input_messages, str):
                    input_messages = [{"role": "user", "content": input_messages}]
                elif isinstance(input_messages, list):
                    if not input_messages:
                        raise ValueError("Responses fallback requires non-empty messages")
                    if not (isinstance(input_messages[0], dict) and "role" in input_messages[0]):
                        import json as _json
                        input_messages = [{"role": "user", "content": _json.dumps(input_messages)}]
                else:
                    import json as _json
                    input_messages = [{"role": "user", "content": _json.dumps(input_messages)}]
                kwargs.pop("model", None)
                if "tools" in kwargs:
                    global _DROP_TOOLS_LOGGED
                    if not _DROP_TOOLS_LOGGED:
                        logger.warning("Dropping tools for chat-completions fallback")
                        _DROP_TOOLS_LOGGED = True
                    kwargs.pop("tools", None)
                max_output_tokens = kwargs.pop("max_output_tokens", None)
                if max_output_tokens is not None and "max_tokens" not in kwargs:
                    kwargs["max_tokens"] = max_output_tokens
                kwargs.pop("messages", None)
                kwargs.pop("model", None)
                return await self.chat_completions_create(
                    model=model,
                    messages=input_messages,
                    **kwargs
                )

            for key in ("frequency_penalty", "presence_penalty", "temperature", "top_p"):
                kwargs.pop(key, None)
            start_time = time.time()
            response = await asyncio.to_thread(
                self.client.responses.create,
                model=model,
                **kwargs
            )
            duration = time.time() - start_time

            usage = getattr(response, 'usage', None)
            prompt_tokens = getattr(usage, 'prompt_tokens', None)
            completion_tokens = getattr(usage, 'completion_tokens', None)
            total_tokens = getattr(usage, 'total_tokens', None)

            if prompt_tokens is None and usage is not None:
                prompt_tokens = getattr(usage, 'input_tokens', 0)
                completion_tokens = getattr(usage, 'output_tokens', 0)
                total_tokens = getattr(usage, 'total_tokens', (prompt_tokens or 0) + (completion_tokens or 0))

            usage_data = {
                'prompt_tokens': prompt_tokens or 0,
                'completion_tokens': completion_tokens or 0,
                'total_tokens': total_tokens or 0
            }

            credits_charged, txn_id, calc_details = await self._bill_for_usage(
                model=model,
                usage_data=usage_data,
                operation='responses'
            )

            logger.info(f"OpenAI responses call: {usage_data['total_tokens']} tokens, "
                        f"{credits_charged} credits, {duration:.2f}s")

            return BillableResponse(
                response=response,
                credits_charged=credits_charged,
                raw_cost_usd=calc_details.get('raw_cost_usd', 0),
                transaction_id=txn_id,
                provider='openai',
                model=model,
                usage_data=usage_data,
                calculation_details=calc_details
            )

        except InsufficientCreditsError as e:
            logger.warning(f"Credits limit bypassed for user {self.user_id}: {e}")
            return BillableResponse(
                response=response,
                credits_charged=0,
                raw_cost_usd=0,
                transaction_id=None,
                provider='openai',
                model=model,
                usage_data=usage_data,
                calculation_details={}
            )
        except Exception as e:
            if _is_insufficient_quota_v2(e):
                logger.warning(
                    "OpenAI responses call failed (quota/billing). "
                    f"quota_fail_fast=v2 code={_openai_error_code(e)} err={type(e).__name__}: {e}"
                )
            else:
                logger.error(f"OpenAI responses call failed: {e}")
            raise
    
    async def images_generate(self, **kwargs) -> BillableResponse:
        """
        Generate images with automatic billing.
        """
        model = kwargs.get('model', 'gpt-image-1')
        n_images = kwargs.get('n', 1)
        
        try:
            # Make API call
            start_time = time.time()
            response = await asyncio.to_thread(
                self.client.images.generate,
                **kwargs
            )
            duration = time.time() - start_time
            
            # Usage data for image generation
            usage_data = {
                'job_count': n_images,
                'model': model,
                'size': kwargs.get('size', '1024x1024'),
                'quality': kwargs.get('quality', 'standard')
            }
            
            # Bill for usage
            credits_charged, txn_id, calc_details = await self._bill_for_usage(
                model=model,
                usage_data=usage_data,
                operation='image_generation'
            )
            
            logger.info(f"OpenAI image generation: {n_images} image(s), "
                       f"{credits_charged} credits, {duration:.2f}s")
            
            return BillableResponse(
                response=response,
                credits_charged=credits_charged,
                raw_cost_usd=calc_details.get('raw_cost_usd', 0),
                transaction_id=txn_id,
                provider='openai',
                model=model,
                usage_data=usage_data,
                calculation_details=calc_details
            )
            
        except InsufficientCreditsError as e:
            logger.warning(f"Credits limit bypassed for image generation: {e}")
            return BillableResponse(
                response=response,
                credits_charged=0,
                raw_cost_usd=0,
                transaction_id=None,
                provider='openai',
                model=model,
                usage_data=usage_data,
                calculation_details={}
            )
        except Exception as e:
            logger.error(f"OpenAI image generation failed: {e}")
            raise
    
    # Convenience properties for compatibility
    @property
    def chat(self):
        """Provide access to chat completions."""
        class ChatCompletions:
            def __init__(self, billable_client):
                self.billable_client = billable_client
            
            async def create(self, **kwargs):
                return await self.billable_client.chat_completions_create(**kwargs)
            
            def completions(self):
                return self
        
        return ChatCompletions(self)
    
    @property
    def images(self):
        """Provide access to image generation."""
        class Images:
            def __init__(self, billable_client):
                self.billable_client = billable_client
                
            async def generate(self, **kwargs):
                return await self.billable_client.images_generate(**kwargs)
        
        return Images(self)

class BillableReplicateClient:
    """
    Billable wrapper for Replicate client that automatically deducts credits.
    """
    
    def __init__(self, user_id: str, api_token: Optional[str] = None,
                 pricing_registry=None, credits_service=None,
                 enable_billing: bool = None):
        """Initialize billable Replicate client."""
        self.user_id = user_id
        self.api_token = api_token or os.getenv('REPLICATE_API_TOKEN')
        
        # Get service instances
        self.pricing_registry = pricing_registry or get_pricing_registry()
        self.credits_service = credits_service or get_credits_service()
        
        # Check if billing is enabled
        enable_billing_env = os.getenv('ENABLE_CREDITS_BILLING', 'false').lower()
        self.billing_enabled = enable_billing if enable_billing is not None else enable_billing_env == 'true'
        
        # Initialize Replicate client
        if not _REPLICATE_AVAILABLE:
            raise RuntimeError("Replicate library not available. Install with: pip install replicate")
        
        if self.api_token:
            replicate.Client(api_token=self.api_token)
        else:
            logger.warning("Replicate API token not found")
        
        # Check service availability
        if self.billing_enabled:
            if not self.pricing_registry or not self.pricing_registry.is_available():
                logger.warning("Pricing registry not available - credits billing disabled")
                self.billing_enabled = False
            
            if not self.credits_service or not self.credits_service.is_available():
                logger.warning("Credits service not available - credits billing disabled")
                self.billing_enabled = False
        
        logger.info(f"BillableReplicateClient initialized for user {user_id}, billing_enabled: {self.billing_enabled}")
    
    async def run(self, model: str, input_data: Dict[str, Any]) -> BillableResponse:
        """
        Run Replicate model with automatic billing.
        """
        try:
            # Make API call
            start_time = time.time()
            output = replicate.run(model, input=input_data)
            duration = time.time() - start_time
            
            # Usage data (assuming one job per run)
            usage_data = {
                'job_count': 1,
                'model': model,
                'input': input_data
            }
            
            # Bill for usage if enabled
            credits_charged = 0
            txn_id = None
            calc_details = {}
            
            if self.billing_enabled:
                calculation = self.pricing_registry.calculate_credits('replicate', model, usage_data)
                credits_required = calculation.credits
                
                if credits_required > 0:
                    transaction = await self.credits_service.deduct_credits(
                        user_id=self.user_id,
                        amount=credits_required,
                        reason=f"replicate_run",
                        meta={
                            'provider': 'replicate',
                            'model': model,
                            'operation': 'run',
                            'usage': usage_data,
                            'calculation_details': calculation.calculation_details
                        }
                    )
                    
                    if transaction:
                        credits_charged = credits_required
                        txn_id = transaction.txn_id
                        calc_details = calculation.calculation_details
            
            logger.info(f"Replicate run: {model}, {credits_charged} credits, {duration:.2f}s")
            
            return BillableResponse(
                response=output,
                credits_charged=credits_charged,
                raw_cost_usd=calc_details.get('raw_cost_usd', 0),
                transaction_id=txn_id,
                provider='replicate',
                model=model,
                usage_data=usage_data,
                calculation_details=calc_details
            )
            
        except InsufficientCreditsError as e:
            logger.warning(f"Credits limit bypassed for Replicate operation: {e}")
            return BillableResponse(
                response=output,
                credits_charged=0,
                raw_cost_usd=0,
                transaction_id=None,
                provider='replicate',
                model=model,
                usage_data=usage_data,
                calculation_details={}
            )
        except Exception as e:
            logger.error(f"Replicate run failed: {e}")
            raise

# Factory functions for creating billable clients

def create_billable_openai_client(user_id: str, **kwargs) -> BillableOpenAIClient:
    """Create a billable OpenAI client for a user."""
    return BillableOpenAIClient(user_id=user_id, **kwargs)

def create_billable_replicate_client(user_id: str, **kwargs) -> BillableReplicateClient:
    """Create a billable Replicate client for a user.""" 
    return BillableReplicateClient(user_id=user_id, **kwargs)

# Utility functions

async def estimate_credits_for_chat(user_id: str, model: str, prompt_text: str, 
                                  max_tokens: int = 4000) -> Dict[str, Any]:
    """
    Estimate credits required for a chat completion.
    
    Returns:
        Dictionary with estimated credits and cost breakdown
    """
    pricing_registry = get_pricing_registry()
    if not pricing_registry:
        return {"error": "Pricing registry not available"}
    
    # Rough token estimation (1.3 tokens per word)
    prompt_tokens = len(prompt_text.split()) * 1.3
    estimated_completion_tokens = max_tokens
    
    estimated_usage = {
        'prompt_tokens': int(prompt_tokens),
        'completion_tokens': estimated_completion_tokens,
        'total_tokens': int(prompt_tokens + estimated_completion_tokens)
    }
    
    calculation = pricing_registry.estimate_credits('openai', model, estimated_usage)
    
    return {
        'estimated_credits': calculation.credits,
        'estimated_cost_usd': calculation.raw_cost_usd,
        'markup_applied': calculation.markup_applied,
        'estimated_usage': estimated_usage,
        'calculation_details': calculation.calculation_details
    }

async def estimate_credits_for_image(user_id: str, model: str = 'gpt-image-1', 
                                   count: int = 1) -> Dict[str, Any]:
    """
    Estimate credits required for image generation.
    
    Returns:
        Dictionary with estimated credits and cost breakdown
    """
    pricing_registry = get_pricing_registry()
    if not pricing_registry:
        return {"error": "Pricing registry not available"}
    
    estimated_usage = {
        'job_count': count,
        'model': model
    }
    
    calculation = pricing_registry.estimate_credits('openai', model, estimated_usage)
    
    return {
        'estimated_credits': calculation.credits,
        'estimated_cost_usd': calculation.raw_cost_usd,
        'markup_applied': calculation.markup_applied,
        'estimated_usage': estimated_usage,
        'calculation_details': calculation.calculation_details
    }