import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

/**
 * Proxy reference file requests to the FastAPI backend.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: { filename: string[] } }
) {
  console.log('[references/filename] GET request started')

  try {
    const filename = params.filename.join('/')
    console.log('[references/filename] Filename:', filename)

    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    console.log('[references/filename] Backend URL from env:', backendBaseUrl)

    if (!backendBaseUrl) {
      console.error('[references/filename] Backend URL not configured')
      return NextResponse.json(
        { error: 'Backend URL not configured' },
        { status: 500 }
      )
    }

    // Forward query parameters
    const searchParams = request.nextUrl.searchParams
    const queryString = searchParams.toString()
    const targetUrl = `${backendBaseUrl}/references/${filename}${queryString ? `?${queryString}` : ''}`
    console.log('[references/filename] Target URL:', targetUrl)

    // Prepare headers for the backend request
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }

    // Forward the Authorization header if present
    const authHeader = request.headers.get('Authorization')
    console.log('[references/filename] Authorization header:', authHeader ? `${authHeader.substring(0, 30)}...` : 'MISSING')

    if (authHeader) {
      headers['Authorization'] = authHeader
    }

    // Make the request to the backend
    console.log('[references/filename] Making request to backend...')
    const backendResponse = await fetch(targetUrl, {
      method: 'GET',
      headers
    })

    console.log('[references/filename] Backend response status:', backendResponse.status)

    if (!backendResponse.ok) {
      const errorText = await backendResponse.text()
      console.error('[references/filename] Backend error:', errorText)
      return NextResponse.json(
        { error: `Backend error: ${backendResponse.status}` },
        { status: backendResponse.status }
      )
    }

    const data = await backendResponse.json()
    console.log('[references/filename] Success, returning data')

    return NextResponse.json(data, {
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
      }
    })

  } catch (error) {
    console.error('[references/filename] Request failed:', error)
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

export async function PUT(
  request: NextRequest,
  { params }: { params: { filename: string[] } }
) {
  console.log('[references/filename] PUT request started')

  try {
    const filename = params.filename.join('/')
    console.log('[references/filename] Filename:', filename)

    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    console.log('[references/filename] Backend URL from env:', backendBaseUrl)

    if (!backendBaseUrl) {
      console.error('[references/filename] Backend URL not configured')
      return NextResponse.json(
        { error: 'Backend URL not configured' },
        { status: 500 }
      )
    }

    // Get the request body
    const body = await request.json()
    console.log('[references/filename] Request body keys:', Object.keys(body))

    // Forward query parameters
    const searchParams = request.nextUrl.searchParams
    const queryString = searchParams.toString()
    const targetUrl = `${backendBaseUrl}/references/${filename}${queryString ? `?${queryString}` : ''}`
    console.log('[references/filename] Target URL:', targetUrl)

    // Prepare headers for the backend request
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }

    // Forward the Authorization header if present
    const authHeader = request.headers.get('Authorization')
    console.log('[references/filename] Authorization header:', authHeader ? `${authHeader.substring(0, 30)}...` : 'MISSING')

    if (authHeader) {
      headers['Authorization'] = authHeader
    }

    // Make the request to the backend
    console.log('[references/filename] Making PUT request to backend...')
    const backendResponse = await fetch(targetUrl, {
      method: 'PUT',
      headers,
      body: JSON.stringify(body)
    })

    console.log('[references/filename] Backend response status:', backendResponse.status)

    if (!backendResponse.ok) {
      const errorText = await backendResponse.text()
      console.error('[references/filename] Backend error:', errorText)
      return NextResponse.json(
        { error: `Backend error: ${backendResponse.status}` },
        { status: backendResponse.status }
      )
    }

    const data = await backendResponse.json()
    console.log('[references/filename] PUT success, returning data')

    return NextResponse.json(data, {
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
      }
    })

  } catch (error) {
    console.error('[references/filename] PUT request failed:', error)
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