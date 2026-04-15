'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { PlayIcon, PauseIcon, StopIcon, Cog6ToothIcon, BoltIcon } from '@heroicons/react/24/outline'
import { useAuthToken, ANONYMOUS_USER } from '@/lib/auth'
import { useProject } from '@/hooks/useFirestore'
import { AutoCompleteEstimate } from '@/types/project'
import { fetchApi } from '@/lib/api-client'
import JobProgressBanner from '@/components/JobProgressBanner'
import { GlobalLoader } from '@/stores/useGlobalLoaderStore'
import { toast } from '@/hooks/useAppToast'

interface AutoCompleteConfig {
  targetWordCount: number
  targetChapterCount: number
  minimumQualityScore: number
  maxRetriesPerChapter: number
  autoPauseOnFailure: boolean
  contextImprovementEnabled: boolean
  qualityGatesEnabled: boolean
  userReviewRequired: boolean
}

interface JobProgress {
  job_id: string
  current_step: number
  total_steps: number
  completed_steps: number
  progress_percentage: number
  estimated_time_remaining: number | null
  current_chapter: number
  chapters_completed: number
  total_chapters: number
  last_update: string
  detailed_status: string
}

interface AutoCompleteJob {
  job_id: string
  job_type: string
  status: string
  priority: string
  created_at: string
  started_at: string | null
  completed_at: string | null
  config: AutoCompleteConfig
  error: string | null
  result: any
  retries: number
  max_retries: number
  user_id: string
  project_path: string
  progress: JobProgress
}

const TERMINAL_JOB_STATUSES = new Set(['completed', 'failed', 'cancelled'])
const RUNNING_JOB_STATUSES = new Set(['running', 'generating', 'retrying', 'quality_checking'])
const CONTROLLABLE_JOB_STATUSES = new Set(['pending', 'initializing', 'paused', ...Array.from(RUNNING_JOB_STATUSES)])

function normalizeJobStatus(status: unknown) {
  return String(status || '').trim().toLowerCase()
}

interface AutoCompleteBookManagerProps {
  onJobStarted?: (jobId: string) => void
  onJobCompleted?: (jobId: string, result: any) => void
  projectId: string | null
}

