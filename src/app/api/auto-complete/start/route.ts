import { NextRequest, NextResponse } from 'next/server'
import { auth, currentUser } from '@clerk/nextjs/server'

// Force dynamic rendering
export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

interface AutoCompleteStartRequest {
  project_id: string
  book_bible: string
  starting_chapter?: number
  target_chapters?: number
  quality_threshold?: number
  words_per_chapter?: number
}

export async function POST(request: NextRequest) {
  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      return NextResponse.json(
        { error: 'Backend URL not configured (NEXT_PUBLIC_BACKEND_URL missing)' },
        { status: 500 }
      )
    }

    // Get Clerk auth and JWT token with early validation
    const { getToken } = await auth()
    const user = await currentUser()
    
    if (!user) {
      console.warn('[auto-complete/start] Unauthenticated request attempt')
      return NextResponse.json(
        { error: 'Authentication required. Please sign in to start auto-completion.' },
        { status: 401 }
      )
    }

    // Get token early to avoid unnecessary processing if auth fails
    let token: string | null = null
    try {
      token = await getToken()
      if (!token) {
        console.error('[auto-complete/start] Failed to get token for authenticated user')
        return NextResponse.json(
          { error: 'Authentication token could not be retrieved. Please try signing in again.' },
          { status: 401 }
        )
      }
    } catch (error) {
      console.error('[auto-complete/start] Token retrieval error:', error)
      return NextResponse.json(
        { error: 'Authentication failed. Please try signing in again.' },
        { status: 401 }
      )
    }

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'authorization': `Bearer ${token}`
    }

    // Parse request body for validation
    const requestData: AutoCompleteStartRequest = await request.json()
    
    // Validate required fields with detailed error messages
    if (!requestData.project_id) {
      console.warn('[auto-complete/start] Missing project_id in request')
      return NextResponse.json(
        { error: 'Project ID is required. Please select a project first.' },
        { status: 400 }
      )
    }

    if (!requestData.book_bible || requestData.book_bible.trim().length < 100) {
      console.warn('[auto-complete/start] Missing or insufficient book_bible content')
      return NextResponse.json(
        { error: 'Book Bible content is required and must be at least 100 characters. Please create a Book Bible first.' },
        { status: 400 }
      )
    }

    console.log(`[auto-complete/start] Starting job for user ${user.id}, project ${requestData.project_id}`)

    // Note: Budget check removed since estimated_total_cost is no longer in request
    // Budget validation will need to be handled in the backend or via separate estimation call

    // Check for existing running jobs (idempotency)
    try {
      const jobsResponse = await fetch(`${backendBaseUrl}/auto-complete/jobs?project_id=${requestData.project_id}`, {
        headers
      })

      if (jobsResponse.ok) {
        const jobsData = await jobsResponse.json()
        const runningJobs = jobsData.jobs?.filter((job: any) => 
          ['pending', 'running', 'generating'].includes(job.status)
        )

        if (runningJobs && runningJobs.length > 0) {
          return NextResponse.json(
            { 
              error: 'Job already running',
              details: `A job is already ${runningJobs[0].status} for this project`,
              existing_job_id: runningJobs[0].job_id
            },
            { status: 409 } // Conflict
          )
        }
      }
    } catch (jobCheckError) {
      console.warn('Job check failed, proceeding:', jobCheckError)
      // Don't block the request if job check fails
    }

    const targetUrl = `${backendBaseUrl}/auto-complete/start`

    // Forward the request to the backend
    const backendResponse = await fetch(targetUrl, {
      method: 'POST',
      headers,
      body: JSON.stringify(requestData),
      cache: 'no-store'
    })

    // Handle response parsing with fallback for non-JSON responses
    let data
    const contentType = backendResponse.headers.get('content-type')
    
    if (contentType && contentType.includes('application/json')) {
      try {
        data = await backendResponse.json()
      } catch (parseError) {
        console.error('[proxy] Failed to parse JSON response:', parseError)
        const textData = await backendResponse.text()
        data = { error: 'Invalid JSON response from backend', raw_response: textData }
      }
    } else {
      // Non-JSON response (likely HTML error page or plain text)
      const textData = await backendResponse.text()
      console.error('[proxy] Non-JSON response from backend:', textData)
      data = { error: 'Backend returned non-JSON response', raw_response: textData }
    }
    
    return NextResponse.json(data, { status: backendResponse.status })
  } catch (error: any) {
    console.error('[proxy] /api/auto-complete/start error:', error)
    return NextResponse.json(
      { error: error.message || 'Internal Server Error' },
      { status: 500 }
    )
  }
} 