#!/usr/bin/env python3
"""
LLM Orchestrator - Phase 1 MVP
Robust implementation with retry logic, exponential back-off, and structured logging.
"""

import os
import json
import time
import random
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import logging
from datetime import datetime
import asyncio

# Third-party imports (will need to install)
try:
    import openai
    from openai import OpenAI
except ImportError:
    print("ERROR: OpenAI library not installed. Run: pip install openai")
    exit(1)

# Local imports
try:
    from backend.system.prompt_manager import PromptManager
except ImportError:
    # Fallback to the root-level prompt_manager
    try:
        from backend.prompt_manager import PromptManager
    except ImportError:
        # Final fallback - create a minimal PromptManager for testing
        class PromptManager:
            def __init__(self, prompts_dir):
                self.prompts_dir = prompts_dir
                self.logger = logging.getLogger(__name__)
                self.logger.warning("Using fallback PromptManager - YAML templates not available")
            
            def get_template(self, stage):
                return None
        
        logging.getLogger(__name__).error("PromptManager not available - using fallback")

@dataclass
class GenerationResult:
    """Result of a chapter generation attempt."""
    success: bool
    content: str
    metadata: Dict[str, Any]
    error: Optional[str] = None
    tokens_used: int = 0
    cost_estimate: float = 0.0
    retry_count: int = 0

@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True

