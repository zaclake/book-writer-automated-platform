import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(
  request: NextRequest,
  { params }: { params: { projectId: string } }
) {
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
        { error: 'Authorization header required' },
        { status: 401 }
      )
    }

    console.log(`[References API] Fetching references for project: ${projectId}`)

    // Make request to backend
    const response = await fetch(`${backendBaseUrl}/v2/projects/${projectId}/references`, {
      method: 'GET',
      headers: {
        'Authorization': authHeader,
        'Content-Type': 'application/json',
      },
    })

    console.log(`[References API] Backend response status: ${response.status}`)

    if (!response.ok) {
      const errorText = await response.text()
      console.error(`[References API] Backend error: ${response.status} - ${errorText}`)
      
      if (response.status === 404) {
        // Project not found - return empty array instead of error
        return NextResponse.json([])
      }
      
      return NextResponse.json(
        { error: `Backend error: ${response.status}` },
        { status: response.status }
      )
    }

    const data = await response.json()
    console.log(`[References API] Backend response:`, data)

    // Backend returns { success: true, files: [...], total: number }
    // Frontend expects just the array of files
    const referenceFiles = data.files || []
    
    console.log(`[References API] Returning ${referenceFiles.length} reference files`)
    return NextResponse.json(referenceFiles)

  } catch (error) {
    console.error('[References API] Error:', error)
    return NextResponse.json(
      { error: 'Failed to fetch references' },
      { status: 500 }
    )
  }
} 