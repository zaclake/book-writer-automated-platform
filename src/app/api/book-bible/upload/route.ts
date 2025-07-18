import { NextRequest, NextResponse } from 'next/server'

// Force dynamic rendering to prevent static generation issues
export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

/**
 * Proxy Book Bible upload requests to the FastAPI backend.
 */
export async function POST(request: NextRequest) {
  console.log('[book-bible/upload] Request started')
  
  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    console.log('[book-bible/upload] Backend URL from env:', backendBaseUrl)
    
    if (!backendBaseUrl) {
      console.error('[book-bible/upload] Backend URL not configured - NEXT_PUBLIC_BACKEND_URL not set')
      return NextResponse.json(
        { error: 'Backend URL not configured (NEXT_PUBLIC_BACKEND_URL missing)' },
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
      const authHeader = request.headers.get('Authorization')
      if (!authHeader) {
        console.log('[book-bible/upload] No Authorization header found')
        return NextResponse.json(
          { error: 'Authentication token missing' },
          { status: 401 }
        )
      }
      
      const token = authHeader.replace('Bearer ', '')
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
    console.log('[book-bible/upload] Streaming body to backend...')
    const textBody = await request.text()
    const response = await fetch(targetUrl, {
      method: 'POST',
      headers,
      body: textBody
    })

    console.log('[book-bible/upload] Backend response status:', response.status)
    const contentType = response.headers.get('content-type') || ''
    if (!response.ok) {
      const errText = await response.text()
      console.error('[book-bible/upload] Backend error:', errText)
      return NextResponse.json({ error: errText }, { status: response.status })
    }

    let payload: any
    if (contentType.includes('application/json')) {
      payload = await response.json()
    } else {
      payload = { message: await response.text() }
    }

    console.log('[book-bible/upload] Success:', payload)
    return NextResponse.json(payload)

  } catch (error: any) {
    console.error('[book-bible/upload] Request failed:', error)
    return NextResponse.json(
      { error: `Upload failed: ${error.message}` },
      { status: 500 }
    )
  }
} 