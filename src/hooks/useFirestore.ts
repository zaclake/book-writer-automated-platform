/**
 * React hooks for real-time data integration via API endpoints
 * Uses intelligent polling to simulate real-time experience while avoiding Firestore permission issues
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { useAuth, useUser } from '@clerk/nextjs'
import { firestoreClient, Project, Chapter, GenerationJob, ensureFirebaseInitialized, authenticateWithFirebase } from '@/lib/firestore-client'
import { errorMonitoring } from '@/lib/errorMonitoring'

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
  projects: 30000,      // 30 seconds - less frequent updates for dashboard
  chapters: 10000,      // 10 seconds - moderate updates  
  activeJobs: 3000,     // 3 seconds - frequent updates for active jobs
  completedJobs: 60000, // 60 seconds - infrequent updates for completed jobs
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

    let isPageVisible = !document.hidden

    // Initial fetch
    fetchData()

    // Set up polling with visibility check
    const startPolling = () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
      intervalRef.current = setInterval(() => {
        if (isPageVisible) {
          fetchData()
        }
      }, interval)
    }

    startPolling()

    // Handle visibility changes
    const handleVisibilityChange = () => {
      isPageVisible = !document.hidden
      if (isPageVisible) {
        fetchData() // Refresh when page becomes visible
        startPolling() // Restart polling
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
      document.removeEventListener('visibilitychange', handleVisibilityChange)
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
  const intervalRef = useRef<NodeJS.Timeout | undefined>()

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
          
          // Debug: Log what backend is returning
          console.log('📊 Backend projects response:', {
            total: backendProjects.length,
            samples: backendProjects.slice(0, 3).map(p => ({
              id: p.id,
              title: p.metadata?.title,
              hasMetadata: !!p.metadata,
              metadataKeys: p.metadata ? Object.keys(p.metadata) : []
            }))
          })
          
          // Convert backend format to frontend format with real chapter counts
          const formattedProjects: Project[] = await Promise.all(
            backendProjects.map(async (project: any) => {
              console.log('🔍 Processing project:', {
                id: project.id,
                backendTitle: project.metadata?.title,
                localStorageTitle: localStorage.getItem(`projectTitle-${project.id}`)
              })
              
              // Fetch real chapter count for each project using v2 endpoint
              let chaptersCount = 0
              try {
                const chaptersResponse = await fetch(`/api/projects/${encodeURIComponent(project.id)}/chapters`, {
                  headers: { 'Authorization': `Bearer ${token}` }
                })

                if (chaptersResponse.ok) {
                  const chaptersData = await chaptersResponse.json()
                  chaptersCount = (chaptersData.chapters || []).length
                } else {
                  console.warn(`Failed to fetch chapters count for project ${project.id}: ${chaptersResponse.status}`)
                  // Use backend progress data as fallback
                  chaptersCount = project.progress?.chapters_completed || 0
                }
              } catch (chaptersError) {
                console.warn(`Failed to fetch chapters count for project ${project.id}:`, chaptersError)
                // Use backend progress data as fallback
                chaptersCount = project.progress?.chapters_completed || 0
              }

              // Prioritize backend title, fallback to localStorage, then UUID
              const finalTitle = (project.metadata?.title && project.metadata.title.trim()) 
                ? project.metadata.title.trim()
                : localStorage.getItem(`projectTitle-${project.id}`) 
                  ? localStorage.getItem(`projectTitle-${project.id}`)
                  : `Project ${project.id}`
              
              console.log('✅ Final title chosen:', {
                projectId: project.id,
                finalTitle,
                source: (project.metadata?.title && project.metadata.title.trim()) 
                  ? 'backend' 
                  : localStorage.getItem(`projectTitle-${project.id}`) 
                    ? 'localStorage' 
                    : 'fallback'
              })
              
              return {
                id: project.id,
                metadata: {
                  project_id: project.id,
                  title: finalTitle,
                  owner_id: project.metadata?.owner_id || userId,
                  collaborators: project.metadata?.collaborators || [],
                  status: project.metadata?.status || 'active',
                  visibility: project.metadata?.visibility || 'private',
                  created_at: project.metadata?.created_at ? new Date(project.metadata.created_at) : new Date(),
                  updated_at: project.metadata?.updated_at ? new Date(project.metadata.updated_at) : new Date()
                },
                book_bible: project.book_bible ? {
                  content: project.book_bible.content,
                  last_modified: project.book_bible.last_modified ? new Date(project.book_bible.last_modified) : new Date(),
                  modified_by: project.book_bible.modified_by || userId,
                  version: project.book_bible.version || 1,
                  word_count: project.book_bible.word_count || 0
                } : undefined,
                settings: {
                  genre: project.settings?.genre || 'Fiction',
                  target_chapters: project.settings?.target_chapters || 25,
                  word_count_per_chapter: project.settings?.word_count_per_chapter || 3800,
                  target_audience: project.settings?.target_audience || 'Adult',
                  writing_style: project.settings?.writing_style || 'Narrative',
                  quality_gates_enabled: project.settings?.quality_gates_enabled !== false,
                  auto_completion_enabled: project.settings?.auto_completion_enabled !== false
                },
                progress: {
                  chapters_completed: chaptersCount, // Use real chapter count
                  current_word_count: project.progress?.current_word_count || 0,
                  target_word_count: (project.settings?.target_chapters || 25) * (project.settings?.word_count_per_chapter || 3800),
                  completion_percentage: project.progress?.completion_percentage || Math.round((chaptersCount / (project.settings?.target_chapters || 25)) * 100),
                  last_chapter_generated: project.progress?.last_chapter_generated || 0,
                  quality_baseline: project.progress?.quality_baseline || {
                    prose: 0,
                    character: 0,
                    story: 0,
                    emotion: 0,
                    freshness: 0,
                    engagement: 0
                  }
                }
              }
            })
          )
          
          console.log('🔧 Fetched projects from backend:', formattedProjects.length)
          setProjects(formattedProjects)
        } else {
          console.error('Failed to fetch projects from backend:', response.status, await response.text())
          setProjects([])
        }
      } catch (error) {
        errorMonitoring.trackProjectsLoadError(error)
        console.error('Error fetching projects from backend:', error)
        setProjects([])
      }
      
      setLoading(false)
      
      // Return empty unsubscribe function
      return () => {}
    } catch (err) {
      errorMonitoring.trackProjectsLoadError(err)
      console.error('Error setting up projects subscription:', err)
      setError('Failed to load projects')
      setLoading(false)
    }
  }, [isSignedIn, userId, getToken, firebaseReady])

  useEffect(() => {
    let isPageVisible = !document.hidden

    // Initial fetch
    fetchProjects()
    
    // Set up polling with reduced frequency using stable ref
    const startPolling = () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
      intervalRef.current = setInterval(() => {
        if (isPageVisible) {
          fetchProjects()
        }
      }, POLLING_INTERVALS.projects)
    }

    startPolling()

    // Add window focus revalidation for better UX
    const handleFocus = () => {
      fetchProjects()
    }

    // Pause/resume polling based on page visibility
    const handleVisibilityChange = () => {
      isPageVisible = !document.hidden
      if (isPageVisible) {
        fetchProjects() // Refresh when page becomes visible
        startPolling() // Restart polling
      }
    }

    window.addEventListener('focus', handleFocus)
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
      window.removeEventListener('focus', handleFocus)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [fetchProjects])

  return { projects, loading, error, refetch: fetchProjects }
}

/**
 * Hook to get a specific project with real data and chapter counting
 */
