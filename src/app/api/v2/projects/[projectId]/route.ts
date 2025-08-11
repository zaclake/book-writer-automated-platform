import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

/**
 * Proxy single project requests to the FastAPI backend with authentication.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: { projectId: string } }
) {
  console.log('[v2/projects/single] GET request started for project:', params.projectId)
  
  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      console.error('[v2/projects/single] Backend URL not configured')
      return NextResponse.json(
        { error: 'Backend URL not configured (NEXT_PUBLIC_BACKEND_URL missing)' },
        { status: 500 }
      )
    }

    // Get Clerk auth and JWT token
    const { getToken } = await auth()
    const headers: Record<string, string> = {
      'Content-Type': 'application/json'
    }
    
    try {
      const token = await getToken()
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
        console.log('[v2/projects/single] Auth token added to request')
      } else {
        console.warn('[v2/projects/single] No auth token available')
        return NextResponse.json(
          { error: 'Authentication required' },
          { status: 401 }
        )
      }
    } catch (error) {
      console.error('[v2/projects/single] Failed to get Clerk token:', error)
      return NextResponse.json(
        { error: 'Authentication failed' },
        { status: 401 }
      )
    }

    // Forward query parameters
    const url = new URL(request.url)
    const queryParams = url.searchParams.toString()
    const targetUrl = `${backendBaseUrl}/v2/projects/${params.projectId}`
    const fullTargetUrl = queryParams ? `${targetUrl}?${queryParams}` : targetUrl
    
    console.log('[v2/projects/single] Forwarding to:', fullTargetUrl)

    const backendResponse = await fetch(fullTargetUrl, {
      method: 'GET',
      headers,
      cache: 'no-store'
    })

    const data = await backendResponse.json()
    
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
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      console.error('[v2/projects/single] Backend URL not configured')
      return NextResponse.json(
        { error: 'Backend URL not configured (NEXT_PUBLIC_BACKEND_URL missing)' },
        { status: 500 }
      )
    }

    const { getToken } = await auth()
    const headers: Record<string, string> = {
      'Content-Type': 'application/json'
    }

    const token = await getToken()
    if (!token) {
      return NextResponse.json({ error: 'Authentication required' }, { status: 401 })
    }
    headers['Authorization'] = `Bearer ${token}`

    const body = await request.text()

    const targetUrl = `${backendBaseUrl}/v2/projects/${params.projectId}`
    const backendResponse = await fetch(targetUrl, {
      method: 'PUT',
      headers,
      body,
    })

    const data = await backendResponse.json().catch(() => ({}))
    return NextResponse.json(data, { status: backendResponse.status })
  } catch (error) {
    console.error('[v2/projects/single] PUT error:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: { projectId: string } }
) {
  console.log('[v2/projects/single] DELETE request started for project:', params.projectId)
  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      console.error('[v2/projects/single] Backend URL not configured')
      return NextResponse.json(
        { error: 'Backend URL not configured (NEXT_PUBLIC_BACKEND_URL missing)' },
        { status: 500 }
      )
    }

    // Get Clerk auth and JWT token
    const { getToken } = await auth()
    const headers: Record<string, string> = {
      'Content-Type': 'application/json'
    }

    try {
      const token = await getToken()
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
        console.log('[v2/projects/single] Auth token added to DELETE request')
      } else {
        console.warn('[v2/projects/single] No auth token available for DELETE')
        return NextResponse.json(
          { error: 'Authentication required' },
          { status: 401 }
        )
      }
    } catch (error) {
      console.error('[v2/projects/single] Failed to get Clerk token:', error)
      return NextResponse.json(
        { error: 'Authentication failed' },
        { status: 401 }
      )
    }

    const targetUrl = `${backendBaseUrl}/v2/projects/${params.projectId}`
    console.log('[v2/projects/single] Forwarding DELETE to:', targetUrl)

    const backendResponse = await fetch(targetUrl, {
      method: 'DELETE',
      headers,
      cache: 'no-store'
    })

    const data = await backendResponse.json().catch(() => ({}))
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