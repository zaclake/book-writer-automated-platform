#!/usr/bin/env python3
"""
Pattern Database Engine
Tracks writing patterns across chapters to prevent repetition while maintaining voice consistency.
"""

import json
import os
import re
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path

class PatternDatabase:
    """Manages pattern tracking for writing freshness analysis."""
    
    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path)
        self.state_dir = self.project_path / ".project-state"
        self.db_path = self.state_dir / "pattern-database.json"
        self.db = self._load_database()
    
    def _load_database(self) -> Dict[str, Any]:
        """Load existing pattern database or create new one."""
        if self.db_path.exists():
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        
        # Create fresh database structure
        return {
            "metadata": {
                "created": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "chapter_count": 0,
                "total_patterns": 0
            },
            "physical_descriptions": {
                "characters": {},  # character_name: [descriptions]
                "settings": {},    # location_name: [descriptions]
                "objects": {},     # object_type: [descriptions]
                "sensory": {       # sense_type: [descriptions]
                    "visual": [],
                    "auditory": [],
                    "tactile": [],
                    "olfactory": [],
                    "gustatory": []
                }
            },
            "language_patterns": {
                "metaphors": [],           # [{"text": str, "chapter": int, "context": str}]
                "similes": [],            # [{"text": str, "chapter": int, "context": str}]
                "adjective_combinations": [], # [{"combo": str, "frequency": int, "chapters": []}]
                "sentence_structures": [],    # [{"pattern": str, "frequency": int, "chapters": []}]
                "paragraph_structures": [],   # [{"type": str, "frequency": int, "chapters": []}]
                "dialogue_tags": [],         # [{"tag": str, "frequency": int, "chapters": []}]
                "transitions": []            # [{"phrase": str, "type": str, "chapters": []}]
            },
            "emotional_expressions": {
                "character_reactions": {},   # character_name: {emotion: [expressions]}
                "internal_monologue": {},   # character_name: [thought_patterns]
                "conflict_expressions": [], # [{"type": str, "expression": str, "chapter": int}]
                "resolution_techniques": [] # [{"technique": str, "context": str, "chapter": int}]
            },
            "action_sequences": {
                "movement_descriptions": [], # [{"action": str, "description": str, "chapter": int}]
                "pacing_patterns": [],      # [{"type": str, "pattern": str, "chapter": int}]
                "choreography": [],         # [{"sequence": str, "style": str, "chapter": int}]
                "tension_building": []      # [{"technique": str, "effectiveness": str, "chapter": int}]
            },
            "chapter_summaries": {},        # chapter_num: {word_count, themes, characters, etc}
            "repetition_flags": []          # [{"type": str, "description": str, "severity": str, "chapters": []}]
        }
    
    def save_database(self):
        """Save pattern database to disk."""
        # Ensure state directory exists
        self.state_dir.mkdir(exist_ok=True)
        
        # Update metadata
        self.db["metadata"]["last_updated"] = datetime.now().isoformat()
        self.db["metadata"]["total_patterns"] = self._count_total_patterns()
        
        # Save to file
        with open(self.db_path, 'w', encoding='utf-8') as f:
            json.dump(self.db, f, indent=2, ensure_ascii=False)
    
    def _count_total_patterns(self) -> int:
        """Count total tracked patterns across all categories."""
        count = 0
        count += len(self.db["language_patterns"]["metaphors"])
        count += len(self.db["language_patterns"]["similes"])
        count += len(self.db["action_sequences"]["movement_descriptions"])
        count += len(self.db["emotional_expressions"]["conflict_expressions"])
        count += sum(len(descs) for descs in self.db["physical_descriptions"]["characters"].values())
        count += sum(len(descs) for descs in self.db["physical_descriptions"]["settings"].values())
        return count
    
    def add_chapter_patterns(self, chapter_num: int, chapter_text: str, 
                           characters: List[str] = None, settings: List[str] = None):
        """Extract and add patterns from a new chapter."""
        self.db["metadata"]["chapter_count"] = max(self.db["metadata"]["chapter_count"], chapter_num)
        
        # Extract metaphors and similes
        metaphors = self._extract_metaphors(chapter_text, chapter_num)
        similes = self._extract_similes(chapter_text, chapter_num)
        
        self.db["language_patterns"]["metaphors"].extend(metaphors)
        self.db["language_patterns"]["similes"].extend(similes)
        
        # Extract sentence structures
        sentence_patterns = self._extract_sentence_patterns(chapter_text, chapter_num)
        self._update_pattern_frequency(self.db["language_patterns"]["sentence_structures"], sentence_patterns, chapter_num)
        
        # Extract paragraph structures
        paragraph_patterns = self._extract_paragraph_patterns(chapter_text, chapter_num)
        self._update_pattern_frequency(self.db["language_patterns"]["paragraph_structures"], paragraph_patterns, chapter_num)
        
        # Extract dialogue tags
        dialogue_tags = self._extract_dialogue_tags(chapter_text, chapter_num)
        self._update_pattern_frequency(self.db["language_patterns"]["dialogue_tags"], dialogue_tags, chapter_num)
        
        # Store chapter summary
        self.db["chapter_summaries"][str(chapter_num)] = {
            "word_count": len(chapter_text.split()),
            "characters": characters or [],
            "settings": settings or [],
            "metaphor_count": len(metaphors),
            "simile_count": len(similes),
            "date_added": datetime.now().isoformat()
        }
        
        self.save_database()
    
    def _extract_metaphors(self, text: str, chapter_num: int) -> List[Dict[str, Any]]:
        """Extract metaphor patterns from text."""
        metaphors = []
        
        # Simple metaphor detection patterns
        metaphor_patterns = [
            r'(\w+\s+(?:is|was|are|were)\s+(?:a|an|the)?\s*\w+(?:\s+\w+){0,3})',
            r'(\w+\s+(?:became|becomes)\s+(?:a|an|the)?\s*\w+(?:\s+\w+){0,3})',
            r'(his|her|their|the)\s+(\w+)\s+(?:is|was|are|were)\s+(?:a|an|the)?\s*(\w+)'
        ]
        
        for pattern in metaphor_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                metaphor_text = match.group(0).strip()
                if len(metaphor_text) > 10 and not self._is_literal_description(metaphor_text):
                    metaphors.append({
                        "text": metaphor_text,
                        "chapter": chapter_num,
                        "context": self._get_context(text, match.start(), match.end())
                    })
        
        return metaphors[:10]  # Limit to prevent over-collection
    
    def _extract_similes(self, text: str, chapter_num: int) -> List[Dict[str, Any]]:
        """Extract simile patterns from text."""
        similes = []
        
        # Simile detection patterns
        simile_patterns = [
            r'(\w+(?:\s+\w+){0,3}\s+like\s+(?:a|an|the)?\s*\w+(?:\s+\w+){0,4})',
            r'(\w+(?:\s+\w+){0,3}\s+as\s+\w+\s+as\s+(?:a|an|the)?\s*\w+(?:\s+\w+){0,3})',
            r'(seemed\s+like\s+(?:a|an|the)?\s*\w+(?:\s+\w+){0,3})'
        ]
        
        for pattern in simile_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                simile_text = match.group(0).strip()
                similes.append({
                    "text": simile_text,
                    "chapter": chapter_num,
                    "context": self._get_context(text, match.start(), match.end())
                })
        
        return similes[:10]  # Limit to prevent over-collection
    
    def _extract_sentence_patterns(self, text: str, chapter_num: int) -> List[str]:
        """Extract sentence structure patterns."""
        sentences = re.split(r'[.!?]+', text)
        patterns = []
        
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 10:
                continue
            
            # Analyze sentence structure
            pattern = self._analyze_sentence_structure(sentence)
            if pattern:
                patterns.append(pattern)
        
        return patterns
    
    def _extract_paragraph_patterns(self, text: str, chapter_num: int) -> List[str]:
        """Extract paragraph structure patterns."""
        paragraphs = text.split('\n\n')
        patterns = []
        
        for para in paragraphs:
            para = para.strip()
            if len(para) < 50:
                continue
            
            # Detect thinking patterns
            if re.search(r'(thought about|considered|wondered|realized)', para, re.IGNORECASE):
                if re.search(r'though|although|however|but', para, re.IGNORECASE):
                    patterns.append("thinking_pattern_contrast")
                else:
                    patterns.append("thinking_pattern_simple")
            
            # Detect question patterns
            if '?' in para:
                patterns.append("question_pattern")
            
            # Detect dialogue patterns
            if '"' in para or "'" in para:
                patterns.append("dialogue_pattern")
        
        return patterns
    
    def _extract_dialogue_tags(self, text: str, chapter_num: int) -> List[str]:
        """Extract dialogue tag patterns."""
        tags = []
        
        # Common dialogue tag patterns
        tag_patterns = [
            r'"[^"]*"\s*,?\s*(\w+\s+(?:said|asked|replied|answered|whispered|shouted|murmured|called|declared|stated|exclaimed|muttered|growled|sighed))',
            r'(\w+\s+(?:said|asked|replied|answered|whispered|shouted|murmured|called|declared|stated|exclaimed|muttered|growled|sighed))\s*,?\s*"[^"]*"'
        ]
        
        for pattern in tag_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                tag = match.group(1).strip().lower()
                tags.append(tag)
        
        return tags
    
    def _update_pattern_frequency(self, pattern_list: List[Dict], new_patterns: List[str], chapter_num: int):
        """Update frequency tracking for patterns."""
        for pattern in new_patterns:
            # Find existing pattern or create new one
            existing = next((p for p in pattern_list if p.get("pattern") == pattern or p.get("tag") == pattern), None)
            
            if existing:
                existing["frequency"] += 1
                if chapter_num not in existing["chapters"]:
                    existing["chapters"].append(chapter_num)
            else:
                pattern_list.append({
                    "pattern": pattern,
                    "frequency": 1,
                    "chapters": [chapter_num]
                })
    
    def _analyze_sentence_structure(self, sentence: str) -> Optional[str]:
        """Analyze sentence structure for patterns."""
        sentence = sentence.strip().lower()
        
        # Detect common patterns
        if sentence.startswith(('she thought', 'he thought', 'they thought')):
            return "thought_opening"
        elif sentence.startswith(('she felt', 'he felt', 'they felt')):
            return "feeling_opening"
        elif sentence.startswith(('she could', 'he could', 'they could')):
            return "ability_opening"
        elif sentence.count(',') >= 3:
            return "complex_comma_structure"
        elif ' and ' in sentence and sentence.count(' and ') >= 2:
            return "multiple_and_structure"
        
        return None
    
    def _is_literal_description(self, text: str) -> bool:
        """Check if text is likely a literal rather than metaphorical description."""
        literal_indicators = ['was wearing', 'had on', 'stood at', 'measured', 'weighed', 'aged']
        return any(indicator in text.lower() for indicator in literal_indicators)
    
    def _get_context(self, text: str, start: int, end: int, context_length: int = 50) -> str:
        """Get surrounding context for a pattern match."""
        context_start = max(0, start - context_length)
        context_end = min(len(text), end + context_length)
        return text[context_start:context_end].strip()
    
    def analyze_repetition_risk(self, chapter_num: int) -> Dict[str, Any]:
        """Analyze repetition risk for current chapter patterns."""
        risks = {
            "high_risk": [],
            "medium_risk": [],
            "low_risk": [],
            "score": 10  # Start with perfect score, deduct for problems
        }
        
        # Check metaphor repetition
        recent_metaphors = [m for m in self.db["language_patterns"]["metaphors"] 
                          if m["chapter"] >= chapter_num - 5]
        metaphor_texts = [m["text"].lower() for m in recent_metaphors]
        
        for metaphor in recent_metaphors:
            if metaphor_texts.count(metaphor["text"].lower()) > 1:
                risks["high_risk"].append(f"Repeated metaphor: '{metaphor['text']}'")
                risks["score"] -= 2
        
        # Check sentence pattern frequency
        for pattern in self.db["language_patterns"]["sentence_structures"]:
            if pattern["frequency"] > 10:
                risks["medium_risk"].append(f"Overused sentence pattern: {pattern['pattern']} ({pattern['frequency']} times)")
                risks["score"] -= 1
        
        # Check paragraph pattern frequency
        for pattern in self.db["language_patterns"]["paragraph_structures"]:
            if pattern["frequency"] > 5:
                risks["high_risk"].append(f"Overused paragraph pattern: {pattern['pattern']} ({pattern['frequency']} times)")
                risks["score"] -= 2
        
        # Ensure score doesn't go below 0
        risks["score"] = max(0, risks["score"])
        
        return risks
    
    def get_pattern_summary(self) -> Dict[str, Any]:
        """Get summary of all tracked patterns."""
        return {
            "metadata": self.db["metadata"],
            "total_metaphors": len(self.db["language_patterns"]["metaphors"]),
            "total_similes": len(self.db["language_patterns"]["similes"]),
            "sentence_patterns": len(self.db["language_patterns"]["sentence_structures"]),
            "paragraph_patterns": len(self.db["language_patterns"]["paragraph_structures"]),
            "dialogue_tags": len(self.db["language_patterns"]["dialogue_tags"]),
            "chapters_tracked": self.db["metadata"]["chapter_count"],
            "recent_risks": self.analyze_repetition_risk(self.db["metadata"]["chapter_count"])
        }
    
    def check_freshness_score(self, chapter_text: str, chapter_num: int) -> float:
        """Calculate freshness score for new chapter content (7+ required)."""
        temp_metaphors = self._extract_metaphors(chapter_text, chapter_num)
        temp_similes = self._extract_similes(chapter_text, chapter_num)
        temp_patterns = self._extract_sentence_patterns(chapter_text, chapter_num)
        
        score = 10.0
        
        # Check against existing patterns
        existing_metaphors = [m["text"].lower() for m in self.db["language_patterns"]["metaphors"]]
        existing_similes = [s["text"].lower() for s in self.db["language_patterns"]["similes"]]
        
        # Deduct for repeated metaphors/similes
        for metaphor in temp_metaphors:
            if metaphor["text"].lower() in existing_metaphors:
                score -= 1.5
        
        for simile in temp_similes:
            if simile["text"].lower() in existing_similes:
                score -= 1.5
        
        # Deduct for overused sentence patterns
        for pattern in temp_patterns:
            existing_pattern = next((p for p in self.db["language_patterns"]["sentence_structures"] 
                                   if p["pattern"] == pattern), None)
            if existing_pattern and existing_pattern["frequency"] > 5:
                score -= 0.5
        
        return max(0.0, score)

