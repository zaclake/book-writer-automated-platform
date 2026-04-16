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

    @staticmethod
    def _get_genre_art_direction(genre: str) -> str:
        """Return marketing-informed cover design guidance for a given genre."""
        genre_lower = (genre or '').lower().strip()

        directions = {
            'romance': (
                "Romance covers that sell feature close-up figures (one or two people) with warm, "
                "intimate lighting and soft-focus or lush painterly backgrounds. Palettes lean warm: "
                "golds, deep reds, blush pinks, sunset tones. Photorealistic or oil-painting styles "
                "dominate the market. Composition centers the figure(s) with a scenic or atmospheric "
                "backdrop (beach, garden, city at dusk). Typography is elegant script or refined serif."
            ),
            'thriller': (
                "Thriller/suspense covers use high contrast and a limited dark palette with one bold "
                "accent color (red, electric blue, amber). Compositions favor a lone figure, an object "
                "under dramatic directional lighting, or a striking urban/desolate landscape shot from "
                "a cinematic angle. Photorealistic or gritty textured styles work best. Typography is "
                "bold, oversized sans-serif or stencil. Atmosphere should feel tense and urgent."
            ),
            'suspense': (
                "Thriller/suspense covers use high contrast and a limited dark palette with one bold "
                "accent color (red, electric blue, amber). Compositions favor a lone figure, an object "
                "under dramatic directional lighting, or a striking urban/desolate landscape shot from "
                "a cinematic angle. Photorealistic or gritty textured styles work best. Typography is "
                "bold, oversized sans-serif or stencil. Atmosphere should feel tense and urgent."
            ),
            'fantasy': (
                "Fantasy covers feature sweeping, epic compositions: vast landscapes, dramatic skies, "
                "towering architecture, or a central heroic figure. Rich saturated colors (deep blues, "
                "purples, golds, emerald greens) dominate. Illustrated or digital-painting styles are "
                "the standard. Magical elements (glowing runes, ethereal light, mythical creatures) add "
                "genre signaling. Typography is ornate, bold serif or custom fantasy lettering."
            ),
            'science fiction': (
                "Sci-fi covers lean cinematic: cool palettes (teals, steel blues, deep space blacks with "
                "neon accents), sleek technological elements, vast space or futuristic cityscapes. "
                "Photorealistic CGI or digital-art styles dominate. Composition often features a figure "
                "dwarfed by scale, a ship, or an alien landscape. Typography is clean, modern sans-serif "
                "or futuristic display type."
            ),
            'mystery': (
                "Mystery covers use moody, atmospheric scenes: foggy streets, dimly lit interiors, "
                "obscured or partially revealed objects. Palettes are muted and dark with one accent "
                "color drawing the eye. Photorealistic or noir-tinged illustrative styles work well. "
                "Composition suggests something hidden -- partial views, doorways, shadows. Typography "
                "is clean serif or understated sans-serif."
            ),
            'horror': (
                "Horror covers feature unsettling, atmospheric imagery: abandoned spaces, distorted "
                "figures, eerie natural settings, or visceral close-ups. Palettes are heavily desaturated "
                "with one shock color (blood red, sickly green). Gritty, textured, or photorealistic "
                "styles create dread. Typography is distressed, cracked, or handwritten-style. Negative "
                "space and darkness are used aggressively."
            ),
            'historical': (
                "Historical fiction covers evoke the era through period-appropriate visual elements: "
                "architecture, clothing, landscapes, artifacts. Painterly, oil-painting, or sepia-toned "
                "photorealistic styles dominate. Warm earthy palettes (ochre, sienna, aged gold, deep "
                "greens) suggest authenticity. A single figure in period dress or a sweeping landscape "
                "establishes setting. Typography uses classic serif fonts."
            ),
            'literary fiction': (
                "Literary fiction covers favor abstract, minimalist, or conceptual design. They may be "
                "typography-forward with a single striking visual element, or use fine-art photography "
                "or illustration. Muted, sophisticated palettes (dusty pastels, earth tones, monochrome "
                "with one accent). The design signals intelligence and artistry over genre tropes. "
                "Typography is refined -- elegant serif or modern minimalist."
            ),
            'young adult': (
                "YA covers are vibrant, bold, and eye-catching. Dynamic compositions with strong central "
                "imagery (a figure in action, a symbolic object, a dramatic landscape). Bright, saturated "
                "color palettes or striking high-contrast designs. Stylized illustration, vector art, or "
                "bold photographic treatments. Typography is large, impactful, and often integrated into "
                "the artwork. Energy and emotion are paramount."
            ),
            'contemporary': (
                "Contemporary fiction covers range from clean photographic designs to modern illustration. "
                "They often use a single compelling image (an object, a scene, a candid figure) with "
                "generous whitespace. Palettes are modern and fresh. Photography-based, collage, or "
                "clean graphic design styles work well. Typography is clean and contemporary -- often "
                "the dominant design element."
            ),
            'children': (
                "Children's book covers are bright, colorful, and inviting with charming illustrated "
                "characters and whimsical scenes. Bold, saturated primary and secondary colors. "
                "Illustration styles range from watercolor to digital cartoon to hand-drawn. Characters "
                "are expressive and engaging. Typography is playful, rounded, and highly readable."
            ),
        }

        if genre_lower in directions:
            return directions[genre_lower]

        for key, direction in directions.items():
            if key in genre_lower or genre_lower in key:
                return direction

        return (
            "Design a distinctive, professional book cover. Choose an art style (photorealistic, "
            "illustrated, painterly, minimalist, or graphic) that best matches the story's tone. "
            "Use a strong focal point, a cohesive color palette, and a composition that reads well "
            "at both full size and thumbnail. Make bold creative choices rather than defaulting to "
            "generic imagery."
        )

    async def _generate_creative_brief(
        self,
        book_bible_content: str,
        reference_files: Dict[str, str],
        genre: str = '',
        ui_options: Optional[Dict[str, Any]] = None,
        vector_context: Optional[str] = None,
        requirements: Optional[str] = None,
        user_feedback: Optional[str] = None,
        previous_prompt: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Use an LLM to produce a rich, genre-aware creative brief for cover art.

        Returns a dict with keys: art_style, composition, color_palette,
        key_visual_elements, mood, typography_style, what_to_avoid, scene_description.
        """
        if not self.openai_client:
            return None
        try:
            bible_excerpt = (book_bible_content or "")[:2500]

            ref_snippets: List[str] = []
            for name, content in (reference_files or {}).items():
                if not content:
                    continue
                ref_snippets.append(f"--- {name} ---\n{content[:400]}")
                if len(ref_snippets) >= 6:
                    break
            refs_joined = "\n\n".join(ref_snippets)

            title_txt = (ui_options or {}).get('title_text') or ''
            author_txt = (ui_options or {}).get('author_text') or ''

            genre_direction = self._get_genre_art_direction(genre)

            system_msg = (
                "You are an award-winning book cover designer and art director with deep knowledge "
                "of what sells across every genre. Your job is to produce a vivid, specific creative "
                "brief for a book cover image.\n\n"
                "You must make bold, distinctive creative choices. Every book deserves a unique cover "
                "that could not be confused with any other. Avoid generic or safe defaults.\n\n"
                "Output valid JSON only with these keys:\n"
                "- art_style: The rendering style (e.g. 'cinematic photorealistic', 'lush oil painting', "
                "'stylized digital illustration', 'moody noir photography', 'watercolor wash', "
                "'minimalist graphic design', 'detailed fantasy illustration'). Be specific.\n"
                "- composition: A detailed 2-3 sentence description of the layout, focal point, "
                "perspective, and spatial arrangement.\n"
                "- color_palette: List of 3-5 specific colors (e.g. 'deep crimson', 'weathered gold', "
                "'midnight navy' -- not just 'red', 'blue').\n"
                "- key_visual_elements: List of 4-8 concrete visual elements to include, described "
                "vividly (e.g. 'a crumbling stone archway overgrown with ivy' not just 'archway').\n"
                "- mood: A 2-4 word evocative mood phrase (e.g. 'haunting intimacy', 'electric tension').\n"
                "- typography_style: Suggested type treatment if text is included (e.g. 'bold distressed "
                "sans-serif', 'elegant gold foil script').\n"
                "- what_to_avoid: List of 2-4 things to explicitly avoid for this particular book.\n"
                "- scene_description: A single vivid paragraph (3-5 sentences) describing exactly what "
                "the cover image should depict, as if briefing a painter. This is the most important field."
            )

            requirements_block = ""
            if requirements:
                requirements_block = (
                    f"\n\nUSER REQUIREMENTS (HIGHEST PRIORITY -- these override genre conventions "
                    f"and all other considerations):\n{requirements}\n"
                )

            feedback_block = ""
            if user_feedback and previous_prompt:
                feedback_block = (
                    f"\n\nPREVIOUS ATTEMPT:\nThe previous cover used this prompt: {previous_prompt[:500]}\n"
                    f"User feedback on that attempt: {user_feedback}\n"
                    f"Adjust the brief to address this feedback while keeping what worked.\n"
                )
            elif user_feedback:
                feedback_block = (
                    f"\n\nUSER FEEDBACK on previous cover: {user_feedback}\n"
                    f"Adjust the brief to address this feedback.\n"
                )

            vector_block = ""
            if vector_context:
                vector_block = f"\n\nAdditional context from project memory:\n{vector_context}\n"

            user_msg = (
                f"Title: {title_txt}\nAuthor: {author_txt}\n"
                f"Genre: {genre or 'Not specified'}\n\n"
                f"GENRE MARKETING GUIDANCE:\n{genre_direction}\n\n"
                f"BOOK BIBLE:\n{bible_excerpt}\n\n"
                f"REFERENCE FILES:\n{refs_joined}\n"
                f"{vector_block}"
                f"{requirements_block}"
                f"{feedback_block}"
                "\nProduce a creative brief that would result in a cover that stands out on a "
                "bookstore shelf and clearly signals the genre to the target reader. Make specific, "
                "bold choices -- never generic."
            )

            if self.billable_client:
                async with semaphore(get_image_semaphore()):
                    billable_response = await self.openai_client.chat_completions_create(
                        model=os.getenv("DEFAULT_AI_MODEL", "gpt-4o"),
                        messages=[
                            {"role": "system", "content": system_msg},
                            {"role": "user", "content": user_msg},
                        ],
                        temperature=0.7,
                        max_tokens=800,
                        timeout=90
                    )
                response = billable_response.response
            else:
                import functools
                with thread_semaphore(get_image_thread_semaphore()):
                    response = await asyncio.to_thread(
                        functools.partial(
                            getattr(self.openai_client.chat.completions, "create"),
                            model=os.getenv("DEFAULT_AI_MODEL", "gpt-4o"),
                            messages=[
                                {"role": "system", "content": system_msg},
                                {"role": "user", "content": user_msg},
                            ],
                            temperature=0.7,
                            max_tokens=800,
                            timeout=90
                        )
                    )

            content = response.choices[0].message.content
            raw = content.strip()
            if raw.startswith("```"):
                raw = re.sub(r'^```(?:json)?\s*', '', raw)
                raw = re.sub(r'\s*```$', '', raw)
            import json as _json
            brief = _json.loads(raw)
            if not isinstance(brief, dict):
                return None
            logger.info(f"Creative brief generated: {list(brief.keys())}")
            return brief
        except Exception as e:
            logger.error(f"Failed to generate creative brief: {e}")
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
    
    def generate_cover_prompt(
        self,
        creative_brief: Optional[Dict[str, Any]] = None,
        book_details: Optional[Dict[str, Any]] = None,
        user_feedback: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
        requirements: Optional[str] = None,
    ) -> str:
        """Build the image-generation prompt from the LLM creative brief.

        Falls back to ``book_details`` (regex-extracted) when the creative brief
        is unavailable.
        """
        prompt_parts: List[str] = []

        # --- User requirements always come first when provided ---
        if requirements:
            prompt_parts.append(
                f"PRIMARY DIRECTIVE -- the following user requirements take absolute precedence "
                f"over every other instruction: {requirements}"
            )

        # --- Scene description (the creative core) ---
        if creative_brief and creative_brief.get('scene_description'):
            prompt_parts.append(creative_brief['scene_description'])

        # --- Art style ---
        if creative_brief and creative_brief.get('art_style'):
            prompt_parts.append(f"Render in this style: {creative_brief['art_style']}")
        elif not creative_brief:
            prompt_parts.append("Create a striking, professional book cover")

        # --- Composition ---
        if creative_brief and creative_brief.get('composition'):
            prompt_parts.append(f"Composition: {creative_brief['composition']}")
        elif book_details and book_details.get('composition'):
            prompt_parts.append(f"Composition: {book_details['composition']}")

        # --- Key visual elements ---
        if creative_brief and creative_brief.get('key_visual_elements'):
            elements = creative_brief['key_visual_elements']
            if isinstance(elements, list):
                prompt_parts.append("Key visual elements: " + '; '.join(str(e) for e in elements[:8]))
        elif book_details:
            visual_elements = book_details.get('visual_elements', [])
            if visual_elements:
                prompt_parts.append("featuring " + ', '.join(visual_elements[:4]))

        # --- Color palette ---
        if creative_brief and creative_brief.get('color_palette'):
            palette = creative_brief['color_palette']
            if isinstance(palette, list):
                prompt_parts.append("Color palette: " + ', '.join(str(c) for c in palette[:5]))
        elif book_details and book_details.get('color_palette'):
            prompt_parts.append("Color palette: " + ', '.join(book_details['color_palette']))

        # --- Mood ---
        if creative_brief and creative_brief.get('mood'):
            prompt_parts.append(f"The overall mood is {creative_brief['mood']}")
        elif book_details and book_details.get('mood_tone'):
            prompt_parts.append(f"The overall mood is {book_details['mood_tone']}")

        # --- What to avoid ---
        if creative_brief and creative_brief.get('what_to_avoid'):
            avoids = creative_brief['what_to_avoid']
            if isinstance(avoids, list):
                prompt_parts.append("Avoid: " + '; '.join(str(a) for a in avoids[:4]))

        # --- Fallback character / theme injection when no creative brief ---
        if not creative_brief and book_details:
            characters = book_details.get('main_characters', [])
            if characters:
                prompt_parts.append(f"featuring {characters[0]}")
            themes = book_details.get('themes', [])
            if themes:
                prompt_parts.append(f"conveying themes of {', '.join(themes[:2])}")

        # --- User feedback (regeneration) ---
        if user_feedback:
            prompt_parts.append(f"Incorporating this feedback from the user: {user_feedback}")

        # --- Typography ---
        include_title_opt = bool((options or {}).get('include_title'))
        include_author_opt = bool((options or {}).get('include_author'))
        title_text_opt = ((options or {}).get('title_text') or '').strip()
        author_text_opt = ((options or {}).get('author_text') or '').strip()

        if include_title_opt or include_author_opt:
            prompt_parts.append(
                "Render ONLY the exact text strings provided below on the cover. "
                "Do not invent, paraphrase, or add ANY other text (no subtitles, taglines, "
                "logos, publisher marks, or series names). No quotation marks around the text. "
                "Use standard Latin letters only."
            )
            if include_title_opt and title_text_opt:
                prompt_parts.append(f'Title (render exactly): {title_text_opt}')
            if include_author_opt and author_text_opt:
                prompt_parts.append(f'Author (render exactly): {author_text_opt}')

            typography_style = ''
            if creative_brief and creative_brief.get('typography_style'):
                typography_style = creative_brief['typography_style']
            prompt_parts.append(
                f"Typography: high-contrast, clean, legible. "
                f"{typography_style + '. ' if typography_style else ''}"
                f"No other text anywhere on the cover."
            )
        else:
            prompt_parts.append("Do NOT render any text anywhere on the image.")

        # --- Technical: flat front cover, portrait orientation ---
        prompt_parts.append(
            "Portrait orientation book cover (aspect ratio ~1.6:1). "
            "Must read clearly at both full size and thumbnail."
        )
        prompt_parts.append(
            "IMPORTANT: Create ONLY the flat front cover design viewed straight-on. "
            "NO 3D perspective, NO physical book object, NO spine, NO back cover, "
            "NO thickness, NO depth, NO mockup. Completely flat 2D design filling "
            "the entire frame edge-to-edge."
        )

        full_prompt = '. '.join(prompt_parts) + '.'

        if len(full_prompt) > 4000:
            full_prompt = full_prompt[:3997] + '...'

        logger.info(f"Generated cover art prompt ({len(full_prompt)} chars): {full_prompt[:200]}...")
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
        """Overlay title and author text onto the image using PIL with alpha-safe compositing.
        - Loads a readable sans-serif font
        - Fits text within safe margins
        - Draws semi-transparent background plates for contrast
        """
        try:
            from PIL import ImageDraw, ImageFont
            base = Image.open(io.BytesIO(image_bytes)).convert('RGBA')
            width, height = base.size

            # Try to load a decent sans-serif font; fallback to default
            font_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            ]
            def load_font(target_size: int):
                for path in font_paths:
                    try:
                        return ImageFont.truetype(path, size=max(16, target_size))
                    except Exception:
                        continue
                return ImageFont.load_default()

            # Dynamic font sizing to fit width
            def fit_text_to_width(draw: ImageDraw.ImageDraw, text: str, max_width: int, max_size: int, min_size: int = 16):
                size = max_size
                font = load_font(size)
                # Shrink font until it fits or reaches min_size
                while size > min_size:
                    bbox = draw.textbbox((0, 0), text, font=font)
                    if (bbox[2] - bbox[0]) <= max_width:
                        break
                    size -= 2
                    font = load_font(size)
                return font

            def wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> List[str]:
                # Simple greedy word wrap
                words = str(text).split()
                if not words:
                    return []
                lines: List[str] = []
                current = words[0]
                for word in words[1:]:
                    candidate = current + ' ' + word
                    bbox = draw.textbbox((0, 0), candidate, font=font)
                    if (bbox[2] - bbox[0]) <= max_width:
                        current = candidate
                    else:
                        lines.append(current)
                        current = word
                lines.append(current)
                return lines

            # Layer for drawing with alpha
            overlay = Image.new('RGBA', base.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(overlay)

            side_margin = int(width * 0.08)
            max_text_width = width - side_margin * 2

            # Title at upper third
            y = int(height * 0.14)
            if title_text:
                # Fit font and allow multi-line wrapping
                title_font = fit_text_to_width(draw, title_text, max_text_width, max(height // 10, 36))
                title_lines = wrap_text(draw, title_text, title_font, max_text_width)
                # Compute block dimensions
                line_bboxes = [draw.textbbox((0, 0), ln, font=title_font) for ln in title_lines]
                line_heights = [(b[3] - b[1]) for b in line_bboxes]
                text_height = sum(line_heights) + max(8, height // 120) * (len(title_lines) - 1)
                text_width = max((b[2] - b[0]) for b in line_bboxes) if line_bboxes else 0
                x = (width - text_width) // 2
                pad = 18
                # Background plate
                draw.rectangle([x - pad, y - pad, x + text_width + pad, y + text_height + pad], fill=(0, 0, 0, 168))
                # Render lines centered
                line_y = y
                for ln, lh in zip(title_lines, line_heights):
                    lb = draw.textbbox((0, 0), ln, font=title_font)
                    lw = lb[2] - lb[0]
                    lx = (width - lw) // 2
                    draw.text((lx, line_y), ln, font=title_font, fill=(255, 255, 255, 255))
                    line_y += lh + max(8, height // 120)
                y = y + text_height + max(12, height // 60)

            # Author near lower portion
            if author_text:
                y_author = int(height * 0.80)
                author_font = fit_text_to_width(draw, author_text, max_text_width, max(height // 16, 24))
                author_lines = wrap_text(draw, author_text, author_font, max_text_width)
                abbs = [draw.textbbox((0, 0), ln, font=author_font) for ln in author_lines]
                a_heights = [(b[3] - b[1]) for b in abbs]
                block_h = sum(a_heights) + max(6, height // 160) * (len(author_lines) - 1)
                block_w = max((b[2] - b[0]) for b in abbs) if abbs else 0
                ax = (width - block_w) // 2
                apad = 14
                draw.rectangle([ax - apad, y_author - apad, ax + block_w + apad, y_author + block_h + apad], fill=(0, 0, 0, 148))
                line_y = y_author
                for ln, lh in zip(author_lines, a_heights):
                    lb = draw.textbbox((0, 0), ln, font=author_font)
                    lw = lb[2] - lb[0]
                    lx = (width - lw) // 2
                    draw.text((lx, line_y), ln, font=author_font, fill=(255, 255, 255, 255))
                    line_y += lh + max(6, height // 160)

            composed = Image.alpha_composite(base, overlay).convert('RGB')
            out = io.BytesIO()
            composed.save(out, format='JPEG', quality=95, dpi=(300, 300), optimize=True)
            return out.getvalue()
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
            try:
                fallback = Image.new(
                    'RGB',
                    (KDP_COVER_SPECS["ideal_width"], KDP_COVER_SPECS["ideal_height"]),
                    (30, 30, 30)
                )
                out = io.BytesIO()
                fallback.save(out, format='JPEG', quality=90, dpi=(300, 300), optimize=True)
                return out.getvalue()
            except Exception:
                return b""
    
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
    
    async def generate_cover_art(
        self,
        project_id: str,
        user_id: str,
        book_bible_content: str,
        reference_files: Dict[str, str],
        user_feedback: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
        job_id: Optional[str] = None,
        requirements: Optional[str] = None,
        vector_context: Optional[str] = None
    ) -> CoverArtJob:
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
            # Step 1: Detect genre via lightweight extraction (needed for creative brief)
            logger.info(f"Extracting book details for project {project_id}")
            book_details = self.extract_book_details(book_bible_content, reference_files, ui_options=options or {})
            detected_genre = book_details.get('genre', '')

            # Step 2: Generate LLM creative brief (primary path)
            logger.info(f"Generating creative brief for project {project_id}")
            creative_brief = await self._generate_creative_brief(
                book_bible_content,
                reference_files,
                genre=detected_genre,
                ui_options=options or {},
                vector_context=vector_context,
                requirements=requirements,
                user_feedback=user_feedback,
                previous_prompt=job.prompt if user_feedback else None
            )
            if creative_brief:
                logger.info(f"Creative brief generated successfully for project {project_id}")
            else:
                logger.warning(f"Creative brief failed for project {project_id}, falling back to regex extraction")

            # Step 3: Build the image prompt
            logger.info(f"Generating cover art prompt for project {project_id}")

            resolved_options = {}
            include_title = bool((options or {}).get('include_title'))
            include_author = bool((options or {}).get('include_author'))
            title_text = ((options or {}).get('title_text') or book_details.get('title') or '').strip()
            author_text = ((options or {}).get('author_text') or '').strip()
            resolved_options['include_title'] = include_title and bool(title_text)
            resolved_options['include_author'] = include_author and bool(author_text)
            resolved_options['title_text'] = title_text if resolved_options['include_title'] else ''
            resolved_options['author_text'] = author_text if resolved_options['include_author'] else ''

            prompt = self.generate_cover_prompt(
                creative_brief=creative_brief,
                book_details=book_details if not creative_brief else None,
                user_feedback=user_feedback,
                options=resolved_options,
                requirements=requirements,
            )
            job.prompt = prompt
            
            # Step 4: Generate image (GPT-image-1 only; no fallback)
            logger.info(f"Generating cover image for project {project_id}")
            original_url, image_bytes = await self.generate_cover_image(prompt)
            
            # Step 5: Upload to Firebase
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