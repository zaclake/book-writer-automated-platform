#!/usr/bin/env python3
"""
Chapter Context Builder
Shared helpers to normalize references and canon context across flows.
"""

from __future__ import annotations

from typing import Dict, Any


def normalize_references(references: Dict[str, str]) -> Dict[str, str]:
    """Normalize reference keys (with/without .md, dash/underscore aliases)."""
    normalized: Dict[str, str] = {}
    for key, value in (references or {}).items():
        if value is None:
            continue
        name = str(key)
        normalized[name] = value
        lower = name.lower()
        normalized[lower] = value
        if lower.endswith(".md"):
            base = lower[:-3]
            normalized[base] = value
        else:
            normalized[f"{lower}.md"] = value
            base = lower
        # Cross-alias dashes and underscores so consumers can look up either form
        if "-" in base:
            underscore_form = base.replace("-", "_")
            normalized[underscore_form] = value
            normalized[f"{underscore_form}.md"] = value
        elif "_" in base:
            dash_form = base.replace("_", "-")
            normalized[dash_form] = value
            normalized[f"{dash_form}.md"] = value
    return normalized


def get_canon_log(references: Dict[str, str]) -> str:
    refs = normalize_references(references or {})
    return (
        refs.get("canon-log.md")
        or refs.get("canon_log.md")
        or refs.get("canon-log")
        or refs.get("canon_log")
        or ""
    )


def references_from_context(context: Dict[str, Any]) -> Dict[str, str]:
    """Extract reference content from a context dict and normalize."""
    if not context:
        return {}
    refs = context.get("references")
    if isinstance(refs, dict):
        return normalize_references(refs)
    derived = {
        k.replace("_reference", ""): v
        for k, v in context.items()
        if isinstance(v, str) and k.endswith("_reference")
    }
    return normalize_references(derived)
