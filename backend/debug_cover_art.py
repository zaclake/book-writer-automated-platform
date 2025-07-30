#!/usr/bin/env python3
"""
Debug script for cover art service
"""

import os
import sys
import json
import asyncio
import logging
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent))

from services.cover_art_service import CoverArtService

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def debug_cover_art_service():
    """Debug the cover art service configuration."""
    
    print("=== Cover Art Service Debug ===")
    
    # Check environment variables
    print("\n1. Environment Variables:")
    openai_key = os.getenv('OPENAI_API_KEY')
    firebase_bucket = os.getenv('FIREBASE_STORAGE_BUCKET')
    service_account = os.getenv('SERVICE_ACCOUNT_JSON')
    
    print(f"   OPENAI_API_KEY: {'✓ Set' if openai_key else '✗ Missing'}")
    if openai_key:
        print(f"   OPENAI_API_KEY length: {len(openai_key)}")
        print(f"   OPENAI_API_KEY starts with: {openai_key[:20]}...")
    
    print(f"   FIREBASE_STORAGE_BUCKET: {'✓ Set' if firebase_bucket else '✗ Missing'}")
    if firebase_bucket:
        print(f"   FIREBASE_STORAGE_BUCKET: {firebase_bucket}")
    
    print(f"   SERVICE_ACCOUNT_JSON: {'✓ Set' if service_account else '✗ Missing'}")
    if service_account:
        try:
            sa_data = json.loads(service_account)
            print(f"   Service Account Project: {sa_data.get('project_id', 'Not found')}")
        except:
            print("   Service Account JSON: Invalid format")
    
    # Initialize service
    print("\n2. Service Initialization:")
    try:
        service = CoverArtService()
        print(f"   Service Available: {'✓' if service.is_available() else '✗'}")
        print(f"   OpenAI Client: {'✓' if service.openai_client else '✗'}")
        print(f"   Firebase Bucket: {'✓' if service.firebase_bucket else '✗'}")
        
        if service.firebase_bucket:
            print(f"   Firebase Bucket Name: {service.firebase_bucket.name}")
        
    except Exception as e:
        print(f"   ✗ Service initialization failed: {e}")
        return
    
    # Test OpenAI connection (without actually generating)
    print("\n3. OpenAI Connection Test:")
    if service.openai_client:
        try:
            # Test with a simple models list call
            models = service.openai_client.models.list()
            print("   ✓ OpenAI connection successful")
            print(f"   Available models: {len(models.data)} found")
            # Check if DALL-E 3 is available
            dalle_models = [m for m in models.data if 'dall-e' in m.id.lower()]
            print(f"   DALL-E models: {[m.id for m in dalle_models]}")
        except Exception as e:
            print(f"   ✗ OpenAI connection failed: {e}")
    else:
        print("   ✗ OpenAI client not initialized")
    
    # Test Firebase connection
    print("\n4. Firebase Storage Test:")
    if service.firebase_bucket:
        try:
            # Try to list some files (just to test connection)
            blobs = list(service.firebase_bucket.list_blobs(max_results=1))
            print("   ✓ Firebase Storage connection successful")
        except Exception as e:
            print(f"   ✗ Firebase Storage connection failed: {e}")
    else:
        print("   ✗ Firebase bucket not initialized")
    
    # Test prompt generation
    print("\n5. Prompt Generation Test:")
    try:
        test_book_details = {
            'title': 'Test Fantasy Novel',
            'genre': 'fantasy',
            'setting': 'A magical kingdom with ancient castles',
            'main_characters': ['Aria the Mage', 'Sir Gareth'],
            'themes': ['courage', 'friendship'],
            'visual_elements': ['castle', 'magical', 'forest'],
            'mood_tone': 'adventurous'
        }
        
        prompt = service.generate_cover_prompt(test_book_details)
        print("   ✓ Prompt generation successful")
        print(f"   Generated prompt: {prompt[:100]}...")
        print(f"   Prompt length: {len(prompt)} characters")
        
    except Exception as e:
        print(f"   ✗ Prompt generation failed: {e}")
    
    print("\n=== Debug Complete ===")

if __name__ == "__main__":
    asyncio.run(debug_cover_art_service()) 