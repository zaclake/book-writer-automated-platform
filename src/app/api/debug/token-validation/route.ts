import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'
import admin from 'firebase-admin'

// Initialize Firebase Admin SDK
if (!admin.apps.length) {
  try {
    const serviceAccountKey = process.env.FIREBASE_SERVICE_ACCOUNT_KEY || process.env.SERVICE_ACCOUNT_JSON
    
    if (!serviceAccountKey) {
      console.error('❌ Firebase Admin SDK: No service account key found in environment variables')
    } else {
      console.log('✅ Firebase Admin SDK: Service account key found')
    }
    
    const serviceAccount = JSON.parse(serviceAccountKey || '{}')
    
    admin.initializeApp({
      credential: admin.credential.cert(serviceAccount),
      projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID
    })
    
    console.log('✅ Firebase Admin SDK initialized successfully')
  } catch (error) {
    console.error('❌ Firebase Admin SDK initialization failed:', error)
  }
}

async function validateToken() {
  try {
    console.log('🔍 Token validation debug endpoint called')
    
    // Check if Firebase Admin is properly initialized
    if (!admin.apps.length) {
      console.error('❌ Firebase Admin SDK not initialized')
      return NextResponse.json(
        { error: 'Firebase Admin SDK not initialized' },
        { status: 500 }
      )
    }
    
    // Get authentication from Clerk
    const { userId } = await auth()
    if (!userId) {
      return NextResponse.json({ error: 'Not authenticated' }, { status: 401 })
    }
    
    // Check Firebase Admin config
    const adminApp = admin.apps[0]
    const adminProjectId = adminApp?.options?.projectId
    
    // Check client config from environment variables
    const clientProjectId = process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID
    
    // Generate a custom token
    const customToken = await admin.auth().createCustomToken(userId)
    
    // Try to decode the custom token to see its structure
    let tokenPayload = null
    try {
      // Extract the payload (middle part) of the JWT
      const tokenParts = customToken.split('.')
      if (tokenParts.length === 3) {
        const payloadBase64 = tokenParts[1]
        // Add padding if needed
        const paddedPayload = payloadBase64 + '='.repeat((4 - payloadBase64.length % 4) % 4)
        const payloadJson = Buffer.from(paddedPayload, 'base64').toString('utf8')
        tokenPayload = JSON.parse(payloadJson)
      }
    } catch (decodeError) {
      console.error('Token decode error:', decodeError)
    }
    
    return NextResponse.json({
      timestamp: new Date().toISOString(),
      userId: userId.substring(0, 8) + '...',
      adminConfig: {
        projectId: adminProjectId,
        appName: adminApp?.name,
        storageBucket: adminApp?.options?.storageBucket
      },
      clientConfig: {
        projectId: clientProjectId,
        apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY ? 'Present' : 'Missing',
        authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN || 'Missing',
        storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET || 'Missing',
        messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID || 'Missing',
        appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID ? 'Present' : 'Missing'
      },
      configMatch: {
        projectIdMatch: adminProjectId === clientProjectId,
        adminProjectId,
        clientProjectId
      },
      customToken: {
        length: customToken.length,
        startsWithCorrectFormat: customToken.split('.').length === 3,
        payload: tokenPayload
      }
    })
    
  } catch (error: any) {
    console.error('❌ Token validation error:', error)
    return NextResponse.json({
      error: error.message,
      details: error.stack?.split('\n').slice(0, 5)
    }, { status: 500 })
  }
}

export async function GET(request: NextRequest) {
  return await validateToken()
}

export async function POST(request: NextRequest) {
  return await validateToken()
} 