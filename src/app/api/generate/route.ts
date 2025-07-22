import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function POST(request: NextRequest) {
  console.log('[generate] POST request started')
  
  try {
    const body = await request.json()
    const { project_id, chapter_number, words, stage } = body
    console.log('[generate] Request body:', { project_id, chapter_number, words, stage })

    if (!project_id || !chapter_number || !words) {
      console.log('[generate] Missing required fields')
      return NextResponse.json(
        { error: 'project_id, chapter_number, and words are required' },
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

    if (words < 500 || words > 10000) {
      return NextResponse.json(
        { error: 'Word count must be between 500 and 10000' },
        { status: 400 }
      )
    }

    const validStages = ['spike', 'complete', '5-stage']
    if (stage && !validStages.includes(stage)) {
      return NextResponse.json(
        { error: 'Invalid stage. Must be one of: spike, complete, 5-stage' },
        { status: 400 }
      )
    }

    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    console.log('[generate] Backend URL from env:', backendBaseUrl)

    if (!backendBaseUrl) {
      console.error('[generate] Backend URL not configured')
      return NextResponse.json(
        { error: 'Backend URL not configured' },
        { status: 500 }
      )
    }

    const targetUrl = `${backendBaseUrl}/chapters/generate`
    console.log('[generate] Target URL:', targetUrl)

    // Prepare headers for the backend request
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }

    // Forward the Authorization header if present
    const authHeader = request.headers.get('Authorization')
    console.log('[generate] Authorization header:', authHeader ? `${authHeader.substring(0, 30)}...` : 'MISSING')

    if (authHeader) {
      headers['Authorization'] = authHeader
    }

    // Forward the request body as-is (it's already in the correct format)
    console.log('[generate] Making request to backend with body:', body)

    // Make the request to the backend
    const backendResponse = await fetch(targetUrl, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      // Add timeout to prevent Vercel function timeout
      signal: AbortSignal.timeout(25000) // 25 seconds for chapter generation
    })

    console.log('[generate] Backend response status:', backendResponse.status)

    if (!backendResponse.ok) {
      const errorText = await backendResponse.text()
      console.error('[generate] Backend error:', errorText)
      
      // Try to parse as JSON first, fall back to text
      let errorData
      try {
        errorData = JSON.parse(errorText)
      } catch {
        errorData = { detail: errorText }
      }
      
      return NextResponse.json(
        errorData,
        { status: backendResponse.status }
      )
    }

    const data = await backendResponse.json()
    console.log('[generate] Backend success, returning data')

    return NextResponse.json(data, {
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
      }
    })

  } catch (error) {
    console.error('[generate] Request failed:', error)
    
    // Handle timeout errors specifically
    if (error instanceof Error && error.name === 'AbortError') {
      return NextResponse.json(
        { error: 'Chapter generation timeout - please try again' },
        { status: 408, headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        }}
      )
    }
    
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500, headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
      }}
    )
  }
}

export async function OPTIONS(request: NextRequest) {
  console.log('[generate] OPTIONS request')
  
  return NextResponse.json({
    message: 'Generate route is accessible'
  }, {
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    }
  })
}

 