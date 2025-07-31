import { NextRequest, NextResponse } from 'next/server'

export async function POST(request: NextRequest) {
  try {
    const requestBody = await request.json()

    // Validate required fields
    if (!requestBody.project_id || !requestBody.book_bible) {
      return NextResponse.json(
        { error: 'Project ID and book bible are required' },
        { status: 400 }
      )
    }

    // Get backend URL
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    
    if (!backendBaseUrl) {
      console.error('[auto-complete/estimate] Backend URL not configured')
      return NextResponse.json(
        { error: 'Backend URL not configured' },
        { status: 500 }
      )
    }

    const targetUrl = `${backendBaseUrl}/auto-complete/estimate`
    console.log('[auto-complete/estimate] Target URL:', targetUrl)

    // Prepare headers for the backend request
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }

    // Forward the Authorization header if present
    const authHeader = request.headers.get('Authorization')
    if (authHeader) {
      headers['Authorization'] = authHeader
    }

    console.log('[auto-complete/estimate] Request payload:', {
      ...requestBody,
      book_bible: requestBody.book_bible ? `${requestBody.book_bible.substring(0, 100)}... (${requestBody.book_bible.length} chars)` : 'undefined'
    })
    console.log('[auto-complete/estimate] Making request to backend')

    // Make the request to the backend
    const backendResponse = await fetch(targetUrl, {
      method: 'POST',
      headers,
      body: JSON.stringify(requestBody)
    })

    console.log('[auto-complete/estimate] Backend response status:', backendResponse.status)

    if (!backendResponse.ok) {
      const errorText = await backendResponse.text()
      console.error('[auto-complete/estimate] Backend error:', errorText)
      
      // Try to parse as JSON first, fall back to text
      let errorData
      try {
        errorData = JSON.parse(errorText)
        if (backendResponse.status === 422) {
          console.error('[auto-complete/estimate] Validation errors:', JSON.stringify(errorData, null, 2))
        }
      } catch {
        errorData = { detail: errorText }
      }
      
      return NextResponse.json(
        errorData,
        { status: backendResponse.status }
      )
    }

    const data = await backendResponse.json()
    console.log('[auto-complete/estimate] Backend success, returning data')

    return NextResponse.json(data)

  } catch (error: any) {
    console.error('[auto-complete/estimate] Request failed:', error)
    
    // Handle timeout errors
    if (error.message?.includes('timeout')) {
      return NextResponse.json(
        { error: 'Estimation timed out' },
        { status: 408 }
      )
    }

    return NextResponse.json(
      { error: `Estimation failed: ${error.message}` },
      { status: 500 }
    )
  }
} 