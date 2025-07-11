import { NextRequest, NextResponse } from 'next/server'

export async function GET(request: NextRequest) {
  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      return NextResponse.json(
        { error: 'Backend URL not configured' },
        { status: 500 }
      )
    }

    // Test basic connectivity to backend
    const response = await fetch(`${backendBaseUrl}/health`, {
      method: 'GET',
      cache: 'no-store'
    })

    const data = await response.json()
    
    return NextResponse.json({
      message: 'Backend connection test',
      backendUrl: backendBaseUrl,
      backendHealthy: response.ok,
      backendResponse: data,
      timestamp: new Date().toISOString()
    })
  } catch (error: any) {
    console.error('[test-backend] Error:', error)
    return NextResponse.json(
      { 
        error: 'Backend connection failed',
        details: error.message || 'Unknown error',
        timestamp: new Date().toISOString()
      },
      { status: 500 }
    )
  }
} 