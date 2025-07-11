import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

export const dynamic = 'force-dynamic'

export async function GET(request: NextRequest) {
  try {
    // Get Clerk auth and JWT token
    const { getToken } = await auth()
    
    try {
      const token = await getToken()
      
      return NextResponse.json({
        success: true,
        hasToken: !!token,
        tokenPreview: token ? token.substring(0, 50) + '...' : null,
        tokenLength: token ? token.length : 0,
        timestamp: new Date().toISOString()
      })
    } catch (error) {
      console.error('Failed to get Clerk token:', error)
      return NextResponse.json({
        success: false,
        error: 'Failed to get token',
        details: error instanceof Error ? error.message : 'Unknown error',
        timestamp: new Date().toISOString()
      }, { status: 500 })
    }
  } catch (error: any) {
    console.error('[token-test] error:', error)
    return NextResponse.json({
      success: false,
      error: 'Auth failed',
      details: error.message || 'Internal Server Error',
      timestamp: new Date().toISOString()
    }, { status: 500 })
  }
} 