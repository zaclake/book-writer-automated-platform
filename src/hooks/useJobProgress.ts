import { useState, useEffect, useCallback } from 'react'
import { useAuthToken } from '@/lib/auth'

interface JobProgress {
  id: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'failed-rate-limit'
  progress: number // 0-100
  stage?: string
  message?: string
  result?: any
  error?: string
}

interface UseJobProgressOptions {
  pollInterval?: number // milliseconds
  timeout?: number // milliseconds
  onComplete?: (result: any) => void
  onError?: (error: string) => void
  onTimeout?: () => void
}

export function useJobProgress(
  jobId: string | null,
  options: UseJobProgressOptions = {}
) {
  const { getAuthHeaders } = useAuthToken()
  const {
    pollInterval = 2000, // 2 seconds
    timeout = 300000, // 5 minutes
    onComplete,
    onError,
    onTimeout
  } = options

  const [progress, setProgress] = useState<JobProgress | null>(null)
  const [isPolling, setIsPolling] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [timeElapsed, setTimeElapsed] = useState(0)

  const pollProgress = useCallback(async (id: string) => {
    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetch(`/api/v2/projects/${id}/references/progress`, {
        headers: authHeaders
      })
      
      if (!response.ok) {
        throw new Error(`Failed to get job status: ${response.statusText}`)
      }

      const data = await response.json()
      
      const jobProgress: JobProgress = {
        id: data.id || id,
        status: data.status || 'pending',
        progress: data.progress || 0,
        stage: data.stage,
        message: data.message,
        result: data.result,
        error: data.error
      }

      setProgress(jobProgress)

      // Handle completion
      if (jobProgress.status === 'completed') {
        setIsPolling(false)
        onComplete?.(jobProgress.result)
      } else if (jobProgress.status === 'failed' || jobProgress.status === 'failed-rate-limit') {
        setIsPolling(false)
        const errorMsg = jobProgress.error || jobProgress.message || 'Job failed'
        setError(errorMsg)
        onError?.(errorMsg)
      }

      return jobProgress

    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error'
      setError(errorMsg)
      setIsPolling(false)
      onError?.(errorMsg)
      return null
    }
  }, [onComplete, onError])

  // Start polling when jobId is provided
  useEffect(() => {
    if (!jobId) {
      setIsPolling(false)
      setProgress(null)
      setError(null)
      setTimeElapsed(0)
      return
    }

    setIsPolling(true)
    setError(null)
    setTimeElapsed(0)

    const pollIntervalId = setInterval(() => {
      pollProgress(jobId)
    }, pollInterval)

    // Timeout handler
    const timeoutId = setTimeout(() => {
      setIsPolling(false)
      clearInterval(pollIntervalId)
      onTimeout?.()
    }, timeout)

    // Elapsed time tracker
    const startTime = Date.now()
    const timeIntervalId = setInterval(() => {
      setTimeElapsed(Date.now() - startTime)
    }, 1000)

    // Initial poll
    pollProgress(jobId)

    return () => {
      clearInterval(pollIntervalId)
      clearTimeout(timeoutId)
      clearInterval(timeIntervalId)
    }
  }, [jobId, pollInterval, timeout, pollProgress, onTimeout])

  const startPolling = useCallback((id: string) => {
    setIsPolling(true)
    setError(null)
    setTimeElapsed(0)
  }, [])

  const stopPolling = useCallback(() => {
    setIsPolling(false)
  }, [])

  return {
    progress,
    isPolling,
    error,
    timeElapsed,
    startPolling,
    stopPolling
  }
} 