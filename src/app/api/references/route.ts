import { NextRequest, NextResponse } from 'next/server'

// Force dynamic rendering/runtime so we can access the filesystem at request time
export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

/**
 * Proxy reference files list requests to the FastAPI backend.
 */
export async function GET(request: NextRequest) {
  console.log('[references] Request started')

  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    console.log('[references] Backend URL from env:', backendBaseUrl)

    if (!backendBaseUrl) {
      console.error('[references] Backend URL not configured - NEXT_PUBLIC_BACKEND_URL not set')
      return NextResponse.json(
        { error: 'Backend URL not configured (NEXT_PUBLIC_BACKEND_URL missing)' },
        { status: 500 }
      )
    }

    // Forward query parameters
    const searchParams = request.nextUrl.searchParams
    const queryString = searchParams.toString()
    const targetUrl = `${backendBaseUrl}/references${queryString ? `?${queryString}` : ''}`
    console.log('[references] Target URL:', targetUrl)

    // Prepare headers for the backend request
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }

    // Forward the Authorization header if present
    const authHeader = request.headers.get('Authorization')
    console.log('[references] Authorization header:', authHeader ? `${authHeader.substring(0, 30)}...` : 'MISSING')

    if (authHeader) {
      headers['Authorization'] = authHeader
    }

    console.log('[references] Final headers for backend:', Object.keys(headers))

    // Make the request to the backend
    console.log('[references] Making request to backend...')
    const response = await fetch(targetUrl, {
      method: 'GET',
      headers,
    })

    console.log('[references] Backend response status:', response.status)
    console.log('[references] Backend response headers:')
    response.headers.forEach((value, key) => {
      console.log(`  ${key}: ${value}`)
    })

    if (!response.ok) {
      const errorText = await response.text()
      console.error('[references] Backend error:', errorText)

      return NextResponse.json(
        { error: `Backend error: ${response.status} ${response.statusText}`, details: errorText },
        { status: response.status }
      )
    }

    const data = await response.json()
    console.log('[references] Backend response data keys:', Object.keys(data))

    return NextResponse.json(data)

  } catch (error: any) {
    console.error('[references] Unexpected error:', error)
    return NextResponse.json(
      { error: 'Internal Server Error', details: error.message },
      { status: 500 }
    )
  }
}

/**
 * Proxy reference generation requests to the FastAPI backend.
 */
export async function POST(request: NextRequest) {
  console.log('[references] POST request started')

  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    console.log('[references] Backend URL from env:', backendBaseUrl)

    if (!backendBaseUrl) {
      console.error('[references] Backend URL not configured - NEXT_PUBLIC_BACKEND_URL not set')
      return NextResponse.json(
        { error: 'Backend URL not configured (NEXT_PUBLIC_BACKEND_URL missing)' },
        { status: 500 }
      )
    }

    // Get the request body
    const body = await request.json()
    console.log('[references] Request body keys:', Object.keys(body))

    const targetUrl = `${backendBaseUrl}/references/generate`
    console.log('[references] Target URL:', targetUrl)

    // Prepare headers for the backend request
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }

    // Forward the Authorization header if present
    const authHeader = request.headers.get('Authorization')
    console.log('[references] Authorization header:', authHeader ? `${authHeader.substring(0, 30)}...` : 'MISSING')

    if (authHeader) {
      headers['Authorization'] = authHeader
    }

    console.log('[references] Final headers for backend:', Object.keys(headers))

    // Make the request to the backend
    console.log('[references] Making POST request to backend...')
    const response = await fetch(targetUrl, {
      method: 'POST',
      headers,
      body: JSON.stringify(body)
    })

    console.log('[references] Backend response status:', response.status)

    if (!response.ok) {
      const errorText = await response.text()
      console.error('[references] Backend error:', errorText)
      
      // Try to parse as JSON first, fall back to text
      let errorData
      try {
        errorData = JSON.parse(errorText)
      } catch {
        errorData = { detail: errorText }
      }
      
      return NextResponse.json(
        errorData,
        { status: response.status }
      )
    }

    const data = await response.json()
    console.log('[references] POST success, returning data')

    return NextResponse.json(data, {
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
      }
    })

  } catch (error) {
    console.error('[references] POST request failed:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500, headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
      }}
    )
  }
} 