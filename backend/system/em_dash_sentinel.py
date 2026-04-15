#!/usr/bin/env python3
"""
Em Dash Sentinel
Detects prohibited em dash characters in generated text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class EmDashScanResult:
    violations_found: int
    positions: List[int]
    file_path: Optional[str] = None


class EmDashSentinel:
    """Scan text for em dash characters and report violations."""

    def __init__(self, project_path: str = "."):
        self.project_path = project_path

    def scan_text(self, text: str, file_path: Optional[str] = None) -> EmDashScanResult:
        if not text:
            return EmDashScanResult(violations_found=0, positions=[], file_path=file_path)

        positions: List[int] = []
        for idx, ch in enumerate(text):
            if ch == "—":
                positions.append(idx)

        return EmDashScanResult(
            violations_found=len(positions),
            positions=positions,
            file_path=file_path
        )
