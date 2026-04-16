#!/usr/bin/env python3
"""
Audiobook Text Preparation Pipeline

Transforms raw chapter markdown into clean, TTS-optimized text for ElevenLabs.
Handles markdown stripping, pronunciation glossary, scene breaks, chapter
announcements, character normalization, and sentence-boundary chunking.
"""

import re
import logging
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)

MAX_CHUNK_CHARS = 4500
SCENE_BREAK_SSML = '<break time="1.5s"/>'
CHAPTER_PAUSE_SSML = '<break time="2s"/>'

# Patterns that indicate a scene break in markdown
SCENE_BREAK_PATTERNS = [
    re.compile(r'^\s*\*\s*\*\s*\*\s*$', re.MULTILINE),
    re.compile(r'^\s*---+\s*$', re.MULTILINE),
    re.compile(r'^\s*___+\s*$', re.MULTILINE),
    re.compile(r'^\s*\*{3,}\s*$', re.MULTILINE),
    re.compile(r'^\s*-{3,}\s*$', re.MULTILINE),
    re.compile(r'^\s*#{1,3}\s*$', re.MULTILINE),  # bare heading markers
]

# All-caps token detection for abbreviation scanning
ABBREVIATION_PATTERN = re.compile(r'\b([A-Z]{2,})\b')


def strip_markdown(text: str) -> str:
    """Remove markdown formatting while preserving prose content."""
    result = text

    # Remove heading markers but keep text
    result = re.sub(r'^#{1,6}\s+', '', result, flags=re.MULTILINE)

    # Remove bold/italic markers
    result = re.sub(r'\*\*\*(.+?)\*\*\*', r'\1', result)
    result = re.sub(r'\*\*(.+?)\*\*', r'\1', result)
    result = re.sub(r'\*(.+?)\*', r'\1', result)
    result = re.sub(r'___(.+?)___', r'\1', result)
    result = re.sub(r'__(.+?)__', r'\1', result)
    result = re.sub(r'_(.+?)_', r'\1', result)

    # Remove inline code
    result = re.sub(r'`(.+?)`', r'\1', result)

    # Convert links to just link text
    result = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', result)

    # Remove image references
    result = re.sub(r'!\[([^\]]*)\]\([^)]+\)', '', result)

    # Remove blockquote markers
    result = re.sub(r'^>\s*', '', result, flags=re.MULTILINE)

    # Remove HTML tags (except SSML break tags we insert)
    result = re.sub(r'<(?!break\b)[^>]+>', '', result)

    return result


def apply_pronunciation_glossary(text: str, glossary: List[Dict[str, str]]) -> str:
    """Apply pronunciation glossary substitutions.

    Each entry is applied as a case-sensitive whole-word replacement.
    """
    if not glossary:
        return text

    result = text
    for entry in glossary:
        abbreviation = entry.get('abbreviation', '')
        spoken_form = entry.get('spoken_form', '')
        if not abbreviation or not spoken_form:
            continue
        pattern = re.compile(r'\b' + re.escape(abbreviation) + r'\b')
        result = pattern.sub(spoken_form, result)

    return result


def convert_scene_breaks(text: str) -> str:
    """Replace scene break markers with SSML pause tags."""
    result = text
    for pattern in SCENE_BREAK_PATTERNS:
        result = pattern.sub(SCENE_BREAK_SSML, result)

    # Collapse 3+ consecutive blank lines into a scene break pause
    result = re.sub(r'\n{4,}', f'\n\n{SCENE_BREAK_SSML}\n\n', result)

    return result


