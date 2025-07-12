"""
Reference File Generator
Parses book-bible.md content and generates individual reference files.
"""
import re
from pathlib import Path
from typing import Dict, List, Tuple


def generate_reference_files(book_bible_text: str, references_dir: Path) -> List[str]:
    """
    Parse book-bible.md content and generate individual reference files.
    
    Args:
        book_bible_text: The complete book bible markdown content
        references_dir: Path to the references directory
        
    Returns:
        List of filenames that were created
    """
    # Ensure references directory exists
    references_dir.mkdir(parents=True, exist_ok=True)
    
    # Split content by top-level headings (## sections)
    sections = _parse_sections(book_bible_text)
    
    # Map section names to filenames
    section_mapping = {
        'characters': 'characters.md',
        'character': 'characters.md',
        'outline': 'outline.md',
        'plot': 'outline.md',
        'story': 'outline.md',
        'structure': 'outline.md',
        'world': 'world-building.md',
        'worldbuilding': 'world-building.md',
        'world-building': 'world-building.md',
        'setting': 'world-building.md',
        'style': 'style-guide.md',
        'voice': 'style-guide.md',
        'tone': 'style-guide.md',
        'writing': 'style-guide.md',
        'theme': 'plot-timeline.md',
        'themes': 'plot-timeline.md',
        'timeline': 'plot-timeline.md',
        'research': 'research-notes.md',
        'notes': 'research-notes.md'
    }
    
    created_files = []
    file_contents = {}
    
    # Process each section
    for section_name, content in sections.items():
        if not content.strip():
            continue
            
        # Determine target filename
        section_key = section_name.lower().replace(' ', '').replace('-', '')
        filename = section_mapping.get(section_key, 'misc-notes.md')
        
        # Accumulate content for each file (in case multiple sections map to same file)
        if filename not in file_contents:
            file_contents[filename] = []
        
        file_contents[filename].append(f"## {section_name}\n\n{content.strip()}")
    
    # Write files
    for filename, content_parts in file_contents.items():
        file_path = references_dir / filename
        combined_content = "\n\n".join(content_parts)
        
        file_path.write_text(combined_content, encoding='utf-8')
        created_files.append(filename)
    
    # Create default files if they don't exist
    default_files = [
        ('characters.md', _get_default_characters_template()),
        ('outline.md', _get_default_outline_template()),
        ('world-building.md', _get_default_worldbuilding_template()),
        ('style-guide.md', _get_default_style_template()),
        ('plot-timeline.md', _get_default_timeline_template())
    ]
    
    for filename, template in default_files:
        file_path = references_dir / filename
        if not file_path.exists():
            file_path.write_text(template, encoding='utf-8')
            created_files.append(filename)
    
    return sorted(list(set(created_files)))


def _parse_sections(text: str) -> Dict[str, str]:
    """
    Parse markdown text into sections based on ## headings.
    
    Args:
        text: The markdown text to parse
        
    Returns:
        Dictionary mapping section names to their content
    """
    sections = {}
    
    # Split by ## headings
    parts = re.split(r'^## +(.+)$', text, flags=re.MULTILINE)
    
    # First part is content before any ## heading (usually title/intro)
    if len(parts) > 1:
        # Process pairs of (heading, content)
        for i in range(1, len(parts), 2):
            if i + 1 < len(parts):
                heading = parts[i].strip()
                content = parts[i + 1].strip()
                sections[heading] = content
    
    return sections


def _get_default_characters_template() -> str:
    """Get default template for characters.md"""
    return """# Characters

## Main Characters

### [Character Name]
- **Age:** 
- **Occupation:** 
- **Background:** 
- **Personality:** 
- **Goals:** 
- **Conflicts:** 
- **Character Arc:** 

## Supporting Characters

### [Character Name]
- **Role:** 
- **Relationship to MC:** 
- **Key Traits:** 

## Character Voice Guidelines

- **Dialogue Style:** 
- **Speech Patterns:** 
- **Vocabulary Level:** 
- **Emotional Expression:** 
"""


def _get_default_outline_template() -> str:
    """Get default template for outline.md"""
    return """# Story Outline

## Three-Act Structure

### Act I - Setup
- **Hook:** 
- **Inciting Incident:** 
- **Plot Point 1:** 

### Act II - Confrontation
- **Rising Action:** 
- **Midpoint:** 
- **Plot Point 2:** 

### Act III - Resolution
- **Climax:** 
- **Falling Action:** 
- **Resolution:** 

## Chapter Breakdown

### Chapter 1
- **Purpose:** 
- **Key Events:** 
- **Character Development:** 
- **Word Count Target:** 

### Chapter 2
- **Purpose:** 
- **Key Events:** 
- **Character Development:** 
- **Word Count Target:** 
"""


def _get_default_worldbuilding_template() -> str:
    """Get default template for world-building.md"""
    return """# World Building

## Setting

### Time Period
- **Era:** 
- **Specific Year/Date:** 

### Location
- **Primary Setting:** 
- **Secondary Locations:** 
- **Geography:** 

## Society & Culture

### Social Structure
- **Government:** 
- **Economy:** 
- **Class System:** 

### Daily Life
- **Technology Level:** 
- **Transportation:** 
- **Communication:** 
- **Entertainment:** 

## Rules & Constraints

### Physical Laws
- **Natural Laws:** 
- **Supernatural Elements:** 

### Social Rules
- **Cultural Norms:** 
- **Taboos:** 
- **Traditions:** 
"""


def _get_default_style_template() -> str:
    """Get default template for style-guide.md"""
    return """# Style Guide

## Narrative Voice

### Point of View
- **POV Type:** (First/Third Person, Limited/Omniscient)
- **Narrator Characteristics:** 

### Tone
- **Overall Tone:** 
- **Mood:** 
- **Atmosphere:** 

## Writing Style

### Sentence Structure
- **Average Length:** 
- **Complexity:** 
- **Rhythm:** 

### Vocabulary
- **Register:** (Formal/Informal)
- **Specialized Terms:** 
- **Avoiding:** 

## Consistency Guidelines

### Character Voice
- **Dialogue Patterns:** 
- **Internal Monologue:** 

### Descriptions
- **Level of Detail:** 
- **Sensory Focus:** 
- **Metaphor Style:** 

### Pacing
- **Action Scenes:** 
- **Dialogue Scenes:** 
- **Descriptive Passages:** 
"""


def _get_default_timeline_template() -> str:
    """Get default template for plot-timeline.md"""
    return """# Plot Timeline

## Story Timeline

### Before Story Begins
- **Backstory Events:** 
- **Character History:** 

### Story Events

#### Day 1
- **Morning:** 
- **Afternoon:** 
- **Evening:** 

#### Day 2
- **Morning:** 
- **Afternoon:** 
- **Evening:** 

## Thematic Development

### Theme 1: [Theme Name]
- **Introduction:** 
- **Development:** 
- **Resolution:** 

### Theme 2: [Theme Name]
- **Introduction:** 
- **Development:** 
- **Resolution:** 

## Character Arc Timeline

### [Character Name]
- **Starting Point:** 
- **Midpoint Change:** 
- **End Point:** 
""" 