class LLMOrchestrator:
    """Orchestrates LLM-based chapter generation with quality gate integration."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o", 
                 retry_config: Optional[RetryConfig] = None, prompts_dir: str = "prompts",
                 user_id: Optional[str] = None, enable_billing: Optional[bool] = None):
        """Initialize the orchestrator."""
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY environment variable.")
        
        self.model = model
        self.user_id = user_id
        self.retry_config = retry_config or RetryConfig()
        
        # Initialize client - use billable client if user_id provided and billing enabled
        billing_enabled = enable_billing if enable_billing is not None else os.getenv('ENABLE_CREDITS_BILLING', 'false').lower() == 'true'
        
        if self.user_id and billing_enabled:
            try:
                from ..services.billable_client import create_billable_openai_client
                self.client = create_billable_openai_client(user_id=self.user_id, api_key=self.api_key)
                self.billable_client = True
                self.logger = None  # Will be set up later
                self._setup_logging()
                self.logger.info(f"LLM Orchestrator initialized with billable client for user {user_id}")
            except Exception as e:
                # Fallback to regular client if billable client fails
                self.client = OpenAI(api_key=self.api_key)
                self.billable_client = False
                self.logger = None
                self._setup_logging()
                self.logger.warning(f"Failed to initialize billable client, using regular client: {e}")
        else:
            self.client = OpenAI(api_key=self.api_key)
            self.billable_client = False
        
        # Initialize prompt manager
        try:
            self.prompt_manager = PromptManager(prompts_dir)
        except FileNotFoundError:
            self.prompt_manager = None
            print(f"Warning: Prompts directory not found at {prompts_dir}. Using fallback prompts.")
        
        # Setup structured logging
        self._setup_logging()
        
        # Cost tracking (GPT-4o pricing as of 2024)
        self.cost_per_1k_input_tokens = 0.005  # $0.005 per 1K input tokens
        self.cost_per_1k_output_tokens = 0.015  # $0.015 per 1K output tokens
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 1.0  # Minimum 1 second between requests
        
    def _setup_logging(self):
        """Setup structured logging."""
        # Create logs directory
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        
        # Setup logger
        self.logger = logging.getLogger("llm_orchestrator")
        self.logger.setLevel(logging.INFO)
        
        # Remove existing handlers
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        # File handler
        log_file = logs_dir / f"orchestrator_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
    def _wait_for_rate_limit(self):
        """Ensure minimum time between requests."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            self.logger.info(f"Rate limiting: waiting {sleep_time:.2f}s")
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _calculate_retry_delay(self, attempt: int) -> float:
        """Calculate delay for retry attempt with exponential backoff."""
        base_delay = self.retry_config.base_delay
        exponential_delay = base_delay * (self.retry_config.exponential_base ** attempt)
        
        # Add jitter to prevent thundering herd
        if self.retry_config.jitter:
            jitter = random.uniform(0.1, 0.3) * exponential_delay
            exponential_delay += jitter
        
        return min(exponential_delay, self.retry_config.max_delay)
    
    def _is_retryable_error(self, error: Exception) -> bool:
        """Determine if an error is retryable."""
        if isinstance(error, openai.RateLimitError):
            return True
        if isinstance(error, openai.APIConnectionError):
            return True
        if isinstance(error, openai.InternalServerError):
            return True
        if isinstance(error, openai.APITimeoutError):
            return True
        
        # For general API errors, check status code
        if hasattr(error, 'status_code'):
            # Retry on 5xx errors and 429 (rate limit)
            if error.status_code >= 500 or error.status_code == 429:
                return True
        
        return False
    
    async def _make_api_call(self, messages: List[Dict[str, str]], **kwargs) -> dict:
        """Make API call with retry logic. Returns (response, credits_charged)."""
        last_error = None
        
        for attempt in range(self.retry_config.max_retries + 1):
            try:
                # Rate limiting
                self._wait_for_rate_limit()
                
                self.logger.info(f"Making API call (attempt {attempt + 1}/{self.retry_config.max_retries + 1})")
                
                if self.billable_client:
                    # Use billable client - this automatically handles credit billing
                    billable_response = await self.client.chat_completions_create(
                        model=self.model,
                        messages=messages,
                        timeout=120,  # 2 minute timeout for chapter generation
                        **kwargs
                    )
                    response = billable_response.response
                    credits_charged = billable_response.credits_charged
                    
                    # Add credits info to metadata for compatibility
                    if hasattr(response, '_credits_charged'):
                        response._credits_charged = credits_charged
                    else:
                        # If we can't attach to response, we'll handle it in calling methods
                        pass
                        
                else:
                    # Use regular client - no billing
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        timeout=120,  # 2 minute timeout for chapter generation
                        **kwargs
                    )
                    if hasattr(response, '_credits_charged'):
                        response._credits_charged = 0
                
                self.logger.info(f"API call successful on attempt {attempt + 1}")
                return response
                
            except Exception as e:
                last_error = e
                self.logger.warning(f"API call failed on attempt {attempt + 1}: {str(e)}")
                
                # Don't retry on final attempt
                if attempt == self.retry_config.max_retries:
                    break
                
                # Check if error is retryable
                if not self._is_retryable_error(e):
                    self.logger.error(f"Non-retryable error: {str(e)}")
                    break
                
                # Calculate and apply retry delay
                delay = self._calculate_retry_delay(attempt)
                self.logger.info(f"Retrying in {delay:.2f}s...")
                time.sleep(delay)
        
        # All retries exhausted
        raise last_error
    
    async def generate_chapter_spike(self, chapter_number: int, target_words: int = 3800) -> GenerationResult:
        """
        Phase 0 spike: Generate a chapter using hard-coded prompt.
        Maintained for backward compatibility.
        """
        return await self.generate_chapter(chapter_number, target_words, stage="spike")
    
    async def generate_chapter_5_stage(self, chapter_number: int, target_words: int = 3800,
                                 context: Dict[str, Any] = None) -> List[GenerationResult]:
        """
        Generate a chapter using the complete 5-stage process.
        Returns results from all stages.
        """
        if not self.prompt_manager:
            raise ValueError("5-stage generation requires prompt templates. Prompt manager not initialized.")
        
        context = context or {}
        results = []
        
        # Default context values - include all required and optional variables
        default_context = {
            "chapter_number": chapter_number,
            "target_words": target_words,
            "genre": "thriller",
            "story_context": "A detective investigates mysterious crimes in a modern urban setting.",
            "required_plot_points": "Advance investigation, reveal new clue",
            "focus_characters": "Detective protagonist",
            "chapter_climax_goal": "Significant revelation or plot advancement",
            # Optional variables with defaults
            "previous_chapter_summary": "Previous events leading to this chapter",
            "character_requirements": "Detective must show professional competence and personal stakes",
            "plot_requirements": "Advance main investigation plot",
            "theme_repetition_limits": "Stay within established theme limits",
            "character_voices": "Detective: Professional, determined. Supporting: Distinct personalities",
            "previous_events": "Ongoing investigation with developing leads",
            "scene_requirements": "Crime scene or investigation setting",
            "dialogue_requirements": "Professional law enforcement dialogue with subtext",
            "description_requirements": "Urban setting with attention to investigative details",
            "pacing_strategy": "Build tension through reveals and character interaction"
        }
        
        # Merge with provided context
        full_context = {**default_context, **context}
        
        self.logger.info(f"Starting 5-stage generation for Chapter {chapter_number}")
        
        # Stage 1: Strategic Planning
        self.logger.info("Stage 1: Strategic Planning")
        stage1_result = await self._execute_stage(1, full_context)
        results.append(stage1_result)
        
        if not stage1_result.success:
            self.logger.error("Stage 1 failed, aborting 5-stage process")
            return results
        
        # Update context with blueprint
        full_context["chapter_blueprint"] = stage1_result.content
        full_context["opening_hook_requirement"] = "Compelling opening that draws reader in"
        full_context["climax_requirement"] = "Meaningful revelation or emotional peak"
        full_context["ending_requirement"] = "Hook for next chapter"
        
        # Stage 2: First Draft Generation
        self.logger.info("Stage 2: First Draft Generation")
        stage2_result = await self._execute_stage(2, full_context)
        results.append(stage2_result)
        
        if not stage2_result.success:
            self.logger.error("Stage 2 failed, aborting 5-stage process")
            return results
        
        # Stage 3: Craft Excellence Review
        self.logger.info("Stage 3: Craft Excellence Review")
        full_context["chapter_content"] = stage2_result.content
        # Add Stage 3 specific optional variables
        full_context.update({
            "pattern_database_context": "No previous patterns for MVP testing",
            "previous_chapters_context": "First chapter in the story",
            "character_goals": "Solve the central mystery",
            "theme_limits": "Justice, truth, determination - stay within limits",
            "inspiration_reference": "Modern detective thriller style"
        })
        stage3_result = await self._execute_stage(3, full_context)
        results.append(stage3_result)
        
        if not stage3_result.success:
            self.logger.error("Stage 3 failed, aborting 5-stage process")
            return results
        
        # Stage 4: Targeted Refinement (if needed)
        # For now, skip to Stage 5 - refinement logic would analyze stage 3 results
        self.logger.info("Stage 4: Skipped for MVP (would analyze stage 3 results)")
        
        # Stage 5: Final Integration
        self.logger.info("Stage 5: Final Integration")
        full_context["refined_chapter"] = stage2_result.content  # Would be stage 4 output normally
        # Add Stage 5 specific optional variables  
        full_context.update({
            "story_arc_context": "Part of ongoing detective series",
            "pattern_database": "Empty for MVP",
            "previous_chapters_summary": "Story beginning with initial investigation",
            "next_chapter_preview": "Investigation continues with new leads",
            "character_timeline": "Detective's ongoing case progression",
            "world_rules": "Modern urban police procedural setting",
            "theme_development": "Justice and truth themes building",
            "series_context": "Standalone chapter with series potential"
        })
        stage5_result = await self._execute_stage(5, full_context)
        results.append(stage5_result)
        
        self.logger.info("5-stage generation completed")
        return results
    
    async def _execute_stage(self, stage_number: int, context: Dict[str, Any]) -> GenerationResult:
        """Execute a specific stage with given context."""
        try:
            # Get template and render prompts
            system_prompt, user_prompt = self.prompt_manager.render_prompts(stage_number, context)
            stage_config = self.prompt_manager.get_stage_config(stage_number)
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            # Make API call with stage-specific configuration
            response = await self._make_api_call(
                messages=messages,
                temperature=stage_config.get('temperature', 0.7),
                max_tokens=stage_config.get('max_tokens', 4000),
                top_p=1,
                frequency_penalty=0.1,
                presence_penalty=0.1
            )
            
            # Extract content and calculate costs
            content = response.choices[0].message.content
            usage = response.usage
            
            input_cost = (usage.prompt_tokens / 1000) * self.cost_per_1k_input_tokens
            output_cost = (usage.completion_tokens / 1000) * self.cost_per_1k_output_tokens
            total_cost = input_cost + output_cost
            
            metadata = {
                "stage": stage_number,
                "model": self.model,
                "timestamp": datetime.now().isoformat(),
                "tokens_used": {
                    "prompt": usage.prompt_tokens,
                    "completion": usage.completion_tokens,
                    "total": usage.total_tokens
                },
                "cost_breakdown": {
                    "input_cost": input_cost,
                    "output_cost": output_cost,
                    "total_cost": total_cost
                },
                "stage_config": stage_config
            }
            
            return GenerationResult(
                success=True,
                content=content,
                metadata=metadata,
                tokens_used=usage.total_tokens,
                cost_estimate=total_cost
            )
            
        except Exception as e:
            self.logger.error(f"Stage {stage_number} execution failed: {str(e)}")
            return GenerationResult(
                success=False,
                content="",
                metadata={
                    "stage": stage_number,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                },
                error=str(e)
            )

    async def generate_chapter(self, chapter_number: int, target_words: int = 3800, 
                        stage: str = "complete") -> GenerationResult:
        """
        Generate a chapter with robust error handling and retry logic.
        """
        start_time = time.time()
        
        self.logger.info(f"Starting chapter {chapter_number} generation (stage: {stage})")
        self.logger.info(f"Target words: {target_words}, Model: {self.model}")
        
        # Build prompts based on stage
        if stage == "spike":
            system_prompt, user_prompt = self._build_spike_prompts(chapter_number, target_words)
        else:
            system_prompt, user_prompt = self._build_comprehensive_prompts(chapter_number, target_words)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            # Make API call with retry logic
            response = await self._make_api_call(
                messages=messages,
                temperature=0.7,
                max_tokens=6000,
                top_p=1,
                frequency_penalty=0.1,
                presence_penalty=0.1
            )
            
            generation_time = time.time() - start_time
            
            # Extract content and metadata
            content = response.choices[0].message.content
            usage = response.usage
            
            # Calculate costs
            input_cost = (usage.prompt_tokens / 1000) * self.cost_per_1k_input_tokens
            output_cost = (usage.completion_tokens / 1000) * self.cost_per_1k_output_tokens
            total_cost = input_cost + output_cost
            
            # Prepare metadata
            metadata = {
                "model": self.model,
                "chapter_number": chapter_number,
                "generation_time": generation_time,
                "timestamp": datetime.now().isoformat(),
                "stage": stage,
                "tokens_used": {
                    "prompt": usage.prompt_tokens,
                    "completion": usage.completion_tokens,
                    "total": usage.total_tokens
                },
                "cost_breakdown": {
                    "input_cost": input_cost,
                    "output_cost": output_cost,
                    "total_cost": total_cost
                },
                "word_count": len(content.split()),
                "target_words": target_words,
                "retry_attempts": 0  # Will be updated if retries occurred
            }
            
            self.logger.info(f"Generation completed in {generation_time:.2f}s")
            self.logger.info(f"Tokens used: {usage.total_tokens}, Cost: ${total_cost:.4f}")
            self.logger.info(f"Word count: {metadata['word_count']} (target: {target_words})")
            
            return GenerationResult(
                success=True,
                content=content,
                metadata=metadata,
                tokens_used=usage.total_tokens,
                cost_estimate=total_cost
            )
            
        except Exception as e:
            generation_time = time.time() - start_time
            error_msg = str(e)
            
            self.logger.error(f"Generation failed after {generation_time:.2f}s: {error_msg}")
            
            return GenerationResult(
                success=False,
                content="",
                metadata={
                    "chapter_number": chapter_number,
                    "error": error_msg,
                    "timestamp": datetime.now().isoformat(),
                    "stage": stage,
                    "generation_time": generation_time,
                    "model": self.model
                },
                error=error_msg
            )
    
    def _build_spike_prompts(self, chapter_number: int, target_words: int) -> tuple[str, str]:
        """Build simple prompts for spike testing."""
        system_prompt = """You are an expert novelist writing a high-quality thriller chapter. 
        Focus on:
        - Compelling character development
        - Strong dialogue with subtext
        - Multiple layers of tension
        - Professional prose quality
        - Meaningful plot advancement
        
        Write exactly {target_words} words (+/- 100 words acceptable).
        Create engaging, publication-quality content."""
        
        user_prompt = f"""Write Chapter {chapter_number} of a thriller novel.
        
        Requirements:
        - Target length: {target_words} words
        - Include meaningful plot advancement
        - Develop characters through action and dialogue
        - Build tension throughout
        - End with compelling hook for next chapter
        
        Begin writing the chapter now."""
        
        return system_prompt.format(target_words=target_words), user_prompt
    
    def _build_comprehensive_prompts(self, chapter_number: int, target_words: int) -> tuple[str, str]:
        """Build comprehensive prompts for full chapter generation."""
        # This will be expanded in Phase 2 with context retrieval
        system_prompt = """You are an expert novelist following a comprehensive writing system.

        WRITING SYSTEM REQUIREMENTS:
        - Target length: {target_words} words (+/- 200 words acceptable)
        - Minimum 2 significant plot advancement points
        - Character development through action and dialogue
        - Multiple tension layers throughout
        - Professional prose quality (publication standard)
        - Strong opening hook and compelling ending
        - Authentic dialogue with subtext
        - Varied sentence structure and pacing
        
        QUALITY STANDARDS:
        - 8+ on all craft elements (character, plot, prose, structure)
        - Reader engagement throughout
        - Genre expectations met (thriller/mystery)
        - Professional polish and consistency
        
        Write publication-ready content that meets these standards."""
        
        user_prompt = f"""Write Chapter {chapter_number} of a thriller novel.
        
        CHAPTER REQUIREMENTS:
        - Target: {target_words} words
        - Advance plot meaningfully (minimum 2 significant points)
        - Develop characters through authentic action and dialogue
        - Create multiple layers of tension
        - End with compelling forward momentum
        
        Focus on professional quality prose that engages readers throughout.
        Begin writing the chapter now."""
        
        return system_prompt.format(target_words=target_words), user_prompt
    
    def save_chapter(self, result: GenerationResult, output_file: str) -> bool:
        """Save generated chapter to file with metadata."""
        try:
            # Ensure chapters directory exists
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save the chapter content
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(result.content)
            
            # Save metadata to companion file
            metadata_file = output_path.with_suffix('.json')
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(result.metadata, f, indent=2)
            
            self.logger.info(f"Chapter saved to {output_file}")
            self.logger.info(f"Metadata saved to {metadata_file}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save chapter: {str(e)}")
            return False
    
    def get_cost_estimate(self, prompt_text: str, target_completion_words: int) -> dict:
        """Estimate cost for a generation request."""
        # Rough token estimation
        prompt_tokens = len(prompt_text.split()) * 1.3
        completion_tokens = target_completion_words * 1.3
        
        input_cost = (prompt_tokens / 1000) * self.cost_per_1k_input_tokens
        output_cost = (completion_tokens / 1000) * self.cost_per_1k_output_tokens
        
        return {
            "estimated_prompt_tokens": int(prompt_tokens),
            "estimated_completion_tokens": int(completion_tokens),
            "estimated_total_tokens": int(prompt_tokens + completion_tokens),
            "estimated_input_cost": input_cost,
            "estimated_output_cost": output_cost,
            "estimated_total_cost": input_cost + output_cost
        }

