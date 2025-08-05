import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

/**
 * Proxy chapter generation requests to the FastAPI backend with authentication.
 */
export async function POST(request: NextRequest) {
  console.log('[v2/chapters/generate] POST request started')
  
  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      console.error('[v2/chapters/generate] Backend URL not configured')
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
        console.log('[v2/chapters/generate] Auth token added to request')
      } else {
        console.warn('[v2/chapters/generate] No auth token available')
        return NextResponse.json(
          { error: 'Authentication required' },
          { status: 401 }
        )
      }
    } catch (error) {
      console.error('[v2/chapters/generate] Failed to get Clerk token:', error)
      return NextResponse.json(
        { error: 'Authentication failed' },
        { status: 401 }
      )
    }

    // Get request body
    const body = await request.json()
    console.log('[v2/chapters/generate] Request body keys:', Object.keys(body))

    const targetUrl = `${backendBaseUrl}/v2/chapters/generate`
    
    console.log('[v2/chapters/generate] Forwarding to:', targetUrl)
    console.log('[v2/chapters/generate] Headers:', Object.keys(headers))

    let backendResponse;
    try {
      backendResponse = await fetch(targetUrl, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
        cache: 'no-store',
        signal: AbortSignal.timeout(30000) // 30 second timeout
      })
      console.log('[v2/chapters/generate] Backend response status:', backendResponse.status)
    } catch (fetchError) {
      console.error('[v2/chapters/generate] Fetch error:', fetchError)
      return NextResponse.json(
        { error: 'Failed to connect to backend service', details: fetchError.message },
        { status: 503 }
      )
    }

    const data = await backendResponse.json()
    
    if (!backendResponse.ok) {
      console.error('[v2/chapters/generate] Backend error:', backendResponse.status, data)
      return NextResponse.json(data, { status: backendResponse.status })
    }

    console.log('[v2/chapters/generate] Request completed successfully')
    return NextResponse.json(data)

  } catch (error) {
    console.error('[v2/chapters/generate] Error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}