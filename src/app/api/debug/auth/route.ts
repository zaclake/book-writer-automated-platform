import { NextRequest, NextResponse } from 'next/server'
import { currentUser } from '@clerk/nextjs/server'

export async function GET(request: NextRequest) {
  try {
    // Check environment variables (without exposing them)
    const hasPublishableKey = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
    const hasSecretKey = !!process.env.CLERK_SECRET_KEY
    
    // Try to get current user (this will show if Clerk is working)
    let userStatus = 'unknown'
    let userId = null
    
    try {
      const user = await currentUser()
      if (user) {
        userStatus = 'authenticated'
        userId = user.id
      } else {
        userStatus = 'not_authenticated'
      }
    } catch (error) {
      userStatus = 'clerk_error'
      console.error('Clerk user check failed:', error)
    }
    
    return NextResponse.json({
      environment: {
        hasPublishableKey,
        hasSecretKey,
        nodeEnv: process.env.NODE_ENV,
        vercelEnv: process.env.VERCEL_ENV
      },
      auth: {
        userStatus,
        userId: userId ? 'present' : 'none',
        clerkConfigured: hasPublishableKey && hasSecretKey
      },
      timestamp: new Date().toISOString()
    })
  } catch (error) {
    console.error('Auth debug error:', error)
    return NextResponse.json(
      { 
        error: 'Debug check failed',
        message: error instanceof Error ? error.message : 'Unknown error'
      }, 
      { status: 500 }
    )
  }
} 