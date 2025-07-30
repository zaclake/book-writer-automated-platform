import { NextRequest, NextResponse } from 'next/server'
import { auth, currentUser } from '@clerk/nextjs/server'
import { initializeApp, getApps, cert } from 'firebase-admin/app'
import { getFirestore } from 'firebase-admin/firestore'

// Force dynamic rendering to prevent static generation issues
export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

// Initialize Firebase Admin SDK
let adminDb: FirebaseFirestore.Firestore | null = null

function initializeFirebaseAdmin() {
  try {
    if (getApps().length === 0) {
      // Parse service account from environment variable
      const serviceAccountJson = process.env.SERVICE_ACCOUNT_JSON
      
      if (!serviceAccountJson) {
        return { success: false, error: 'SERVICE_ACCOUNT_JSON environment variable not found' }
      }
      
      const serviceAccount = JSON.parse(serviceAccountJson)
      
      // Validate required fields
      if (!serviceAccount.project_id) {
        return { success: false, error: 'Service account JSON missing project_id' }
      }
      
      initializeApp({
        credential: cert(serviceAccount),
        projectId: serviceAccount.project_id
      })
    }
    
    adminDb = getFirestore()
    return { success: true }
  } catch (error) {
    console.error('Failed to initialize Firebase Admin:', error)
    return { success: false, error: `Firebase initialization failed: ${error instanceof Error ? error.message : 'Unknown error'}` }
  }
}

export async function GET(request: NextRequest) {
  try {
    // Initialize Firebase Admin if not already done
    if (!adminDb) {
      const initResult = initializeFirebaseAdmin()
      if (!initResult.success) {
        console.error('Firebase Admin initialization failed:', initResult.error)
        return NextResponse.json({ 
          error: 'Database service unavailable',
          details: initResult.error 
        }, { status: 503 })
      }
    }
    
    // Try both auth methods to ensure compatibility
    let userId: string | null = null
    
    try {
      const user = await currentUser()
      userId = user?.id || null
    } catch (currentUserError) {
      console.log('currentUser() failed, trying auth():', currentUserError)
      try {
        const authResult = await auth()
        userId = authResult.userId
      } catch (authError) {
        console.error('Both auth methods failed:', authError)
      }
    }
    
    if (!userId) {
      console.log('GET /api/users/v2/usage - No userId found')
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    console.log('GET /api/users/v2/usage - userId:', userId)

    try {
      // Get user usage and limits from Firestore
      const userRef = adminDb!.collection('users').doc(userId)
      const userDoc = await userRef.get()
      
      if (!userDoc.exists) {
        console.log('GET /api/users/v2/usage - No user document found')
        return NextResponse.json({ 
          usage: {
            monthly_cost: 0.0,
            chapters_generated: 0,
            api_calls: 0,
            words_generated: 0,
            projects_created: 0
          },
          limits: {
            monthly_cost_limit: 50.0,
            monthly_chapter_limit: 100,
            concurrent_projects_limit: 5,
            storage_limit_mb: 1000
          },
          remaining: {
            monthly_cost_remaining: 50.0,
            monthly_chapter_remaining: 100
          }
        })
      }

      const userData = userDoc.data()
      const usage = userData?.usage || {
        monthly_cost: 0.0,
        chapters_generated: 0,
        api_calls: 0,
        words_generated: 0,
        projects_created: 0
      }
      
      const limits = userData?.limits || {
        monthly_cost_limit: 50.0,
        monthly_chapter_limit: 100,
        concurrent_projects_limit: 5,
        storage_limit_mb: 1000
      }

      // Calculate remaining amounts
      const remaining = {
        monthly_cost_remaining: Math.max(0, limits.monthly_cost_limit - usage.monthly_cost),
        monthly_chapter_remaining: Math.max(0, limits.monthly_chapter_limit - usage.chapters_generated)
      }

      console.log('GET /api/users/v2/usage - Returning usage data')
      return NextResponse.json({
        usage,
        limits,
        remaining
      })
    } catch (firestoreError) {
      console.error('Firestore read failed:', firestoreError)
      return NextResponse.json(
        { error: 'Failed to read usage data' },
        { status: 500 }
      )
    }
  } catch (error) {
    console.error('GET /api/users/v2/usage error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}