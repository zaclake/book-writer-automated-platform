#!/usr/bin/env python3
"""
Audiobook Generation Service

Generates audiobooks from book chapters using ElevenLabs Text-to-Speech API.
Handles chapter-by-chapter generation, MP3 concatenation, and Firebase Storage upload.
"""

import os
import io
import json
import logging
import asyncio
import tempfile
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple, Callable
from dataclasses import dataclass

import firebase_admin
from firebase_admin import storage

logger = logging.getLogger(__name__)

# Optional ElevenLabs SDK
try:
    from elevenlabs.client import ElevenLabs
    _ELEVENLABS_AVAILABLE = True
except ImportError:
    ElevenLabs = None
    _ELEVENLABS_AVAILABLE = False

# Optional pydub for audio concatenation
try:
    from pydub import AudioSegment
    _PYDUB_AVAILABLE = True
except ImportError:
    AudioSegment = None
    _PYDUB_AVAILABLE = False

# Text preparation
try:
    from backend.services.audiobook_text_prep import (
        prepare_chapter, detect_abbreviations, estimate_characters,
    )
except ImportError:
    try:
        from services.audiobook_text_prep import (
            prepare_chapter, detect_abbreviations, estimate_characters,
        )
    except ImportError:
        from .audiobook_text_prep import (
            prepare_chapter, detect_abbreviations, estimate_characters,
        )

# Billing
try:
    from backend.services.pricing_registry import get_pricing_registry
    from backend.services.credits_service import get_credits_service, InsufficientCreditsError
except ImportError:
    try:
        from services.pricing_registry import get_pricing_registry
        from services.credits_service import get_credits_service, InsufficientCreditsError
    except ImportError:
        get_pricing_registry = None
        get_credits_service = None
        InsufficientCreditsError = Exception

# Concurrency controls
try:
    from backend.system.concurrency import get_image_semaphore, semaphore
except Exception:
    try:
        from system.concurrency import get_image_semaphore, semaphore
    except Exception:
        _tts_sem = None

        def get_image_semaphore():
            global _tts_sem
            if _tts_sem is None:
                limit = int(os.getenv("MAX_CONCURRENT_TTS", "2"))
                _tts_sem = asyncio.Semaphore(max(1, limit))
            return _tts_sem

        class semaphore:
            def __init__(self, sem):
                self._sem = sem
            async def __aenter__(self):
                await self._sem.acquire()
                return self
            async def __aexit__(self, *args):
                self._sem.release()
                return False


CURATED_VOICES = [
    {
        "id": "pNInz6obpgDQGcFmaJgB",
        "name": "Adam",
        "gender": "male",
        "description": "Deep, warm American male. Natural storytelling delivery.",
        "accent": "American",
        "style": "narrative",
    },
    {
        "id": "21m00Tcm4TlvDq8ikWAM",
        "name": "Rachel",
        "gender": "female",
        "description": "Clear, professional American female. Warm and engaging.",
        "accent": "American",
        "style": "narrative",
    },
    {
        "id": "ErXwobaYiN019PkySvjV",
        "name": "Antoni",
        "gender": "male",
        "description": "Young, articulate American male. Crisp and expressive.",
        "accent": "American",
        "style": "narrative",
    },
    {
        "id": "EXAVITQu4vr4xnSDxMaL",
        "name": "Bella",
        "gender": "female",
        "description": "Soft, expressive American female. Great for literary fiction.",
        "accent": "American",
        "style": "literary",
    },
    {
        "id": "VR6AewLTigWG4xSOukaG",
        "name": "Arnold",
        "gender": "male",
        "description": "Strong, authoritative American male. Commanding presence.",
        "accent": "American",
        "style": "dramatic",
    },
    {
        "id": "MF3mGyEYCl7XYWbV9V6O",
        "name": "Elli",
        "gender": "female",
        "description": "Friendly, youthful American female. Upbeat and clear.",
        "accent": "American",
        "style": "conversational",
    },
    {
        "id": "TxGEqnHWrfWFTfGW9XjX",
        "name": "Josh",
        "gender": "male",
        "description": "Warm, deep American male. Ideal for fiction and non-fiction.",
        "accent": "American",
        "style": "narrative",
    },
    {
        "id": "AZnzlk1XvdvUeBnXmlld",
        "name": "Domi",
        "gender": "female",
        "description": "Confident, assertive American female. Strong narrator voice.",
        "accent": "American",
        "style": "dramatic",
    },
    {
        "id": "jBpfuIE2acCO8z3wKNLl",
        "name": "Gigi",
        "gender": "female",
        "description": "Animated, expressive American female. Great for YA and children's.",
        "accent": "American",
        "style": "expressive",
    },
    {
        "id": "onwK4e9ZLuTAKqWW03F9",
        "name": "Daniel",
        "gender": "male",
        "description": "Refined British male. Sophisticated and measured delivery.",
        "accent": "British",
        "style": "literary",
    },
    {
        "id": "XB0fDUnXU5powFXDhCwa",
        "name": "Charlotte",
        "gender": "female",
        "description": "Elegant British female. Poised and articulate narrator.",
        "accent": "British",
        "style": "literary",
    },
    {
        "id": "IKne3meq5aSn9XLyUdCD",
        "name": "Charlie",
        "gender": "male",
        "description": "Natural Australian male. Relaxed and approachable.",
        "accent": "Australian",
        "style": "conversational",
    },
]

