import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function POST(request: NextRequest) {
  console.log('[v2/chapters/generate] POST request started')
  
  try {
    const body = await request.json()
    const { project_id, chapter_number, target_word_count, stage } = body
    console.log('[v2/chapters/generate] Request body:', { project_id, chapter_number, target_word_count, stage })

    // Validate required fields
    if (!project_id || !chapter_number) {
      console.log('[v2/chapters/generate] Missing required fields')
      return NextResponse.json(
        { error: 'project_id and chapter_number are required' },
        { status: 400 }
      )
    }

    // Validate inputs
    if (chapter_number < 1 || chapter_number > 200) {
      return NextResponse.json(
        { error: 'Chapter number must be between 1 and 200' },
        { status: 400 }
      )
    }

    if (target_word_count && (target_word_count < 500 || target_word_count > 10000)) {
      return NextResponse.json(
        { error: 'Word count must be between 500 and 10000' },
        { status: 400 }
      )
    }

    const validStages = ['simple', 'spike', 'complete', '5-stage']
    if (stage && !validStages.includes(stage)) {
      return NextResponse.json(
        { error: 'Invalid stage. Must be one of: simple, spike, complete, 5-stage' },
        { status: 400 }
      )
    }

    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    console.log('[v2/chapters/generate] Backend URL from env:', backendBaseUrl)

    if (!backendBaseUrl) {
      console.error('[v2/chapters/generate] Backend URL not configured')
      return NextResponse.json(
        { error: 'Backend URL not configured' },
        { status: 500 }
      )
    }

    // Get auth token from request headers
    const authHeader = request.headers.get('authorization')
    if (!authHeader) {
      console.error('[v2/chapters/generate] No authorization header')
      return NextResponse.json(
        { error: 'Authentication required' },
        { status: 401 }
      )
    }

    // Prepare request body for backend
    const backendRequestBody = {
      project_id,
      chapter_number,
      target_word_count: target_word_count || 2000,
      stage: stage || 'simple'
    }

    // Make request to backend
    const backendUrl = `${backendBaseUrl}/v2/chapters/generate`
    console.log('[v2/chapters/generate] Making request to backend:', backendUrl)
    
    const backendResponse = await fetch(backendUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': authHeader,
      },
      body: JSON.stringify(backendRequestBody),
      // Add timeout to prevent Vercel function timeout - 45 seconds for AI generation
      signal: AbortSignal.timeout(45000)
    })

    console.log('[v2/chapters/generate] Backend response status:', backendResponse.status)

    if (!backendResponse.ok) {
      const errorData = await backendResponse.text()
      console.error('[v2/chapters/generate] Backend error:', errorData)
      
      try {
        const errorJson = JSON.parse(errorData)
        return NextResponse.json(
          { error: errorJson.detail || 'Backend generation failed' },
          { status: backendResponse.status }
        )
      } catch {
        return NextResponse.json(
          { error: 'Chapter generation failed' },
          { status: backendResponse.status }
        )
      }
    }

    const responseData = await backendResponse.json()
    console.log('[v2/chapters/generate] Backend success response received')

    return NextResponse.json(responseData)

  } catch (error) {
    console.error('[v2/chapters/generate] Error:', error)
    return NextResponse.json(
      { error: 'Internal server error during chapter generation' },
      { status: 500 }
    )
  }
} 