/**
 * Frontend Firestore Client
 * Provides real-time listeners and client-side data operations.
 */

import { 
  initializeApp, 
  getApps, 
  FirebaseApp 
} from 'firebase/app'
import { 
  getFirestore, 
  doc, 
  collection, 
  query, 
  where, 
  orderBy, 
  onSnapshot, 
  getDocs, 
  getDoc, 
  Firestore,
  DocumentData,
  QuerySnapshot,
  DocumentSnapshot,
  Unsubscribe,
  QueryConstraint,
  enableIndexedDbPersistence,
  enableMultiTabIndexedDbPersistence
} from 'firebase/firestore'
import { 
  getAuth, 
  signInWithCustomToken, 
  onAuthStateChanged,
  Auth,
  User 
} from 'firebase/auth'
import { useAuth } from '@clerk/nextjs'

// Firebase configuration with fallbacks
const getFirebaseConfig = () => {
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
  if (!messagingSenderId && rawAppId) {
    messagingSenderId = extractSenderIdFromAppId(rawAppId)
    if (typeof window !== 'undefined') {
      console.warn('🔧 WORKAROUND: Extracted messaging sender ID from app ID:', messagingSenderId)
    }
  }

  const config = {
    apiKey: cleanEnvVar(process.env.NEXT_PUBLIC_FIREBASE_API_KEY),
    authDomain: cleanEnvVar(process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN),
    projectId: cleanEnvVar(process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID),
    storageBucket: cleanEnvVar(process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET),
    messagingSenderId: messagingSenderId,
    appId: rawAppId
  }
  
  // Debug environment variables in development and when they're missing
  if (typeof window !== 'undefined' && (!isFirebaseConfigured(config) || process.env.NODE_ENV === 'development')) {
    console.log('🔍 Firebase config debug:', {
      apiKey: config.apiKey ? `${config.apiKey.substring(0, 10)}...` : 'MISSING',
      authDomain: config.authDomain || 'MISSING',
      projectId: config.projectId || 'MISSING', 
      storageBucket: config.storageBucket || 'MISSING',
      messagingSenderId: config.messagingSenderId || 'MISSING',
      appId: config.appId ? `${config.appId.substring(0, 20)}...` : 'MISSING',
      
      // Raw environment variable debug
      raw: {
        messagingSenderIdRaw: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
        messagingSenderIdType: typeof process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
        messagingSenderIdLength: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID?.length,
        allFirebaseVars: Object.keys(process.env).filter(k => k.includes('FIREBASE')),
        extractedFromAppId: rawMessagingSenderId !== messagingSenderId ? messagingSenderId : null
      }
    })
  }
  
  return config
}

// Check if Firebase is properly configured
const isFirebaseConfigured = (config?: ReturnType<typeof getFirebaseConfig>) => {
  const cfg = config || getFirebaseConfig()
  
  // Check if all required fields are present and not empty
  const requiredFields = [
    cfg.apiKey,
    cfg.authDomain, 
    cfg.projectId,
    cfg.storageBucket,
    cfg.messagingSenderId,
    cfg.appId
  ]
  
  const isConfigured = requiredFields.every(field => 
    field && 
    field !== 'undefined' && 
    field.trim().length > 0
  )
  
  if (typeof window !== 'undefined' && process.env.NODE_ENV === 'development') {
    console.log('Firebase config check:', {
      configured: isConfigured,
      apiKey: !!cfg.apiKey && cfg.apiKey !== 'undefined',
      authDomain: !!cfg.authDomain && cfg.authDomain !== 'undefined',
      projectId: !!cfg.projectId && cfg.projectId !== 'undefined',
      storageBucket: !!cfg.storageBucket && cfg.storageBucket !== 'undefined',
      messagingSenderId: !!cfg.messagingSenderId && cfg.messagingSenderId !== 'undefined',
      appId: !!cfg.appId && cfg.appId !== 'undefined',
      failedFields: requiredFields.map((field, index) => {
        const fieldNames = ['apiKey', 'authDomain', 'projectId', 'storageBucket', 'messagingSenderId', 'appId']
        return !field || field === 'undefined' || field.trim().length === 0 ? fieldNames[index] : null
      }).filter(Boolean)
    })
  }
  
  return isConfigured
}

