import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

/**
 * Proxy reference generation requests to the FastAPI backend.
 */
export async function POST(
  request: NextRequest,
  { params }: { params: { projectId: string } }
) {
  console.log('[v2/projects/references/generate] POST request started for project:', params.projectId)

  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      console.error('[v2/projects/references/generate] Backend URL not configured')
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

    // Get request body (may be empty for regeneration)
    let body = {}
    try {
      body = await request.json()
    } catch {
      // Empty body is valid for regeneration requests
    }

    const targetUrl = `${backendBaseUrl}/v2/projects/${params.projectId}/references/generate`

    console.log('[v2/projects/references/generate] Forwarding to:', targetUrl)

    const backendResponse = await fetch(targetUrl, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      cache: 'no-store'
    })

    const data = await backendResponse.json()

    if (!backendResponse.ok) {
      console.error('[v2/projects/references/generate] Backend error:', backendResponse.status, data)
      return NextResponse.json(data, { status: backendResponse.status })
    }

    console.log('[v2/projects/references/generate] Request completed successfully')
    return NextResponse.json(data)

  } catch (error) {
    console.error('[v2/projects/references/generate] Error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}
