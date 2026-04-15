"""
Central logging configuration.

Call `setup_logging()` exactly once at process startup (e.g. from `backend/main.py`).

Goals:
- Prevent duplicate handlers / duplicate log lines
- Provide high-signal, text-friendly logs for Railway
- Add correlation fields (request_id, job_id) when available
"""

from __future__ import annotations

import logging
import os
import sys
import contextvars
from typing import Optional


# Context vars are set in request middleware / job submission paths.
# We intentionally keep these optional to avoid tight coupling.
request_id_contextvar = contextvars.ContextVar("request_id", default=None)
job_id_contextvar = contextvars.ContextVar("job_id", default=None)
run_id_contextvar = contextvars.ContextVar("run_id", default=None)


class ContextFilter(logging.Filter):
    """Inject request_id/job_id into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.request_id = request_id_contextvar.get()
        except Exception:
            record.request_id = None
        try:
            record.job_id = job_id_contextvar.get()
        except Exception:
            record.job_id = None
        try:
            record.run_id = run_id_contextvar.get()
        except Exception:
            record.run_id = None
        return True


def _parse_level(level_name: str) -> int:
    name = (level_name or "WARNING").upper()
    return getattr(logging, name, logging.WARNING)


def setup_logging(
    *,
    level_name: Optional[str] = None,
    force: bool = True,
) -> None:
    """
    Configure root logging for the process.

    Args:
        level_name: LOG_LEVEL override (e.g. INFO). Defaults to env LOG_LEVEL or WARNING.
        force: If True, removes existing handlers to prevent duplicates.
    """

    level = _parse_level(level_name or os.getenv("LOG_LEVEL", "WARNING"))

    root = logging.getLogger()
    root.setLevel(level)

    if force:
        # Remove all existing handlers to prevent duplication from multiple basicConfig calls.
        for h in list(root.handlers):
            root.removeHandler(h)

    # Text format optimized for Railway console scanning and filtering.
    # Example:
    # 2026-01-28 22:00:27,216 INFO backend.auto_complete.llm_orchestrator rid=... jid=... Expansion pass triggered...
    fmt = "%(asctime)s %(levelname)s %(name)s rid=%(request_id)s jid=%(job_id)s run=%(run_id)s %(message)s"
    formatter = logging.Formatter(fmt)

    stream = logging.StreamHandler(sys.stdout)
    stream.setLevel(level)
    stream.setFormatter(formatter)
    stream.addFilter(ContextFilter())
    root.addHandler(stream)

    # Silence noisy dependencies unless explicitly elevated.
    for noisy_logger in (
        "uvicorn.access",
        "uvicorn.error",
        "httpx",
        "httpcore",
        "openai",
        "asyncio",
    ):
        logging.getLogger(noisy_logger).setLevel(max(level, logging.WARNING))