# CLI Interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Pattern Database Engine")
    parser.add_argument("action", choices=["init", "add", "analyze", "summary"], 
                       help="Action to perform")
    parser.add_argument("--chapter", type=int, help="Chapter number")
    parser.add_argument("--file", help="Chapter file path")
    parser.add_argument("--characters", nargs="*", help="Character names in chapter")
    parser.add_argument("--settings", nargs="*", help="Settings in chapter")
    
    args = parser.parse_args()
    
    db = PatternDatabase()
    
    if args.action == "init":
        db.save_database()
        print("Pattern database initialized")
    
    elif args.action == "add" and args.chapter and args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                chapter_text = f.read()
            
            db.add_chapter_patterns(args.chapter, chapter_text, 
                                  args.characters, args.settings)
            print(f"Added patterns from chapter {args.chapter}")
            
            # Show freshness score
            score = db.check_freshness_score(chapter_text, args.chapter)
            print(f"Freshness score: {score:.1f}/10.0")
            
        except FileNotFoundError:
            print(f"Error: Chapter file {args.file} not found")
    
    elif args.action == "analyze":
        if args.chapter:
            risks = db.analyze_repetition_risk(args.chapter)
            print(f"Repetition analysis for chapter {args.chapter}:")
            print(f"Score: {risks['score']}/10")
            if risks["high_risk"]:
                print("High risk patterns:")
                for risk in risks["high_risk"]:
                    print(f"  - {risk}")
        else:
            print("Please specify --chapter for analysis")
    
    elif args.action == "summary":
        summary = db.get_pattern_summary()
        print("Pattern Database Summary:")
        print(f"Chapters tracked: {summary['chapters_tracked']}")
        print(f"Total metaphors: {summary['total_metaphors']}")
        print(f"Total similes: {summary['total_similes']}")
        print(f"Sentence patterns: {summary['sentence_patterns']}")
        print(f"Paragraph patterns: {summary['paragraph_patterns']}")
        print(f"Overall freshness score: {summary['recent_risks']['score']}/10") 