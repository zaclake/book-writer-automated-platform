"""
Reference Content Generator
Uses OpenAI API to generate rich, book-specific content for reference files based on book bible and YAML prompts.
"""
import os
import json
import yaml
import logging
import asyncio
from functools import partial
from pathlib import Path
from typing import Dict, Any, Optional, List
try:
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except Exception:
    OpenAI = None
    _OPENAI_AVAILABLE = False
# Concurrency controls with robust import fallbacks
try:
    from backend.system.concurrency import (
        get_llm_semaphore,
        semaphore,
        get_llm_thread_semaphore,
        thread_semaphore,
    )
except Exception:
    try:
        from ..system.concurrency import (
            get_llm_semaphore,
            semaphore,
            get_llm_thread_semaphore,
            thread_semaphore,
        )
    except Exception:
        try:
            from system.concurrency import (
                get_llm_semaphore,
                semaphore,
                get_llm_thread_semaphore,
                thread_semaphore,
            )
        except Exception:
            import threading  # type: ignore
            import asyncio  # type: ignore

            _llm_sem = None
            _llm_thread_sem = None

            def _get_int_env(name: str, default: int) -> int:
                try:
                    return max(1, int(os.getenv(name, str(default))))
                except Exception:
                    return default

            def get_llm_semaphore() -> 'asyncio.Semaphore':  # type: ignore
                global _llm_sem
                if _llm_sem is None:
                    _llm_sem = asyncio.Semaphore(_get_int_env("MAX_CONCURRENT_LLM", 6))
                return _llm_sem

            def get_llm_thread_semaphore() -> 'threading.BoundedSemaphore':  # type: ignore
                global _llm_thread_sem
                if _llm_thread_sem is None:
                    _llm_thread_sem = threading.BoundedSemaphore(_get_int_env("MAX_CONCURRENT_LLM", 6))
                return _llm_thread_sem

            class semaphore:  # type: ignore
                def __init__(self, sem):
                    self._sem = sem
                async def __aenter__(self):
                    await self._sem.acquire()
                    return self
                async def __aexit__(self, exc_type, exc, tb):
                    self._sem.release()
                    return False

            class thread_semaphore:  # type: ignore
                def __init__(self, sem):
                    self._sem = sem
                def __enter__(self):
                    self._sem.acquire()
                    return self
                def __exit__(self, exc_type, exc, tb):
                    self._sem.release()
                    return False

logger = logging.getLogger(__name__)


