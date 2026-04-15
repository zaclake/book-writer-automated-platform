#!/usr/bin/env python3
"""
Initialize Firestore with default pricing data for the credits system.
Run this script once to set up the initial pricing registry.
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any

logger = logging.getLogger(__name__)

async def initialize_pricing_data():
    """Initialize Firestore with default pricing data."""
    try:
        # Import database adapter
        from backend.database_integration import get_database_adapter
        
        db_adapter = get_database_adapter()
        if not db_adapter or not hasattr(db_adapter, 'firestore'):
            logger.error("❌ Database adapter not available or Firestore not configured")
            return False
        
        firestore = db_adapter.firestore.db  # Access the actual Firestore client
        logger.info("✅ Connected to Firestore")
        
        # Default pricing data based on OpenAI's current pricing (as of 2026)
        default_pricing = {
            'openai': {
                'gpt-4.1': {
                    # Standard tier: $2.00 / 1M input tokens, $8.00 / 1M output tokens
                    'input_usd_per_1k': 0.002,
                    'output_usd_per_1k': 0.008,
                    'provider': 'openai',
                    'model_type': 'chat'
                },
                'gpt-4.1-mini': {
                    # Standard tier: $0.40 / 1M input tokens, $1.60 / 1M output tokens
                    'input_usd_per_1k': 0.0004,
                    'output_usd_per_1k': 0.0016,
                    'provider': 'openai',
                    'model_type': 'chat'
                },
                'gpt-4.1-nano': {
                    # Standard tier: $0.10 / 1M input tokens, $0.40 / 1M output tokens
                    'input_usd_per_1k': 0.0001,
                    'output_usd_per_1k': 0.0004,
                    'provider': 'openai',
                    'model_type': 'chat'
                },
                'gpt-4o': {
                    'input_usd_per_1k': 0.005,   # $5 per 1M input tokens
                    'output_usd_per_1k': 0.015,  # $15 per 1M output tokens
                    'provider': 'openai',
                    'model_type': 'chat'
                },
                'gpt-4o-mini': {
                    'input_usd_per_1k': 0.00015,  # $0.15 per 1M input tokens
                    'output_usd_per_1k': 0.0006,  # $0.60 per 1M output tokens
                    'provider': 'openai',
                    'model_type': 'chat'
                },
                'gpt-4-turbo': {
                    'input_usd_per_1k': 0.01,     # $10 per 1M input tokens
                    'output_usd_per_1k': 0.03,    # $30 per 1M output tokens
                    'provider': 'openai',
                    'model_type': 'chat'
                },
                'gpt-image-1': {
                    'job_usd': 0.250,  # High quality 1024x1536 image
                    'provider': 'openai',
                    'model_type': 'image',
                    'image_size': '1024x1536',
                    'quality': 'high'
                },
                'dall-e-3': {
                    'job_usd': 0.040,  # $0.04 per 1024x1024 image
                    'provider': 'openai',
                    'model_type': 'image',
                    'image_size': '1024x1024'
                },
                'dall-e-3-hd': {
                    'job_usd': 0.080,  # $0.08 per 1024x1024 HD image
                    'provider': 'openai',
                    'model_type': 'image',
                    'image_size': '1024x1024',
                    'quality': 'hd'
                },
                'dall-e-3-large': {
                    'job_usd': 0.080,  # $0.08 per 1024x1792 or 1792x1024 image
                    'provider': 'openai',
                    'model_type': 'image',
                    'image_size': '1024x1792'
                },
                'dall-e-3-large-hd': {
                    'job_usd': 0.120,  # $0.12 per 1024x1792 or 1792x1024 HD image
                    'provider': 'openai',
                    'model_type': 'image',
                    'image_size': '1024x1792',
                    'quality': 'hd'
                }
            }
        }
        
        # System configuration
        system_config = {
            'credits_markup': float(os.getenv('CREDITS_MARKUP', '5.0')),
            'credits_enabled': True,
            'billing_enabled': os.getenv('ENABLE_CREDITS_BILLING', 'false').lower() == 'true',
            'beta_credits_enabled': os.getenv('ENABLE_BETA_CREDITS', 'false').lower() == 'true',
            'last_updated': datetime.now(timezone.utc),
            'version': '1.0.0'
        }
        
        logger.info("📝 Writing system configuration...")
        
        # Write system configuration
        firestore.collection('system').document('config').set(system_config)
        
        logger.info("💰 Writing pricing data...")
        
        # Write pricing data for each provider and model
        pricing_doc = firestore.collection('system').document('model_pricing')
        pricing_doc.set({
            'providers': default_pricing,
            'last_updated': datetime.now(timezone.utc),
            'version': '1.0.0'
        })
        
        logger.info("✅ Successfully initialized pricing data in Firestore")
        logger.info(f"   - Markup: {system_config['credits_markup']}x")
        logger.info(f"   - Billing enabled: {system_config['billing_enabled']}")
        logger.info(f"   - Beta credits enabled: {system_config['beta_credits_enabled']}")
        logger.info(f"   - Models configured: {sum(len(models) for models in default_pricing.values())}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize pricing data: {e}")
        return False

async def verify_pricing_data():
    """Verify that pricing data was written correctly."""
    try:
        from backend.database_integration import get_database_adapter
        
        db_adapter = get_database_adapter()
        if not db_adapter or not hasattr(db_adapter, 'firestore'):
            logger.error("❌ Database adapter not available")
            return False
        
        firestore = db_adapter.firestore.db  # Access the actual Firestore client
        
        # Check system config
        config_doc = firestore.collection('system').document('config').get()
        if not config_doc.exists:
            logger.error("❌ System config document not found")
            return False
        
        config_data = config_doc.to_dict()
        logger.info(f"✅ System config found - markup: {config_data.get('credits_markup')}x")
        
        # Check pricing data
        pricing_doc = firestore.collection('system').document('model_pricing').get()
        if not pricing_doc.exists:
            logger.error("❌ Pricing document not found")
            return False
        
        pricing_data = pricing_doc.to_dict()
        providers = pricing_data.get('providers', {})
        model_count = sum(len(models) for models in providers.values())
        logger.info(f"✅ Pricing data found - {len(providers)} providers, {model_count} models")
        
        # Sample a few key models
        openai_models = providers.get('openai', {})
        if 'gpt-4.1' in openai_models:
            gpt41 = openai_models['gpt-4.1']
            logger.info(f"   - GPT-4.1: ${gpt41.get('input_usd_per_1k')}/1k input, ${gpt41.get('output_usd_per_1k')}/1k output")
        if 'gpt-4o' in openai_models:
            gpt4o = openai_models['gpt-4o']
            logger.info(f"   - GPT-4o: ${gpt4o.get('input_usd_per_1k')}/1k input, ${gpt4o.get('output_usd_per_1k')}/1k output")
        
        if 'gpt-image-1' in openai_models:
            gpt_image = openai_models['gpt-image-1']
            logger.info(f"   - GPT-image-1: ${gpt_image.get('job_usd')}/image")

        if 'dall-e-3' in openai_models:
            dalle = openai_models['dall-e-3']
            logger.info(f"   - DALL-E 3: ${dalle.get('job_usd')}/image")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to verify pricing data: {e}")
        return False

async def main():
    """Main function."""
    logger.info("🚀 Initializing Firestore pricing data for credits system...")
    
    # Initialize pricing data
    success = await initialize_pricing_data()
    if not success:
        logger.error("❌ Failed to initialize pricing data")
        return
    
    # Verify the data was written correctly
    logger.info("🔍 Verifying pricing data...")
    success = await verify_pricing_data()
    if not success:
        logger.error("❌ Failed to verify pricing data")
        return
    
    logger.info("🎉 Firestore pricing data initialization completed successfully!")
    logger.info("")
    logger.info("Next steps:")
    logger.info("1. Deploy the updated Firestore security rules")
    logger.info("2. Deploy the Firestore indexes")
    logger.info("3. Set environment variables:")
    logger.info(f"   - ENABLE_CREDITS_SYSTEM=true")
    logger.info(f"   - ENABLE_CREDITS_BILLING=true (for production)")
    logger.info(f"   - ENABLE_BETA_CREDITS=true (for beta testing)")
    logger.info(f"   - CREDITS_MARKUP=5.0 (or your preferred markup)")

if __name__ == "__main__":
    asyncio.run(main())