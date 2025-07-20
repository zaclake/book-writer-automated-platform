import { NextRequest, NextResponse } from 'next/server'
import { auth, currentUser } from '@clerk/nextjs/server'

interface ExpandRequest {
  source_data: any
  creation_mode: 'quickstart' | 'guided'
  book_specs?: {
    target_chapters?: number
    target_word_count?: number
    word_count_per_chapter?: number
    book_length_tier?: string
  }
}

export async function POST(request: NextRequest) {
  try {
    // Authentication
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

    const { source_data, creation_mode, book_specs }: ExpandRequest = await request.json()

    // Validate request
    if (!source_data || !creation_mode) {
      return NextResponse.json(
        { error: 'source_data and creation_mode are required' },
        { status: 400 }
      )
    }

    if (!['quickstart', 'guided'].includes(creation_mode)) {
      return NextResponse.json(
        { error: 'Invalid creation mode. Must be quickstart or guided' },
        { status: 400 }
      )
    }

    // Check if OpenAI expansion is enabled
    const openaiEnabled = process.env.ENABLE_OPENAI_EXPANSION !== 'false'
    
    if (!openaiEnabled) {
      return NextResponse.json(
        { error: 'OpenAI expansion is disabled via environment configuration' },
        { status: 503 }
      )
    }

    // Call backend expansion API
    const backendUrl = process.env.RAILWAY_URL || 'http://localhost:8000'
    
    try {
      console.log('Calling backend expansion API...')
      
      const backendResponse = await fetch(`${backendUrl}/v2/projects/expand-book-bible`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${authToken}`,
        },
        body: JSON.stringify({
          source_data,
          creation_mode,
          book_specs: book_specs || {}
        }),
      })

      if (!backendResponse.ok) {
        const errorData = await backendResponse.text()
        console.error('Backend expansion API error:', backendResponse.status, errorData)
        return NextResponse.json(
          { error: `Backend API error: ${backendResponse.status} - ${errorData}` },
          { status: backendResponse.status }
        )
      }

      const expansionResult = await backendResponse.json()
      
      console.log('Backend expansion successful:', {
        inputLength: JSON.stringify(source_data).length,
        outputLength: expansionResult.expanded_content?.length || 0
      })

      return NextResponse.json({
        success: true,
        expanded_content: expansionResult.expanded_content,
        metadata: {
          creation_mode,
          expansion_time: expansionResult.expansion_time,
          word_count: expansionResult.word_count,
          ai_generated: true
        }
      })

    } catch (error) {
      console.error('Backend expansion API call failed:', error)
      return NextResponse.json(
        { error: 'Failed to expand book bible content' },
        { status: 500 }
      )
    }

  } catch (error) {
    console.error('POST /api/book-bible/expand error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
} 