export function useProject(projectId: string | null) {
  const { userId, isLoaded, isSignedIn, getToken } = useAuth()
  const [project, setProject] = useState<Project | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchProject = useCallback(async () => {
    if (!isSignedIn || !userId || !projectId) {
      setProject(null)
      setLoading(false)
      return
    }

    try {
      setLoading(true)
      setError(null)

      const token = await getToken()
      if (!token) {
        setError('Authentication required')
        return
      }

      // Fetch project data from backend
      const projectResponse = await fetch('/api/projects', {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      })

      if (!projectResponse.ok) {
        throw new Error(`Failed to fetch projects: ${projectResponse.statusText}`)
      }

      const projectData = await projectResponse.json()
      const backendProjects = projectData.projects || []
      
      // Find the specific project
      const foundProject = backendProjects.find((p: any) => p.id === projectId)
      
      if (!foundProject) {
        setProject(null)
        setLoading(false)
        return
      }

      // Fetch chapters to get real count using v2 endpoint
      let chaptersCount = 0
      try {
        const chaptersResponse = await fetch(`/api/projects/${encodeURIComponent(projectId)}/chapters`, {
          headers: { 'Authorization': `Bearer ${token}` }
        })

        if (chaptersResponse.ok) {
          const chaptersData = await chaptersResponse.json()
          chaptersCount = (chaptersData.chapters || []).length
        } else {
          console.warn(`Failed to fetch chapters count for project ${projectId}: ${chaptersResponse.status}`)
          // Use backend progress data as fallback
          chaptersCount = foundProject.progress?.chapters_completed || 0
        }
      } catch (chaptersError) {
        console.warn('Failed to fetch chapters count:', chaptersError)
        // Use backend progress data as fallback
        chaptersCount = foundProject.progress?.chapters_completed || 0
      }

      // Format project with real chapter count
      const formattedProject: Project = {
        id: foundProject.id,
        metadata: {
          project_id: foundProject.id,
          title: (foundProject.metadata?.title && foundProject.metadata.title.trim()) || 
                 localStorage.getItem(`projectTitle-${foundProject.id}`) || 
                 `Project ${foundProject.id}`,
          owner_id: foundProject.metadata?.owner_id || userId,
          collaborators: foundProject.metadata?.collaborators || [],
          status: foundProject.metadata?.status || 'active',
          visibility: foundProject.metadata?.visibility || 'private',
          created_at: foundProject.metadata?.created_at ? new Date(foundProject.metadata.created_at) : new Date(),
          updated_at: foundProject.metadata?.updated_at ? new Date(foundProject.metadata.updated_at) : new Date()
        },
        book_bible: foundProject.book_bible ? {
          content: foundProject.book_bible.content,
          last_modified: foundProject.book_bible.last_modified ? new Date(foundProject.book_bible.last_modified) : new Date(),
          modified_by: foundProject.book_bible.modified_by || userId,
          version: foundProject.book_bible.version || 1,
          word_count: foundProject.book_bible.word_count || 0
        } : undefined,
        settings: {
          genre: foundProject.settings?.genre || 'Fiction',
          target_chapters: foundProject.settings?.target_chapters || 25,
          word_count_per_chapter: foundProject.settings?.word_count_per_chapter || 3800,
          target_audience: foundProject.settings?.target_audience || 'Adult',
          writing_style: foundProject.settings?.writing_style || 'Narrative',
          quality_gates_enabled: foundProject.settings?.quality_gates_enabled !== false,
          auto_completion_enabled: foundProject.settings?.auto_completion_enabled !== false
        },
        progress: {
          chapters_completed: chaptersCount, // Use real chapter count
          current_word_count: foundProject.progress?.current_word_count || 0,
          target_word_count: (foundProject.settings?.target_chapters || 25) * (foundProject.settings?.word_count_per_chapter || 3800),
          completion_percentage: foundProject.progress?.completion_percentage || 0,
          last_chapter_generated: foundProject.progress?.last_chapter_generated || 0,
          quality_baseline: foundProject.progress?.quality_baseline || {
            prose: 0,
            character: 0,
            story: 0,
            emotion: 0,
            freshness: 0,
            engagement: 0
          }
        }
      }

      setProject(formattedProject)
      setLoading(false)

    } catch (err) {
      errorMonitoring.captureException(err as Error, { projectId: projectId || 'unknown' })
      console.error('Error fetching project:', err)
      setError('Failed to load project')
      setLoading(false)
    }
  }, [isSignedIn, userId, projectId, getToken])

  useEffect(() => {
    let intervalId: NodeJS.Timeout | undefined
    let isPageVisible = !document.hidden

    fetchProject()
    
    // Set up polling for real-time updates with visibility check
    const startPolling = () => {
      if (intervalId) clearInterval(intervalId)
      intervalId = setInterval(() => {
        if (isPageVisible) {
          fetchProject()
        }
      }, POLLING_INTERVALS.projects)
    }

    startPolling()

    // Handle visibility changes
    const handleVisibilityChange = () => {
      isPageVisible = !document.hidden
      if (isPageVisible) {
        fetchProject()
        startPolling()
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    
    return () => {
      if (intervalId) clearInterval(intervalId)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [fetchProject])

  return {
    project,
    loading,
    error,
    refreshProject: fetchProject
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