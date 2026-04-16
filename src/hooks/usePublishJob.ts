import { useState, useEffect } from 'react'
import useSWR from 'swr'
import { useAuthToken } from '@/lib/auth'
import { GlobalLoader } from '@/stores/useGlobalLoaderStore'
import { fetchApi } from '@/lib/api-client'

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
  include_kdp_kit?: boolean
  kdp_description?: string
  kdp_keywords?: string[]
  kdp_categories?: string[]
  kdp_subtitle?: string
  kdp_series_name?: string
  kdp_series_number?: string
  kdp_language?: string
  kdp_primary_marketplace?: string
  kdp_author_bio?: string
  kdp_contributors?: string
  kdp_edition?: string
  kdp_reading_age_min?: number
  kdp_reading_age_max?: number
  kdp_imprint?: string
  kdp_pricing?: string
  kdp_adult_content?: boolean
  kdp_drm?: boolean
  kdp_select?: boolean
  kdp_territories?: string
  kdp_publishing_rights?: string
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
    kdp_kit_url?: string
    kdp_package_url?: string
    cover_art_url?: string
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
    kdp_kit?: string
    kdp_package?: string
    cover_art?: string
  } | null
}

const createFetcher = (getAuthHeaders: () => Promise<Record<string, string>>) => async (url: string) => {
  const authHeaders = await getAuthHeaders()
  const response = await fetchApi(url, {
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
      onSuccess: (data: any) => {
        if (data?.progress?.progress_percentage != null) {
          GlobalLoader.update({
            progress: data.progress.progress_percentage,
            stage: data.progress.current_step || 'Publishing...',
            showProgress: true,
          })
        }
      },
      onError: (err) => {
        console.error('Failed to fetch job status:', err)
        setError(new Error('Failed to fetch job status'))
        GlobalLoader.update({ stage: 'Reconnecting for updates...', showProgress: true })
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
        stage: 'Preparing content...',
        showProgress: true,
        safeToLeave: true,
        canMinimize: true,
        customMessages: [
          'Packaging chapters...',
          'Building book structure...',
          'Creating navigation...',
          'Formatting typography...',
          'Uploading files...',
        ],
        timeoutMs: 3600000,
      })

      const response = await fetchApi(`/api/v2/publish/project/${projectId}`, {
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
  // Prefer flattened fields on result; fallback to top-level download_urls if present
  const downloadUrls = jobStatus ? {
    epub: jobStatus.result?.epub_url || (jobStatus as any)?.download_urls?.epub,
    pdf: jobStatus.result?.pdf_url || (jobStatus as any)?.download_urls?.pdf,
    html: jobStatus.result?.html_url || (jobStatus as any)?.download_urls?.html,
    kdp_kit: jobStatus.result?.kdp_kit_url || (jobStatus as any)?.download_urls?.kdp_kit,
    kdp_package: (jobStatus.result as any)?.kdp_package_url || (jobStatus as any)?.download_urls?.kdp_package,
    cover_art: (jobStatus.result as any)?.cover_art_url || (jobStatus as any)?.download_urls?.cover_art,
  } : null

  return {
    startPublishJob,
    jobStatus,
    isLoading: isLoading || (currentJobId && !jobStatus && !statusError),
    error: error || statusError,
    downloadUrls
  }
} 