// Project interface that extends the base Project with chapters data
export interface Project {
  id: string
  metadata: {
    project_id: string
    title: string
    owner_id: string
    collaborators: string[]
    status: 'active' | 'completed' | 'archived' | 'paused'
    visibility: 'private' | 'shared' | 'public'
    created_at: Date
    updated_at: Date
  }
  book_bible?: {
    content: string
    last_modified: Date
    modified_by: string
    version: number
    word_count: number
  }
  settings: {
    genre: string
    target_chapters: number
    word_count_per_chapter: number
    target_audience: string
    writing_style: string
    quality_gates_enabled: boolean
    auto_completion_enabled: boolean
  }
  progress: {
    chapters_completed: number
    current_word_count: number
    target_word_count: number
    completion_percentage: number
    last_chapter_generated: number
    quality_baseline: {
      prose: number
      character: number
      story: number
      emotion: number
      freshness: number
      engagement: number
    }
  }
  // Optional chapters array for compatibility
  chapters?: Array<{
    id: string
    chapter_number: number
    title?: string
    content?: string
    word_count?: number
  }>
}

// Auto-complete estimation interface (credit-based)
export interface AutoCompleteEstimate {
  total_chapters: number
  words_per_chapter: number
  total_words: number
  quality_threshold: number
  estimated_total_credits: number
  credits_per_chapter: number
  estimation_method?: string
  notes?: string[]
} 