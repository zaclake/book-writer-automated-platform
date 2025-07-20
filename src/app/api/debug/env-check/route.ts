import { NextRequest, NextResponse } from 'next/server'

export async function GET(request: NextRequest) {
  // Check if we're in build time or runtime
  const isServer = typeof window === 'undefined'
  const nodeEnv = process.env.NODE_ENV
  
  // Helper to clean environment variables that might be the string "undefined"
  const cleanEnvVar = (value: string | undefined): string => {
    if (!value || value === 'undefined' || value === 'null') {
      return ''
    }
    return value.trim()
  }

  // CRITICAL FIX: Extract sender ID from app ID if messaging sender ID is missing
  const extractSenderIdFromAppId = (appId: string): string => {
    // Firebase App ID format: "1:681297692294:web:6bebc5668ea47c037cb307"
    // The sender ID is the number after the first colon
    const match = appId.match(/^1:(\d+):/)
    return match ? match[1] : ''
  }

  const rawMessagingSenderId = cleanEnvVar(process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID)
  const rawAppId = cleanEnvVar(process.env.NEXT_PUBLIC_FIREBASE_APP_ID)
  
  // If messaging sender ID is empty or "undefined", try to extract from app ID
  let messagingSenderId = rawMessagingSenderId
  let workaroundUsed = false
  if (!messagingSenderId && rawAppId) {
    messagingSenderId = extractSenderIdFromAppId(rawAppId)
    workaroundUsed = true
  }
  
  // Get all environment variables
  const envVars = {
    // Firebase Config
    'NEXT_PUBLIC_FIREBASE_API_KEY': process.env.NEXT_PUBLIC_FIREBASE_API_KEY || 'undefined',
    'NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN': process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN || 'undefined',
    'NEXT_PUBLIC_FIREBASE_PROJECT_ID': process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID || 'undefined',
    'NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET': process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET || 'undefined',
    'NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID': process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID || 'undefined',
    'NEXT_PUBLIC_FIREBASE_APP_ID': process.env.NEXT_PUBLIC_FIREBASE_APP_ID || 'undefined',
    
    // Auth Config
    'NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY': process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ? '***set***' : 'undefined',
    'CLERK_SECRET_KEY': process.env.CLERK_SECRET_KEY ? '***set***' : 'undefined',
    
    // Backend Config
    'NEXT_PUBLIC_BACKEND_URL': process.env.NEXT_PUBLIC_BACKEND_URL || 'undefined'
  }

  // CRITICAL: Detect value swap issue
  const appIdValue = process.env.NEXT_PUBLIC_FIREBASE_APP_ID || ''
  const messagingSenderIdValue = process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID || ''
  const expectedSenderId = '681297692294'
  
  // Check if sender ID is embedded in app ID (indicates swap)
  const senderIdInAppId = appIdValue.includes(expectedSenderId)
  const messagingSenderIncorrect = messagingSenderIdValue === 'undefined' || messagingSenderIdValue === '' || messagingSenderIdValue !== expectedSenderId

  // Additional debugging info
  const debugInfo = {
    environment: nodeEnv,
    isServer: isServer,
    timestamp: new Date().toISOString(),
    vercelEnv: process.env.VERCEL_ENV || 'undefined',
    vercelUrl: process.env.VERCEL_URL || 'undefined',
    
    // CRITICAL ANALYSIS: Variable value swap detection
    valueSwapAnalysis: {
      expectedSenderId: expectedSenderId,
      currentMessagingSenderId: messagingSenderIdValue,
      currentAppId: appIdValue,
      senderIdFoundInAppId: senderIdInAppId,
      messagingSenderIncorrect: messagingSenderIncorrect,
      likelySwapIssue: senderIdInAppId && messagingSenderIncorrect,
      recommendation: senderIdInAppId && messagingSenderIncorrect 
        ? 'CRITICAL: The messaging sender ID appears to be embedded in the app ID. Check Vercel environment variable configuration for value swap.'
        : 'Configuration appears correct.'
    },

    // FIREBASE WORKAROUND TEST
    firebaseWorkaroundTest: {
      status: workaroundUsed ? 'WORKAROUND_APPLIED' : 'NORMAL_OPERATION',
      originalSenderId: rawMessagingSenderId || 'EMPTY',
      extractedSenderId: workaroundUsed ? messagingSenderId : null,
      appIdSource: rawAppId || 'EMPTY',
      workaroundSuccessful: workaroundUsed && messagingSenderId === expectedSenderId,
      recommendation: workaroundUsed 
        ? `Workaround successfully extracted sender ID '${messagingSenderId}' from app ID. Firebase should now initialize correctly.`
        : 'No workaround needed - messaging sender ID is properly configured.'
    },
    
    // Check specific Firebase variable in different ways
    firebaseMessagingDebug: {
      directEnvAccess: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
      stringified: JSON.stringify(process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID),
      typeof: typeof process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
      length: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID?.length || 0,
      isUndefined: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID === undefined,
      isEmptyString: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID === '',
      isNull: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID === null,
      isStringUndefined: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID === 'undefined'
    },
    
    // Firebase App ID analysis
    firebaseAppIdDebug: {
      value: appIdValue,
      containsExpectedSenderId: senderIdInAppId,
      extractedSenderFromAppId: senderIdInAppId ? appIdValue.match(/(\d+)/)?.[1] : null,
      format: appIdValue.includes(':') ? 'Valid Firebase App ID format' : 'Invalid format'
    },
    
    // List all NEXT_PUBLIC_ variables found
    allNextPublicVars: Object.keys(process.env)
      .filter(key => key.startsWith('NEXT_PUBLIC_'))
      .reduce((acc, key) => {
        acc[key] = process.env[key] ? (key.includes('FIREBASE') ? process.env[key] : '***set***') : 'undefined'
        return acc
      }, {} as Record<string, string>),
      
    // All environment variables with FIREBASE in the name
    allFirebaseVars: Object.keys(process.env)
      .filter(key => key.includes('FIREBASE'))
      .reduce((acc, key) => {
        acc[key] = process.env[key] || 'undefined'
        return acc
      }, {} as Record<string, string>)
  }

  const response = {
    environmentVariables: envVars,
    debugInfo: debugInfo
  }

  return NextResponse.json(response, {
    headers: {
      'Cache-Control': 'no-store, no-cache, must-revalidate',
      'Pragma': 'no-cache',
      'Expires': '0'
    }
  })
} 