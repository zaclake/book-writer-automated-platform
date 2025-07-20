# Firestore Schema Design
**Book Writing Automation System - Commercial Architecture**

## 🎯 **Schema Overview**

This schema transforms the current file-based system into a scalable, multi-tenant Firestore architecture supporting hundreds of users with real-time collaboration and cross-device synchronization.

### **Core Collections Structure**

```
/users/{clerk_user_id}
/projects/{project_id}
/chapters/{chapter_id}
/generation_jobs/{job_id}
/subscriptions/{clerk_user_id}
/usage_tracking/{month_year_user_id}
```

---

## 📋 **Detailed Collection Schemas**

### **1. Users Collection** 
`/users/{clerk_user_id}`

```typescript
interface User {
  // Profile Information
  profile: {
    clerk_id: string;           // Primary key from Clerk
    email: string;
    name: string;
    avatar_url?: string;
    subscription_tier: 'free' | 'pro' | 'enterprise';
    created_at: Timestamp;
    last_active: Timestamp;
    timezone: string;
  };

  // Usage & Quota Tracking
  usage: {
    monthly_cost: number;           // Current month's OpenAI costs
    chapters_generated: number;     // Total chapters generated
    api_calls: number;             // Total API calls made
    words_generated: number;       // Total words generated
    projects_created: number;      // Total projects created
    last_reset_date: Timestamp;    // Monthly usage reset
  };

  // User Preferences
  preferences: {
    default_genre: string;
    default_word_count: number;
    quality_strictness: 'lenient' | 'standard' | 'strict';
    auto_backup_enabled: boolean;
    collaboration_notifications: boolean;
    email_notifications: boolean;
    preferred_llm_model: string;
  };

  // Quotas & Limits
  limits: {
    monthly_cost_limit: number;
    monthly_chapter_limit: number;
    concurrent_projects_limit: number;
    storage_limit_mb: number;
  };
}
```

### **2. Projects Collection**
`/projects/{project_id}`

```typescript
interface Project {
  // Core Metadata
  metadata: {
    project_id: string;
    title: string;
    created_at: Timestamp;
    updated_at: Timestamp;
    owner_id: string;              // Clerk user ID
    collaborators: string[];       // Array of Clerk user IDs
    status: 'active' | 'completed' | 'archived' | 'paused';
    visibility: 'private' | 'shared' | 'public';
  };

  // Book Content
  book_bible: {
    content: string;               // Full book bible text
    last_modified: Timestamp;
    modified_by: string;           // Clerk user ID
    version: number;
    word_count: number;
  };

  // Reference Files (migrated from current filesystem structure)
  references: {
    characters: {
      content: string;
      last_modified: Timestamp;
      modified_by: string;
    };
    outline: {
      content: string;
      last_modified: Timestamp;
      modified_by: string;
    };
    plot_timeline: {
      content: string;
      last_modified: Timestamp;
      modified_by: string;
    };
    style_guide: {
      content: string;
      last_modified: Timestamp;
      modified_by: string;
    };
    world_building: {
      content: string;
      last_modified: Timestamp;
      modified_by: string;
    };
    research_notes: {
      content: string;
      last_modified: Timestamp;
      modified_by: string;
    };
  };

  // Project Settings
  settings: {
    genre: string;
    target_chapters: number;
    word_count_per_chapter: number;
    target_audience: string;
    writing_style: string;
    quality_gates_enabled: boolean;
    auto_completion_enabled: boolean;
  };

  // Progress Tracking (migrated from .project-state)
  progress: {
    chapters_completed: number;
    current_word_count: number;
    target_word_count: number;
    completion_percentage: number;
    estimated_completion_date: Timestamp;
    last_chapter_generated: number;
    quality_baseline: {
      prose: number;
      character: number;
      story: number;
      emotion: number;
      freshness: number;
      engagement: number;
    };
  };

  // Story Continuity (migrated from chapter context manager)
  story_continuity: {
    main_characters: string[];
    active_plot_threads: string[];
    world_building_elements: Record<string, any>;
    theme_tracking: Record<string, any>;
    timeline_events: Array<{
      chapter: number;
      event: string;
      impact: string;
    }>;
    character_relationships: Record<string, any>;
    settings_visited: string[];
    story_arc_progress: number;
    tone_consistency: Record<string, any>;
  };
}
```

### **3. Chapters Collection**
`/chapters/{chapter_id}`

```typescript
interface Chapter {
  // Core Identifiers
  project_id: string;
  chapter_number: number;
  chapter_id: string;              // UUID

  // Content
  content: string;                 // Main chapter text
  title?: string;

  // Metadata (migrated from current JSON structure)
  metadata: {
    word_count: number;
    target_word_count: number;
    created_at: Timestamp;
    updated_at: Timestamp;
    created_by: string;            // Clerk user ID
    stage: 'draft' | 'revision' | 'complete';
    generation_time: number;       // Seconds
    retry_attempts: number;
    
    // AI Generation Details
    model_used: string;
    tokens_used: {
      prompt: number;
      completion: number;
      total: number;
    };
    cost_breakdown: {
      input_cost: number;
      output_cost: number;
      total_cost: number;
    };
  };

  // Quality Assessment
  quality_scores: {
    brutal_assessment: {
      score: number;
      feedback: string;
      assessed_at: Timestamp;
    };
    engagement_score: number;
    overall_rating: number;
    craft_scores: {
      prose: number;
      character: number;
      story: number;
      emotion: number;
      freshness: number;
    };
    pattern_violations: string[];
    improvement_suggestions: string[];
  };

  // Version History
  versions: Array<{
    version_number: number;
    content: string;
    timestamp: Timestamp;
    reason: string;               // "initial_generation", "quality_revision", "user_edit"
    user_id: string;
    changes_summary: string;
  }>;

  // Context Data (for chapter generation)
  context_data: {
    character_states: Record<string, any>;
    plot_threads: string[];
    world_state: Record<string, any>;
    timeline_position: any;
    previous_chapter_summary: string;
  };
}
```

