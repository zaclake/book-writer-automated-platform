import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

/**
 * Proxy Book Bible upload requests to the FastAPI backend.
 */
export async function POST(request: NextRequest) {
  console.log('[book-bible/upload] Request started')
  
  try {
    const backendBaseUrl = (process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL)?.trim()
    console.log('[book-bible/upload] Backend URL from env:', backendBaseUrl)
    
    if (!backendBaseUrl) {
      console.error('[book-bible/upload] Backend URL not configured - neither BACKEND_URL nor NEXT_PUBLIC_BACKEND_URL set')
      return NextResponse.json(
        { error: 'Backend URL not configured (BACKEND_URL or NEXT_PUBLIC_BACKEND_URL missing)' },
        { status: 500 }
      )
    }

    const targetUrl = `${backendBaseUrl}/book-bible/upload`
    console.log('[book-bible/upload] Target URL:', targetUrl)

    const headers: Record<string, string> = {
      'Content-Type': 'application/json'
    }
    
    // Get Clerk auth and JWT token with better error handling
    console.log('[book-bible/upload] Getting authentication...')
    try {
      const authResult = await auth()
      console.log('[book-bible/upload] Auth result:', { userId: authResult?.userId })
      
      if (!authResult?.getToken) {
        console.log('[book-bible/upload] No getToken function available')
        return NextResponse.json(
          { error: 'Authentication service unavailable' },
          { status: 500 }
        )
      }
      
      const token = await authResult.getToken()
      console.log('[book-bible/upload] Token obtained:', { hasToken: !!token })
      
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
        console.log('[book-bible/upload] Authorization header added')
      } else {
        console.log('[book-bible/upload] No token available')
        return NextResponse.json(
          { error: 'Authentication token unavailable' },
          { status: 401 }
        )
      }
      
    } catch (authError) {
      console.error('[book-bible/upload] Authentication error:', authError)
      return NextResponse.json(
        { error: 'Authentication failed' },
        { status: 401 }
      )
    }

    // Get the request body
    const body = await request.json()
    console.log('[book-bible/upload] Request body keys:', Object.keys(body))

    // Make the request to the backend
    console.log('[book-bible/upload] Making request to backend...')
    const response = await fetch(targetUrl, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    })

    console.log('[book-bible/upload] Backend response status:', response.status)
    
    if (!response.ok) {
      const errorText = await response.text()
      console.error('[book-bible/upload] Backend error:', errorText)
      return NextResponse.json(
        { error: `Backend error: ${errorText}` },
        { status: response.status }
      )
    }

    const data = await response.json()
    console.log('[book-bible/upload] Success:', data)
    
    return NextResponse.json(data)

  } catch (error: any) {
    console.error('[book-bible/upload] Request failed:', error)
    return NextResponse.json(
      { error: `Upload failed: ${error.message}` },
      { status: 500 }
    )
  }
} 