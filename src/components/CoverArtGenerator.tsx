'use client'

import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useAuthToken, ANONYMOUS_USER } from '@/lib/auth'
import { fetchApi } from '@/lib/api-client'
import { Button } from './ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card'
import { Textarea } from './ui/textarea'
import { Input } from './ui/input'
import { Label } from './ui/label'
import { Checkbox } from './ui/checkbox'
import { Separator } from './ui/separator'
import { GlobalLoader } from '@/stores/useGlobalLoaderStore'
import { Alert, AlertDescription } from './ui/alert'
import { Badge } from './ui/badge'
import {
  Download,
  Image as ImageIcon,
  RefreshCw,
  Sparkles,
  AlertCircle,
  Trash2,
  ZoomIn,
  Paintbrush,
  X,
  Check,
  BookOpen,
  Layers,
} from 'lucide-react'

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

const GENERATION_STAGES = [
  { label: 'Analyzing your book', duration: 10000 },
  { label: 'Crafting visual concept', duration: 12000 },
  { label: 'Rendering artwork', duration: 20000 },
  { label: 'Finalizing design', duration: 18000 },
]

function BookMockup({ imageUrl, onImageLoad }: { imageUrl: string; onImageLoad?: () => void }) {
  const SPINE_W = 32
  const PAGE_DEPTH = 14
  const ROTATE_Y = -14

  return (
    <div
      className="flex items-center justify-center py-4"
      style={{ perspective: '1200px' }}
    >
      <div
        className="relative group"
        style={{
          width: '280px',
          transformStyle: 'preserve-3d',
          transform: `rotateY(${ROTATE_Y}deg)`,
          transition: 'transform 0.5s cubic-bezier(0.25, 0.46, 0.45, 0.94)',
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLElement).style.transform = `rotateY(${ROTATE_Y + 6}deg) translateY(-4px)`
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLElement).style.transform = `rotateY(${ROTATE_Y}deg)`
        }}
      >
        {/* Shadow beneath */}
        <div
          className="absolute pointer-events-none"
          style={{
            width: '90%',
            height: '20px',
            bottom: '-18px',
            left: '10%',
            background: 'radial-gradient(ellipse at center, rgba(0,0,0,0.25) 0%, transparent 70%)',
            filter: 'blur(6px)',
            transform: 'rotateX(90deg)',
            transformOrigin: 'bottom center',
          }}
        />

        {/* Front cover */}
        <div
          className="relative rounded-r-sm overflow-hidden"
          style={{
            width: '100%',
            aspectRatio: '1 / 1.6',
            transformStyle: 'preserve-3d',
            transform: `translateZ(${PAGE_DEPTH}px)`,
          }}
        >
          <img
            src={imageUrl}
            alt="Book cover"
            className="w-full h-full object-cover"
            onLoad={onImageLoad}
          />
          {/* Lighting overlay */}
          <div
            className="absolute inset-0 pointer-events-none"
            style={{
              background: 'linear-gradient(to right, rgba(255,255,255,0.12) 0%, rgba(255,255,255,0.04) 15%, transparent 40%, rgba(0,0,0,0.06) 85%, rgba(0,0,0,0.12) 100%)',
            }}
          />
          {/* Spine edge highlight */}
          <div
            className="absolute left-0 top-0 bottom-0 pointer-events-none"
            style={{
              width: '3px',
              background: 'linear-gradient(to right, rgba(0,0,0,0.15), transparent)',
            }}
          />
        </div>

        {/* Spine */}
        <div
          className="absolute top-0 rounded-l-sm"
          style={{
            width: `${SPINE_W}px`,
            height: '100%',
            left: `${-SPINE_W}px`,
            transformOrigin: 'right center',
            transform: `rotateY(-90deg) translateZ(0px)`,
            background: 'linear-gradient(to right, #3a3530 0%, #4a453e 30%, #3d3833 70%, #332f2a 100%)',
          }}
        >
          {/* Spine texture lines */}
          <div
            className="absolute inset-0 pointer-events-none opacity-20"
            style={{
              backgroundImage: 'repeating-linear-gradient(to bottom, transparent, transparent 3px, rgba(255,255,255,0.08) 3px, rgba(255,255,255,0.08) 4px)',
            }}
          />
        </div>

        {/* Page edges (right side, visible when rotated) */}
        <div
          className="absolute top-[2px] bottom-[2px]"
          style={{
            width: `${PAGE_DEPTH}px`,
            right: `${-PAGE_DEPTH}px`,
            transformOrigin: 'left center',
            transform: 'rotateY(90deg)',
            background: 'linear-gradient(to right, #f5f0e8 0%, #ede8df 40%, #e8e3da 100%)',
            borderTop: '1px solid #ddd8cf',
            borderBottom: '1px solid #ddd8cf',
            borderRight: '1px solid #d8d3ca',
          }}
        >
          {/* Page line texture */}
          <div
            className="absolute inset-0 pointer-events-none"
            style={{
              backgroundImage: 'repeating-linear-gradient(to bottom, transparent, transparent 2px, rgba(0,0,0,0.03) 2px, rgba(0,0,0,0.03) 3px)',
            }}
          />
        </div>

        {/* Bottom edge */}
        <div
          className="absolute left-0 right-0"
          style={{
            height: `${PAGE_DEPTH}px`,
            bottom: `${-PAGE_DEPTH}px`,
            transformOrigin: 'top center',
            transform: 'rotateX(90deg)',
            background: 'linear-gradient(to bottom, #ede8df 0%, #e5e0d7 100%)',
            borderLeft: '1px solid #d8d3ca',
            borderRight: '1px solid #d8d3ca',
          }}
        />
      </div>
    </div>
  )
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
  const [includeTitle, setIncludeTitle] = useState(true)
  const [includeAuthor, setIncludeAuthor] = useState(true)
  const [titleText, setTitleText] = useState('')
  const [authorText, setAuthorText] = useState('')
  const [coverArtCacheBuster, setCoverArtCacheBuster] = useState<number | null>(null)
  const [lightboxOpen, setLightboxOpen] = useState(false)
  const [generationStage, setGenerationStage] = useState(0)
  const [feedbackExpanded, setFeedbackExpanded] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [viewMode, setViewMode] = useState<'showcase' | 'flat'>('showcase')
  const feedbackRef = useRef<HTMLTextAreaElement>(null)

  const isFinalCoverArtStatus = (status?: string | null) =>
    status === 'completed' || status === 'failed' || status === 'deleted' || status === 'not_started'

  const shouldPollForCoverArtStatus = (status?: string | null) =>
    status === 'pending' || status === 'processing' || status === 'generating'

  const isInProgress = shouldPollForCoverArtStatus(coverArtStatus?.status)

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

  // Stepped generation stage timer
  useEffect(() => {
    if (!isInProgress && !isGenerating) {
      setGenerationStage(0)
      return
    }
    setGenerationStage(0)
    const timers: NodeJS.Timeout[] = []
    let cumulative = 0
    for (let i = 1; i < GENERATION_STAGES.length; i++) {
      cumulative += GENERATION_STAGES[i - 1].duration
      timers.push(setTimeout(() => setGenerationStage(i), cumulative))
    }
    return () => timers.forEach(clearTimeout)
  }, [isInProgress, isGenerating])

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
        if (regenerate) { setUserFeedback(''); setFeedbackExpanded(false) }
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

  const downloadCoverArt = useCallback(() => {
    if (coverArtStatus?.image_url) {
      const link = document.createElement('a')
      link.href = coverArtStatus.image_url
      link.download = `cover-art-${projectId}.jpg`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
    }
  }, [coverArtStatus?.image_url, projectId])

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

  // ─── Lightbox ─────────────────────────────────────────────────
  const renderLightbox = () => {
    if (!lightboxOpen || !imageUrl) return null
    return (
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Cover art preview"
        className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-8 animate-in fade-in duration-200"
        style={{ backgroundColor: 'rgba(0,0,0,0.85)' }}
        onClick={() => setLightboxOpen(false)}
        onKeyDown={(e) => { if (e.key === 'Escape') setLightboxOpen(false) }}
        tabIndex={-1}
        ref={(el) => el?.focus()}
      >
        <div
          className="relative flex flex-col items-center gap-4 max-w-full max-h-full animate-in zoom-in-95 duration-200"
          onClick={(e) => e.stopPropagation()}
        >
          <img
            src={imageUrl}
            alt="Cover Art Full Size"
            className="max-w-full max-h-[85vh] object-contain rounded-lg shadow-2xl"
          />
          <div className="flex items-center gap-4">
            <Button
              onClick={downloadCoverArt}
              size="sm"
              className="bg-white/15 hover:bg-white/25 text-white border-white/20 backdrop-blur-sm"
              variant="outline"
            >
              <Download className="h-4 w-4 mr-2" />
              Download
            </Button>
            <span className="text-white/60 text-xs">
              1600 x 2560px &middot; KDP Ready
            </span>
          </div>
        </div>
        <button
          onClick={() => setLightboxOpen(false)}
          className="absolute top-4 right-4 w-10 h-10 flex items-center justify-center rounded-full bg-white/10 text-white hover:bg-white/20 transition backdrop-blur-sm"
          aria-label="Close preview"
        >
          <X className="h-5 w-5" />
        </button>
      </div>
    )
  }

  // ─── Generation progress ─────────────────────────────────────
  const renderGenerationProgress = () => (
    <div className="py-8 space-y-8">
      {/* Pulsing placeholder */}
      <div className="mx-auto w-48 sm:w-56 aspect-[1/1.6] rounded-xl bg-gradient-to-br from-gray-100 to-gray-200 dark:from-gray-800 dark:to-gray-900 animate-pulse flex items-center justify-center shadow-inner">
        <Paintbrush className="h-10 w-10 text-gray-300 dark:text-gray-600" />
      </div>

      {/* Stepped stages */}
      <div className="max-w-sm mx-auto space-y-3">
        {GENERATION_STAGES.map((stage, i) => {
          const isActive = i === generationStage
          const isDone = i < generationStage
          return (
            <div key={stage.label} className="flex items-center gap-3">
              <div className={`
                w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium shrink-0 transition-all duration-500
                ${isDone ? 'bg-green-100 text-green-600' : ''}
                ${isActive ? 'bg-indigo-100 text-indigo-600 ring-2 ring-indigo-300 ring-offset-1' : ''}
                ${!isDone && !isActive ? 'bg-gray-100 text-gray-400' : ''}
              `}>
                {isDone ? <Check className="h-3.5 w-3.5" /> : i + 1}
              </div>
              <span className={`text-sm transition-colors duration-300 ${
                isActive ? 'text-foreground font-medium' : isDone ? 'text-muted-foreground' : 'text-muted-foreground/50'
              }`}>
                {stage.label}{isActive ? '...' : ''}
              </span>
              {isActive && (
                <div className="ml-auto w-4 h-4 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
              )}
            </div>
          )
        })}
      </div>

      <p className="text-xs text-center text-muted-foreground">
        This usually takes 30 -- 60 seconds. You can safely navigate away.
      </p>
    </div>
  )

  // ─── Completed state: two-panel layout ────────────────────────
  const renderCompleted = () => {
    if (coverArtStatus?.status !== 'completed' || !imageUrl) return null

    return (
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] gap-6 lg:gap-8">
        {/* Left: Cover image / mockup */}
        <div className="flex flex-col items-center lg:items-end gap-3">
          {/* View toggle */}
          <div className="inline-flex items-center rounded-lg bg-gray-100 dark:bg-gray-800 p-0.5 text-sm">
            <button
              onClick={() => setViewMode('showcase')}
              className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all ${
                viewMode === 'showcase'
                  ? 'bg-white dark:bg-gray-700 text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <BookOpen className="h-3.5 w-3.5" />
              Showcase
            </button>
            <button
              onClick={() => setViewMode('flat')}
              className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all ${
                viewMode === 'flat'
                  ? 'bg-white dark:bg-gray-700 text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <Layers className="h-3.5 w-3.5" />
              Flat
            </button>
          </div>

          {/* Showcase mode: 3D book */}
          {viewMode === 'showcase' && (
            <div
              className="w-full cursor-pointer"
              style={{ maxWidth: '400px' }}
              onClick={() => setLightboxOpen(true)}
            >
              <BookMockup imageUrl={imageUrl} onImageLoad={() => GlobalLoader.hide()} />
            </div>
          )}

          {/* Flat mode: original cover */}
          {viewMode === 'flat' && (
            <div
              className="relative cursor-pointer group w-full"
              style={{ maxWidth: '400px' }}
              onClick={() => setLightboxOpen(true)}
            >
              <img
                src={imageUrl}
                alt="Generated Cover Art"
                className="w-full rounded-xl shadow-xl border border-gray-200/60 dark:border-gray-700/60 object-contain transition-all duration-300 group-hover:shadow-2xl group-hover:scale-[1.01]"
                onLoad={() => GlobalLoader.hide()}
              />
              <div className="absolute inset-0 bg-black/0 group-hover:bg-black/5 rounded-xl transition-colors duration-300 flex items-center justify-center">
                <ZoomIn className="h-8 w-8 text-white opacity-0 group-hover:opacity-90 transition-opacity duration-300 drop-shadow-lg" />
              </div>
            </div>
          )}
        </div>

        {/* Right: Actions + feedback */}
        <div className="space-y-5 lg:py-2">
          {/* Primary actions */}
          <div className="space-y-2.5">
            <Button onClick={downloadCoverArt} className="w-full min-h-[44px] touch-manipulation">
              <Download className="h-4 w-4 mr-2" />
              Download Cover
            </Button>
            <p className="text-xs text-muted-foreground text-center">
              1600 x 2560px &middot; 300 DPI &middot; KDP Ready
            </p>
          </div>

          <Separator />

          {/* Inline regeneration */}
          <div className="space-y-3">
            <Label className="text-sm font-medium">Refine your cover</Label>
            {feedbackExpanded ? (
              <Textarea
                ref={feedbackRef}
                id="cover-art-feedback"
                name="coverArtFeedback"
                placeholder="Describe changes you'd like... e.g., darker mood, add a castle, warmer colors, different art style..."
                value={userFeedback}
                onChange={(e) => setUserFeedback(e.target.value)}
                rows={3}
                className="text-sm"
              />
            ) : (
              <Input
                placeholder="Describe changes you'd like..."
                value={userFeedback}
                onChange={(e) => setUserFeedback(e.target.value)}
                onFocus={() => {
                  setFeedbackExpanded(true)
                  setTimeout(() => feedbackRef.current?.focus(), 50)
                }}
                className="text-sm"
              />
            )}
            <Button
              onClick={() => generateCoverArt(true)}
              disabled={!canGenerateCoverArt}
              variant="outline"
              className="w-full min-h-[44px] touch-manipulation"
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              Regenerate{userFeedback ? ' with Changes' : ''}
            </Button>
          </div>

          <Separator />

          {/* Prompt details */}
          {coverArtStatus.prompt && (
            <details>
              <summary className="text-sm font-medium cursor-pointer text-muted-foreground hover:text-foreground transition select-none">
                View AI prompt used
              </summary>
              <p className="text-xs text-muted-foreground mt-2 p-3 bg-muted rounded-lg leading-relaxed">
                {coverArtStatus.prompt}
              </p>
            </details>
          )}

          {/* Delete -- low prominence */}
          <div className="pt-1">
            {showDeleteConfirm ? (
              <div className="flex items-center gap-2 text-sm">
                <span className="text-red-600">Delete this cover?</span>
                <Button onClick={deleteCoverArt} variant="outline" size="sm" className="text-red-600 border-red-200 hover:bg-red-50 h-8">
                  Yes, delete
                </Button>
                <Button onClick={() => setShowDeleteConfirm(false)} variant="outline" size="sm" className="h-8">
                  Cancel
                </Button>
              </div>
            ) : (
              <button
                onClick={() => setShowDeleteConfirm(true)}
                className="text-xs text-muted-foreground hover:text-red-500 transition-colors inline-flex items-center gap-1"
              >
                <Trash2 className="h-3 w-3" />
                Delete cover art
              </button>
            )}
          </div>
        </div>
      </div>
    )
  }

  // ─── Initial generation form ─────────────────────────────────
  const renderGenerationForm = () => {
    if (coverArtStatus && coverArtStatus.status !== 'not_started' && coverArtStatus.status !== 'deleted') {
      return null
    }

    return (
      <div className="space-y-6">
        {/* Empty-state placeholder */}
        <div className="flex justify-center">
          <div className="w-44 sm:w-52 aspect-[1/1.6] rounded-xl border-2 border-dashed border-gray-200 dark:border-gray-700 flex flex-col items-center justify-center gap-3 text-muted-foreground/60">
            <ImageIcon className="h-10 w-10" />
            <span className="text-xs font-medium text-center px-4">Your cover will appear here</span>
          </div>
        </div>

        <Separator />

        {/* Creative direction */}
        <div className="space-y-2">
          <Label htmlFor="cover-art-requirements" className="text-sm font-medium">
            Creative Direction
          </Label>
          <Textarea
            id="cover-art-requirements"
            name="coverArtRequirements"
            placeholder="Optional: describe the look you want (e.g., dark and moody oil painting style; feature a lighthouse on a cliff; earthy color palette). Leave blank to let the AI design based on your book content."
            value={userRequirements}
            onChange={(e) => setUserRequirements(e.target.value)}
            rows={3}
            className="text-sm"
          />
          <p className="text-xs text-muted-foreground">
            Works great without guidance -- the AI reads your book bible and references. Add specifics only to steer the design.
          </p>
        </div>

        {/* Title/Author Options */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <div className="space-y-2.5">
            <div className="flex items-center gap-2.5">
              <Checkbox
                id="cover-art-include-title"
                checked={includeTitle}
                onChange={e => setIncludeTitle((e.target as HTMLInputElement).checked)}
              />
              <Label htmlFor="cover-art-include-title" className="cursor-pointer">
                Include Title
              </Label>
            </div>
            {includeTitle && (
              <Input
                id="cover-art-title"
                name="coverArtTitle"
                value={titleText}
                onChange={e => setTitleText(e.target.value)}
                placeholder="Book title"
                className="text-sm"
              />
            )}
          </div>
          <div className="space-y-2.5">
            <div className="flex items-center gap-2.5">
              <Checkbox
                id="cover-art-include-author"
                checked={includeAuthor}
                onChange={e => setIncludeAuthor((e.target as HTMLInputElement).checked)}
              />
              <Label htmlFor="cover-art-include-author" className="cursor-pointer">
                Include Author
              </Label>
            </div>
            {includeAuthor && (
              <Input
                id="cover-art-author"
                name="coverArtAuthor"
                value={authorText}
                onChange={e => setAuthorText(e.target.value)}
                placeholder="Author name"
                className="text-sm"
              />
            )}
          </div>
        </div>

        {!referencesCompleted && (
          <div className="p-4 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-lg">
            <div className="flex items-center gap-2 text-amber-800 dark:text-amber-200">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span className="text-sm">
                Cover art generation will be available once your reference files are completed.
              </span>
            </div>
          </div>
        )}

        {referencesCompleted && !serviceAvailable && (
          <div className="p-4 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg">
            <div className="flex items-center gap-2 text-red-800 dark:text-red-200">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span className="text-sm">
                Cover art generation service is currently unavailable. Please check configuration.
              </span>
            </div>
          </div>
        )}

        <div className="flex justify-center pt-1">
          <Button
            onClick={() => generateCoverArt(false)}
            disabled={!canGenerateCoverArt}
            size="lg"
            className="min-h-[48px] px-10 touch-manipulation"
          >
            <Sparkles className="h-5 w-5 mr-2" />
            Generate Cover Art
          </Button>
        </div>

        {referencesCompleted && (
          <p className="text-xs text-muted-foreground text-center">
            The AI analyzes your book bible and reference files to create a unique, genre-appropriate cover.
          </p>
        )}
      </div>
    )
  }

  // ─── Main render ──────────────────────────────────────────────
  return (
    <div className="space-y-6">
      {renderLightbox()}

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Sparkles className="h-5 w-5" />
                Cover Art Generator
              </CardTitle>
              <CardDescription className="mt-1">
                Create a professional, genre-appropriate book cover powered by AI.
              </CardDescription>
            </div>
            {referenceProgress && (
              <Badge variant={referencesCompleted ? "default" : "secondary"} className="shrink-0">
                {referencesCompleted ? "References Complete" : `References ${referenceProgress.progress}%`}
              </Badge>
            )}
          </div>
        </CardHeader>

        <CardContent className="space-y-5">
          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {isInProgress && renderGenerationProgress()}
          {renderCompleted()}
          {renderGenerationForm()}

          {coverArtStatus?.status === 'failed' && (
            <div className="space-y-4">
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                  {coverArtStatus.error || 'Cover art generation failed. Please try again.'}
                </AlertDescription>
              </Alert>
              <div className="flex justify-center">
                <Button
                  onClick={() => generateCoverArt(false)}
                  disabled={!canGenerateCoverArt}
                  variant="outline"
                  className="min-h-[44px] touch-manipulation"
                >
                  <RefreshCw className="h-4 w-4 mr-2" />
                  Try Again
                </Button>
              </div>
            </div>
          )}

          <div className="text-xs text-muted-foreground pt-3 border-t text-center">
            Covers meet Kindle Direct Publishing specifications &middot; Powered by GPT-image-1
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
