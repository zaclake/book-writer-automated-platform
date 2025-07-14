import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

/**
 * Proxy reference file requests to the FastAPI backend.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: { filename: string } }
) {
  console.log('[references/filename] GET request started')

  try {
    const filename = params.filename
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
    const response = await fetch(targetUrl, {
      method: 'GET',
      headers,
    })

    console.log('[references/filename] Backend response status:', response.status)

    if (!response.ok) {
      const errorText = await response.text()
      console.error('[references/filename] Backend error:', errorText)

      return NextResponse.json(
        { error: `Backend error: ${response.status} ${response.statusText}`, details: errorText },
        { status: response.status }
      )
    }

    const data = await response.json()
    console.log('[references/filename] Backend response data keys:', Object.keys(data))

    return NextResponse.json(data)

  } catch (error: any) {
    console.error('[references/filename] Unexpected error:', error)
    return NextResponse.json(
      { error: 'Internal Server Error', details: error.message },
      { status: 500 }
    )
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: { filename: string } }
) {
  console.log('[references/filename] PUT request started')

  try {
    const filename = params.filename
    console.log('[references/filename] PUT Filename:', filename)

    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    console.log('[references/filename] PUT Backend URL from env:', backendBaseUrl)

    if (!backendBaseUrl) {
      console.error('[references/filename] PUT Backend URL not configured')
      return NextResponse.json(
        { error: 'Backend URL not configured' },
        { status: 500 }
      )
    }

    // Get the request body
    const body = await request.json()
    console.log('[references/filename] PUT Request body keys:', Object.keys(body))

    // Forward query parameters
    const searchParams = request.nextUrl.searchParams
    const queryString = searchParams.toString()
    const targetUrl = `${backendBaseUrl}/references/${filename}${queryString ? `?${queryString}` : ''}`
    console.log('[references/filename] PUT Target URL:', targetUrl)

    // Prepare headers for the backend request
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }

    // Forward the Authorization header if present
    const authHeader = request.headers.get('Authorization')
    console.log('[references/filename] PUT Authorization header:', authHeader ? `${authHeader.substring(0, 30)}...` : 'MISSING')

    if (authHeader) {
      headers['Authorization'] = authHeader
    }

    console.log('[references/filename] PUT Final headers for backend:', Object.keys(headers))

    // Make the request to the backend
    console.log('[references/filename] PUT Making request to backend...')
    const response = await fetch(targetUrl, {
      method: 'PUT',
      headers,
      body: JSON.stringify(body),
    })

    console.log('[references/filename] PUT Backend response status:', response.status)

    if (!response.ok) {
      const errorText = await response.text()
      console.error('[references/filename] PUT Backend error:', errorText)

      return NextResponse.json(
        { error: `Backend error: ${response.status} ${response.statusText}`, details: errorText },
        { status: response.status }
      )
    }

    const data = await response.json()
    console.log('[references/filename] PUT Backend response data keys:', Object.keys(data))

    return NextResponse.json(data)

  } catch (error: any) {
    console.error('[references/filename] PUT Unexpected error:', error)
    return NextResponse.json(
      { error: 'Internal Server Error', details: error.message },
      { status: 500 }
    )
  }
}