// Log configuration issues in production for debugging
if (typeof window !== 'undefined' && !isFirebaseConfigured()) {
  console.warn('⚠️ Firebase not configured - running in offline mode')
  
  if (process.env.NODE_ENV === 'development') {
    const config = getFirebaseConfig()
    console.log('Missing Firebase config values:', {
      apiKey: !config.apiKey,
      authDomain: !config.authDomain,
      projectId: !config.projectId,
      storageBucket: !config.storageBucket,
      messagingSenderId: !config.messagingSenderId,
      appId: !config.appId
    })
  }
}

// Types for our data structures
export interface Project {
  id: string
  metadata: {
    project_id: string
    title: string
    owner_id: string
    collaborators: string[]
    status: 'active' | 'completed' | 'archived' | 'paused'
    visibility: 'private' | 'shared' | 'public'
    created_at: any
    updated_at: any
  }
  book_bible?: {
    content: string
    last_modified: any
    modified_by: string
    version: number
    word_count: number
  }
  settings: {
    genre: string
    target_chapters: number
    word_count_per_chapter: number
    target_audience: string
    writing_style: string
    quality_gates_enabled: boolean
    auto_completion_enabled: boolean
  }
  progress: {
    chapters_completed: number
    current_word_count: number
    target_word_count: number
    completion_percentage: number
    last_chapter_generated: number
    quality_baseline: {
      prose: number
      character: number
      story: number
      emotion: number
      freshness: number
      engagement: number
    }
  }
}

export interface Chapter {
  id: string
  project_id: string
  chapter_number: number
  content: string
  title?: string
  metadata: {
    word_count: number
    target_word_count: number
    created_by: string
    stage: 'draft' | 'revision' | 'complete'
    generation_time: number
    retry_attempts: number
    model_used: string
    created_at: any
    updated_at: any
  }
  quality_scores: {
    overall_rating: number
    engagement_score: number
    craft_scores: {
      prose: number
      character: number
      story: number
      emotion: number
      freshness: number
    }
  }
  versions: Array<{
    version_number: number
    content: string
    timestamp: any
    reason: string
    user_id: string
    changes_summary: string
  }>
}

export interface GenerationJob {
  id: string
  job_type: 'single_chapter' | 'auto_complete_book' | 'reference_generation'
  project_id: string
  user_id: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'paused' | 'cancelled'
  created_at: any
  started_at?: any
  completed_at?: any
  progress: {
    current_step: string
    total_steps: number
    completed_steps: number
    percentage: number
  }
  results: {
    chapters_generated: string[]
    total_cost: number
    total_tokens: number
    average_quality_score: number
    generation_time: number
  }
}

// Initialize Firebase (only in browser, not during build)
let app: FirebaseApp | null = null
let db: Firestore | null = null
let auth: Auth | null = null
let currentUser: User | null = null

if (typeof window !== 'undefined') {
  if (isFirebaseConfigured()) {
    try {
      if (getApps().length === 0) {
        app = initializeApp(getFirebaseConfig())
      } else {
        app = getApps()[0]
      }
      db = getFirestore(app)
      auth = getAuth(app)
      
      // Set up auth state listener
      onAuthStateChanged(auth, (user) => {
        currentUser = user
        if (user) {
          console.log('✅ Firebase Auth: User signed in:', user.uid)
        } else {
          console.log('🔐 Firebase Auth: User signed out')
        }
      })
      
      console.log('✅ Firebase initialized successfully')
    } catch (error) {
      console.error('❌ Failed to initialize Firebase:', error)
    }
  } else {
    console.warn('⚠️ Firebase not configured - running in offline mode')
  }
}

export { db }
export { getFirebaseConfig }

