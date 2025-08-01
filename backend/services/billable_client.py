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
                logger.warning(f"Zero credits calculated for {model} usage: {usage_data}")
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
            logger.error(f"Insufficient credits for user {self.user_id}: {e}")
            raise
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
            logger.error(f"Insufficient credits for provisional billing: {e}")
            raise
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
        model = kwargs.get('model', 'gpt-4o')
        
        try:
            # Make API call
            start_time = time.time()
            response = self.client.chat.completions.create(**kwargs)
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
            
        except InsufficientCreditsError:
            # Re-raise as HTTP 402 compatible error
            from fastapi import HTTPException
            raise HTTPException(status_code=402, detail={
                "error": "INSUFFICIENT_CREDITS",
                "message": "Insufficient credits for this operation",
                "user_id": self.user_id
            })
        except Exception as e:
            logger.error(f"OpenAI chat completion failed: {e}")
            raise
    
    async def images_generate(self, **kwargs) -> BillableResponse:
        """
        Generate images with automatic billing.
        """
        model = kwargs.get('model', 'dall-e-3')
        n_images = kwargs.get('n', 1)
        
        try:
            # Make API call
            start_time = time.time()
            response = self.client.images.generate(**kwargs)
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
            
        except InsufficientCreditsError:
            from fastapi import HTTPException
            raise HTTPException(status_code=402, detail={
                "error": "INSUFFICIENT_CREDITS",
                "message": "Insufficient credits for image generation",
                "user_id": self.user_id
            })
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
            
        except InsufficientCreditsError:
            from fastapi import HTTPException
            raise HTTPException(status_code=402, detail={
                "error": "INSUFFICIENT_CREDITS",
                "message": "Insufficient credits for Replicate operation",
                "user_id": self.user_id
            })
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

async def estimate_credits_for_image(user_id: str, model: str = 'dall-e-3', 
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