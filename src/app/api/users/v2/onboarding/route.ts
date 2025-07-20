import { NextRequest, NextResponse } from 'next/server'
import { auth, currentUser } from '@clerk/nextjs/server'
import { initializeApp, getApps, cert } from 'firebase-admin/app'
import { getFirestore } from 'firebase-admin/firestore'

interface OnboardingData {
  purpose: 'personal' | 'commercial' | 'educational'
  involvement_level: 'hands_off' | 'balanced' | 'hands_on'
  writing_experience: 'beginner' | 'intermediate' | 'advanced' | 'professional'
  genre_preference: string
  bio?: string
  writing_goals?: string
}

// Initialize Firebase Admin SDK
let adminDb: FirebaseFirestore.Firestore

try {
  if (getApps().length === 0) {
    // Parse service account from environment variable
    const serviceAccountJson = process.env.SERVICE_ACCOUNT_JSON
    
    if (!serviceAccountJson) {
      throw new Error('SERVICE_ACCOUNT_JSON environment variable not found')
    }
    
    const serviceAccount = JSON.parse(serviceAccountJson)
    
    // Validate required fields
    if (!serviceAccount.project_id) {
      throw new Error('Service account JSON missing project_id')
    }
    
    initializeApp({
      credential: cert(serviceAccount),
      projectId: serviceAccount.project_id
    })
  }
  
  adminDb = getFirestore()
} catch (error) {
  console.error('Failed to initialize Firebase Admin:', error)
}

export async function POST(request: NextRequest) {
  try {
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
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const onboardingData: OnboardingData = await request.json()

    // Validate required fields
    if (!onboardingData.purpose || !onboardingData.involvement_level || !onboardingData.writing_experience) {
      return NextResponse.json(
        { error: 'Purpose, involvement level, and writing experience are required' },
        { status: 400 }
      )
    }

    // Validate purpose
    if (!['personal', 'commercial', 'educational'].includes(onboardingData.purpose)) {
      return NextResponse.json(
        { error: 'Invalid purpose value' },
        { status: 400 }
      )
    }

    // Validate involvement level
    if (!['hands_off', 'balanced', 'hands_on'].includes(onboardingData.involvement_level)) {
      return NextResponse.json(
        { error: 'Invalid involvement level value' },
        { status: 400 }
      )
    }

    // Validate writing experience
    if (!['beginner', 'intermediate', 'advanced', 'professional'].includes(onboardingData.writing_experience)) {
      return NextResponse.json(
        { error: 'Invalid writing experience value' },
        { status: 400 }
      )
    }

    try {
      // Save onboarding data to Firestore
      const userRef = adminDb.collection('users').doc(userId)
      
      // Check if user document exists, create if not
      const userDoc = await userRef.get()
      
      const now = new Date()
      const onboardingPreferences = {
        'preferences.purpose': onboardingData.purpose,
        'preferences.involvement_level': onboardingData.involvement_level,
        'preferences.writing_experience': onboardingData.writing_experience,
        'preferences.default_genre': onboardingData.genre_preference || 'Fiction',
        'preferences.bio': onboardingData.bio || '',
        'preferences.writing_goals': onboardingData.writing_goals || '',
        'preferences.onboarding_completed': true,
        'preferences.onboarding_completed_at': now
      }

      if (!userDoc.exists) {
        // Create new user document with full structure
        await userRef.set({
          profile: {
            clerk_id: userId,
            created_at: now,
            last_active: now
          },
          preferences: {
            purpose: onboardingData.purpose,
            involvement_level: onboardingData.involvement_level,
            writing_experience: onboardingData.writing_experience,
            default_genre: onboardingData.genre_preference || 'Fiction',
            bio: onboardingData.bio || '',
            writing_goals: onboardingData.writing_goals || '',
            onboarding_completed: true,
            onboarding_completed_at: now,
            default_word_count: 2000,
            quality_strictness: 'standard',
            auto_backup_enabled: true,
            collaboration_notifications: true,
            email_notifications: true,
            preferred_llm_model: 'gpt-4o'
          },
          usage: {
            monthly_cost: 0.0,
            chapters_generated: 0,
            api_calls: 0,
            words_generated: 0,
            projects_created: 0,
            last_reset_date: now
          },
          limits: {
            monthly_cost_limit: 50.0,
            monthly_chapter_limit: 100,
            concurrent_projects_limit: 5,
            storage_limit_mb: 1000
          }
        })
      } else {
        // Update existing user document
        await userRef.update(onboardingPreferences)
      }

      const completedOnboardingData = {
        ...onboardingData,
        completed: true,
        completed_at: now.toISOString()
      }

      return NextResponse.json({ 
        success: true, 
        message: 'Onboarding completed successfully',
        data: completedOnboardingData
      })
    } catch (firestoreError) {
      console.error('Firestore operation failed:', firestoreError)
      return NextResponse.json(
        { error: 'Failed to save onboarding data' },
        { status: 500 }
      )
    }
  } catch (error) {
    console.error('POST /api/users/v2/onboarding error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}

export async function GET(request: NextRequest) {
  try {
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
      console.log('GET /api/users/v2/onboarding - No userId found')
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    console.log('GET /api/users/v2/onboarding - userId:', userId)

    try {
      // Get onboarding status from Firestore
      const userRef = adminDb.collection('users').doc(userId)
      const userDoc = await userRef.get()
      
      if (!userDoc.exists) {
        console.log('GET /api/users/v2/onboarding - No user document found')
        return NextResponse.json({ 
          completed: false,
          message: 'Onboarding not completed'
        })
      }

      const userData = userDoc.data()
      const preferences = userData?.preferences || {}
      
      if (!preferences.onboarding_completed) {
        console.log('GET /api/users/v2/onboarding - Onboarding not completed')
        return NextResponse.json({ 
          completed: false,
          message: 'Onboarding not completed'
        })
      }

      console.log('GET /api/users/v2/onboarding - Returning onboarding data')
      return NextResponse.json({
        completed: true,
        data: {
          purpose: preferences.purpose,
          involvement_level: preferences.involvement_level,
          writing_experience: preferences.writing_experience,
          genre_preference: preferences.default_genre,
          bio: preferences.bio,
          writing_goals: preferences.writing_goals,
          completed: true,
          completed_at: preferences.onboarding_completed_at?.toDate?.()?.toISOString() || new Date().toISOString()
        }
      })
    } catch (firestoreError) {
      console.error('Firestore read failed:', firestoreError)
      return NextResponse.json(
        { error: 'Failed to read onboarding data' },
        { status: 500 }
      )
    }
  } catch (error) {
    console.error('GET /api/users/v2/onboarding error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
} 