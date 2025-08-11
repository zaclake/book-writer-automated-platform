import os
import asyncio
import threading
from typing import Optional

_llm_semaphore: Optional[asyncio.Semaphore] = None
_image_semaphore: Optional[asyncio.Semaphore] = None
_firestore_semaphore: Optional[asyncio.Semaphore] = None
_llm_thread_semaphore: Optional[threading.BoundedSemaphore] = None
_image_thread_semaphore: Optional[threading.BoundedSemaphore] = None


def _get_int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
        return max(1, value)
    except Exception:
        return default


def get_llm_semaphore() -> asyncio.Semaphore:
    global _llm_semaphore
    if _llm_semaphore is None:
        _llm_semaphore = asyncio.Semaphore(_get_int_env("MAX_CONCURRENT_LLM", 6))
    return _llm_semaphore


def get_image_semaphore() -> asyncio.Semaphore:
    global _image_semaphore
    if _image_semaphore is None:
        _image_semaphore = asyncio.Semaphore(_get_int_env("MAX_CONCURRENT_IMAGE", 2))
    return _image_semaphore


def get_firestore_semaphore() -> asyncio.Semaphore:
    global _firestore_semaphore
    if _firestore_semaphore is None:
        _firestore_semaphore = asyncio.Semaphore(_get_int_env("MAX_CONCURRENT_FIRESTORE", 20))
    return _firestore_semaphore


def get_llm_thread_semaphore() -> threading.BoundedSemaphore:
    global _llm_thread_semaphore
    if _llm_thread_semaphore is None:
        _llm_thread_semaphore = threading.BoundedSemaphore(_get_int_env("MAX_CONCURRENT_LLM", 6))
    return _llm_thread_semaphore


def get_image_thread_semaphore() -> threading.BoundedSemaphore:
    global _image_thread_semaphore
    if _image_thread_semaphore is None:
        _image_thread_semaphore = threading.BoundedSemaphore(_get_int_env("MAX_CONCURRENT_IMAGE", 2))
    return _image_thread_semaphore


class semaphore:
    """Async context manager to acquire and release a semaphore."""

    def __init__(self, sem: asyncio.Semaphore):
        self._sem = sem

    async def __aenter__(self):
        await self._sem.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._sem.release()
        return False


class thread_semaphore:
    """Sync context manager for threading semaphores."""

    def __init__(self, sem: threading.BoundedSemaphore):
        self._sem = sem

    def __enter__(self):
        self._sem.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        self._sem.release()
        return False


