import { NextRequest, NextResponse } from 'next/server'
import { currentUser } from '@clerk/nextjs/server'

export async function GET(request: NextRequest) {
  try {
    // Get the current user from Clerk
    const user = await currentUser()
    
    // Get all headers
    const headers = Object.fromEntries(request.headers.entries())
    
    return NextResponse.json({
      message: 'Auth Debug Endpoint',
      user: {
        authenticated: !!user,
        userId: user?.id || null,
        email: user?.emailAddresses?.[0]?.emailAddress || null
      },
      headers: {
        hasAuthHeader: !!headers.authorization,
        authHeaderPrefix: headers.authorization ? headers.authorization.substring(0, 20) + '...' : null,
        userAgent: headers['user-agent'],
        cookie: headers.cookie ? 'present' : 'missing'
      },
      timestamp: new Date().toISOString()
    })
  } catch (error) {
    console.error('Auth debug error:', error)
    return NextResponse.json({
      error: error instanceof Error ? error.message : 'Unknown error',
      timestamp: new Date().toISOString()
    }, { status: 500 })
  }
} 