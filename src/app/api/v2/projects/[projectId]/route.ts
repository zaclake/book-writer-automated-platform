import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

/**
 * Proxy single project requests to the FastAPI backend.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: { projectId: string } }
) {
  console.log('[v2/projects/single] GET request started for project:', params.projectId)

  try {
    const backendBaseUrl =
      process.env.NEXT_PUBLIC_BACKEND_URL?.trim() || process.env.BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      console.error('[v2/projects/single] Backend URL not configured')
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
    const targetUrl = `${normalizedBase}/v2/projects/${encodeURIComponent(params.projectId)}`
    const fullTargetUrl = queryParams ? `${targetUrl}?${queryParams}` : targetUrl

    console.log('[v2/projects/single] Forwarding to:', fullTargetUrl)

    const backendResponse = await fetch(fullTargetUrl, {
      method: 'GET',
      headers,
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
      console.error('[v2/projects/single] Backend error:', backendResponse.status, data)
      return NextResponse.json(data, { status: backendResponse.status })
    }

    console.log('[v2/projects/single] Request completed successfully')
    return NextResponse.json(data)

  } catch (error) {
    console.error('[v2/projects/single] Error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: { projectId: string } }
) {
  console.log('[v2/projects/single] PUT request started for project:', params.projectId)

  try {
    const backendBaseUrl =
      process.env.NEXT_PUBLIC_BACKEND_URL?.trim() || process.env.BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      console.error('[v2/projects/single] Backend URL not configured')
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
    const targetUrl = `${normalizedBase}/v2/projects/${encodeURIComponent(params.projectId)}`
    const backendResponse = await fetch(targetUrl, {
      method: 'PUT',
      headers,
      body,
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
    console.error('[v2/projects/single] PUT error:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: { projectId: string } }
) {
  console.log('[v2/projects/single] PATCH request started for project:', params.projectId)

  try {
    const backendBaseUrl =
      process.env.NEXT_PUBLIC_BACKEND_URL?.trim() || process.env.BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      console.error('[v2/projects/single] Backend URL not configured')
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
    const targetUrl = `${normalizedBase}/v2/projects/${encodeURIComponent(params.projectId)}`
    const backendResponse = await fetch(targetUrl, {
      method: 'PATCH',
      headers,
      body,
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
    console.error('[v2/projects/single] PATCH error:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: { projectId: string } }
) {
  console.log('[v2/projects/single] DELETE request started for project:', params.projectId)

  try {
    const backendBaseUrl =
      process.env.NEXT_PUBLIC_BACKEND_URL?.trim() || process.env.BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      console.error('[v2/projects/single] Backend URL not configured')
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

    const normalizedBase = backendBaseUrl.replace(/\/$/, '')
    const targetUrl = `${normalizedBase}/v2/projects/${encodeURIComponent(params.projectId)}`
    console.log('[v2/projects/single] Forwarding DELETE to:', targetUrl)

    const backendResponse = await fetch(targetUrl, {
      method: 'DELETE',
      headers,
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
      console.error('[v2/projects/single] Backend DELETE error:', backendResponse.status, data)
      return NextResponse.json(data, { status: backendResponse.status })
    }

    console.log('[v2/projects/single] DELETE completed successfully')
    return NextResponse.json(data)
  } catch (error) {
    console.error('[v2/projects/single] DELETE error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}
