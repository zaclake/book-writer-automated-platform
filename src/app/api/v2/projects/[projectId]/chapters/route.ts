import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

/**
 * Proxy project chapters requests to the FastAPI backend with authentication.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: { projectId: string } }
) {
  console.log('[v2/projects/chapters] GET request started for project:', params.projectId)
  
  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      console.error('[v2/projects/chapters] Backend URL not configured')
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
        console.log('[v2/projects/chapters] Auth token added to request')
      } else {
        console.warn('[v2/projects/chapters] No auth token available')
        return NextResponse.json(
          { error: 'Authentication required' },
          { status: 401 }
        )
      }
    } catch (error) {
      console.error('[v2/projects/chapters] Failed to get Clerk token:', error)
      return NextResponse.json(
        { error: 'Authentication failed' },
        { status: 401 }
      )
    }

    // Forward query parameters
    const url = new URL(request.url)
    const queryParams = url.searchParams.toString()
    const targetUrl = `${backendBaseUrl}/v2/chapters/project/${params.projectId}`
    const fullTargetUrl = queryParams ? `${targetUrl}?${queryParams}` : targetUrl
    
    console.log('[v2/projects/chapters] Forwarding to:', fullTargetUrl)

    const backendResponse = await fetch(fullTargetUrl, {
      method: 'GET',
      headers,
      cache: 'no-store'
    })

    const data = await backendResponse.json()
    
    if (!backendResponse.ok) {
      console.error('[v2/projects/chapters] Backend error:', backendResponse.status, data)
      return NextResponse.json(data, { status: backendResponse.status })
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