class ReferenceContentGenerator:
    """Generates AI-powered content for reference files based on book bible and prompts."""
    
    def __init__(self, prompts_dir: Optional[Path] = None, user_id: Optional[str] = None):
        """
        Initialize the content generator.
        
        Args:
            prompts_dir: Directory containing YAML prompt files (defaults to prompts/reference-generation)
            user_id: User ID for billing (if None, billing is disabled)
        """
        self.client = None
        self.sync_client = None
        self.user_id = user_id
        self.billable_client = False
        
        if prompts_dir:
            self.prompts_dir = prompts_dir
        else:
            # Simple path resolution
            self.prompts_dir = Path(__file__).parent.parent / "prompts" / "reference-generation"
        
        # Initialize OpenAI client if API key is available
        api_key = os.getenv('OPENAI_API_KEY')
        if not _OPENAI_AVAILABLE:
            logger.warning("OpenAI library not installed. Reference generation disabled.")
        elif api_key:
            self.sync_client = OpenAI(api_key=api_key)
            if self.user_id and os.getenv('ENABLE_CREDITS_BILLING', 'false').lower() == 'true':
                # Try to use billable client
                try:
                    from backend.services.billable_client import create_billable_openai_client
                    self.client = create_billable_openai_client(user_id=self.user_id, api_key=api_key)
                    self.billable_client = True
                    logger.info(f"Reference content generator initialized with billable client for user {user_id}")
                except Exception as e:
                    # Fallback to regular client
                    self.client = self.sync_client
                    self.billable_client = False
                    logger.warning(f"Failed to initialize billable client for reference generation: {e}")
            else:
                self.client = self.sync_client
                self.billable_client = False
        else:
            logger.warning("OPENAI_API_KEY not found. Content generation will be disabled.")
    
    def is_available(self) -> bool:
        """Check if content generation is available (API key configured)."""
        return self.client is not None and _OPENAI_AVAILABLE

    def _call_chat_completion(self, **kwargs):
        """Invoke chat completions with billing-aware fallback."""
        if self.billable_client:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                billable_response = asyncio.run(self.client.chat_completions_create(**kwargs))
                return billable_response.response
            # Avoid deadlocking inside a running loop; fall back to sync client
            if self.sync_client:
                logger.warning("Billable client called from running loop; falling back to sync OpenAI client.")
                return self.sync_client.chat.completions.create(**kwargs)
        if self.sync_client:
            return self.sync_client.chat.completions.create(**kwargs)
        return self.client.chat.completions.create(**kwargs)

    def _call_responses_completion(self, **kwargs):
        """Invoke Responses API with billing-aware fallback."""
        input_messages = kwargs.pop("messages", None)
        if input_messages is None:
            input_messages = kwargs.pop("input", None)
        if input_messages is None:
            raise ValueError("Responses API requires input or messages")
        max_tokens = kwargs.pop("max_tokens", None)
        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens
        for key in ("frequency_penalty", "presence_penalty", "temperature", "top_p"):
            kwargs.pop(key, None)

        if self.billable_client:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                billable_response = asyncio.run(self.client.responses_create(input=input_messages, **kwargs))
                return billable_response.response
            if self.sync_client and hasattr(self.sync_client, "responses"):
                logger.warning("Billable responses called from running loop; falling back to sync OpenAI client.")
                return self.sync_client.responses.create(input=input_messages, **kwargs)

        client = self.sync_client or self.client
        if not hasattr(client, "responses"):
            raise RuntimeError("OpenAI Responses API not available in client runtime.")
        return client.responses.create(input=input_messages, **kwargs)

    def _extract_response_text(self, response) -> str:
        """Normalize output text from chat or responses APIs."""
        if hasattr(response, "output_text"):
            return response.output_text or ""
        if hasattr(response, "choices"):
            try:
                return response.choices[0].message.content or ""
            except Exception:
                return ""
        return ""

    async def apply_reference_edit(
        self,
        reference_type: str,
        current_content: str,
        instructions: str,
        scope: str = "document",
        section_title: Optional[str] = None
    ) -> str:
        """Apply user instructions to update an existing reference document or section."""
        if not self.is_available():
            raise Exception("OpenAI API not available. Check OPENAI_API_KEY configuration.")

        cleaned_type = reference_type.replace('-', ' ').strip()
        if scope == "section":
            system_prompt = (
                "You are a senior story editor. Update the provided reference section using the user's instructions. "
                "Preserve all relevant facts unless explicitly asked to change them. "
                "Return only the updated section text without any title, headings, or markdown symbols. "
                "Use short paragraphs or labeled lines (e.g., 'Goal: ...') where helpful."
            )
        else:
            system_prompt = (
                "You are a senior story editor. Update the existing reference document using the user's instructions. "
                "Preserve all relevant facts unless explicitly asked to change them. "
                "Return a clean, human-readable document with clear section titles on their own lines. "
                "Avoid markdown symbols like #, *, -, backticks, or numbered list prefixes. "
                "Use short paragraphs or labeled lines (e.g., 'Goal: ...') where helpful. "
                "Return only the updated document text."
            )

        user_prompt = (
            f"REFERENCE TYPE: {cleaned_type}\n\n"
            f"SECTION TITLE: {section_title or 'N/A'}\n\n"
            "CURRENT DOCUMENT:\n"
            f"{current_content}\n\n"
            "USER INSTRUCTIONS:\n"
            f"{instructions}\n"
        )

        request_label = "section" if scope == "section" else "document"
        return await self._make_openai_request(system_prompt, user_prompt, f"reference_edit_{reference_type}_{request_label}")
    
    async def expand_book_bible(self, source_data: dict, creation_mode: str, book_specs: dict) -> str:
        """
        Expand QuickStart or Guided wizard data into a comprehensive book bible using OpenAI.
        
        Args:
            source_data: Data from QuickStart or Guided wizard
            creation_mode: 'quickstart' or 'guided'
            book_specs: Book length specifications (target_chapters, word_count, etc.)
            
        Returns:
            Expanded book bible content as markdown
        """
        if not self.is_available():
            raise Exception("OpenAI API not available. Check OPENAI_API_KEY configuration.")
        
        try:
            # Build the expansion prompt based on creation mode
            if creation_mode == 'quickstart':
                return await self._expand_quickstart_data(source_data, book_specs)
            elif creation_mode == 'guided':
                return await self._expand_guided_data(source_data, book_specs)
            else:
                raise ValueError(f"Unsupported creation mode: {creation_mode}")
                
        except Exception as e:
            logger.error(f"Failed to expand book bible for mode {creation_mode}: {e}")
            raise
    
    async def _expand_quickstart_data(self, data: dict, book_specs: dict) -> str:
        """Expand QuickStart data into full book bible."""
        system_prompt = """You are an expert story development assistant. Your task is to take basic story elements and expand them into a comprehensive book bible that will guide the writing of a full novel.

You must create a detailed, professional book bible that includes:
1. Expanded character profiles with motivations, backstories, and arcs
2. Rich world-building with specific details about setting, culture, and rules  
3. Detailed plot structure with three-act breakdown and chapter outline
4. Themes and motifs woven throughout the story
5. Writing style guidelines and tone consistency
6. Conflict escalation and resolution planning

The book bible should be comprehensive enough for a writer to begin crafting chapters immediately."""

        user_prompt = f"""Please expand the following basic story elements into a comprehensive book bible:

**Title:** {data.get('title', 'Untitled')}
**Genre:** {data.get('genre', 'Fiction')}
**Brief Premise:** {data.get('brief_premise', 'Not provided')}
**Main Character:** {data.get('main_character', 'Not provided')}
**Setting:** {data.get('setting', 'Not provided')}
**Central Conflict:** {data.get('conflict', 'Not provided')}

**Book Specifications:**
- Target Chapters: {book_specs.get('chapter_count_target', 25)}
- Target Word Count: {book_specs.get('word_count_target', 75000):,} words
- Words per Chapter: {book_specs.get('avg_words_per_chapter', 3000)}

Create a detailed book bible in markdown format that includes:

## Story Overview
- Expanded premise with deeper thematic elements
- Genre-specific conventions and expectations

## Character Development
- Detailed main character profile with background, motivations, flaws, and character arc
- Supporting characters and their relationships
- Character growth throughout the story

## World Building
- Expanded setting details with specific locations
- Cultural, social, and historical context
- Rules and constraints of this world

## Plot Structure
- Three-act structure breakdown
- Major plot points and turning points
- Chapter-by-chapter outline with key scenes
- Conflict escalation and resolution

## Themes and Motifs
- Central themes explored in the story
- Recurring motifs and symbols
- How themes develop across chapters

## Writing Guidelines
- Tone and voice consistency
- Point of view and narrative style
- Genre-specific elements to include

Generate comprehensive, specific content that gives a writer everything needed to begin writing chapters immediately."""

        return await self._make_openai_request(system_prompt, user_prompt, "book_bible_expansion")
    
    async def _expand_guided_data(self, data: dict, book_specs: dict) -> str:
        """Expand Guided wizard data into full book bible."""
        system_prompt = """You are an expert story development assistant. Your task is to take detailed story planning information and synthesize it into a comprehensive, professional book bible for novel writing.

You must create a cohesive book bible that weaves together all the provided elements into a unified vision, expanding where needed and ensuring consistency throughout. The book bible should be detailed enough for immediate chapter writing."""

        user_prompt = f"""Please synthesize and expand the following detailed story elements into a comprehensive book bible:

**Title:** {data.get('title', 'Untitled')}
**Genre:** {data.get('genre', 'Fiction')}
**Premise:** {data.get('premise', 'Not provided')}
**Main Characters:** {data.get('main_characters', 'Not provided')}
**Setting Time:** {data.get('setting_time', 'Not provided')}
**Setting Place:** {data.get('setting_place', 'Not provided')}
**Central Conflict:** {data.get('central_conflict', 'Not provided')}
**Themes:** {data.get('themes', 'Not provided')}
**Target Audience:** {data.get('target_audience', 'Not provided')}
**Tone:** {data.get('tone', 'Not provided')}
**Key Plot Points:** {data.get('key_plot_points', 'Not provided')}

**Book Specifications:**
- Target Chapters: {book_specs.get('chapter_count_target', 25)}
- Target Word Count: {book_specs.get('word_count_target', 75000):,} words
- Words per Chapter: {book_specs.get('avg_words_per_chapter', 3000)}

Create a detailed, cohesive book bible in markdown format that includes:

## Story Overview
- Unified premise incorporating all provided elements
- Genre analysis and reader expectations

## Character Profiles
- Expanded character descriptions with psychological depth
- Character relationships and dynamics
- Character arcs and development throughout the story

## World and Setting
- Detailed world-building combining time and place elements
- Cultural, historical, and environmental context
- Specific locations and their significance

## Plot Architecture
- Comprehensive plot structure incorporating provided plot points
- Three-act breakdown with clear progression
- Detailed chapter outline with scene descriptions
- Conflict development and resolution path

## Thematic Framework
- Deep exploration of provided themes
- How themes manifest in plot, character, and setting
- Thematic consistency throughout chapters

## Voice and Style Guide
- Tone implementation guidelines based on target audience
- Narrative voice and point of view decisions
- Style consistency for the specified tone: "{data.get('tone', 'Not specified')}"

## Writing Direction
- Scene-by-scene guidance for opening chapters
- Pacing and rhythm guidelines
- Key scenes that must be included

Ensure all elements work together cohesively and provide specific, actionable guidance for writing."""

        return await self._make_openai_request(system_prompt, user_prompt, "book_bible_expansion")
    
    async def _make_openai_request(self, system_prompt: str, user_prompt: str, request_type: str) -> str:
        """Make OpenAI API request with exponential back-off on rate limits."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        import time
        import random
        max_retries = 3
        base_delay = 2.0  # Start with 2 second delay
        # Note: GPT-4o limit is roughly 10 requests or 10k tokens per minute for most orgs.
        # We reduce max_tokens and pace requests accordingly; see generate_all_references.
        
        for attempt in range(max_retries + 1):
            try:
                start_time = time.time()
                
                if attempt > 0:
                    # Exponential back-off with jitter for rate limits
                    delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1)
                    logger.info(f"Retrying OpenAI request for {request_type} (attempt {attempt + 1}/{max_retries + 1}) after {delay:.1f}s delay")
                    await asyncio.sleep(delay)
                
                logger.info(f"Starting OpenAI API request for {request_type} (attempt {attempt + 1})")
                
                if self.billable_client:
                    # Use billable client guarded by async semaphore
                    async with semaphore(get_llm_semaphore()):
                        billable_response = await self.client.chat_completions_create(
                            model='gpt-4o',
                            messages=messages,
                            temperature=0.7,
                            max_tokens=1800,  # keep well under 10k TPM across multiple calls
                            top_p=0.9,
                            timeout=120
                        )
                        response = billable_response.response
                        credits_charged = billable_response.credits_charged
                        logger.info(f"Credits charged for {request_type}: {credits_charged}")
                else:
                    # Use regular client in threadpool guarded by thread semaphore
                    with thread_semaphore(get_llm_thread_semaphore()):
                        response = await asyncio.to_thread(
                            partial(
                                self.client.chat.completions.create,
                                model='gpt-4o',
                                messages=messages,
                                temperature=0.7,
                                max_tokens=1800,
                                top_p=0.9,
                                timeout=120
                            )
                        )
                
                duration = time.time() - start_time
                content = response.choices[0].message.content
                
                logger.info(f"OpenAI API request completed for {request_type} in {duration:.2f}s, generated {len(content)} characters")
                
                if not content or len(content.strip()) < 200:
                    raise Exception("Generated content is too short or empty")
                
                return content
                
            except Exception as e:
                error_str = str(e).lower()
                
                # Check if this is a rate limit error that we should retry
                if ("rate_limit" in error_str or "429" in error_str or "insufficient_quota" in error_str) and attempt < max_retries:
                    logger.warning(f"Rate limit hit for {request_type} on attempt {attempt + 1}, will retry")
                    continue
                
                # For other errors or final attempt, log and raise
                logger.error(f"OpenAI API request failed for {request_type} (attempt {attempt + 1}): {e}")
                
                if "timeout" in error_str:
                    raise Exception("Content generation timed out. Please try again.")
                elif "rate_limit" in error_str or "429" in error_str or "insufficient_quota" in error_str:
                    raise Exception("API rate limit exceeded after retries. Please try again later.")
                elif "authentication" in error_str:
                    raise Exception("OpenAI API authentication failed. Please check your API key.")
                else:
                    raise Exception(f"Content generation failed: {str(e)}")
        
        # This should never be reached due to the logic above, but just in case
        raise Exception(f"Failed to complete request for {request_type} after {max_retries + 1} attempts")
    
    def load_prompt(self, reference_type: str) -> Dict[str, Any]:
        """
        Load YAML prompt configuration for a specific reference type.
        
        Args:
            reference_type: Type of reference (characters, outline, world-building, style-guide, plot-timeline)
            
        Returns:
            Dictionary containing prompt configuration
            
        Raises:
            FileNotFoundError: If prompt file doesn't exist
        """
        # Simple fallback for missing prompt files
        fallback_prompt = {
            'name': f'{reference_type.title()} Reference Generator',
            'system_prompt': f'You are an expert {reference_type} specialist. Create comprehensive {reference_type} documentation based on the book bible.',
            'user_prompt_template': f'Based on this book bible content:\n\n{{book_bible_content}}\n\nCreate detailed {reference_type} documentation. Format as markdown.',
            'model_config': {'model': 'gpt-4o', 'temperature': 0.7, 'max_tokens': 3000}
        }
        
        prompt_file = self.prompts_dir / f"{reference_type}-prompt.yaml"
        
        if prompt_file.exists():
            try:
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    prompt_config = yaml.safe_load(f)
                
                # Validate required fields
                required_fields = ['name', 'system_prompt', 'user_prompt_template', 'model_config']
                for field in required_fields:
                    if field not in prompt_config:
                        logger.warning(f"Missing field {field} in prompt config, using fallback")
                        return fallback_prompt
                
                return prompt_config
                
            except Exception as e:
                logger.warning(f"Error loading prompt file {prompt_file}: {e}, using fallback")
                return fallback_prompt
        
        # Use fallback if file doesn't exist
        logger.info(f"Prompt file not found: {prompt_file}, using fallback")
        return fallback_prompt
    
    CHAINING_DEPENDENCIES: Dict[str, List[str]] = {
        "characters": [],
        "world-building": ["characters"],
        "outline": ["characters", "world-building"],
        "plot-timeline": ["characters", "outline"],
        "entity-registry": ["characters", "world-building"],
        "style-guide": ["characters"],
        "themes-and-motifs": ["outline"],
        "director-guide": ["outline", "characters", "style-guide"],
        "relationship-map": ["characters", "outline", "plot-timeline"],
        "research-notes": [],
        "target-audience-profile": [],
        "series-bible": [],
    }

    CHAINING_TRIM_LIMITS: Dict[str, int] = {
        "characters": 4000,
        "world-building": 3000,
        "outline": 4000,
        "plot-timeline": 3000,
        "style-guide": 2000,
        "themes-and-motifs": 2000,
        "entity-registry": 3000,
        "relationship-map": 3000,
    }

    @staticmethod
    def _build_book_length_context(
        book_length_tier: Optional[str] = None,
        estimated_chapters: Optional[int] = None,
        target_word_count: Optional[int] = None,
        bible_word_count: Optional[int] = None,
    ) -> str:
        parts: List[str] = []

        if any([book_length_tier, estimated_chapters, target_word_count]):
            parts.append("BOOK LENGTH CONTEXT:")
            if book_length_tier:
                tier_label = book_length_tier.replace("_", " ").title()
                parts.append(f"- Length Tier: {tier_label}")
                if "short" in book_length_tier.lower() or "novella" in book_length_tier.lower():
                    parts.append("- Guidance: This is a SHORT book. Prioritize depth over breadth. Fewer characters with richer profiles. Scene-level detail per chapter.")
                elif "long" in book_length_tier.lower() or "epic" in book_length_tier.lower():
                    parts.append("- Guidance: This is a LONG book. Include a larger supporting cast. Group chapters into sequences. Plan for multiple subplots and parallel arcs.")
                else:
                    parts.append("- Guidance: Standard-length novel. Balance breadth and depth appropriately.")
            if estimated_chapters:
                parts.append(f"- Estimated Chapters: {estimated_chapters}")
            if target_word_count:
                parts.append(f"- Target Word Count: {target_word_count:,} words")

        if bible_word_count is not None:
            if not parts:
                parts.append("INPUT DENSITY CONTEXT:")
            else:
                parts.append("")
                parts.append("INPUT DENSITY:")
            if bible_word_count < 100:
                parts.append(f"- The user's book bible is very brief ({bible_word_count} words). You MUST be highly creative: invent detailed characters, locations, plot structure, and world details that fit the genre and any hints provided. Build a fully realized story foundation from minimal input.")
            elif bible_word_count < 500:
                parts.append(f"- The user's book bible is brief ({bible_word_count} words). Fill in significant detail: create full character profiles, develop the setting, and build out the plot structure. Use genre conventions and any thematic hints to guide your extrapolation.")
            elif bible_word_count <= 2000:
                parts.append(f"- The user's book bible is moderate ({bible_word_count} words). Build on the details provided, filling gaps where the user left room. Balance extraction with intelligent extrapolation.")
            elif bible_word_count <= 5000:
                parts.append(f"- The user's book bible is moderately detailed ({bible_word_count} words). Use the provided details as the foundation and fill gaps where needed, but prioritize what the user has written.")
            else:
                parts.append(f"- The user's book bible is very detailed ({bible_word_count} words). Honor every specific detail the user has provided. Do not override, simplify, or contradict their vision. Extract and organize their content rather than inventing over it.")

        if not parts:
            return ""
        return "\n".join(parts)

    @staticmethod
    def _build_prior_references_context(
        prior_references: Optional[Dict[str, str]] = None,
        reference_type: str = "",
    ) -> str:
        if not prior_references:
            return ""
        deps = ReferenceContentGenerator.CHAINING_DEPENDENCIES.get(reference_type, [])
        if not deps:
            return ""
        sections = ["PREVIOUSLY GENERATED REFERENCES (use these for consistency — do not contradict):"]
        for dep in deps:
            content = prior_references.get(dep, "")
            if not content:
                continue
            limit = ReferenceContentGenerator.CHAINING_TRIM_LIMITS.get(dep, 3000)
            trimmed = content[:limit] + ("..." if len(content) > limit else "")
            label = dep.replace("-", " ").title()
            sections.append(f"\n--- {label} Reference ---\n{trimmed}")
        if len(sections) == 1:
            return ""
        return "\n".join(sections)

    def generate_content(self, reference_type: str, book_bible_content: str, 
                        additional_context: Optional[Dict[str, Any]] = None,
                        book_length_tier: Optional[str] = None,
                        estimated_chapters: Optional[int] = None,
                        target_word_count: Optional[int] = None,
                        prior_references: Optional[Dict[str, str]] = None) -> str:
        """
        Generate content for a specific reference file type.
        
        Args:
            reference_type: Type of reference to generate (characters, outline, etc.)
            book_bible_content: The complete book bible markdown content
            additional_context: Optional additional context to include in prompt
            book_length_tier: Optional book length tier (short_story, novella, standard, long, epic)
            estimated_chapters: Optional estimated chapter count
            target_word_count: Optional target word count
            prior_references: Optional dict of already-generated reference content keyed by type
            
        Returns:
            Generated markdown content for the reference file
            
        Raises:
            RuntimeError: If OpenAI API is not available
            Exception: If content generation fails
        """
        if not self.is_available():
            raise RuntimeError("OpenAI API key not configured. Cannot generate content.")
        
        # Load prompt configuration
        try:
            prompt_config = self.load_prompt(reference_type)
        except (FileNotFoundError, yaml.YAMLError, ValueError) as e:
            logger.error(f"Failed to load prompt for {reference_type}: {e}")
            raise Exception(f"Prompt loading failed: {e}")
        
        # Extract configuration
        model_config = prompt_config['model_config']
        system_prompt = prompt_config['system_prompt']
        user_prompt_template = prompt_config['user_prompt_template']
        
        # Build structured context for template rendering
        bible_word_count = len(book_bible_content.split()) if book_bible_content else 0
        book_length_context = self._build_book_length_context(
            book_length_tier=book_length_tier,
            estimated_chapters=estimated_chapters,
            target_word_count=target_word_count,
            bible_word_count=bible_word_count,
        )
        prior_refs_context = self._build_prior_references_context(
            prior_references=prior_references,
            reference_type=reference_type,
        )

        context = {
            'book_bible_content': book_bible_content,
            'book_length_context': book_length_context,
            'prior_references': prior_refs_context,
            **(additional_context or {})
        }
        
        # Legacy: also append book specs to bible content for backward compat
        if book_length_tier or estimated_chapters or target_word_count:
            book_specs = []
            if book_length_tier:
                book_specs.append(f"Book Length Category: {book_length_tier.replace('_', ' ').title()}")
            if estimated_chapters:
                book_specs.append(f"Estimated Chapters: {estimated_chapters}")
            if target_word_count:
                book_specs.append(f"Target Word Count: {target_word_count:,} words")
            context['book_specifications'] = "\n".join(book_specs)
            if book_specs:
                context['book_bible_content'] = f"{book_bible_content}\n\n## Book Specifications\n{context['book_specifications']}"
        
        # Provide safe defaults for all known optional template vars so missing
        # keys don't blow up formatting while preserving required vars like
        # {book_bible_content}.
        _optional_defaults = {
            'book_length_context': '',
            'prior_references': '',
            'book_specifications': '',
        }
        for key, default in _optional_defaults.items():
            context.setdefault(key, default)

        try:
            user_prompt = user_prompt_template.format(**context)
        except KeyError as e:
            # A template references a var we didn't anticipate.  Add an empty
            # default for that specific key and retry instead of stripping ALL
            # template vars (which would also remove {book_bible_content}).
            missing_key = str(e).strip("'\"")
            context[missing_key] = ''
            logger.warning(f"Template key {missing_key!r} missing for {reference_type}; defaulting to empty")
            try:
                user_prompt = user_prompt_template.format(**context)
            except KeyError as e2:
                context[str(e2).strip("'\"")]  = ''
                try:
                    user_prompt = user_prompt_template.format(**context)
                except Exception:
                    import re
                    user_prompt = re.sub(r'\{[a-zA-Z_]+\}', '', user_prompt_template)
                    logger.error(f"Multiple missing template keys for {reference_type}; stripped remaining vars")

        if reference_type != 'plot-timeline':
            user_prompt += (
                "\n\nOUTPUT REQUIREMENTS:\n"
                "- Replace all bracketed placeholders with concrete, story-specific details; do not include bracketed guidance.\n"
                "- Do not leave headings empty; every heading/subheading must include at least one sentence or bullet.\n"
                "- Avoid placeholder text like 'TBD', 'To be determined', or 'Not specified'.\n"
                "- When details are missing, infer plausible specifics consistent with the book bible and genre.\n"
            )
        else:
            user_prompt += (
                "\n\nOUTPUT NOTES:\n"
                "- Provide as many concrete must-include items as possible.\n"
                "- If a field is genuinely unknowable, omit it rather than leaving a placeholder.\n"
            )
        
        # Prepare messages for OpenAI API
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # Make API request with timeout and transient retry (handles 5xx/Cloudflare 502)
        import time
        import random
        max_attempts = 4
        base_delay = 2.0
        for attempt in range(1, max_attempts + 1):
            try:
                start_time = time.time()
                logger.info(f"Starting OpenAI API request for {reference_type} using {model_config.get('model', 'gpt-4o')} (attempt {attempt}/{max_attempts})")

                model_name = model_config.get('model', 'gpt-4o')
                use_responses = model_name.startswith("gpt-5")
                try:
                    if use_responses:
                        response = self._call_responses_completion(
                            model=model_name,
                            input=messages,
                            temperature=model_config.get('temperature', 0.7),
                            max_tokens=model_config.get('max_tokens', 4000),
                            top_p=model_config.get('top_p', 0.9),
                            timeout=90  # 90s per attempt
                        )
                    else:
                        response = self._call_chat_completion(
                            model=model_name,
                            messages=messages,
                            temperature=model_config.get('temperature', 0.7),
                            max_tokens=model_config.get('max_tokens', 4000),
                            top_p=model_config.get('top_p', 0.9),
                            timeout=90  # 90s per attempt
                        )
                except Exception as e:
                    if not use_responses and "not a chat model" in str(e).lower():
                        logger.warning("Chat completions rejected model; retrying with Responses API.")
                        response = self._call_responses_completion(
                            model=model_name,
                            input=messages,
                            temperature=model_config.get('temperature', 0.7),
                            max_tokens=model_config.get('max_tokens', 4000),
                            top_p=model_config.get('top_p', 0.9),
                            timeout=90  # 90s per attempt
                        )
                    else:
                        raise

                duration = time.time() - start_time
                logger.info(f"OpenAI API request completed for {reference_type} in {duration:.2f} seconds")

                generated_content = self._extract_response_text(response)

                if not generated_content or len(generated_content.strip()) < 100:
                    raise Exception("Generated content is too short or empty")

                if 'expected_sections' in prompt_config:
                    missing_sections = self._validate_content_sections(
                        generated_content,
                        prompt_config['expected_sections']
                    )
                    if missing_sections:
                        logger.warning(f"Generated content missing sections: {missing_sections}")

                logger.info(f"Successfully generated {len(generated_content)} characters for {reference_type}")
                return generated_content

            except Exception as e:
                error_str = str(e).lower()
                is_transient = any(tok in error_str for tok in ["502", "bad gateway", "5xx", "service unavailable"]) \
                    or "httpstatuserror" in error_str or "gateway" in error_str
                is_timeout = "timeout" in error_str
                is_rate = ("rate_limit" in error_str or "429" in error_str or "insufficient_quota" in error_str)

                # Retry transient (5xx) and rate limit errors with backoff
                if attempt < max_attempts and (is_transient or is_rate or is_timeout):
                    delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1)
                    logger.warning(f"Transient error for {reference_type} on attempt {attempt}: {e}. Retrying in {delay:.1f}s")
                    time.sleep(delay)
                    continue

                # Non-retryable or exhausted retries
                logger.error(f"OpenAI API request failed for {reference_type}: {e}")
                if is_timeout:
                    raise Exception("Content generation timed out. Please try again later.")
                if is_rate:
                    raise Exception("OpenAI API rate limit exceeded. Please wait and try again.")
                if "authentication" in error_str:
                    raise Exception("OpenAI API authentication failed. Please check your API key.")
                raise Exception(f"Content generation failed: {e}")
    
    def _validate_content_sections(self, content: str, expected_sections: List[str]) -> List[str]:
        """
        Validate that generated content contains expected sections.
        
        Args:
            content: Generated markdown content
            expected_sections: List of section names that should be present
            
        Returns:
            List of missing section names
        """
        missing_sections = []
        content_lower = content.lower()
        
        for section in expected_sections:
            # Look for section headers (## Section Name or # Section Name)
            section_patterns = [
                f"## {section.lower()}",
                f"# {section.lower()}",
                section.lower().replace(' ', '')  # Also check without spaces
            ]
            
            if not any(pattern in content_lower for pattern in section_patterns):
                missing_sections.append(section)
        
        return missing_sections
    
    CHAINED_GENERATION_ORDER: List[str] = [
        'characters',
        'world-building',
        'outline',
        'plot-timeline',
        'entity-registry',
        'style-guide',
        'themes-and-motifs',
        'director-guide',
        'relationship-map',
        'research-notes',
        'target-audience-profile',
    ]

    def generate_all_references(self, book_bible_content: str, 
                               references_dir: Path,
                               reference_types: Optional[List[str]] = None,
                               book_length_tier: Optional[str] = None,
                               estimated_chapters: Optional[int] = None,
                               target_word_count: Optional[int] = None,
                               include_series_bible: bool = False) -> Dict[str, Any]:
        """
        Generate content for all reference file types with chained context.
        
        Each reference is generated with access to previously-generated references
        as defined by CHAINING_DEPENDENCIES, ensuring consistency across documents.
        
        Args:
            book_bible_content: The complete book bible markdown content
            references_dir: Directory to write generated reference files
            reference_types: List of reference types to generate (defaults to chained order)
            book_length_tier: Optional book length tier
            estimated_chapters: Optional estimated chapter count
            target_word_count: Optional target word count
            include_series_bible: Whether to include series bible generation
            
        Returns:
            Dictionary with generation results for each reference type
        """
        if not self.is_available():
            return {"error": "OpenAI API key not configured"}
        
        if reference_types is None:
            reference_types = list(self.CHAINED_GENERATION_ORDER)
        
        if include_series_bible and 'series-bible' not in reference_types:
            reference_types.append('series-bible')
        
        results = {}
        generated_content: Dict[str, str] = {}
        references_dir.mkdir(parents=True, exist_ok=True)
        
        import time
        
        for i, ref_type in enumerate(reference_types):
            try:
                if i > 0:
                    delay = 12.0
                    logger.info(f"Waiting {delay}s before generating {ref_type} to respect rate limits")
                    time.sleep(delay)
                
                logger.info(f"Generating content for {ref_type} (chained with {len(generated_content)} prior references)")
                
                content = self.generate_content(
                    ref_type, 
                    book_bible_content,
                    book_length_tier=book_length_tier,
                    estimated_chapters=estimated_chapters,
                    target_word_count=target_word_count,
                    prior_references=generated_content if generated_content else None,
                )
                
                filename_map = {
                    'characters': 'characters.md',
                    'outline': 'outline.md',
                    'world-building': 'world-building.md',
                    'style-guide': 'style-guide.md',
                    'plot-timeline': 'plot-timeline.md',
                    'themes-and-motifs': 'themes-and-motifs.md',
                    'research-notes': 'research-notes.md',
                    'target-audience-profile': 'target-audience-profile.md',
                    'series-bible': 'series-bible.md',
                    'director-guide': 'director-guide.md',
                    'entity-registry': 'entity-registry.md',
                    'relationship-map': 'relationship-map.md',
                }
                
                filename = filename_map.get(ref_type, f"{ref_type}.md")
                file_path = references_dir / filename
                
                file_path.write_text(content, encoding='utf-8')
                
                generated_content[ref_type] = content
                
                results[ref_type] = {
                    "success": True,
                    "filename": filename,
                    "content_length": len(content),
                    "file_path": str(file_path)
                }
                
                logger.info(f"Successfully generated {filename} ({len(content)} characters)")
                
            except Exception as e:
                logger.error(f"Failed to generate {ref_type}: {e}")
                results[ref_type] = {
                    "success": False,
                    "error": str(e)
                }
        
        return results
    
    def regenerate_reference(self, reference_type: str, book_bible_content: str,
                           references_dir: Path) -> Dict[str, Any]:
        """
        Regenerate content for a specific reference file.
        
        Args:
            reference_type: Type of reference to regenerate
            book_bible_content: The complete book bible content
            references_dir: Directory containing reference files
            
        Returns:
            Dictionary with regeneration result
        """
        try:
            logger.info(f"Starting regeneration of {reference_type} reference")
            
            # Generate new content
            content = self.generate_content(reference_type, book_bible_content)
            
            # Determine filename and write
            filename_map = {
                'characters': 'characters.md',
                'outline': 'outline.md', 
                'world-building': 'world-building.md',
                'style-guide': 'style-guide.md',
                'plot-timeline': 'plot-timeline.md',
                'themes-and-motifs': 'themes-and-motifs.md',
                'research-notes': 'research-notes.md',
                'target-audience-profile': 'target-audience-profile.md',
                'series-bible': 'series-bible.md',
                'director-guide': 'director-guide.md',
                'entity-registry': 'entity-registry.md',
                'relationship-map': 'relationship-map.md',
            }
            
            filename = filename_map.get(reference_type, f"{reference_type}.md")
            file_path = references_dir / filename
            
            # Backup existing file if it exists
            if file_path.exists():
                backup_path = file_path.with_suffix('.bak')
                file_path.rename(backup_path)
                logger.info(f"Backed up existing {filename} to {backup_path.name}")
            
            # Write new content
            file_path.write_text(content, encoding='utf-8')
            
            return {
                "success": True,
                "filename": filename,
                "content_length": len(content),
                "file_path": str(file_path),
                "message": f"Successfully regenerated {filename}"
            }
            
        except Exception as e:
            logger.error(f"Failed to regenerate {reference_type}: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Regeneration failed for {reference_type}: {e}"
            }


# Convenience function for use in other modules
def generate_reference_content(reference_type: str, book_bible_content: str, 
                             output_path: Path) -> Dict[str, Any]:
    """
    Convenience function to generate content for a single reference file.
    
    Args:
        reference_type: Type of reference to generate
        book_bible_content: Book bible markdown content
        output_path: Path where to write the generated content
        
    Returns:
        Generation result dictionary
    """
    generator = ReferenceContentGenerator()
    
    if not generator.is_available():
        return {"success": False, "error": "OpenAI API not configured"}
    
    try:
        content = generator.generate_content(reference_type, book_bible_content)
        output_path.write_text(content, encoding='utf-8')
        
        return {
            "success": True,
            "content_length": len(content),
            "file_path": str(output_path)
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)} 