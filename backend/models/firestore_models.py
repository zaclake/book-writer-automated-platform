#!/usr/bin/env python3
"""
Pydantic Models for Firestore Schema
Provides validation and serialization for the commercial architecture.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field, validator
from enum import Enum

# =====================================================================
# ENUMS
# =====================================================================

class SubscriptionTier(str, Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"

class ProjectStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"
    PAUSED = "paused"

class ProjectVisibility(str, Enum):
    PRIVATE = "private"
    SHARED = "shared"
    PUBLIC = "public"

class ChapterStage(str, Enum):
    DRAFT = "draft"
    REVISION = "revision"
    COMPLETE = "complete"

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"

class JobType(str, Enum):
    SINGLE_CHAPTER = "single_chapter"
    AUTO_COMPLETE_BOOK = "auto_complete_book"
    REFERENCE_GENERATION = "reference_generation"

class BookLengthTier(str, Enum):
    NOVELLA = "novella"           # 17,500-40,000 words, 8-15 chapters
    SHORT_NOVEL = "short_novel"   # 40,000-60,000 words, 15-20 chapters
    STANDARD_NOVEL = "standard_novel"  # 60,000-90,000 words, 20-30 chapters
    LONG_NOVEL = "long_novel"     # 90,000-120,000 words, 25-35 chapters
    EPIC_NOVEL = "epic_novel"     # 120,000+ words, 30-50+ chapters

# =====================================================================
# USER MODELS
# =====================================================================

class UserProfile(BaseModel):
    clerk_id: str
    email: str
    name: str
    subscription_tier: SubscriptionTier = SubscriptionTier.FREE
    avatar_url: Optional[str] = None
    created_at: Optional[datetime] = None
    last_active: Optional[datetime] = None
    timezone: str = "UTC"

class UserUsage(BaseModel):
    monthly_cost: float = 0.0
    chapters_generated: int = 0
    api_calls: int = 0
    words_generated: int = 0
    projects_created: int = 0
    last_reset_date: Optional[datetime] = None

class UserPreferences(BaseModel):
    default_genre: str = "Fiction"
    default_word_count: int = 2000
    quality_strictness: str = "standard"
    auto_backup_enabled: bool = True
    collaboration_notifications: bool = True
    email_notifications: bool = True
    preferred_llm_model: str = "gpt-4o"

class UserLimits(BaseModel):
    monthly_cost_limit: float = 50.0
    monthly_chapter_limit: int = 100
    concurrent_projects_limit: int = 5
    storage_limit_mb: int = 1000

class User(BaseModel):
    profile: UserProfile
    usage: UserUsage
    preferences: UserPreferences
    limits: UserLimits

# =====================================================================
# PROJECT MODELS
# =====================================================================

class ProjectMetadata(BaseModel):
    project_id: Optional[str] = None
    title: str
    owner_id: str
    collaborators: List[str] = []
    status: ProjectStatus = ProjectStatus.ACTIVE
    visibility: ProjectVisibility = ProjectVisibility.PRIVATE
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class BookBible(BaseModel):
    content: str
    must_include_sections: List[str] = []  # Critical elements that must be included
    book_length_tier: Optional[BookLengthTier] = None  # Target book length category
    estimated_chapters: Optional[int] = None  # Auto-calculated or user-specified
    target_word_count: Optional[int] = None  # Auto-calculated based on tier
    last_modified: Optional[datetime] = None
    modified_by: Optional[str] = None
    version: int = 1
    word_count: int = 0

    @classmethod
    def get_book_length_specs(cls, tier: BookLengthTier) -> Dict[str, Any]:
        """Get word count ranges and chapter estimates for a book length tier."""
        specs = {
            BookLengthTier.NOVELLA: {
                "word_count_min": 17500,
                "word_count_max": 40000,
                "word_count_target": 28750,
                "chapter_count_min": 8,
                "chapter_count_max": 15,
                "chapter_count_target": 12,
                "avg_words_per_chapter": 2400
            },
            BookLengthTier.SHORT_NOVEL: {
                "word_count_min": 40000,
                "word_count_max": 60000,
                "word_count_target": 50000,
                "chapter_count_min": 15,
                "chapter_count_max": 20,
                "chapter_count_target": 18,
                "avg_words_per_chapter": 2800
            },
            BookLengthTier.STANDARD_NOVEL: {
                "word_count_min": 60000,
                "word_count_max": 90000,
                "word_count_target": 75000,
                "chapter_count_min": 20,
                "chapter_count_max": 30,
                "chapter_count_target": 25,
                "avg_words_per_chapter": 3000
            },
            BookLengthTier.LONG_NOVEL: {
                "word_count_min": 90000,
                "word_count_max": 120000,
                "word_count_target": 105000,
                "chapter_count_min": 25,
                "chapter_count_max": 35,
                "chapter_count_target": 30,
                "avg_words_per_chapter": 3500
            },
            BookLengthTier.EPIC_NOVEL: {
                "word_count_min": 120000,
                "word_count_max": 200000,
                "word_count_target": 160000,
                "chapter_count_min": 30,
                "chapter_count_max": 50,
                "chapter_count_target": 40,
                "avg_words_per_chapter": 4000
            }
        }
        return specs.get(tier, specs[BookLengthTier.STANDARD_NOVEL])

    def auto_calculate_specifications(self) -> None:
        """Auto-calculate estimated_chapters and target_word_count based on book_length_tier."""
        if self.book_length_tier:
            specs = self.get_book_length_specs(self.book_length_tier)
            if not self.estimated_chapters:
                self.estimated_chapters = specs["chapter_count_target"]
            if not self.target_word_count:
                self.target_word_count = specs["word_count_target"]

class ReferenceFile(BaseModel):
    content: str
    last_modified: Optional[datetime] = None
    modified_by: Optional[str] = None

class ProjectReferences(BaseModel):
    characters: Optional[ReferenceFile] = None
    outline: Optional[ReferenceFile] = None
    plot_timeline: Optional[ReferenceFile] = None
    style_guide: Optional[ReferenceFile] = None
    world_building: Optional[ReferenceFile] = None
    research_notes: Optional[ReferenceFile] = None
    themes_and_motifs: Optional[ReferenceFile] = None
    target_audience_profile: Optional[ReferenceFile] = None
    series_bible: Optional[ReferenceFile] = None  # Optional for standalone books

class DirectorNote(BaseModel):
    note_id: Optional[str] = None
    chapter_id: str
    content: str
    created_by: str
    created_at: Optional[datetime] = None
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    position: Optional[int] = None  # Character position in chapter if specific

class ProjectSettings(BaseModel):
    genre: str = "Fiction"
    target_chapters: int = 25
    word_count_per_chapter: int = 2000
    target_audience: str = "General"
    writing_style: str = "Professional"
    quality_gates_enabled: bool = True
    auto_completion_enabled: bool = False
    involvement_level: str = "balanced"  # "hands_off", "balanced", "hands_on"
    purpose: str = "personal"  # "personal", "commercial", "educational"

class QualityBaseline(BaseModel):
    prose: float = 0.0
    character: float = 0.0
    story: float = 0.0
    emotion: float = 0.0
    freshness: float = 0.0
    engagement: float = 0.0

class ProjectProgress(BaseModel):
    chapters_completed: int = 0
    current_word_count: int = 0
    target_word_count: int = 0
    completion_percentage: float = 0.0
    estimated_completion_date: Optional[datetime] = None
    last_chapter_generated: int = 0
    quality_baseline: QualityBaseline = QualityBaseline()

class TimelineEvent(BaseModel):
    chapter: int
    event: str
    impact: str

class StoryContinuity(BaseModel):
    main_characters: List[str] = []
    active_plot_threads: List[str] = []
    world_building_elements: Dict[str, Any] = {}
    theme_tracking: Dict[str, Any] = {}
    timeline_events: List[TimelineEvent] = []
    character_relationships: Dict[str, Any] = {}
    settings_visited: List[str] = []
    story_arc_progress: float = 0.0
    tone_consistency: Dict[str, Any] = {}

class Project(BaseModel):
    metadata: ProjectMetadata
    book_bible: Optional[BookBible] = None
    references: ProjectReferences = ProjectReferences()
    settings: ProjectSettings = ProjectSettings()
    progress: ProjectProgress = ProjectProgress()
    story_continuity: StoryContinuity = StoryContinuity()

# =====================================================================
# CHAPTER MODELS
# =====================================================================

class TokenUsage(BaseModel):
    prompt: int = 0
    completion: int = 0
    total: int = 0

class CostBreakdown(BaseModel):
    input_cost: float = 0.0
    output_cost: float = 0.0
    total_cost: float = 0.0

class ChapterMetadata(BaseModel):
    word_count: int
    target_word_count: int = 2000
    created_by: str
    stage: ChapterStage = ChapterStage.DRAFT
    generation_time: float = 0.0
    retry_attempts: int = 0
    model_used: str = "gpt-4o"
    tokens_used: TokenUsage = TokenUsage()
    cost_breakdown: CostBreakdown = CostBreakdown()
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class BrutalAssessment(BaseModel):
    score: float
    feedback: str
    assessed_at: Optional[datetime] = None

class CraftScores(BaseModel):
    prose: float = 0.0
    character: float = 0.0
    story: float = 0.0
    emotion: float = 0.0
    freshness: float = 0.0

class QualityScores(BaseModel):
    brutal_assessment: Optional[BrutalAssessment] = None
    engagement_score: float = 0.0
    overall_rating: float = 0.0
    craft_scores: CraftScores = CraftScores()
    pattern_violations: List[str] = []
    improvement_suggestions: List[str] = []

class ChapterVersion(BaseModel):
    version_number: int
    content: str
    timestamp: Optional[datetime] = None
    reason: str  # "initial_generation", "quality_revision", "user_edit"
    user_id: str
    changes_summary: str = ""

class ContextData(BaseModel):
    character_states: Dict[str, Any] = {}
    plot_threads: List[str] = []
    world_state: Dict[str, Any] = {}
    timeline_position: Optional[Any] = None
    previous_chapter_summary: str = ""

class Chapter(BaseModel):
    project_id: str
    chapter_number: int
    chapter_id: Optional[str] = None
    content: str
    title: Optional[str] = None
    metadata: ChapterMetadata
    quality_scores: QualityScores = QualityScores()
    versions: List[ChapterVersion] = []
    context_data: ContextData = ContextData()
    director_notes: List[DirectorNote] = []

# =====================================================================
# GENERATION JOB MODELS
# =====================================================================

class JobProgress(BaseModel):
    current_step: str = "Initializing"
    total_steps: int = 1
    completed_steps: int = 0
    percentage: float = 0.0
    estimated_time_remaining: Optional[float] = None

class JobConfig(BaseModel):
    chapters_to_generate: Optional[List[int]] = None
    target_word_count: Optional[int] = None
    quality_gates_enabled: bool = True
    max_retry_attempts: int = 3
    auto_retry_on_failure: bool = True

class CompletionTriggers(BaseModel):
    word_count_target_reached: bool = False
    plot_resolution_achieved: bool = False
    character_arcs_completed: bool = False
    manual_completion_requested: bool = False

class AutoCompleteData(BaseModel):
    current_chapter: int = 0
    total_chapters_planned: int = 0
    chapters_completed: int = 0
    failed_chapters: List[int] = []
    skipped_chapters: List[int] = []
    completion_triggers: CompletionTriggers = CompletionTriggers()

class JobResults(BaseModel):
    chapters_generated: List[str] = []  # Chapter IDs
    total_cost: float = 0.0
    total_tokens: int = 0
    average_quality_score: float = 0.0
    generation_time: float = 0.0

class GenerationJob(BaseModel):
    job_id: Optional[str] = None
    job_type: JobType
    project_id: str
    user_id: str
    status: JobStatus = JobStatus.PENDING
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    progress: JobProgress = JobProgress()
    config: JobConfig = JobConfig()
    auto_complete_data: Optional[AutoCompleteData] = None
    results: JobResults = JobResults()

# =====================================================================
# REQUEST/RESPONSE MODELS
# =====================================================================

class CreateProjectRequest(BaseModel):
    title: str
    genre: str = "Fiction"
    target_chapters: int = 25
    word_count_per_chapter: int = 2000
    book_bible_content: Optional[str] = None
    include_series_bible: bool = False
    must_include_sections: List[str] = []
    creation_mode: str = "quickstart"
    book_length_tier: Optional[str] = None
    estimated_chapters: Optional[int] = None
    target_word_count: Optional[int] = None
    source_data: Optional[dict] = None

class UpdateProjectRequest(BaseModel):
    title: Optional[str] = None
    status: Optional[ProjectStatus] = None
    settings: Optional[ProjectSettings] = None
    book_bible_content: Optional[str] = None

class CreateChapterRequest(BaseModel):
    project_id: str
    chapter_number: int
    content: str
    title: Optional[str] = None
    target_word_count: int = 2000

class ProjectListResponse(BaseModel):
    projects: List[Project]
    total: int

class ChapterListResponse(BaseModel):
    chapters: List[Chapter]
    total: int

# =====================================================================
# VALIDATION
# =====================================================================

class ProjectMetadata(ProjectMetadata):
    @validator('title')
    def title_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Title cannot be empty')
        return v.strip()

class ChapterMetadata(ChapterMetadata):
    @validator('word_count')
    def word_count_must_be_positive(cls, v):
        if v < 0:
            raise ValueError('Word count must be non-negative')
        return v 