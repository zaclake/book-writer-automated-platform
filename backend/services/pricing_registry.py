#!/usr/bin/env python3
"""
Pricing Registry Service
Manages model pricing data and credit conversion with intelligent caching and auto-refresh.
"""

import os
import json
import logging
import asyncio
import time
import math
from datetime import datetime, timezone
from typing import Dict, Optional, Any, Tuple
from dataclasses import dataclass
from threading import Lock

logger = logging.getLogger(__name__)

@dataclass
class ModelPricing:
    """Model pricing information."""
    provider: str
    model: str
    input_usd_per_1k: Optional[float] = None
    output_usd_per_1k: Optional[float] = None
    job_usd: Optional[float] = None  # For flat-rate models like DALL-E
    last_updated: Optional[datetime] = None

@dataclass
class CreditCalculation:
    """Credit calculation result."""
    credits: int
    raw_cost_usd: float
    markup_applied: float
    calculation_details: Dict[str, Any]

class PricingRegistry:
    """
    Centralized pricing registry that loads model costs and markup rules from Firestore.
    Provides thread-safe caching with automatic refresh and cost→credit conversion.
    """
    
    def __init__(self, firestore_service=None):
        """Initialize the pricing registry."""
        self.firestore_service = firestore_service
        self._pricing_cache: Dict[str, ModelPricing] = {}
        self._markup_rules: Dict[str, float] = {}
        self._cache_lock = Lock()
        self._last_refresh = 0
        self._refresh_interval = 300  # 5 minutes
        self._available = False
        
        # Default fallback values (can be overridden by Firestore)
        self._default_markup = float(os.getenv('CREDITS_MARKUP', '5.0'))
        self._default_pricing = {
            'openai': {
                'gpt-4o': ModelPricing('openai', 'gpt-4o', 0.005, 0.015),
                'gpt-4o-mini': ModelPricing('openai', 'gpt-4o-mini', 0.00015, 0.0006),
                'gpt-4-turbo': ModelPricing('openai', 'gpt-4-turbo', 0.01, 0.03),
                'dall-e-3': ModelPricing('openai', 'dall-e-3', job_usd=0.04),  # Standard quality
                'dall-e-2': ModelPricing('openai', 'dall-e-2', job_usd=0.02)
            },
            'replicate': {
                'stable-diffusion-3': ModelPricing('replicate', 'stable-diffusion-3', job_usd=0.02)
            }
        }
        
        # Initialize with defaults
        self._load_defaults()
        
        # Try to load from Firestore
        if self.firestore_service and self.firestore_service.available:
            asyncio.create_task(self._initial_load())
        else:
            logger.warning("Firestore not available, using default pricing")
    
    def _load_defaults(self):
        """Load default pricing into cache."""
        with self._cache_lock:
            self._pricing_cache.clear()
            for provider, models in self._default_pricing.items():
                for model_name, pricing in models.items():
                    cache_key = f"{provider}:{model_name}"
                    self._pricing_cache[cache_key] = pricing
            
            # Default markup rules
            self._markup_rules = {
                'default': self._default_markup,
                'openai': self._default_markup,
                'replicate': self._default_markup
            }
            
            self._available = True
            logger.info(f"Loaded default pricing for {len(self._pricing_cache)} models")
    
    async def _initial_load(self):
        """Initial load from Firestore."""
        try:
            await self._refresh_from_firestore()
            logger.info("Successfully loaded pricing from Firestore")
        except Exception as e:
            logger.error(f"Failed to load pricing from Firestore: {e}")
            logger.info("Using default pricing values")
    
    async def _refresh_from_firestore(self):
        """Refresh pricing data from Firestore."""
        if not self.firestore_service or not self.firestore_service.available:
            return
        
        try:
            # Load model pricing document
            pricing_doc = await self._get_firestore_doc('system', 'model_pricing')
            markup_doc = await self._get_firestore_doc('system', 'markup_rules')
            
            if pricing_doc:
                await self._update_pricing_cache(pricing_doc)
            
            if markup_doc:
                await self._update_markup_cache(markup_doc)
            
            self._last_refresh = time.time()
            
        except Exception as e:
            logger.error(f"Failed to refresh pricing from Firestore: {e}")
    
    async def _get_firestore_doc(self, collection: str, document: str) -> Optional[Dict[str, Any]]:
        """Get a document from Firestore."""
        try:
            if not self.firestore_service.db:
                return None
                
            doc_ref = self.firestore_service.db.collection(collection).document(document)
            doc = await asyncio.get_event_loop().run_in_executor(None, doc_ref.get)
            
            if doc.exists:
                return doc.to_dict()
            return None
            
        except Exception as e:
            logger.error(f"Failed to get Firestore document {collection}/{document}: {e}")
            return None
    
    async def _update_pricing_cache(self, pricing_data: Dict[str, Any]):
        """Update pricing cache from Firestore data."""
        with self._cache_lock:
            schema_version = pricing_data.get('schema_version', '1.0')
            updated_at = pricing_data.get('updated_at')
            
            # Support both 'models' and 'providers' keys for backward compatibility
            providers_data = pricing_data.get('models') or pricing_data.get('providers', {})
            
            if providers_data:
                for provider, models in providers_data.items():
                    for model_name, model_data in models.items():
                        cache_key = f"{provider}:{model_name}"
                        
                        pricing = ModelPricing(
                            provider=provider,
                            model=model_name,
                            input_usd_per_1k=model_data.get('input_usd_per_1k'),
                            output_usd_per_1k=model_data.get('output_usd_per_1k'),
                            job_usd=model_data.get('job_usd'),
                            last_updated=updated_at
                        )
                        
                        self._pricing_cache[cache_key] = pricing
            
            logger.info(f"Updated pricing cache with {len(providers_data)} providers (schema v{schema_version})")
    
    async def _update_markup_cache(self, markup_data: Dict[str, Any]):
        """Update markup cache from Firestore data."""
        with self._cache_lock:
            if 'rules' in markup_data:
                self._markup_rules.update(markup_data['rules'])
            
            logger.info(f"Updated markup rules: {self._markup_rules}")
    
    async def _ensure_fresh_cache(self):
        """Ensure cache is fresh, refresh if needed."""
        current_time = time.time()
        if current_time - self._last_refresh > self._refresh_interval:
            await self._refresh_from_firestore()
    
    def is_available(self) -> bool:
        """Check if pricing registry is available."""
        return self._available
    
    def get_model_pricing(self, provider: str, model: str) -> Optional[ModelPricing]:
        """Get pricing for a specific model."""
        cache_key = f"{provider}:{model}"
        
        with self._cache_lock:
            return self._pricing_cache.get(cache_key)
    
    def get_markup_multiplier(self, provider: str = None) -> float:
        """Get markup multiplier for a provider."""
        with self._cache_lock:
            if provider and provider in self._markup_rules:
                return self._markup_rules[provider]
            return self._markup_rules.get('default', self._default_markup)
    
    def calculate_cost(self, provider: str, model: str, usage: Dict[str, Any]) -> float:
        """
        Calculate raw USD cost for model usage.
        
        Args:
            provider: Provider name (openai, replicate, etc.)
            model: Model name
            usage: Usage data with keys like prompt_tokens, completion_tokens, or job_count
            
        Returns:
            Raw cost in USD
        """
        pricing = self.get_model_pricing(provider, model)
        if not pricing:
            logger.error(f"No pricing found for {provider}:{model}")
            return 0.0
        
        try:
            # Token-based pricing (OpenAI chat models)
            if pricing.input_usd_per_1k is not None and pricing.output_usd_per_1k is not None:
                input_tokens = usage.get('prompt_tokens', 0)
                output_tokens = usage.get('completion_tokens', 0)
                
                input_cost = (input_tokens / 1000) * pricing.input_usd_per_1k
                output_cost = (output_tokens / 1000) * pricing.output_usd_per_1k
                
                return input_cost + output_cost
            
            # Job-based pricing (DALL-E, Replicate)
            elif pricing.job_usd is not None:
                job_count = usage.get('job_count', 1)
                return job_count * pricing.job_usd
            
            else:
                logger.error(f"Invalid pricing configuration for {provider}:{model}")
                return 0.0
                
        except Exception as e:
            logger.error(f"Failed to calculate cost for {provider}:{model}: {e}")
            return 0.0
    
    def calculate_credits(self, provider: str, model: str, usage: Dict[str, Any]) -> CreditCalculation:
        """
        Calculate credits required for model usage.
        
        Args:
            provider: Provider name
            model: Model name  
            usage: Usage data
            
        Returns:
            CreditCalculation with credits and breakdown
        """
        # Calculate raw cost
        raw_cost = self.calculate_cost(provider, model, usage)
        markup = self.get_markup_multiplier(provider)
        
        # Apply markup and convert to credits
        marked_up_cost = raw_cost * markup
        credits = math.ceil(marked_up_cost * 100)  # 1 credit = $0.01
        
        calculation_details = {
            'provider': provider,
            'model': model,
            'usage': usage,
            'raw_cost_usd': raw_cost,
            'markup_multiplier': markup,
            'marked_up_cost_usd': marked_up_cost,
            'credit_conversion_rate': 100,  # credits per dollar
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        return CreditCalculation(
            credits=credits,
            raw_cost_usd=raw_cost,
            markup_applied=markup,
            calculation_details=calculation_details
        )
    
    def estimate_credits(self, provider: str, model: str, estimated_usage: Dict[str, Any]) -> CreditCalculation:
        """
        Estimate credits for planned model usage.
        Same as calculate_credits but with 'estimated_' prefix in details.
        """
        calculation = self.calculate_credits(provider, model, estimated_usage)
        calculation.calculation_details['is_estimate'] = True
        calculation.calculation_details['estimated_usage'] = estimated_usage
        return calculation
    
    async def create_pricing_document_template(self) -> Dict[str, Any]:
        """Create a template for the Firestore pricing document."""
        return {
            'schema_version': '1.0',
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc),
            'description': 'Model pricing configuration for credit calculation',
            'models': {
                'openai': {
                    'gpt-4o': {
                        'input_usd_per_1k': 0.005,
                        'output_usd_per_1k': 0.015,
                        'description': 'GPT-4o standard pricing'
                    },
                    'gpt-4o-mini': {
                        'input_usd_per_1k': 0.00015,
                        'output_usd_per_1k': 0.0006,
                        'description': 'GPT-4o mini pricing'
                    },
                    'dall-e-3': {
                        'job_usd': 0.04,
                        'description': 'DALL-E 3 standard quality 1024x1024'
                    }
                },
                'replicate': {
                    'stable-diffusion-3': {
                        'job_usd': 0.02,
                        'description': 'Stable Diffusion 3 image generation'
                    }
                }
            }
        }
    
    async def create_markup_document_template(self) -> Dict[str, Any]:
        """Create a template for the Firestore markup rules document."""
        return {
            'schema_version': '1.0',
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc),
            'description': 'Credit markup rules for revenue calculation',
            'rules': {
                'default': 5.0,
                'openai': 5.0,
                'replicate': 5.0,
                'image_generation': 5.0
            },
            'notes': {
                'default': '5x markup provides $0.05 revenue per $0.01 raw cost',
                'calculation': '1 credit = $0.01 user value = $0.002 raw cost at 5x markup'
            }
        }
    
    async def initialize_firestore_documents(self):
        """Initialize pricing documents in Firestore if they don't exist."""
        if not self.firestore_service or not self.firestore_service.available:
            logger.warning("Cannot initialize Firestore documents - Firestore not available")
            return False
        
        try:
            # Check if documents exist
            pricing_doc = await self._get_firestore_doc('system', 'model_pricing')
            markup_doc = await self._get_firestore_doc('system', 'markup_rules')
            
            # Create pricing document if it doesn't exist
            if not pricing_doc:
                template = await self.create_pricing_document_template()
                doc_ref = self.firestore_service.db.collection('system').document('model_pricing')
                await asyncio.get_event_loop().run_in_executor(None, doc_ref.set, template)
                logger.info("Created model_pricing document in Firestore")
            
            # Create markup document if it doesn't exist
            if not markup_doc:
                template = await self.create_markup_document_template()
                doc_ref = self.firestore_service.db.collection('system').document('markup_rules')
                await asyncio.get_event_loop().run_in_executor(None, doc_ref.set, template)
                logger.info("Created markup_rules document in Firestore")
            
            # Refresh cache from newly created documents
            await self._refresh_from_firestore()
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Firestore documents: {e}")
            return False
    
    async def update_model_pricing(self, provider: str, model: str, pricing_data: Dict[str, Any]) -> bool:
        """Update pricing for a specific model in Firestore."""
        if not self.firestore_service or not self.firestore_service.available:
            return False
        
        try:
            doc_ref = self.firestore_service.db.collection('system').document('model_pricing')
            
            # Update specific model pricing
            update_path = f"models.{provider}.{model}"
            pricing_data['updated_at'] = datetime.now(timezone.utc)
            
            await asyncio.get_event_loop().run_in_executor(
                None, 
                doc_ref.update, 
                {update_path: pricing_data, 'updated_at': datetime.now(timezone.utc)}
            )
            
            # Refresh cache
            await self._refresh_from_firestore()
            
            logger.info(f"Updated pricing for {provider}:{model}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update model pricing: {e}")
            return False
    
    async def update_markup_rule(self, provider: str, markup: float) -> bool:
        """Update markup rule for a provider in Firestore."""
        if not self.firestore_service or not self.firestore_service.available:
            return False
        
        try:
            doc_ref = self.firestore_service.db.collection('system').document('markup_rules')
            
            await asyncio.get_event_loop().run_in_executor(
                None,
                doc_ref.update,
                {
                    f'rules.{provider}': markup,
                    'updated_at': datetime.now(timezone.utc)
                }
            )
            
            # Refresh cache
            await self._refresh_from_firestore()
            
            logger.info(f"Updated markup rule for {provider}: {markup}x")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update markup rule: {e}")
            return False

# Global instance
_pricing_registry: Optional[PricingRegistry] = None

def get_pricing_registry(firestore_service=None) -> PricingRegistry:
    """Get or create the global pricing registry instance."""
    global _pricing_registry
    
    if _pricing_registry is None:
        _pricing_registry = PricingRegistry(firestore_service)
    
    return _pricing_registry

def initialize_pricing_registry(firestore_service):
    """Initialize the global pricing registry with Firestore service."""
    global _pricing_registry
    _pricing_registry = PricingRegistry(firestore_service)
    return _pricing_registry