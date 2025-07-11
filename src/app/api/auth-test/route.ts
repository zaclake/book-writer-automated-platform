import { NextRequest, NextResponse } from 'next/server'
import { currentUser } from '@clerk/nextjs/server'

export async function GET(request: NextRequest) {
  try {
    // This endpoint is not protected by middleware, so we can test auth status
    const user = await currentUser()
    
    return NextResponse.json({
      authenticated: !!user,
      userId: user?.id || null,
      email: user?.emailAddresses?.[0]?.emailAddress || null,
      timestamp: new Date().toISOString()
    })
  } catch (error) {
    console.error('Auth test error:', error)
    return NextResponse.json({
      authenticated: false,
      error: error instanceof Error ? error.message : 'Unknown error',
      timestamp: new Date().toISOString()
    })
  }
} 