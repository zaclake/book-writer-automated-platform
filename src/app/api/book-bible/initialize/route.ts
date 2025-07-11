import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

/**
 * Proxy Book Bible initialization requests to the FastAPI backend.
 */
export async function POST(request: NextRequest) {
  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL
    if (!backendBaseUrl) {
      return NextResponse.json(
        { error: 'Backend URL not configured (NEXT_PUBLIC_BACKEND_URL missing)' },
        { status: 500 }
      )
    }

    const targetUrl = `${backendBaseUrl}/book-bible/initialize`

    const headers: Record<string, string> = {
      'Content-Type': 'application/json'
    }
    
    // Get Clerk auth and JWT token with better error handling
    try {
      const { getToken } = await auth()
      const token = await getToken()
      if (token) {
        headers['authorization'] = `Bearer ${token}`
      } else {
        // No token available - user not authenticated
        return NextResponse.json(
          { error: 'User not authenticated' },
          { status: 401 }
        )
      }
    } catch (error) {
      console.error('Failed to get Clerk authentication:', error)
      return NextResponse.json(
        { error: 'Authentication failed' },
        { status: 401 }
      )
    }

    const body = await request.text()

    const backendResponse = await fetch(targetUrl, {
      method: 'POST',
      headers,
      body,
      cache: 'no-store'
    })

    const data = await backendResponse.json()
    return NextResponse.json(data, { status: backendResponse.status })
  } catch (error: any) {
    console.error('[proxy] /api/book-bible/initialize error:', error)
    return NextResponse.json(
      { error: error.message || 'Internal Server Error' },
      { status: 500 }
    )
  }
} 