async def main():
    """Main function for command-line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description="LLM Orchestrator - Phase 1 MVP")
    parser.add_argument("--chapter", type=int, required=True, help="Chapter number to generate")
    parser.add_argument("--model", default="gpt-4o", help="OpenAI model to use")
    parser.add_argument("--words", type=int, default=3800, help="Target word count")
    parser.add_argument("--output", help="Output file path (default: chapters/chapter-{N}.md)")
    parser.add_argument("--stage", default="complete", choices=["spike", "complete", "5-stage"], 
                       help="Generation stage")
    parser.add_argument("--max-retries", type=int, default=3, help="Maximum retry attempts")
    parser.add_argument("--estimate-only", action="store_true", help="Only estimate cost, don't generate")
    
    args = parser.parse_args()
    
    # Set default output path
    if not args.output:
        args.output = f"chapters/chapter-{args.chapter:02d}.md"
    
    # Initialize orchestrator
    try:
        retry_config = RetryConfig(max_retries=args.max_retries)
        orchestrator = LLMOrchestrator(model=args.model, retry_config=retry_config)
    except ValueError as e:
        print(f"ERROR: {e}")
        return 1
    
    # Cost estimation mode
    if args.estimate_only:
        system_prompt, user_prompt = orchestrator._build_comprehensive_prompts(args.chapter, args.words)
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        estimate = orchestrator.get_cost_estimate(full_prompt, args.words)
        
        print(f"💰 Cost Estimation for Chapter {args.chapter}")
        print(f"📊 Estimated tokens: {estimate['estimated_total_tokens']}")
        print(f"💵 Estimated cost: ${estimate['estimated_total_cost']:.4f}")
        print(f"   Input: ${estimate['estimated_input_cost']:.4f}")
        print(f"   Output: ${estimate['estimated_output_cost']:.4f}")
        return 0
    
    # Generate chapter
    print(f"Generating Chapter {args.chapter} using {args.model} (stage: {args.stage})...")
    
    if args.stage == "5-stage":
        # 5-stage generation
        results = await orchestrator.generate_chapter_5_stage(args.chapter, args.words)
        
        if not results:
            print("❌ 5-stage generation failed: No results returned")
            return 1
        
        # Check if all stages completed successfully
        successful_stages = [r for r in results if r.success]
        failed_stages = [r for r in results if not r.success]
        
        print(f"📊 5-Stage Generation Summary:")
        print(f"   ✅ Successful stages: {len(successful_stages)}")
        print(f"   ❌ Failed stages: {len(failed_stages)}")
        
        total_cost = sum(r.cost_estimate for r in successful_stages)
        print(f"   💰 Total cost: ${total_cost:.4f}")
        
        # Save final result if available
        final_result = results[-1] if results else None
        if final_result and final_result.success:
            if orchestrator.save_chapter(final_result, args.output):
                print(f"✅ Final chapter saved to: {args.output}")
                
                # Save all stage results
                stages_dir = Path(args.output).parent / "stages"
                stages_dir.mkdir(exist_ok=True)
                
                for i, result in enumerate(results, 1):
                    if result.success:
                        stage_file = stages_dir / f"chapter-{args.chapter:02d}-stage-{i}.md"
                        with open(stage_file, 'w', encoding='utf-8') as f:
                            f.write(result.content)
                        print(f"   📁 Stage {i} saved to: {stage_file}")
                
                return 0
            else:
                print("❌ Failed to save final chapter")
                return 1
        else:
            print("❌ 5-stage generation failed: Final stage unsuccessful")
            return 1
    
    else:
        # Single-stage generation
        result = await orchestrator.generate_chapter(args.chapter, args.words, args.stage)
        
        if result.success:
            # Save chapter
            if orchestrator.save_chapter(result, args.output):
                print(f"✅ Chapter {args.chapter} generated successfully!")
                print(f"📁 Saved to: {args.output}")
                print(f"📊 Word count: {result.metadata['word_count']}")
                print(f"💰 Cost: ${result.cost_estimate:.4f}")
                print(f"⏱️  Time: {result.metadata['generation_time']:.2f}s")
                print(f"\n🔍 Next step: Run quality gates with:")
                print(f"   python3 system/brutal_assessment_scorer.py assess --chapter-file {args.output}")
                return 0
            else:
                print("❌ Failed to save chapter")
                return 1
        else:
            print(f"❌ Generation failed: {result.error}")
            return 1

if __name__ == "__main__":
    import asyncio
    exit(asyncio.run(main())) 