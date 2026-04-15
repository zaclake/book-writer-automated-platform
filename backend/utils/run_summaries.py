"""
Run summary utilities.

Goals:
- Emit exactly one structured JSON summary line per unit of work (chapter run / book run).
- Provide stable digests for large inputs (bible/ledger/canon/etc.) without logging content.
- Be safe in production: default=str serialization, bounded sizes, no placeholders.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_digest(text: str, *, max_chars: int = 200_000) -> str:
    """
    Hash text with a size cap to avoid pathological memory usage.
    """
    if not text:
        return ""
    raw = text if len(text) <= max_chars else text[:max_chars]
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def text_stats(text: str, *, digest_max_chars: int = 200_000) -> Dict[str, Any]:
    if not text:
        return {"chars": 0, "words": 0, "sha256": ""}
    return {
        "chars": len(text),
        "words": len(text.split()),
        "sha256": sha256_digest(text, max_chars=digest_max_chars),
    }


def safe_json(obj: Any) -> str:
    return json.dumps(
        obj,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def emit_summary(logger: logging.Logger, payload: Dict[str, Any]) -> None:
    """
    Emit a single-line JSON log. `payload` MUST be JSON-serializable via default=str.
    """
    if not isinstance(payload, dict):
        raise TypeError("emit_summary payload must be a dict")
    # Encourage consistent fields.
    payload.setdefault("timestamp", utc_now_iso())
    logger.info(safe_json(payload))

