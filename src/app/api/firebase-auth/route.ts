import { NextRequest, NextResponse } from 'next/server'

// Use dynamic import to avoid initialization issues
let admin: any = null

async function initializeFirebaseAdmin() {
  if (!admin) {
    admin = await import('firebase-admin')
  }
  
  // Only initialize if no apps exist
  if (admin.apps.length === 0) {
    try {
      const serviceAccountKey = process.env.FIREBASE_SERVICE_ACCOUNT_KEY || process.env.SERVICE_ACCOUNT_JSON
      
      if (!serviceAccountKey) {
        console.error('❌ Firebase Admin SDK: No service account key found')
        throw new Error('No service account key found')
      }
      
      const serviceAccount = JSON.parse(serviceAccountKey)
      console.log('🔍 Service account details:', {
        project_id: serviceAccount.project_id,
        client_email: serviceAccount.client_email
      })
      
      // Initialize with explicit project ID to ensure correct context
      admin.initializeApp({
        credential: admin.credential.cert(serviceAccount),
        projectId: serviceAccount.project_id
      })
      
      console.log('✅ Firebase Admin SDK initialized with explicit project ID:', serviceAccount.project_id)
    } catch (error) {
      console.error('❌ Firebase Admin SDK initialization failed:', error)
      throw error
    }
  } else {
    console.log('🔄 Using existing Firebase Admin SDK app')
  }
  
  return admin
}

export async function POST(request: NextRequest) {
  try {
    console.log('🔐 Firebase Auth endpoint called')
    
    // Initialize Firebase Admin SDK
    const firebaseAdmin = await initializeFirebaseAdmin()
    
    // Get authentication from Clerk (primary source)
    let userId: string | null = null
    
    try {
      console.log('🔍 Getting Clerk authentication...')
      const authResult = await auth()
      userId = authResult.userId
      console.log('✅ Clerk authentication successful for user:', userId?.substring(0, 8) + '...')
      
      // Also try to get user ID from request body for verification/logging
      let bodyUserId: string | null = null
      try {
        const body = await request.json()
        bodyUserId = body.userId
        console.log('🔍 User ID from request body:', bodyUserId?.substring(0, 8) + '...')
        
        // Log comparison for debugging
        if (bodyUserId && userId) {
          console.log('🔍 User ID comparison:', {
            clerk: userId,
            body: bodyUserId,
            match: userId === bodyUserId
          })
        }
      } catch (bodyError: any) {
        console.log('ℹ️ No request body or parsing error (using Clerk auth only):', bodyError.message)
      }
      
      console.log('✅ User ID verification successful, using Clerk ID:', userId?.substring(0, 8) + '...')
    } catch (authError: any) {
      console.error('❌ Clerk authentication error:', authError)
      return NextResponse.json(
        { 
          error: 'Unauthorized - No user authentication found',
          debug: 'Firebase auth endpoint could not find Clerk user ID',
          suggestion: 'Make sure you are signed in to Clerk'
        },
        { status: 401 }
      )
    }

    if (!userId) {
      console.error('❌ No user ID found after authentication')
      return NextResponse.json(
        { 
          error: 'Unauthorized - No user ID found',
          debug: 'User ID is null after Clerk authentication',
          suggestion: 'Try signing out and signing in again'
        },
        { status: 401 }
      )
    }

    // Generate a Firebase custom token for this user
    console.log('🔥 Generating Firebase custom token for user:', userId.substring(0, 8) + '...')
    console.log('🔍 About to call createCustomToken with userId:', userId)
    
    try {
      // Use the simplest possible token creation without any options
      console.log('🔧 Calling createCustomToken with exact userId:', JSON.stringify(userId))
      const customToken = await firebaseAdmin.auth().createCustomToken(userId)
      
      console.log('✅ Firebase custom token generated successfully')
      
      // Debug: Log token payload to verify all fields
      const tokenParts = customToken.split('.')
      const payload = JSON.parse(Buffer.from(tokenParts[1], 'base64').toString())
      console.log('🔍 Complete token payload:', {
        sub: payload.sub,
        uid: payload.uid,
        aud: payload.aud,
        iss: payload.iss,
        iat: payload.iat,
        exp: payload.exp,
        providedUserId: userId,
        subMatchesUserId: payload.sub === userId,
        uidMatchesUserId: payload.uid === userId
      })
    
    return NextResponse.json({ 
      customToken,
        userId: userId.substring(0, 8) + '...' // Only return partial ID for security
    })
    
    } catch (firebaseError: any) {
      console.error('❌ Firebase token generation error:', firebaseError)
      return NextResponse.json(
        { 
          error: 'Failed to generate Firebase token',
          debug: `Firebase error: ${firebaseError.message}`,
          suggestion: 'Check Firebase Admin SDK configuration'
        },
        { status: 500 }
      )
    }
    
  } catch (error: any) {
    console.error('❌ Unexpected error in Firebase auth endpoint:', error)
    
    return NextResponse.json(
      { 
        error: 'Internal server error', 
        debug: `Unexpected error: ${error.message}`,
        suggestion: 'Please try again or contact support'
      },
      { status: 500 }
    )
  }
} 