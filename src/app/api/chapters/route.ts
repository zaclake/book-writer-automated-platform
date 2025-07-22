import { NextRequest, NextResponse } from 'next/server'

export async function GET(request: NextRequest) {
  try {
    // Get project ID from query parameters
    const url = new URL(request.url)
    const projectId = url.searchParams.get('project_id')
    
    if (!projectId) {
      return NextResponse.json(
        { error: 'Project ID is required' },
        { status: 400 }
      )
    }

    // Get backend URL
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    
    if (!backendBaseUrl) {
      console.error('[chapters] Backend URL not configured')
      return NextResponse.json(
        { error: 'Backend URL not configured' },
        { status: 500 }
      )
    }

    const targetUrl = `${backendBaseUrl}/v1/chapters?project_id=${encodeURIComponent(projectId)}`
    console.log('[chapters] Target URL:', targetUrl)

    // Prepare headers for the backend request
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }

    // Forward the Authorization header if present
    const authHeader = request.headers.get('Authorization')
    if (authHeader) {
      headers['Authorization'] = authHeader
    }

    console.log('[chapters] Making request to backend')

    // Make the request to the backend
    const backendResponse = await fetch(targetUrl, {
      method: 'GET',
      headers,
      // Add timeout to prevent Vercel function timeout
      signal: AbortSignal.timeout(20000) // 20 seconds
    })

    console.log('[chapters] Backend response status:', backendResponse.status)

    if (!backendResponse.ok) {
      const errorText = await backendResponse.text()
      console.error('[chapters] Backend error:', errorText)
      
      // Try to parse as JSON first, fall back to text
      let errorData
      try {
        errorData = JSON.parse(errorText)
      } catch {
        errorData = { detail: errorText }
      }
      
      return NextResponse.json(
        errorData,
        { status: backendResponse.status }
      )
    }

    const data = await backendResponse.json()
    console.log('[chapters] Backend success, returning data')

    return NextResponse.json(data)

  } catch (error: any) {
    console.error('[chapters] Request failed:', error)
    
    // Handle timeout errors specifically
    if (error instanceof Error && error.name === 'AbortError') {
      return NextResponse.json(
        { error: 'Request timeout - please try again' },
        { status: 408 }
      )
    }
    
    return NextResponse.json(
      { error: `Failed to list chapters: ${error.message}` },
      { status: 500 }
    )
  }
} 