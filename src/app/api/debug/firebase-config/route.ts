import { NextResponse } from 'next/server'

export async function GET() {
  try {
    const config = {
      NEXT_PUBLIC_FIREBASE_API_KEY: process.env.NEXT_PUBLIC_FIREBASE_API_KEY ? 'SET' : 'MISSING',
      NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN ? 'SET' : 'MISSING',
      NEXT_PUBLIC_FIREBASE_PROJECT_ID: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID ? 'SET' : 'MISSING',
      NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET ? 'SET' : 'MISSING',
      NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID ? 'SET' : 'MISSING',
      NEXT_PUBLIC_FIREBASE_APP_ID: process.env.NEXT_PUBLIC_FIREBASE_APP_ID ? 'SET' : 'MISSING',
      
      // Admin SDK vars (for comparison)
      FIREBASE_SERVICE_ACCOUNT_KEY: process.env.FIREBASE_SERVICE_ACCOUNT_KEY ? 'SET' : 'MISSING',
      SERVICE_ACCOUNT_JSON: process.env.SERVICE_ACCOUNT_JSON ? 'SET' : 'MISSING',
    }

    const missingVars = Object.entries(config)
      .filter(([key, value]) => value === 'MISSING' && key.startsWith('NEXT_PUBLIC_'))
      .map(([key]) => key)

    return NextResponse.json({
      status: missingVars.length === 0 ? 'ALL_SET' : 'MISSING_VARS',
      config,
      missingClientVars: missingVars,
      message: missingVars.length > 0 
        ? `Missing ${missingVars.length} Firebase client environment variables` 
        : 'All Firebase client environment variables are set'
    })
    
  } catch (error) {
    return NextResponse.json(
      { error: 'Failed to check Firebase config', details: error.message },
      { status: 500 }
    )
  }
} 