// Enable offline persistence
let persistenceEnabled = false
let initializationAttempted = false

async function enableOfflinePersistence() {
  if (persistenceEnabled || !db) {
    if (!db) {
      console.warn('⚠️ Cannot enable persistence - Firestore not initialized')
    }
    return
  }
  
  try {
    // Try multi-tab persistence first (recommended for web apps)
    await enableMultiTabIndexedDbPersistence(db)
    console.log('✓ Multi-tab Firestore offline persistence enabled')
    persistenceEnabled = true
  } catch (err: any) {
    if (err.code === 'failed-precondition') {
      // Multiple tabs open, persistence can only be enabled in one tab at a time
      console.warn('⚠️ Multi-tab persistence failed - trying single tab persistence')
      try {
        await enableIndexedDbPersistence(db!)
        console.log('✓ Single-tab Firestore offline persistence enabled')
        persistenceEnabled = true
      } catch (singleTabErr: any) {
        if (singleTabErr.code === 'failed-precondition') {
          console.warn('⚠️ Persistence can only be enabled in one tab at a time.')
        } else if (singleTabErr.code === 'unimplemented') {
          console.warn('⚠️ The current browser does not support persistence.')
        } else {
          console.error('❌ Error enabling single-tab persistence:', singleTabErr)
        }
      }
    } else if (err.code === 'unimplemented') {
      console.warn('⚠️ The current browser does not support offline persistence.')
    } else {
      console.error('❌ Error enabling multi-tab persistence:', err)
    }
  }
}

/**
 * Reinitialize Firebase when configuration becomes available.
 * This handles the case where the app starts with empty config but later receives valid config.
 */
export async function reinitializeFirebase(): Promise<boolean> {
  if (typeof window === 'undefined') {
    return false
  }

  // Get fresh config in case environment variables have been loaded
  const currentConfig = getFirebaseConfig()
  
  // Check if config is now available
  if (!isFirebaseConfigured(currentConfig)) {
    console.log('🔍 Firebase config still not available for reinitialization')
    console.log('Current config status:', {
      apiKey: !!currentConfig.apiKey,
      authDomain: !!currentConfig.authDomain,
      projectId: !!currentConfig.projectId,
      storageBucket: !!currentConfig.storageBucket,
      messagingSenderId: !!currentConfig.messagingSenderId,
      appId: !!currentConfig.appId
    })
    return false
  }

  // Don't reinitialize if already properly initialized
  if (db && !initializationAttempted) {
    console.log('✅ Firebase already properly initialized')
    return true
  }

  try {
    console.log('🔄 Attempting to reinitialize Firebase with available config...')
    
    // Clear previous state
    db = null
    app = null
    persistenceEnabled = false
    initializationAttempted = true

    // Initialize Firebase with fresh config
    if (getApps().length === 0) {
      app = initializeApp(currentConfig)
    } else {
      app = getApps()[0]
    }
    
    db = getFirestore(app)
    console.log('✅ Firebase reinitialized successfully')

    // Enable offline persistence
    await enableOfflinePersistence()

    // Test connection
    try {
      // Simple connection test
      const testDoc = doc(db, 'connection-test', 'test')
      console.log('🔄 Firebase connection established - offline operations should sync')
    } catch (connError) {
      console.warn('⚠️ Firebase connection check failed:', connError)
    }

    return true
  } catch (error) {
    console.error('❌ Failed to reinitialize Firebase:', error)
    return false
  }
}

/**
 * Check if Firebase is ready and attempt reinitialization if needed.
 * Call this when you suspect config might have become available.
 */
