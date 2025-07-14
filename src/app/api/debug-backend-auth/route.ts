import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

export const dynamic = 'force-dynamic'

export async function GET(request: NextRequest) {
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

    // Test backend auth endpoint
    const testUrl = `${backendBaseUrl}/debug/auth`
    
    const response = await fetch(testUrl, {
      method: 'GET',
      headers,
      cache: 'no-store'
    })

    const data = await response.json()
    
    return NextResponse.json({
      backend_url: backendBaseUrl,
      backend_status: response.status,
      backend_response: data,
      headers_sent: headers,
      timestamp: new Date().toISOString()
    })
    
  } catch (error: any) {
    return NextResponse.json(
      { 
        error: `Debug backend auth failed: ${error.message}`,
        timestamp: new Date().toISOString()
      },
      { status: 500 }
    )
  }
} 