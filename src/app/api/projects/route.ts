import { NextRequest, NextResponse } from 'next/server'
import { auth, currentUser } from '@clerk/nextjs/server'

export async function GET(request: NextRequest) {
  console.log('[projects] GET request started')
  
  try {
    // Use the correct Clerk auth pattern that works in other routes
    let userId: string | null = null
    let authToken: string | null = null
    
    try {
      const user = await currentUser()
      userId = user?.id || null
      console.log('[projects] Got user from currentUser():', !!userId)
      
      if (userId) {
        const { getToken } = await auth()
        authToken = await getToken()
        console.log('[projects] Got auth token:', !!authToken)
      }
    } catch (currentUserError) {
      console.log('[projects] currentUser() failed, trying auth():', currentUserError)
      try {
        const { userId: authUserId, getToken } = await auth()
        userId = authUserId
        if (getToken) {
          authToken = await getToken()
        }
        console.log('[projects] Got user from auth():', !!userId, !!authToken)
      } catch (authError) {
        console.error('[projects] Both auth methods failed:', authError)
      }
    }
    
    if (!userId) {
      console.error('[projects] No user ID found')
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    if (!authToken) {
      console.error('[projects] No auth token found')
      return NextResponse.json({ error: 'Failed to get auth token' }, { status: 401 })
    }

    // Get backend URL
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      console.error('[projects] Backend URL not configured')
      return NextResponse.json({ error: 'Backend URL not configured' }, { status: 500 })
    }

    console.log('[projects] Making request to backend:', `${backendBaseUrl}/v2/projects/`)

    // Get all projects for the user from backend
    const response = await fetch(`${backendBaseUrl}/v2/projects/`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${authToken}`
      },
      // Add timeout to prevent function timeout
      signal: AbortSignal.timeout(20000)
    })

    if (!response.ok) {
      const errorText = await response.text()
      console.error('[projects] Backend API error:', response.status, errorText)
      return NextResponse.json(
        { error: 'Failed to fetch projects' },
        { status: response.status }
      )
    }

    const result = await response.json()
    console.log('[projects] Backend response projects count:', result.projects?.length || 0)
    const projects = result.projects || []

    // Transform to match expected frontend format
    const userProjects = projects.map((project: any) => ({
      id: project.id,
      title: project.metadata?.title || project.title,
      genre: project.settings?.genre || 'Fiction',
      status: project.metadata?.status || 'active',
      created_at: project.metadata?.created_at,
      settings: project.settings,
      must_include_count: 0 // This would need to be stored/calculated properly
    }))

    console.log('[projects] Returning projects:', userProjects.length)

    return NextResponse.json({
      success: true,
      projects: userProjects,
      total: userProjects.length
    })

  } catch (error) {
    console.error('[projects] GET error:', error)
    
    // Handle timeout errors specifically
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