import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

export const dynamic = 'force-dynamic'

export async function GET(request: NextRequest) {
  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      return NextResponse.json(
        { error: 'Backend URL not configured' },
        { status: 500 }
      )
    }

    // Get Clerk auth and JWT token
    const { getToken } = await auth()
    
    try {
      const token = await getToken()
      
      if (!token) {
        return NextResponse.json({
          error: 'No token available',
          step: 'token_extraction'
        }, { status: 401 })
      }

      // Test backend authentication directly
      const testUrl = `${backendBaseUrl}/auto-complete/jobs?limit=1`
      
      const backendResponse = await fetch(testUrl, {
        method: 'GET',
        headers: {
          'authorization': `Bearer ${token}`,
          'content-type': 'application/json'
        },
        cache: 'no-store'
      })

      const responseText = await backendResponse.text()
      let responseData
      try {
        responseData = JSON.parse(responseText)
      } catch {
        responseData = { raw: responseText }
      }

      return NextResponse.json({
        success: backendResponse.ok,
        status: backendResponse.status,
        tokenPreview: token.substring(0, 50) + '...',
        tokenLength: token.length,
        backendResponse: responseData,
        step: 'backend_auth_test',
        timestamp: new Date().toISOString()
      })
      
    } catch (error) {
      console.error('Backend auth test failed:', error)
      return NextResponse.json({
        error: 'Backend auth test failed',
        details: error instanceof Error ? error.message : 'Unknown error',
        step: 'backend_request'
      }, { status: 500 })
    }
  } catch (error: any) {
    console.error('[debug-backend-auth] error:', error)
    return NextResponse.json({
      error: 'Debug test failed',
      details: error.message || 'Internal Server Error',
      step: 'initialization'
    }, { status: 500 })
  }
} 