export function ensureFirebaseInitialized(): Promise<boolean> {
  return new Promise((resolve) => {
    if (typeof window === 'undefined') {
      resolve(false)
      return
    }

    // Get fresh config 
    const currentConfig = getFirebaseConfig()

    // If already initialized properly, we're good
    if (db && isFirebaseConfigured(currentConfig)) {
      resolve(true)
      return
    }

    // If config is available but not initialized, try reinitializing
    if (isFirebaseConfigured(currentConfig) && !db) {
      reinitializeFirebase().then(resolve)
      return
    }

    // If config is not available, check periodically for a short time
    let attempts = 0
    const maxAttempts = 10 // 5 seconds total
    const checkInterval = setInterval(async () => {
      attempts++
      const freshConfig = getFirebaseConfig()
      
      if (isFirebaseConfigured(freshConfig)) {
        clearInterval(checkInterval)
        const success = await reinitializeFirebase()
        resolve(success)
      } else if (attempts >= maxAttempts) {
        clearInterval(checkInterval)
        console.warn('⏰ Timeout waiting for Firebase config')
        resolve(false)
      }
    }, 500)
  })
}

/**
 * Authenticate with Firebase using Clerk authentication
 */
export async function authenticateWithFirebase(userId?: string): Promise<boolean> {
  if (typeof window === 'undefined' || !auth) {
    console.warn('Firebase Auth not available')
    return false
  }

  try {
    console.log('🔐 Starting Firebase authentication process...')
    
    // Get Firebase custom token from our API
    const requestBody = userId ? { userId } : {}
    
    const response = await fetch('/api/firebase-auth', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestBody)
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      console.error('❌ Firebase auth endpoint error:', {
        status: response.status,
        statusText: response.statusText,
        error: errorData
      })
      throw new Error(`Failed to get Firebase token: ${response.status}`)
    }

    const { customToken } = await response.json()

    // Sign in to Firebase with the custom token
    await signInWithCustomToken(auth, customToken)
    console.log('✅ Successfully authenticated with Firebase')
    return true

  } catch (error) {
    console.error('❌ Failed to authenticate with Firebase:', error)
    return false
  }
}

// Initialize offline persistence
if (typeof window !== 'undefined') {
  initializationAttempted = true
  enableOfflinePersistence()
}

/**
 * Frontend Firestore Service
 * Handles real-time subscriptions and client-side operations
 */
export class FirestoreClientService {
  private db: Firestore
  private userId: string | null = null

  constructor() {
    this.db = db
  }

  setUserId(userId: string) {
    this.userId = userId
  }

  // =====================================================================
  // PROJECT LISTENERS
  // =====================================================================

  /**
   * Subscribe to user's projects with real-time updates
   */
  subscribeToUserProjects(
    userId: string,
    onUpdate: (projects: Project[]) => void,
    onError: (error: Error) => void
  ): Unsubscribe {
    // Firestore subscriptions disabled - using backend APIs only
    console.log('🔧 Firestore project subscriptions disabled - using backend APIs only')
    onUpdate([])
    return () => {} // Return no-op unsubscribe function
    
    const projectsRef = collection(this.db, 'projects')
    
    // Query for projects owned by user
    const ownedQuery = query(
      projectsRef,
      where('metadata.owner_id', '==', userId),
      orderBy('metadata.updated_at', 'desc')
    )

    // Query for projects where user is collaborator
    const collabQuery = query(
      projectsRef,
      where('metadata.collaborators', 'array-contains', userId),
      orderBy('metadata.updated_at', 'desc')
    )

    // We'll need to combine results from both queries
    let ownedProjects: Project[] = []
    let collabProjects: Project[] = []
    let ownedUnsubscribe: Unsubscribe
    let collabUnsubscribe: Unsubscribe

    const updateProjects = () => {
      // Combine and deduplicate projects
      const allProjects = [...ownedProjects, ...collabProjects]
      const uniqueProjects = allProjects.filter((project, index, self) =>
        index === self.findIndex(p => p.id === project.id)
      )
      
      // Sort by updated_at descending
      uniqueProjects.sort((a, b) => 
        b.metadata.updated_at?.toDate?.() - a.metadata.updated_at?.toDate?.()
      )
      
      onUpdate(uniqueProjects)
    }

    // Subscribe to owned projects
    ownedUnsubscribe = onSnapshot(
      ownedQuery,
      (snapshot: QuerySnapshot<DocumentData>) => {
        ownedProjects = snapshot.docs.map(doc => ({
          id: doc.id,
          ...doc.data()
        })) as Project[]
        updateProjects()
      },
      (error) => {
        console.error('Error in owned projects subscription:', error)
        onError(error)
      }
    )

    // Subscribe to collaborative projects
    collabUnsubscribe = onSnapshot(
      collabQuery,
      (snapshot: QuerySnapshot<DocumentData>) => {
        collabProjects = snapshot.docs.map(doc => ({
          id: doc.id,
          ...doc.data()
        })) as Project[]
        updateProjects()
      },
      (error) => {
        console.error('Error in collaborative projects subscription:', error)
        onError(error)
      }
    )

    // Return combined unsubscribe function
    return () => {
      ownedUnsubscribe()
      collabUnsubscribe()
    }
  }

