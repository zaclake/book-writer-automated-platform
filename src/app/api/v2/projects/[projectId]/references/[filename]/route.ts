import { NextRequest, NextResponse } from 'next/server'
import { auth, currentUser } from '@clerk/nextjs/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

/**
 * Proxy v2 project reference file requests to the FastAPI backend.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: { projectId: string; filename: string } }
) {
  console.log('[v2/projects/references] GET request started')

  try {
    const { projectId, filename } = params
    console.log('[v2/projects/references] ProjectId:', projectId, 'Filename:', filename)

    // Get auth token
    let authToken: string | null = null
    try {
      const user = await currentUser()
      if (user?.id) {
        const { getToken } = await auth()
        authToken = await getToken()
      }
    } catch (error) {
      console.error('[v2/projects/references] Auth error:', error)
    }

    if (!authToken) {
      console.error('[v2/projects/references] No auth token found')
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      console.error('[v2/projects/references] Backend URL not configured')
      return NextResponse.json(
        { error: 'Backend URL not configured' },
        { status: 500 }
      )
    }

    const targetUrl = `${backendBaseUrl}/v2/projects/${projectId}/references/${filename}`
    console.log('[v2/projects/references] Target URL:', targetUrl)

    // Make the request to the backend
    const response = await fetch(targetUrl, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json'
      },
      signal: AbortSignal.timeout(30000)
    })

    console.log('[v2/projects/references] Backend response status:', response.status)

    if (!response.ok) {
      const errorText = await response.text()
      console.error('[v2/projects/references] Backend error:', errorText)
      return NextResponse.json(
        { error: `Backend error: ${response.status}` },
        { status: response.status }
      )
    }

    const data = await response.json()
    console.log('[v2/projects/references] Success, returning data')

    return NextResponse.json(data, {
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
      }
    })

  } catch (error) {
    console.error('[v2/projects/references] Request failed:', error)
    
    if (error instanceof Error && error.name === 'AbortError') {
      return NextResponse.json(
        { error: 'Request timeout - please try again' },
        { status: 408 }
      )
    }
    
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: { projectId: string; filename: string } }
) {
  console.log('[v2/projects/references] PUT request started')

  try {
    const { projectId, filename } = params
    console.log('[v2/projects/references] ProjectId:', projectId, 'Filename:', filename)

    // Get request body
    const body = await request.json()
    console.log('[v2/projects/references] Request body keys:', Object.keys(body))

    // Get auth token
    let authToken: string | null = null
    try {
      const user = await currentUser()
      if (user?.id) {
        const { getToken } = await auth()
        authToken = await getToken()
      }
    } catch (error) {
      console.error('[v2/projects/references] Auth error:', error)
    }

    if (!authToken) {
      console.error('[v2/projects/references] No auth token found')
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      console.error('[v2/projects/references] Backend URL not configured')
      return NextResponse.json(
        { error: 'Backend URL not configured' },
        { status: 500 }
      )
    }

    const targetUrl = `${backendBaseUrl}/v2/projects/${projectId}/references/${filename}`
    console.log('[v2/projects/references] Target URL:', targetUrl)

    // Make the request to the backend
    const response = await fetch(targetUrl, {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(30000)
    })

    console.log('[v2/projects/references] Backend response status:', response.status)

    if (!response.ok) {
      const errorText = await response.text()
      console.error('[v2/projects/references] Backend error:', errorText)
      return NextResponse.json(
        { error: `Backend error: ${response.status}` },
        { status: response.status }
      )
    }

    const data = await response.json()
    console.log('[v2/projects/references] PUT success, returning data')

    return NextResponse.json(data)

  } catch (error) {
    console.error('[v2/projects/references] PUT request failed:', error)
    
    if (error instanceof Error && error.name === 'AbortError') {
      return NextResponse.json(
        { error: 'Request timeout - please try again' },
        { status: 408 }
      )
    }
    
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}

export async function OPTIONS(
  request: NextRequest,
  { params }: { params: { projectId: string; filename: string } }
) {
  return NextResponse.json({
    message: 'Route is accessible'
  }, {
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    }
  })
} 