import { NextRequest, NextResponse } from 'next/server'
import { auth, currentUser } from '@clerk/nextjs/server'

// Force dynamic rendering
export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

interface AutoCompleteStartRequest {
  project_id: string
  config: any
  book_bible: any
  estimated_total_cost?: number
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

    // Get Clerk auth and JWT token
    const { getToken } = await auth()
    const user = await currentUser()
    
    if (!user) {
      return NextResponse.json(
        { error: 'Authentication required' },
        { status: 401 }
      )
    }

    const headers: Record<string, string> = {
      'Content-Type': 'application/json'
    }
    
    try {
      const token = await getToken()
      if (token) {
        headers['authorization'] = `Bearer ${token}`
      }
    } catch (error) {
      console.error('Failed to get Clerk token:', error)
      return NextResponse.json(
        { error: 'Authentication failed' },
        { status: 401 }
      )
    }

    // Parse request body for validation
    const requestData: AutoCompleteStartRequest = await request.json()
    
    // Validate required fields
    if (!requestData.project_id) {
      return NextResponse.json(
        { error: 'Project ID is required' },
        { status: 400 }
      )
    }

    // Check user's budget if estimated cost is provided
    if (requestData.estimated_total_cost && requestData.estimated_total_cost > 0) {
      try {
        // Fetch user's current usage and limits
        const baseUrl = process.env.NODE_ENV === 'production' 
          ? `https://${process.env.VERCEL_URL || 'your-domain.com'}`
          : 'http://localhost:3000'
        const usageResponse = await fetch(`${baseUrl}/api/users/v2/usage`, {
          headers: {
            'Authorization': `Bearer ${await getToken()}`,
            'Content-Type': 'application/json'
          }
        })

        if (usageResponse.ok) {
          const usageData = await usageResponse.json()
          const remainingBudget = usageData.remaining?.monthly_cost_remaining || 0

          if (requestData.estimated_total_cost > remainingBudget) {
            return NextResponse.json(
              { 
                error: 'Insufficient budget',
                details: `Estimated cost $${requestData.estimated_total_cost} exceeds remaining budget $${remainingBudget.toFixed(2)}`,
                estimated_cost: requestData.estimated_total_cost,
                remaining_budget: remainingBudget
              },
              { status: 402 } // Payment Required
            )
          }
        }
      } catch (budgetError) {
        console.warn('Budget check failed, proceeding with caution:', budgetError)
        // Don't block the request if budget check fails, but log it
      }
    }

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

    const data = await backendResponse.json()
    return NextResponse.json(data, { status: backendResponse.status })
  } catch (error: any) {
    console.error('[proxy] /api/auto-complete/start error:', error)
    return NextResponse.json(
      { error: error.message || 'Internal Server Error' },
      { status: 500 }
    )
  }
} 