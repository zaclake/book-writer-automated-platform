import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(request: NextRequest) {
  try {
    console.log('[projects] === REQUEST START ===')
    
    // Get backend URL
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    console.log('[projects] Backend URL:', backendBaseUrl)
    
    if (!backendBaseUrl) {
      console.log('[projects] ERROR: Backend URL not configured')
      return NextResponse.json(
        { error: 'Backend URL not configured' },
        { status: 500 }
      )
    }

    // Get auth token from request headers
    const authHeader = request.headers.get('authorization')
    console.log('[projects] Auth header present:', !!authHeader)
    console.log('[projects] Auth header length:', authHeader?.length || 0)
    console.log('[projects] Auth header preview:', authHeader?.substring(0, 50) + '...')
    
    if (!authHeader) {
      console.log('[projects] ERROR: No authorization header')
      return NextResponse.json(
        { error: 'Authentication required' },
        { status: 401 }
      )
    }

    // Make request to backend
    const backendUrl = `${backendBaseUrl}/v2/projects/`
    console.log('[projects] Backend URL target:', backendUrl)
    
    console.log('[projects] Making backend request...')
    const backendResponse = await fetch(backendUrl, {
      method: 'GET',
      headers: {
        'Authorization': authHeader,
        'Content-Type': 'application/json'
      }
    })
    
    console.log('[projects] Backend response status:', backendResponse.status)
    console.log('[projects] Backend response ok:', backendResponse.ok)

    if (!backendResponse.ok) {
      const errorData = await backendResponse.text()
      console.error('[projects] Backend error:', errorData)
      
      // Forward X-Auth-Error header from backend for debugging
      const responseHeaders: Record<string, string> = {}
      const authError = backendResponse.headers.get('X-Auth-Error')
      if (authError) {
        responseHeaders['X-Auth-Error'] = authError
        console.error('[projects] Auth error from backend:', authError)
      }
      
      try {
        const errorJson = JSON.parse(errorData)
        return NextResponse.json(
          { error: errorJson.detail || 'Authentication failed' },
          { 
            status: backendResponse.status,
            headers: responseHeaders
          }
        )
      } catch {
        return NextResponse.json(
          { error: 'Authentication failed' },
          { 
            status: backendResponse.status,
            headers: responseHeaders
          }
        )
      }
    }

    const responseData = await backendResponse.json()
    console.log('[projects] Success! Returning data with', responseData?.length || 0, 'projects')
    return NextResponse.json(responseData)

  } catch (error) {
    console.error('[projects] Unexpected error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
} 