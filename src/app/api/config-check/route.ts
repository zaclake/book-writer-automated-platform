import { NextResponse } from 'next/server'

export async function GET() {
  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
  
  const debugInfo = {
    timestamp: new Date().toISOString(),
    environment: process.env.NODE_ENV,
    vercelEnv: process.env.VERCEL_ENV || 'Not set',
    deploymentUrl: process.env.VERCEL_URL || 'Not set',
    
    backendConfig: {
      value: backendUrl || 'NOT SET',
      isSet: !!backendUrl,
      pointsToRailway: backendUrl?.includes('railway.app') || false,
      pointsToWrongDomain: backendUrl?.includes('writerbloom.com') || false
    },
    
    allPublicVars: Object.keys(process.env)
      .filter(key => key.startsWith('NEXT_PUBLIC_'))
      .reduce((acc, key) => {
        acc[key] = process.env[key]
        return acc
      }, {} as Record<string, string | undefined>),
    
    vercelVars: {
      url: process.env.VERCEL_URL || 'Not set',
      env: process.env.VERCEL_ENV || 'Not set',
      commitSha: process.env.VERCEL_GIT_COMMIT_SHA || 'Not set'
    },
    
    diagnosis: {
      status: 'unknown',
      issues: [] as string[],
      recommendations: [] as string[]
    }
  }
  
  // Diagnose issues
  if (!backendUrl) {
    debugInfo.diagnosis.status = 'critical'
    debugInfo.diagnosis.issues.push('NEXT_PUBLIC_BACKEND_URL is not set')
    debugInfo.diagnosis.recommendations.push('Set NEXT_PUBLIC_BACKEND_URL in Vercel project settings to https://silky-loss-production.up.railway.app')
  } else if (backendUrl.includes('writerbloom.com')) {
    debugInfo.diagnosis.status = 'error'
    debugInfo.diagnosis.issues.push('NEXT_PUBLIC_BACKEND_URL points to frontend domain instead of backend')
    debugInfo.diagnosis.recommendations.push('Change NEXT_PUBLIC_BACKEND_URL to https://silky-loss-production.up.railway.app')
  } else if (backendUrl.includes('railway.app')) {
    debugInfo.diagnosis.status = 'good'
    debugInfo.diagnosis.recommendations.push('Configuration looks correct')
  } else {
    debugInfo.diagnosis.status = 'warning'
    debugInfo.diagnosis.issues.push('NEXT_PUBLIC_BACKEND_URL has unexpected value')
    debugInfo.diagnosis.recommendations.push('Verify backend URL is correct: https://silky-loss-production.up.railway.app')
  }
  
  debugInfo.diagnosis.recommendations.push('After making changes, redeploy the application')
  
  return NextResponse.json(debugInfo, {
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    }
  })
} 