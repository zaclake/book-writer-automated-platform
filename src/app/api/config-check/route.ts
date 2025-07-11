import { NextRequest, NextResponse } from 'next/server'

export async function GET(request: NextRequest) {
  try {
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL
    
    return NextResponse.json({
      backendUrl: backendUrl || 'NOT_SET',
      expectedUrl: 'https://silky-loss-production.up.railway.app',
      isConfigured: !!backendUrl,
      isCorrectUrl: backendUrl === 'https://silky-loss-production.up.railway.app',
      timestamp: new Date().toISOString()
    })
  } catch (error) {
    console.error('Config check error:', error)
    return NextResponse.json({
      error: error instanceof Error ? error.message : 'Unknown error',
      timestamp: new Date().toISOString()
    })
  }
} 