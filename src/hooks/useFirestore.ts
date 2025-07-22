/**
 * React hooks for real-time data integration via API endpoints
 * Uses intelligent polling to simulate real-time experience while avoiding Firestore permission issues
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { useAuth, useUser } from '@clerk/nextjs'
import { firestoreClient, Project, Chapter, GenerationJob, ensureFirebaseInitialized, authenticateWithFirebase } from '@/lib/firestore-client'

// Type definitions (keeping the same interface for backward compatibility)
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

// =====================================================================
// POLLING CONFIGURATION
// =====================================================================

const POLLING_INTERVALS = {
  projects: 10000,      // 10 seconds - less frequent updates
  chapters: 5000,       // 5 seconds - moderate updates
  activeJobs: 2000,     // 2 seconds - frequent updates for active jobs
  completedJobs: 30000, // 30 seconds - infrequent updates for completed jobs
}

// =====================================================================
// SHARED UTILITIES
// =====================================================================

async function getAuthHeaders(): Promise<Record<string, string>> {
  // This will be implemented using the auth context
  return {}
}

function usePolling<T>(
  fetcher: () => Promise<T>,
  interval: number,
  enabled: boolean = true
): { data: T | null; loading: boolean; error: Error | null; refresh: () => void } {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const intervalRef = useRef<NodeJS.Timeout | null>(null)
  const isMountedRef = useRef(true)

  const fetchData = useCallback(async () => {
    if (!enabled || !isMountedRef.current) return

    try {
      setError(null)
      const result = await fetcher()
      if (isMountedRef.current) {
        setData(result)
        setLoading(false)
      }
    } catch (err) {
      if (isMountedRef.current) {
        setError(err as Error)
        setLoading(false)
      }
    }
  }, [fetcher, enabled])

  const refresh = useCallback(() => {
    fetchData()
  }, [fetchData])

  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      return
    }

    // Initial fetch
    fetchData()

    // Set up polling
    intervalRef.current = setInterval(fetchData, interval)

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
    }
  }, [fetchData, interval, enabled])

  useEffect(() => {
    return () => {
      isMountedRef.current = false
    }
  }, [])

  return { data, loading, error, refresh }
}

/**
 * Hook to ensure Firebase is initialized before performing operations
 */
function useFirebaseReady() {
  const [isReady, setIsReady] = useState(false)
  
  useEffect(() => {
    ensureFirebaseInitialized().then(setIsReady)
  }, [])
  
  return isReady
}

// =====================================================================
// PROJECT HOOKS
// =====================================================================

/**
 * Hook to get user's projects with intelligent polling
 */
