import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

export const dynamic = 'force-dynamic'

/**
 * Proxy the request to the FastAPI backend `/auto-complete/jobs` endpoint.
 * The backend base URL is provided via the `NEXT_PUBLIC_BACKEND_URL` env var.
 */
export async function GET(request: NextRequest) {
  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL
    if (!backendBaseUrl) {
      return NextResponse.json(
        { error: 'Backend URL not configured (NEXT_PUBLIC_BACKEND_URL missing)' },
        { status: 500 }
      )
    }

    const queryString = request.nextUrl.searchParams.toString()
    const targetUrl = `${backendBaseUrl}/auto-complete/jobs${queryString ? `?${queryString}` : ''}`

    // Get Clerk auth and JWT token
    const { getToken } = auth()
    const headers: Record<string, string> = {}
    
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

    const backendResponse = await fetch(targetUrl, {
      method: 'GET',
      headers,
      // Disable Next.js caching for dynamic data
      cache: 'no-store'
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