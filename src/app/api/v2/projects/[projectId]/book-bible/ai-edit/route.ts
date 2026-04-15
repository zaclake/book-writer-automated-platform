import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

/**
 * Proxy AI edit requests for the book bible to the FastAPI backend.
 */
export async function POST(
  request: NextRequest,
  { params }: { params: { projectId: string } }
) {
  console.log('[v2/projects/book-bible/ai-edit] POST request started for:', params.projectId)

  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      console.error('[v2/projects/book-bible/ai-edit] Backend URL not configured')
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

    const body = await request.json()
    const targetUrl = `${backendBaseUrl}/v2/projects/${params.projectId}/book-bible/ai-edit`

    const backendResponse = await fetch(targetUrl, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      cache: 'no-store'
    })

    const data = await backendResponse.json()

    if (!backendResponse.ok) {
      console.error('[v2/projects/book-bible/ai-edit] Backend error:', backendResponse.status, data)
      return NextResponse.json(data, { status: backendResponse.status })
    }

    return NextResponse.json(data)
  } catch (error) {
    console.error('[v2/projects/book-bible/ai-edit] Error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}
