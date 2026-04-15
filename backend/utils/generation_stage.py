"""
Stage normalization and feature-gated routing.

This project supports a newer "simple" chapter generation path (aka stage="complete")
and a legacy "5-stage" path. The legacy path must be explicitly enabled via an
environment flag to prevent accidental usage.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


def _env_bool(name: str, default: bool = False) -> bool:
    default_str = "true" if default else "false"
    try:
        env = str(os.getenv(name, default_str)).strip().lower()
    except Exception:
        env = default_str
    return env in ("1", "true", "yes", "y", "on")


def normalize_stage(stage: Optional[str]) -> str:
    """
    Normalize user-provided stage to a canonical internal value.

    Canonical values used by the system:
    - "complete" (simple/default)
    - "spike"
    - "5-stage" (legacy)
    """
    s = (stage or "").strip().lower()
    if not s or s == "simple":
        return "complete"
    if s in ("complete", "spike"):
        return s
    if s in ("5-stage", "5stage", "5_stage", "five-stage", "five_stage"):
        return "5-stage"
    # Safe fallback: treat unknown as simple/default.
    return "complete"


@dataclass(frozen=True)
class StageResolution:
    requested: str
    effective: str
    allow_5_stage: bool


def resolve_generation_stage(
    requested_stage: Optional[str],
    *,
    allow_5_stage: Optional[bool] = None,
) -> StageResolution:
    """
    Resolve requested stage into an effective stage, gating the legacy 5-stage path.

    If allow_5_stage is None, it is derived from ENABLE_5_STAGE_WRITING (default false).
    """
    requested_norm = normalize_stage(requested_stage)
    allow = _env_bool("ENABLE_5_STAGE_WRITING", False) if allow_5_stage is None else bool(allow_5_stage)
    effective = requested_norm
    if requested_norm == "5-stage" and not allow:
        effective = "complete"
    return StageResolution(requested=requested_norm, effective=effective, allow_5_stage=allow)

