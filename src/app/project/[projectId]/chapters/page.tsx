'use client'

import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { useParams, usePathname, useRouter, useSearchParams } from 'next/navigation'
import { useAuthToken } from '@/lib/auth'
import { fetchApi } from '@/lib/api-client'
import { useProjectChapters, useProject, useUserJobs } from '@/hooks/useFirestore'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { CollapsibleSidebar } from '@/components/layout/CollapsibleSidebar'
import ProjectLayout from '@/components/layout/ProjectLayout'
import { GlobalLoader } from '@/stores/useGlobalLoaderStore'
import { ChapterVersionHistoryDialog } from '@/components/ChapterVersionHistory'
import ChapterTipTapEditor, { type SelectionInfo } from '@/components/editor/ChapterTipTapEditor'
import { InlineDiff, DiffStats } from '@/components/editor/InlineDiff'
import { RippleReport } from '@/components/editor/RippleReport'
import { AnimatePresence, motion } from 'framer-motion'
import {
  DocumentPlusIcon,
  BookmarkIcon,
  Bars3Icon,
  ArrowPathIcon,
  CheckCircleIcon,
  ClockIcon,
} from '@heroicons/react/24/outline'

interface Chapter {
  id: string
  chapter_number: number
  content?: string
  metadata?: {
    word_count?: number
    status?: string
    updated_at?: string | { _seconds?: number; seconds?: number }
    gates_passed?: boolean
    failure_reason?: string | null
  }
}

