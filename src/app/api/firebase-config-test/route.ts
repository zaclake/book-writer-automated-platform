import { NextRequest, NextResponse } from 'next/server'

export async function GET(request: NextRequest) {
  // Helper to clean environment variables that might be the string "undefined"
  const cleanEnvVar = (value: string | undefined): string => {
    if (!value || value === 'undefined' || value === 'null') {
      return ''
    }
    return value.trim()
  }

  // Extract sender ID from app ID if messaging sender ID is missing
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

  const config = {
    apiKey: cleanEnvVar(process.env.NEXT_PUBLIC_FIREBASE_API_KEY),
    authDomain: cleanEnvVar(process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN),
    projectId: cleanEnvVar(process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID),
    storageBucket: cleanEnvVar(process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET),
    messagingSenderId: messagingSenderId,
    appId: rawAppId
  }

  // Check if all required fields are present and not empty
  const requiredFields = [
    config.apiKey,
    config.authDomain, 
    config.projectId,
    config.storageBucket,
    config.messagingSenderId,
    config.appId
  ]
  
  const isConfigured = requiredFields.every(field => 
    field && 
    field !== 'undefined' && 
    field.trim().length > 0
  )

  const response = {
    status: isConfigured ? 'SUCCESS' : 'MISSING_FIELDS',
    workaroundUsed: workaroundUsed,
    config: {
      ...config,
      apiKey: config.apiKey ? `${config.apiKey.substring(0, 10)}...` : 'MISSING'
    },
    rawValues: {
      originalMessagingSenderId: rawMessagingSenderId || 'EMPTY',
      originalAppId: rawAppId || 'EMPTY',
      extractedSenderId: workaroundUsed ? messagingSenderId : null
    },
    validation: {
      allFieldsPresent: isConfigured,
      missingFields: requiredFields.map((field, index) => {
        const fieldNames = ['apiKey', 'authDomain', 'projectId', 'storageBucket', 'messagingSenderId', 'appId']
        return !field || field === 'undefined' || field.trim().length === 0 ? fieldNames[index] : null
      }).filter(Boolean)
    }
  }

  return NextResponse.json(response)
} 