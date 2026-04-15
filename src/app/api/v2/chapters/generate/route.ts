import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

/**
 * Proxy chapter generation requests to the FastAPI backend.
 */
export async function POST(request: NextRequest) {
  console.log('[v2/chapters/generate] POST request started')

  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      console.error('[v2/chapters/generate] Backend URL not configured')
      return NextResponse.json(
        { error: 'Backend URL not configured (NEXT_PUBLIC_BACKEND_URL missing)' },
        { status: 500 }
      )
    }

    const authHeader = request.headers.get('Authorization')
    const sessionToken = request.cookies.get('user_session')?.value
    const resolvedAuthHeader = authHeader || (sessionToken ? `Bearer ${sessionToken}` : null)
    const headers: Record<string, string> = {
      'Content-Type': 'application/json'
    }
    if (resolvedAuthHeader) {
      headers['Authorization'] = resolvedAuthHeader
    }

    // Get request body
    const body = await request.json()
    console.log('[v2/chapters/generate] Request body keys:', Object.keys(body))

    const targetUrl = `${backendBaseUrl}/v2/chapters/generate`

    console.log('[v2/chapters/generate] Forwarding to:', targetUrl)
    console.log('[v2/chapters/generate] Headers:', Object.keys(headers))

    let backendResponse;
    try {
      backendResponse = await fetch(targetUrl, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
        cache: 'no-store',
        // Allow long-running backend; if this times out, we'll inform client to keep waiting.
        signal: AbortSignal.timeout(60000)
      })
      console.log('[v2/chapters/generate] Backend response status:', backendResponse.status)
    } catch (fetchError) {
      console.error('[v2/chapters/generate] Fetch error:', fetchError)
      // Signal to client that job likely continues on backend; client should poll for chapter
      return NextResponse.json(
        { status: 'accepted', message: 'Backend still processing. Please poll chapter status.' },
        { status: 202 }
      )
    }

    const contentType = backendResponse.headers.get('content-type') || ''
    let data: any = null
    let rawText: string | null = null
    if (contentType.includes('application/json')) {
      data = await backendResponse.json()
    } else {
      rawText = await backendResponse.text()
      data = rawText ? { error: rawText } : { error: 'Empty response from backend' }
    }

    if (!backendResponse.ok) {
      console.error('[v2/chapters/generate] Backend error:', backendResponse.status, data)
      return NextResponse.json(
        {
          ...data,
          status: backendResponse.status,
          backend_content_type: contentType || 'unknown',
          backend_raw: rawText
        },
        { status: backendResponse.status }
      )
    }

    console.log('[v2/chapters/generate] Request completed successfully')
    return NextResponse.json(data)

  } catch (error) {
    console.error('[v2/chapters/generate] Error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}