# ElevenLabs pricing per 1K characters
ELEVENLABS_PRICING = {
    "eleven_multilingual_v2": 0.10,
    "eleven_v3": 0.10,
    "eleven_flash_v2_5": 0.05,
    "eleven_turbo_v2_5": 0.05,
}

DEFAULT_MODEL = "eleven_multilingual_v2"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
MAX_RETRIES = 3
RETRY_DELAYS = [2, 4, 8]


class AudiobookService:
    """Service for generating audiobooks using ElevenLabs TTS."""

    def __init__(self, user_id: Optional[str] = None, elevenlabs_api_key: Optional[str] = None):
        self.elevenlabs_client = None
        self.firebase_bucket = None
        self.available = False
        self.user_id = user_id
        self.billing_enabled = False
        self.pricing_registry = None
        self.credits_service = None

        api_key = elevenlabs_api_key or os.getenv("ELEVENLABS_API_KEY")

        if _ELEVENLABS_AVAILABLE and api_key:
            self.elevenlabs_client = ElevenLabs(api_key=api_key)
            logger.info("ElevenLabs client initialized")
        elif not _ELEVENLABS_AVAILABLE:
            logger.warning("elevenlabs package not installed. Audiobook generation disabled.")
        else:
            logger.warning("ELEVENLABS_API_KEY not set. Audiobook generation disabled.")

        if not _PYDUB_AVAILABLE:
            logger.warning("pydub package not installed. Audio concatenation will use raw bytes.")

        # Firebase Storage
        try:
            storage_bucket = os.getenv("FIREBASE_STORAGE_BUCKET")
            if not storage_bucket:
                service_account_json = os.getenv("SERVICE_ACCOUNT_JSON")
                if service_account_json:
                    project_id = json.loads(service_account_json).get("project_id")
                else:
                    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "book-writer-automated")
                storage_bucket = f"{project_id}.appspot.com"
            self.firebase_bucket = storage.bucket(storage_bucket)
            logger.info(f"Firebase Storage initialized: {storage_bucket}")
        except Exception as e:
            logger.error(f"Failed to init Firebase Storage: {e}")

        # Billing
        enable_billing = os.getenv("ENABLE_CREDITS_BILLING", "false").lower() == "true"
        if user_id and enable_billing:
            try:
                self.pricing_registry = get_pricing_registry() if get_pricing_registry else None
                self.credits_service = get_credits_service() if get_credits_service else None
                if self.pricing_registry and self.credits_service:
                    self.billing_enabled = True
                    logger.info(f"Audiobook billing enabled for user {user_id}")
            except Exception as e:
                logger.warning(f"Billing init failed: {e}")

        self.available = self.elevenlabs_client is not None and self.firebase_bucket is not None

    def is_available(self) -> bool:
        return self.available

    def get_voices(self) -> List[Dict[str, Any]]:
        """Return the curated voice list."""
        return CURATED_VOICES

    def estimate_cost(
        self,
        chapters: List[Dict[str, Any]],
        glossary: Optional[List[Dict[str, str]]] = None,
        model_id: str = DEFAULT_MODEL,
    ) -> Dict[str, Any]:
        """Estimate cost for audiobook generation.

        Uses the pricing registry (with markup) when available so the estimate
        matches what billing will actually charge.
        """
        total_chars = estimate_characters(chapters, glossary)
        rate = ELEVENLABS_PRICING.get(model_id, 0.10)
        cost_usd = (total_chars / 1000) * rate
        estimated_minutes = max(1, total_chars / 10000)

        estimated_credits = max(1, int(cost_usd * 100))
        if self.pricing_registry:
            try:
                usage = {"prompt_tokens": total_chars, "completion_tokens": 0}
                calc = self.pricing_registry.estimate_credits("elevenlabs", model_id, usage)
                if calc.credits > 0:
                    estimated_credits = calc.credits
            except Exception:
                pass

        return {
            "total_characters": total_chars,
            "total_chapters": len(chapters),
            "estimated_cost_usd": round(cost_usd, 2),
            "estimated_credits": estimated_credits,
            "estimated_duration_minutes": round(estimated_minutes, 1),
            "model": model_id,
            "rate_per_1k_chars": rate,
        }

    async def generate_preview(
        self,
        text: str,
        voice_id: str,
        model_id: str = DEFAULT_MODEL,
        glossary: Optional[List[Dict[str, str]]] = None,
        chapter_number: int = 1,
        chapter_title: str = "",
    ) -> bytes:
        """Generate a short audio preview using the full text prep pipeline.

        Returns MP3 bytes for the first ~500 preprocessed characters.
        """
        if not self.elevenlabs_client:
            raise RuntimeError("ElevenLabs client not available")

        chunks = prepare_chapter(text, chapter_number, chapter_title, glossary)
        preview_text = " ".join(chunks)[:500] if chunks else text[:500]

        audio_bytes = await self._tts_call(preview_text, voice_id, model_id)
        return audio_bytes

    async def generate_audiobook(
        self,
        project_id: str,
        chapters: List[Dict[str, Any]],
        config: Dict[str, Any],
        progress_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """Generate a full audiobook from chapters.

        Args:
            project_id: Project ID
            chapters: Sorted list of chapter dicts with 'content', 'chapter_number', 'title'
            config: AudiobookConfig dict with voice_id, model_id, pronunciation_glossary
            progress_callback: Optional async callback(status, current_chapter, total_chapters, percentage)

        Returns:
            Dict with chapter_urls, full_book_url, file_sizes, total_duration_seconds, etc.
        """
        if not self.is_available():
            raise RuntimeError("Audiobook service not available")

        voice_id = config.get("voice_id")
        model_id = config.get("model_id", DEFAULT_MODEL)
        glossary = config.get("pronunciation_glossary", [])

        if not voice_id:
            raise ValueError("voice_id is required")

        total_chapters = len(chapters)
        chapter_audio_segments: List[Tuple[int, bytes]] = []
        chapter_urls: Dict[int, str] = {}
        file_sizes: Dict[str, int] = {}
        total_chars = 0
        job_id = config.get("job_id", project_id)

        with tempfile.TemporaryDirectory() as tmp_dir:
            for idx, chapter in enumerate(chapters):
                chapter_number = chapter.get("chapter_number", idx + 1)
                chapter_title = chapter.get("title", "")
                content = chapter.get("content", "")

                if not content.strip():
                    logger.warning(f"Skipping empty chapter {chapter_number}")
                    continue

                if progress_callback:
                    await progress_callback(
                        "generating",
                        chapter_number,
                        total_chapters,
                        round((idx / total_chapters) * 100, 1),
                    )

                # Preprocess text into chunks
                chunks = prepare_chapter(content, chapter_number, chapter_title, glossary)
                total_chars += sum(len(c) for c in chunks)

                # Generate audio for each chunk
                chunk_audio_parts: List[bytes] = []
                for chunk_idx, chunk_text in enumerate(chunks):
                    audio_bytes = await self._tts_call_with_retry(
                        chunk_text, voice_id, model_id
                    )
                    chunk_audio_parts.append(audio_bytes)

                # Concatenate chunks into chapter audio
                chapter_mp3 = self._concatenate_mp3(chunk_audio_parts)
                chapter_audio_segments.append((chapter_number, chapter_mp3))

                # Upload chapter MP3
                chapter_path = f"audiobooks/{project_id}/{job_id}/chapter-{chapter_number}.mp3"
                chapter_url = await self._upload_to_firebase(
                    chapter_mp3, chapter_path, "audio/mpeg"
                )
                chapter_urls[chapter_number] = chapter_url
                file_sizes[f"chapter_{chapter_number}"] = len(chapter_mp3)

                logger.info(
                    f"Chapter {chapter_number}/{total_chapters} complete: "
                    f"{len(chapter_mp3)} bytes"
                )

            if not chapter_audio_segments:
                raise RuntimeError("No audio was generated — all chapters were empty or skipped")

            # Concatenate all chapters into full book
            if progress_callback:
                await progress_callback("concatenating", total_chapters, total_chapters, 95.0)

            all_chapter_bytes = [audio for _, audio in chapter_audio_segments]
            full_book_mp3 = self._concatenate_mp3(all_chapter_bytes)

            # Upload full book
            if progress_callback:
                await progress_callback("uploading", total_chapters, total_chapters, 98.0)

            full_book_path = f"audiobooks/{project_id}/{job_id}/full-book.mp3"
            full_book_url = await self._upload_to_firebase(
                full_book_mp3, full_book_path, "audio/mpeg"
            )
            file_sizes["full_book"] = len(full_book_mp3)

        # Calculate duration from pydub if available
        total_duration = None
        if _PYDUB_AVAILABLE:
            try:
                segment = AudioSegment.from_mp3(io.BytesIO(full_book_mp3))
                total_duration = len(segment) / 1000.0
            except Exception as e:
                logger.warning(f"Could not determine audio duration: {e}")

        # Bill for usage
        credits_charged = 0
        cost_usd = 0.0
        if self.billing_enabled:
            cost_usd = (total_chars / 1000) * ELEVENLABS_PRICING.get(model_id, 0.10)
            credits_charged = await self._bill_for_usage(model_id, total_chars, cost_usd)

        result = {
            "chapter_urls": chapter_urls,
            "full_book_url": full_book_url,
            "file_sizes": file_sizes,
            "total_characters": total_chars,
            "total_duration_seconds": total_duration,
            "credits_charged": credits_charged,
            "cost_usd": round(cost_usd, 2),
        }

        logger.info(
            f"Audiobook generation complete for {project_id}: "
            f"{total_chapters} chapters, {total_chars} chars, "
            f"{file_sizes.get('full_book', 0)} bytes"
        )
        return result

    async def _tts_call(self, text: str, voice_id: str, model_id: str) -> bytes:
        """Make a single TTS API call."""
        async with semaphore(get_image_semaphore()):
            audio_iterator = await asyncio.to_thread(
                self.elevenlabs_client.text_to_speech.convert,
                text=text,
                voice_id=voice_id,
                model_id=model_id,
                output_format=DEFAULT_OUTPUT_FORMAT,
            )
            # The SDK returns a generator; consume into bytes
            chunks = []
            for chunk in audio_iterator:
                if isinstance(chunk, bytes):
                    chunks.append(chunk)
            return b"".join(chunks)

    async def _tts_call_with_retry(
        self, text: str, voice_id: str, model_id: str
    ) -> bytes:
        """TTS call with exponential backoff retry."""
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                return await self._tts_call(text, voice_id, model_id)
            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAYS[attempt]
                    logger.warning(
                        f"TTS call failed (attempt {attempt + 1}/{MAX_RETRIES}), "
                        f"retrying in {delay}s: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"TTS call failed after {MAX_RETRIES} attempts: {e}")
        raise RuntimeError(f"TTS generation failed after {MAX_RETRIES} retries: {last_error}")

    def _concatenate_mp3(self, audio_parts: List[bytes]) -> bytes:
        """Concatenate multiple MP3 byte segments into one."""
        if not audio_parts:
            return b""
        if len(audio_parts) == 1:
            return audio_parts[0]

        if _PYDUB_AVAILABLE:
            try:
                combined = AudioSegment.empty()
                for part in audio_parts:
                    segment = AudioSegment.from_mp3(io.BytesIO(part))
                    combined += segment
                output = io.BytesIO()
                combined.export(output, format="mp3", bitrate="128k")
                return output.getvalue()
            except Exception as e:
                logger.warning(f"pydub concatenation failed, using raw concat: {e}")

        # Fallback: raw byte concatenation (works for same-format MP3s)
        return b"".join(audio_parts)

    async def _upload_to_firebase(
        self, data: bytes, path: str, content_type: str
    ) -> str:
        """Upload bytes to Firebase Storage and return public URL."""
        if not self.firebase_bucket:
            raise RuntimeError("Firebase Storage not available")

        blob = self.firebase_bucket.blob(path)
        blob.upload_from_string(data, content_type=content_type)
        blob.make_public()
        url = blob.public_url
        logger.info(f"Uploaded {len(data)} bytes to {path}")
        return url

    async def _bill_for_usage(
        self, model_id: str, total_characters: int, cost_usd: float
    ) -> int:
        """Bill the user for audiobook generation."""
        if not self.billing_enabled or not self.pricing_registry or not self.credits_service:
            return 0

        try:
            # Use prompt_tokens as character count for compatibility with pricing registry
            usage = {"prompt_tokens": total_characters, "completion_tokens": 0}
            calculation = self.pricing_registry.calculate_credits(
                "elevenlabs", model_id, usage
            )
            credits = calculation.credits

            if credits <= 0:
                return 0

            transaction = await self.credits_service.deduct_credits(
                user_id=self.user_id,
                amount=credits,
                reason="elevenlabs_audiobook_generation",
                meta={
                    "provider": "elevenlabs",
                    "model": model_id,
                    "operation": "audiobook_generation",
                    "total_characters": total_characters,
                    "cost_usd": cost_usd,
                    "calculation_details": calculation.calculation_details,
                },
            )
            if transaction:
                logger.info(f"Billed {credits} credits for audiobook ({total_characters} chars)")
                return credits

        except Exception as e:
            logger.error(f"Failed to bill for audiobook: {e}")

        return 0
