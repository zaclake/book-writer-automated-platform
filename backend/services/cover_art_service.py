#!/usr/bin/env python3
"""
Cover Art Generation Service
Generates book cover images using OpenAI DALL-E 3 based on reference files and book bible content.
"""

import os
import json
import logging
import asyncio
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from openai import OpenAI
import firebase_admin
from firebase_admin import storage, credentials
from google.cloud.exceptions import NotFound
import requests
from PIL import Image
import io

logger = logging.getLogger(__name__)

# KDP cover specifications based on research
KDP_COVER_SPECS = {
    "ideal_width": 1600,
    "ideal_height": 2560,
    "min_width": 625,
    "min_height": 1000,
    "aspect_ratio": 1.6,  # height/width
    "max_file_size_mb": 50,
    "dpi": 300,
    "format": "JPEG",
    "color_profile": "RGB"
}

@dataclass
class CoverArtJob:
    """Represents a cover art generation job."""
    job_id: str
    project_id: str
    user_id: str
    status: str  # 'pending', 'generating', 'completed', 'failed'
    prompt: Optional[str] = None
    user_feedback: Optional[str] = None
    image_url: Optional[str] = None
    storage_path: Optional[str] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    attempt_number: int = 1

class CoverArtService:
    """Service for generating book cover art using OpenAI DALL-E 3."""
    
    def __init__(self):
        """Initialize the cover art service."""
        self.openai_client = None
        self.firebase_bucket = None
        self.available = False
        
        # Initialize OpenAI client
        openai_api_key = os.getenv('OPENAI_API_KEY')
        if openai_api_key:
            self.openai_client = OpenAI(api_key=openai_api_key)
        else:
            logger.warning("OPENAI_API_KEY not found. Cover art generation will be disabled.")
            
        # Initialize Firebase Storage
        try:
            # Get Firebase project ID and storage bucket
            project_id = None
            storage_bucket = os.getenv('FIREBASE_STORAGE_BUCKET')
            service_account_json = os.getenv('SERVICE_ACCOUNT_JSON')
            
            if service_account_json:
                service_account_info = json.loads(service_account_json)
                project_id = service_account_info.get('project_id')
                if not storage_bucket:
                    storage_bucket = f"{project_id}.appspot.com"
            
            if not project_id:
                project_id = os.getenv('GOOGLE_CLOUD_PROJECT', 'book-writer-automated')
                
            if not storage_bucket:
                storage_bucket = f"{project_id}.appspot.com"
            
            # Initialize Firebase if not already done
            if not firebase_admin._apps:
                if service_account_json:
                    cred = credentials.Certificate(json.loads(service_account_json))
                    firebase_admin.initialize_app(cred, {
                        'storageBucket': storage_bucket
                    })
                else:
                    firebase_admin.initialize_app(options={
                        'storageBucket': storage_bucket
                    })
            
            # Get storage bucket
            self.firebase_bucket = storage.bucket(storage_bucket)
            logger.info(f"Firebase Storage initialized successfully with bucket: {storage_bucket}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Firebase Storage: {e}")
            
        # Check if service is available
        self.available = self.openai_client is not None and self.firebase_bucket is not None
        
        if self.available:
            logger.info("Cover Art Service initialized successfully")
        else:
            logger.warning("Cover Art Service not available - missing OpenAI API key or Firebase Storage")
    
    def is_available(self) -> bool:
        """Check if the service is available."""
        return self.available
    
    def extract_book_details(self, book_bible_content: str, reference_files: Dict[str, str]) -> Dict[str, Any]:
        """
        Extract key details from book bible and reference files for prompt generation.
        
        Args:
            book_bible_content: The main book bible markdown content
            reference_files: Dictionary of reference file names to their content
            
        Returns:
            Dictionary of extracted book details
        """
        details = {
            'title': '',
            'genre': '',
            'setting': '',
            'time_period': '',
            'main_characters': [],
            'mood_tone': '',
            'themes': [],
            'visual_elements': [],
            'target_audience': '',
            'book_description': ''
        }
        
        try:
            # Extract from book bible
            bible_lower = book_bible_content.lower()
            
            # Extract title (look for # Title or ## Title)
            title_patterns = ['# ', '## ']
            for pattern in title_patterns:
                if pattern in book_bible_content:
                    lines = book_bible_content.split('\n')
                    for line in lines:
                        if line.strip().startswith(pattern):
                            details['title'] = line.replace(pattern, '').strip()
                            break
                    if details['title']:
                        break
            
            # Extract genre from common patterns
            genre_keywords = {
                'fantasy': ['fantasy', 'magic', 'wizard', 'dragon', 'elf', 'dwarf'],
                'science fiction': ['sci-fi', 'science fiction', 'space', 'alien', 'future', 'technology'],
                'romance': ['romance', 'love', 'relationship', 'heart'],
                'mystery': ['mystery', 'detective', 'crime', 'murder', 'investigation'],
                'thriller': ['thriller', 'suspense', 'chase', 'danger'],
                'horror': ['horror', 'scary', 'frightening', 'supernatural'],
                'historical': ['historical', 'period', 'century', 'war', 'ancient'],
                'contemporary': ['contemporary', 'modern', 'current', 'today'],
                'young adult': ['young adult', 'ya', 'teen', 'high school'],
                'literary fiction': ['literary', 'literary fiction', 'character study']
            }
            
            for genre, keywords in genre_keywords.items():
                if any(keyword in bible_lower for keyword in keywords):
                    details['genre'] = genre
                    break
            
            # Extract setting and time period
            setting_sections = ['setting', 'world', 'location', 'place']
            for section in setting_sections:
                if f'## {section}' in bible_lower or f'# {section}' in bible_lower:
                    # Find the section and extract content
                    section_start = bible_lower.find(f'## {section}')
                    if section_start == -1:
                        section_start = bible_lower.find(f'# {section}')
                    
                    if section_start != -1:
                        section_end = book_bible_content.find('\n##', section_start + 1)
                        if section_end == -1:
                            section_end = book_bible_content.find('\n#', section_start + 1)
                        if section_end == -1:
                            section_end = len(book_bible_content)
                        
                        setting_text = book_bible_content[section_start:section_end]
                        details['setting'] = setting_text[:500]  # First 500 chars
                        break
            
            # Extract from reference files
            if 'characters.md' in reference_files:
                char_content = reference_files['characters.md']
                # Extract main character names (look for ## or ### headers)
                char_lines = char_content.split('\n')
                for line in char_lines:
                    if line.strip().startswith('##') and not line.strip().startswith('###'):
                        char_name = line.replace('#', '').strip()
                        if char_name and len(char_name) < 50:  # Reasonable name length
                            details['main_characters'].append(char_name)
                        if len(details['main_characters']) >= 3:  # Limit to top 3
                            break
            
            if 'themes-and-motifs.md' in reference_files:
                themes_content = reference_files['themes-and-motifs.md']
                # Extract theme keywords
                theme_keywords = ['love', 'betrayal', 'redemption', 'courage', 'sacrifice', 
                                'power', 'justice', 'revenge', 'family', 'friendship', 
                                'identity', 'growth', 'survival', 'hope', 'loss']
                themes_lower = themes_content.lower()
                for keyword in theme_keywords:
                    if keyword in themes_lower:
                        details['themes'].append(keyword)
                    if len(details['themes']) >= 3:
                        break
            
            if 'style-guide.md' in reference_files:
                style_content = reference_files['style-guide.md']
                style_lower = style_content.lower()
                
                # Extract mood/tone
                mood_keywords = {
                    'dark': ['dark', 'gritty', 'somber', 'serious'],
                    'light': ['light', 'humorous', 'funny', 'comedic'],
                    'dramatic': ['dramatic', 'intense', 'emotional'],
                    'mysterious': ['mysterious', 'enigmatic', 'secretive'],
                    'romantic': ['romantic', 'passionate', 'loving'],
                    'adventurous': ['adventurous', 'exciting', 'thrilling']
                }
                
                for mood, keywords in mood_keywords.items():
                    if any(keyword in style_lower for keyword in keywords):
                        details['mood_tone'] = mood
                        break
            
            # Extract visual elements from world-building
            if 'world-building.md' in reference_files:
                world_content = reference_files['world-building.md']
                world_lower = world_content.lower()
                
                visual_keywords = ['castle', 'city', 'forest', 'mountain', 'desert', 'ocean', 
                                 'village', 'palace', 'tower', 'bridge', 'river', 'valley',
                                 'medieval', 'modern', 'futuristic', 'ancient', 'magical',
                                 'industrial', 'rural', 'urban', 'wilderness']
                
                for keyword in visual_keywords:
                    if keyword in world_lower:
                        details['visual_elements'].append(keyword)
                    if len(details['visual_elements']) >= 5:
                        break
            
            # Extract target audience
            if 'target-audience-profile.md' in reference_files:
                audience_content = reference_files['target-audience-profile.md']
                audience_lower = audience_content.lower()
                
                if 'young adult' in audience_lower or 'ya' in audience_lower:
                    details['target_audience'] = 'young adult'
                elif 'teen' in audience_lower:
                    details['target_audience'] = 'teen'
                elif 'adult' in audience_lower:
                    details['target_audience'] = 'adult'
                elif 'children' in audience_lower:
                    details['target_audience'] = 'children'
            
            # Create book description summary
            if details['title']:
                desc_parts = [f"'{details['title']}'"]
                if details['genre']:
                    desc_parts.append(f"a {details['genre']} novel")
                if details['main_characters']:
                    desc_parts.append(f"featuring {', '.join(details['main_characters'][:2])}")
                if details['setting']:
                    setting_brief = details['setting'][:100] + "..." if len(details['setting']) > 100 else details['setting']
                    desc_parts.append(f"set in {setting_brief}")
                
                details['book_description'] = ' '.join(desc_parts)
            
        except Exception as e:
            logger.error(f"Error extracting book details: {e}")
        
        return details
    
    def generate_cover_prompt(self, book_details: Dict[str, Any], user_feedback: Optional[str] = None) -> str:
        """
        Generate a DALL-E 3 prompt for cover art based on book details.
        
        Args:
            book_details: Extracted book details
            user_feedback: Optional user feedback for regeneration
            
        Returns:
            Generated prompt string
        """
        prompt_parts = []
        
        # Start with base cover art instruction
        prompt_parts.append("Create a professional book cover design")
        
        # Add genre-specific styling
        genre = book_details.get('genre', '').lower()
        genre_styles = {
            'fantasy': 'epic fantasy style with magical elements, dramatic lighting, rich colors',
            'science fiction': 'futuristic sci-fi style with sleek design, metallic elements, cosmic backdrop',
            'romance': 'romantic style with warm colors, elegant typography, emotional imagery',
            'mystery': 'mysterious noir style with shadows, muted colors, intriguing elements',
            'thriller': 'intense thriller style with bold colors, dynamic composition, suspenseful mood',
            'horror': 'dark horror style with ominous atmosphere, dramatic shadows, chilling elements',
            'historical': 'period-appropriate historical style with authentic details, vintage feel',
            'contemporary': 'modern contemporary style with clean design, current aesthetic',
            'young adult': 'vibrant YA style with bold colors, appealing to teen readers',
            'literary fiction': 'sophisticated literary style with artistic composition, refined aesthetic'
        }
        
        if genre in genre_styles:
            prompt_parts.append(f"in {genre_styles[genre]}")
        
        # Add visual elements from setting/world-building
        visual_elements = book_details.get('visual_elements', [])
        if visual_elements:
            elements_str = ', '.join(visual_elements[:3])  # Top 3 elements
            prompt_parts.append(f"featuring {elements_str}")
        
        # Add mood/tone
        mood = book_details.get('mood_tone', '')
        if mood:
            mood_descriptions = {
                'dark': 'with a dark, brooding atmosphere',
                'light': 'with a bright, uplifting feel',
                'dramatic': 'with dramatic, intense energy',
                'mysterious': 'with an enigmatic, mysterious quality',
                'romantic': 'with romantic, passionate undertones',
                'adventurous': 'with adventurous, exciting energy'
            }
            if mood in mood_descriptions:
                prompt_parts.append(mood_descriptions[mood])
        
        # Add character elements if available
        characters = book_details.get('main_characters', [])
        if characters and len(characters) > 0:
            if len(characters) == 1:
                prompt_parts.append(f"featuring {characters[0]} as the protagonist")
            else:
                prompt_parts.append(f"with characters including {characters[0]}")
        
        # Add themes if available
        themes = book_details.get('themes', [])
        if themes:
            theme_str = ', '.join(themes[:2])  # Top 2 themes
            prompt_parts.append(f"conveying themes of {theme_str}")
        
        # Technical specifications for KDP compliance
        prompt_parts.append(f"Designed as a book cover with portrait orientation (aspect ratio 1.6:1)")
        prompt_parts.append("with clean, readable composition suitable for both large and thumbnail sizes")
        prompt_parts.append("Professional quality, high contrast, commercially viable design")
        
        # Add user feedback if provided
        if user_feedback:
            prompt_parts.append(f"Incorporating this feedback: {user_feedback}")
        
        # Join all parts
        full_prompt = '. '.join(prompt_parts) + '.'
        
        # Ensure prompt isn't too long (DALL-E has limits)
        if len(full_prompt) > 1000:
            full_prompt = full_prompt[:1000] + '...'
        
        logger.info(f"Generated cover art prompt: {full_prompt[:200]}...")
        return full_prompt
    
    async def generate_cover_image(self, prompt: str) -> Tuple[str, bytes]:
        """
        Generate cover image using OpenAI DALL-E 3.
        
        Args:
            prompt: Text prompt for image generation
            
        Returns:
            Tuple of (image_url, image_bytes)
        """
        if not self.openai_client:
            raise RuntimeError("OpenAI client not available")
        
        try:
            logger.info("Starting DALL-E 3 image generation")
            
            response = self.openai_client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1792",  # Closest to 1.6:1 aspect ratio available
                quality="hd",
                n=1,
                response_format="url"
            )
            
            image_url = response.data[0].url
            logger.info(f"DALL-E 3 generated image URL: {image_url}")
            
            # Download the image
            image_response = requests.get(image_url, timeout=60)
            image_response.raise_for_status()
            image_bytes = image_response.content
            
            # Process image to meet KDP specifications
            processed_bytes = await self._process_image_for_kdp(image_bytes)
            
            logger.info(f"Generated and processed cover image ({len(processed_bytes)} bytes)")
            return image_url, processed_bytes
            
        except Exception as e:
            logger.error(f"Failed to generate cover image: {e}")
            raise
    
    async def _process_image_for_kdp(self, image_bytes: bytes) -> bytes:
        """
        Process generated image to meet KDP specifications.
        
        Args:
            image_bytes: Original image bytes
            
        Returns:
            Processed image bytes
        """
        try:
            # Open image with PIL
            image = Image.open(io.BytesIO(image_bytes))
            
            # Convert to RGB if needed
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Resize to ideal KDP dimensions while maintaining aspect ratio
            target_width = KDP_COVER_SPECS["ideal_width"]
            target_height = KDP_COVER_SPECS["ideal_height"]
            
            # Calculate current aspect ratio
            current_ratio = image.height / image.width
            target_ratio = target_height / target_width
            
            if abs(current_ratio - target_ratio) > 0.1:  # If significantly different from target ratio
                # Crop to target aspect ratio
                if current_ratio > target_ratio:
                    # Image is too tall, crop height
                    new_height = int(image.width * target_ratio)
                    top = (image.height - new_height) // 2
                    image = image.crop((0, top, image.width, top + new_height))
                else:
                    # Image is too wide, crop width
                    new_width = int(image.height / target_ratio)
                    left = (image.width - new_width) // 2
                    image = image.crop((left, 0, left + new_width, image.height))
            
            # Resize to exact target dimensions
            image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
            
            # Add subtle border if background is very light (to prevent disappearing on white backgrounds)
            # Check if image has light edges
            def is_light_color(rgb_tuple):
                # Consider a color light if it's brightness > 240
                return sum(rgb_tuple) / 3 > 240
            
            # Sample edge pixels
            edge_pixels = []
            width, height = image.size
            
            # Sample top edge
            for x in range(0, width, width//10):
                edge_pixels.append(image.getpixel((x, 0)))
            # Sample bottom edge  
            for x in range(0, width, width//10):
                edge_pixels.append(image.getpixel((x, height-1)))
            # Sample left edge
            for y in range(0, height, height//10):
                edge_pixels.append(image.getpixel((0, y)))
            # Sample right edge
            for y in range(0, height, height//10):
                edge_pixels.append(image.getpixel((width-1, y)))
            
            light_edges = sum(1 for pixel in edge_pixels if is_light_color(pixel))
            
            if light_edges > len(edge_pixels) * 0.7:  # If >70% of edges are light
                # Add a subtle gray border
                from PIL import ImageDraw
                draw = ImageDraw.Draw(image)
                border_color = (180, 180, 180)  # Light gray
                border_width = 3
                
                # Draw border
                draw.rectangle(
                    [(0, 0), (width-1, height-1)], 
                    outline=border_color, 
                    width=border_width
                )
                logger.info("Added subtle border due to light background")
            
            # Save as high-quality JPEG
            output_buffer = io.BytesIO()
            image.save(
                output_buffer, 
                format='JPEG', 
                quality=95,  # High quality
                dpi=(300, 300),  # 300 DPI as required by KDP
                optimize=True
            )
            
            processed_bytes = output_buffer.getvalue()
            
            # Check file size
            size_mb = len(processed_bytes) / (1024 * 1024)
            if size_mb > KDP_COVER_SPECS["max_file_size_mb"]:
                logger.warning(f"Image size {size_mb:.1f}MB exceeds KDP limit of {KDP_COVER_SPECS['max_file_size_mb']}MB")
                # Re-save with lower quality if needed
                output_buffer = io.BytesIO()
                image.save(
                    output_buffer, 
                    format='JPEG', 
                    quality=85,  # Lower quality
                    dpi=(300, 300),
                    optimize=True
                )
                processed_bytes = output_buffer.getvalue()
                size_mb = len(processed_bytes) / (1024 * 1024)
                logger.info(f"Reduced image size to {size_mb:.1f}MB")
            
            logger.info(f"Processed image to KDP specs: {target_width}x{target_height}, {size_mb:.1f}MB")
            return processed_bytes
            
        except Exception as e:
            logger.error(f"Failed to process image for KDP: {e}")
            # Return original if processing fails
            return image_bytes
    
    async def upload_to_firebase(self, image_bytes: bytes, project_id: str, job_id: str) -> str:
        """
        Upload processed image to Firebase Storage.
        
        Args:
            image_bytes: Processed image bytes
            project_id: Project ID
            job_id: Cover art job ID
            
        Returns:
            Public URL of uploaded image
        """
        if not self.firebase_bucket:
            raise RuntimeError("Firebase Storage not available")
        
        try:
            # Create storage path
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"cover-art/{project_id}/{job_id}_{timestamp}.jpg"
            
            # Upload to Firebase Storage
            blob = self.firebase_bucket.blob(filename)
            blob.upload_from_string(
                image_bytes,
                content_type='image/jpeg'
            )
            
            # Make blob publicly accessible
            blob.make_public()
            
            # Get public URL
            public_url = blob.public_url
            
            logger.info(f"Uploaded cover art to Firebase Storage: {filename}")
            return public_url
            
        except Exception as e:
            logger.error(f"Failed to upload to Firebase Storage: {e}")
            raise
    
    async def generate_cover_art(self, project_id: str, user_id: str, 
                                book_bible_content: str, reference_files: Dict[str, str],
                                user_feedback: Optional[str] = None, 
                                job_id: Optional[str] = None) -> CoverArtJob:
        """
        Complete cover art generation workflow.
        
        Args:
            project_id: Project ID
            user_id: User ID
            book_bible_content: Book bible content
            reference_files: Reference files content
            user_feedback: Optional user feedback for regeneration
            job_id: Optional existing job ID for regeneration
            
        Returns:
            CoverArtJob with results
        """
        if not self.is_available():
            raise RuntimeError("Cover art service not available")
        
        # Create or update job
        if not job_id:
            import uuid
            job_id = str(uuid.uuid4())
            attempt_number = 1
        else:
            # This is a regeneration
            attempt_number = 2  # Could be enhanced to track actual attempt count
        
        job = CoverArtJob(
            job_id=job_id,
            project_id=project_id,
            user_id=user_id,
            status='generating',
            user_feedback=user_feedback,
            created_at=datetime.now(timezone.utc),
            attempt_number=attempt_number
        )
        
        try:
            # Step 1: Extract book details
            logger.info(f"Extracting book details for project {project_id}")
            book_details = self.extract_book_details(book_bible_content, reference_files)
            
            # Step 2: Generate prompt
            logger.info(f"Generating cover art prompt for project {project_id}")
            prompt = self.generate_cover_prompt(book_details, user_feedback)
            job.prompt = prompt
            
            # Step 3: Generate image
            logger.info(f"Generating cover image for project {project_id}")
            original_url, image_bytes = await self.generate_cover_image(prompt)
            
            # Step 4: Upload to Firebase
            logger.info(f"Uploading cover art for project {project_id}")
            public_url = await self.upload_to_firebase(image_bytes, project_id, job_id)
            
            # Update job with success
            job.status = 'completed'
            job.image_url = public_url
            job.storage_path = f"cover-art/{project_id}/{job_id}"
            job.completed_at = datetime.now(timezone.utc)
            
            logger.info(f"Cover art generation completed successfully for project {project_id}")
            return job
            
        except Exception as e:
            # Update job with failure
            job.status = 'failed'
            job.error = str(e)
            job.completed_at = datetime.now(timezone.utc)
            
            logger.error(f"Cover art generation failed for project {project_id}: {e}")
            return job 