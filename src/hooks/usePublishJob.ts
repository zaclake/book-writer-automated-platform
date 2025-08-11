import { useState, useEffect } from 'react'
import useSWR from 'swr'
import { useAuthToken } from '@/lib/auth'
import { GlobalLoader } from '@/stores/useGlobalLoaderStore'

interface PublishConfig {
  title: string
  author: string
  publisher?: string
  isbn?: string
  date?: string
  rights: string
  dedication?: string
  acknowledgments?: string
  foreword?: string
  preface?: string
  epilogue?: string
  about_author?: string
  call_to_action?: string
  other_books?: string
  connect_author?: string
  book_club_questions?: string
  formats: string[]
  use_existing_cover: boolean
  include_toc: boolean
}

interface JobProgress {
  current_step: string
  progress_percentage: number
  last_update: string
}

interface JobStatus {
  job_id: string
  status: string
  progress?: JobProgress
  result?: {
    epub_url?: string
    pdf_url?: string
    html_url?: string
    file_sizes?: Record<string, number>
    word_count?: number
    page_count?: number
  }
  error?: string
  created_at: string
  started_at?: string
  completed_at?: string
}

interface PublishJobHook {
  startPublishJob: (projectId: string, config: PublishConfig) => Promise<void>
  jobStatus: JobStatus | null
  isLoading: boolean
  error: Error | null
  downloadUrls: {
    epub?: string
    pdf?: string
    html?: string
  } | null
}

const createFetcher = (getAuthHeaders: () => Promise<Record<string, string>>) => async (url: string) => {
  const authHeaders = await getAuthHeaders()
  const response = await fetch(url, {
    headers: authHeaders
  })
  
  if (!response.ok) {
    throw new Error('Failed to fetch')
  }
  
  return response.json()
}

export function usePublishJob(): PublishJobHook {
  const { getAuthHeaders, isLoaded, isSignedIn } = useAuthToken()
  const [currentJobId, setCurrentJobId] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  // Create fetcher with auth headers
  const fetcher = createFetcher(getAuthHeaders)

  // Poll job status if we have a job ID
  const { data: jobStatus, error: statusError } = useSWR(
    currentJobId ? `/api/v2/publish/${currentJobId}` : null,
    fetcher,
    {
      refreshInterval: (data) => {
        // Stop polling if job is completed or failed
        if (data?.status === 'completed' || data?.status === 'failed') {
          return 0
        }
        return 2000 // Poll every 2 seconds
      },
      onError: (err) => {
        console.error('Failed to fetch job status:', err)
        setError(new Error('Failed to fetch job status'))
      }
    }
  )

  // Clear job when it's completed or failed after a delay
  useEffect(() => {
    if (jobStatus?.status === 'completed' || jobStatus?.status === 'failed') {
      GlobalLoader.hide()
      const timer = setTimeout(() => {
        // Keep the job ID to show results, but stop polling
      }, 1000)
      return () => clearTimeout(timer)
    }
  }, [jobStatus?.status])

  const startPublishJob = async (projectId: string, config: PublishConfig) => {
    try {
      setIsLoading(true)
      setError(null)

      if (!isLoaded || !isSignedIn) {
        throw new Error('User not authenticated')
      }

      const authHeaders = await getAuthHeaders()
      if (!authHeaders.Authorization) {
        throw new Error('No authentication token found')
      }

      GlobalLoader.show({
        title: 'Publishing Your Book',
        stage: 'Starting...',
        showProgress: true,
        size: 'md',
        customMessages: [
          '📦 Packaging content...',
          '🧩 Building chapters into formats...',
          '🧭 Creating navigation and TOC...',
          '✨ Polishing layout and typography...',
          '☁️ Uploading final files...',
        ],
        timeoutMs: 3600000,
      })

      const response = await fetch(`/api/v2/publish/project/${projectId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders
        },
        body: JSON.stringify(config)
      })

      if (!response.ok) {
        const errorData = await response.json()
        GlobalLoader.hide()
        throw new Error(errorData.detail || errorData.error || 'Failed to start publish job')
      }

      const result = await response.json()
      setCurrentJobId(result.job_id)
      // Keep loader visible; progress will be updated by effect below
      
    } catch (err) {
      console.error('Failed to start publish job:', err)
      setError(err instanceof Error ? err : new Error('Unknown error'))
      GlobalLoader.hide()
    } finally {
      setIsLoading(false)
    }
  }

  // Extract download URLs from job result
  const downloadUrls = jobStatus?.result ? {
    epub: jobStatus.result.epub_url,
    pdf: jobStatus.result.pdf_url,
    html: jobStatus.result.html_url
  } : null

  return {
    startPublishJob,
    jobStatus,
    isLoading: isLoading || (currentJobId && !jobStatus && !statusError),
    error: error || statusError,
    downloadUrls
  }
} 