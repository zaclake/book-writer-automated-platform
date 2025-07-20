/**
 * Shared types used across the application
 * Keep these synchronized with backend models
 */

export enum BookLengthTier {
  NOVELLA = 'novella',          // 17,500-40,000 words, 8-15 chapters
  SHORT_NOVEL = 'short_novel',  // 40,000-60,000 words, 15-20 chapters
  STANDARD_NOVEL = 'standard_novel', // 60,000-90,000 words, 20-30 chapters
  LONG_NOVEL = 'long_novel',    // 90,000-120,000 words, 25-35 chapters
  EPIC_NOVEL = 'epic_novel'     // 120,000+ words, 30-50+ chapters
}

export enum SubscriptionTier {
  FREE = 'free',
  PRO = 'pro', 
  ENTERPRISE = 'enterprise'
}

export enum ProjectStatus {
  ACTIVE = 'active',
  COMPLETED = 'completed',
  ARCHIVED = 'archived',
  PAUSED = 'paused'
}

export enum ProjectVisibility {
  PRIVATE = 'private',
  SHARED = 'shared',
  PUBLIC = 'public'
}

export enum ChapterStage {
  DRAFT = 'draft',
  REVISION = 'revision', 
  COMPLETE = 'complete'
}

export enum JobStatus {
  PENDING = 'pending',
  RUNNING = 'running',
  COMPLETED = 'completed',
  FAILED = 'failed',
  PAUSED = 'paused',
  CANCELLED = 'cancelled'
}

export enum JobType {
  SINGLE_CHAPTER = 'single_chapter',
  AUTO_COMPLETE_BOOK = 'auto_complete_book',
  REFERENCE_GENERATION = 'reference_generation'
}

export interface BookLengthSpecs {
  word_count_min: number
  word_count_max: number
  word_count_target: number
  chapter_count_min: number
  chapter_count_max: number
  chapter_count_target: number
  avg_words_per_chapter: number
}

export interface UserPreferences {
  writing_style: string
  default_word_count: number
  preferred_genres: string[]
  notification_settings: {
    email_notifications: boolean
    auto_save_alerts: boolean
    quality_warnings: boolean
  }
}

export interface UserProfile {
  clerk_id: string
  email: string
  name: string
  subscription_tier: SubscriptionTier
  avatar_url?: string
  created_at?: string
  last_active?: string
  timezone: string
}

export interface UserUsage {
  monthly_cost: number
  chapters_generated: number
  api_calls: number
  words_generated: number
  projects_created: number
  last_reset_date?: string
}

export interface QualityScores {
  overall_rating: number
  prose: number
  character: number
  story: number
  emotion: number
  freshness: number
}

export interface Chapter {
  id: string
  project_id: string
  chapter_number: number
  title?: string
  content: string
  stage: ChapterStage
  quality_scores?: QualityScores
  created_at: string
  updated_at: string
  word_count: number
  version: number
}

export interface ReferenceFile {
  id: string
  project_id: string
  name: string
  content: string
  file_type: string
  created_by: string
  created_at: string
  size: number
  version: number
}

export interface ProjectMetadata {
  title: string
  owner_id: string
  collaborators: string[]
  status: ProjectStatus
  visibility: ProjectVisibility
  created_at: string
  updated_at: string
}

export interface ProjectSettings {
  genre: string
  target_chapters: number
  word_count_per_chapter: number
  target_audience: string
  writing_style: string
}

export interface Project {
  id: string
  metadata: ProjectMetadata
  settings: ProjectSettings
  book_bible_content?: string
}

export type CreationMode = 'select' | 'quickstart' | 'guided' | 'paste'

export interface QuickStartData {
  title: string
  genre: string
  brief_premise: string
  main_character: string
  setting: string
  conflict: string
}

export interface GuidedWizardData {
  title: string
  genre: string
  premise: string
  main_characters: string
  setting_time: string
  setting_place: string
  central_conflict: string
  themes: string
  target_audience: string
  tone: string
  key_plot_points: string
}

export interface PasteData {
  title: string
  genre: string
  content: string
}

export interface BookBibleData {
  title: string
  genre: string
  target_chapters: number
  word_count_per_chapter: number
  content: string
  must_include_sections: string[]
  creation_mode: CreationMode
  source_data?: any
  book_length_tier?: BookLengthTier
  estimated_chapters?: number
  target_word_count?: number
  include_series_bible?: boolean
} 