### **4. Generation Jobs Collection**
`/generation_jobs/{job_id}`

```typescript
interface GenerationJob {
  // Job Identification
  job_id: string;                 // UUID
  job_type: 'single_chapter' | 'auto_complete_book' | 'reference_generation';
  project_id: string;
  user_id: string;               // Clerk user ID

  // Job Status
  status: 'pending' | 'running' | 'completed' | 'failed' | 'paused' | 'cancelled';
  created_at: Timestamp;
  started_at?: Timestamp;
  completed_at?: Timestamp;
  error_message?: string;

  // Progress Tracking
  progress: {
    current_step: string;
    total_steps: number;
    completed_steps: number;
    percentage: number;
    estimated_time_remaining?: number;
  };

  // Job Configuration
  config: {
    chapters_to_generate?: number[];
    target_word_count?: number;
    quality_gates_enabled: boolean;
    max_retry_attempts: number;
    auto_retry_on_failure: boolean;
  };

  // Auto-Complete Specific (migrated from book-completion-state.json)
  auto_complete_data?: {
    current_chapter: number;
    total_chapters_planned: number;
    chapters_completed: number;
    failed_chapters: number[];
    skipped_chapters: number[];
    completion_triggers: {
      word_count_target_reached: boolean;
      plot_resolution_achieved: boolean;
      character_arcs_completed: boolean;
      manual_completion_requested: boolean;
    };
  };

  // Results
  results: {
    chapters_generated: string[];   // Chapter IDs
    total_cost: number;
    total_tokens: number;
    average_quality_score: number;
    generation_time: number;
  };
}
```

### **5. Subscriptions Collection**
`/subscriptions/{clerk_user_id}`

```typescript
interface Subscription {
  user_id: string;               // Clerk user ID
  stripe_customer_id: string;
  subscription_id: string;
  tier: 'free' | 'pro' | 'enterprise';
  status: 'active' | 'canceled' | 'past_due' | 'unpaid';
  current_period_start: Timestamp;
  current_period_end: Timestamp;
  cancel_at_period_end: boolean;
  created_at: Timestamp;
  updated_at: Timestamp;

  // Billing History
  billing_history: Array<{
    amount: number;
    currency: string;
    invoice_id: string;
    paid_at: Timestamp;
    status: string;
  }>;

  // Usage Limits by Tier
  limits: {
    monthly_cost_limit: number;
    monthly_chapter_limit: number;
    concurrent_projects_limit: number;
    storage_limit_mb: number;
    collaboration_users_limit: number;
  };
}
```

### **6. Usage Tracking Collection**
`/usage_tracking/{month_year_user_id}` (e.g., "2024-01-user123")

```typescript
interface UsageTracking {
  user_id: string;
  month_year: string;            // "2024-01"
  
  // Daily Breakdown
  daily_usage: Record<string, {   // Key: "2024-01-15"
    api_calls: number;
    cost: number;
    chapters_generated: number;
    words_generated: number;
    tokens_used: number;
  }>;

  // Monthly Totals
  monthly_totals: {
    total_cost: number;
    total_api_calls: number;
    total_chapters: number;
    total_words: number;
    total_tokens: number;
  };

  // Quota Status
  quota_status: {
    cost_quota_used: number;
    cost_quota_remaining: number;
    chapter_quota_used: number;
    chapter_quota_remaining: number;
    quota_reset_date: Timestamp;
  };

  created_at: Timestamp;
  updated_at: Timestamp;
}
```

---

## 🔄 **Migration Considerations**

### **Current File System → Firestore Mapping**

| Current Location | Firestore Collection | Notes |
|------------------|---------------------|-------|
| `.project-meta.json` | `/projects/{id}` | Merge metadata + settings |
| `chapters/chapter-XX.md` | `/chapters/{id}` | Content field |
| `chapters/chapter-XX.json` | `/chapters/{id}` | Metadata field |
| `references/*.md` | `/projects/{id}/references` | Subcollection or embedded |
| `.project-state/` | `/projects/{id}/progress` | Embedded document |
| Auto-complete state | `/generation_jobs/{id}` | Job tracking |

### **Data Validation Rules**

```typescript
// Example validation for chapters
const chapterValidator = {
  project_id: 'required|string',
  chapter_number: 'required|integer|min:1',
  content: 'required|string|min:100',
  'metadata.word_count': 'required|integer|min:0',
  'quality_scores.overall_rating': 'numeric|min:0|max:10'
};
```

### **Indexing Strategy**

```typescript
// Required composite indexes
const indexes = [
  // User's projects
  { collection: 'projects', fields: ['metadata.owner_id', 'metadata.created_at'] },
  
  // Project chapters ordered
  { collection: 'chapters', fields: ['project_id', 'chapter_number'] },
  
  // User's jobs
  { collection: 'generation_jobs', fields: ['user_id', 'created_at'] },
  
  // Chapter versions
  { collection: 'chapters', fields: ['project_id', 'metadata.updated_at'] }
];
```

---

## 🚀 **Implementation Priority**

1. **Phase 1**: Users + Projects (basic CRUD)
2. **Phase 2**: Chapters with versioning
3. **Phase 3**: Generation jobs tracking
4. **Phase 4**: Usage tracking + billing
5. **Phase 5**: Real-time collaboration features

This schema provides a solid foundation for scaling to commercial SaaS with proper user isolation, billing integration, and collaborative features while maintaining all current functionality. 