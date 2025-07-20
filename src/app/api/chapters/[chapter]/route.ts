import { NextRequest, NextResponse } from 'next/server'

export async function GET(
  request: NextRequest,
  { params }: { params: { chapter: string } }
) {
  try {
    const chapterNumber = parseInt(params.chapter)
    
    if (isNaN(chapterNumber) || chapterNumber < 1) {
      return NextResponse.json(
        { error: 'Invalid chapter number' },
        { status: 400 }
      )
    }

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
      console.error('[chapters/{chapter}] Backend URL not configured')
      return NextResponse.json(
        { error: 'Backend URL not configured' },
        { status: 500 }
      )
    }

    const targetUrl = `${backendBaseUrl}/v2/chapters/project/${encodeURIComponent(projectId)}/chapter/${chapterNumber}`
    console.log('[chapters/{chapter}] Target URL:', targetUrl)

    // Prepare headers for the backend request
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }

    // Forward the Authorization header if present
    const authHeader = request.headers.get('Authorization')
    if (authHeader) {
      headers['Authorization'] = authHeader
    }

    console.log('[chapters/{chapter}] Making request to backend')

    // Make the request to the backend
    const backendResponse = await fetch(targetUrl, {
      method: 'GET',
      headers
    })

    console.log('[chapters/{chapter}] Backend response status:', backendResponse.status)

    if (!backendResponse.ok) {
      const errorText = await backendResponse.text()
      console.error('[chapters/{chapter}] Backend error:', errorText)
      
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
    console.log('[chapters/{chapter}] Backend success, returning data')

    return NextResponse.json(data)

  } catch (error: any) {
    console.error('[chapters/{chapter}] Request failed:', error)
    return NextResponse.json(
      { error: `Failed to get chapter: ${error.message}` },
      { status: 500 }
    )
  }
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: { chapter: string } }
) {
  try {
    const chapterNumber = parseInt(params.chapter)
    
    if (isNaN(chapterNumber) || chapterNumber < 1) {
      return NextResponse.json(
        { error: 'Invalid chapter number' },
        { status: 400 }
      )
    }

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
      console.error('[chapters/{chapter}] Backend URL not configured')
      return NextResponse.json(
        { error: 'Backend URL not configured' },
        { status: 500 }
      )
    }

    const targetUrl = `${backendBaseUrl}/v2/chapters/project/${encodeURIComponent(projectId)}/chapter/${chapterNumber}`
    console.log('[chapters/{chapter}] Delete Target URL:', targetUrl)

    // Prepare headers for the backend request
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }

    // Forward the Authorization header if present
    const authHeader = request.headers.get('Authorization')
    if (authHeader) {
      headers['Authorization'] = authHeader
    }

    console.log('[chapters/{chapter}] Making delete request to backend')

    // Make the request to the backend
    const backendResponse = await fetch(targetUrl, {
      method: 'DELETE',
      headers
    })

    console.log('[chapters/{chapter}] Backend delete response status:', backendResponse.status)

    if (!backendResponse.ok) {
      const errorText = await backendResponse.text()
      console.error('[chapters/{chapter}] Backend delete error:', errorText)
      
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
    console.log('[chapters/{chapter}] Backend delete success, returning data')

    return NextResponse.json(data)

  } catch (error: any) {
    console.error('[chapters/{chapter}] Delete request failed:', error)
    return NextResponse.json(
      { error: `Failed to delete chapter: ${error.message}` },
      { status: 500 }
    )
  }
} 