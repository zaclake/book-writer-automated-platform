import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

/**
 * Proxy title recommendation requests to the FastAPI backend.
 */
export async function POST(
  request: NextRequest,
  { params }: { params: { projectId: string } }
) {
  console.log('[v2/projects/title-recommendations] POST request started for project:', params.projectId)

  try {
    const backendBaseUrl =
      process.env.NEXT_PUBLIC_BACKEND_URL?.trim() || process.env.BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      console.error('[v2/projects/title-recommendations] Backend URL not configured')
      return NextResponse.json(
        { error: 'Backend URL not configured (NEXT_PUBLIC_BACKEND_URL/BACKEND_URL missing)' },
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

    const body = await request.text()
    const normalizedBase = backendBaseUrl.replace(/\/$/, '')
    const targetUrl = `${normalizedBase}/v2/projects/${encodeURIComponent(params.projectId)}/title-recommendations`

    console.log('[v2/projects/title-recommendations] Forwarding to:', targetUrl)

    const backendResponse = await fetch(targetUrl, {
      method: 'POST',
      headers,
      body,
      cache: 'no-store'
    })

    const rawText = await backendResponse.text()
    let data: any = {}
    if (rawText) {
      try {
        data = JSON.parse(rawText)
      } catch {
        data = { message: rawText }
      }
    }

    if (!backendResponse.ok) {
      console.error('[v2/projects/title-recommendations] Backend error:', backendResponse.status, data)
      return NextResponse.json(data, { status: backendResponse.status })
    }

    console.log('[v2/projects/title-recommendations] Request completed successfully')
    return NextResponse.json(data)
  } catch (error) {
    console.error('[v2/projects/title-recommendations] Error:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