export function useUserProjects() {
  const { userId, isLoaded, isSignedIn, getToken } = useAuth()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const firebaseReady = useFirebaseReady()

  const fetchProjects = useCallback(async () => {
    if (!isSignedIn || !userId || !firebaseReady) {
      setLoading(false)
      return
    }

    try {
      setLoading(true)
      setError(null)
      
      // Ensure Firebase is ready before attempting Firestore operations
      const ready = await ensureFirebaseInitialized()
      if (!ready) {
        console.warn('⚠️ Firebase not ready for Firestore operations')
        setError('Offline mode - some features may be limited')
        return
      }

      const token = await getToken()
      if (!token) {
        setError('Authentication required')
        return
      }

      // Skip Firebase authentication - using Clerk only
      console.log('🔧 Skipping Firebase authentication - using Clerk authentication only')
      
      // Use backend APIs to fetch projects
      console.log('🔧 Fetching projects from backend API')
      
      try {
        const response = await fetch('/api/projects', {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        })
        
        if (response.ok) {
          const data = await response.json()
          console.log('📊 Raw backend response:', data)
          const backendProjects = data.projects || []
          
          // Convert backend format to frontend format
          const formattedProjects: Project[] = backendProjects.map((project: any) => ({
            id: project.id,
            metadata: {
              project_id: project.id,
              title: project.title || `Project ${project.id}`,
              owner_id: userId,
              collaborators: [],
              status: project.status || 'active',
              visibility: 'private',
              created_at: project.created_at ? new Date(project.created_at) : new Date(),
              updated_at: project.updated_at ? new Date(project.updated_at) : new Date()
            },
            settings: {
              genre: project.genre || project.settings?.genre || 'Fiction',
              target_chapters: project.settings?.target_chapters || 25,
              word_count_per_chapter: project.settings?.word_count_per_chapter || 3800,
              target_audience: 'Adult',
              writing_style: 'Narrative',
              quality_gates_enabled: true,
              auto_completion_enabled: true
            },
            progress: {
              chapters_completed: 0,
              current_word_count: 0,
              target_word_count: (project.settings?.target_chapters || 25) * (project.settings?.word_count_per_chapter || 3800),
              completion_percentage: 0,
              last_chapter_generated: 0,
              quality_baseline: {
                prose: 0,
                character: 0,
                story: 0,
                emotion: 0,
                freshness: 0,
                engagement: 0
              }
            }
          }))
          
          console.log('🔧 Fetched projects from backend:', formattedProjects.length)
          setProjects(formattedProjects)
        } else {
          console.error('Failed to fetch projects from backend:', response.status, await response.text())
          setProjects([])
        }
      } catch (error) {
        console.error('Error fetching projects from backend:', error)
        setProjects([])
      }
      
      setLoading(false)
      
      // Return empty unsubscribe function
      return () => {}
    } catch (err) {
      console.error('Error setting up projects subscription:', err)
      setError('Failed to load projects')
      setLoading(false)
    }
  }, [isSignedIn, userId, getToken, firebaseReady])

  useEffect(() => {
    let unsubscribe: (() => void) | undefined

    const setupSubscription = async () => {
      unsubscribe = await fetchProjects()
    }

    setupSubscription()

    return () => {
      if (unsubscribe) {
        unsubscribe()
      }
    }
  }, [fetchProjects])

  return { projects, loading, error, refetch: fetchProjects }
}

/**
 * Hook to get a specific project with polling
 */
export function useProject(projectId: string | null) {
  const { userId, isLoaded, isSignedIn, getToken } = useAuth()

     const fetcher = useCallback(async (): Promise<Project | null> => {
     if (!isSignedIn || !userId || !projectId) return null

     // Check if this is the current project in localStorage
     const lastProjectId = localStorage.getItem('lastProjectId')
     if (projectId !== lastProjectId) return null

     // Create project from localStorage data
     const bookBible = localStorage.getItem(`bookBible-${projectId}`)
     
     return {
       id: projectId,
       metadata: {
         project_id: projectId,
         title: `Project ${projectId.split('-')[1] || 'Unknown'}`,
         owner_id: userId,
         collaborators: [],
         status: 'active' as const,
         visibility: 'private' as const,
         created_at: new Date(),
         updated_at: new Date()
       },
       book_bible: bookBible ? {
         content: bookBible,
         last_modified: new Date(),
         modified_by: userId,
         version: 1,
         word_count: bookBible.split(' ').length
       } : undefined,
       settings: {
         genre: 'Fiction',
         target_chapters: 25,
         word_count_per_chapter: 3800,
         target_audience: 'Adult',
         writing_style: 'Narrative',
         quality_gates_enabled: true,
         auto_completion_enabled: true
       },
       progress: {
         chapters_completed: 0,
         current_word_count: 0,
         target_word_count: 95000,
         completion_percentage: 0,
         last_chapter_generated: 0,
         quality_baseline: {
           prose: 0,
           character: 0,
           story: 0,
           emotion: 0,
           freshness: 0,
           engagement: 0
         }
       }
     }
   }, [isSignedIn, userId, projectId, getToken])

  const { data: project, loading, error, refresh } = usePolling(
    fetcher,
    POLLING_INTERVALS.projects,
    isLoaded && isSignedIn && !!projectId
  )

  return {
    project,
    loading,
    error,
    refreshProject: refresh
  }
}

// =====================================================================
// CHAPTER HOOKS
// =====================================================================

/**
 * Hook to get project chapters with polling
 */
