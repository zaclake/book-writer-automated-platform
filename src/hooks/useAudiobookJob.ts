import { useState, useEffect } from 'react'
import useSWR from 'swr'
import { useAuthToken } from '@/lib/auth'
import { GlobalLoader } from '@/stores/useGlobalLoaderStore'
import { fetchApi } from '@/lib/api-client'

// ── Types ──────────────────────────────────────────────────────────

export interface AudiobookVoice {
  id: string
  name: string
  gender: string
  description: string
  accent: string
  style: string
}

export interface AudiobookEstimate {
  total_characters: number
  total_chapters: number
  estimated_cost_usd: number
  estimated_credits: number
  estimated_duration_minutes: number
  model: string
  rate_per_1k_chars: number
}

export interface PronunciationEntry {
  abbreviation: string
  spoken_form: string
}

export interface AbbreviationSuggestion {
  abbreviation: string
  spoken_form: string
  occurrences: number
}

export interface AudiobookConfig {
  voice_id: string
  model_id?: string
  pronunciation_glossary?: PronunciationEntry[]
  elevenlabs_api_key?: string
}

interface AudiobookJobProgress {
  current_step: string
  current_chapter: number
  total_chapters: number
  progress_percentage: number
}

interface AudiobookJobResult {
  chapter_urls?: Record<string, string>
  full_book_url?: string
  file_sizes?: Record<string, number>
  total_characters?: number
  total_duration_seconds?: number
  credits_charged?: number
  cost_usd?: number
  error_message?: string
}

interface AudiobookJobStatus {
  job_id: string
  status: string
  progress?: AudiobookJobProgress
  result?: AudiobookJobResult
  error?: string
  created_at?: string
  started_at?: string
  completed_at?: string
}

// ── Fetcher ────────────────────────────────────────────────────────

const createFetcher = (getAuthHeaders: () => Promise<Record<string, string>>) =>
  async (url: string) => {
    const authHeaders = await getAuthHeaders()
    const response = await fetchApi(url, { headers: authHeaders })
    if (!response.ok) throw new Error('Failed to fetch')
    return response.json()
  }

// ── useAudiobookVoices ─────────────────────────────────────────────

export function useAudiobookVoices() {
  const { getAuthHeaders } = useAuthToken()
  const fetcher = createFetcher(getAuthHeaders)

  const { data, error, isLoading } = useSWR<AudiobookVoice[]>(
    '/api/v2/audiobook/voices',
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 60000 }
  )

  return { voices: data || [], error, isLoading }
}

// ── useAudiobookEstimate ───────────────────────────────────────────

export function useAudiobookEstimate(projectId: string | null) {
  const { getAuthHeaders } = useAuthToken()
  const fetcher = createFetcher(getAuthHeaders)

  const { data, error, isLoading, mutate } = useSWR<AudiobookEstimate>(
    projectId ? `/api/v2/audiobook/estimate/${projectId}` : null,
    fetcher,
    { revalidateOnFocus: false }
  )

  return { estimate: data, error, isLoading, refresh: mutate }
}

// ── useAudiobookJob ────────────────────────────────────────────────

export function useAudiobookJob() {
  const { getAuthHeaders, isLoaded, isSignedIn } = useAuthToken()
  const [currentJobId, setCurrentJobId] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const fetcher = createFetcher(getAuthHeaders)

  const { data: jobStatus, error: statusError } = useSWR<AudiobookJobStatus>(
    currentJobId ? `/api/v2/audiobook/${currentJobId}` : null,
    fetcher,
    {
      refreshInterval: (data) => {
        if (data?.status === 'completed' || data?.status === 'failed') return 0
        return 2000
      },
      onSuccess: (data) => {
        if (data?.progress?.progress_percentage != null) {
          const step = data.progress.current_step || 'Generating audiobook...'
          GlobalLoader.update({
            progress: data.progress.progress_percentage,
            stage: step,
            showProgress: true,
          })
        }
      },
      onError: () => {
        setError(new Error('Failed to fetch job status'))
        GlobalLoader.update({ stage: 'Reconnecting...', showProgress: true })
      },
    }
  )

  useEffect(() => {
    if (jobStatus?.status === 'completed' || jobStatus?.status === 'failed') {
      GlobalLoader.hide()
    }
  }, [jobStatus?.status])

  const startAudiobookJob = async (projectId: string, config: AudiobookConfig) => {
    try {
      setIsLoading(true)
      setError(null)

      if (!isLoaded || !isSignedIn) throw new Error('User not authenticated')

      const authHeaders = await getAuthHeaders()
      if (!authHeaders.Authorization) throw new Error('No authentication token found')

      GlobalLoader.show({
        title: 'Generating Audiobook',
        stage: 'Preparing chapters...',
        showProgress: true,
        safeToLeave: true,
        canMinimize: true,
        customMessages: [
          'Preprocessing text...',
          'Generating speech...',
          'Converting chapters...',
          'Building audiobook...',
          'Uploading files...',
        ],
        timeoutMs: 7200000, // 2 hours max
      })

      const response = await fetchApi(`/api/v2/audiobook/project/${projectId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify(config),
      })

      if (!response.ok) {
        const errorData = await response.json()
        GlobalLoader.hide()
        throw new Error(errorData.detail || errorData.error || 'Failed to start audiobook job')
      }

      const result = await response.json()
      setCurrentJobId(result.job_id)
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Unknown error'))
      GlobalLoader.hide()
    } finally {
      setIsLoading(false)
    }
  }

  const generatePreview = async (
    projectId: string,
    voiceId: string,
    modelId?: string,
    glossary?: PronunciationEntry[],
    chapterNumber?: number,
  ): Promise<string | null> => {
    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetchApi(`/api/v2/audiobook/preview/${projectId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify({
          voice_id: voiceId,
          model_id: modelId || 'eleven_multilingual_v2',
          pronunciation_glossary: glossary || [],
          chapter_number: chapterNumber,
        }),
      })

      if (!response.ok) return null

      const blob = await response.blob()
      return URL.createObjectURL(blob)
    } catch {
      return null
    }
  }

  const scanAbbreviations = async (projectId: string): Promise<AbbreviationSuggestion[]> => {
    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetchApi(`/api/v2/audiobook/abbreviations/${projectId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: '{}',
      })

      if (!response.ok) return []
      return await response.json()
    } catch {
      return []
    }
  }

  const downloadUrls = jobStatus?.status === 'completed' && jobStatus.result
    ? {
        full_book: jobStatus.result.full_book_url,
        chapters: jobStatus.result.chapter_urls,
      }
    : null

  return {
    startAudiobookJob,
    generatePreview,
    scanAbbreviations,
    jobStatus,
    isLoading: isLoading || !!(currentJobId && !jobStatus && !statusError),
    error: error || statusError,
    downloadUrls,
  }
}
