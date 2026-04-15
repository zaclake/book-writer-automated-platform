import { NextRequest, NextResponse } from 'next/server'

// Force dynamic rendering to prevent static generation issues
export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

/**
 * Proxy publishing requests to the FastAPI backend.
 */
export async function POST(
  request: NextRequest,
  { params }: { params: { projectId: string } }
) {
  console.log('[v2/publish/project] POST request started for project:', params.projectId)

  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    console.log('[v2/publish/project] Backend URL from env:', backendBaseUrl)

    if (!backendBaseUrl) {
      console.error('[v2/publish/project] Backend URL not configured - NEXT_PUBLIC_BACKEND_URL not set')
      return NextResponse.json(
        { error: 'Backend URL not configured (NEXT_PUBLIC_BACKEND_URL missing)' },
        { status: 500 }
      )
    }

    const targetUrl = `${backendBaseUrl}/v2/publish/project/${params.projectId}`
    console.log('[v2/publish/project] Target URL:', targetUrl)

    // Get the request body
    const body = await request.json()
    console.log('[v2/publish/project] Request body keys:', Object.keys(body))

    const authHeader = request.headers.get('Authorization')
    const sessionToken = request.cookies.get('user_session')?.value
    const resolvedAuthHeader = authHeader || (sessionToken ? `Bearer ${sessionToken}` : null)
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (resolvedAuthHeader) {
      headers.Authorization = resolvedAuthHeader
    }

    // Make the request to the backend with simple retry to avoid transient ECONNRESET
    console.log('[v2/publish/project] Making request to backend...')
    let response: Response | null = null
    let attempt = 0
    const maxAttempts = 3
    while (attempt < maxAttempts) {
      attempt++
      try {
        response = await fetch(targetUrl, {
          method: 'POST',
          headers,
          body: JSON.stringify(body),
          cache: 'no-store',
        })
        break
      } catch (err) {
        console.warn(`[v2/publish/project] Attempt ${attempt} failed:`, err)
        if (attempt >= maxAttempts) throw err
        await new Promise(r => setTimeout(r, 300 * attempt))
      }
    }

    console.log('[v2/publish/project] Backend response status:', response!.status)

    if (!response!.ok) {
      const errorText = await response!.text()
      console.error('[v2/publish/project] Backend error:', errorText)
      return NextResponse.json(
        { error: 'Backend request failed', details: errorText },
        { status: response!.status }
      )
    }

    const result = await response!.json()
    console.log('[v2/publish/project] Success - job started:', result.job_id)

    return NextResponse.json(result)

  } catch (error) {
    console.error('[v2/publish/project] Request failed:', error)
    return NextResponse.json(
      { error: 'Publishing request failed', details: error instanceof Error ? error.message : String(error) },
      { status: 500 }
    )
  }
}
