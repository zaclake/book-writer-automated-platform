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
import re
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

# Optional advanced NLP
try:
    import spacy
    _NLP = spacy.load("en_core_web_sm")  # small model, fast; install during build
except Exception:
    _NLP = None

logger = logging.getLogger(__name__)

# Concurrency controls (robust import across environments)
try:
    # Primary: absolute import when `backend` is a package
    from backend.system.concurrency import (
        get_image_semaphore,
        get_image_thread_semaphore,
        semaphore,
        thread_semaphore,
    )
except Exception:
    try:
        # Fallback: relative import when running within the backend package
        from ..system.concurrency import (
            get_image_semaphore,
            get_image_thread_semaphore,
            semaphore,
            thread_semaphore,
        )
    except Exception:
        try:
            # Fallback: top-level import when code is executed from repo root
            from system.concurrency import (
                get_image_semaphore,
                get_image_thread_semaphore,
                semaphore,
                thread_semaphore,
            )
        except Exception:
            # Last resort: minimal local implementations
            import threading  # type: ignore
            _image_sem = None
            _image_thread_sem = None

            def _get_int_env(name: str, default: int) -> int:
                try:
                    value = int(os.getenv(name, str(default)))
                    return max(1, value)
                except Exception:
                    return default

            def get_image_semaphore() -> asyncio.Semaphore:  # type: ignore
                global _image_sem
                if _image_sem is None:
                    _image_sem = asyncio.Semaphore(_get_int_env("MAX_CONCURRENT_IMAGE", 2))
                return _image_sem

            def get_image_thread_semaphore() -> 'threading.BoundedSemaphore':  # type: ignore
                global _image_thread_sem
                if _image_thread_sem is None:
                    _image_thread_sem = threading.BoundedSemaphore(_get_int_env("MAX_CONCURRENT_IMAGE", 2))
                return _image_thread_sem

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
    
    def __init__(self, user_id: Optional[str] = None):
        """Initialize the cover art service."""
        self.openai_client = None
        self.billable_client = False
        self.firebase_bucket = None
        self.available = False
        
        # Initialize OpenAI client - use BillableClient if user_id provided and billing enabled
        openai_api_key = os.getenv('OPENAI_API_KEY')
        enable_billing = os.getenv('ENABLE_CREDITS_BILLING', 'false').lower() == 'true'
        
        if openai_api_key:
            if user_id and enable_billing:
                try:
                    from backend.services.billable_client import BillableOpenAIClient
                    self.openai_client = BillableOpenAIClient(user_id)
                    self.billable_client = True
                    logger.info(f"Initialized billable cover art service for user {user_id}")
                except ImportError:
                    logger.warning("BillableClient not available, using regular OpenAI client")
                    self.openai_client = OpenAI(api_key=openai_api_key)
                    self.billable_client = False
            else:
                self.openai_client = OpenAI(api_key=openai_api_key)
                self.billable_client = False
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

    async def _generate_visual_spec(self, book_bible_content: str, reference_files: Dict[str, str], ui_options: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Use a text model to synthesize a concrete visual spec from the book bible and references.
        Returns a dict with keys like: visual_elements (list), composition (str), palette (list), mood (str).
        """
        if not self.openai_client:
            return None
        try:
            # Build short context
            bible_excerpt = (book_bible_content or "")[:1200]
            ref_snippets: List[str] = []
            for name, content in (reference_files or {}).items():
                if not content:
                    continue
                ref_snippets.append(f"{name}: {content[:600]}")
                if len(ref_snippets) >= 4:
                    break
            refs_joined = "\n".join(ref_snippets)

            title_txt = (ui_options or {}).get('title_text') or ''
            author_txt = (ui_options or {}).get('author_text') or ''

            system_msg = (
                "You are a senior book cover art director. From the given context, produce a concise, concrete visual brief strictly grounded in the material. "
                "Do not invent settings or motifs that are not present. Output valid JSON only with keys: visual_elements (list of 3-6 concise nouns), composition (one sentence), palette (list of 2-4 colors by common names), mood (one word)."
            )
            user_msg = (
                f"Title: {title_txt}\nAuthor: {author_txt}\n\n"
                f"Book Bible (excerpt):\n{bible_excerpt}\n\n"
                f"References (snippets):\n{refs_joined}\n\n"
                "Constraints: No text rendering; we will add typography later. Choose only elements clearly supported by the context."
            )

            import functools
            with thread_semaphore(get_image_thread_semaphore()):
                response = await asyncio.to_thread(
                    functools.partial(
                        getattr(self.openai_client.chat.completions, "create"),
                        model=os.getenv("DEFAULT_AI_MODEL", "gpt-4o-mini"),
                        messages=[
                            {"role": "system", "content": system_msg},
                            {"role": "user", "content": user_msg},
                        ],
                        temperature=0.2,
                        max_tokens=400,
                    )
                )
            # OpenAI SDK returns ChatCompletion with message.content
            content = response.choices[0].message.content
            import json as _json
            spec = _json.loads(content)
            if not isinstance(spec, dict) or "visual_elements" not in spec:
                return None
            return spec
        except Exception as e:
            logger.error(f"Failed to generate visual spec: {e}")
            return None
    
    def extract_book_details(self, book_bible_content: str, reference_files: Dict[str, str], ui_options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
            # Normalize reference filenames for robust matching
            normalized_refs: Dict[str, str] = {}
            for raw_name, content in (reference_files or {}).items():
                try:
                    name_only = str(Path(raw_name).name).lower()
                except Exception:
                    name_only = str(raw_name).lower()
                normalized_refs[name_only] = content or ''
            
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
            
            # Fallback: use UI-provided title if available
            if not details['title'] and ui_options:
                ui_title = (ui_options.get('title_text') or '').strip()
                if ui_title:
                    details['title'] = ui_title

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
            
            # Extract setting from multiple sources with priority
            self._extract_setting_details(details, book_bible_content, normalized_refs)
            
            # Extract characters intelligently
            self._extract_character_details(details, normalized_refs)
            
            # Extract themes intelligently
            self._extract_theme_details(details, normalized_refs)
            
            # Extract mood/tone from style guide
            self._extract_mood_tone(details, normalized_refs)
            
            # Extract target audience
            # Accept multiple variants e.g. audience.md, target_audience.md
            audience_key = next((k for k in normalized_refs.keys() if any(t in k for t in ['target-audience', 'target_audience', 'audience'])), None)
            if audience_key:
                audience_content = normalized_refs[audience_key]
                audience_lower = audience_content.lower()
                
                if 'young adult' in audience_lower or 'ya' in audience_lower:
                    details['target_audience'] = 'young adult'
                elif 'teen' in audience_lower:
                    details['target_audience'] = 'teen'
                elif 'adult' in audience_lower:
                    details['target_audience'] = 'adult'
                elif 'children' in audience_lower:
                    details['target_audience'] = 'children'
            
            # Create book description summary (do not infer if missing)
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
        
        logger.info(f"Extracted book details: {details}")
        return details
    
    def _extract_setting_details(self, details: Dict[str, Any], book_bible_content: str, reference_files: Dict[str, str]):
        """Extract setting and visual elements intelligently from multiple sources."""
        
        # Priority 1: Look for explicit setting sections in book bible
        setting_sections = ['setting', 'world', 'location', 'place', 'environment']
        for section in setting_sections:
            if f'## {section}' in book_bible_content.lower() or f'# {section}' in book_bible_content.lower():
                section_start = book_bible_content.lower().find(f'## {section}')
                if section_start == -1:
                    section_start = book_bible_content.lower().find(f'# {section}')
                
                if section_start != -1:
                    section_end = book_bible_content.find('\n##', section_start + 1)
                    if section_end == -1:
                        section_end = book_bible_content.find('\n#', section_start + 1)
                    if section_end == -1:
                        section_end = len(book_bible_content)
                    
                    setting_text = book_bible_content[section_start:section_end]
                    details['setting'] = setting_text[:500]  # First 500 chars
                    break
        
        # Priority 2: Extract from world-building file more intelligently
        # Accept flexible filenames for world/setting
        world_key = next((k for k in reference_files.keys() if any(t in k for t in ['world-building', 'world_building', 'world', 'setting'])), None)
        if world_key:
            world_content = reference_files[world_key]
            self._extract_visual_elements_smart(details, world_content)
        
        # Do NOT fall back to outline/timeline. Only world-building/setting may influence visual elements.
        # This prevents spurious environment terms from plot summaries affecting the cover.
    
    def _extract_visual_elements_smart(self, details: Dict[str, Any], content: str):
        """Smartly extract visual elements by analyzing context, not just keyword matching."""
        content_lower = content.lower()

        def count_word_occurrences(text: str, word: str) -> int:
            try:
                return len(re.findall(r"\\b" + re.escape(word) + r"\\b", text))
            except re.error:
                return text.count(word)
        
        # Look for setting descriptions with context
        water_keywords = ['lake', 'ocean', 'sea', 'river', 'water', 'shore', 'dock', 'pier', 'boat', 'island']
        forest_keywords = ['forest', 'woods', 'trees', 'woodland']
        urban_keywords = ['city', 'town', 'urban', 'street']
        rural_keywords = ['rural', 'countryside', 'farm', 'village']
        mountain_keywords = ['mountain', 'hill', 'peak', 'cliff']
        building_keywords = ['castle', 'palace', 'tower', 'mansion', 'cabin', 'house']
        
        # Analyze which environment dominates (count mentions)
        def count_mentions(keywords: List[str]) -> int:
            return sum(count_word_occurrences(content_lower, kw) for kw in keywords)

        water_score = count_mentions(water_keywords)
        forest_score = count_mentions(forest_keywords)
        urban_score = count_mentions(urban_keywords)
        rural_score = count_mentions(rural_keywords)
        mountain_score = count_mentions(mountain_keywords)
        building_score = count_mentions(building_keywords)
        # Industrial/plant detection
        industrial_keywords = ['factory', 'industrial', 'plant', 'wastewater', 'rendering', 'pipe', 'pipes', 'smokestack', 'chimney', 'tank']
        industrial_score = count_mentions(industrial_keywords)
        
        # Add dominant elements only
        scores = [
            (water_score, water_keywords),
            (forest_score, forest_keywords),
            (urban_score, urban_keywords),
            (rural_score, rural_keywords),
            (mountain_score, mountain_keywords),
            (building_score, building_keywords),
            (industrial_score, industrial_keywords)
        ]
        
        # Sort by score and take top elements
        scores.sort(key=lambda x: x[0], reverse=True)
        
        added = 0
        for score, keywords in scores[:3]:  # Top 3 environment types
            # For industrial cues allow a single explicit mention; for others require 2
            min_thresh = 1 if keywords is industrial_keywords else 2
            if score >= min_thresh and added < 2:
                # Find the most mentioned keyword in this category
                best_keyword = max(keywords, key=lambda k: content_lower.count(k))
                if content_lower.count(best_keyword) > 0:
                    details['visual_elements'].append(best_keyword)
                    added += 1
        
        # Look for time period indicators conservatively and only if clearly stated
        if any(term in content_lower for term in ['time period', 'set in ', ' era']):
            if re.search(r"\\b(medieval|middle ages|knight)\\b", content_lower):
                details['visual_elements'].append('medieval')
            elif re.search(r"\\b(modern|contemporary|current)\\b", content_lower):
                details['visual_elements'].append('modern')
            elif re.search(r"\\b(future|futuristic|sci-?fi)\\b", content_lower):
                details['visual_elements'].append('futuristic')

        # === Advanced NLP extraction (spaCy) ===
        if _NLP:
            doc = _NLP(content)
            # Pick up LOCATION / FACILITY / ORG nouns for scenery
            candidate_tokens = [ent.text.lower() for ent in doc.ents if ent.label_ in {'GPE', 'LOC', 'FAC'}]
            # Add top frequency tokens not already included
            for tok in candidate_tokens:
                if tok not in details['visual_elements'] and len(details['visual_elements']) < 5:
                    details['visual_elements'].append(tok)
    
    def _extract_character_details(self, details: Dict[str, Any], reference_files: Dict[str, str]):
        """Extract character names more intelligently."""
        # Accept flexible filenames for characters
        char_key = next((k for k in reference_files.keys() if 'character' in k), None)
        if char_key:
            char_content = reference_files[char_key]
            char_lines = char_content.split('\n')
            
            for line in char_lines:
                # Look for character names in headers, but filter out generic section names
                if line.strip().startswith('##') and not line.strip().startswith('###'):
                    char_name = line.replace('#', '').strip()
                    
                    # Filter out section headers and generic terms
                    skip_terms = ['character', 'profile', 'description', 'core', 'main', 'supporting', 
                                'minor', 'antagonist', 'protagonist', 'cast', 'overview', 'summary']
                    
                    if (char_name and 
                        len(char_name) < 50 and  # Reasonable name length
                        not any(skip_term in char_name.lower() for skip_term in skip_terms) and
                        not char_name.lower().endswith('s')):  # Avoid plural section names
                        
                        details['main_characters'].append(char_name)
                        if len(details['main_characters']) >= 3:  # Limit to top 3
                            break

        # spaCy fallback for names
        if _NLP and len(details['main_characters']) < 3:
            # Try to find any character-like file content
            char_any_key = next((k for k in reference_files.keys() if 'character' in k), None)
            combined_chars = "\n".join((reference_files.get(char_any_key or '', '')).split('\n')[:500])
            doc = _NLP(combined_chars)
            for ent in doc.ents:
                if ent.label_ == 'PERSON' and 2 <= len(ent.text.split()) <= 4:
                    name = ent.text.strip()
                    if name not in details['main_characters']:
                        details['main_characters'].append(name)
                    if len(details['main_characters']) >= 3:
                        break
    
    def _extract_theme_details(self, details: Dict[str, Any], reference_files: Dict[str, str]):
        """Extract themes more intelligently."""
        # Accept flexible filenames for themes
        themes_key = next((k for k in reference_files.keys() if 'theme' in k or 'motif' in k), None)
        if themes_key:
            themes_content = reference_files[themes_key]
            themes_lower = themes_content.lower()
            
            # Look for explicit theme statements
            theme_keywords = ['love', 'betrayal', 'redemption', 'courage', 'sacrifice', 
                            'power', 'justice', 'revenge', 'family', 'friendship', 
                            'identity', 'growth', 'survival', 'hope', 'loss', 'fear',
                            'isolation', 'mystery', 'discovery', 'transformation']
            
            # Count frequency and take most mentioned
            theme_counts = [(keyword, themes_lower.count(keyword)) for keyword in theme_keywords]
            theme_counts.sort(key=lambda x: x[1], reverse=True)
            
            for theme, count in theme_counts[:3]:
                if count > 0:
                    details['themes'].append(theme)
    
    def _extract_mood_tone(self, details: Dict[str, Any], reference_files: Dict[str, str]):
        """Extract mood and tone more intelligently."""
        style_content = ""
        
        # Check only style/voice-specific files to avoid noisy matches from outline/theme
        for filename in reference_files.keys():
            if any(token in filename for token in ['style', 'voice', 'mood', 'palette']):
                style_content += reference_files[filename] + "\n"
        
        if style_content:
            style_lower = style_content.lower()
            
            # More nuanced mood detection
            mood_scores = {
                'dark': sum(1 for word in ['dark', 'gritty', 'somber', 'serious', 'horror', 'scary', 'ominous'] if word in style_lower),
                'light': sum(1 for word in ['light', 'humorous', 'funny', 'comedic', 'bright', 'cheerful'] if word in style_lower),
                'dramatic': sum(1 for word in ['dramatic', 'intense', 'emotional', 'powerful'] if word in style_lower),
                'mysterious': sum(1 for word in ['mysterious', 'enigmatic', 'secretive', 'mystery'] if word in style_lower),
                'romantic': sum(1 for word in ['romantic', 'passionate', 'loving', 'romance'] if word in style_lower),
                'adventurous': sum(1 for word in ['adventurous', 'exciting', 'thrilling', 'action'] if word in style_lower)
            }
            
            # Take the highest scoring mood
            if mood_scores:
                best_mood = max(mood_scores.items(), key=lambda x: x[1])
                if best_mood[1] > 0:
                    details['mood_tone'] = best_mood[0]

        # === Color palette detection (only when style/voice content exists) ===
        color_keywords = ['red', 'crimson', 'scarlet', 'blue', 'azure', 'navy', 'green', 'emerald', 'olive',
                          'purple', 'violet', 'magenta', 'yellow', 'gold', 'amber', 'orange', 'teal', 'cyan',
                          'white', 'black', 'gray', 'silver', 'brown']
        palette = []
        # Only extract a palette if there is an explicit palette marker to avoid incidental color words
        if style_content and ('palette' in style_lower or '# color palette' in style_lower or 'color palette' in style_lower):
            for word in color_keywords:
                if re.search(r"\\b" + re.escape(word) + r"\\b", style_lower):
                    palette.append(word)
                if len(palette) >= 3:
                    break
        details['color_palette'] = palette
    
    def generate_cover_prompt(self, book_details: Dict[str, Any], user_feedback: Optional[str] = None, options: Optional[Dict[str, Any]] = None, requirements: Optional[str] = None, raw_bible_excerpt: Optional[str] = None, references_digest: Optional[str] = None) -> str:
        """
        Generate a DALL-E 3 prompt for cover art based on book details.
        
        Args:
            book_details: Extracted book details
            user_feedback: Optional user feedback for regeneration
            
        Returns:
            Generated prompt string
        """
        prompt_parts = []
        
        # Start with base cover art instruction - be very explicit about 2D only
        prompt_parts.append("Create a professional 2D book cover design viewed straight-on from the front, completely flat with no 3D elements or perspective")
        # Strict grounding policy: derive everything from references; avoid assumptions
        prompt_parts.append("Ground every visual decision strictly in the provided book bible and reference files; do not invent details, settings, characters, symbols, or moods that are not supported by those materials")

        # Add optional user requirements early and give them precedence
        if requirements:
            prompt_parts.append(
                "User requirements (override genre and mood cues from references when conflicting): "
                + requirements
            )

        # Operating instructions: prioritization and how to use references
        prompt_parts.append(
            "Follow this priority of guidance: (1) user requirements (if provided), (2) book bible main content, (3) reference files. "
            "When using reference files: derive concrete visual elements only from (a) setting/world-building (environments, landscapes, architecture), (b) characters (include named characters but do not fabricate appearance details that are not specified; use non-specific silhouettes if needed), (c) themes (only symbolic elements explicitly mentioned), and (d) color palette if specified. "
            "If information is missing or ambiguous, keep the composition simple and neutral rather than assuming details. No logos or series marks. No text unless title/author options are explicitly provided."
        )

        # Add explicit grounding context (not to be rendered on image)
        if raw_bible_excerpt or references_digest:
            prompt_parts.append(
                "Grounding context (for guidance only; do NOT render any of this text on the image):"
            )
            if raw_bible_excerpt:
                prompt_parts.append(f"Book bible core excerpt: {raw_bible_excerpt}")
            if references_digest:
                prompt_parts.append(f"Reference highlights: {references_digest}")
        
        # Optionally acknowledge genre without prescribing a style
        genre = book_details.get('genre', '').lower()
        if genre:
            if requirements:
                prompt_parts.append(
                    f"Align with the story's genre: {genre}, only where it does not conflict with the user requirements"
                )
            else:
                prompt_parts.append(
                    f"The visual language should align with the story's genre: {genre}, without relying on generic tropes or preconceived aesthetics"
                )
        
        # Prefer explicit composition from spec if provided
        composition = book_details.get('composition', '')
        if composition:
            prompt_parts.append(f"Composition: {composition}")

        # Add visual elements from setting/world-building
        visual_elements = book_details.get('visual_elements', [])
        if visual_elements:
            elements_str = ', '.join(visual_elements[:3])  # Top 3 elements
            prompt_parts.append(f"featuring {elements_str}")
        else:
            # Explicitly instruct neutrality when we found no credible environment evidence
            prompt_parts.append("Use a simple, neutral background and focus on strong typography and a minimal symbolic element derived only from explicit references, if any")
        
        # Add mood/tone (neutral phrasing, no hardcoded adjectives beyond extracted label)
        # Do not inject tone descriptors automatically; tone should emerge from user requirements and reference content
        
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
        prompt_parts.append("Adhere strictly to the cultural, historical, and stylistic context present in the references; avoid adding symbols, attire, or architecture that are not supported by the provided materials")
        
        # Add user feedback if provided
        if user_feedback:
            prompt_parts.append(f"Incorporating this feedback: {user_feedback}")

        # When requirements present, they already appeared earlier with precedence

        # Handle options for title/author – ask the image model to render exact text (no invention)
        if options:
            include_title = options.get('include_title', False)
            include_author = options.get('include_author', False)
            title_text = (options.get('title_text') or '').strip()
            author_text = (options.get('author_text') or '').strip()

            if include_title and title_text:
                prompt_parts.append(
                    f"Render EXACTLY this book title text: \"{title_text}\" — case-sensitive, character-for-character, no paraphrasing, no translation, no abbreviations. Place large and readable near the upper third."
                )
            elif include_title:
                prompt_parts.append("Reserve ample space near the upper third for the book title typography.")

            if include_author and author_text:
                prompt_parts.append(
                    f"Render EXACTLY this author name: \"{author_text}\" — case-sensitive, character-for-character. Place smaller, complementary typography near the lower portion."
                )
            elif include_author:
                prompt_parts.append("Reserve subtle space near the lower portion for the author name typography.")

            if not include_title and not include_author:
                prompt_parts.append("No text on the image.")

            # Typesetting hard constraints (highest priority)
            if include_title or include_author:
                typeset_lines = ["Typesetting (MUST FOLLOW EXACTLY):"]
                if include_title and title_text:
                    typeset_lines.append(f"TitleText: {title_text}")
                if include_author and author_text:
                    typeset_lines.append(f"AuthorText: {author_text}")
                typeset_lines.append(
                    "Render only the exact strings above. Do not add subtitles, taglines, series names, punctuation, or any extra words."
                )
                typeset_lines.append(
                    "If any instruction conflicts, prioritize rendering these exact strings over all other instructions. Do not translate, localize, or stylistically modify the characters."
                )
                prompt_parts.append(' '.join(typeset_lines))

            # Repeat as a final checklist at the end to maximize adherence
            if include_title or include_author:
                checklist = ["Final typesetting checklist (repeat):"]
                if include_title and title_text:
                    checklist.append(f"TitleText: {title_text}")
                if include_author and author_text:
                    checklist.append(f"AuthorText: {author_text}")
                checklist.append("Render only these exact strings. No other words anywhere on the cover.")
                prompt_parts.append(' '.join(checklist))

        # Critical: ONLY the front cover, no 3D book mockup
        prompt_parts.append("IMPORTANT: Create ONLY the flat front cover design as if looking straight at it from the front. NO 3D perspective, NO physical book object, NO spine visible, NO back cover, NO thickness, NO depth, NO mockup presentation. This should be a completely flat 2D cover design that fills the entire frame edge-to-edge, as if it were printed on paper and photographed straight-on.")

        # Color palette guidance (only if palette was explicitly derived from style/voice files)
        if book_details.get('color_palette'):
            palette_str = ', '.join(book_details['color_palette'])
            prompt_parts.append(f"Primary color palette (only if explicitly specified in style/voice references): {palette_str}")
        
        # Join all parts
        full_prompt = '. '.join(prompt_parts) + '.'
        
        # Ensure prompt isn't too long
        if len(full_prompt) > 1800:
            full_prompt = full_prompt[:1800] + '...'
        
        logger.info(f"Generated cover art prompt: {full_prompt[:200]}...")
        return full_prompt
    
    async def generate_cover_image(self, prompt: str) -> Tuple[str, bytes]:
        """
        Generate cover image using OpenAI GPT-image-1 (primary) or DALL-E 3 (fallback).
        
        Args:
            prompt: Text prompt for image generation
            
        Returns:
            Tuple of (image_url, image_bytes)
        """
        if not self.openai_client:
            raise RuntimeError("OpenAI client not available")
        
        try:
            logger.info("Starting AI image generation with GPT-image-1 (no fallback)")
            logger.info(f"Using prompt: {prompt}")

            # GPT-image-1 only
            logger.info("Attempting GPT-image-1 generation...")
            if self.billable_client:
                # Use billable client
                async with semaphore(get_image_semaphore()):
                    billable_response = await self.openai_client.images_generate(
                        model="gpt-image-1",
                        prompt=prompt,
                        size="1024x1536",  # Portrait (closest allowed)
                        quality="high",  # GPT-image-1 uses 'high' instead of 'hd'
                        n=1
                        # Note: GPT-image-1 doesn't support response_format parameter
                    )
                response = billable_response.response
                credits_charged = billable_response.credits_charged
                logger.info(f"GPT-image-1 generation successful! Credits charged: {credits_charged}")
            else:
                # Use regular client (wrap sync call in threadpool and guard with thread semaphore)
                import functools
                with thread_semaphore(get_image_thread_semaphore()):
                    response = await asyncio.to_thread(
                        functools.partial(
                            self.openai_client.images.generate,
                            model="gpt-image-1",
                            prompt=prompt,
                            size="1024x1536",  # Portrait (closest allowed)
                            quality="high",  # GPT-image-1 uses 'high' instead of 'hd'
                            n=1
                        )
                    )
                logger.info("GPT-image-1 generation successful!")
            
            data_item = response.data[0]
            # Determine whether we got a URL (DALL-E 3) or b64_json (GPT-image-1)
            if getattr(data_item, 'b64_json', None):
                import base64
                logger.info("Received base64 image data from GPT-image-1")
                image_bytes = base64.b64decode(data_item.b64_json)
                image_url = None  # Will be set after upload to Firebase
            else:
                image_url = data_item.url
                logger.info(f"AI generated image URL: {image_url}")
                # Safety checker: log revised prompt (DALL-E 3 feature)
                if getattr(data_item, 'revised_prompt', None):
                    logger.warning(f"OpenAI revised prompt: {data_item.revised_prompt}")
                logger.info("Downloading generated image from OpenAI...")
                image_response = requests.get(image_url, timeout=60)
                image_response.raise_for_status()
                image_bytes = image_response.content
                logger.info(f"Downloaded image: {len(image_bytes)} bytes")
            
            # Process image to meet KDP specifications
            logger.info("Processing image for KDP specifications...")
            processed_bytes = await self._process_image_for_kdp(image_bytes)
            
            logger.info(f"Generated and processed cover image ({len(processed_bytes)} bytes)")
            return image_url, processed_bytes
            
        except Exception as e:
            logger.error(f"Failed to generate cover image: {e}")
            logger.error(f"OpenAI client available: {self.openai_client is not None}")
            logger.error(f"OpenAI API key configured: {os.getenv('OPENAI_API_KEY') is not None}")
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

    def _overlay_text(self, image_bytes: bytes, title_text: Optional[str], author_text: Optional[str]) -> bytes:
        """Overlay title and author text onto the image using PIL.
        Tries common system fonts; falls back to PIL's default font.
        """
        try:
            image = Image.open(io.BytesIO(image_bytes)).convert('RGB')
            from PIL import ImageDraw, ImageFont

            draw = ImageDraw.Draw(image)
            width, height = image.size

            # Try to load a decent sans-serif font; fallback to default
            font_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            ]
            title_font = None
            author_font = None
            for path in font_paths:
                try:
                    title_font = ImageFont.truetype(path, size=max(36, height // 18))
                    author_font = ImageFont.truetype(path, size=max(24, height // 28))
                    break
                except Exception:
                    continue
            if title_font is None:
                title_font = ImageFont.load_default()
                author_font = ImageFont.load_default()

            # Helper to draw text with outline for readability
            def draw_text_centered(y_pos: int, text: str, font, pad_y: int = 10):
                if not text:
                    return
                text_bbox = draw.textbbox((0, 0), text, font=font)
                text_w = text_bbox[2] - text_bbox[0]
                text_h = text_bbox[3] - text_bbox[1]
                x = (width - text_w) // 2
                y = y_pos
                # Semi-transparent dark rectangle behind text
                rect_pad = 14
                rect = [x - rect_pad, y - rect_pad, x + text_w + rect_pad, y + text_h + rect_pad]
                draw.rectangle(rect, fill=(0, 0, 0, 160))
                # Text (white)
                draw.text((x, y), text, font=font, fill=(255, 255, 255))
                return y + text_h + pad_y

            current_y = height // 8
            if title_text:
                current_y = draw_text_centered(current_y, title_text, title_font, pad_y=height // 40)
            if author_text:
                # Place near lower portion if title exists; else keep upper third
                if title_text:
                    current_y = int(height * 0.78)
                draw_text_centered(current_y, author_text, author_font, pad_y=0)

            output = io.BytesIO()
            image.save(output, format='JPEG', quality=95, optimize=True)
            return output.getvalue()
        except Exception as e:
            logger.error(f"Failed to overlay text: {e}")
            return image_bytes

    def _render_cover_programmatically(
        self,
        book_bible_content: str,
        reference_files: Dict[str, str],
        book_details: Dict[str, Any],
        options: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """Render a clean, minimalistic cover using PIL only, avoiding image model hallucinations.
        Uses palette if available and draws a simple motif if industrial/factory cues are present.
        """
        try:
            width = KDP_COVER_SPECS["ideal_width"]
            height = KDP_COVER_SPECS["ideal_height"]
            from PIL import ImageDraw

            # Determine palette
            palette = book_details.get('color_palette') or []
            # Default palette suitable for industrial theme
            default_palette = [(25, 28, 36), (230, 90, 40), (240, 240, 240)]  # dark slate, orange, light gray
            colors: List[Tuple[int, int, int]] = []
            named = {
                'red': (200, 60, 60), 'blue': (60, 90, 200), 'green': (60, 160, 90), 'purple': (120, 70, 160),
                'yellow': (220, 190, 60), 'orange': (230, 120, 50), 'teal': (40, 150, 150), 'black': (10, 10, 10),
                'white': (245, 245, 245), 'gray': (120, 120, 120), 'brown': (120, 85, 60)
            }
            for name in palette[:3]:
                rgb = named.get(str(name).lower().strip())
                if rgb:
                    colors.append(rgb)
            if not colors:
                colors = default_palette[:2]

            # Build base image with vertical gradient
            base = Image.new('RGB', (width, height), colors[0])
            draw = ImageDraw.Draw(base)
            top = colors[0]
            bottom = colors[1] if len(colors) > 1 else colors[0]
            for y in range(height):
                ratio = y / max(1, height - 1)
                r = int(top[0] * (1 - ratio) + bottom[0] * ratio)
                g = int(top[1] * (1 - ratio) + bottom[1] * ratio)
                b = int(top[2] * (1 - ratio) + bottom[2] * ratio)
                draw.line([(0, y), (width, y)], fill=(r, g, b))

            # Decide motif from content
            combined = (book_bible_content or "") + "\n" + "\n".join((reference_files or {}).values())
            cl = combined.lower()
            industrial_terms = ['factory', 'industrial', 'plant', 'wastewater', 'rendering', 'pipe', 'smokestack']
            has_industrial = any(t in cl for t in industrial_terms)

            # Draw simple motif
            fg = (240, 240, 240) if (sum(colors[0]) < 360) else (30, 30, 30)
            if has_industrial:
                # Factory silhouette: rectangles + chimneys + pipes
                ground_y = int(height * 0.68)
                draw.rectangle([0, ground_y, width, height], fill=(0, 0, 0, 60))
                # Buildings
                b1 = [int(width * 0.12), ground_y - int(height * 0.18), int(width * 0.32), ground_y]
                b2 = [int(width * 0.34), ground_y - int(height * 0.25), int(width * 0.56), ground_y]
                b3 = [int(width * 0.58), ground_y - int(height * 0.15), int(width * 0.75), ground_y]
                for box in (b1, b2, b3):
                    draw.rectangle(box, fill=(40, 40, 40))
                # Chimneys
                ch1 = [int(width * 0.38), ground_y - int(height * 0.38), int(width * 0.42), ground_y - int(height * 0.25)]
                ch2 = [int(width * 0.44), ground_y - int(height * 0.34), int(width * 0.48), ground_y - int(height * 0.25)]
                draw.rectangle(ch1, fill=(50, 50, 50))
                draw.rectangle(ch2, fill=(50, 50, 50))
                # Pipes
                draw.line([(int(width * 0.20), ground_y - int(height * 0.08)), (int(width * 0.55), ground_y - int(height * 0.08))], fill=fg, width=6)
                draw.line([(int(width * 0.55), ground_y - int(height * 0.08)), (int(width * 0.55), ground_y - int(height * 0.02))], fill=fg, width=6)
            else:
                # Minimal diagonal band
                band_color = (fg[0], fg[1], fg[2])
                band_height = int(height * 0.12)
                for offset in range(-band_height // 2, band_height // 2):
                    y = int(height * 0.55) + offset
                    draw.line([(int(width * 0.1), y - int(width * 0.2)), (int(width * 0.9), y + int(width * 0.2))], fill=band_color, width=3)

            # Add text overlay
            title_txt = (options or {}).get('title_text') if (options or {}).get('include_title') else ''
            author_txt = (options or {}).get('author_text') if (options or {}).get('include_author') else ''
            bytes_out = io.BytesIO()
            base.save(bytes_out, format='JPEG', quality=95, optimize=True)
            composed = self._overlay_text(bytes_out.getvalue(), (title_txt or '').strip(), (author_txt or '').strip())
            return composed
        except Exception as e:
            logger.error(f"Failed to render programmatic cover: {e}")
            # Fallback to a plain background
            return Image.new('RGB', (KDP_COVER_SPECS["ideal_width"], KDP_COVER_SPECS["ideal_height"]), (30, 30, 30)).tobytes()
    
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
            # Create storage path with timestamp and random suffix for cache busting
            import random
            import string
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
            filename = f"cover-art/{project_id}/{job_id}_{timestamp}_{random_suffix}.jpg"
            
            logger.info(f"Uploading to Firebase Storage: {filename}")
            
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
            logger.info(f"Public URL: {public_url}")
            return public_url
            
        except Exception as e:
            logger.error(f"Failed to upload to Firebase Storage: {e}")
            raise
    
    async def generate_cover_art(self, project_id: str, user_id: str, 
                                book_bible_content: str, reference_files: Dict[str, str],
                                user_feedback: Optional[str] = None,
                                options: Optional[Dict[str, Any]] = None,
                                job_id: Optional[str] = None,
                                requirements: Optional[str] = None) -> CoverArtJob:
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
            book_details = self.extract_book_details(book_bible_content, reference_files, ui_options=options or {})
            # Step 1b: Generate explicit visual spec and merge conservatively
            spec = await self._generate_visual_spec(book_bible_content, reference_files, options or {})
            if spec:
                try:
                    ve = spec.get('visual_elements') or []
                    if isinstance(ve, list) and ve:
                        book_details['visual_elements'] = [str(x)[:24] for x in ve][:6]
                    palette = spec.get('palette') or []
                    if isinstance(palette, list) and palette:
                        book_details['color_palette'] = [str(x)[:16] for x in palette][:4]
                    mood = spec.get('mood')
                    if isinstance(mood, str) and mood:
                        book_details['mood_tone'] = mood[:16]
                    comp = spec.get('composition')
                    if isinstance(comp, str) and comp:
                        book_details['composition'] = comp[:200]
                    logger.info(f"Visual spec merged: {spec}")
                except Exception:
                    pass
            
            # Step 2: Generate prompt, with explicit grounding excerpts to discourage model hallucinations
            logger.info(f"Generating cover art prompt for project {project_id}")
            bible_excerpt = (book_bible_content or "")[:400]
            try:
                ref_parts = []
                for name, content in (reference_files or {}).items():
                    if not content:
                        continue
                    ref_parts.append(f"{name}: {content[:120]}")
                references_digest = "; ".join(ref_parts)[:400]
            except Exception:
                references_digest = None

            prompt = self.generate_cover_prompt(
                book_details,
                user_feedback,
                options,
                requirements,
                raw_bible_excerpt=bible_excerpt,
                references_digest=references_digest
            )
            job.prompt = prompt
            
            # Step 3: Generate image (GPT-image-1 only; no fallback)
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