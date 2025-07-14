import { NextRequest, NextResponse } from 'next/server'

export async function GET(request: NextRequest) {
  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    
    if (!backendBaseUrl) {
      return NextResponse.json(
        { error: 'Backend URL not configured (NEXT_PUBLIC_BACKEND_URL missing)' },
        { status: 500 }
      )
    }

    const testUrl = `${backendBaseUrl}/status`
    
    const response = await fetch(testUrl, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json'
      }
    })

    if (!response.ok) {
      return NextResponse.json(
        { 
          error: `Backend test failed: ${response.status} ${response.statusText}`,
          backend_url: backendBaseUrl
        },
        { status: response.status }
      )
    }

    const data = await response.json()
    
    return NextResponse.json({
      success: true,
      message: 'Backend connection successful',
      backend_url: backendBaseUrl,
      backend_response: data
    })
    
  } catch (error: any) {
    return NextResponse.json(
      { 
        error: `Backend test error: ${error.message}`,
        backend_url: process.env.NEXT_PUBLIC_BACKEND_URL
      },
      { status: 500 }
    )
  }
} 