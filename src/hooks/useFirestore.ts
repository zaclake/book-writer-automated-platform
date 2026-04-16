/**
 * React hooks for real-time data integration via API endpoints
 * Uses intelligent polling to simulate real-time experience while avoiding Firestore permission issues
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { useAuthToken, ANONYMOUS_USER } from '@/lib/auth'
import { firestoreClient, Project, Chapter, GenerationJob, ensureFirebaseInitialized, authenticateWithFirebase } from '@/lib/firestore-client'
import { fetchApi } from '@/lib/api-client'
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
    book_length_tier?: string
    estimated_chapters?: number
    target_word_count?: number
    source_data?: any
  }
  settings: {
    genre: string
    target_chapters: number
    word_count_per_chapter: number
    target_audience: string
    writing_style: string
    quality_gates_enabled: boolean
    auto_completion_enabled: boolean
    involvement_level: string
    purpose: string
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
  cover_art_url?: string
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
  projects: 300000,     // 5 minutes - much less frequent for dashboard
  chapters: 180000,     // 3 minutes - less disruptive for chapters
  activeJobs: 15000,    // 15 seconds - still responsive for active jobs
  completedJobs: 600000, // 10 minutes - very infrequent for completed jobs
}

// =====================================================================
// SHARED UTILITIES
// =====================================================================

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
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  const fetchData = useCallback(async () => {
    if (!isMountedRef.current) return

    try {
      setError(null)
      const result = await fetcherRef.current()
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
  }, [])

  const refresh = useCallback(() => {
    fetchData()
  }, [fetchData])

  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      return
    }

    let isPageVisible = !document.hidden

    fetchData()

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

    let lastRefreshTime = 0
    const REFRESH_COOLDOWN = 30000
    
    const handleVisibilityChange = () => {
      isPageVisible = !document.hidden
      if (isPageVisible) {
        const now = Date.now()
        if (now - lastRefreshTime > REFRESH_COOLDOWN) {
          lastRefreshTime = now
          fetchData()
        }
        startPolling()
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
  const { getAuthHeaders, isLoaded, isSignedIn, user } = useAuthToken()
  const userId = user?.id || ANONYMOUS_USER.id
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const intervalRef = useRef<NodeJS.Timeout | undefined>()
  const inFlightRef = useRef<AbortController | null>(null)
  // Track initial successful load to avoid UI flashing/loading-on-focus
  const hasLoadedOnce = useRef(false)

  const fetchProjects = useCallback(async () => {
    if (!isLoaded) {
      return
    }
    if (!isSignedIn) {
      setProjects([])
      setLoading(false)
      return
    }

    if (inFlightRef.current) {
      return
    }

    const controller = new AbortController()
    inFlightRef.current = controller
    const timeoutId: ReturnType<typeof setTimeout> = setTimeout(() => {
      controller.abort()
    }, 20000)

    try {
      if (!hasLoadedOnce.current) {
        setLoading(true)
      }
      setError(null)

      const authHeaders = await getAuthHeaders()

      try {
        const response = await fetchApi('/api/v2/projects', {
          method: 'GET',
          headers: {
            ...authHeaders,
            'Content-Type': 'application/json'
          },
          signal: controller.signal
        })
        
        if (response.ok) {
          const data = await response.json()
          const backendProjects = data.projects || []

          const formattedProjects: Project[] = backendProjects.map((project: any) => {
            const finalTitle = (project.metadata?.title && project.metadata.title.trim())
              ? project.metadata.title.trim()
              : localStorage.getItem(`projectTitle-${project.id}`)
                ? localStorage.getItem(`projectTitle-${project.id}`)
                : `Project ${project.id}`

            const chaptersCompleted = project.progress?.chapters_completed || 0
            const targetChapters = project.settings?.target_chapters || 25
            const wordsPerChapter = project.settings?.word_count_per_chapter || 3800

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
                target_chapters: targetChapters,
                word_count_per_chapter: wordsPerChapter,
                target_audience: project.settings?.target_audience || 'Adult',
                writing_style: project.settings?.writing_style || 'Narrative',
                quality_gates_enabled: project.settings?.quality_gates_enabled !== false,
                auto_completion_enabled: project.settings?.auto_completion_enabled !== false
              },
              progress: {
                chapters_completed: chaptersCompleted,
                current_word_count: project.progress?.current_word_count || 0,
                target_word_count: targetChapters * wordsPerChapter,
                completion_percentage: project.progress?.completion_percentage || Math.round((chaptersCompleted / targetChapters) * 100),
                last_chapter_generated: project.progress?.last_chapter_generated || 0,
                quality_baseline: project.progress?.quality_baseline || {
                  prose: 0,
                  character: 0,
                  story: 0,
                  emotion: 0,
                  freshness: 0,
                  engagement: 0
                }
              },
              cover_art_url: project.cover_art_url || undefined,
            }
          })
          setProjects(formattedProjects)
        } else {
          console.error('Failed to fetch projects from backend:', response.status, await response.text())
          setProjects([])
        }
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') {
          console.warn('Projects fetch aborted due to timeout')
        } else {
          errorMonitoring.trackProjectsLoadError(error)
          console.error('Error fetching projects from backend:', error)
          setProjects([])
        }
      }
      
      setLoading(false)
      hasLoadedOnce.current = true

      return () => {}
    } catch (err) {
      errorMonitoring.trackProjectsLoadError(err)
      console.error('Error setting up projects subscription:', err)
      setError('Failed to load projects')
      setLoading(false)
      hasLoadedOnce.current = true
    } finally {
      clearTimeout(timeoutId)
      inFlightRef.current = null
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoaded, isSignedIn, userId])

  const fetchProjectsRef = useRef(fetchProjects)
  fetchProjectsRef.current = fetchProjects

  useEffect(() => {
    let isPageVisible = !document.hidden

    fetchProjectsRef.current()
    
    const startPolling = () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
      intervalRef.current = setInterval(() => {
        if (isPageVisible) {
          fetchProjectsRef.current()
        }
      }, POLLING_INTERVALS.projects)
    }

    startPolling()

    let lastRefreshTime = 0
    const REFRESH_COOLDOWN = 30000

    const handleFocus = () => {
      const now = Date.now()
      if (now - lastRefreshTime > REFRESH_COOLDOWN) {
        lastRefreshTime = now
        fetchProjectsRef.current()
      }
    }

    const handleVisibilityChange = () => {
      isPageVisible = !document.hidden
      if (isPageVisible) {
        const now = Date.now()
        if (now - lastRefreshTime > REFRESH_COOLDOWN) {
          lastRefreshTime = now
          fetchProjectsRef.current()
        }
        startPolling()
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
  }, [isLoaded, isSignedIn])

  return { projects, loading, error, refetch: fetchProjects }
}

/**
 * Hook to get a specific project with real data and chapter counting
 */