export function useProjectChapters(projectId: string | null) {
  const { userId, isLoaded, isSignedIn, getToken } = useAuth()

     const fetcher = useCallback(async (): Promise<Chapter[]> => {
     if (!isSignedIn || !userId || !projectId) return []

     const token = await getToken()
     const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {}

     const response = await fetch(`/api/chapters?project_id=${encodeURIComponent(projectId)}`, { headers })
     if (!response.ok) {
       throw new Error(`Failed to fetch chapters: ${response.statusText}`)
     }

     const data = await response.json()
     const chapters = data.chapters || []
     
     // Convert old format to new format
     return chapters.map((chapter: any, index: number) => ({
       id: `${projectId}-${chapter.chapter}`,
       project_id: projectId,
       chapter_number: chapter.chapter,
       content: '', // Will be loaded on demand
       title: `Chapter ${chapter.chapter}`,
       metadata: {
         word_count: chapter.word_count || 0,
         target_word_count: chapter.target_word_count || 3800,
         created_by: userId,
         stage: 'complete' as const,
         generation_time: chapter.generation_time || 0,
         retry_attempts: 0,
         model_used: 'gpt-4',
         created_at: new Date(chapter.created_at),
         updated_at: new Date(chapter.created_at)
       },
       quality_scores: {
         overall_rating: chapter.quality_score || 0,
         engagement_score: 0,
         craft_scores: {
           prose: 0,
           character: 0,
           story: 0,
           emotion: 0,
           freshness: 0
         }
       },
       versions: []
     }))
   }, [isSignedIn, userId, projectId, getToken])

  const { data: chapters, loading, error, refresh } = usePolling(
    fetcher,
    POLLING_INTERVALS.chapters,
    isLoaded && isSignedIn && !!projectId
  )

  return {
    chapters: chapters || [],
    loading,
    error,
    refreshChapters: refresh
  }
}

/**
 * Hook to get a specific chapter with polling
 */
export function useChapter(chapterId: string | null) {
  const { userId, isLoaded, isSignedIn, getToken } = useAuth()

     const fetcher = useCallback(async (): Promise<Chapter | null> => {
     if (!isSignedIn || !userId || !chapterId) return null

     const token = await getToken()
     const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {}

     // Parse chapter ID to get chapter number
     const chapterNumber = chapterId.split('-').pop()
     if (!chapterNumber) return null

     const response = await fetch(`/api/chapters/${chapterNumber}`, { headers })
     if (!response.ok) {
       if (response.status === 404) return null
       throw new Error(`Failed to fetch chapter: ${response.statusText}`)
     }

     const data = await response.json()
     const chapterData = data.chapter
     
     // Convert to new format
     return {
       id: chapterId,
       project_id: chapterData.project_id || localStorage.getItem('lastProjectId') || 'unknown',
       chapter_number: parseInt(chapterNumber),
       content: chapterData.content || '',
       title: chapterData.title || `Chapter ${chapterNumber}`,
       metadata: {
         word_count: chapterData.word_count || 0,
         target_word_count: chapterData.target_word_count || 3800,
         created_by: userId,
         stage: 'complete' as const,
         generation_time: chapterData.generation_time || 0,
         retry_attempts: 0,
         model_used: 'gpt-4',
         created_at: new Date(chapterData.created_at || Date.now()),
         updated_at: new Date(chapterData.updated_at || Date.now())
       },
       quality_scores: {
         overall_rating: chapterData.quality_score || 0,
         engagement_score: 0,
         craft_scores: {
           prose: 0,
           character: 0,
           story: 0,
           emotion: 0,
           freshness: 0
         }
       },
       versions: []
     }
   }, [isSignedIn, userId, chapterId, getToken])

  const { data: chapter, loading, error, refresh } = usePolling(
    fetcher,
    POLLING_INTERVALS.chapters,
    isLoaded && isSignedIn && !!chapterId
  )

  return {
    chapter,
    loading,
    error,
    refreshChapter: refresh
  }
}

// =====================================================================
// GENERATION JOB HOOKS
// =====================================================================

/**
 * Hook to get user's generation jobs with adaptive polling
 */
