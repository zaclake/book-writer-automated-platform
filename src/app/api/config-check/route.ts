import { NextRequest, NextResponse } from 'next/server'

export async function GET(request: NextRequest) {
  try {
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    
    return NextResponse.json({
      success: true,
      config: {
        backend_url: backendUrl || 'NOT_SET',
        backend_configured: !!backendUrl,
        clerk_publishable_key: process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ? 'SET' : 'NOT_SET',
        clerk_secret_key: process.env.CLERK_SECRET_KEY ? 'SET' : 'NOT_SET',
        openai_api_key: process.env.OPENAI_API_KEY ? 'SET' : 'NOT_SET',
        node_env: process.env.NODE_ENV || 'development',
        vercel_env: process.env.VERCEL_ENV || 'development'
      }
    })
    
  } catch (error: any) {
    return NextResponse.json(
      { 
        error: `Config check failed: ${error.message}`,
        success: false
      },
      { status: 500 }
    )
  }
} 