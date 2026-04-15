import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

/**
 * Proxy individual reference file requests to the FastAPI backend.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: { projectId: string; filename: string } }
) {
  console.log('[v2/projects/references/filename] GET request started for:', params.projectId, params.filename)

  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      console.error('[v2/projects/references/filename] Backend URL not configured')
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

    // Forward query parameters
    const url = new URL(request.url)
    const queryParams = url.searchParams.toString()
    const targetUrl = `${backendBaseUrl}/v2/projects/${params.projectId}/references/${params.filename}`
    const fullTargetUrl = queryParams ? `${targetUrl}?${queryParams}` : targetUrl

    console.log('[v2/projects/references/filename] Forwarding to:', fullTargetUrl)

    const backendResponse = await fetch(fullTargetUrl, {
      method: 'GET',
      headers,
      cache: 'no-store'
    })

    const data = await backendResponse.json()

    if (!backendResponse.ok) {
      console.error('[v2/projects/references/filename] Backend error:', backendResponse.status, data)
      return NextResponse.json(data, { status: backendResponse.status })
    }

    console.log('[v2/projects/references/filename] Request completed successfully')
    return NextResponse.json(data)

  } catch (error) {
    console.error('[v2/projects/references/filename] Error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: { projectId: string; filename: string } }
) {
  console.log('[v2/projects/references/filename] PUT request started for:', params.projectId, params.filename)

  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      console.error('[v2/projects/references/filename] Backend URL not configured')
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
    const targetUrl = `${backendBaseUrl}/v2/projects/${params.projectId}/references/${params.filename}`

    const backendResponse = await fetch(targetUrl, {
      method: 'PUT',
      headers,
      body: JSON.stringify(body),
      cache: 'no-store'
    })

    const data = await backendResponse.json()

    if (!backendResponse.ok) {
      console.error('[v2/projects/references/filename] Backend error:', backendResponse.status, data)
      return NextResponse.json(data, { status: backendResponse.status })
    }

    return NextResponse.json(data)
  } catch (error) {
    console.error('[v2/projects/references/filename] Error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}
