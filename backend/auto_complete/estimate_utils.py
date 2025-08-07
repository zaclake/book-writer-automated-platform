#!/usr/bin/env python3
"""
Auto-Complete Estimation Utilities
Provides credit-based cost estimation for auto-complete book generation.
"""

import logging
import math
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

def estimate_chapter_credits(
    words_per_chapter: int, 
    quality_threshold: float, 
    model: str = 'gpt-4o',
    pricing_registry=None
) -> Dict[str, Any]:
    """
    Estimate credits required for generating a single chapter.
    
    Args:
        words_per_chapter: Target word count for the chapter
        quality_threshold: Quality threshold (0.0 to 10.0)
        model: AI model to use for generation
        pricing_registry: PricingRegistry instance (will get global if None)
        
    Returns:
        Dict with credits, raw_cost_usd, and calculation details
    """
    try:
        # Get pricing registry if not provided
        if pricing_registry is None:
            from backend.services.pricing_registry import get_pricing_registry
            pricing_registry = get_pricing_registry()
        
        if not pricing_registry or not pricing_registry.is_available():
            logger.error("Pricing registry not available for credit estimation")
            return {
                'credits': 0,
                'raw_cost_usd': 0.0,
                'error': 'Pricing service unavailable'
            }
        
        # Estimate token usage based on word count
        # Rule of thumb: 1.3 tokens per word for input, varies for output
        base_input_tokens = int(words_per_chapter * 1.3)
        
        # Output tokens estimate (chapter content generation)
        # Assume we generate roughly the target word count
        base_output_tokens = int(words_per_chapter * 1.3)
        
        # Apply quality and complexity multipliers
        quality_multiplier = _get_quality_multiplier(quality_threshold)
        retry_multiplier = _get_retry_multiplier(quality_threshold)
        
        # Total estimated tokens with multipliers
        estimated_input_tokens = int(base_input_tokens * quality_multiplier)
        estimated_output_tokens = int(base_output_tokens * quality_multiplier * retry_multiplier)
        
        # Create usage data for pricing calculation
        usage_data = {
            'prompt_tokens': estimated_input_tokens,
            'completion_tokens': estimated_output_tokens,
            'total_tokens': estimated_input_tokens + estimated_output_tokens
        }
        
        # Calculate credits using pricing registry
        credit_calculation = pricing_registry.estimate_credits('openai', model, usage_data)
        
        calculation_details = {
            'words_per_chapter': words_per_chapter,
            'quality_threshold': quality_threshold,
            'model': model,
            'base_input_tokens': base_input_tokens,
            'base_output_tokens': base_output_tokens,
            'quality_multiplier': quality_multiplier,
            'retry_multiplier': retry_multiplier,
            'estimated_input_tokens': estimated_input_tokens,
            'estimated_output_tokens': estimated_output_tokens,
            'total_tokens': usage_data['total_tokens'],
            'pricing_calculation': credit_calculation.calculation_details
        }
        
        return {
            'credits': credit_calculation.credits,
            'raw_cost_usd': credit_calculation.raw_cost_usd,
            'markup_applied': credit_calculation.markup_applied,
            'calculation_details': calculation_details
        }
        
    except Exception as e:
        logger.error(f"Failed to estimate chapter credits: {e}")
        return {
            'credits': 0,
            'raw_cost_usd': 0.0,
            'error': f'Estimation failed: {str(e)}'
        }

def estimate_auto_complete_credits(
    total_chapters: int,
    words_per_chapter: int,
    quality_threshold: float,
    model: str = 'gpt-4o',
    pricing_registry=None
) -> Dict[str, Any]:
    """
    Estimate total credits for auto-completing a book.
    
    Args:
        total_chapters: Number of chapters to generate
        words_per_chapter: Target words per chapter
        quality_threshold: Quality threshold (0.0 to 10.0)
        model: AI model to use
        pricing_registry: PricingRegistry instance (optional)
        
    Returns:
        Dict with total estimation details
    """
    try:
        # Estimate single chapter
        chapter_estimate = estimate_chapter_credits(
            words_per_chapter=words_per_chapter,
            quality_threshold=quality_threshold,
            model=model,
            pricing_registry=pricing_registry
        )
        
        if 'error' in chapter_estimate:
            return chapter_estimate
        
        # Calculate totals
        credits_per_chapter = chapter_estimate['credits']
        total_credits = credits_per_chapter * total_chapters
        total_words = words_per_chapter * total_chapters
        
        # Add some overhead for initial setup and finalization (5%)
        overhead_credits = math.ceil(total_credits * 0.05)
        total_credits_with_overhead = total_credits + overhead_credits
        
        return {
            'total_chapters': total_chapters,
            'total_words': total_words,
            'words_per_chapter': words_per_chapter,
            'quality_threshold': quality_threshold,
            'estimated_total_credits': total_credits_with_overhead,
            'credits_per_chapter': credits_per_chapter,
            'base_credits': total_credits,
            'overhead_credits': overhead_credits,
            'model': model,
            'calculation_details': {
                'chapter_estimate': chapter_estimate,
                'overhead_percentage': 5.0,
                'total_raw_cost_usd': chapter_estimate['raw_cost_usd'] * total_chapters,
                'markup_applied': chapter_estimate['markup_applied']
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to estimate auto-complete credits: {e}")
        return {
            'error': f'Auto-complete estimation failed: {str(e)}',
            'total_chapters': total_chapters,
            'total_words': words_per_chapter * total_chapters,
            'estimated_total_credits': 0
        }

def _get_quality_multiplier(quality_threshold: float) -> float:
    """
    Get quality multiplier based on threshold.
    Higher quality requires more complex prompts and context.
    """
    if quality_threshold >= 9.0:
        return 2.5  # Extremely high quality
    elif quality_threshold >= 8.0:
        return 2.0  # High quality
    elif quality_threshold >= 7.0:
        return 1.7  # Good quality
    elif quality_threshold >= 6.0:
        return 1.4  # Standard quality
    else:
        return 1.2  # Basic quality

def _get_retry_multiplier(quality_threshold: float) -> float:
    """
    Get retry multiplier based on quality threshold.
    Higher quality may require more retries to meet standards.
    """
    if quality_threshold >= 9.0:
        return 1.8  # May need multiple retries
    elif quality_threshold >= 8.0:
        return 1.5  # Some retries expected
    elif quality_threshold >= 7.0:
        return 1.3  # Occasional retries
    else:
        return 1.1  # Minimal retries

def get_estimation_notes(quality_threshold: float, total_chapters: int) -> List[str]:
    """
    Get estimation notes based on configuration.
    """
    notes = []
    
    if quality_threshold >= 8.0:
        notes.append("High quality threshold may require additional retries")
    
    if total_chapters > 20:
        notes.append("Large book projects benefit from chapter-by-chapter monitoring")
    
    if quality_threshold < 6.0:
        notes.append("Lower quality threshold provides faster, more economical generation")
    
    return notes
