'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { PlayIcon, PauseIcon, StopIcon, Cog6ToothIcon, BoltIcon } from '@heroicons/react/24/outline'
import { useAuthToken } from '@/lib/auth'
import { useUser } from '@clerk/nextjs'

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
  const { getAuthHeaders, isLoaded, isSignedIn } = useAuthToken()
  const { user } = useUser()
  const [currentJob, setCurrentJob] = useState<AutoCompleteJob | null>(null)
  const [isStarting, setIsStarting] = useState(false)
  const [isEstimating, setIsEstimating] = useState(false)
  const [showConfig, setShowConfig] = useState(false)
  const [status, setStatus] = useState('')
  const [estimation, setEstimation] = useState<any>(null)
  const [progressStream, setProgressStream] = useState<EventSource | null>(null)
  const [showConfirmModal, setShowConfirmModal] = useState(false)
  const [confirmText, setConfirmText] = useState('')
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

  const intervalRef = useRef<NodeJS.Timeout | null>(null)
  const isInitializedRef = useRef(false)
  const progressTrackingRef = useRef<string | null>(null)
  const estimationTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  // Cleanup function to prevent resource leaks
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
      if (currentJob?.job_id && ['pending', 'running', 'generating'].includes(currentJob.status)) {
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

  const checkForExistingJob = async () => {
    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetch('/api/auto-complete/jobs?limit=1&status=active', {
        headers: authHeaders
      })
      if (response.ok) {
        const data = await response.json()
        if (data.jobs && Array.isArray(data.jobs) && data.jobs.length > 0) {
          const job = data.jobs[0]
          setCurrentJob(job)
          // Progress tracking will be handled by the consolidated useEffect
        }
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

    if (currentJob && ['pending', 'running', 'generating'].includes(currentJob.status)) {
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
      const response = await fetch('/api/auto-complete/start', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders
        },
        body: JSON.stringify({
          project_id: projectId,
          book_bible: bookBible || (typeof window !== 'undefined' ? localStorage.getItem(`bookBible-${projectId}`) : null),
          starting_chapter: 1,
          target_chapters: config.targetChapterCount,
          quality_threshold: config.minimumQualityScore / 10.0, // Convert from 0-100 scale to 0-10 scale
          words_per_chapter: Math.round(config.targetWordCount / config.targetChapterCount)
          // Note: estimated_total_cost removed to match backend AutoCompleteRequest model
        })
      })

      const data = await response.json()

      if (response.ok) {
        setStatus('✅ Auto-completion started successfully!')
        setCurrentJob(null) // Will be updated by progress tracking
        startProgressTracking(data.job_id)
        onJobStarted?.(data.job_id)
      } else {
        // Handle specific error types
        if (response.status === 409) {
          setStatus(`🔄 Job already running: ${data.details || data.error}`)
          if (data.existing_job_id) {
            setStatus(`🔄 Resuming existing job: ${data.existing_job_id}`)
            startProgressTracking(data.existing_job_id)
          }
        } else if (response.status === 402) {
          setStatus(`💰 Budget exceeded: ${data.details || data.error}`)
          if (data.estimated_cost && data.remaining_budget) {
            setStatus(`💰 Budget exceeded: Cost $${data.estimated_cost} > Available $${data.remaining_budget.toFixed(2)}`)
          }
        } else {
          setStatus(`❌ Failed to start: ${data.error || data.details || 'Unknown error'}`)
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
      setStatus('❌ Please sign in to get cost estimate')
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
    setStatus('💰 Calculating cost estimate...')
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
      
      console.log('Auto-complete estimate request payload:', {
        ...requestPayload,
        book_bible: `${bookBible?.substring(0, 200)}... (${bookBible?.length} chars)` // Log truncated bible for debugging
      })
      
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
        setStatus(`💰 Estimated total cost: $${data.estimation.estimated_total_cost} for ${data.estimation.total_chapters} chapters`)
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

  const startProgressTracking = (jobId: string, isReconnect = false) => {
    // First, get initial status
    fetchJobStatus(jobId)
    
    // Set up real-time SSE connection
    try {
      const eventSource = new EventSource(`/api/auto-complete/${jobId}/progress`)
      setProgressStream(eventSource)
      
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
        
        if (data.job_id) {
          // Update job status from SSE data
          const updatedJob = { ...currentJob } as AutoCompleteJob
          if (updatedJob) {
            updatedJob.status = data.status
            updatedJob.error = data.error
            updatedJob.result = data.result
            updatedJob.progress = {
              ...updatedJob.progress,
              progress_percentage: data.progress_percentage,
              current_step: data.current_step,
              current_chapter: data.current_chapter,
              chapters_completed: data.chapters_completed,
              total_chapters: data.total_chapters,
              estimated_time_remaining: data.estimated_time_remaining,
              last_update: data.last_update,
              detailed_status: data.detailed_status || `Processing chapter ${data.current_chapter}...`
            }
            setCurrentJob(updatedJob)
          }
        }
      }
      
      eventSource.addEventListener('progress', (event) => {
        const data = JSON.parse(event.data)
        
        if (data.job_id) {
          // Create updated job object
          setCurrentJob(prevJob => {
            if (!prevJob) return prevJob
            
            return {
              ...prevJob,
              status: data.status,
              error: data.error,
              result: data.result,
              progress: {
                ...prevJob.progress,
                progress_percentage: data.progress_percentage,
                current_step: data.current_step,
                current_chapter: data.current_chapter,
                chapters_completed: data.chapters_completed,
                total_chapters: data.total_chapters,
                estimated_time_remaining: data.estimated_time_remaining,
                last_update: data.last_update,
                detailed_status: data.detailed_status || `Processing chapter ${data.current_chapter}...`
              }
            }
          })
        }
      })
      
      eventSource.addEventListener('completion', (event) => {
        const data = JSON.parse(event.data)
        
        if (data.type === 'final') {
          if (data.status === 'completed') {
            onJobCompleted?.(jobId, data.result)
          }
          
          // Clean up SSE connection
          eventSource.close()
          setProgressStream(null)
          reconnectAttemptsRef.current = 0
        }
      })
      
      eventSource.addEventListener('error', (event) => {
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
      })
      
      eventSource.onerror = (event) => {
        console.error('SSE connection error:', event)
        eventSource.close()
        setProgressStream(null)
        
        // Attempt reconnection with exponential backoff
        attemptReconnection(jobId)
      }
    } catch (error) {
      console.error('Failed to create SSE connection:', error)
      // Fallback to polling immediately
      fallbackToPolling(jobId)
    }
  }

  const attemptReconnection = (jobId: string) => {
    const maxAttempts = 5
    const baseDelay = 1000 // 1 second
    
    if (reconnectAttemptsRef.current >= maxAttempts) {
      console.log('Max reconnection attempts reached, falling back to polling')
      setStatus('❌ Connection lost - using polling updates')
      fallbackToPolling(jobId)
      return
    }
    
    reconnectAttemptsRef.current++
    const delay = baseDelay * Math.pow(2, reconnectAttemptsRef.current - 1) // Exponential backoff
    
    setStatus(`🔄 Connection lost, reconnecting in ${delay/1000}s... (${reconnectAttemptsRef.current}/${maxAttempts})`)
    
    reconnectTimeoutRef.current = setTimeout(() => {
      console.log(`Attempting reconnection ${reconnectAttemptsRef.current}/${maxAttempts}`)
      startProgressTracking(jobId, true)
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
      const response = await fetch(`/api/auto-complete/${jobId}/status`, {
        headers: authHeaders
      })
      if (response.ok) {
        const data = await response.json()
        setCurrentJob(data.job)
        
        // Check if job is completed
        if (['completed', 'failed', 'cancelled'].includes(data.job.status)) {
          if (intervalRef.current) {
            clearInterval(intervalRef.current)
            intervalRef.current = null
          }
          
          if (data.job.status === 'completed') {
            onJobCompleted?.(jobId, data.job.result)
          }
        }
      }
    } catch (error) {
      console.error('Failed to fetch job status:', error)
    }
  }

  const controlJob = async (action: 'pause' | 'resume' | 'cancel') => {
    if (!currentJob) return

    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetch(`/api/auto-complete/${currentJob.job_id}/control`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders
        },
        body: JSON.stringify({ action })
      })

      const data = await response.json()

      if (response.ok) {
        setStatus(`✅ Job ${action}d successfully`)
        fetchJobStatus(currentJob.job_id)
      } else {
        setStatus(`❌ Failed to ${action}: ${data.error}`)
      }
    } catch (error) {
      setStatus(`❌ Error: ${error instanceof Error ? error.message : 'Unknown error'}`)
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

  // If user is not authenticated, show sign-in prompt
  if (!isLoaded) {
    return (
      <div className="card">
        <div className="text-center py-8">
          <div className="animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-3/4 mx-auto mb-2"></div>
            <div className="h-4 bg-gray-200 rounded w-1/2 mx-auto"></div>
          </div>
        </div>
      </div>
    )
  }

  if (!isSignedIn) {
    return (
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">
            Auto-Complete Book
          </h2>
        </div>
        <div className="text-center py-8">
          <div className="text-gray-500 mb-4">Please sign in to use auto-completion</div>
          <p className="text-sm text-gray-400">
            Authentication is required to start and manage auto-completion jobs.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
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
                type="number"
                value={config.targetWordCount}
                onChange={(e) => setConfig({...config, targetWordCount: parseInt(e.target.value)})}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Target Chapter Count
              </label>
              <input
                type="number"
                value={config.targetChapterCount}
                onChange={(e) => setConfig({...config, targetChapterCount: parseInt(e.target.value)})}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Minimum Quality Score
              </label>
              <input
                type="number"
                step="0.1"
                min="0"
                max="100"
                value={config.minimumQualityScore}
                onChange={(e) => setConfig({...config, minimumQualityScore: parseFloat(e.target.value)})}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Max Retries Per Chapter
              </label>
              <input
                type="number"
                value={config.maxRetriesPerChapter}
                onChange={(e) => setConfig({...config, maxRetriesPerChapter: parseInt(e.target.value)})}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
          </div>
          <div className="mt-4 space-y-2">
            <label className="flex items-center">
              <input
                type="checkbox"
                checked={config.autoPauseOnFailure}
                onChange={(e) => setConfig({...config, autoPauseOnFailure: e.target.checked})}
                className="mr-2"
              />
              <span className="text-sm text-gray-700">Auto-pause on failure</span>
            </label>
            <label className="flex items-center">
              <input
                type="checkbox"
                checked={config.contextImprovementEnabled}
                onChange={(e) => setConfig({...config, contextImprovementEnabled: e.target.checked})}
                className="mr-2"
              />
              <span className="text-sm text-gray-700">Context improvement enabled</span>
            </label>
            <label className="flex items-center">
              <input
                type="checkbox"
                checked={config.qualityGatesEnabled}
                onChange={(e) => setConfig({...config, qualityGatesEnabled: e.target.checked})}
                className="mr-2"
              />
              <span className="text-sm text-gray-700">Quality gates enabled</span>
            </label>
            <label className="flex items-center">
              <input
                type="checkbox"
                checked={config.userReviewRequired}
                onChange={(e) => setConfig({...config, userReviewRequired: e.target.checked})}
                className="mr-2"
              />
              <span className="text-sm text-gray-700">User review required</span>
            </label>
          </div>
        </div>
      )}

      {/* Current Job Status */}
      {currentJob ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <span className="text-lg">{getStatusIcon(currentJob.status)}</span>
              <span className={`font-medium ${getStatusColor(currentJob.status)}`}>
                {currentJob.status.toUpperCase()}
              </span>
            </div>
            <div className="flex space-x-2">
              {currentJob.status === 'running' && (
                <button
                  onClick={() => controlJob('pause')}
                  className="flex items-center px-3 py-1 bg-yellow-100 text-yellow-800 rounded-md hover:bg-yellow-200"
                >
                  <PauseIcon className="w-4 h-4 mr-1" />
                  Pause
                </button>
              )}
              {currentJob.status === 'paused' && (
                <button
                  onClick={() => controlJob('resume')}
                  className="flex items-center px-3 py-1 bg-green-100 text-green-800 rounded-md hover:bg-green-200"
                >
                  <PlayIcon className="w-4 h-4 mr-1" />
                  Resume
                </button>
              )}
              {['running', 'paused'].includes(currentJob.status) && (
                <button
                  onClick={() => controlJob('cancel')}
                  className="flex items-center px-3 py-1 bg-red-100 text-red-800 rounded-md hover:bg-red-200"
                >
                  <StopIcon className="w-4 h-4 mr-1" />
                  Cancel
                </button>
              )}
            </div>
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
          <div className="grid grid-cols-2 gap-4 text-sm">
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
          <div className="grid grid-cols-2 gap-4 text-xs text-gray-600">
            <div>
              <span>Started:</span>
              <span className="ml-2">{formatDate(currentJob.started_at)}</span>
            </div>
            <div>
              <span>Job ID:</span>
              <span className="ml-2 font-mono">{currentJob.job_id.substring(0, 8)}...</span>
            </div>
          </div>
        </div>
      ) : (
        <div className="text-center py-8">
          <div className="text-gray-500 mb-4">
            No active auto-completion job
          </div>
          
          {/* Estimation Display */}
          {estimation && (
            <div className="mb-6 p-4 bg-blue-50 rounded-lg text-left">
                              <h4 className="font-medium text-blue-900 mb-2"><span aria-label="Money icon">💰</span> Cost Estimation</h4>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-blue-700">Total Chapters:</span>
                  <span className="ml-2 font-medium">{estimation.total_chapters}</span>
                </div>
                <div>
                  <span className="text-blue-700">Words per Chapter:</span>
                  <span className="ml-2 font-medium">{estimation.words_per_chapter.toLocaleString()}</span>
                </div>
                <div>
                  <span className="text-blue-700">Total Words:</span>
                  <span className="ml-2 font-medium">{estimation.total_words.toLocaleString()}</span>
                </div>
                <div>
                  <span className="text-blue-700">Total Tokens:</span>
                  <span className="ml-2 font-medium">{estimation.estimated_total_tokens.toLocaleString()}</span>
                </div>
                <div className="col-span-2">
                  <span className="text-blue-700">Estimated Total Cost:</span>
                  <span className="ml-2 font-bold text-lg text-blue-900">${estimation.estimated_total_cost}</span>
                </div>
                <div>
                  <span className="text-blue-700">Cost per Chapter:</span>
                  <span className="ml-2 font-medium">${estimation.estimated_cost_per_chapter}</span>
                </div>
                <div>
                  <span className="text-blue-700">Quality Threshold:</span>
                  <span className="ml-2 font-medium">{estimation.quality_threshold}%</span>
                </div>
              </div>
              {estimation.notes && estimation.notes.length > 0 && (
                <div className="mt-3 pt-3 border-t border-blue-200">
                  <div className="text-xs text-blue-600">
                    {estimation.notes.map((note: string, index: number) => (
                      <div key={index}>• {note}</div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
          
          {/* Action Buttons */}
          <div className="flex justify-center space-x-4">
            <button
              onClick={estimateAutoCompletion}
              disabled={isEstimating}
              className={`flex items-center px-4 py-2 rounded-lg font-medium transition-all ${
                isEstimating
                  ? 'bg-gray-300 text-gray-600 cursor-not-allowed'
                  : 'bg-brand-soft-purple text-white hover:bg-brand-lavender shadow-lg hover:shadow-xl'
              }`}
            >
                                <span aria-label="Money icon">💰</span>
              {isEstimating ? 'Estimating...' : 'Estimate Cost'}
            </button>
            
            <button
              onClick={() => setShowConfirmModal(true)}
              disabled={isStarting || !estimation}
              className={`flex items-center px-6 py-3 rounded-lg font-medium transition-all ${
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
              {/* Cost Summary */}
              <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                <div className="flex items-start space-x-3">
                  <div className="text-yellow-600 text-xl" aria-label="Warning icon">⚠️</div>
                  <div>
                    <h3 className="font-medium text-yellow-900 mb-2">Important: AI Generation Costs</h3>
                    <div className="space-y-2 text-sm text-yellow-800">
                      <p>This will automatically generate <strong>{estimation.total_chapters} chapters</strong> with approximately <strong>{estimation.total_words.toLocaleString()} words</strong>.</p>
                      <p><strong>Estimated cost: ${estimation.estimated_total_cost}</strong></p>
                      <p>Actual costs may vary based on content complexity and revisions needed.</p>
                      {userUsage && (
                        <p className="mt-2 pt-2 border-t border-yellow-300">
                          <strong>Budget remaining: ${userUsage.remaining.monthly_cost_remaining.toFixed(2)}</strong>
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Budget Warning */}
              {userUsage && estimation && parseFloat(estimation.estimated_total_cost) > userUsage.remaining.monthly_cost_remaining && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                  <div className="flex items-start space-x-3">
                    <div className="text-red-600 text-xl" aria-label="Error icon">🚫</div>
                    <div>
                      <h3 className="font-medium text-red-900 mb-2">Budget Exceeded</h3>
                      <div className="space-y-1 text-sm text-red-800">
                        <p>This operation would exceed your monthly budget limit.</p>
                        <p>Cost: ${estimation.estimated_total_cost} | Available: ${userUsage.remaining.monthly_cost_remaining.toFixed(2)}</p>
                        <p>Please contact support to increase your limit or wait until next month.</p>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Cost Breakdown */}
              <div className="bg-gray-50 rounded-lg p-4">
                <h4 className="font-medium text-gray-900 mb-3">Cost Breakdown</h4>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-gray-600">Chapters:</span>
                    <span className="ml-2 font-medium">{estimation.total_chapters}</span>
                  </div>
                  <div>
                    <span className="text-gray-600">Words per Chapter:</span>
                    <span className="ml-2 font-medium">{estimation.words_per_chapter.toLocaleString()}</span>
                  </div>
                  <div>
                    <span className="text-gray-600">Total Tokens:</span>
                    <span className="ml-2 font-medium">{estimation.estimated_total_tokens.toLocaleString()}</span>
                  </div>
                  <div>
                    <span className="text-gray-600">Cost per Chapter:</span>
                    <span className="ml-2 font-medium">${estimation.estimated_cost_per_chapter}</span>
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
                  type="text"
                  value={confirmText}
                  onChange={(e) => setConfirmText(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder="Type CONFIRM to proceed"
                />
              </div>

              {/* Action Buttons */}
              <div className="flex space-x-3">
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
                  disabled={
                    confirmText !== 'CONFIRM' || 
                    (userUsage && parseFloat(estimation.estimated_total_cost) > userUsage.remaining.monthly_cost_remaining)
                  }
                  className={`flex-1 px-4 py-2 rounded-lg font-medium transition-colors ${
                    confirmText === 'CONFIRM' && 
                    (!userUsage || parseFloat(estimation.estimated_total_cost) <= userUsage.remaining.monthly_cost_remaining)
                      ? 'bg-green-600 text-white hover:bg-green-700'
                      : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                  }`}
                >
                  {isStarting ? 'Starting...' : 
                   userUsage && parseFloat(estimation.estimated_total_cost) > userUsage.remaining.monthly_cost_remaining
                     ? 'Budget Exceeded'
                     : `Confirm & Start ($${estimation.estimated_total_cost})`}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
} 