export function useUserJobs(limit: number = 10) {
  const { userId, isLoaded, isSignedIn, getToken } = useAuth()

  const fetcher = useCallback(async (): Promise<GenerationJob[]> => {
    if (!isSignedIn || !userId) return []

    const token = await getToken()
    const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {}

    const response = await fetch(`/api/auto-complete/jobs?limit=${limit}`, { headers })
    if (!response.ok) {
      throw new Error(`Failed to fetch jobs: ${response.statusText}`)
    }

    const data = await response.json()
    return data.jobs || []
  }, [isSignedIn, userId, limit, getToken])

  const { data: jobs, loading, error, refresh } = usePolling(
    fetcher,
    POLLING_INTERVALS.activeJobs, // Use fast polling for jobs
    isLoaded && isSignedIn
  )

  return {
    jobs: jobs || [],
    loading,
    error
  }
}

/**
 * Hook to get a specific generation job with frequent polling
 */
export function useGenerationJob(jobId: string | null) {
  const { userId, isLoaded, isSignedIn, getToken } = useAuth()

  const fetcher = useCallback(async (): Promise<GenerationJob | null> => {
    if (!isSignedIn || !userId || !jobId) return null

    const token = await getToken()
    const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {}

    const response = await fetch(`/api/auto-complete/${jobId}/status`, { headers })
    if (!response.ok) {
      if (response.status === 404) return null
      throw new Error(`Failed to fetch job: ${response.statusText}`)
    }

    const data = await response.json()
    return data.job
  }, [isSignedIn, userId, jobId, getToken])

  const { data: job, loading, error, refresh } = usePolling(
    fetcher,
    POLLING_INTERVALS.activeJobs,
    isLoaded && isSignedIn && !!jobId
  )

  return {
    job,
    loading,
    error
  }
}

// =====================================================================
// UTILITY HOOKS
// =====================================================================

/**
 * Hook to track online/offline status for better UX during connectivity issues
 */
export function useOnlineStatus() {
  const [isOnline, setIsOnline] = useState(true)

  useEffect(() => {
    const handleOnline = () => setIsOnline(true)
    const handleOffline = () => setIsOnline(false)

    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)

    // Check initial status
    setIsOnline(navigator.onLine)

    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  return isOnline
}

/**
 * Hook to provide real-time status indicators
 */
export function useRealtimeStatus() {
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date())
  const [connectionStatus, setConnectionStatus] = useState<'connected' | 'disconnected' | 'reconnecting'>('connected')
  const isOnline = useOnlineStatus()

  useEffect(() => {
    if (isOnline) {
      setConnectionStatus('connected')
      setLastUpdate(new Date())
    } else {
      setConnectionStatus('disconnected')
    }
  }, [isOnline])

  const markUpdate = useCallback(() => {
    setLastUpdate(new Date())
    setConnectionStatus('connected')
  }, [])

  return {
    lastUpdate,
    connectionStatus,
    isOnline,
    markUpdate
  }
}

/**
 * Hook for optimistic updates with rollback capability
 */
export function useOptimisticUpdates<T>() {
  const [optimisticData, setOptimisticData] = useState<T | null>(null)
  const [pendingUpdates, setPendingUpdates] = useState<Set<string>>(new Set())

  const applyOptimisticUpdate = useCallback((updateId: string, newData: T) => {
    setOptimisticData(newData)
    setPendingUpdates(prev => new Set(prev).add(updateId))
  }, [])

  const confirmUpdate = useCallback((updateId: string) => {
    setPendingUpdates(prev => {
      const newSet = new Set(prev)
      newSet.delete(updateId)
      return newSet
    })
    
    if (pendingUpdates.size === 1) {
      setOptimisticData(null)
    }
  }, [pendingUpdates.size])

  const rollbackUpdate = useCallback((updateId: string) => {
    setPendingUpdates(prev => {
      const newSet = new Set(prev)
      newSet.delete(updateId)
      return newSet
    })
    setOptimisticData(null)
  }, [])

  return {
    optimisticData,
    hasPendingUpdates: pendingUpdates.size > 0,
    applyOptimisticUpdate,
    confirmUpdate,
    rollbackUpdate
  }
} 