export function AutoCompleteBookManager({ 
  onJobStarted, 
  onJobCompleted,
  projectId
}: AutoCompleteBookManagerProps) {
  const { getAuthHeaders, isLoaded, isSignedIn, user: authUser } = useAuthToken()
  const user = authUser || ANONYMOUS_USER
  const { project } = useProject(projectId)
  // Unified toast (sonner-rendered via AppLayout)
  const [currentJob, setCurrentJob] = useState<AutoCompleteJob | null>(null)
  const [isStarting, setIsStarting] = useState(false)
  const [isEstimating, setIsEstimating] = useState(false)
  const [showConfig, setShowConfig] = useState(false)
  const [status, setStatus] = useState('')
  const [estimation, setEstimation] = useState<AutoCompleteEstimate | null>(null)
  const [progressStream, setProgressStream] = useState<EventSource | null>(null)
  const [showConfirmModal, setShowConfirmModal] = useState(false)
  const [confirmText, setConfirmText] = useState('')
  const [showStopModal, setShowStopModal] = useState(false)
  const [stopConfirmText, setStopConfirmText] = useState('')
  const [userUsage, setUserUsage] = useState<any>(null)
  
  const [config, setConfig] = useState<AutoCompleteConfig>({
    targetWordCount: 80000,
    targetChapterCount: 20,
    minimumQualityScore: 80.0,
    maxRetriesPerChapter: 3,
    autoPauseOnFailure: true,
    contextImprovementEnabled: true,
    qualityGatesEnabled: true,
    userReviewRequired: false
  })
  const [hasUserCustomizedConfig, setHasUserCustomizedConfig] = useState(false)

  const intervalRef = useRef<NodeJS.Timeout | null>(null)
  const isInitializedRef = useRef(false)
  const progressTrackingRef = useRef<string | null>(null)
  const estimationTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const jobFinishedRef = useRef(false)
  const connectionModeRef = useRef<'sse' | 'polling'>('sse')

  // Cleanup function to prevent resource leaks
  // IMPORTANT: must be defined before any effect that references it (avoids TDZ runtime crash in prod bundles)
  const cleanupProgress = useCallback(() => {
    setProgressStream(prev => {
      if (prev) {
        prev.close()
      }
      return null
    })
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
    if (estimationTimeoutRef.current) {
      clearTimeout(estimationTimeoutRef.current)
      estimationTimeoutRef.current = null
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    progressTrackingRef.current = null
    reconnectAttemptsRef.current = 0
    jobFinishedRef.current = false
    connectionModeRef.current = 'sse'
  }, [])

  useEffect(() => {
    setHasUserCustomizedConfig(false)
  }, [projectId])

  // When project changes, reset job tracking/UI state so we don't leak state across projects.
  useEffect(() => {
    isInitializedRef.current = false
    cleanupProgress()
    setCurrentJob(null)
    setStatus('')
    setEstimation(null)
    setShowConfirmModal(false)
    setConfirmText('')
    setShowStopModal(false)
    setStopConfirmText('')
  }, [projectId, cleanupProgress])

  useEffect(() => {
    if (!project || hasUserCustomizedConfig) return
    const derivedWordCount = project.book_bible?.target_word_count
      || (project.settings?.target_chapters && project.settings?.word_count_per_chapter
        ? project.settings.target_chapters * project.settings.word_count_per_chapter
        : undefined)
    const derivedChapters = project.settings?.target_chapters

    if (derivedWordCount && derivedChapters) {
      setConfig(prev => ({
        ...prev,
        targetWordCount: derivedWordCount,
        targetChapterCount: derivedChapters
      }))
    }
  }, [project, hasUserCustomizedConfig])

  // localStorage helper functions for job persistence
  const getStoredJobId = () => {
    if (typeof window === 'undefined') return null
    return localStorage.getItem(`runningJobId-${projectId}`)
  }

  const storeJobId = (jobId: string) => {
    if (typeof window === 'undefined') return
    localStorage.setItem(`runningJobId-${projectId}`, jobId)
  }

  const clearStoredJobId = () => {
    if (typeof window === 'undefined') return
    localStorage.removeItem(`runningJobId-${projectId}`)
  }

  const updateConfig = useCallback((updates: Partial<AutoCompleteConfig>) => {
    setConfig(prev => ({ ...prev, ...updates }))
    setHasUserCustomizedConfig(true)
  }, [])

  // Fetch user usage data
  const fetchUserUsage = async () => {
    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetch('/api/users/v2/usage', {
        headers: authHeaders
      })
      
      if (response.ok) {
        const data = await response.json()
        setUserUsage(data)
      }
    } catch (error) {
      console.error('Failed to fetch user usage:', error)
    }
  }

  // Clear book bible cache when it's updated
  const clearBookBibleCache = useCallback(() => {
    if (typeof window !== 'undefined' && projectId) {
      try {
        localStorage.removeItem(`bookBible-${projectId}`)
        console.log('Cleared book bible cache for project:', projectId)
      } catch (error) {
        console.error('Failed to clear book bible cache:', error)
      }
    }
  }, [projectId])

  // Listen for book bible updates and clear cache
  useEffect(() => {
    const handleBookBibleUpdate = (event: CustomEvent) => {
      if (event.detail.projectId === projectId) {
        clearBookBibleCache()
        // Also clear estimation to force re-estimation with new bible
        setEstimation(null)
        setStatus('📝 Book Bible updated - please re-estimate')
      }
    }

    if (typeof window !== 'undefined') {
      window.addEventListener('bookBibleUpdated', handleBookBibleUpdate as EventListener)
      return () => {
        window.removeEventListener('bookBibleUpdated', handleBookBibleUpdate as EventListener)
      }
    }
  }, [projectId, clearBookBibleCache])

  // Single effect to handle initialization and job tracking
  useEffect(() => {
    const initializeAndTrack = async () => {
      // Only initialize once when authentication is ready
      if (isLoaded && isSignedIn && !isInitializedRef.current) {
        isInitializedRef.current = true
        await checkForExistingJob()
        await fetchUserUsage()
        
        // Auto-estimate cost if no active job and no existing estimation
        estimationTimeoutRef.current = setTimeout(async () => {
          if (!currentJob && !estimation) {
            await estimateAutoCompletion()
          }
        }, 1000) // Small delay to let the UI settle
      }
      
      // Handle progress tracking when job changes
      if (
        currentJob?.job_id &&
        CONTROLLABLE_JOB_STATUSES.has(normalizeJobStatus(currentJob.status)) &&
        !TERMINAL_JOB_STATUSES.has(normalizeJobStatus(currentJob.status))
      ) {
        // Prevent starting tracking for the same job twice
        if (progressTrackingRef.current !== currentJob.job_id) {
          cleanupProgress()
          progressTrackingRef.current = currentJob.job_id
          startProgressTracking(currentJob.job_id)
        }
      } else {
        // Clean up when no active job
        cleanupProgress()
      }
    }

    initializeAndTrack()
    
    return cleanupProgress
  }, [isLoaded, isSignedIn, currentJob?.job_id, currentJob?.status, cleanupProgress])

  // Reset initialization flag when user changes
  useEffect(() => {
    isInitializedRef.current = false
    cleanupProgress()
  }, [user?.id, cleanupProgress])

  // Auto-refresh estimate when config changes (only if we have an existing estimation)
  useEffect(() => {
    if (isLoaded && isSignedIn && !currentJob && estimation) {
      // Debounce config changes to avoid too many API calls
      const debounceTimer = setTimeout(async () => {
        await estimateAutoCompletion()
      }, 500)

      return () => clearTimeout(debounceTimer)
    }
  }, [config.targetWordCount, config.targetChapterCount, config.minimumQualityScore, isLoaded, isSignedIn, currentJob])

  // Check for stored running job on component mount and reconnect
  useEffect(() => {
    if (isLoaded && isSignedIn && projectId && !currentJob) {
      const storedJobId = getStoredJobId()
      if (storedJobId) {
        console.log('Found stored job ID, reconnecting:', storedJobId)
        setStatus('🔄 Reconnecting to running job...')
        startProgressTracking(storedJobId).catch(console.error)
      }
    }
  }, [isLoaded, isSignedIn, projectId])

  // Clear stored job ID when job completes or fails
  useEffect(() => {
    if (
      currentJob &&
      ['completed', 'failed', 'cancelled'].includes(normalizeJobStatus(currentJob.status))
    ) {
      clearStoredJobId()
    }
  }, [currentJob?.status])

  const checkForExistingJob = async () => {
    try {
      const authHeaders = await getAuthHeaders()
      // Use Next.js proxy to avoid CORS.
      // Backend only supports exact status filters, so we fetch a small page and filter client-side.
      const response = await fetchApi(`/api/auto-complete/jobs?limit=25`, { headers: authHeaders })
      if (response.ok) {
        const data = await response.json()
        const jobs = (data && Array.isArray((data as any).jobs) ? (data as any).jobs : []) as any[]
        const relevant = jobs
          .filter((job: any) => String(job?.project_id || '') === String(projectId || ''))
          .filter((job: any) => String(job?.job_type || '') === 'auto_complete_book')
          .sort((a: any, b: any) => {
            const aTime = Date.parse(String(a?.created_at || a?.started_at || 0))
            const bTime = Date.parse(String(b?.created_at || b?.started_at || 0))
            return (Number.isFinite(bTime) ? bTime : 0) - (Number.isFinite(aTime) ? aTime : 0)
          })

        const active = relevant.find((job: any) => !TERMINAL_JOB_STATUSES.has(normalizeJobStatus(job?.status)))
        if (active) setCurrentJob(active)
      }
    } catch (error) {
      console.error('Failed to check for existing job:', error)
    }
  }

  const startAutoCompletion = async () => {
    if (!isSignedIn) {
      setStatus('❌ Please sign in to start auto-completion')
      return
    }

    if (!projectId) {
      setStatus('❌ No project selected. Please select a project first.')
      return
    }

    if (!user?.id) {
      setStatus('❌ User not authenticated. Please sign in.')
      return
    }

    if (
      currentJob &&
      CONTROLLABLE_JOB_STATUSES.has(normalizeJobStatus(currentJob.status)) &&
      !TERMINAL_JOB_STATUSES.has(normalizeJobStatus(currentJob.status))
    ) {
      setStatus('❌ A job is already running')
      return
    }

    // Guard against SSR
    if (typeof window === 'undefined') {
      setStatus('❌ Client-side features not available')
      return
    }

    // Check for book bible before starting
    const bookBible = localStorage.getItem(`bookBible-${projectId}`)
    if (!bookBible) {
      try {
        // Try to fetch from backend
        const authHeaders = await getAuthHeaders()
        const bookBibleResponse = await fetch(`/api/book-bible/${projectId}`, {
          headers: authHeaders
        })
        
        if (!bookBibleResponse.ok) {
          setStatus('❌ Book Bible not found - please create a Book Bible first in the Book Bible tab')
          return
        }
        
        const projectData = await bookBibleResponse.json()
        const bookBibleData = projectData?.book_bible?.content
        if (!bookBibleData || bookBibleData.trim().length === 0) {
          setStatus('❌ Book Bible is empty - please create content in the Book Bible tab first')
          return
        }
        
        // Cache the book bible locally
        localStorage.setItem(`bookBible-${projectId}`, bookBibleData)
      } catch (error) {
        setStatus('❌ Unable to load Book Bible - please ensure you have created one in the Book Bible tab')
        return
      }
    }

    setIsStarting(true)
    setStatus('🚀 Starting auto-completion...')

    try {
      const authHeaders = await getAuthHeaders()
      // Use server-side proxy route to avoid client->Railway network issues
      const response = await fetch('/api/auto-complete/start', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders,
        },
        body: JSON.stringify({
        project_id: projectId,
        book_bible: bookBible || (typeof window !== 'undefined' ? localStorage.getItem(`bookBible-${projectId}`) : null),
        starting_chapter: 1,
        target_chapters: config.targetChapterCount,
        quality_threshold: config.minimumQualityScore / 10.0, // Convert from 0-100 scale to 0-10 scale
          words_per_chapter: Math.round(config.targetWordCount / config.targetChapterCount)
        })
      })

      if (response.ok) {
        const data = await response.json()
        setStatus('✅ Auto-completion started successfully!')
        setCurrentJob(null) // Will be updated by progress tracking
        const jobId = data?.job_id
        if (jobId) {
          storeJobId(jobId) // Persist job ID for recovery
          // Prime UI with a pending job so the banner shows immediately
          setCurrentJob({
            job_id: jobId,
            status: 'pending',
            progress: {
              progress_percentage: 0,
              current_step: 0,
              current_chapter: 0,
              chapters_completed: 0,
              total_chapters: estimation?.total_chapters || config.targetChapterCount,
              estimated_time_remaining: undefined,
              last_update: new Date().toISOString(),
              detailed_status: 'Starting book generation...'
            },
            retries: 0,
            max_retries: 3,
            started_at: new Date().toISOString()
          } as any)
          // Show toast notification about safe navigation
          toast({
            title: "🚀 Book generation started!",
            description: "This process takes ~30–45 minutes. You can safely navigate away; progress will continue and update here.",
            variant: "default"
          })
          GlobalLoader.show({
            title: 'Auto-completing Your Book',
            stage: 'Initializing...',
            progress: 0,
            showProgress: true,
            safeToLeave: true,
            canMinimize: true,
            customMessages: [
              'Planning chapter structure...',
              'Writing chapter content...',
              'Running quality checks...',
              'Refining prose...',
              'Checking consistency...',
            ],
            timeoutMs: 14400000,
          })
          // Wait a moment for the job to initialize before starting tracking
          setTimeout(() => {
            startProgressTracking(jobId).catch(console.error)
          }, 1000)
        }
        onJobStarted?.(jobId)
      } else {
        const errorData = await response.json().catch(() => ({}))
        if (response.status === 409) {
          setStatus(`🔄 Job already running: ${errorData.error || ''}`)
          if (errorData?.existing_job_id) {
            setStatus(`🔄 Resuming existing job: ${errorData.existing_job_id}`)
            storeJobId(errorData.existing_job_id)
            // Prime UI with pending banner
            setCurrentJob({
              job_id: errorData.existing_job_id,
              status: 'pending',
              progress: {
                progress_percentage: 0,
                current_step: 0,
                current_chapter: 0,
                chapters_completed: 0,
                total_chapters: estimation?.total_chapters || config.targetChapterCount,
                estimated_time_remaining: undefined,
                last_update: new Date().toISOString(),
                detailed_status: 'Reconnecting to running job...'
              }
            } as any)
            setTimeout(() => {
              startProgressTracking(errorData.existing_job_id).catch(console.error)
            }, 1000)
          }
        } else if (response.status === 402) {
          setStatus(`💳 Insufficient credits: ${errorData.error || ''}`)
          if (errorData?.estimated_credits && errorData?.remaining_credits) {
            setStatus(`💳 Insufficient credits: Need ${errorData.estimated_credits} > Available ${errorData.remaining_credits}`)
          }
        } else if (response.status === 504 || response.status === 408) {
          setStatus(`⏱️ Server timeout - this is normal for long operations. The job may have started. Please refresh in a few moments.`)
        } else {
          setStatus(`❌ Failed to start: ${errorData.error || 'Unknown error'}`)
        }
      }
    } catch (error) {
      setStatus(`❌ Error: ${error instanceof Error ? error.message : 'Unknown error'}`)
    } finally {
      setIsStarting(false)
    }
  }

  const estimateAutoCompletion = async () => {
    if (!isSignedIn) {
      setStatus('❌ Please sign in to get credit estimate')
      return
    }

    // Guard against SSR
    if (typeof window === 'undefined') {
      return
    }

    const currentProjectId = projectId || localStorage.getItem('lastProjectId')
    if (!currentProjectId) {
      setStatus('❌ No project selected - upload or select a Book Bible first')
      return
    }

    let bookBible = localStorage.getItem(`bookBible-${currentProjectId}`)
    if (!bookBible) {
      // Try to fetch from backend
      try {
        const authHeaders = await getAuthHeaders()
        const bookBibleResponse = await fetch(`/api/book-bible/${currentProjectId}`, {
          headers: authHeaders
        })
        
        if (bookBibleResponse.ok) {
          const projectData = await bookBibleResponse.json()
          const bookBibleData = projectData?.book_bible?.content
          if (bookBibleData && bookBibleData.trim().length > 0) {
            bookBible = bookBibleData
            // Cache it for future use
            localStorage.setItem(`bookBible-${currentProjectId}`, bookBible)
          } else {
            setStatus('❌ Book Bible is empty - please create content in the Book Bible tab first')
            return
          }
        } else {
          setStatus('❌ Book Bible not found - please create a Book Bible first in the Book Bible tab')
          return
        }
      } catch (error) {
        setStatus('❌ Unable to load Book Bible - please ensure you have created one in the Book Bible tab')
        return
      }
    }

    setIsEstimating(true)
    setStatus('🔢 Calculating credit estimate...')
    setEstimation(null)

    try {
      const requestPayload = {
        project_id: currentProjectId,
        book_bible: bookBible,
        starting_chapter: 1,
        target_chapters: config.targetChapterCount,
        quality_threshold: config.minimumQualityScore / 10.0, // Convert from 0-100 scale to 0-10 scale
        words_per_chapter: Math.round(config.targetWordCount / config.targetChapterCount)
      }
      
      try {
        const bbStr = typeof bookBible === 'string' ? bookBible : JSON.stringify(bookBible)
        console.log('Auto-complete estimate request payload:', {
          ...requestPayload,
          book_bible: `${bbStr?.substring(0, 200)}... (${bbStr?.length} chars)`
        })
      } catch {
        console.log('Auto-complete estimate request payload: [book_bible present, non-stringable]')
      }
      
      const authHeaders = await getAuthHeaders()
      const response = await fetch('/api/auto-complete/estimate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders
        },
        body: JSON.stringify(requestPayload)
      })

      const data = await response.json()

      if (response.ok) {
        setEstimation(data.estimation)
        setStatus(`🔢 Estimated usage: ${data.estimation.estimated_total_credits.toLocaleString()} credits for ${data.estimation.total_chapters} chapters`)
      } else {
        setStatus(`❌ Estimation failed: ${data.error}`)
      }
    } catch (error) {
      console.error('Auto-complete estimation error:', error)
      
      // Provide more specific error messages
      let errorMessage = 'Unknown error occurred'
      if (error instanceof Error) {
        if (error.message.includes('Backend URL not configured')) {
          errorMessage = 'Backend service not configured. Please check environment settings.'
        } else if (error.message.includes('fetch')) {
          errorMessage = 'Unable to connect to backend service. Please try again.'
        } else if (error.message.includes('timeout')) {
          errorMessage = 'Estimation timed out. Please try again.'
        } else {
          errorMessage = error.message
        }
      }
      
      setStatus(`❌ Estimation Error: ${errorMessage}`)
    } finally {
      setIsEstimating(false)
    }
  }

  const startProgressTracking = async (jobId: string, isReconnect = false) => {
    if (!isReconnect) {
      setStatus('📡 Connecting to progress updates...')
    }
    
    // First, get initial status
    fetchJobStatus(jobId)
    
    // Set up real-time SSE connection directly to backend
    try {
      const authHeaders = await getAuthHeaders()
      // Connect to Next.js server-side proxy for SSE to avoid CORS
      const eventSource = new EventSource(`/api/auto-complete/${jobId}/progress`)
      setProgressStream(eventSource)
      connectionModeRef.current = 'sse'
      
      // Reset reconnect attempts on successful connection
      if (!isReconnect) {
        reconnectAttemptsRef.current = 0
      }
      
      eventSource.onopen = () => {
        console.log('SSE connection opened successfully')
        reconnectAttemptsRef.current = 0 // Reset on successful connection
        if (isReconnect) {
          setStatus('🔄 Reconnected to progress updates')
        }
      }
      
      eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data)
        
        // Handle heartbeat messages
        if (data.type === 'heartbeat') {
          console.log('SSE heartbeat received')
          return
        }
        
        if (data.job_id && data.progress) {
          setCurrentJob(prev => {
            const previous = (prev || {}) as any
            const next: any = { ...previous }
            next.status = data.status
            next.error = data.error
            next.result = data.result
            next.progress = {
              ...(previous.progress || {}),
              progress_percentage: data.progress.progress_percentage || 0,
              current_step: data.progress.current_step || 0,
              current_chapter: data.progress.current_chapter || 0,
              chapters_completed: data.progress.chapters_completed || 0,
              total_chapters: data.progress.total_chapters || 0,
              estimated_time_remaining: data.progress.estimated_time_remaining,
              last_update: data.progress.last_update || data.timestamp,
              detailed_status: data.progress.detailed_status || `Processing chapter ${data.progress.current_chapter || 0}...`
            }
            // Keep global loader in sync during progress
            GlobalLoader.update({
              progress: next.progress.progress_percentage,
              stage: next.progress.detailed_status,
              showProgress: true,
            })
            // Handle completion
            if (data.status === 'completed') {
              jobFinishedRef.current = true
              onJobCompleted?.(jobId, data.result)
              try { eventSource.close() } catch {}
              setProgressStream(null)
              reconnectAttemptsRef.current = 0
              clearStoredJobId()
              // Finalize loader
              GlobalLoader.hide()
              // Safety: force close after short delay if any other operations kept it open
              setTimeout(() => GlobalLoader.forceHide?.(), 1500)
            }
            return next as AutoCompleteJob
          })
        }
      }
      
      // Named event listeners for better semantics
      eventSource.addEventListener('progress', (event) => {
        const data = JSON.parse(event.data)
        
        if (data.job_id && data.progress) {
          setCurrentJob(prev => {
            const previous = (prev || {}) as any
            const next: any = { ...previous }
            next.status = data.status
            next.error = data.error
            next.result = data.result
            next.progress = {
              ...(previous.progress || {}),
              progress_percentage: data.progress.progress_percentage || 0,
              current_step: data.progress.current_step || 0,
              current_chapter: data.progress.current_chapter || 0,
              chapters_completed: data.progress.chapters_completed || 0,
              total_chapters: data.progress.total_chapters || 0,
              estimated_time_remaining: data.progress.estimated_time_remaining,
              last_update: data.progress.last_update || data.timestamp,
              detailed_status: data.progress.detailed_status || `Processing chapter ${data.progress.current_chapter || 0}...`
            }
            GlobalLoader.update({
              progress: next.progress.progress_percentage,
              stage: next.progress.detailed_status,
              showProgress: true,
            })
            return next as AutoCompleteJob
          })
        }
      })
      
      eventSource.addEventListener('completion', (event) => {
        const data = JSON.parse(event.data)
        
        if (data.job_id && data.progress) {
          // Update job with final status
          jobFinishedRef.current = true
          setCurrentJob(prev => {
            const previous = (prev || {}) as any
            const next: any = { ...previous }
            next.status = data.status
            next.error = data.error
            next.result = data.result
            next.progress = {
              ...(previous.progress || {}),
              progress_percentage: data.progress.progress_percentage || 0,
              current_step: data.progress.current_step || 0,
              current_chapter: data.progress.current_chapter || 0,
              chapters_completed: data.progress.chapters_completed || 0,
              total_chapters: data.progress.total_chapters || 0,
              estimated_time_remaining: data.progress.estimated_time_remaining,
              last_update: data.progress.last_update || data.timestamp,
              detailed_status: data.progress.detailed_status || `${data.status === 'completed' ? 'Completed' : 'Failed'}`
            }
            return next as AutoCompleteJob
          })
          
          // Handle completion
          if (data.status === 'completed') {
            GlobalLoader.hide()
            onJobCompleted?.(jobId, data.result)
            setTimeout(() => GlobalLoader.forceHide?.(), 1500)
          }
          
          // Clean up SSE connection and localStorage
          eventSource.close()
          setProgressStream(null)
          reconnectAttemptsRef.current = 0
          clearStoredJobId()
        }
      })
      
      eventSource.addEventListener('error', (event) => {
        // Ignore errors after completion/intentional close
        if (jobFinishedRef.current) {
          return
        }
        const messageEvent = event as MessageEvent
        if (messageEvent.data) {
          try {
            const data = JSON.parse(messageEvent.data)
            setStatus(`❌ Stream error: ${data.message}`)
            console.error('SSE error:', data)
          } catch (e) {
            setStatus('❌ Stream error: Connection failed')
            console.error('SSE error:', event)
          }
        } else {
          setStatus('❌ Stream error: Connection failed')
          console.error('SSE error:', event)
        }
        
        // Trigger reconnection
        attemptReconnection(jobId)
        // Do not hide the global loader on transient stream errors; show reconnecting
        GlobalLoader.update({ stage: 'Connection lost. Reconnecting...', showProgress: true })
      })
      
      eventSource.onerror = (event) => {
        // Ignore errors after completion/intentional close
        if (jobFinishedRef.current) {
          return
        }
        console.error('SSE connection error:', event)
        try { eventSource.close() } catch {}
        setProgressStream(null)
        // Switch to polling quietly to avoid alarming message
        if (connectionModeRef.current !== 'polling') {
          connectionModeRef.current = 'polling'
          setStatus('Using polling updates for progress...')
          GlobalLoader.update({ stage: 'Syncing progress...', showProgress: true })
          fallbackToPolling(jobId)
        }
      }
    } catch (error) {
      console.error('Failed to create SSE connection:', error)
      // Fallback to polling immediately
      if (connectionModeRef.current !== 'polling') {
        connectionModeRef.current = 'polling'
        setStatus('Using polling updates for progress...')
        GlobalLoader.update({ stage: 'Syncing progress...', showProgress: true })
        fallbackToPolling(jobId)
      }
    }
  }

  const attemptReconnection = (jobId: string) => {
    const maxAttempts = 5
    const baseDelay = 1000 // 1 second
    
    if (reconnectAttemptsRef.current >= maxAttempts) {
      console.log('Max reconnection attempts reached, falling back to polling')
      setStatus('Using polling updates for progress...')
      GlobalLoader.update({ stage: 'Syncing progress...', showProgress: true })
      fallbackToPolling(jobId)
      return
    }
    
    reconnectAttemptsRef.current++
    const delay = baseDelay * Math.pow(2, reconnectAttemptsRef.current - 1) // Exponential backoff
    
    setStatus(`🔄 Reconnecting for live updates in ${Math.round(delay/1000)}s... (${reconnectAttemptsRef.current}/${maxAttempts})`)
    
    reconnectTimeoutRef.current = setTimeout(async () => {
      console.log(`Attempting reconnection ${reconnectAttemptsRef.current}/${maxAttempts}`)
      await startProgressTracking(jobId, true)
    }, delay)
  }

  const fallbackToPolling = (jobId: string) => {
    // Clean up any existing reconnection timeout
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    
    // Start polling fallback
    intervalRef.current = setInterval(() => {
      fetchJobStatus(jobId)
    }, 5000)
  }

  const fetchJobStatus = async (jobId: string) => {
    try {
      const authHeaders = await getAuthHeaders()
      // Use Next.js proxy route
      const response = await fetch(`/api/auto-complete/${jobId}/status`, { headers: authHeaders })
      if (response.ok) {
        const data = await response.json()
        setCurrentJob(data)
        
        // Check if job is completed
        const normalizedStatus = normalizeJobStatus((data as any)?.status)
        if (['completed', 'failed', 'cancelled'].includes(normalizedStatus)) {
          if (intervalRef.current) {
            clearInterval(intervalRef.current)
            intervalRef.current = null
          }
          clearStoredJobId()
          
          if (normalizedStatus === 'completed') {
            GlobalLoader.hide()
            onJobCompleted?.(jobId, (data as any)?.result)
            setTimeout(() => GlobalLoader.forceHide?.(), 1500)
          }
          if (normalizedStatus === 'failed' || normalizedStatus === 'cancelled') {
            GlobalLoader.hide()
            setTimeout(() => GlobalLoader.forceHide?.(), 1500)
            const errorMessage = (data as any)?.error || (data as any)?.error_message || 'Job failed. Check logs for details.'
            setStatus(`❌ Generation failed: ${errorMessage}`)
          }
        }
      } else {
        if (response.status === 404) {
          // Job not found (likely completed or stale). Stop polling and clear stored ID
          if (intervalRef.current) {
            clearInterval(intervalRef.current)
            intervalRef.current = null
          }
          clearStoredJobId()
          setCurrentJob(null)
          setStatus('ℹ️ No active job found (it may have completed).')
          return
        }
        const err = await response.json().catch(() => ({}))
        console.error('Failed to fetch job status:', err)
      }
    } catch (error) {
      console.error('Failed to fetch job status:', error)
    }
  }

  const controlJob = async (action: 'pause' | 'resume' | 'cancel') => {
    if (!currentJob) return

    try {
      const authHeaders = await getAuthHeaders()
      // Optimistic UI update (server is source of truth; we still refresh status after)
      const nextStatus =
        action === 'pause' ? 'paused' :
        action === 'resume' ? 'generating' :
        'cancelled'
      setCurrentJob(prev => (prev ? ({ ...(prev as any), status: nextStatus } as any) : prev))
      const response = await fetch(`/api/auto-complete/${currentJob.job_id}/control`, {
        method: 'POST',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({ action })
      })

      if (response.ok) {
        setStatus(`✅ Job ${action}d successfully`)
        if (action === 'cancel') {
          clearStoredJobId()
          setShowStopModal(false)
          setStopConfirmText('')
        }
        fetchJobStatus(currentJob.job_id)
      } else {
        const err = await response.json().catch(() => ({}))
        setStatus(`❌ Failed to ${action}: ${err.error || response.status}`)
        fetchJobStatus(currentJob.job_id)
      }
    } catch (error) {
      setStatus(`❌ Error: ${error instanceof Error ? error.message : 'Unknown error'}`)
      fetchJobStatus(currentJob.job_id)
    }
  }

  const formatTimeRemaining = (seconds: number | null) => {
    if (!seconds) return 'Calculating...'
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    return `${hours}h ${minutes}m`
  }

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'N/A'
    return new Date(dateString).toLocaleString()
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'text-green-600'
      case 'failed':
      case 'cancelled':
        return 'text-red-600'
      case 'running':
      case 'generating':
        return 'text-blue-600'
      case 'paused':
        return 'text-yellow-600'
      default:
        return 'text-gray-600'
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return '✅'
      case 'failed':
        return '❌'
      case 'cancelled':
        return '⏹️'
      case 'running':
      case 'generating':
        return '🚀'
      case 'paused':
        return '⏸️'
      default:
        return '⏳'
    }
  }

  return (
    <div className="card">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-4">
        <h2 className="text-lg font-semibold text-gray-900">
          Auto-Complete Book
        </h2>
        <button
          onClick={() => setShowConfig(!showConfig)}
          className="p-2 text-gray-500 hover:text-gray-700"
        >
          <Cog6ToothIcon className="w-5 h-5" />
        </button>
      </div>

      {/* Configuration Panel */}
      {showConfig && (
        <div className="mb-6 p-4 bg-gray-50 rounded-lg">
          <h3 className="text-sm font-medium text-gray-900 mb-3">Configuration</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Target Word Count
              </label>
              <input
                id="auto-complete-target-words"
                name="targetWordCount"
                type="number"
                value={config.targetWordCount}
                onChange={(e) => updateConfig({ targetWordCount: parseInt(e.target.value) })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Target Chapter Count
              </label>
              <input
                id="auto-complete-target-chapters"
                name="targetChapterCount"
                type="number"
                value={config.targetChapterCount}
                onChange={(e) => updateConfig({ targetChapterCount: parseInt(e.target.value) })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Minimum Quality Score
              </label>
              <input
                id="auto-complete-min-quality"
                name="minimumQualityScore"
                type="number"
                step="0.1"
                min="0"
                max="100"
                value={config.minimumQualityScore}
                onChange={(e) => updateConfig({ minimumQualityScore: parseFloat(e.target.value) })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Max Retries Per Chapter
              </label>
              <input
                id="auto-complete-max-retries"
                name="maxRetriesPerChapter"
                type="number"
                value={config.maxRetriesPerChapter}
                onChange={(e) => updateConfig({ maxRetriesPerChapter: parseInt(e.target.value) })}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
          </div>
          <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-2">
            <label className="flex items-center">
              <input
                id="auto-complete-auto-pause"
                name="autoPauseOnFailure"
                type="checkbox"
                checked={config.autoPauseOnFailure}
                onChange={(e) => updateConfig({ autoPauseOnFailure: e.target.checked })}
                className="mr-2"
              />
              <span className="text-sm text-gray-700">Auto-pause on failure</span>
            </label>
            <label className="flex items-center">
              <input
                id="auto-complete-context-improve"
                name="contextImprovementEnabled"
                type="checkbox"
                checked={config.contextImprovementEnabled}
                onChange={(e) => updateConfig({ contextImprovementEnabled: e.target.checked })}
                className="mr-2"
              />
              <span className="text-sm text-gray-700">Context improvement enabled</span>
            </label>
            <label className="flex items-center">
              <input
                id="auto-complete-quality-gates"
                name="qualityGatesEnabled"
                type="checkbox"
                checked={config.qualityGatesEnabled}
                onChange={(e) => updateConfig({ qualityGatesEnabled: e.target.checked })}
                className="mr-2"
              />
              <span className="text-sm text-gray-700">Quality gates enabled</span>
            </label>
            <label className="flex items-center">
              <input
                id="auto-complete-user-review"
                name="userReviewRequired"
                type="checkbox"
                checked={config.userReviewRequired}
                onChange={(e) => updateConfig({ userReviewRequired: e.target.checked })}
                className="mr-2"
              />
              <span className="text-sm text-gray-700">User review required</span>
            </label>
          </div>
        </div>
      )}

      {/* Job Progress Banner */}
      {currentJob && (() => {
        const s = normalizeJobStatus(currentJob.status as any)
        const displayStatus: 'running' | 'pending' | 'completed' | 'failed' =
          ['running','generating','retrying','quality_checking'].includes(s) ? 'running' :
          ['pending','initializing','paused'].includes(s) ? 'pending' :
          (s === 'completed' ? 'completed' : (s === 'failed' || s === 'cancelled' ? 'failed' : 'pending'))
        return (
          <JobProgressBanner
            jobId={currentJob.job_id}
            status={displayStatus}
            progressPercentage={currentJob.progress?.progress_percentage || 0}
            currentChapter={currentJob.progress?.current_chapter || 0}
            totalChapters={currentJob.progress?.total_chapters || 0}
            estimatedTimeRemaining={
              currentJob.progress?.estimated_time_remaining 
                ? typeof currentJob.progress.estimated_time_remaining === 'string' 
                  ? currentJob.progress.estimated_time_remaining 
                  : `${Math.round(currentJob.progress.estimated_time_remaining / 60)} minutes`
                : undefined
            }
            detailedStatus={currentJob.progress?.detailed_status}
            onDismiss={displayStatus === 'completed' || displayStatus === 'failed' ? () => setCurrentJob(null) : undefined}
          />
        )
      })()}

      {/* Current Job Status */}
      {currentJob ? (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div className="flex items-center space-x-2">
              <span className="text-lg">{getStatusIcon(currentJob.status)}</span>
              <span className={`font-medium ${getStatusColor(currentJob.status)}`}>
                {currentJob.status.toUpperCase()}
              </span>
            </div>
            <div className="flex flex-wrap gap-2">
              {RUNNING_JOB_STATUSES.has(normalizeJobStatus(currentJob.status)) && (
                <button
                  onClick={() => controlJob('pause')}
                  className="flex items-center px-3 py-1 bg-yellow-100 text-yellow-800 rounded-md hover:bg-yellow-200"
                >
                  <PauseIcon className="w-4 h-4 mr-1" />
                  Pause
                </button>
              )}
              {normalizeJobStatus(currentJob.status) === 'paused' && (
                <button
                  onClick={() => controlJob('resume')}
                  className="flex items-center px-3 py-1 bg-green-100 text-green-800 rounded-md hover:bg-green-200"
                >
                  <PlayIcon className="w-4 h-4 mr-1" />
                  Resume
                </button>
              )}
              {CONTROLLABLE_JOB_STATUSES.has(normalizeJobStatus(currentJob.status)) &&
                !TERMINAL_JOB_STATUSES.has(normalizeJobStatus(currentJob.status)) && (
                <button
                  onClick={() => setShowStopModal(true)}
                  className="flex items-center px-3 py-1 bg-red-100 text-red-800 rounded-md hover:bg-red-200"
                >
                  <StopIcon className="w-4 h-4 mr-1" />
                  Stop
                </button>
              )}
            </div>
          </div>
          <div className="text-xs text-gray-500">
            Pause takes effect between chapters. Stop cancels the job.
          </div>

          {/* Progress Bar */}
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span>Progress</span>
              <span>{Math.round(currentJob.progress.progress_percentage)}%</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div
                className="bg-primary-600 h-2 rounded-full transition-all duration-500"
                style={{ width: `${currentJob.progress.progress_percentage}%` }}
              />
            </div>
          </div>

          {/* Chapter Progress */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-gray-600">Current Chapter:</span>
              <span className="ml-2 font-medium">{currentJob.progress.current_chapter}</span>
            </div>
            <div>
              <span className="text-gray-600">Chapters Completed:</span>
              <span className="ml-2 font-medium">
                {currentJob.progress.chapters_completed} / {currentJob.progress.total_chapters}
              </span>
            </div>
            <div>
              <span className="text-gray-600">Time Remaining:</span>
              <span className="ml-2 font-medium">
                {formatTimeRemaining(currentJob.progress.estimated_time_remaining)}
              </span>
            </div>
            <div>
              <span className="text-gray-600">Retries:</span>
              <span className="ml-2 font-medium">{currentJob.retries} / {currentJob.max_retries}</span>
            </div>
          </div>

          {/* Detailed Status */}
          <div className="p-3 bg-gray-50 rounded-lg">
            <div className="text-sm font-medium text-gray-900 mb-1">Status Details</div>
            <div className="text-sm text-gray-700">{currentJob.progress.detailed_status}</div>
          </div>

          {/* Error Display */}
          {currentJob.error && (
            <div className="p-3 bg-red-50 rounded-lg">
              <div className="text-sm font-medium text-red-900 mb-1">Error</div>
              <div className="text-sm text-red-700">{currentJob.error}</div>
            </div>
          )}

          {/* Job Info */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs text-gray-600">
            <div>
              <span>Started:</span>
              <span className="ml-2">{formatDate(currentJob.started_at)}</span>
            </div>
            <div>
              <span>Job ID:</span>
              <span className="ml-2 font-mono">{(currentJob.job_id || '').substring(0, 8)}...</span>
            </div>
          </div>
        </div>
      ) : (
        <div className="text-center py-8">
          {/* Always render a prominent progress section if we have a job (even pending) */}
          {currentJob && (
            <div className="max-w-2xl mx-auto text-left mb-6">
              <JobProgressBanner
                jobId={currentJob.job_id}
                status={(['running','generating','retrying','quality_checking'].includes(currentJob.status as any) ? 'running' : 'pending') as any}
                progressPercentage={currentJob.progress?.progress_percentage || 0}
                currentChapter={currentJob.progress?.current_chapter || 0}
                totalChapters={currentJob.progress?.total_chapters || (estimation?.total_chapters || config.targetChapterCount)}
                estimatedTimeRemaining={
                  currentJob.progress?.estimated_time_remaining 
                    ? typeof currentJob.progress.estimated_time_remaining === 'string' 
                      ? currentJob.progress.estimated_time_remaining 
                      : `${Math.round(currentJob.progress.estimated_time_remaining / 60)} minutes`
                    : undefined
                }
                detailedStatus={currentJob.progress?.detailed_status || 'Starting...'}
              />
            </div>
          )}
          {!currentJob && (
            <div className="mb-4 p-4 bg-blue-50 border border-blue-100 rounded-lg max-w-2xl mx-auto text-left">
              <div className="text-gray-900 font-medium mb-1">No active book generation</div>
              <p className="text-gray-700 text-sm">
                Book generation typically takes <span className="font-medium">30–45 minutes</span>. You can safely
                browse other pages or return later—your progress is saved automatically and updates will appear here.
              </p>
            </div>
          )}
          
          {/* Estimation Display */}
          {estimation && (
            <div className="mb-6 p-4 bg-blue-50 rounded-lg text-left">
              <h4 className="font-medium text-blue-900 mb-2"><span aria-label="Credits icon">🔢</span> Credit Estimation</h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-blue-700">Total Chapters:</span>
                  <span className="ml-2 font-medium">{estimation.total_chapters}</span>
                </div>
                <div>
                  <span className="text-blue-700">Total Words:</span>
                  <span className="ml-2 font-medium">{estimation.total_words.toLocaleString()}</span>
                </div>
                <div className="col-span-2">
                  <span className="text-blue-700">Estimated Credits:</span>
                  <span className="ml-2 font-bold text-lg text-blue-900">{estimation.estimated_total_credits.toLocaleString()}</span>
                </div>
                <div>
                  <span className="text-blue-700">Quality Threshold:</span>
                  <span className="ml-2 font-medium">{estimation.quality_threshold}%</span>
                </div>
              </div>
            </div>
          )}
          
          {/* Action Buttons */}
          <div className="flex flex-col sm:flex-row justify-center gap-3">
            <button
              onClick={estimateAutoCompletion}
              disabled={isEstimating}
              className={`flex items-center justify-center px-4 py-2 rounded-lg font-medium transition-all w-full sm:w-auto ${
                isEstimating
                  ? 'bg-gray-300 text-gray-600 cursor-not-allowed'
                  : 'bg-brand-soft-purple text-white hover:bg-brand-lavender shadow-lg hover:shadow-xl'
              }`}
            >
                                <span aria-label="Money icon">💰</span>
              {isEstimating ? 'Estimating...' : 'Estimate Credits'}
            </button>
            
            <button
              onClick={() => setShowConfirmModal(true)}
              disabled={isStarting || !estimation}
              className={`flex items-center justify-center px-6 py-3 rounded-lg font-medium transition-all w-full sm:w-auto ${
                isStarting || !estimation
                  ? 'bg-gray-300 text-gray-600 cursor-not-allowed'
                  : 'bg-brand-forest text-white hover:bg-brand-forest/90 shadow-lg hover:shadow-xl hover:scale-105'
              }`}
            >
              <PlayIcon className="w-5 h-5 mr-2" />
              {!estimation ? 'Get Estimate First' : 'Start Auto-Completion'}
            </button>
          </div>
        </div>
      )}

      {/* Status Messages */}
      {status && (
        <div className="mt-4 p-3 bg-blue-50 rounded-lg">
          <div className="text-sm text-blue-800">{status}</div>
        </div>
      )}

      {/* Confirmation Modal */}
      {showConfirmModal && estimation && (
        <div 
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="confirm-modal-title"
        >
          <div className="bg-white rounded-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6 border-b border-gray-200">
              <div className="flex items-center justify-between">
                <h2 id="confirm-modal-title" className="text-xl font-semibold text-gray-900">Confirm Auto-Completion</h2>
                <button
                  onClick={() => {
                    setShowConfirmModal(false)
                    setConfirmText('')
                  }}
                  className="text-gray-400 hover:text-gray-600"
                  aria-label="Close confirmation dialog"
                >
                  <span className="sr-only">Close</span>
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            <div className="p-6 space-y-6">
              {/* Credit Summary */}
              <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                <div className="flex items-start space-x-3">
                  <div className="text-yellow-600 text-xl" aria-label="Warning icon">⚠️</div>
                  <div>
                    <h3 className="font-medium text-yellow-900 mb-2">Important: AI Generation Credits</h3>
                    <div className="space-y-2 text-sm text-yellow-800">
                      <p>This will automatically generate <strong>{estimation.total_chapters} chapters</strong> with approximately <strong>{estimation.total_words.toLocaleString()} words</strong>.</p>
                      <p><strong>Estimated credits: {estimation.estimated_total_credits.toLocaleString()}</strong></p>
                      <p>Actual credit usage may vary based on content complexity and revisions needed.</p>
                    </div>
                  </div>
                </div>
              </div>



              {/* Credit Breakdown */}
              <div className="bg-gray-50 rounded-lg p-4">
                <h4 className="font-medium text-gray-900 mb-3">Credit Breakdown</h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-gray-600">Chapters:</span>
                    <span className="ml-2 font-medium">{estimation.total_chapters}</span>
                  </div>
                  <div>
                    <span className="text-gray-600">Words per Chapter:</span>
                    <span className="ml-2 font-medium">{estimation.words_per_chapter.toLocaleString()}</span>
                  </div>
                  <div>
                    <span className="text-gray-600">Credits per Chapter:</span>
                    <span className="ml-2 font-medium">{estimation.credits_per_chapter.toLocaleString()}</span>
                  </div>
                  <div>
                    <span className="text-gray-600">Quality Threshold:</span>
                    <span className="ml-2 font-medium">{estimation.quality_threshold}%</span>
                  </div>
                </div>
              </div>

              {/* Safety Features */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <h4 className="font-medium text-blue-900 mb-2">Safety Features</h4>
                <div className="space-y-1 text-sm text-blue-800">
                  <p>✓ Quality gates at {estimation.quality_threshold}% threshold</p>
                  <p>✓ Progress tracking with pause/resume capability</p>
                  <p>✓ Chapter-by-chapter generation (not all at once)</p>
                  <p>✓ You can stop the process at any time</p>
                </div>
              </div>

              {/* Confirmation Input */}
              <div className="space-y-3">
                <label className="block text-sm font-medium text-gray-700">
                  To confirm, type <strong>CONFIRM</strong> below:
                </label>
                <input
                  id="auto-complete-confirm"
                  name="confirmText"
                  type="text"
                  value={confirmText}
                  onChange={(e) => setConfirmText(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder="Type CONFIRM to proceed"
                />
              </div>

              {/* Action Buttons */}
              <div className="flex flex-col sm:flex-row gap-3">
                <button
                  onClick={() => {
                    setShowConfirmModal(false)
                    setConfirmText('')
                  }}
                  className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => {
                    if (confirmText === 'CONFIRM') {
                      setShowConfirmModal(false)
                      setConfirmText('')
                      startAutoCompletion()
                    }
                  }}
                  disabled={confirmText !== 'CONFIRM'}
                  className={`flex-1 px-4 py-2 rounded-lg font-medium transition-colors ${
                    confirmText === 'CONFIRM'
                      ? 'bg-green-600 text-white hover:bg-green-700'
                      : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                  }`}
                >
                  {isStarting ? 'Starting...' : `Confirm & Start (${estimation.estimated_total_credits.toLocaleString()} credits)`}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Stop Modal */}
      {showStopModal && currentJob && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="stop-modal-title"
        >
          <div className="bg-white rounded-xl max-w-xl w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6 border-b border-gray-200">
              <div className="flex items-center justify-between">
                <h2 id="stop-modal-title" className="text-xl font-semibold text-gray-900">Stop Auto-Complete?</h2>
                <button
                  onClick={() => {
                    setShowStopModal(false)
                    setStopConfirmText('')
                  }}
                  className="text-gray-400 hover:text-gray-600"
                  aria-label="Close stop dialog"
                >
                  <span className="sr-only">Close</span>
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            <div className="p-6 space-y-4">
              <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                <div className="text-sm text-red-800 space-y-1">
                  <div className="font-semibold">This will cancel the running job.</div>
                  <div>It may take a moment to stop if a chapter is currently generating.</div>
                  <div>You can start a new auto-complete run later.</div>
                </div>
              </div>

              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700">
                  To confirm, type <strong>STOP</strong>:
                </label>
                <input
                  id="auto-complete-stop-confirm"
                  name="stopConfirmText"
                  type="text"
                  value={stopConfirmText}
                  onChange={(e) => setStopConfirmText(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500 focus:border-red-500"
                  placeholder="Type STOP to cancel the job"
                />
              </div>

              <div className="flex flex-col sm:flex-row gap-3">
                <button
                  onClick={() => {
                    setShowStopModal(false)
                    setStopConfirmText('')
                  }}
                  className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
                >
                  Keep Running
                </button>
                <button
                  onClick={() => {
                    if (stopConfirmText === 'STOP') {
                      controlJob('cancel')
                    }
                  }}
                  disabled={stopConfirmText !== 'STOP'}
                  className={`flex-1 px-4 py-2 rounded-lg font-medium transition-colors ${
                    stopConfirmText === 'STOP'
                      ? 'bg-red-600 text-white hover:bg-red-700'
                      : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                  }`}
                >
                  Stop Now
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
} 