def _strip_redundant_chapter_heading(text: str, chapter_number: int) -> str:
    """Remove the first line if it's a chapter heading that duplicates the announcement.

    Matches patterns like:
      "Chapter 1: Title", "Chapter 1 - Title", "Chapter 1. Title",
      "Chapter One", "CHAPTER 1", "1. Title", "1 - Title", bare "Chapter 1"
    """
    lines = text.lstrip('\n').split('\n', 1)
    if not lines:
        return text

    first_line = lines[0].strip()
    if not first_line:
        return text

    first_lower = first_line.lower()

    # "Chapter N" or "Chapter N: ...", "Chapter N - ...", "CHAPTER N"
    ch_prefix = f"chapter {chapter_number}"
    if first_lower.startswith(ch_prefix):
        rest_of_first = first_lower[len(ch_prefix):].lstrip()
        if not rest_of_first or rest_of_first[0] in (':', '-', '.', ',', '—'):
            return lines[1].lstrip('\n') if len(lines) > 1 else ''

    # Written-out numbers for chapters 1-20
    number_words = {
        1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five',
        6: 'six', 7: 'seven', 8: 'eight', 9: 'nine', 10: 'ten',
        11: 'eleven', 12: 'twelve', 13: 'thirteen', 14: 'fourteen',
        15: 'fifteen', 16: 'sixteen', 17: 'seventeen', 18: 'eighteen',
        19: 'nineteen', 20: 'twenty',
    }
    word = number_words.get(chapter_number)
    if word:
        word_prefix = f"chapter {word}"
        if first_lower.startswith(word_prefix):
            rest = first_lower[len(word_prefix):].lstrip()
            if not rest or rest[0] in (':', '-', '.', ',', '—'):
                return lines[1].lstrip('\n') if len(lines) > 1 else ''

    # "1. Title" or "1 - Title" (bare number at start)
    num_pattern = re.match(r'^' + str(chapter_number) + r'\s*[.\-:—]\s*', first_line)
    if num_pattern:
        remainder = first_line[num_pattern.end():].strip()
        body = lines[1].lstrip('\n') if len(lines) > 1 else ''
        if not remainder:
            return body
        return body

    return text


def add_chapter_announcement(text: str, chapter_number: int, chapter_title: Optional[str] = None) -> str:
    """Prepend a spoken chapter announcement with a pause.

    Also strips any redundant chapter heading from the body to avoid
    the TTS reading "Chapter 1" twice.
    """
    text = _strip_redundant_chapter_heading(text, chapter_number)

    if chapter_title and chapter_title.strip():
        announcement = f"Chapter {chapter_number}. {chapter_title.strip()}."
    else:
        announcement = f"Chapter {chapter_number}."

    return f"{announcement}\n{CHAPTER_PAUSE_SSML}\n\n{text}"


def normalize_characters(text: str) -> str:
    """Normalize unicode characters for natural TTS rendering."""
    result = text

    # Smart quotes to straight quotes
    result = result.replace('\u201c', '"').replace('\u201d', '"')
    result = result.replace('\u2018', "'").replace('\u2019', "'")

    # Em dash to comma for natural pause
    result = result.replace('\u2014', ', ')
    # En dash to hyphen
    result = result.replace('\u2013', '-')

    # Ellipsis character to dots
    result = result.replace('\u2026', '...')

    # Remove zero-width characters
    result = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', result)

    # Non-breaking space to regular space
    result = result.replace('\u00a0', ' ')

    # Collapse multiple spaces
    result = re.sub(r' {2,}', ' ', result)

    return result


def chunk_at_sentence_boundaries(text: str, max_chars: int = MAX_CHUNK_CHARS) -> List[str]:
    """Split text into chunks at sentence boundaries.

    Never splits mid-sentence. Stays under max_chars per chunk.
    """
    if len(text) <= max_chars:
        return [text.strip()] if text.strip() else []

    # Split into sentences using punctuation followed by whitespace
    sentence_pattern = re.compile(r'(?<=[.!?])\s+')
    sentences = sentence_pattern.split(text)

    chunks: List[str] = []
    current_chunk: List[str] = []
    current_length = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        sentence_len = len(sentence) + 1  # +1 for space between sentences

        if current_length + sentence_len > max_chars and current_chunk:
            chunks.append(' '.join(current_chunk))
            current_chunk = [sentence]
            current_length = len(sentence)
        else:
            current_chunk.append(sentence)
            current_length += sentence_len

    if current_chunk:
        chunks.append(' '.join(current_chunk))

    # Safety: if any single sentence exceeds max_chars, split on clause boundaries
    final_chunks: List[str] = []
    for chunk in chunks:
        if len(chunk) <= max_chars:
            final_chunks.append(chunk)
        else:
            # Fall back to splitting on commas/semicolons
            clause_parts = re.split(r'(?<=[,;])\s+', chunk)
            sub_chunk: List[str] = []
            sub_len = 0
            for part in clause_parts:
                if sub_len + len(part) + 1 > max_chars and sub_chunk:
                    final_chunks.append(' '.join(sub_chunk))
                    sub_chunk = [part]
                    sub_len = len(part)
                else:
                    sub_chunk.append(part)
                    sub_len += len(part) + 1
            if sub_chunk:
                final_chunks.append(' '.join(sub_chunk))

    return [c for c in final_chunks if c.strip()]


