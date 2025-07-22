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

  console.log('[book-bible/create] Making backend request to:', `${backendBaseUrl}/v2/projects/`)

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
    }),
    // Add timeout to prevent function timeout
    signal: AbortSignal.timeout(20000) // 20 seconds, leaving 10 seconds buffer for Vercel
  })

  if (!response.ok) {
    const errorText = await response.text()
    console.error('[book-bible/create] Backend error:', response.status, errorText)
    throw new Error(`Backend API error: ${response.status} - ${errorText}`)
  }

  const result = await response.json()
  console.log('[book-bible/create] Backend response:', result)
  
  // Extract project ID from the backend response structure
  const projectId = result.project?.id || result.project_id || result.id
  console.log('[book-bible/create] Extracted project ID:', projectId)
  
  if (!projectId) {
    console.error('[book-bible/create] No project ID found in backend response:', result)
    throw new Error('Backend did not return a valid project ID')
  }
  
  return projectId
}

async function generateExpandedBookBible(data: any, mode: string): Promise<string> {
  // Simplified template generation to reduce processing time
  console.log('[book-bible/create] Generating expanded book bible for mode:', mode)
  
  if (mode === 'quickstart') {
    return `# ${data.title}

## Genre
${data.genre}

## Premise
${data.brief_premise}

## Main Character
**Name:** ${data.main_character}
**Role:** Protagonist

## Setting
${data.setting}

## Central Conflict
${data.conflict}

## Story Structure
This book bible will be expanded with AI assistance during the writing process.

## Character Profiles
[To be expanded during writing]

## World Building
[To be expanded during writing]

## Themes and Motifs
[To be developed during writing]
`
  } else if (mode === 'guided') {
    return `# ${data.title}

## Genre
${data.genre}

## Premise
${data.premise}

## Main Characters
${data.main_characters}

## Setting
**Time:** ${data.setting_time}
**Place:** ${data.setting_place}

## Central Conflict
${data.central_conflict}

## Themes
${data.themes}

## Target Audience
${data.target_audience}

## Tone
${data.tone}

## Key Plot Points
${data.key_plot_points}

[Additional details will be expanded during the writing process]
`
  } else {
    // Paste-in mode - return content as-is
    return data.content
  }
}

export async function POST(request: NextRequest) {
  console.log('[book-bible/create] POST request started')
  
  try {
    // Use the correct Clerk auth pattern that works in other routes
    let userId: string | null = null
    let authToken: string | null = null
    
    try {
      const user = await currentUser()
      userId = user?.id || null
      console.log('[book-bible/create] Got user from currentUser():', !!userId)
      
      if (userId) {
        const { getToken } = await auth()
        authToken = await getToken()
        console.log('[book-bible/create] Got auth token:', !!authToken)
      }
    } catch (currentUserError) {
      console.log('[book-bible/create] currentUser() failed, trying auth():', currentUserError)
      try {
        const { userId: authUserId, getToken } = await auth()
        userId = authUserId
        if (getToken) {
          authToken = await getToken()
        }
        console.log('[book-bible/create] Got user from auth():', !!userId, !!authToken)
      } catch (authError) {
        console.error('[book-bible/create] Both auth methods failed:', authError)
      }
    }
    
    if (!userId) {
      console.error('[book-bible/create] No user ID found')
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    if (!authToken) {
      console.error('[book-bible/create] No auth token found')
      return NextResponse.json({ error: 'Failed to get auth token' }, { status: 401 })
    }

    const bookBibleData: BookBibleData = await request.json()
    console.log('[book-bible/create] Processing book bible data:', {
      title: bookBibleData.title,
      mode: bookBibleData.creation_mode,
      hasSourceData: !!bookBibleData.source_data
    })

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

    // Generate expanded book bible content if needed (optimized for speed)
    let finalContent = bookBibleData.content
    if (bookBibleData.creation_mode !== 'paste' && bookBibleData.source_data) {
      try {
        finalContent = await generateExpandedBookBible(
          bookBibleData.source_data, 
          bookBibleData.creation_mode
        )
        console.log('[book-bible/create] Generated expanded content length:', finalContent.length)
      } catch (error) {
        console.error('[book-bible/create] Failed to expand book bible:', error)
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

    console.log('[book-bible/create] Creating project in backend...')

    // Create project in backend (with timeout protection)
    const projectId = await createProjectInBackend(projectData, authToken)

    console.log(`[book-bible/create] Book Bible created successfully for user ${userId}:`, {
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
    console.error('[book-bible/create] POST error:', error)
    
    // Handle timeout errors specifically
    if (error instanceof Error && error.name === 'AbortError') {
      return NextResponse.json(
        { error: 'Request timeout - please try again with a simpler book bible' },
        { status: 408 }
      )
    }
    
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}

 