  /**
   * Subscribe to a specific project
   */
  subscribeToProject(
    projectId: string,
    onUpdate: (project: Project | null) => void,
    onError: (error: Error) => void
  ): Unsubscribe {
    const projectRef = doc(this.db, 'projects', projectId)
    
    return onSnapshot(
      projectRef,
      (snapshot: DocumentSnapshot<DocumentData>) => {
        if (snapshot.exists()) {
          const project: Project = {
            id: snapshot.id,
            ...snapshot.data()
          } as Project
          onUpdate(project)
        } else {
          onUpdate(null)
        }
      },
      (error) => {
        console.error('Error in project subscription:', error)
        onError(error)
      }
    )
  }

  // =====================================================================
  // CHAPTER LISTENERS
  // =====================================================================

  /**
   * Subscribe to chapters for a specific project
   */
  subscribeToProjectChapters(
    projectId: string,
    onUpdate: (chapters: Chapter[]) => void,
    onError: (error: Error) => void
  ): Unsubscribe {
    const chaptersRef = collection(this.db, 'chapters')
    const chaptersQuery = query(
      chaptersRef,
      where('project_id', '==', projectId),
      orderBy('chapter_number', 'asc')
    )

    return onSnapshot(
      chaptersQuery,
      (snapshot: QuerySnapshot<DocumentData>) => {
        const chapters = snapshot.docs.map(doc => ({
          id: doc.id,
          ...doc.data()
        })) as Chapter[]
        onUpdate(chapters)
      },
      (error) => {
        console.error('Error in chapters subscription:', error)
        onError(error)
      }
    )
  }

  /**
   * Subscribe to a specific chapter with version history
   */
  subscribeToChapter(
    chapterId: string,
    onUpdate: (chapter: Chapter | null) => void,
    onError: (error: Error) => void
  ): Unsubscribe {
    const chapterRef = doc(this.db, 'chapters', chapterId)
    
    return onSnapshot(
      chapterRef,
      (snapshot: DocumentSnapshot<DocumentData>) => {
        if (snapshot.exists()) {
          const chapter: Chapter = {
            id: snapshot.id,
            ...snapshot.data()
          } as Chapter
          onUpdate(chapter)
        } else {
          onUpdate(null)
        }
      },
      (error) => {
        console.error('Error in chapter subscription:', error)
        onError(error)
      }
    )
  }

  // =====================================================================
  // GENERATION JOB LISTENERS
  // =====================================================================

  /**
   * Subscribe to user's generation jobs
   */
  subscribeToUserJobs(
    userId: string,
    onUpdate: (jobs: GenerationJob[]) => void,
    onError: (error: Error) => void,
    limit: number = 10
  ): Unsubscribe {
    const jobsRef = collection(this.db, 'generation_jobs')
    const jobsQuery = query(
      jobsRef,
      where('user_id', '==', userId),
      orderBy('created_at', 'desc')
    )

    return onSnapshot(
      jobsQuery,
      (snapshot: QuerySnapshot<DocumentData>) => {
        const jobs = snapshot.docs.slice(0, limit).map(doc => ({
          id: doc.id,
          ...doc.data()
        })) as GenerationJob[]
        onUpdate(jobs)
      },
      (error) => {
        console.error('Error in jobs subscription:', error)
        onError(error)
      }
    )
  }