def prepare_chapter(
    raw_markdown: str,
    chapter_number: int,
    chapter_title: Optional[str] = None,
    glossary: Optional[List[Dict[str, str]]] = None,
) -> List[str]:
    """Full preprocessing pipeline for a single chapter.

    Returns a list of TTS-ready text chunks.
    """
    text = raw_markdown or ""

    # Step 1: Strip markdown formatting
    text = strip_markdown(text)

    # Step 2: Apply pronunciation glossary
    if glossary:
        text = apply_pronunciation_glossary(text, glossary)

    # Step 3: Convert scene breaks to SSML pauses
    text = convert_scene_breaks(text)

    # Step 4: Normalize unicode characters
    text = normalize_characters(text)

    # Step 5: Add chapter announcement
    text = add_chapter_announcement(text, chapter_number, chapter_title)

    # Step 6: Clean up whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    # Step 7: Chunk at sentence boundaries
    chunks = chunk_at_sentence_boundaries(text)

    logger.info(
        f"Prepared chapter {chapter_number}: {len(raw_markdown)} chars -> "
        f"{sum(len(c) for c in chunks)} chars in {len(chunks)} chunks"
    )
    return chunks


def detect_abbreviations(chapters_text: List[str]) -> List[Dict[str, str]]:
    """Scan chapter texts for likely abbreviations and suggest spoken forms.

    Returns a list of suggested glossary entries sorted by frequency.
    """
    counts: Dict[str, int] = {}
    for text in chapters_text:
        for match in ABBREVIATION_PATTERN.finditer(text):
            token = match.group(1)
            # Skip very common English words that happen to be all-caps
            if token in {'I', 'A', 'OK', 'US', 'AM', 'PM', 'TV', 'OR', 'AN',
                         'IN', 'ON', 'IT', 'IF', 'IS', 'AT', 'AS', 'DO', 'NO',
                         'SO', 'TO', 'UP', 'BY', 'WE', 'HE', 'ME', 'MY', 'BE'}:
                # Only skip 1-2 letter common words; DO stays since it's
                # a real abbreviation in many technical domains
                if len(token) <= 2 and token not in {'DO'}:
                    continue
            counts[token] = counts.get(token, 0) + 1

    # Only suggest abbreviations that appear at least twice
    suggestions: List[Dict[str, str]] = []
    for token, count in sorted(counts.items(), key=lambda x: -x[1]):
        if count < 2:
            continue
        # Auto-generate spoken form by spacing letters
        spoken = '. '.join(token) + '.'
        suggestions.append({
            'abbreviation': token,
            'spoken_form': spoken,
            'occurrences': count,
        })

    logger.info(f"Detected {len(suggestions)} abbreviation candidates")
    return suggestions


def estimate_characters(
    chapters: List[Dict[str, Any]],
    glossary: Optional[List[Dict[str, str]]] = None,
) -> int:
    """Estimate total character count after preprocessing.

    Args:
        chapters: List of chapter dicts with 'content', 'chapter_number', 'title' keys
        glossary: Optional pronunciation glossary

    Returns:
        Total character count for cost estimation
    """
    total = 0
    for ch in chapters:
        content = ch.get('content', '')
        chapter_number = ch.get('chapter_number', 1)
        title = ch.get('title', '')
        chunks = prepare_chapter(content, chapter_number, title, glossary)
        total += sum(len(c) for c in chunks)
    return total
