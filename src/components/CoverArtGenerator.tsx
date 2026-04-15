'use client'

import React, { useState, useEffect } from 'react'
import { useAuthToken, ANONYMOUS_USER } from '@/lib/auth'
import { fetchApi } from '@/lib/api-client'
import { Button } from './ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card'
import { Textarea } from './ui/textarea'
import { GlobalLoader } from '@/stores/useGlobalLoaderStore'
import { Alert, AlertDescription } from './ui/alert'
import { Badge } from './ui/badge'
import { Download, Image as ImageIcon, RefreshCw, Sparkles, AlertCircle, Trash2, ZoomIn } from 'lucide-react'

interface CoverArtGeneratorProps {
  projectId: string
}

interface ReferenceProgress {
  status: string
  progress: number
  stage: string
  message: string
  completed: boolean
}

interface CoverArtStatus {
  job_id?: string
  status: string
  image_url?: string
  prompt?: string
  error?: string
  message: string
  created_at?: string
  completed_at?: string
  attempt_number?: number
  service_available?: boolean
}

export function CoverArtGenerator({ projectId }: CoverArtGeneratorProps) {
  const { getAuthHeaders, user: authUser } = useAuthToken()
  const user = authUser || ANONYMOUS_USER

  const [referenceProgress, setReferenceProgress] = useState<ReferenceProgress | null>(null)
  const [coverArtStatus, setCoverArtStatus] = useState<CoverArtStatus | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [isPolling, setIsPolling] = useState(false)
  const [userFeedback, setUserFeedback] = useState('')
  const [userRequirements, setUserRequirements] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [showFeedbackForm, setShowFeedbackForm] = useState(false)
  const [includeTitle, setIncludeTitle] = useState(true)
  const [includeAuthor, setIncludeAuthor] = useState(true)
  const [titleText, setTitleText] = useState('')
  const [authorText, setAuthorText] = useState('')
  const [coverArtCacheBuster, setCoverArtCacheBuster] = useState<number | null>(null)
  const [lightboxOpen, setLightboxOpen] = useState(false)

  const isFinalCoverArtStatus = (status?: string | null) =>
    status === 'completed' || status === 'failed' || status === 'deleted' || status === 'not_started'

  const shouldPollForCoverArtStatus = (status?: string | null) =>
    status === 'pending' || status === 'processing' || status === 'generating'

  useEffect(() => {
    checkReferenceProgress()
    checkCoverArtStatus()

    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        checkReferenceProgress()
        checkCoverArtStatus()
      }
    }
    document.addEventListener('visibilitychange', handleVisibility)
    return () => document.removeEventListener('visibilitychange', handleVisibility)
  }, [projectId])

  useEffect(() => {
    const initDefaults = async () => {
      try {
        const authHeaders = await getAuthHeaders()
        const projRes = await fetchApi(`/api/v2/projects/${projectId}`, { headers: authHeaders })
        if (projRes.ok) {
          const data = await projRes.json()
          const p = data.project || data
          if (p?.metadata?.title) setTitleText(p.metadata.title)
        }
      } catch {}
    }
    initDefaults()
  }, [projectId])

  useEffect(() => {
    if (coverArtStatus?.image_url) setCoverArtCacheBuster(Date.now())
    else setCoverArtCacheBuster(null)
  }, [coverArtStatus?.image_url])

  useEffect(() => {
    if (user) setAuthorText(user.fullName || '')
  }, [user])

  useEffect(() => {
    let pollInterval: NodeJS.Timeout | null = null
    const status = coverArtStatus?.status
    const isFinal = isFinalCoverArtStatus(status)
    if (isPolling && !isFinal && shouldPollForCoverArtStatus(status)) {
      pollInterval = setInterval(() => {
        if (document.hidden) return
        checkCoverArtStatus()
      }, 3000)
    }
    return () => { if (pollInterval) clearInterval(pollInterval) }
  }, [isPolling, coverArtStatus?.status])

  useEffect(() => {
    const status = coverArtStatus?.status
    const isFinal = isFinalCoverArtStatus(status)
    const visible = isGenerating || (isPolling && !isFinal)
    if (visible) {
      GlobalLoader.show({
        title: 'Generating Cover Art',
        stage: coverArtStatus?.message || 'Creating design...',
        showProgress: false,
        safeToLeave: true,
        canMinimize: true,
        customMessages: [
          'Analyzing book content...',
          'Creating visual concept...',
          'Rendering artwork...',
          'Finalizing design...',
        ],
        timeoutMs: 900000,
      })
    } else {
      GlobalLoader.hide()
    }
  }, [isGenerating, isPolling, coverArtStatus?.status, coverArtStatus?.message])

  const checkReferenceProgress = async () => {
    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetchApi(`/api/v2/projects/${projectId}/references/progress`, {
        headers: { ...authHeaders, 'Content-Type': 'application/json' }
      })
      if (response.ok) setReferenceProgress(await response.json())
    } catch {}
  }

  const checkCoverArtStatus = async () => {
    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetch(`/api/cover-art/${projectId}`, {
        headers: { ...authHeaders, 'Content-Type': 'application/json' }
      })
      if (response.ok) {
        const data = await response.json()
        setError(null)
        setCoverArtStatus(data)
        if (data.status) setIsPolling(shouldPollForCoverArtStatus(data.status))
        if (isFinalCoverArtStatus(data.status)) { setIsPolling(false); setIsGenerating(false) }
      } else {
        setError('Failed to fetch cover art status')
      }
    } catch {
      setError('Failed to fetch cover art status')
    }
  }

  const generateCoverArt = async (regenerate = false) => {
    try {
      setError(null)
      setIsGenerating(true)
      setIsPolling(true)

      const authHeaders = await getAuthHeaders()
      const requestBody: any = {
        user_feedback: regenerate ? userFeedback : undefined,
        regenerate,
        requirements: !regenerate && userRequirements ? userRequirements : undefined,
        options: {
          include_title: includeTitle,
          include_author: includeAuthor,
          title_text: titleText,
          author_text: authorText
        }
      }

      const response = await fetch(`/api/cover-art/${projectId}`, {
        method: 'POST',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody)
      })

      const data = await response.json()
      if (response.ok) {
        setCoverArtStatus({ job_id: data.job_id, status: 'pending', message: data.message })
        if (regenerate) { setUserFeedback(''); setShowFeedbackForm(false) }
      } else {
        setError(data.error || 'Failed to start cover art generation')
        setIsGenerating(false)
        setIsPolling(false)
      }
    } catch {
      setError('Failed to start cover art generation')
      setIsGenerating(false)
      setIsPolling(false)
    }
  }

  const downloadCoverArt = () => {
    if (coverArtStatus?.image_url) {
      const link = document.createElement('a')
      link.href = coverArtStatus.image_url
      link.download = `cover-art-${projectId}.jpg`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
    }
  }

  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  const deleteCoverArt = async () => {
    if (!coverArtStatus?.job_id) return
    setShowDeleteConfirm(false)
    try {
      setError(null)
      const authHeaders = await getAuthHeaders()
      const response = await fetch(`/api/cover-art/${projectId}`, {
        method: 'DELETE',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({ jobId: coverArtStatus.job_id })
      })
      const data = await response.json()
      if (response.ok) {
        setCoverArtStatus(null)
        setShowFeedbackForm(false)
        setIsGenerating(false)
        setIsPolling(false)
        await checkCoverArtStatus()
      } else {
        setError(data.error || 'Failed to delete cover art')
      }
    } catch {
      setError('Failed to delete cover art')
    }
  }

  const referencesCompleted = referenceProgress?.completed === true
  const serviceAvailable = coverArtStatus?.service_available !== false
  const canGenerateCoverArt = referencesCompleted && serviceAvailable && !isGenerating
  const imageUrl = coverArtStatus?.image_url
    ? `${coverArtStatus.image_url}${coverArtCacheBuster ? `?t=${coverArtCacheBuster}` : ''}`
    : null

  return (
    <div className="space-y-6">
      {/* Lightbox */}
      {lightboxOpen && imageUrl && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Cover art preview"
          className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
          onClick={() => setLightboxOpen(false)}
          onKeyDown={(e) => { if (e.key === 'Escape') setLightboxOpen(false) }}
          tabIndex={-1}
          ref={(el) => el?.focus()}
        >
          <img
            src={imageUrl}
            alt="Cover Art Full Size"
            className="max-w-full max-h-full object-contain rounded-lg shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          />
          <button
            onClick={() => setLightboxOpen(false)}
            className="absolute top-4 right-4 w-10 h-10 flex items-center justify-center rounded-full bg-black/50 text-white hover:bg-black/70 transition"
            aria-label="Close preview"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
          </button>
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5" />
            AI Cover Art Generator
          </CardTitle>
          <CardDescription>
            Generate professional book cover art using AI based on your reference files and book content.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {referenceProgress && (
            <div className="flex items-center gap-2">
              <Badge variant={referencesCompleted ? "default" : "secondary"}>
                {referencesCompleted ? "References Complete" : "References In Progress"}
              </Badge>
              {!referencesCompleted && (
                <span className="text-sm text-muted-foreground">
                  {referenceProgress.progress}% - {referenceProgress.stage}
                </span>
              )}
            </div>
          )}

          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {coverArtStatus && (
            <div className="space-y-4">
              {coverArtStatus.status === 'pending' && (
                <div className="text-center py-12">
                  <div className="w-10 h-10 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
                  <p className="text-sm text-muted-foreground">Generating cover art...</p>
                  <p className="text-xs text-muted-foreground mt-1">This usually takes 30-60 seconds.</p>
                </div>
              )}

              {coverArtStatus.status === 'completed' && imageUrl && (
                <div className="space-y-4">
                  <div
                    className="relative mx-auto cursor-pointer group"
                    style={{ maxWidth: '360px' }}
                    onClick={() => setLightboxOpen(true)}
                  >
                    <img
                      src={imageUrl}
                      alt="Generated Cover Art"
                      className="w-full rounded-xl shadow-lg border border-gray-100 object-contain transition-transform duration-200 group-hover:scale-[1.02]"
                      onLoad={() => GlobalLoader.hide()}
                    />
                    <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 rounded-xl transition flex items-center justify-center">
                      <ZoomIn className="h-8 w-8 text-white opacity-0 group-hover:opacity-80 transition drop-shadow-lg" />
                    </div>
                  </div>

                  <div className="flex flex-col sm:flex-row gap-2 justify-center">
                    <Button onClick={downloadCoverArt} variant="outline" className="min-h-[44px] touch-manipulation">
                      <Download className="h-4 w-4 mr-2" />
                      Download
                    </Button>
                    <Button
                      onClick={() => setShowFeedbackForm(true)}
                      variant="outline"
                      className="min-h-[44px] touch-manipulation"
                    >
                      <RefreshCw className="h-4 w-4 mr-2" />
                      Regenerate
                    </Button>
                    {showDeleteConfirm ? (
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-red-600">Delete cover art?</span>
                        <Button onClick={deleteCoverArt} variant="outline" size="sm" className="text-red-600 border-red-200 hover:bg-red-50">Yes</Button>
                        <Button onClick={() => setShowDeleteConfirm(false)} variant="outline" size="sm">No</Button>
                      </div>
                    ) : (
                    <Button
                      onClick={() => setShowDeleteConfirm(true)}
                      variant="outline"
                      className="text-red-600 hover:text-red-700 hover:bg-red-50 min-h-[44px] touch-manipulation"
                    >
                      <Trash2 className="h-4 w-4 mr-2" />
                      Delete
                    </Button>
                    )}
                  </div>

                  {coverArtStatus.prompt && (
                    <details className="mt-4">
                      <summary className="text-sm font-medium cursor-pointer text-muted-foreground hover:text-foreground transition">
                        View AI Prompt Used
                      </summary>
                      <p className="text-sm text-muted-foreground mt-2 p-3 bg-muted rounded-lg leading-relaxed">
                        {coverArtStatus.prompt}
                      </p>
                    </details>
                  )}
                </div>
              )}

              {coverArtStatus.status === 'failed' && (
                <Alert variant="destructive">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>
                    {coverArtStatus.error || 'Cover art generation failed. Please try again.'}
                  </AlertDescription>
                </Alert>
              )}
            </div>
          )}

          {/* Feedback Form for Regeneration */}
          {showFeedbackForm && (
            <Card className="border-2 border-dashed">
              <CardHeader className="pb-3">
                <CardTitle className="text-lg">Improve Your Cover Art</CardTitle>
                <CardDescription>
                  Describe what you'd like to change or improve in the next generation.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <Textarea
                  id="cover-art-feedback"
                  name="coverArtFeedback"
                  placeholder="e.g., Make it darker and more mysterious, add a castle in the background, use warmer colors..."
                  value={userFeedback}
                  onChange={(e) => setUserFeedback(e.target.value)}
                  rows={3}
                />
                <div className="flex flex-col sm:flex-row gap-2">
                  <Button
                    onClick={() => generateCoverArt(true)}
                    disabled={!canGenerateCoverArt}
                    className="min-h-[44px] touch-manipulation"
                  >
                    <Sparkles className="h-4 w-4 mr-2" />
                    Generate New Version
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => setShowFeedbackForm(false)}
                    className="min-h-[44px] touch-manipulation"
                  >
                    Cancel
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Initial Generation Form */}
          {(!coverArtStatus || coverArtStatus.status === 'not_started' || coverArtStatus.status === 'deleted') && (
            <div className="space-y-5">
              <div className="space-y-2">
                <label className="text-sm font-medium">Optional guidance for the cover design</label>
                <Textarea
                  id="cover-art-requirements"
                  name="coverArtRequirements"
                  placeholder="Optional: add any specific requirements (e.g., must feature a lighthouse; avoid weapons; prefer earthy tones). If left blank, the AI will derive the design from your book content."
                  value={userRequirements}
                  onChange={(e) => setUserRequirements(e.target.value)}
                  rows={3}
                />
                <p className="text-xs text-muted-foreground">
                  Works great without any guidance. Add specifics only if you want to steer the design.
                </p>
              </div>

              {/* Title/Author Options */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="flex items-center gap-2 text-sm font-medium cursor-pointer">
                    <input
                      id="cover-art-include-title"
                      name="coverArtIncludeTitle"
                      type="checkbox"
                      checked={includeTitle}
                      onChange={e => setIncludeTitle(e.target.checked)}
                      className="rounded"
                    /> Include Title
                  </label>
                  {includeTitle && (
                    <Textarea
                      id="cover-art-title"
                      name="coverArtTitle"
                      value={titleText}
                      onChange={e => setTitleText(e.target.value)}
                      rows={1}
                      className="text-sm"
                    />
                  )}
                </div>
                <div className="space-y-2">
                  <label className="flex items-center gap-2 text-sm font-medium cursor-pointer">
                    <input
                      id="cover-art-include-author"
                      name="coverArtIncludeAuthor"
                      type="checkbox"
                      checked={includeAuthor}
                      onChange={e => setIncludeAuthor(e.target.checked)}
                      className="rounded"
                    /> Include Author
                  </label>
                  {includeAuthor && (
                    <Textarea
                      id="cover-art-author"
                      name="coverArtAuthor"
                      value={authorText}
                      onChange={e => setAuthorText(e.target.value)}
                      rows={1}
                      className="text-sm"
                    />
                  )}
                </div>
              </div>

              {!referencesCompleted && (
                <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg">
                  <div className="flex items-center gap-2 text-amber-800">
                    <AlertCircle className="h-4 w-4 shrink-0" />
                    <span className="text-sm">
                      Cover art generation will be available once your reference files are completed.
                    </span>
                  </div>
                </div>
              )}

              {referencesCompleted && !serviceAvailable && (
                <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
                  <div className="flex items-center gap-2 text-red-800">
                    <AlertCircle className="h-4 w-4 shrink-0" />
                    <span className="text-sm">
                      Cover art generation service is currently unavailable. Please check configuration.
                    </span>
                  </div>
                </div>
              )}

              <div className="flex justify-center">
                <Button
                  onClick={() => generateCoverArt(false)}
                  disabled={!canGenerateCoverArt}
                  size="lg"
                  className="min-h-[48px] px-8 touch-manipulation"
                >
                  <ImageIcon className="h-5 w-5 mr-2" />
                  Generate Cover Art
                </Button>
              </div>

              {referencesCompleted && (
                <p className="text-sm text-muted-foreground text-center">
                  AI will analyze your book content and reference files to create a professional cover design.
                </p>
              )}
            </div>
          )}

          <div className="text-xs text-muted-foreground space-y-1 pt-2 border-t">
            <p>Generated covers meet Kindle Direct Publishing specifications (1600x2560px, 300 DPI)</p>
            <p>Powered by GPT-image-1 for high-quality, commercially viable designs</p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
