import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

/**
 * Proxy project status requests to the FastAPI backend.
 */
export async function GET(request: NextRequest) {
  console.log('[project/status] Request started')
  
  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    console.log('[project/status] Backend URL from env:', backendBaseUrl)
    
    if (!backendBaseUrl) {
      console.error('[project/status] Backend URL not configured - NEXT_PUBLIC_BACKEND_URL not set')
      return NextResponse.json(
        { error: 'Backend URL not configured (NEXT_PUBLIC_BACKEND_URL missing)' },
        { status: 500 }
      )
    }

    const targetUrl = `${backendBaseUrl}/project/status`
    console.log('[project/status] Target URL:', targetUrl)

    const headers: Record<string, string> = {
      'Content-Type': 'application/json'
    }
    
    // Get Clerk auth and JWT token with better error handling
    console.log('[project/status] Getting authentication...')
    try {
      const authResult = await auth()
      console.log('[project/status] Auth result:', { userId: authResult?.userId })
      
      if (!authResult?.getToken) {
        console.log('[project/status] No getToken function available')
        return NextResponse.json(
          { error: 'Authentication service unavailable' },
          { status: 500 }
        )
      }
      
      const token = await authResult.getToken()
      console.log('[project/status] Token obtained:', { hasToken: !!token })
      
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
        console.log('[project/status] Authorization header added')
      } else {
        console.log('[project/status] No token available')
        return NextResponse.json(
          { error: 'Authentication token unavailable' },
          { status: 401 }
        )
      }
      
    } catch (authError) {
      console.error('[project/status] Authentication error:', authError)
      return NextResponse.json(
        { error: 'Authentication failed' },
        { status: 401 }
      )
    }

    // Get query parameters
    const url = new URL(request.url)
    const projectId = url.searchParams.get('project_id')
    
    // Add project_id to target URL if provided
    const fullTargetUrl = projectId ? `${targetUrl}?project_id=${projectId}` : targetUrl
    console.log('[project/status] Full target URL:', fullTargetUrl)

    // Make the request to the backend
    console.log('[project/status] Making request to backend...')
    const response = await fetch(fullTargetUrl, {
      method: 'GET',
      headers,
      // Prevent long-hanging proxies causing 504s
      signal: AbortSignal.timeout(15000),
      cache: 'no-store',
    })

    console.log('[project/status] Backend response status:', response.status)
    
    if (!response.ok) {
      const errorText = await response.text()
      console.error('[project/status] Backend error:', errorText)
      return NextResponse.json(
        { error: `Backend error: ${errorText}` },
        { status: response.status }
      )
    }

    const data = await response.json()
    console.log('[project/status] Success:', data)
    
    return NextResponse.json(data)

  } catch (error: any) {
    console.error('[project/status] Request failed:', error)
    return NextResponse.json(
      { error: `Status request failed: ${error.message}` },
      { status: 500 }
    )
  }
} 