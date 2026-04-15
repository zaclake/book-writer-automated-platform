import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

/**
 * Proxy project chapters requests to the FastAPI backend.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: { projectId: string } }
) {
  console.log('[v2/projects/chapters] GET request started for project:', params.projectId)

  try {
    const backendBaseUrl =
      process.env.NEXT_PUBLIC_BACKEND_URL?.trim() || process.env.BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      console.error('[v2/projects/chapters] Backend URL not configured')
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

    // Forward query parameters
    const url = new URL(request.url)
    const queryParams = url.searchParams.toString()
    const normalizedBase = backendBaseUrl.replace(/\/$/, '')
    const targetUrl = `${normalizedBase}/v2/projects/${encodeURIComponent(params.projectId)}/chapters`
    const fullTargetUrl = queryParams ? `${targetUrl}?${queryParams}` : targetUrl

    console.log('[v2/projects/chapters] Forwarding to:', fullTargetUrl)

    // Add retry for transient backend fetch failures (ECONNRESET)
    let backendResponse: Response | null = null
    let attempt = 0
    const maxAttempts = 3
    while (attempt < maxAttempts) {
      attempt++
      try {
        backendResponse = await fetch(fullTargetUrl, {
          method: 'GET',
          headers,
          cache: 'no-store',
          signal: AbortSignal.timeout(60000),
        })
        break
      } catch (err) {
        console.warn(`[v2/projects/chapters] Attempt ${attempt} failed:`, err)
        if (attempt >= maxAttempts) throw err
        await new Promise(r => setTimeout(r, 250 * attempt))
      }
    }

    const rawText = await backendResponse!.text()
    let data: any = {}
    if (rawText) {
      try {
        data = JSON.parse(rawText)
      } catch {
        data = { message: rawText }
      }
    }

    if (!backendResponse!.ok) {
      console.error('[v2/projects/chapters] Backend error:', backendResponse!.status, data)
      return NextResponse.json(data, { status: backendResponse!.status })
    }

    console.log('[v2/projects/chapters] Request completed successfully')
    return NextResponse.json(data)

  } catch (error) {
    console.error('[v2/projects/chapters] Error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: { projectId: string } }
) {
  try {
    const backendBaseUrl =
      process.env.NEXT_PUBLIC_BACKEND_URL?.trim() || process.env.BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      return NextResponse.json(
        { error: 'Backend URL not configured' },
        { status: 500 }
      )
    }

    const authHeader = request.headers.get('Authorization')
    const sessionToken = request.cookies.get('user_session')?.value
    const resolvedAuthHeader = authHeader || (sessionToken ? `Bearer ${sessionToken}` : null)
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (resolvedAuthHeader) {
      headers['Authorization'] = resolvedAuthHeader
    }

    const normalizedBase = backendBaseUrl.replace(/\/$/, '')
    const targetUrl = `${normalizedBase}/v2/projects/${encodeURIComponent(params.projectId)}/chapters`

    const backendResponse = await fetch(targetUrl, {
      method: 'DELETE',
      headers,
      cache: 'no-store',
      signal: AbortSignal.timeout(60000),
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

    return NextResponse.json(data, { status: backendResponse.status })
  } catch (error) {
    console.error('[v2/projects/chapters] DELETE error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}
