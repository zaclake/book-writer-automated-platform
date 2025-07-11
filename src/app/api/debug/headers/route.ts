import { NextRequest, NextResponse } from 'next/server'

export async function GET(request: NextRequest) {
  try {
    const headers = Object.fromEntries(request.headers.entries())
    
    return NextResponse.json({
      headers,
      url: request.url,
      method: request.method,
      timestamp: new Date().toISOString(),
      hasAuthHeader: !!headers.authorization,
      authHeaderPrefix: headers.authorization ? headers.authorization.substring(0, 20) + '...' : null
    })
  } catch (error) {
    console.error('Headers debug error:', error)
    return NextResponse.json({
      error: error instanceof Error ? error.message : 'Unknown error',
      timestamp: new Date().toISOString()
    })
  }
} 