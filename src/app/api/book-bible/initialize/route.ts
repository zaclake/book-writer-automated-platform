import { NextRequest, NextResponse } from 'next/server'

// Force dynamic rendering to prevent static generation issues
export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

/**
 * Proxy Book Bible initialization requests to the FastAPI backend.
 */
export async function POST(request: NextRequest) {
  console.log('[book-bible/initialize] Request started')
  
  try {
    // Debug: Log all headers
    console.log('[book-bible/initialize] Request headers:')
    request.headers.forEach((value, key) => {
      console.log(`  ${key}: ${value}`)
    })
    
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    console.log('[book-bible/initialize] Backend URL from env:', backendBaseUrl)
    
    if (!backendBaseUrl) {
      console.error('[book-bible/initialize] Backend URL not configured - NEXT_PUBLIC_BACKEND_URL not set')
      return NextResponse.json(
        { error: 'Backend URL not configured (NEXT_PUBLIC_BACKEND_URL missing)' },
        { status: 500 }
      )
    }

    const targetUrl = `${backendBaseUrl}/book-bible/initialize`
    console.log('[book-bible/initialize] Target URL:', targetUrl)

    // Get the request body
    const body = await request.json()
    console.log('[book-bible/initialize] Request body keys:', Object.keys(body))

    // Prepare headers for the backend request
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }

    // Forward the Authorization header if present
    const authHeader = request.headers.get('Authorization')
    console.log('[book-bible/initialize] Authorization header:', authHeader ? `${authHeader.substring(0, 30)}...` : 'MISSING')
    
    if (authHeader) {
      headers['Authorization'] = authHeader
      
      // Debug: Check JWT format
      if (authHeader.startsWith('Bearer ')) {
        const token = authHeader.substring(7)
        const parts = token.split('.')
        console.log('[book-bible/initialize] JWT parts count:', parts.length)
        console.log('[book-bible/initialize] JWT first part:', parts[0]?.substring(0, 20))
      }
    }

    console.log('[book-bible/initialize] Final headers for backend:', Object.keys(headers))

    // Make the request to the backend
    console.log('[book-bible/initialize] Making request to backend...')
    const response = await fetch(targetUrl, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    })

    console.log('[book-bible/initialize] Backend response status:', response.status)
    console.log('[book-bible/initialize] Backend response headers:')
    response.headers.forEach((value, key) => {
      console.log(`  ${key}: ${value}`)
    })

    if (!response.ok) {
      const errorText = await response.text()
      console.error('[book-bible/initialize] Backend error:', errorText)
      
      return NextResponse.json(
        { error: `Backend error: ${response.status} ${response.statusText}`, details: errorText },
        { status: response.status }
      )
    }

    const data = await response.json()
    console.log('[book-bible/initialize] Backend response data keys:', Object.keys(data))

    return NextResponse.json(data)

  } catch (error: any) {
    console.error('[book-bible/initialize] Unexpected error:', error)
    return NextResponse.json(
      { error: 'Internal Server Error', details: error.message },
      { status: 500 }
    )
  }
} 