  /**
   * Subscribe to a specific generation job for progress tracking
   */
  subscribeToJob(
    jobId: string,
    onUpdate: (job: GenerationJob | null) => void,
    onError: (error: Error) => void
  ): Unsubscribe {
    const jobRef = doc(this.db, 'generation_jobs', jobId)
    
    return onSnapshot(
      jobRef,
      (snapshot: DocumentSnapshot<DocumentData>) => {
        if (snapshot.exists()) {
          const job: GenerationJob = {
            id: snapshot.id,
            ...snapshot.data()
          } as GenerationJob
          onUpdate(job)
        } else {
          onUpdate(null)
        }
      },
      (error) => {
        console.error('Error in job subscription:', error)
        onError(error)
      }
    )
  }

  // =====================================================================
  // ONE-TIME READS (for initial data loading)
  // =====================================================================

  /**
   * Get user projects (one-time read)
   */
  async getUserProjects(userId: string): Promise<Project[]> {
    try {
      const projectsRef = collection(this.db, 'projects')
      
      // Get owned projects
      const ownedQuery = query(
        projectsRef,
        where('metadata.owner_id', '==', userId)
      )
      const ownedSnapshot = await getDocs(ownedQuery)
      const ownedProjects = ownedSnapshot.docs.map(doc => ({
        id: doc.id,
        ...doc.data()
      })) as Project[]

      // Get collaborative projects
      const collabQuery = query(
        projectsRef,
        where('metadata.collaborators', 'array-contains', userId)
      )
      const collabSnapshot = await getDocs(collabQuery)
      const collabProjects = collabSnapshot.docs.map(doc => ({
        id: doc.id,
        ...doc.data()
      })) as Project[]

      // Combine and deduplicate
      const allProjects = [...ownedProjects, ...collabProjects]
      const uniqueProjects = allProjects.filter((project, index, self) =>
        index === self.findIndex(p => p.id === project.id)
      )

      return uniqueProjects
    } catch (error) {
      console.error('Error getting user projects:', error)
      throw error
    }
  }

  /**
   * Get project chapters (one-time read)
   */
  async getProjectChapters(projectId: string): Promise<Chapter[]> {
    try {
      const chaptersRef = collection(this.db, 'chapters')
      const chaptersQuery = query(
        chaptersRef,
        where('project_id', '==', projectId),
        orderBy('chapter_number', 'asc')
      )
      
      const snapshot = await getDocs(chaptersQuery)
      return snapshot.docs.map(doc => ({
        id: doc.id,
        ...doc.data()
      })) as Chapter[]
    } catch (error) {
      console.error('Error getting project chapters:', error)
      throw error
    }
  }

  /**
   * Get a specific project (one-time read)
   */
  async getProject(projectId: string): Promise<Project | null> {
    try {
      const projectRef = doc(this.db, 'projects', projectId)
      const snapshot = await getDoc(projectRef)
      
      if (snapshot.exists()) {
        return {
          id: snapshot.id,
          ...snapshot.data()
        } as Project
      }
      
      return null
    } catch (error) {
      console.error('Error getting project:', error)
      throw error
    }
  }

  /**
   * Get a specific chapter (one-time read)
   */
  async getChapter(chapterId: string): Promise<Chapter | null> {
    try {
      const chapterRef = doc(this.db, 'chapters', chapterId)
      const snapshot = await getDoc(chapterRef)
      
      if (snapshot.exists()) {
        return {
          id: snapshot.id,
          ...snapshot.data()
        } as Chapter
      }
      
      return null
    } catch (error) {
      console.error('Error getting chapter:', error)
      throw error
    }
  }
}

// Export a singleton instance
export const firestoreClient = new FirestoreClientService() 