import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

/**
 * Proxy reference generation requests to the FastAPI backend with authentication.
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

    // Get Clerk auth and JWT token
    const { getToken } = await auth()
    const headers: Record<string, string> = {
      'Content-Type': 'application/json'
    }
    
    try {
      const token = await getToken()
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
        console.log('[v2/projects/references/generate] Auth token added to request')
      } else {
        console.warn('[v2/projects/references/generate] No auth token available')
        return NextResponse.json(
          { error: 'Authentication required' },
          { status: 401 }
        )
      }
    } catch (error) {
      console.error('[v2/projects/references/generate] Failed to get Clerk token:', error)
      return NextResponse.json(
        { error: 'Authentication failed' },
        { status: 401 }
      )
    }

    // Get request body
    const body = await request.json()

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