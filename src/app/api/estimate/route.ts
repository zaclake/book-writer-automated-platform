import { NextRequest, NextResponse } from 'next/server'

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { project_id, chapter_number, words, stage } = body

    if (!project_id || !chapter_number || !words) {
      return NextResponse.json(
        { error: 'project_id, chapter_number, and word count are required' },
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
    if (!backendBaseUrl) {
      console.error('[estimate] Backend URL not configured')
      return NextResponse.json(
        { error: 'Backend URL not configured' },
        { status: 500 }
      )
    }

    const targetUrl = `${backendBaseUrl}/v2/estimate`
    console.log('[estimate] Target URL:', targetUrl)

    // Prepare headers for the backend request
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }
    const authHeader = request.headers.get('Authorization')
    if (authHeader) {
      headers['Authorization'] = authHeader
    }

    // Forward the request body as-is
    console.log('[estimate] Making request to backend with body:', body)
    const backendResponse = await fetch(targetUrl, {
      method: 'POST',
      headers,
      body: JSON.stringify(body)
    })

    console.log('[estimate] Backend response status:', backendResponse.status)

    if (!backendResponse.ok) {
      const errorText = await backendResponse.text()
      console.error('[estimate] Backend error:', errorText)
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
    console.log('[estimate] Backend success, returning data')
    return NextResponse.json(data)
  } catch (error: any) {
    console.error('[estimate] Request failed:', error)
    if (error.message?.includes('timeout')) {
      return NextResponse.json(
        { error: 'Estimation timed out' },
        { status: 408 }
      )
    }
    return NextResponse.json(
      { error: `Estimation failed: ${error.message}` },
      { status: 500 }
    )
  }
} 