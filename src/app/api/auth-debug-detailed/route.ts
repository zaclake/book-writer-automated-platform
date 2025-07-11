import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

export async function GET(request: NextRequest) {
  try {
    console.log('=== AUTH DEBUG START ===')
    
    // Check environment variables
    const envCheck = {
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY,
      CLERK_SECRET_KEY: !!process.env.CLERK_SECRET_KEY,
      NEXT_PUBLIC_BACKEND_URL: process.env.NEXT_PUBLIC_BACKEND_URL,
    }
    
    console.log('Environment check:', envCheck)
    
    // Try to get auth info
    let authInfo: any = {}
    let authError: string | null = null
    
    try {
      const { userId, getToken } = await auth()
      console.log('Auth userId:', userId)
      
      authInfo.userId = userId
      authInfo.hasUserId = !!userId
      
      if (userId) {
        try {
          const token = await getToken()
          console.log('Token available:', !!token)
          authInfo.hasToken = !!token
          authInfo.tokenLength = token ? token.length : 0
        } catch (tokenError) {
          console.error('Token error:', tokenError)
          authInfo.tokenError = String(tokenError)
        }
      }
    } catch (error) {
      console.error('Auth error:', error)
      authError = String(error)
    }
    
    // Check headers
    const headers = {
      cookie: request.headers.get('cookie') ? 'present' : 'missing',
      authorization: request.headers.get('authorization') ? 'present' : 'missing',
      userAgent: request.headers.get('user-agent'),
    }
    
    console.log('Headers:', headers)
    
    const result = {
      timestamp: new Date().toISOString(),
      environment: envCheck,
      auth: authInfo,
      authError,
      headers,
      url: request.url,
    }
    
    console.log('=== AUTH DEBUG END ===')
    console.log('Result:', JSON.stringify(result, null, 2))
    
    return NextResponse.json(result)
  } catch (error) {
    console.error('Debug endpoint error:', error)
    return NextResponse.json(
      { error: String(error), timestamp: new Date().toISOString() },
      { status: 500 }
    )
  }
} 