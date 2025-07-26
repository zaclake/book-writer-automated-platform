import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

interface RouteParams {
  params: {
    projectId: string
  }
}

export async function GET(request: NextRequest, { params }: RouteParams) {
  try {
    const { projectId } = params

    if (!projectId) {
      return NextResponse.json(
        { error: 'Project ID is required' },
        { status: 400 }
      )
    }

    // Get backend URL
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      return NextResponse.json(
        { error: 'Backend URL not configured' },
        { status: 500 }
      )
    }

    // Get auth token from request headers
    const authHeader = request.headers.get('authorization')
    if (!authHeader) {
      return NextResponse.json(
        { error: 'Authentication required' },
        { status: 401 }
      )
    }

    // Make request to backend
    const backendUrl = `${backendBaseUrl}/v2/projects/${projectId}/references/progress`
    
    const backendResponse = await fetch(backendUrl, {
      method: 'GET',
      headers: {
        'Authorization': authHeader,
        'Content-Type': 'application/json'
      }
    })

    if (!backendResponse.ok) {
      const errorData = await backendResponse.text()
      console.error('[progress] Backend error:', errorData)
      
      try {
        const errorJson = JSON.parse(errorData)
        return NextResponse.json(
          { error: errorJson.detail || 'Failed to get progress' },
          { status: backendResponse.status }
        )
      } catch {
        return NextResponse.json(
          { error: 'Failed to get progress' },
          { status: backendResponse.status }
        )
      }
    }

    const responseData = await backendResponse.json()
    return NextResponse.json(responseData)

  } catch (error) {
    console.error('[progress] Error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
} 