#!/usr/bin/env python3
"""
Cadence Analyzer
Tracks sentence/paragraph rhythm fingerprints to detect repetitive cadence.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional


@dataclass
class CadenceFingerprint:
    chapter_number: int
    created_at: str
    sentence_count: int
    avg_sentence_length: float
    sentence_length_std: float
    paragraph_count: int
    avg_paragraph_length: float
    dialogue_ratio: float
    punctuation_profile: Dict[str, float]


class CadenceAnalyzer:
    """Analyze and store cadence fingerprints per chapter."""

    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.state_dir = self.project_path / ".project-state"
        self.state_dir.mkdir(exist_ok=True)
        self.fingerprint_path = self.state_dir / "cadence-fingerprints.json"
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self.fingerprint_path.exists():
            return {"metadata": {"created": datetime.now().isoformat()}, "fingerprints": {}, "scene_fingerprints": {}}
        try:
            return json.loads(self.fingerprint_path.read_text(encoding="utf-8"))
        except Exception:
            return {"metadata": {"created": datetime.now().isoformat()}, "fingerprints": {}, "scene_fingerprints": {}}

    def _save(self) -> None:
        self.data["metadata"]["last_updated"] = datetime.now().isoformat()
        self.fingerprint_path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")

    def analyze(self, chapter_number: int, text: str) -> CadenceFingerprint:
        sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
        sentence_lengths = [len(s.split()) for s in sentences] if sentences else [0]
        avg_sentence = sum(sentence_lengths) / max(1, len(sentence_lengths))
        variance = sum((l - avg_sentence) ** 2 for l in sentence_lengths) / max(1, len(sentence_lengths))
        std = variance ** 0.5

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        paragraph_lengths = [len(p.split()) for p in paragraphs] if paragraphs else [0]
        avg_paragraph = sum(paragraph_lengths) / max(1, len(paragraph_lengths))

        dialogue_words = 0
        total_words = max(1, len(text.split()))
        for paragraph in paragraphs:
            if '"' in paragraph or '“' in paragraph or '”' in paragraph:
                dialogue_words += len(paragraph.split())
        dialogue_ratio = dialogue_words / total_words

        punctuation_profile = {
            "comma": text.count(",") / total_words,
            "semicolon": text.count(";") / total_words,
            "colon": text.count(":") / total_words,
            "question": text.count("?") / total_words,
            "exclamation": text.count("!") / total_words,
        }

        return CadenceFingerprint(
            chapter_number=chapter_number,
            created_at=datetime.utcnow().isoformat(),
            sentence_count=len(sentences),
            avg_sentence_length=avg_sentence,
            sentence_length_std=std,
            paragraph_count=len(paragraphs),
            avg_paragraph_length=avg_paragraph,
            dialogue_ratio=dialogue_ratio,
            punctuation_profile=punctuation_profile
        )

    def store(self, fingerprint: CadenceFingerprint) -> None:
        self.data["fingerprints"][str(fingerprint.chapter_number)] = fingerprint.__dict__
        self._save()

    def get_recent(self, chapter_number: int, lookback: int = 3) -> List[CadenceFingerprint]:
        fingerprints = []
        for i in range(max(1, chapter_number - lookback), chapter_number):
            fp = self.data["fingerprints"].get(str(i))
            if fp:
                fingerprints.append(CadenceFingerprint(**fp))
        return fingerprints

    def store_scene(self, chapter_number: int, scene_number: int, fingerprint: CadenceFingerprint) -> None:
        key = f"{chapter_number}:{scene_number}"
        self.data["scene_fingerprints"][key] = fingerprint.__dict__
        self._save()

    def get_recent_scenes(self, chapter_number: int, scene_number: int, lookback: int = 3) -> List[CadenceFingerprint]:
        fingerprints = []
        start = max(1, scene_number - lookback)
        for i in range(start, scene_number):
            key = f"{chapter_number}:{i}"
            fp = self.data["scene_fingerprints"].get(key)
            if fp:
                fingerprints.append(CadenceFingerprint(**fp))
        return fingerprints

    def similarity(self, a: CadenceFingerprint, b: CadenceFingerprint) -> float:
        """Compute a rough similarity score between two fingerprints (0-1)."""
        metrics = [
            ("avg_sentence_length", 20.0),
            ("sentence_length_std", 10.0),
            ("avg_paragraph_length", 80.0),
            ("dialogue_ratio", 0.5),
            ("comma", 0.05),
            ("semicolon", 0.02),
            ("colon", 0.02),
            ("question", 0.02),
            ("exclamation", 0.02),
        ]

        def norm_diff(val_a: float, val_b: float, denom: float) -> float:
            return min(1.0, abs(val_a - val_b) / max(denom, 1e-6))

        diffs = []
        for key, denom in metrics:
            if key in {"comma", "semicolon", "colon", "question", "exclamation"}:
                va = a.punctuation_profile.get(key, 0.0)
                vb = b.punctuation_profile.get(key, 0.0)
            else:
                va = getattr(a, key)
                vb = getattr(b, key)
            diffs.append(norm_diff(va, vb, denom))

        avg_diff = sum(diffs) / max(1, len(diffs))
        return max(0.0, 1.0 - avg_diff)

    def cadence_similarity_score(self, chapter_number: int, text: str, lookback: int = 3) -> Optional[float]:
        current = self.analyze(chapter_number, text)
        recent = self.get_recent(chapter_number, lookback=lookback)
        if not recent:
            return None
        sims = [self.similarity(current, r) for r in recent]
        return max(sims) if sims else None

    def scene_similarity_score(self, chapter_number: int, scene_number: int, text: str, lookback: int = 3) -> Optional[float]:
        current = self.analyze(chapter_number, text)
        recent = self.get_recent_scenes(chapter_number, scene_number, lookback=lookback)
        if not recent:
            return None
        sims = [self.similarity(current, r) for r in recent]
        return max(sims) if sims else None
