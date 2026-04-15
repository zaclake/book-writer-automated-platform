#!/usr/bin/env python3
"""
Voice Fingerprint Manager
Tracks character dialogue fingerprints to enforce distinct voices.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple


@dataclass
class VoiceFingerprint:
    character: str
    chapter_number: int
    created_at: str
    avg_sentence_length: float
    top_tokens: List[str]
    punctuation_profile: Dict[str, float]


class VoiceFingerprintManager:
    """Extract, store, and compare dialogue fingerprints per character."""

    SPEAKER_PATTERNS = [
        r'"([^"]+)"\s*,?\s*([A-Z][a-zA-Z]+)\s+(?:said|asked|replied|answered|whispered|shouted|murmured|called|declared|stated|exclaimed|muttered|growled|sighed)',
        r'([A-Z][a-zA-Z]+)\s+(?:said|asked|replied|answered|whispered|shouted|murmured|called|declared|stated|exclaimed|muttered|growled|sighed)\s*,?\s*"([^"]+)"'
    ]

    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.state_dir = self.project_path / ".project-state"
        self.state_dir.mkdir(exist_ok=True)
        self.file_path = self.state_dir / "voice-fingerprints.json"
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self.file_path.exists():
            return {"metadata": {"created": datetime.now().isoformat()}, "fingerprints": {}, "scene_fingerprints": {}}
        try:
            return json.loads(self.file_path.read_text(encoding="utf-8"))
        except Exception:
            return {"metadata": {"created": datetime.now().isoformat()}, "fingerprints": {}, "scene_fingerprints": {}}

    def _save(self) -> None:
        self.data["metadata"]["last_updated"] = datetime.now().isoformat()
        self.file_path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")

    def extract_dialogue(self, text: str) -> Dict[str, List[str]]:
        """Extract dialogue per character from tagged speech."""
        dialogue_by_character: Dict[str, List[str]] = {}
        for pattern in self.SPEAKER_PATTERNS:
            for match in re.findall(pattern, text):
                if len(match) != 2:
                    continue
                if pattern.startswith('"'):
                    line, speaker = match
                else:
                    speaker, line = match
                speaker = speaker.strip()
                line = line.strip()
                if not speaker or not line:
                    continue
                dialogue_by_character.setdefault(speaker, []).append(line)
        return dialogue_by_character

    def build_fingerprint(self, character: str, chapter_number: int, lines: List[str]) -> VoiceFingerprint:
        tokens = []
        sentence_lengths = []
        text = " ".join(lines)
        for sentence in re.split(r'[.!?]+', text):
            sentence = sentence.strip()
            if not sentence:
                continue
            words = [w for w in re.split(r'[^a-zA-Z]+', sentence) if w]
            if words:
                sentence_lengths.append(len(words))
                tokens.extend([w.lower() for w in words if len(w) > 3])

        avg_sentence = sum(sentence_lengths) / max(1, len(sentence_lengths))
        token_counts: Dict[str, int] = {}
        for t in tokens:
            token_counts[t] = token_counts.get(t, 0) + 1
        top_tokens = [t for t, _ in sorted(token_counts.items(), key=lambda x: -x[1])[:12]]

        total_words = max(1, len(text.split()))
        punctuation_profile = {
            "comma": text.count(",") / total_words,
            "semicolon": text.count(";") / total_words,
            "colon": text.count(":") / total_words,
            "question": text.count("?") / total_words,
            "exclamation": text.count("!") / total_words,
        }

        return VoiceFingerprint(
            character=character,
            chapter_number=chapter_number,
            created_at=datetime.utcnow().isoformat(),
            avg_sentence_length=avg_sentence,
            top_tokens=top_tokens,
            punctuation_profile=punctuation_profile
        )

    def store_fingerprint(self, fingerprint: VoiceFingerprint) -> None:
        self.data["fingerprints"].setdefault(fingerprint.character, [])
        self.data["fingerprints"][fingerprint.character].append(fingerprint.__dict__)
        self._save()

    def store_scene_fingerprint(self, chapter_number: int, scene_number: int, fingerprint: VoiceFingerprint) -> None:
        key = f"{chapter_number}:{scene_number}:{fingerprint.character}"
        self.data.setdefault("scene_fingerprints", {})
        self.data["scene_fingerprints"][key] = fingerprint.__dict__
        self._save()

    def analyze_chapter(self, chapter_number: int, text: str) -> Dict[str, VoiceFingerprint]:
        dialogue = self.extract_dialogue(text)
        fingerprints: Dict[str, VoiceFingerprint] = {}
        for character, lines in dialogue.items():
            if len(lines) < 2:
                continue
            fp = self.build_fingerprint(character, chapter_number, lines)
            fingerprints[character] = fp
            self.store_fingerprint(fp)
        return fingerprints

    def fingerprints_from_text(self, chapter_number: int, text: str) -> Dict[str, VoiceFingerprint]:
        """Build fingerprints without storing (for assessment)."""
        dialogue = self.extract_dialogue(text)
        fingerprints: Dict[str, VoiceFingerprint] = {}
        for character, lines in dialogue.items():
            if len(lines) < 2:
                continue
            fingerprints[character] = self.build_fingerprint(character, chapter_number, lines)
        return fingerprints

    def analyze_scene(self, chapter_number: int, scene_number: int, text: str) -> Dict[str, VoiceFingerprint]:
        """Build and store fingerprints for a scene."""
        dialogue = self.extract_dialogue(text)
        fingerprints: Dict[str, VoiceFingerprint] = {}
        for character, lines in dialogue.items():
            if len(lines) < 2:
                continue
            fp = self.build_fingerprint(character, chapter_number, lines)
            fingerprints[character] = fp
            self.store_scene_fingerprint(chapter_number, scene_number, fp)
        return fingerprints

    def _token_overlap(self, a: List[str], b: List[str]) -> float:
        if not a or not b:
            return 0.0
        sa = set(a)
        sb = set(b)
        return len(sa.intersection(sb)) / max(1, len(sa.union(sb)))

    def fingerprint_similarity(self, a: VoiceFingerprint, b: VoiceFingerprint) -> float:
        """Similarity between two fingerprints (0-1)."""
        token_sim = self._token_overlap(a.top_tokens, b.top_tokens)
        length_diff = abs(a.avg_sentence_length - b.avg_sentence_length)
        length_sim = max(0.0, 1.0 - min(1.0, length_diff / 10.0))
        punct_sim = 1.0 - min(
            1.0,
            sum(abs(a.punctuation_profile.get(k, 0.0) - b.punctuation_profile.get(k, 0.0)) for k in a.punctuation_profile.keys())
        )
        return (token_sim * 0.5) + (length_sim * 0.3) + (punct_sim * 0.2)

    def chapter_voice_similarity(self, fingerprints: Dict[str, VoiceFingerprint]) -> List[Tuple[str, str, float]]:
        """Return pairs of characters with overly similar voices."""
        names = list(fingerprints.keys())
        conflicts: List[Tuple[str, str, float]] = []
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a = fingerprints[names[i]]
                b = fingerprints[names[j]]
                similarity = self.fingerprint_similarity(a, b)
                if similarity > 0.75:
                    conflicts.append((a.character, b.character, similarity))
        return conflicts

    def recent_character_similarity(self, character: str, fingerprint: VoiceFingerprint, lookback: int = 5) -> Optional[float]:
        """Compare a fingerprint to recent history for the same character."""
        history = self.data.get("fingerprints", {}).get(character, [])
        if not history:
            return None
        recent = history[-lookback:]
        sims = []
        for item in recent:
            try:
                fp = VoiceFingerprint(**item)
                sims.append(self.fingerprint_similarity(fp, fingerprint))
            except Exception:
                continue
        return max(sims) if sims else None

    def global_character_drift(self, character: str, fingerprint: VoiceFingerprint, lookback: int = 10) -> Optional[float]:
        """Measure drift from broader history for a character."""
        history = self.data.get("fingerprints", {}).get(character, [])
        if not history:
            return None
        sample = history[-lookback:]
        sims = []
        for item in sample:
            try:
                fp = VoiceFingerprint(**item)
                sims.append(self.fingerprint_similarity(fp, fingerprint))
            except Exception:
                continue
        return sum(sims) / max(1, len(sims))
