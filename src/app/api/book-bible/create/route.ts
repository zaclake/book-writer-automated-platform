import { NextRequest, NextResponse } from 'next/server'
import { auth, currentUser } from '@clerk/nextjs/server'

interface BookBibleData {
  title: string
  genre: string
  target_chapters: number
  word_count_per_chapter: number
  content: string
  must_include_sections: string[]
  creation_mode: 'quickstart' | 'guided' | 'paste'
  source_data?: any // Original input data for regeneration
  book_length_tier?: string
  estimated_chapters?: number
  target_word_count?: number
  include_series_bible?: boolean
}

interface ProjectCreationData {
  title: string
  genre: string
  book_bible_content: string
  must_include_sections: string[]
  settings?: {
    target_chapters?: number
    word_count_per_chapter?: number
    involvement_level?: string
    purpose?: string
  }
}

// Helper function to call backend API
async function createProjectInBackend(projectData: any, authToken: string): Promise<string> {
  const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
  if (!backendBaseUrl) {
    throw new Error('Backend URL not configured')
  }

  const response = await fetch(`${backendBaseUrl}/v2/projects/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${authToken}`
    },
    body: JSON.stringify({
      title: projectData.title,
      genre: projectData.genre,
      target_chapters: projectData.settings.target_chapters,
      word_count_per_chapter: projectData.settings.word_count_per_chapter,
      book_bible_content: projectData.book_bible_content
    })
  })

  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(`Backend API error: ${response.status} - ${errorText}`)
  }

  const result = await response.json()
  return result.project_id || result.id
}

async function generateExpandedBookBible(data: any, mode: string): Promise<string> {
  // In production, this would call the LLM orchestrator to expand the content
  // For now, return formatted templates based on mode
  
  if (mode === 'quickstart') {
    return `# ${data.title}

## Genre
${data.genre}

## Premise
${data.brief_premise}

## Main Character
**Name:** ${data.main_character}
**Role:** Protagonist
**Background:** [AI would expand character background based on premise and genre]
**Motivations:** [AI would derive motivations from central conflict]
**Character Arc:** [AI would design character growth throughout story]

## Setting
${data.setting}

**World Details:** [AI would expand world-building based on genre and setting]
**Time Period:** [AI would establish specific timeframe]
**Key Locations:** [AI would identify important story locations]

## Central Conflict
${data.conflict}

**Stakes:** [AI would establish what characters stand to lose/gain]
**Obstacles:** [AI would create series of challenges]
**Resolution Path:** [AI would outline how conflict could be resolved]

## Story Structure

### Act I: Setup (Chapters 1-8)
- **Opening Hook:** [AI would design compelling opening]
- **Inciting Incident:** [AI would create story catalyst]
- **Plot Point 1:** [AI would establish first major turning point]

### Act II: Confrontation (Chapters 9-17)
- **Rising Action:** [AI would escalate conflict and complications]
- **Midpoint:** [AI would create major revelation or reversal]
- **Plot Point 2:** [AI would establish crisis moment]

### Act III: Resolution (Chapters 18-25)
- **Climax:** [AI would design story climax]
- **Resolution:** [AI would resolve conflicts and character arcs]
- **Denouement:** [AI would provide satisfying conclusion]

## Character Profiles
[AI would expand supporting characters, relationships, and dynamics]

## World Building
[AI would create comprehensive setting details, rules, and history]

## Themes and Motifs
[AI would identify and develop core themes throughout the story]

## Writing Style Guide
[AI would establish tone, voice, and stylistic preferences]

## Chapter Outline
[AI would create detailed chapter-by-chapter breakdown with plot points and character moments]
`
  } else if (mode === 'guided') {
    return `# ${data.title}

## Genre
${data.genre}

## Premise
${data.premise}

## Main Characters
${data.main_characters}

**Character Development:**
[AI would expand character profiles with detailed backstories, motivations, and arcs]

## Setting
**Time:** ${data.setting_time}
**Place:** ${data.setting_place}

**Expanded World Building:**
[AI would create comprehensive setting details, rules, customs, and history]

## Central Conflict
${data.central_conflict}

**Conflict Analysis:**
[AI would break down conflict layers, stakes, and progression]

## Themes
${data.themes}

**Theme Development:**
[AI would show how themes will be woven throughout the narrative]

## Target Audience
${data.target_audience}

## Tone
${data.tone}

**Voice and Style Guidelines:**
[AI would establish consistent voice and writing style]

## Key Plot Points
${data.key_plot_points}

**Detailed Plot Structure:**
[AI would expand plot points into full three-act structure with chapter breakdown]

## Character Relationships
[AI would map character dynamics, conflicts, and growth]

## Pacing Strategy
[AI would design tension curves and emotional beats]

## Research Requirements
[AI would identify areas needing research for authenticity]

## Series Potential
[AI would identify opportunities for sequel/series development]
`
  } else {
    // Paste-in mode - return content as-is but formatted
    return data.content
  }
}

