import { NextRequest, NextResponse } from 'next/server'
import { currentUser } from '@clerk/nextjs/server'

export async function GET(request: NextRequest) {
  try {
    const user = await currentUser()
    
    return NextResponse.json({
      message: 'This is a protected route',
      authenticated: !!user,
      userId: user?.id || null,
      email: user?.emailAddresses?.[0]?.emailAddress || null,
      timestamp: new Date().toISOString()
    })
  } catch (error) {
    console.error('Protected route error:', error)
    return NextResponse.json({
      error: error instanceof Error ? error.message : 'Unknown error',
      timestamp: new Date().toISOString()
    }, { status: 500 })
  }
} 