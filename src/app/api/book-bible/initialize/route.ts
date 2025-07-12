import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

/**
 * Proxy Book Bible initialization requests to the FastAPI backend.
 */
export async function POST(request: NextRequest) {
  console.log('[book-bible/initialize] Request started')
  
  try {
    const backendBaseUrl = (process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL)?.trim()
    console.log('[book-bible/initialize] Backend URL from env:', backendBaseUrl)
    
    if (!backendBaseUrl) {
      console.error('[book-bible/initialize] Backend URL not configured - neither BACKEND_URL nor NEXT_PUBLIC_BACKEND_URL set')
      return NextResponse.json(
        { error: 'Backend URL not configured (BACKEND_URL or NEXT_PUBLIC_BACKEND_URL missing)' },
        { status: 500 }
      )
    }

    const targetUrl = `${backendBaseUrl}/book-bible/initialize`
    console.log('[book-bible/initialize] Target URL:', targetUrl)

    const headers: Record<string, string> = {
      'Content-Type': 'application/json'
    }
    
    // Get Clerk auth and JWT token with better error handling
    console.log('[book-bible/initialize] Getting authentication...')
    try {
      const authResult = await auth()
      console.log('[book-bible/initialize] Auth result:', { userId: authResult?.userId })
      
      if (!authResult?.getToken) {
        console.log('[book-bible/initialize] No getToken function available')
        return NextResponse.json(
          { error: 'Authentication service unavailable' },
          { status: 500 }
        )
      }
      
      const token = await authResult.getToken()
      console.log('[book-bible/initialize] Token available:', !!token)
      
      if (token) {
        headers['authorization'] = `Bearer ${token}`
        console.log('[book-bible/initialize] Authorization header set')
      } else {
        console.log('[book-bible/initialize] No token - user not authenticated')
        return NextResponse.json(
          { error: 'User not authenticated' },
          { status: 401 }
        )
      }
    } catch (error) {
      console.error('[book-bible/initialize] Clerk authentication error:', error)
      return NextResponse.json(
        { error: `Authentication failed: ${error instanceof Error ? error.message : 'Unknown error'}` },
        { status: 401 }
      )
    }

    console.log('[book-bible/initialize] Reading request body...')
    const body = await request.text()
    console.log('[book-bible/initialize] Body length:', body.length)

    console.log('[book-bible/initialize] Making request to backend...')
    const backendResponse = await fetch(targetUrl, {
      method: 'POST',
      headers,
      body,
      cache: 'no-store'
    })

    console.log('[book-bible/initialize] Backend response status:', backendResponse.status)
    
    try {
      const data = await backendResponse.json()
      console.log('[book-bible/initialize] Backend response parsed successfully')
      return NextResponse.json(data, { status: backendResponse.status })
    } catch (parseError) {
      console.error('[book-bible/initialize] Failed to parse backend response:', parseError)
      const text = await backendResponse.text()
      console.error('[book-bible/initialize] Backend response text:', text)
      return NextResponse.json(
        { error: 'Backend returned invalid response', details: text },
        { status: 500 }
      )
    }
  } catch (error: any) {
    console.error('[book-bible/initialize] Unexpected error:', error)
    console.error('[book-bible/initialize] Error stack:', error?.stack)
    return NextResponse.json(
      { error: `Internal Server Error: ${error?.message || 'Unknown error'}` },
      { status: 500 }
    )
  }
} 