export default function ChapterWritingPage() {
  const params = useParams()
  const projectId = params.projectId as string
  const pathname = usePathname()
  const router = useRouter()
  const searchParams = useSearchParams()
  const { getAuthHeaders, isSignedIn } = useAuthToken()

  const removeAsterisks = (text: string) => text.replace(/\*/g, '')

  const showStatus = useCallback((msg: string, durationMs = 5000) => {
    setStatus(msg)
    if (statusTimerRef.current) clearTimeout(statusTimerRef.current)
    if (durationMs > 0) {
      statusTimerRef.current = setTimeout(() => setStatus(''), durationMs)
    }
  }, [])

  const chapterFromUrl = useMemo(() => {
    const raw = searchParams.get('chapter')
    if (!raw) return null
    const parsed = Number(raw)
    if (!Number.isFinite(parsed)) return null
    const asInt = Math.trunc(parsed)
    return asInt >= 1 ? asInt : null
  }, [searchParams])

  // Core state
  const [currentChapter, setCurrentChapter] = useState<number>(() => chapterFromUrl ?? 1)
  const [pendingChapterTarget, setPendingChapterTarget] = useState<number | null>(null)
  const [unsavedNavDialogOpen, setUnsavedNavDialogOpen] = useState(false)
  const [chapterContent, setChapterContent] = useState('')
  const [originalContent, setOriginalContent] = useState('')
  const [rewriteDialogOpen, setRewriteDialogOpen] = useState(false)
  const [rewriteMode, setRewriteMode] = useState<'polish' | 'full'>('full')
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [status, setStatus] = useState('')
  const statusTimerRef = useRef<NodeJS.Timeout | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [focusMode, setFocusMode] = useState(false)
  const [isPollingChapter, setIsPollingChapter] = useState(false)
  const [versionsOpen, setVersionsOpen] = useState(false)

  // Selection state (driven by TipTap editor)
  const [selectionInfo, setSelectionInfo] = useState<SelectionInfo | null>(null)
  const [selectionMode, setSelectionMode] = useState<'note' | 'rewrite'>('note')
  const [selectionNote, setSelectionNote] = useState('')
  const [selectionInstruction, setSelectionInstruction] = useState('')
  const [selectionBusy, setSelectionBusy] = useState(false)
  const [applyToFuture, setApplyToFuture] = useState(true)
  const [noteScope, setNoteScope] = useState<'chapter' | 'global'>('chapter')

  // Preview state
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewOriginal, setPreviewOriginal] = useState('')
  const [previewProposed, setPreviewProposed] = useState('')
  const [previewContent, setPreviewContent] = useState('')
  const [previewLoading, setPreviewLoading] = useState(false)

  // Ripple analysis state
  const [rippleData, setRippleData] = useState<{
    affected_chapters: Array<{
      chapter_number: number
      chapter_id: string
      severity: 'low' | 'medium' | 'high'
      issues: string[]
      suggested_fix: string
    }>
    source_chapter: number
    total_checked: number
  } | null>(null)
  const [rippleLoading, setRippleLoading] = useState(false)
  const [showRippleNotification, setShowRippleNotification] = useState(false)

  // Polling / loading refs
  const currentChapterRef = useRef(currentChapter)
  currentChapterRef.current = currentChapter
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const pollingAttemptRef = useRef(0)
  const chapterLoadAbortRef = useRef<AbortController | null>(null)
  const chapterLoadRequestIdRef = useRef(0)
  const slowLoadTimerRef = useRef<number | null>(null)
  const generationStartRef = useRef<number | null>(null)
  const generationBaselineRef = useRef('')
  const MAX_POLL_ATTEMPTS = 90
  const CHAPTER_CACHE_TTL_MS = 5 * 60 * 1000
  const chapterCacheRef = useRef<Map<number, { content: string; id: string | null; fetchedAt: number }>>(
    new Map()
  )
  const prefetchInFlightRef = useRef<Set<number>>(new Set())

  // Ref for stable save handler in keyboard shortcuts (updated after saveChapter is defined)
  const saveChapterRef = useRef<() => Promise<boolean>>(() => Promise.resolve(false))

  const [isChapterLoading, setIsChapterLoading] = useState(false)
  const [chapterLoadError, setChapterLoadError] = useState<string | null>(null)
  const [isSlowChapterLoad, setIsSlowChapterLoad] = useState(false)
  const [loadedChapterId, setLoadedChapterId] = useState<string | null>(null)

  const getUpdatedAtMillis = (updatedAt?: string | { _seconds?: number; seconds?: number }) => {
    if (!updatedAt) return null
    if (typeof updatedAt === 'string') {
      const parsed = Date.parse(updatedAt)
      return Number.isNaN(parsed) ? null : parsed
    }
    const seconds = updatedAt._seconds ?? updatedAt.seconds
    return typeof seconds === 'number' ? seconds * 1000 : null
  }

  // Firestore hooks
  const { jobs } = useUserJobs(25)
  const hasActiveAutoCompleteJob = useMemo(() => {
    if (!projectId) return false
    return (jobs || []).some((job: any) => {
      if (!job) return false
      const sameProject = String(job.project_id || '') === String(projectId)
      const isAutoComplete = String(job.job_type || '') === 'auto_complete_book'
      const jobStatus = String(job.status || '').toLowerCase()
      const active = jobStatus && !['completed', 'failed', 'cancelled'].includes(jobStatus)
      return sameProject && isAutoComplete && active
    })
  }, [jobs, projectId])

  const { chapters, loading: chaptersLoading, refreshChapters } = useProjectChapters(projectId, {
    intervalMs: hasActiveAutoCompleteJob ? 15000 : undefined,
  })
  const { project } = useProject(projectId)

  // URL sync
  useEffect(() => {
    if (chapterFromUrl && chapterFromUrl !== currentChapter) {
      requestChapterChange(chapterFromUrl, { updateUrl: false })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chapterFromUrl])

  useEffect(() => {
    if (!chapterFromUrl) {
      updateChapterInUrl(currentChapter)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!isPollingChapter) {
      loadChapter(currentChapter)
    }
  }, [currentChapter, isPollingChapter])

  useEffect(() => {
    setHasUnsavedChanges(chapterContent !== originalContent)
  }, [chapterContent, originalContent])

  useEffect(() => {
    return () => {
      stopChapterPolling()
      chapterLoadAbortRef.current?.abort()
      if (slowLoadTimerRef.current !== null) {
        window.clearTimeout(slowLoadTimerRef.current)
        slowLoadTimerRef.current = null
      }
      if (statusTimerRef.current) {
        clearTimeout(statusTimerRef.current)
        statusTimerRef.current = null
      }
    }
  }, [])

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault()
        if (hasUnsavedChanges && !isSaving) saveChapterRef.current()
      }
      if (e.key === 'Escape') {
        if (previewOpen) setPreviewOpen(false)
        else if (selectionInfo) resetSelection()
        else if (showRippleNotification) setShowRippleNotification(false)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [hasUnsavedChanges, isSaving, previewOpen, selectionInfo, showRippleNotification])

  // Warn before leaving with unsaved changes
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (hasUnsavedChanges) {
        e.preventDefault()
        e.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [hasUnsavedChanges])

  useEffect(() => {
    if (focusMode) setSidebarOpen(false)
  }, [focusMode])

  useEffect(() => {
    if (noteScope === 'global' && !applyToFuture) setApplyToFuture(true)
  }, [noteScope, applyToFuture])

  const currentChapterRecord = chapters.find(ch => Number((ch as any).chapter_number) === Number(currentChapter))
  const currentChapterId = loadedChapterId || currentChapterRecord?.id
  const currentChapterFailureReason = currentChapterRecord?.metadata?.failure_reason || null
  const currentChapterGatesPassed = currentChapterRecord?.metadata?.gates_passed
  const isCurrentChapterFailed = currentChapterGatesPassed === false || !!currentChapterFailureReason

  const chapterLabelByNumber = useMemo(() => {
    const map = new Map<number, string>()
    for (const ch of chapters) {
      const n = Number(ch.chapter_number)
      if (!Number.isFinite(n) || n <= 0) continue
      const suffix = (ch.metadata?.gates_passed === false || ch.metadata?.failure_reason) ? ' (needs review)' : ''
      map.set(n, `Chapter ${n}${suffix} \u2713`)
    }
    return map
  }, [chapters])

  const selectionPresets = [
    { label: 'Tighten', value: 'Tighten this selection without losing meaning.' },
    { label: 'Clarify', value: 'Clarify the intent and remove ambiguity.' },
    { label: 'Punchier', value: 'Make this more punchy and energetic.' },
    { label: 'Smoother', value: 'Improve flow and sentence rhythm.' },
    { label: 'Continuity', value: 'Fix continuity with the surrounding context.' },
  ]

  const resetSelection = useCallback(() => {
    setSelectionInfo(null)
    setSelectionNote('')
    setSelectionInstruction('')
    setSelectionMode('note')
    setPreviewOpen(false)
    setPreviewOriginal('')
    setPreviewProposed('')
    setPreviewContent('')
  }, [])

  useEffect(() => {
    resetSelection()
  }, [currentChapter, resetSelection])

  const maxSelectableChapter = Math.max(project?.settings?.target_chapters || 25, chapters.length || 0, 1)

  const updateChapterInUrl = (chapterNumber: number) => {
    const newParams = new URLSearchParams(searchParams.toString())
    newParams.set('chapter', String(chapterNumber))
    router.replace(`${pathname}?${newParams.toString()}`)
  }

  const requestChapterChange = (
    nextChapterNumber: number,
    options: { updateUrl?: boolean } = {}
  ) => {
    const clamped = Math.max(1, Math.min(nextChapterNumber, maxSelectableChapter))
    const updateUrl = options.updateUrl ?? true

    if (clamped === currentChapter) {
      if (updateUrl) updateChapterInUrl(clamped)
      return
    }

    if (hasUnsavedChanges) {
      setPendingChapterTarget(clamped)
      setUnsavedNavDialogOpen(true)
      return
    }

    stopChapterPolling()
    setCurrentChapter(clamped)
    if (updateUrl) updateChapterInUrl(clamped)
  }

  const prefetchChapter = async (chapterNumber: number) => {
    if (!isSignedIn || !projectId) return
    if (chapterNumber < 1 || chapterNumber > maxSelectableChapter) return

    const cached = chapterCacheRef.current.get(chapterNumber)
    if (cached && Date.now() - cached.fetchedAt < CHAPTER_CACHE_TTL_MS && cached.content) return
    if (prefetchInFlightRef.current.has(chapterNumber)) return

    const fromList = chapters.find(ch => Number((ch as any).chapter_number) === Number(chapterNumber))
    if (fromList?.content) {
      const content = removeAsterisks(fromList.content || '')
      if (content) {
        chapterCacheRef.current.set(chapterNumber, { content, id: fromList.id || null, fetchedAt: Date.now() })
        return
      }
    }

    prefetchInFlightRef.current.add(chapterNumber)
    try {
      const authHeaders = await getAuthHeaders()
      const controller = new AbortController()
      const timeout = window.setTimeout(() => controller.abort(), 25000)
      try {
        const response = await fetchApi(
          `/api/v2/projects/${encodeURIComponent(projectId)}/chapters?include_content=true`,
          { headers: authHeaders, signal: controller.signal, cache: 'no-store' }
        )
        if (!response.ok) return
        const data = await response.json().catch(() => null)
        const match = (data?.chapters || []).find((item: Chapter) => Number((item as any).chapter_number) === Number(chapterNumber))
        const fetchedContent = removeAsterisks(match?.content || '')
        if (!fetchedContent) return
        chapterCacheRef.current.set(chapterNumber, { content: fetchedContent, id: match?.id || null, fetchedAt: Date.now() })
      } finally {
        window.clearTimeout(timeout)
      }
    } catch {
      // best-effort
    } finally {
      prefetchInFlightRef.current.delete(chapterNumber)
    }
  }

  useEffect(() => {
    if (!isSignedIn || !projectId) return
    if (isGenerating || isPollingChapter) return
    prefetchChapter(currentChapter - 1)
    prefetchChapter(currentChapter + 1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentChapter, isSignedIn, projectId, isGenerating, isPollingChapter, maxSelectableChapter])

  useEffect(() => {
    if (!isSignedIn || !projectId) return
    if (isChapterLoading || isGenerating || isPollingChapter) return
    if (chapterContent || isEditing) return

    const record = chapters.find(ch => Number((ch as any).chapter_number) === Number(currentChapter))
    if (!record?.content) return

    const content = removeAsterisks(record.content || '')
    if (!content) return

    chapterCacheRef.current.set(currentChapter, { content, id: record.id || null, fetchedAt: Date.now() })
    setLoadedChapterId(record.id || null)
    setChapterContent(content)
    setOriginalContent(content)
    setIsEditing(true)
  }, [chapters, currentChapter, isSignedIn, projectId, isChapterLoading, isGenerating, isPollingChapter, chapterContent, isEditing])

  // Selection handlers for TipTap
  const handleSelectionChange = useCallback((selection: SelectionInfo | null) => {
    setSelectionInfo(selection)
    if (!selection) {
      setPreviewOpen(false)
    }
  }, [])

  const handleNoteMode = useCallback(() => {
    setSelectionMode('note')
  }, [])

  const handleRewriteMode = useCallback(() => {
    setSelectionMode('rewrite')
  }, [])

  const ensureChapterId = () => {
    if (!currentChapterId) {
      showStatus('Please generate or load this chapter before using selection tools.')
      return null
    }
    return currentChapterId
  }

  const saveSelectionNote = async () => {
    if (!selectionInfo || !selectionNote.trim()) return
    const chapterId = ensureChapterId()
    if (!chapterId) return
    try {
      setSelectionBusy(true)
      const authHeaders = await getAuthHeaders()
      const response = await fetchApi(`/api/chapters/${chapterId}/notes`, {
        method: 'POST',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: selectionNote,
          position: selectionInfo.from,
          selection_start: selectionInfo.from,
          selection_end: selectionInfo.to,
          selection_text: selectionInfo.text,
          apply_to_future: applyToFuture,
          scope: noteScope,
        }),
      })
      if (!response.ok) throw new Error(await response.text())
      showStatus('Note saved successfully')
      resetSelection()
    } catch (error) {
      console.error('Failed to save highlight note:', error)
      showStatus('Unable to save highlight note')
    } finally {
      setSelectionBusy(false)
    }
  }

  const rewriteSelection = async () => {
    if (!selectionInfo || !selectionInstruction.trim()) return
    const chapterId = ensureChapterId()
    if (!chapterId) return
    try {
      setSelectionBusy(true)
      const authHeaders = await getAuthHeaders()
      const response = await fetchApi(`/api/v2/chapters/${chapterId}/rewrite-section`, {
        method: 'POST',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          selection_start: selectionInfo.from,
          selection_end: selectionInfo.to,
          instruction: selectionInstruction,
        }),
      })
      if (!response.ok) throw new Error(await response.text())
      const data = await response.json()
      const cleaned = removeAsterisks(data.content || '')
      setChapterContent(cleaned)
      setOriginalContent(cleaned)
      showStatus('Selection rewritten successfully')
      resetSelection()
      runRippleAnalysis()
    } catch (error) {
      console.error('Failed to rewrite selection:', error)
      showStatus('Unable to rewrite that selection')
    } finally {
      setSelectionBusy(false)
    }
  }

  const findUpdatedSelection = (original: string, updated: string, range: { start: number; end: number }) => {
    const prefix = original.slice(Math.max(0, range.start - 40), range.start)
    const suffix = original.slice(range.end, Math.min(original.length, range.end + 40))
    let startIdx = -1
    let endIdx = -1
    if (prefix) {
      startIdx = updated.indexOf(prefix)
      if (startIdx !== -1) startIdx += prefix.length
    } else {
      startIdx = range.start
    }
    if (suffix && startIdx !== -1) {
      endIdx = updated.indexOf(suffix, startIdx)
    }
    if (startIdx !== -1 && endIdx !== -1 && endIdx > startIdx) {
      return updated.slice(startIdx, endIdx)
    }
    const approxStart = Math.max(0, Math.min(updated.length, range.start))
    const approxEnd = Math.max(approxStart, Math.min(updated.length, approxStart + (range.end - range.start)))
    return updated.slice(approxStart, approxEnd)
  }

  const previewRewriteSelection = async () => {
    if (!selectionInfo || !selectionInstruction.trim()) return
    const chapterId = ensureChapterId()
    if (!chapterId) return
    try {
      setPreviewLoading(true)
      const authHeaders = await getAuthHeaders()
      const response = await fetchApi(`/api/v2/chapters/${chapterId}/rewrite-section`, {
        method: 'POST',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          selection_start: selectionInfo.from,
          selection_end: selectionInfo.to,
          instruction: selectionInstruction,
          preview: true,
        }),
      })
      if (!response.ok) throw new Error(await response.text())
      const data = await response.json()
      const cleaned = removeAsterisks(data.content || data.proposed_content || '')
      const proposed = data.proposed_selection
        ? removeAsterisks(data.proposed_selection)
        : findUpdatedSelection(chapterContent, cleaned, { start: selectionInfo.from, end: selectionInfo.to })
      setPreviewOriginal(selectionInfo.text)
      setPreviewProposed(proposed)
      setPreviewContent(cleaned)
      setPreviewOpen(true)
    } catch (error) {
      console.error('Failed to preview selection rewrite:', error)
      showStatus('Unable to preview this rewrite')
    } finally {
      setPreviewLoading(false)
    }
  }

  const loadChapter = async (chapterNumber: number) => {
    if (!isSignedIn || !projectId) return
    if (isGenerating) return

    const cached = chapterCacheRef.current.get(chapterNumber)
    if (cached && Date.now() - cached.fetchedAt < CHAPTER_CACHE_TTL_MS && cached.content) {
      setIsChapterLoading(false)
      setChapterLoadError(null)
      setIsSlowChapterLoad(false)
      setLoadedChapterId(cached.id)
      setChapterContent(cached.content)
      setOriginalContent(cached.content)
      setIsEditing(true)
      return
    }

    const fromList = chapters.find(ch => Number((ch as any).chapter_number) === Number(chapterNumber))
    if (fromList?.content) {
      const content = removeAsterisks(fromList.content || '')
      if (content) {
        chapterCacheRef.current.set(chapterNumber, { content, id: fromList.id || null, fetchedAt: Date.now() })
        setIsChapterLoading(false)
        setChapterLoadError(null)
        setIsSlowChapterLoad(false)
        setLoadedChapterId(fromList.id || null)
        setChapterContent(content)
        setOriginalContent(content)
        setIsEditing(true)
        return
      }
    }

    chapterLoadAbortRef.current?.abort()
    const controller = new AbortController()
    chapterLoadAbortRef.current = controller

    const requestId = (chapterLoadRequestIdRef.current += 1)
    setIsChapterLoading(true)
    setChapterLoadError(null)
    setIsSlowChapterLoad(false)

    if (slowLoadTimerRef.current !== null) {
      window.clearTimeout(slowLoadTimerRef.current)
      slowLoadTimerRef.current = null
    }
    slowLoadTimerRef.current = window.setTimeout(() => {
      if (chapterLoadRequestIdRef.current === requestId) setIsSlowChapterLoad(true)
    }, 5000)

    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetchApi(`/api/v2/projects/${encodeURIComponent(projectId)}/chapters?include_content=true`, {
        headers: authHeaders,
        signal: controller.signal,
        cache: 'no-store',
      })

      if (chapterLoadRequestIdRef.current !== requestId) return

      if (!response.ok) {
        const errText = await response.text().catch(() => '')
        if (response.status === 403) showStatus('You do not have access to this project', 0)
        setChapterLoadError(errText || `Failed to load chapter (HTTP ${response.status})`)
        return
      }

      const data = await response.json().catch(() => null)
      const match = (data?.chapters || []).find((item: Chapter) => Number((item as any).chapter_number) === Number(chapterNumber))
      const content = removeAsterisks(match?.content || '')
      setLoadedChapterId(match?.id || null)

      if (content) {
        chapterCacheRef.current.set(chapterNumber, { content, id: match?.id || null, fetchedAt: Date.now() })
        setChapterContent(content)
        setOriginalContent(content)
        setIsEditing(true)
      } else {
        chapterCacheRef.current.delete(chapterNumber)
        setChapterContent('')
        setOriginalContent('')
        setIsEditing(false)
        setLoadedChapterId(match?.id || null)
      }
    } catch (error: any) {
      if (error?.name === 'AbortError') return
      console.error('Error loading chapter:', error)
      if (chapterLoadRequestIdRef.current === requestId) setChapterLoadError('Error loading chapter')
    } finally {
      if (chapterLoadRequestIdRef.current === requestId) setIsChapterLoading(false)
      if (slowLoadTimerRef.current !== null) {
        window.clearTimeout(slowLoadTimerRef.current)
        slowLoadTimerRef.current = null
      }
    }
  }

  const stopChapterPolling = () => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = null
    }
    setIsPollingChapter(false)
    pollingAttemptRef.current = 0
  }

  const pollForChapterContent = async () => {
    if (!isSignedIn || !projectId) return

    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetchApi(`/api/v2/projects/${projectId}/chapters?include_content=true`, {
        headers: authHeaders,
      })

      if (!response.ok) {
        if (response.status === 403) showStatus('You do not have access to this project', 0)
        else showStatus('Chapter generation failed. Please try again.', 0)
        stopChapterPolling()
        setIsGenerating(false)
        GlobalLoader.hide()
        generationStartRef.current = null
        generationBaselineRef.current = ''
        return
      }

      const data = await response.json()
      const pollingChapter = currentChapterRef.current
      const chapter = (data?.chapters || []).find(
        (item: Chapter) => Number((item as any).chapter_number) === Number(pollingChapter)
      )
      if (chapter?.content) {
        const updatedAtMs = getUpdatedAtMillis(chapter.metadata?.updated_at)
        const generationStart = generationStartRef.current
        const baseline = generationBaselineRef.current
        if (generationStart) {
          const isFresh = updatedAtMs ? updatedAtMs >= generationStart : chapter.content !== baseline
          if (!isFresh) {
            pollingAttemptRef.current += 1
            if (pollingAttemptRef.current % 3 === 0) setStatus('Still generating... this can take a few minutes.')
            return
          }
        }
        const cleanedContent = removeAsterisks(chapter.content)
        setChapterContent(cleanedContent)
        setOriginalContent(cleanedContent)
        setIsEditing(true)
        showStatus('Chapter generated successfully!')
        stopChapterPolling()
        setIsGenerating(false)
        GlobalLoader.hide()
        window.dispatchEvent(new CustomEvent('refreshCreditBalance'))
        generationStartRef.current = null
        generationBaselineRef.current = ''
        chapterCacheRef.current.delete(pollingChapter)
        refreshChapters()
      } else {
        pollingAttemptRef.current += 1
        if (pollingAttemptRef.current >= MAX_POLL_ATTEMPTS) {
          showStatus('Chapter generation timed out. Please try again.', 0)
          stopChapterPolling()
          setIsGenerating(false)
          GlobalLoader.hide()
          generationStartRef.current = null
          generationBaselineRef.current = ''
          return
        }
        if (pollingAttemptRef.current % 3 === 0) setStatus('Still generating... this can take a few minutes.')
      }
    } catch (error) {
      console.error('Error polling chapter content:', error)
      pollingAttemptRef.current += 1
      if (pollingAttemptRef.current >= MAX_POLL_ATTEMPTS) {
        showStatus('Generation check timed out. Your chapter may still be generating — try refreshing.', 0)
        stopChapterPolling()
        setIsGenerating(false)
        GlobalLoader.hide()
        generationStartRef.current = null
        generationBaselineRef.current = ''
      }
    }
  }

  const startChapterPolling = () => {
    stopChapterPolling()
    setIsPollingChapter(true)
    pollingAttemptRef.current = 0
    pollForChapterContent()
    pollingIntervalRef.current = setInterval(pollForChapterContent, 5000)
  }

  const generateChapter = async () => {
    if (!isSignedIn || !projectId) return

    setIsGenerating(true)
    generationStartRef.current = Date.now()
    generationBaselineRef.current = chapterContent
    GlobalLoader.show({
      title: `Generating Chapter ${currentChapter}`,
      stage: 'Crafting chapter...',
      showProgress: false,
      size: 'md',
      customMessages: [
        'Weaving narrative threads...',
        'Developing character voices...',
        'Building dramatic tension...',
        'Polishing prose perfection...',
      ],
      timeoutMs: 900000,
    })
    showStatus('Generating chapter...', 0)

    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetchApi('/api/v2/chapters/generate', {
        method: 'POST',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: projectId,
          chapter_number: currentChapter,
          target_word_count: 3800,
          stage: 'complete',
        }),
      })

      const data = await response.json().catch(() => ({}))

      if (response.ok && data?.content) {
        const cleanedContent = removeAsterisks(data.content || '')
        setChapterContent(cleanedContent)
        setOriginalContent(cleanedContent)
        setIsEditing(true)
        showStatus('Chapter generated successfully!')
        window.dispatchEvent(new CustomEvent('refreshCreditBalance'))
        setIsGenerating(false)
        GlobalLoader.hide()
        generationStartRef.current = null
        generationBaselineRef.current = ''
        return
      }

      if (response.status === 202) {
        showStatus('Chapter generation started. Waiting for content...', 0)
        startChapterPolling()
        return
      }

      showStatus(`Generation failed: ${data.error || data.detail || 'Unknown error'}`, 0)
      setIsGenerating(false)
      GlobalLoader.hide()
      generationStartRef.current = null
      generationBaselineRef.current = ''
    } catch (error) {
      console.error('Error generating chapter:', error)
      showStatus('Error generating chapter', 0)
      setIsGenerating(false)
      GlobalLoader.hide()
      generationStartRef.current = null
      generationBaselineRef.current = ''
    }
  }

  const saveChapter = async (): Promise<boolean> => {
    if (!isSignedIn || !projectId || !chapterContent.trim()) return false

    setIsSaving(true)
    showStatus('Saving chapter...', 0)

    try {
      const authHeaders = await getAuthHeaders()
      const cleanedContent = removeAsterisks(chapterContent)
      // Bypass fetchApi concurrency limiter for saves — use raw fetch with explicit timeout
      const response = await fetch(`/api/chapters/${currentChapter}?project_id=${projectId}`, {
        method: 'PUT',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: cleanedContent }),
        signal: AbortSignal.timeout(30000),
      })

      if (response.ok) {
        setChapterContent(cleanedContent)
        setOriginalContent(cleanedContent)
        showStatus('Chapter saved successfully!')
        runRippleAnalysis()
        return true
      } else {
        const errText = await response.text().catch(() => '')
        console.error('Save failed:', response.status, errText)
        showStatus(`Failed to save chapter (${response.status})`, 0)
        return false
      }
    } catch (error: any) {
      console.error('Error saving chapter:', error)
      if (error?.name === 'TimeoutError' || error?.name === 'AbortError') {
        showStatus('Save timed out — please try again', 0)
      } else {
        showStatus('Error saving chapter — check your connection', 0)
      }
      return false
    } finally {
      setIsSaving(false)
    }
  }

  saveChapterRef.current = saveChapter

  const runRippleAnalysis = async () => {
    if (!currentChapterId || !isSignedIn) return
    setShowRippleNotification(false)
    setRippleLoading(true)
    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetchApi(`/api/v2/chapters/${currentChapterId}/ripple-analysis`, {
        method: 'POST',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          edit_summary: '',
          chapter_number: currentChapter,
        }),
      })
      if (response.ok) {
        const data = await response.json()
        setRippleData(data)
        if (data.affected_chapters?.length > 0) {
          setShowRippleNotification(true)
        }
      }
    } catch (error) {
      console.error('Ripple analysis failed:', error)
    } finally {
      setRippleLoading(false)
    }
  }

  const rewriteChapter = async (mode: 'polish' | 'full') => {
    if (!isSignedIn || !projectId) return

    setIsGenerating(true)
    generationStartRef.current = Date.now()
    generationBaselineRef.current = chapterContent
    GlobalLoader.show({
      title: mode === 'polish' ? `Polishing Chapter ${currentChapter}` : `Regenerating Chapter ${currentChapter}`,
      stage: mode === 'polish' ? 'Polishing...' : 'Reimagining...',
      showProgress: false,
      size: 'md',
      customMessages: [
        'Exploring alternatives...',
        'Improving continuity...',
        'Sharpening prose...',
      ],
      timeoutMs: 900000,
    })
    showStatus(mode === 'polish' ? 'Polishing chapter...' : 'Regenerating chapter...', 0)

    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetchApi('/api/v2/chapters/generate', {
        method: 'POST',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: projectId,
          chapter_number: currentChapter,
          target_word_count: 3800,
          stage: mode === 'full' ? '5-stage' : 'complete',
          rewrite_mode: mode,
        }),
      })

      const data = await response.json().catch(() => ({}))

      if (response.ok && data?.content) {
        const cleanedContent = removeAsterisks(data.content || '')
        setChapterContent(cleanedContent)
        setOriginalContent(cleanedContent)
        setIsEditing(true)
        showStatus(mode === 'polish' ? 'Chapter polished successfully!' : 'Chapter regenerated successfully!')
        setIsGenerating(false)
        GlobalLoader.hide()
        generationStartRef.current = null
        generationBaselineRef.current = ''
        return
      }

      if (response.status === 202) {
        showStatus(mode === 'polish' ? 'Chapter polish started...' : 'Chapter regeneration started...', 0)
        startChapterPolling()
        return
      }

      showStatus(`Rewrite failed: ${data.error || data.detail || 'Unknown error'}`, 0)
      setIsGenerating(false)
      GlobalLoader.hide()
      generationStartRef.current = null
      generationBaselineRef.current = ''
    } catch (error) {
      console.error('Error rewriting chapter:', error)
      showStatus('Error rewriting chapter', 0)
      setIsGenerating(false)
      GlobalLoader.hide()
      generationStartRef.current = null
      generationBaselineRef.current = ''
    }
  }

  const [isApproving, setIsApproving] = useState(false)

  const approveChapter = async () => {
    if (isApproving) return
    setIsApproving(true)
    try {
      if (hasUnsavedChanges) {
        const saved = await saveChapter()
        if (!saved) {
          showStatus('Cannot approve: save failed. Please try saving again.', 0)
          return
        }
      }
      showStatus('Chapter approved!')
      const maxChapter = Math.max(project?.settings?.target_chapters || 25, chapters.length || 0)
      if (currentChapter < maxChapter) {
        setTimeout(() => requestChapterChange(currentChapter + 1), 600)
      }
    } finally {
      setIsApproving(false)
    }
  }

  const wordCount = (chapterContent || '').split(/\s+/).filter(word => word.length > 0).length

  return (
    <ProjectLayout
      projectId={projectId}
      projectTitle={project?.metadata?.title || project?.title || 'Project'}
      hideNavigation={focusMode}
    >
      <div className="relative bg-gray-50">
        {/* Immersive Header */}
        {!focusMode && (
          <div className="relative bg-gradient-to-br from-gray-900 via-indigo-950 to-gray-900 overflow-hidden">
            <div className="absolute top-0 right-0 w-72 h-72 bg-indigo-500/10 rounded-full blur-3xl" />
            <div className="absolute bottom-0 left-0 w-56 h-56 bg-violet-500/10 rounded-full blur-3xl" />

            <div className="relative z-10 px-4 sm:px-6 md:px-8 lg:px-12 py-6">
              <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between max-w-none">
                <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
                  <h1 className="text-2xl md:text-3xl font-bold text-white tracking-tight">
                    Chapter {currentChapter}: {(project?.metadata?.title && project.metadata.title.trim()) || `Project ${project?.id || 'Unknown'}`}
                  </h1>
                  <div className="bg-white/20 backdrop-blur-sm px-3 py-1 rounded-full text-sm font-bold text-white">
                    {wordCount.toLocaleString()} words
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2 sm:gap-3">
                  <div className="flex flex-wrap items-center gap-2 bg-white/10 backdrop-blur-sm rounded-xl p-2">
                    <button
                      onClick={() => requestChapterChange(currentChapter - 1)}
                      disabled={currentChapter <= 1 || isChapterLoading || isGenerating || isPollingChapter}
                      className="bg-white/20 text-white px-3 py-1 rounded-lg text-sm font-semibold hover:bg-white/30 transition-colors disabled:opacity-50"
                    >
                      &larr; Prev
                    </button>

                    <select
                      id="chapter-select-header"
                      name="currentChapter"
                      value={currentChapter}
                      onChange={(e) => requestChapterChange(Number(e.target.value))}
                      disabled={isChapterLoading || isGenerating || isPollingChapter || (chaptersLoading && chapters.length === 0)}
                      className="bg-white/20 backdrop-blur-sm text-white px-3 py-1 rounded-lg text-sm font-semibold border border-white/20 focus:bg-white/30 transition-colors"
                      style={{ color: 'white' }}
                    >
                      {Array.from({ length: Math.max(project?.settings?.target_chapters || 25, chapters.length || 0) }, (_, i) => (
                        <option key={i + 1} value={i + 1} style={{ color: 'black' }}>
                          {chapterLabelByNumber.get(i + 1) || `Chapter ${i + 1}`}
                        </option>
                      ))}
                    </select>

                    <button
                      onClick={() => requestChapterChange(currentChapter + 1)}
                      disabled={currentChapter >= Math.max(project?.settings?.target_chapters || 25, chapters.length || 0) || isChapterLoading || isGenerating || isPollingChapter}
                      className="bg-white/20 text-white px-3 py-1 rounded-lg text-sm font-semibold hover:bg-white/30 transition-colors disabled:opacity-50"
                    >
                      Next &rarr;
                    </button>
                  </div>

                  {currentChapterId && (
                    <button
                      onClick={() => setVersionsOpen(true)}
                      className="bg-white/10 backdrop-blur-sm text-white p-2 rounded-lg hover:bg-white/20 transition-colors"
                      title="Version history"
                    >
                      <ClockIcon className="w-5 h-5" />
                    </button>
                  )}

                  <button
                    onClick={() => setSidebarOpen(!sidebarOpen)}
                    className="bg-white/10 backdrop-blur-sm text-white p-2 rounded-lg hover:bg-white/20 transition-colors"
                  >
                    <Bars3Icon className="w-5 h-5" />
                  </button>

                  <button
                    onClick={() => setFocusMode(true)}
                    className="bg-white/20 text-white px-3 py-1 rounded-lg text-sm font-semibold hover:bg-white/30 transition-colors"
                  >
                    Focus Mode
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Focus Mode Top Bar */}
        {focusMode && (
          <div className="sticky top-0 z-30 bg-white/95 backdrop-blur border-b border-gray-200 px-3 sm:px-4 py-2 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center justify-between md:gap-3">
              <div className="text-sm font-semibold text-gray-800 truncate">
                Chapter {currentChapter}
              </div>
              <button
                onClick={() => setFocusMode(false)}
                className="text-xs font-semibold text-indigo-500 hover:underline"
              >
                Exit Focus Mode
              </button>
            </div>
            <div className="flex flex-wrap items-center gap-2 md:flex-nowrap md:gap-3 md:flex-1 md:justify-end">
              <button
                onClick={() => requestChapterChange(currentChapter - 1)}
                disabled={currentChapter <= 1 || isChapterLoading || isGenerating || isPollingChapter}
                className="px-3 py-1 rounded-full border border-gray-200 text-xs font-semibold text-gray-700 disabled:opacity-50"
              >
                Prev
              </button>
              <select
                id="chapter-select-focus"
                name="currentChapter"
                value={currentChapter}
                onChange={(e) => requestChapterChange(Number(e.target.value))}
                disabled={isChapterLoading || isGenerating || isPollingChapter || (chaptersLoading && chapters.length === 0)}
                className="flex-1 min-w-[8rem] bg-white border border-gray-300 rounded-full px-3 py-1 text-xs font-semibold text-gray-800"
                aria-label="Select chapter"
              >
                {Array.from({ length: Math.max(project?.settings?.target_chapters || 25, chapters.length || 0) }, (_, i) => (
                  <option key={i + 1} value={i + 1}>
                    {chapterLabelByNumber.get(i + 1) || `Chapter ${i + 1}`}
                  </option>
                ))}
              </select>
              <button
                onClick={() => requestChapterChange(currentChapter + 1)}
                disabled={currentChapter >= Math.max(project?.settings?.target_chapters || 25, chapters.length || 0) || isChapterLoading || isGenerating || isPollingChapter}
                className="px-3 py-1 rounded-full border border-gray-200 text-xs font-semibold text-gray-700 disabled:opacity-50"
              >
                Next
              </button>
              <div className="ml-auto text-xs font-semibold text-gray-500">
                {wordCount.toLocaleString()} words
              </div>
            </div>
          </div>
        )}

        {/* Status Bar */}
        {status && (
          <div className="bg-blue-50 border-b border-blue-200 px-4 sm:px-6 md:px-8 lg:px-12 py-3" role="status" aria-live="polite">
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-blue-800">{status}</div>
              <button
                onClick={() => setStatus('')}
                className="text-xs text-blue-600 hover:text-blue-800 font-semibold"
              >
                Dismiss
              </button>
            </div>
          </div>
        )}

        {/* Main Content Area */}
        <div className="relative">
          {/* Chapter Load Overlay */}
          {(isChapterLoading || chapterLoadError) && !isEditing && !chapterContent && (
            <div className="flex items-center justify-center py-16 sm:py-24">
              <div className="text-center max-w-lg">
                <div className="mb-6">
                  <div className="w-12 h-12 mx-auto border-2 border-gray-200 border-t-indigo-500 rounded-full animate-spin" />
                </div>
                <h2 className="text-2xl font-bold text-gray-900 tracking-tight mb-3">
                  Loading Chapter {currentChapter}...
                </h2>
                <p className="text-gray-500 mb-6">
                  {chapterLoadError
                    ? 'We hit an issue loading this chapter.'
                    : isSlowChapterLoad
                      ? 'This is taking longer than usual. You can retry if it feels stuck.'
                      : 'Fetching your chapter now.'}
                </p>
                <div className="flex flex-col sm:flex-row gap-2 justify-center">
                  <button
                    onClick={() => loadChapter(currentChapter)}
                    disabled={isChapterLoading}
                    className="bg-brand-forest text-white px-6 py-3 rounded-2xl text-base font-bold hover:opacity-95 disabled:opacity-50"
                  >
                    {isChapterLoading ? 'Loading...' : 'Retry'}
                  </button>
                  {chapterLoadError && (
                    <button
                      onClick={() => setStatus(chapterLoadError)}
                      className="border border-gray-200 text-gray-700 px-6 py-3 rounded-2xl text-base font-bold hover:bg-gray-50"
                    >
                      Show details
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Generate Chapter Button */}
          {!isChapterLoading && !chapterLoadError && !isEditing && !chapterContent && (
            <div className="flex items-center justify-center py-16 sm:py-24">
              <div className="text-center max-w-lg">
                <div className="mb-6">
                  <div className="w-16 h-16 mx-auto bg-gray-100 rounded-2xl flex items-center justify-center">
                    <DocumentPlusIcon className="w-8 h-8 text-gray-400" />
                  </div>
                </div>
                <h2 className="text-2xl font-bold text-gray-900 tracking-tight mb-3">
                  Ready to Write Chapter {currentChapter}?
                </h2>
                <p className="text-gray-500 mb-8">
                  Let AI help you craft the next part of your story.
                </p>
                <button
                  onClick={generateChapter}
                  disabled={isGenerating}
                  className="bg-gray-900 text-white px-8 py-3 rounded-xl text-base font-semibold hover:bg-gray-800 transition-all shadow-lg"
                >
                  {isGenerating ? (
                    <>
                      <ArrowPathIcon className="w-6 h-6 mr-3 animate-spin inline" />
                      Generating Chapter {currentChapter}...
                    </>
                  ) : (
                    <>
                      <DocumentPlusIcon className="w-6 h-6 mr-3 inline" />
                      Generate Chapter {currentChapter}
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {/* TipTap Editor */}
          {(isEditing || chapterContent) && (
            <div className="px-4 sm:px-6 md:px-8 lg:px-12 py-6 sm:py-8">
              <div className="max-w-4xl md:max-w-5xl mx-auto">
                <div className="relative bg-white rounded-xl p-4 sm:p-6 lg:p-8 border border-gray-200 shadow-sm">
                  {(isChapterLoading || chapterLoadError) && (
                    <div className="absolute inset-0 z-20 rounded-2xl bg-white/75 backdrop-blur-sm flex items-center justify-center p-6">
                      <div className="text-center max-w-lg">
                        {!chapterLoadError ? (
                          <>
                            <div className="mb-4">
                              <div className="w-12 h-12 mx-auto border-4 border-brand-forest/20 border-t-brand-forest rounded-full animate-spin" />
                            </div>
                            <div className="text-lg font-bold text-gray-900">Loading Chapter {currentChapter}...</div>
                            <div className="mt-2 text-sm font-semibold text-gray-500">
                              {isSlowChapterLoad ? 'Taking longer than usual...' : 'Switching chapters...'}
                            </div>
                          </>
                        ) : (
                          <>
                            <div className="text-lg font-bold text-gray-900">Couldn&apos;t load this chapter</div>
                            <div className="mt-2 text-sm font-semibold text-gray-500">{chapterLoadError}</div>
                            <div className="mt-4 flex flex-col sm:flex-row gap-2 justify-center">
                              <button
                                onClick={() => loadChapter(currentChapter)}
                                className="bg-brand-forest text-white px-5 py-2 rounded-xl font-bold hover:opacity-95"
                              >
                                Retry
                              </button>
                              <button
                                onClick={() => setChapterLoadError(null)}
                                className="border border-gray-200 text-gray-700 px-5 py-2 rounded-xl font-bold hover:bg-gray-50"
                              >
                                Dismiss
                              </button>
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                  )}

                  {isCurrentChapterFailed && (
                    <div className="mb-4">
                      <Alert variant="destructive">
                        <AlertDescription>
                          <div className="space-y-1">
                            <div className="font-semibold">This chapter failed quality checks but was saved anyway.</div>
                            {currentChapterFailureReason && (
                              <div className="text-sm opacity-90">Reason: {currentChapterFailureReason}</div>
                            )}
                            <div className="text-sm opacity-90">You can edit it here, then optionally polish/regenerate when ready.</div>
                          </div>
                        </AlertDescription>
                      </Alert>
                    </div>
                  )}

                  {/* TipTap Editor */}
                  <ChapterTipTapEditor
                    content={chapterContent}
                    onChange={setChapterContent}
                    onSelectionChange={handleSelectionChange}
                    editable={!isGenerating}
                    selectionMode={selectionMode}
                    onNoteMode={handleNoteMode}
                    onRewriteMode={handleRewriteMode}
                    onClearSelection={resetSelection}
                  />

                  {/* Selection Tools Panel */}
                  {selectionInfo && (
                    <div className="mt-6 rounded-2xl border border-brand-lavender/20 bg-white/90 p-4 shadow-sm animate-in fade-in slide-in-from-bottom-2 duration-200">
                      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                        <div>
                          <div className="text-xs font-semibold uppercase tracking-wide text-gray-900/60">Selected text</div>
                          <div className="text-sm font-semibold text-gray-900 mt-1">
                            {selectionInfo.text.trim().length > 160 ? `${selectionInfo.text.trim().slice(0, 160)}...` : selectionInfo.text.trim()}
                          </div>
                        </div>
                        <button
                          onClick={resetSelection}
                          className="text-xs font-semibold text-indigo-500 hover:underline"
                        >
                          Clear selection
                        </button>
                      </div>

                      <div className="flex gap-2 mb-4">
                        <button
                          onClick={() => setSelectionMode('note')}
                          className={`px-4 py-1.5 rounded-full text-xs font-semibold border transition-colors ${
                            selectionMode === 'note'
                              ? 'bg-brand-soft-purple text-white border-brand-soft-purple'
                              : 'bg-white text-gray-900 border-gray-200 hover:bg-gray-50'
                          }`}
                        >
                          Add note
                        </button>
                        <button
                          onClick={() => setSelectionMode('rewrite')}
                          className={`px-4 py-1.5 rounded-full text-xs font-semibold border transition-colors ${
                            selectionMode === 'rewrite'
                              ? 'bg-brand-forest text-white border-brand-forest'
                              : 'bg-white text-gray-900 border-gray-200 hover:bg-gray-50'
                          }`}
                        >
                          AI rewrite
                        </button>
                      </div>

                      {selectionMode === 'note' ? (
                        <div className="space-y-3">
                          <textarea
                            id="selection-note"
                            name="selectionNote"
                            value={selectionNote}
                            onChange={(e) => setSelectionNote(e.target.value)}
                            className="w-full min-h-[90px] rounded-lg border border-brand-lavender/20 p-3 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-brand-lavender/40"
                            placeholder="Add a note about this highlight (tone, continuity, change request)."
                          />
                          <div className="flex flex-wrap items-center gap-3 text-xs text-gray-500">
                            <label className="flex items-center gap-2">
                              <input
                                id="selection-apply-to-future"
                                name="applyToFuture"
                                type="checkbox"
                                checked={applyToFuture}
                                onChange={(e) => setApplyToFuture(e.target.checked)}
                                disabled={noteScope === 'global'}
                              />
                              Apply to future chapters
                            </label>
                            <label className="flex items-center gap-2">
                              <span>Scope</span>
                              <select
                                id="selection-note-scope"
                                name="noteScope"
                                value={noteScope}
                                onChange={(e) => setNoteScope(e.target.value as 'chapter' | 'global')}
                                className="rounded-md border border-gray-200 px-2 py-1 text-xs"
                              >
                                <option value="chapter">Chapter only</option>
                                <option value="global">Global guidance</option>
                              </select>
                            </label>
                          </div>
                          <button
                            onClick={saveSelectionNote}
                            disabled={selectionBusy || !selectionNote.trim()}
                            className="w-full sm:w-auto bg-brand-soft-purple text-white px-4 py-2 rounded-lg text-sm font-semibold hover:opacity-90 disabled:opacity-50 transition-opacity"
                          >
                            {selectionBusy ? 'Saving...' : 'Save Note'}
                          </button>
                        </div>
                      ) : (
                        <div className="space-y-3">
                          <div className="flex flex-wrap gap-2">
                            {selectionPresets.map((preset) => (
                              <button
                                key={preset.label}
                                onClick={() => setSelectionInstruction(preset.value)}
                                className={`px-3 py-1 rounded-full border text-xs font-semibold transition-colors ${
                                  selectionInstruction === preset.value
                                    ? 'bg-brand-forest text-white border-brand-forest'
                                    : 'border-gray-200 text-gray-900 hover:bg-gray-50'
                                }`}
                              >
                                {preset.label}
                              </button>
                            ))}
                          </div>
                          <textarea
                            id="selection-instruction"
                            name="selectionInstruction"
                            value={selectionInstruction}
                            onChange={(e) => setSelectionInstruction(e.target.value)}
                            className="w-full min-h-[90px] rounded-lg border border-brand-lavender/20 p-3 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-brand-lavender/40"
                            placeholder="Tell AI how to rewrite this selection (shorter, punchier, clarify voice, fix continuity)."
                          />
                          <div className="flex flex-col sm:flex-row gap-2">
                            <button
                              onClick={previewRewriteSelection}
                              disabled={previewLoading || !selectionInstruction.trim()}
                              className="w-full sm:w-auto border border-brand-forest text-gray-900 px-4 py-2 rounded-lg text-sm font-semibold hover:bg-brand-forest hover:text-white disabled:opacity-50 transition-colors"
                            >
                              {previewLoading ? (
                                <>
                                  <ArrowPathIcon className="w-4 h-4 mr-1 animate-spin inline" />
                                  Generating preview...
                                </>
                              ) : (
                                'Preview Rewrite'
                              )}
                            </button>
                            <button
                              onClick={rewriteSelection}
                              disabled={selectionBusy || !selectionInstruction.trim()}
                              className="w-full sm:w-auto bg-brand-forest text-white px-4 py-2 rounded-lg text-sm font-semibold hover:opacity-90 disabled:opacity-50 transition-opacity"
                            >
                              {selectionBusy ? 'Rewriting...' : 'Apply AI Rewrite'}
                            </button>
                          </div>

                          {/* Inline Diff Preview */}
                          {previewOpen && (
                            <div className="rounded-xl border border-emerald-200 bg-emerald-50/30 p-4 space-y-3 animate-in fade-in slide-in-from-bottom-2 duration-200">
                              <div className="flex items-center justify-between">
                                <div className="text-xs font-semibold uppercase tracking-wide text-emerald-700">
                                  Inline Diff Preview
                                </div>
                                <DiffStats original={previewOriginal} proposed={previewProposed} />
                              </div>
                              <div className="rounded-lg border border-emerald-200 bg-white p-3">
                                <InlineDiff original={previewOriginal} proposed={previewProposed} />
                              </div>
                              <div className="flex flex-col sm:flex-row gap-2">
                                <button
                                  onClick={() => setPreviewOpen(false)}
                                  className="w-full sm:w-auto border border-gray-200 text-gray-700 px-4 py-2 rounded-lg text-sm font-semibold hover:bg-gray-50 transition-colors"
                                >
                                  Discard
                                </button>
                                <button
                                  onClick={async () => {
                                    if (!previewContent || !currentChapterId) {
                                      if (previewContent) {
                                        setChapterContent(previewContent)
                                        setOriginalContent(previewContent)
                                      }
                                      setPreviewOpen(false)
                                      resetSelection()
                                      return
                                    }
                                    try {
                                      setSelectionBusy(true)
                                      const authHeaders = await getAuthHeaders()
                                      const response = await fetchApi(`/api/v2/chapters/${currentChapterId}/confirm-rewrite`, {
                                        method: 'POST',
                                        headers: { ...authHeaders, 'Content-Type': 'application/json' },
                                        body: JSON.stringify({
                                          proposed_content: previewContent,
                                          original_selection_start: selectionInfo?.from ?? 0,
                                          original_selection_end: selectionInfo?.to ?? 0,
                                          instruction: selectionInstruction,
                                        }),
                                      })
                                      if (response.ok) {
                                        setChapterContent(previewContent)
                                        setOriginalContent(previewContent)
                                        showStatus('Rewrite applied and saved')
                                        runRippleAnalysis()
                                      } else {
                                        setChapterContent(previewContent)
                                        showStatus('Rewrite applied but save failed. Please save manually.', 0)
                                      }
                                    } catch {
                                      setChapterContent(previewContent)
                                      showStatus('Rewrite applied but save failed. Please save manually.', 0)
                                    } finally {
                                      setSelectionBusy(false)
                                      setPreviewOpen(false)
                                      resetSelection()
                                    }
                                  }}
                                  disabled={selectionBusy}
                                  className="w-full sm:w-auto bg-emerald-600 text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-emerald-700 transition-colors disabled:opacity-50"
                                >
                                  {selectionBusy ? 'Saving...' : 'Accept Changes'}
                                </button>
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Floating Bottom Action Bar */}
          {(isEditing || chapterContent) && (
            <div
              className="fixed bottom-0 left-0 right-0 bg-gradient-to-r from-white/95 via-brand-beige/20 to-white/95 backdrop-blur-lg border-t border-white/50 p-3 sm:p-4 shadow-2xl z-40"
              style={{ paddingBottom: 'calc(1rem + env(safe-area-inset-bottom))' }}
            >
              <div className="max-w-4xl mx-auto flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2 text-sm text-gray-900/80 font-semibold">
                  {hasUnsavedChanges && (
                    <div className="flex items-center space-x-2 bg-orange-50 px-3 py-1 rounded-full border border-orange-200">
                      <div className="w-2 h-2 bg-orange-500 rounded-full animate-pulse"></div>
                      <span className="text-orange-700 font-bold">Unsaved changes</span>
                    </div>
                  )}
                  <div className="bg-brand-lavender/10 px-3 py-1 rounded-full border border-brand-lavender/20">
                    <span className="text-gray-900 font-bold">{wordCount.toLocaleString()} words</span>
                  </div>
                </div>

                <div className="flex flex-col sm:flex-row gap-2 w-full sm:w-auto">
                  <button
                    onClick={saveChapter}
                    disabled={!hasUnsavedChanges || isSaving}
                    className="bg-gradient-to-r from-emerald-500 to-emerald-600 text-white px-6 py-2 rounded-xl font-bold hover:shadow-lg transition-all hover:scale-105 disabled:opacity-50 disabled:hover:scale-100 w-full sm:w-auto"
                  >
                    {isSaving ? (
                      <>
                        <ArrowPathIcon className="w-4 h-4 mr-2 animate-spin inline" />
                        Saving...
                      </>
                    ) : (
                      <>
                        <BookmarkIcon className="w-4 h-4 mr-2 inline" />
                        Save
                      </>
                    )}
                  </button>

                  <button
                    onClick={() => setRewriteDialogOpen(true)}
                    disabled={isGenerating}
                    className="bg-gradient-to-r from-blue-500 to-blue-600 text-white px-6 py-2 rounded-xl font-bold hover:shadow-lg transition-all hover:scale-105 disabled:opacity-50 w-full sm:w-auto"
                  >
                    {isGenerating ? (
                      <>
                        <ArrowPathIcon className="w-4 h-4 mr-2 animate-spin inline" />
                        Regenerating...
                      </>
                    ) : (
                      <>
                        <ArrowPathIcon className="w-4 h-4 mr-2 inline" />
                        Regenerate
                      </>
                    )}
                  </button>

                  <button
                    onClick={approveChapter}
                    disabled={isApproving}
                    className="bg-gray-900 text-white px-6 py-2 rounded-xl font-semibold hover:bg-gray-800 transition-all w-full sm:w-auto disabled:opacity-50"
                  >
                    <CheckCircleIcon className="w-4 h-4 mr-2 inline" />
                    {isApproving ? 'Approving...' : 'Approve Chapter'}
                  </button>
                  {focusMode && (
                    <button
                      onClick={() => setFocusMode(false)}
                      className="border border-gray-200 text-gray-700 px-6 py-2 rounded-xl font-bold hover:bg-gray-50 transition-all w-full sm:w-auto"
                    >
                      Exit Focus Mode
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Ripple Analysis Notification */}
        <AnimatePresence>
          {showRippleNotification && rippleData && rippleData.affected_chapters.length > 0 && (
            <motion.div
              key="ripple-report"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 20 }}
              transition={{ duration: 0.2 }}
              className="fixed bottom-24 right-4 sm:right-8 z-50 max-w-md w-full sm:w-auto"
            >
              <RippleReport
                affectedChapters={rippleData.affected_chapters}
                sourceChapter={rippleData.source_chapter}
                totalChecked={rippleData.total_checked}
                onNavigateToChapter={(num) => {
                  setShowRippleNotification(false)
                  requestChapterChange(num)
                }}
                onDismiss={() => setShowRippleNotification(false)}
                onFixComplete={() => showStatus('Downstream chapters queued for rewrite')}
              />
            </motion.div>
          )}
        </AnimatePresence>

        {/* Ripple loading indicator */}
        {rippleLoading && (
          <div className="fixed bottom-24 right-4 sm:right-8 z-50">
            <div className="flex items-center gap-2 bg-white/95 backdrop-blur-sm rounded-full px-4 py-2 shadow-lg border border-brand-lavender/20 text-xs font-semibold text-gray-900">
              <ArrowPathIcon className="w-4 h-4 animate-spin" />
              Checking downstream chapters...
            </div>
          </div>
        )}

        {/* Collapsible Sidebar */}
        {!focusMode && (
          <CollapsibleSidebar
            isOpen={sidebarOpen}
            onToggle={() => setSidebarOpen(!sidebarOpen)}
          />
        )}
      </div>

      {/* Unsaved Changes Dialog */}
      <Dialog
        open={unsavedNavDialogOpen}
        onOpenChange={(open) => {
          setUnsavedNavDialogOpen(open)
          if (!open) setPendingChapterTarget(null)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Unsaved changes</DialogTitle>
          </DialogHeader>
          <div className="space-y-2 text-sm text-gray-600">
            <p>
              You have unsaved changes in Chapter {currentChapter}. What would you like to do before switching
              to Chapter {pendingChapterTarget ?? '...'}?
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setUnsavedNavDialogOpen(false); setPendingChapterTarget(null) }}>
              Cancel
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                const target = pendingChapterTarget
                setUnsavedNavDialogOpen(false)
                setPendingChapterTarget(null)
                if (!target) return
                setCurrentChapter(target)
                updateChapterInUrl(target)
              }}
            >
              Discard &amp; Switch
            </Button>
            <Button
              onClick={async () => {
                const target = pendingChapterTarget
                if (!target) { setUnsavedNavDialogOpen(false); setPendingChapterTarget(null); return }
                const ok = await saveChapter()
                setUnsavedNavDialogOpen(false)
                setPendingChapterTarget(null)
                if (ok) {
                  setCurrentChapter(target)
                  updateChapterInUrl(target)
                } else {
                  showStatus('Save failed — your changes are still in the editor. Try saving again.', 8000)
                }
              }}
              disabled={isSaving}
            >
              {isSaving ? 'Saving...' : 'Save & Switch'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Rewrite Dialog */}
      <Dialog open={rewriteDialogOpen} onOpenChange={setRewriteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rewrite Chapter {currentChapter}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-sm text-gray-600">
            <p>Select how you want to rewrite this chapter.</p>
            <div className="space-y-2">
              <label className="flex items-start gap-2">
                <input type="radio" name="rewriteMode" value="polish" checked={rewriteMode === 'polish'} onChange={() => setRewriteMode('polish')} />
                <span><strong>Polish / Canon Rewrite</strong> keeps structure and plot, improves clarity and specificity.</span>
              </label>
              <label className="flex items-start gap-2">
                <input type="radio" name="rewriteMode" value="full" checked={rewriteMode === 'full'} onChange={() => setRewriteMode('full')} />
                <span><strong>Full Regenerate</strong> wipes and recreates the chapter using the latest system.</span>
              </label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRewriteDialogOpen(false)}>Cancel</Button>
            <Button
              onClick={() => { setRewriteDialogOpen(false); rewriteChapter(rewriteMode) }}
              disabled={isGenerating}
            >
              {rewriteMode === 'polish' ? 'Polish Chapter' : 'Regenerate Chapter'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Version History Dialog */}
      {currentChapterId && (
        <ChapterVersionHistoryDialog
          open={versionsOpen}
          onOpenChange={setVersionsOpen}
          chapterId={currentChapterId}
          currentContent={chapterContent}
          onRestore={async (nextContent) => {
            setChapterContent(nextContent)
          }}
        />
      )}
    </ProjectLayout>
  )
}
