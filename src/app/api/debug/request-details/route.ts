import { NextRequest, NextResponse } from 'next/server'

export async function GET(request: NextRequest) {
  try {
    // Get all headers
    const headers = Object.fromEntries(request.headers.entries())
    
    // Check for Clerk-specific headers and cookies
    const clerkHeaders = Object.entries(headers).filter(([key]) => 
      key.toLowerCase().includes('clerk') || 
      key.toLowerCase().includes('auth') ||
      key.toLowerCase().includes('session')
    )
    
    // Parse cookies to look for Clerk session cookies
    const cookieHeader = headers.cookie || ''
    const cookies = cookieHeader.split(';').map(c => c.trim()).filter(c => c)
    const clerkCookies = cookies.filter(cookie => 
      cookie.includes('__session') || 
      cookie.includes('__clerk') ||
      cookie.includes('_clerk')
    )
    
    return NextResponse.json({
      message: 'Detailed Request Debug',
      url: request.url,
      method: request.method,
      headers: {
        all: headers,
        clerkSpecific: clerkHeaders,
        userAgent: headers['user-agent'],
        authorization: headers.authorization || 'not present',
        cookie: headers.cookie ? 'present' : 'missing'
      },
      cookies: {
        all: cookies,
        clerkSpecific: clerkCookies,
        count: cookies.length
      },
      timestamp: new Date().toISOString()
    })
  } catch (error) {
    console.error('Request details debug error:', error)
    return NextResponse.json({
      error: error instanceof Error ? error.message : 'Unknown error',
      timestamp: new Date().toISOString()
    }, { status: 500 })
  }
} 