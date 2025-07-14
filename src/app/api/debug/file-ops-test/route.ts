import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

/**
 * Test file operations on Railway deployment
 */
export async function GET(request: NextRequest) {
  console.log('[file-ops-test] Request started')
  
  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    console.log('[file-ops-test] Backend URL:', backendBaseUrl)
    
    if (!backendBaseUrl) {
      return NextResponse.json(
        { error: 'Backend URL not configured' },
        { status: 500 }
      )
    }

    const targetUrl = `${backendBaseUrl}/debug/test-file-ops`
    console.log('[file-ops-test] Target URL:', targetUrl)

    // Make request to backend (no auth required for debug endpoint)
    const response = await fetch(targetUrl, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json'
      }
    })

    console.log('[file-ops-test] Backend response status:', response.status)
    
    if (!response.ok) {
      const errorText = await response.text()
      console.error('[file-ops-test] Backend error:', errorText)
      return NextResponse.json(
        { error: `Backend error: ${errorText}` },
        { status: response.status }
      )
    }

    const data = await response.json()
    console.log('[file-ops-test] Success:', data)
    
    return NextResponse.json(data)

  } catch (error: any) {
    console.error('[file-ops-test] Request failed:', error)
    return NextResponse.json(
      { error: `File ops test failed: ${error.message}` },
      { status: 500 }
    )
  }
} 