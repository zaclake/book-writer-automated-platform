import { NextRequest, NextResponse } from 'next/server'
import { auth, currentUser } from '@clerk/nextjs/server'

export async function GET(request: NextRequest) {
  try {
    console.log('🔍 Testing Clerk auth...')
    
    // Method 1: Using auth()
    let authResult
    try {
      authResult = await auth()
      console.log('✅ auth() result:', {
        userId: authResult.userId ? `${authResult.userId.substring(0, 8)}...` : null,
        sessionId: authResult.sessionId ? `${authResult.sessionId.substring(0, 8)}...` : null,
        orgId: authResult.orgId
      })
    } catch (authError: any) {
      console.error('❌ auth() failed:', authError.message)
      authResult = { error: authError.message }
    }
    
    // Method 2: Using currentUser()
    let userResult
    try {
      const user = await currentUser()
      userResult = user ? {
        id: user.id.substring(0, 8) + '...',
        email: user.emailAddresses?.[0]?.emailAddress,
        firstName: user.firstName,
        lastName: user.lastName
      } : null
      console.log('✅ currentUser() result:', userResult ? 'User found' : 'No user')
    } catch (userError: any) {
      console.error('❌ currentUser() failed:', userError.message)
      userResult = { error: userError.message }
    }
    
    return NextResponse.json({
      timestamp: new Date().toISOString(),
      authMethod: authResult,
      userMethod: userResult,
      headers: {
        authorization: request.headers.get('authorization') ? 'Present' : 'Missing',
        cookie: request.headers.get('cookie') ? 'Present' : 'Missing',
        userAgent: request.headers.get('user-agent')?.substring(0, 50) + '...'
      }
    })
    
  } catch (error: any) {
    console.error('❌ Test endpoint error:', error)
    return NextResponse.json({
      error: error.message,
      stack: error.stack?.split('\n').slice(0, 3)
    }, { status: 500 })
  }
}

export async function POST(request: NextRequest) {
  return GET(request) // Same logic for POST
} 