import { NextRequest, NextResponse } from 'next/server'

export async function GET(request: NextRequest) {
  try {
    const authHeader = request.headers.get('authorization')
    
    return NextResponse.json({
      message: 'Client auth test endpoint',
      hasAuthHeader: !!authHeader,
      authHeaderPreview: authHeader ? authHeader.substring(0, 20) + '...' : null,
      instructions: {
        message: 'This endpoint shows how to test authentication from the frontend',
        example: 'Include Authorization: Bearer <token> header in your requests'
      },
      timestamp: new Date().toISOString()
    })
  } catch (error) {
    console.error('Client auth test error:', error)
    return NextResponse.json({
      error: error instanceof Error ? error.message : 'Unknown error',
      timestamp: new Date().toISOString()
    })
  }
} 