export async function POST(request: NextRequest) {
  try {
    // Try both auth methods to ensure compatibility
    let userId: string | null = null
    let authToken: string | null = null
    
    try {
      const user = await currentUser()
      userId = user?.id || null
      if (userId) {
        const { getToken } = auth()
        authToken = await getToken()
      }
    } catch (currentUserError) {
      console.log('currentUser() failed, trying auth():', currentUserError)
      try {
        const authResult = await auth()
        userId = authResult.userId
        authToken = await authResult.getToken()
      } catch (authError) {
        console.error('Both auth methods failed:', authError)
      }
    }
    
    if (!userId) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    if (!authToken) {
      return NextResponse.json({ error: 'Failed to get auth token' }, { status: 401 })
    }

    const bookBibleData: BookBibleData = await request.json()

    // Validate required fields
    if (!bookBibleData.title || !bookBibleData.content) {
      return NextResponse.json(
        { error: 'Title and content are required' },
        { status: 400 }
      )
    }

    // Validate creation mode
    if (!['quickstart', 'guided', 'paste'].includes(bookBibleData.creation_mode)) {
      return NextResponse.json(
        { error: 'Invalid creation mode' },
        { status: 400 }
      )
    }

    // Generate expanded book bible content if needed
    let finalContent = bookBibleData.content
    if (bookBibleData.creation_mode !== 'paste' && bookBibleData.source_data) {
      try {
        finalContent = await generateExpandedBookBible(
          bookBibleData.source_data, 
          bookBibleData.creation_mode
        )
      } catch (error) {
        console.error('Failed to expand book bible:', error)
        // Fall back to original content if expansion fails
      }
    }

    // Get user preferences for project settings
    const defaultSettings = {
      target_chapters: bookBibleData.target_chapters || 25,
      word_count_per_chapter: bookBibleData.word_count_per_chapter || 2000,
      involvement_level: 'balanced',
      purpose: 'personal',
      book_length_tier: bookBibleData.book_length_tier || 'standard_novel',
      estimated_chapters: bookBibleData.estimated_chapters,
      target_word_count: bookBibleData.target_word_count,
      include_series_bible: bookBibleData.include_series_bible || false
    }

    // Create project data
    const projectData = {
      title: bookBibleData.title,
      genre: bookBibleData.genre,
      book_bible_content: finalContent,
      must_include_sections: bookBibleData.must_include_sections,
      settings: {
        ...defaultSettings,
        genre: bookBibleData.genre,
        target_chapters: bookBibleData.target_chapters,
        word_count_per_chapter: bookBibleData.word_count_per_chapter
      },
      owner_id: userId,
      created_at: new Date().toISOString(),
      status: 'active'
    }

    // Create project in backend (Firestore)
    const projectId = await createProjectInBackend(projectData, authToken)

    // In production, this would also:
    // 1. Generate reference files (characters, outline, world-building, style-guide, plot-timeline, 
    //    themes-and-motifs, research-notes, target-audience-profile, and optionally series-bible)
    // 2. Initialize project state tracking with book length specifications
    // 3. Set up pattern database
    // 4. Create initial quality baselines based on target word count and chapter structure

    console.log(`Book Bible created successfully for user ${userId}:`, {
      projectId,
      title: bookBibleData.title,
      mode: bookBibleData.creation_mode,
      contentLength: finalContent.length,
      mustIncludeCount: bookBibleData.must_include_sections.length
    })

    return NextResponse.json({
      success: true,
      message: 'Book Bible created successfully',
      project: {
        id: projectId,
        title: bookBibleData.title,
        genre: bookBibleData.genre,
        status: 'active',
        created_at: projectData.created_at,
        settings: projectData.settings
      }
    })

  } catch (error) {
    console.error('POST /api/book-bible/create error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}

export async function GET(request: NextRequest) {
  try {
    // Try both auth methods to ensure compatibility
    let userId: string | null = null
    let authToken: string | null = null
    
    try {
      const user = await currentUser()
      userId = user?.id || null
      if (userId) {
        const { getToken } = auth()
        authToken = await getToken()
      }
    } catch (currentUserError) {
      console.log('currentUser() failed, trying auth():', currentUserError)
      try {
        const authResult = await auth()
        userId = authResult.userId
        authToken = await authResult.getToken()
      } catch (authError) {
        console.error('Both auth methods failed:', authError)
      }
    }
    
    if (!userId) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    if (!authToken) {
      return NextResponse.json({ error: 'Failed to get auth token' }, { status: 401 })
    }

    // Get backend URL
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      return NextResponse.json({ error: 'Backend URL not configured' }, { status: 500 })
    }

    // Get all projects for the user from backend
    const response = await fetch(`${backendBaseUrl}/v2/projects/`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${authToken}`
      }
    })

    if (!response.ok) {
      const errorText = await response.text()
      console.error('Backend API error:', response.status, errorText)
      return NextResponse.json(
        { error: 'Failed to fetch projects' },
        { status: response.status }
      )
    }

    const result = await response.json()
    const projects = result.projects || []

    // Transform to match expected frontend format
    const userProjects = projects.map((project: any) => ({
      id: project.id,
      title: project.metadata?.title || project.title,
      genre: project.settings?.genre || 'Fiction',
      status: project.metadata?.status || 'active',
      created_at: project.metadata?.created_at,
      settings: project.settings,
      must_include_count: 0 // This would need to be stored/calculated properly
    }))

    return NextResponse.json({
      success: true,
      projects: userProjects,
      total: userProjects.length
    })

  } catch (error) {
    console.error('GET /api/book-bible/create error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
} 