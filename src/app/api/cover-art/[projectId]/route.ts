import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

interface RouteParams {
  params: {
    projectId: string
  }
}

export async function POST(
  request: Request,
  { params }: { params: { projectId: string } }
) {
  try {
    const { projectId } = params
    const body = await request.json()
    
    // Get auth token
    const authHeader = request.headers.get('authorization')
    if (!authHeader?.startsWith('Bearer ')) {
      return NextResponse.json(
        { error: 'Authorization header required' },
        { status: 401 }
      )
    }

    const token = authHeader.substring(7)
    
    console.log('Cover art generation request:', { projectId, body })
    
    // Forward to backend
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'
    const response = await fetch(`${backendUrl}/v2/projects/${projectId}/cover-art`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(body)
    })

    if (!response.ok) {
      const errorText = await response.text()
      console.error('Backend cover art generation error:', response.status, errorText)
      return NextResponse.json(
        { error: 'Failed to start cover art generation', details: errorText },
        { status: response.status }
      )
    }

    const data = await response.json()
    console.log('Cover art generation response from backend:', data)
    return NextResponse.json(data)

  } catch (error) {
    console.error('Cover art generation API error:', error)
    return NextResponse.json(
      { error: 'Internal server error', details: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    )
  }
}

export async function GET(
  request: Request,
  { params }: { params: { projectId: string } }
) {
  try {
    const { projectId } = params
    
    // Get auth token
    const authHeader = request.headers.get('authorization')
    if (!authHeader?.startsWith('Bearer ')) {
      return NextResponse.json(
        { error: 'Authorization header required' },
        { status: 401 }
      )
    }

    const token = authHeader.substring(7)
    
    // Forward to backend
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'
    const response = await fetch(`${backendUrl}/v2/projects/${projectId}/cover-art`, {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    })

    if (!response.ok) {
      const errorText = await response.text()
      console.error('Backend cover art status error:', response.status, errorText)
      return NextResponse.json(
        { error: 'Failed to get cover art status', details: errorText },
        { status: response.status }
      )
    }

    const data = await response.json()
    console.log('Cover art status from backend:', data)
    return NextResponse.json(data)

  } catch (error) {
    console.error('Cover art status API error:', error)
    return NextResponse.json(
      { error: 'Internal server error', details: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    )
  }
}

export async function DELETE(
  request: Request,
  { params }: { params: { projectId: string } }
) {
  try {
    const { projectId } = params
    const body = await request.json()
    const { jobId } = body
    
    if (!jobId) {
      return NextResponse.json(
        { error: 'Job ID is required for deletion' },
        { status: 400 }
      )
    }
    
    // Get auth token
    const authHeader = request.headers.get('authorization')
    if (!authHeader?.startsWith('Bearer ')) {
      return NextResponse.json(
        { error: 'Authorization header required' },
        { status: 401 }
      )
    }

    const token = authHeader.substring(7)
    
    console.log('Cover art deletion request:', { projectId, jobId })
    
    // Forward to backend
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'
    const response = await fetch(`${backendUrl}/v2/projects/${projectId}/cover-art/${jobId}`, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    })

    if (!response.ok) {
      const errorText = await response.text()
      console.error('Backend cover art deletion error:', response.status, errorText)
      return NextResponse.json(
        { error: 'Failed to delete cover art', details: errorText },
        { status: response.status }
      )
    }

    const data = await response.json()
    console.log('Cover art deletion response from backend:', data)
    return NextResponse.json(data)

  } catch (error) {
    console.error('Cover art deletion API error:', error)
    return NextResponse.json(
      { error: 'Internal server error', details: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    )
  }
} 