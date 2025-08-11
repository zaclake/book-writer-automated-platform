import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

/**
 * Proxy auto-complete jobs requests to the FastAPI backend.
 * The backend base URL is provided via the `NEXT_PUBLIC_BACKEND_URL` env var.
 */
export async function GET(request: NextRequest) {
  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      return NextResponse.json(
        { error: 'Backend URL not configured (NEXT_PUBLIC_BACKEND_URL missing)' },
        { status: 500 }
      )
    }

    const targetUrl = `${backendBaseUrl}/auto-complete/jobs`

    // Get Clerk auth and JWT token
    const { getToken } = await auth()
    const headers: Record<string, string> = {
      'Content-Type': 'application/json'
    }
    
    try {
      const token = await getToken()
      if (token) {
        headers['authorization'] = `Bearer ${token}`
      }
    } catch (error) {
      console.error('Failed to get Clerk token:', error)
      return NextResponse.json(
        { error: 'Authentication failed' },
        { status: 401 }
      )
    }

    // Forward query parameters
    const url = new URL(request.url)
    const queryParams = url.searchParams.toString()
    const fullTargetUrl = queryParams ? `${targetUrl}?${queryParams}` : targetUrl

    const backendResponse = await fetch(fullTargetUrl, {
      method: 'GET',
      headers,
      cache: 'no-store',
      // Keep this proxy fast and bounded
      signal: AbortSignal.timeout(15000),
    })

    const data = await backendResponse.json()
    return NextResponse.json(data, { status: backendResponse.status })
  } catch (error: any) {
    console.error('[proxy] /api/auto-complete/jobs error:', error)
    return NextResponse.json(
      { error: error.message || 'Internal Server Error' },
      { status: 500 }
    )
  }
} 