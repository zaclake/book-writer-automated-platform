import { NextRequest, NextResponse } from 'next/server'

// Force dynamic rendering to prevent static generation issues
export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

/**
 * Proxy publishing job status requests to the FastAPI backend.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: { jobId: string } }
) {
  console.log('[v2/publish/status] 🔍 PUBLISH STATUS ROUTE HIT - Job ID:', params.jobId)
  console.log('[v2/publish/status] 🔍 Full URL:', request.url)
  console.log('[v2/publish/status] 🔍 Method:', request.method)
  
  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    console.log('[v2/publish/status] Backend URL from env:', backendBaseUrl)
    
    if (!backendBaseUrl) {
      console.error('[v2/publish/status] Backend URL not configured - NEXT_PUBLIC_BACKEND_URL not set')
      return NextResponse.json(
        { error: 'Backend URL not configured (NEXT_PUBLIC_BACKEND_URL missing)' },
        { status: 500 }
      )
    }

    const targetUrl = `${backendBaseUrl}/v2/publish/${params.jobId}`
    console.log('[v2/publish/status] Target URL:', targetUrl)

    // Prepare headers for the backend request
    const headers: Record<string, string> = {}

    // Forward the Authorization header if present
    const authHeader = request.headers.get('Authorization')
    console.log('[v2/publish/status] Authorization header:', authHeader ? 'present' : 'missing')
    
    if (authHeader) {
      headers['Authorization'] = authHeader
    } else {
      console.log('[v2/publish/status] No Authorization header found')
      return NextResponse.json(
        { error: 'Authentication token missing' },
        { status: 401 }
      )
    }

    // Make the request to the backend
    console.log('[v2/publish/status] Making request to backend...')
    const response = await fetch(targetUrl, {
      method: 'GET',
      headers
    })

    console.log('[v2/publish/status] Backend response status:', response.status)

    if (!response.ok) {
      const errorText = await response.text()
      console.error('[v2/publish/status] Backend error:', errorText)
      return NextResponse.json(
        { error: 'Backend request failed', details: errorText },
        { status: response.status }
      )
    }

    const result = await response.json()
    console.log('[v2/publish/status] Job status:', result.status)

    return NextResponse.json(result)

  } catch (error) {
    console.error('[v2/publish/status] Request failed:', error)
    return NextResponse.json(
      { error: 'Job status request failed', details: error instanceof Error ? error.message : String(error) },
      { status: 500 }
    )
  }
}