export function useProject(projectId: string | null) {
  const { getAuthHeaders, isLoaded, isSignedIn, user } = useAuthToken()
  const userId = user?.id || ANONYMOUS_USER.id
  const [project, setProject] = useState<Project | null>(null)
  const [loading, setLoading] = useState(true)
  // Track whether we have completed the first successful load to avoid
  // repeatedly toggling the loading state during background polling which
  // causes annoying UI flashes every few seconds.
  const hasLoadedOnce = useRef(false)
  const [error, setError] = useState<string | null>(null)
  const notFoundRef = useRef(false)
  const lastProjectIdRef = useRef<string | null>(null)

  const fetchProject = useCallback(async () => {
    if (!projectId) {
      setProject(null)
      setLoading(false)
      return
    }
    if (!isLoaded) {
      return
    }
    if (!isSignedIn) {
      setProject(null)
      setLoading(false)
      return
    }

    if (lastProjectIdRef.current !== projectId) {
      lastProjectIdRef.current = projectId
      notFoundRef.current = false
      hasLoadedOnce.current = false
      setProject(null)
      setLoading(true)
    }

    if (notFoundRef.current) {
      setLoading(false)
      return
    }

    try {
      if (!hasLoadedOnce.current) {
        setLoading(true)
      }
      setError(null)

      const authHeaders = await getAuthHeaders()

      const projectResponse = await fetchApi(`/api/v2/projects/${encodeURIComponent(projectId)}`, {
        method: 'GET',
        headers: {
          ...authHeaders,
          'Content-Type': 'application/json'
        }
      })

      if (projectResponse.status === 404) {
        notFoundRef.current = true
        setProject(null)
        setError('Project not found')
        setLoading(false)
        hasLoadedOnce.current = true
        return
      }

      if (!projectResponse.ok) {
        throw new Error(`Failed to fetch project: ${projectResponse.statusText}`)
      }

      const projectData = await projectResponse.json()
      const foundProject = projectData.project || projectData

      if (!foundProject) {
        setProject(null)
        setLoading(false)
        return
      }

      const chaptersCompleted = foundProject.progress?.chapters_completed || 0
      const targetChapters = foundProject.settings?.target_chapters || 25
      const wordsPerChapter = foundProject.settings?.word_count_per_chapter || 3800

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
          word_count: foundProject.book_bible.word_count || 0,
          book_length_tier: foundProject.book_bible.book_length_tier,
          estimated_chapters: foundProject.book_bible.estimated_chapters,
          target_word_count: foundProject.book_bible.target_word_count,
          source_data: foundProject.book_bible.source_data
        } : undefined,
        settings: {
          genre: foundProject.settings?.genre || 'Fiction',
          target_chapters: targetChapters,
          word_count_per_chapter: wordsPerChapter,
          target_audience: foundProject.settings?.target_audience || 'Adult',
          writing_style: foundProject.settings?.writing_style || 'Narrative',
          quality_gates_enabled: foundProject.settings?.quality_gates_enabled !== false,
          auto_completion_enabled: foundProject.settings?.auto_completion_enabled !== false,
          involvement_level: foundProject.settings?.involvement_level || 'balanced',
          purpose: foundProject.settings?.purpose || 'personal'
        },
        progress: {
          chapters_completed: chaptersCompleted,
          current_word_count: foundProject.progress?.current_word_count || 0,
          target_word_count: targetChapters * wordsPerChapter,
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
      hasLoadedOnce.current = true

    } catch (err) {
      errorMonitoring.captureException(err as Error, { projectId: projectId || 'unknown' })
      console.error('Error fetching project:', err)
      setError('Failed to load project')
      setLoading(false)
      hasLoadedOnce.current = true
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, isLoaded, isSignedIn, userId])

  const fetchProjectRef = useRef(fetchProject)
  fetchProjectRef.current = fetchProject

  useEffect(() => {
    let intervalId: NodeJS.Timeout | undefined
    let isPageVisible = !document.hidden

    fetchProjectRef.current()
    
    const startPolling = () => {
      if (intervalId) clearInterval(intervalId)
      intervalId = setInterval(() => {
        if (isPageVisible) {
          fetchProjectRef.current()
        }
      }, POLLING_INTERVALS.projects)
    }

    startPolling()

    let lastRefreshTime = 0
    const REFRESH_COOLDOWN = 30000
    
    const handleVisibilityChange = () => {
      isPageVisible = !document.hidden
      if (isPageVisible) {
        const now = Date.now()
        if (now - lastRefreshTime > REFRESH_COOLDOWN) {
          lastRefreshTime = now
          fetchProjectRef.current()
        }
        startPolling()
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    
    return () => {
      if (intervalId) clearInterval(intervalId)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [projectId, isLoaded, isSignedIn])

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
export function useProjectChapters(
  projectId: string | null,
  options: { intervalMs?: number } = {}
) {
  const { getAuthHeaders, user } = useAuthToken()
  const userId = user?.id || ANONYMOUS_USER.id

  const fetcher = useCallback(async (): Promise<Chapter[]> => {
    if (!projectId) return []

    const authHeaders = await getAuthHeaders()

    // IMPORTANT:
    // Use Firestore-backed v2 listing, not the legacy v1 filesystem endpoint.
    const response = await fetchApi(`/api/v2/projects/${encodeURIComponent(projectId)}/chapters`, { headers: authHeaders })
    if (!response.ok) {
      throw new Error(`Failed to fetch chapters: ${response.statusText}`)
    }

    const data = await response.json()
    const chapters = Array.isArray(data?.chapters) ? data.chapters : []

    // Normalize Firestore-ish chapters into the UI Chapter shape.
    return chapters
      .map((chapter: any) => {
        const chapterNumber = Number(chapter?.chapter_number ?? chapter?.metadata?.chapter_number ?? 0)
        const title = chapter?.title || `Chapter ${chapterNumber || ''}`.trim()
        const metadata = chapter?.metadata || {}
        const quality = chapter?.quality_scores || {}

        const resolvedId = String(chapter?.id || '') || `${projectId}-${chapterNumber || '0'}`
        return {
          // Prefer real Firestore chapter id so downstream v2 endpoints work correctly.
          id: resolvedId,
          project_id: projectId,
          chapter_number: chapterNumber,
          content: String(chapter?.content || ''),
          title,
          metadata: {
            word_count: Number(metadata?.word_count ?? chapter?.word_count ?? 0),
            target_word_count: Number(metadata?.target_word_count ?? chapter?.target_word_count ?? 3800),
            created_by: String(metadata?.created_by ?? chapter?.created_by ?? userId),
            stage: (metadata?.stage || chapter?.stage || 'draft') as 'draft' | 'revision' | 'complete',
            generation_time: Number(metadata?.generation_time ?? chapter?.generation_time ?? 0),
            retry_attempts: Number(metadata?.retry_attempts ?? chapter?.retry_attempts ?? 0),
            model_used: String(metadata?.model_used ?? chapter?.model_used ?? 'unknown'),
            created_at: metadata?.created_at ?? chapter?.created_at ?? null,
            updated_at: metadata?.updated_at ?? chapter?.updated_at ?? null,
            // Preserve failure metadata when present (used by Chapters UI).
            ...(metadata?.gates_passed != null ? { gates_passed: metadata.gates_passed } : {}),
            ...(metadata?.failure_reason ? { failure_reason: metadata.failure_reason } : {}),
          } as any,
          quality_scores: {
            overall_rating: Number(quality?.overall_rating ?? 0),
            engagement_score: Number(quality?.engagement_score ?? 0),
            craft_scores: {
              prose: Number(quality?.craft_scores?.prose ?? 0),
              character: Number(quality?.craft_scores?.character ?? 0),
              story: Number(quality?.craft_scores?.story ?? 0),
              emotion: Number(quality?.craft_scores?.emotion ?? 0),
              freshness: Number(quality?.craft_scores?.freshness ?? 0),
            }
          },
          versions: Array.isArray(chapter?.versions) ? chapter.versions : []
        } as Chapter
      })
      .filter((chapter: Chapter) => Number.isFinite(chapter.chapter_number) && chapter.chapter_number > 0)
  }, [projectId, getAuthHeaders, userId])

  const { data: chapters, loading, error, refresh } = usePolling(
    fetcher,
    options.intervalMs ?? POLLING_INTERVALS.chapters,
    !!projectId
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
  const { getAuthHeaders, user } = useAuthToken()
  const userId = user?.id || ANONYMOUS_USER.id

  const fetcher = useCallback(async (): Promise<Chapter | null> => {
    if (!chapterId) return null

    const authHeaders = await getAuthHeaders()

    // Parse chapter ID to get chapter number
    const chapterNumber = chapterId.split('-').pop()
    if (!chapterNumber) return null

    const response = await fetchApi(`/api/chapters/${chapterNumber}`, { headers: authHeaders })
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
        model_used: 'gpt-4o',
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
  }, [chapterId, getAuthHeaders, userId])

  const { data: chapter, loading, error, refresh } = usePolling(
    fetcher,
    POLLING_INTERVALS.chapters,
    !!chapterId
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
export function useUserJobs(limit: number = 10, options: { enabled?: boolean } = {}) {
  const { getAuthHeaders, isLoaded, isSignedIn } = useAuthToken()
  const enabled = (options.enabled ?? true) && isLoaded && isSignedIn

  const fetcher = useCallback(async (): Promise<GenerationJob[]> => {
    const authHeaders = await getAuthHeaders()
    // Call backend directly to avoid Vercel timeouts during long jobs
    const response = await fetchApi(`/api/auto-complete/jobs?limit=${limit}`, {
      headers: authHeaders
    })
    if (!response.ok) {
      const txt = await response.text().catch(() => '')
      throw new Error(`Failed to fetch jobs: ${response.status} ${txt}`)
    }
    const data = await response.json()
    return (data?.jobs as any[]) || []
  }, [limit, getAuthHeaders])

  const { data: jobs, loading, error } = usePolling(
    fetcher,
    POLLING_INTERVALS.activeJobs, // fast polling for active jobs
    enabled
  )

  return {
    jobs: enabled ? (jobs || []) : [],
    loading: enabled ? loading : false,
    error: enabled ? error : null
  }
}

/**
 * Hook to get a specific generation job with frequent polling
 */
export function useGenerationJob(jobId: string | null) {
  const { getAuthHeaders } = useAuthToken()

  const fetcher = useCallback(async (): Promise<GenerationJob | null> => {
    if (!jobId) return null

    const authHeaders = await getAuthHeaders()
    const response = await fetchApi(`/api/auto-complete/${jobId}/status`, { headers: authHeaders })
    if (!response.ok) {
      if (response.status === 404) return null
      const txt = await response.text().catch(() => '')
      throw new Error(`Failed to fetch job: ${response.status} ${txt}`)
    }
    return (await response.json()) as any
  }, [jobId, getAuthHeaders])

  const { data: job, loading, error } = usePolling(
    fetcher,
    POLLING_INTERVALS.activeJobs,
    !!jobId
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