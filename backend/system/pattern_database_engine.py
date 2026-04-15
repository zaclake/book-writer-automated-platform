#!/usr/bin/env python3
"""
Pattern Database Engine loader.
Provides an importable module name for the existing pattern database implementation.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Type

_MODULE_NAME = "pattern_database_engine_dynamic"
_ENGINE_FILE = Path(__file__).parent / "pattern-database-engine.py"


def _load_engine_module():
    if not _ENGINE_FILE.exists():
        raise FileNotFoundError(f"Pattern database engine not found: {_ENGINE_FILE}")

    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _ENGINE_FILE)
    if spec is None or spec.loader is None:
        raise ImportError("Failed to load pattern database engine module")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[arg-type]
    return module


def get_pattern_database_class() -> Type:
    module = _load_engine_module()
    if not hasattr(module, "PatternDatabase"):
        raise ImportError("PatternDatabase class missing from engine module")
    return module.PatternDatabase


# Convenience import for callers
PatternDatabase = get_pattern_database_class()
