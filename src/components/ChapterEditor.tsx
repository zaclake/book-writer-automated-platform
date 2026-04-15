'use client'

import React, { useState, useEffect, useRef, startTransition } from 'react'
import { useAuthToken, ANONYMOUS_USER } from '@/lib/auth'
import { fetchApi } from '@/lib/api-client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { toast } from '@/hooks/useAppToast'
import { useAutoSave, useSessionRecovery, SessionRecoveryPrompt } from '@/hooks/useAutoSave'
import { getOfflineManager } from '@/lib/firestore-offline'
import { ChapterVersionHistoryDialog } from '@/components/ChapterVersionHistory'
import { AutoSaveConflictDialog } from '@/components/AutoSaveConflictDialog'

interface Chapter {
  id: string
  project_id: string
  chapter_number: number
  title?: string
  content: string
  metadata: {
    word_count: number
    target_word_count: number
    stage: 'draft' | 'revision' | 'complete'
    created_at: string
    updated_at: string
  }
  quality_scores?: {
    overall_rating: number
    prose: number
    character: number
    story: number
    emotion: number
    freshness: number
  }
  director_notes: Array<{
    note_id: string
    content: string
    created_by: string
    created_at: string
    resolved: boolean
    position?: number
  }>
}

interface DirectorNote {
  note_id: string
  content: string
  created_at: string
  resolved: boolean
  position?: number
  selection_start?: number
  selection_end?: number
  selection_text?: string
  apply_to_future?: boolean
  intent?: string
  scope?: string
}

interface ChapterEditorProps {
  chapterId: string
  projectId: string
  onSave?: (chapter: Chapter) => void
  onClose?: () => void
}

const ChapterEditor: React.FC<ChapterEditorProps> = ({
  chapterId,
  projectId,
  onSave,
  onClose
}) => {
  const { getAuthHeaders, user: authUser, isLoaded } = useAuthToken()
  const user = authUser || ANONYMOUS_USER
  const [chapter, setChapter] = useState<Chapter | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [isRewriting, setIsRewriting] = useState(false)
  const [versionsOpen, setVersionsOpen] = useState(false)
  const [isRebuildingArtifacts, setIsRebuildingArtifacts] = useState(false)
  const [conflictOpen, setConflictOpen] = useState(false)
  const conflictResolverRef = useRef<null | ((decision: 'use_local' | 'discard') => void)>(null)
  const [conflictLocalPreview, setConflictLocalPreview] = useState('')
  
  // Editor state
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [stage, setStage] = useState<'draft' | 'revision' | 'complete'>('draft')
  
  // Director's notes state
  const [showNotesPanel, setShowNotesPanel] = useState(false)
  const [newNote, setNewNote] = useState('')
  const [selectedText, setSelectedText] = useState('')
  const [selectedPosition, setSelectedPosition] = useState<number | undefined>()
  const [selectedRange, setSelectedRange] = useState<{ start: number; end: number } | null>(null)
  const [applyToFuture, setApplyToFuture] = useState(true)
  const [rewriteSelectionNow, setRewriteSelectionNow] = useState(false)
  const [noteScope, setNoteScope] = useState<'chapter' | 'global'>('chapter')
  const [selectionInstruction, setSelectionInstruction] = useState('')
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewOriginal, setPreviewOriginal] = useState('')
  const [previewProposed, setPreviewProposed] = useState('')
  const [previewContent, setPreviewContent] = useState('')
  const [previewLoading, setPreviewLoading] = useState(false)
  const [bubblePos, setBubblePos] = useState<{ top: number; left: number } | null>(null)
  const [bubbleStyle, setBubbleStyle] = useState<{ top: number; left: number } | null>(null)
  const [showResolvedNotes, setShowResolvedNotes] = useState(false)
  const [notes, setNotes] = useState<DirectorNote[]>([])
  const [isLoadingNotes, setIsLoadingNotes] = useState(false)
  
  // Reference files state
  const [showReferencePanel, setShowReferencePanel] = useState(false)
  const [referenceFiles, setReferenceFiles] = useState<any[]>([])
  const [isLoadingReferences, setIsLoadingReferences] = useState(false)
  const [focusMode, setFocusMode] = useState(false)
  
  const contentRef = useRef<HTMLTextAreaElement>(null)
  const bubbleRef = useRef<HTMLDivElement>(null)
  const selectionTimerRef = useRef<number | null>(null)

  // Auto-save data structure
  const chapterData = {
    title,
    content,
    stage,
    chapterId,
    projectId
  }

  // Auto-save function for the hook
  const autoSaveFunction = async (data: typeof chapterData) => {
    if (!user || !chapter) return
    
    try {
      // Use offline manager for intelligent online/offline handling
              await getOfflineManager().updateDocument(
        `projects/${data.projectId}/chapters`,
        data.chapterId,
        {
          title: data.title,
          content: data.content,
          stage: data.stage,
          metadata: {
            ...chapter.metadata,
            updated_at: new Date().toISOString(),
            word_count: data.content.split(/\s+/).filter(word => word.length > 0).length
          }
        }
      )
    } catch (error) {
      console.error('Auto-save error:', error)
      throw error
    }
  }

  // Set up auto-save hook
  const autoSave = useAutoSave(chapterData, autoSaveFunction, {
    key: `chapter_${chapterId}`,
    interval: 30000, // Save every 30 seconds
    debounceDelay: 2000, // Wait 2 seconds after typing stops
    enableLocalStorage: true,
    enableFirestore: true,
    onConflict: async ({ local }) => {
      setConflictLocalPreview(String((local as any)?.content || local || ''))
      setConflictOpen(true)
      return await new Promise<'use_local' | 'discard'>(resolve => {
        conflictResolverRef.current = resolve
      })
    }
  })

  // Set up session recovery
  const sessionRecovery = useSessionRecovery(
    `chapter_${chapterId}`,
    chapterData,
    (recoveredData) => {
      // Batch state updates to prevent multiple re-renders
      startTransition(() => {
        setTitle(recoveredData.title)
        setContent(recoveredData.content)
        setStage(recoveredData.stage)
      })
    }
  )

  useEffect(() => {
    if (isLoaded && chapterId) {
      loadChapter()
      loadReferenceFiles()
      loadNotes()
    }
  }, [isLoaded, chapterId, showResolvedNotes])

  useEffect(() => {
    if (noteScope === 'global' && !applyToFuture) {
      setApplyToFuture(true)
    }
  }, [noteScope, applyToFuture])

  const selectionPresets = [
    { label: 'Tighten', value: 'Tighten this selection without losing meaning.' },
    { label: 'Clarify', value: 'Clarify the intent and remove ambiguity.' },
    { label: 'Punchier', value: 'Make this more punchy and energetic.' },
    { label: 'Smoother', value: 'Improve flow and sentence rhythm.' },
    { label: 'Continuity', value: 'Fix continuity with the surrounding context.' }
  ]

  useEffect(() => {
    if (!selectedRange || !contentRef.current) {
      setBubbleStyle(null)
      return
    }
    const update = () => {
      if (!contentRef.current || !selectedRange) return
      const coords = getCaretCoords(contentRef.current, selectedRange.end)
      setBubblePos(coords)
    }
    update()
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    return () => {
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
    }
  }, [selectedRange])

  useEffect(() => {
    const onSelectionChange = () => {
      if (!contentRef.current) return
      if (document.activeElement !== contentRef.current) return
      if (selectionTimerRef.current !== null) {
        window.clearTimeout(selectionTimerRef.current)
      }
      selectionTimerRef.current = window.setTimeout(() => {
        updateSelectionFromTextarea()
      }, 0)
    }
    document.addEventListener('selectionchange', onSelectionChange)
    return () => {
      document.removeEventListener('selectionchange', onSelectionChange)
    }
  }, [content])

  useEffect(() => {
    if (!bubblePos || !bubbleRef.current) return
    const rect = bubbleRef.current.getBoundingClientRect()
    let left = bubblePos.left - rect.width / 2
    left = Math.max(8, Math.min(left, window.innerWidth - rect.width - 8))
    let top = bubblePos.top - rect.height - 12
    if (top < 8) {
      top = bubblePos.top + 24
    }
    setBubbleStyle({ top, left })
  }, [bubblePos, selectedText])

  useEffect(() => {
    if (focusMode) {
      setShowNotesPanel(false)
      setShowReferencePanel(false)
    }
  }, [focusMode])

  const loadReferenceFiles = async () => {
    if (!user) return
    
    try {
      setIsLoadingReferences(true)
      const authHeaders = await getAuthHeaders()
      const response = await fetchApi(`/api/v2/projects/${projectId}/references`, {
        headers: {
          ...authHeaders
        }
      })

      if (response.ok) {
        const data = await response.json()
        setReferenceFiles(data.files || [])
      } else {
        console.warn('Failed to load reference files')
      }
    } catch (error) {
      console.error('Error loading reference files:', error)
    } finally {
      setIsLoadingReferences(false)
    }
  }

  const loadNotes = async () => {
    if (!user) return

    try {
      setIsLoadingNotes(true)
      const authHeaders = await getAuthHeaders()
      const response = await fetchApi(`/api/chapters/${chapterId}/notes?include_resolved=${showResolvedNotes ? 'true' : 'false'}`, {
        headers: {
          ...authHeaders
        }
      })
      if (response.ok) {
        const data = await response.json()
        setNotes(data.notes || [])
      } else {
        console.warn('Failed to load notes')
      }
    } catch (error) {
      console.error('Error loading notes:', error)
    } finally {
      setIsLoadingNotes(false)
    }
  }

  const loadChapter = async () => {
    if (!user) return
    
    try {
      setIsLoading(true)
      const authHeaders = await getAuthHeaders()
      const response = await fetchApi(`/api/chapters/${chapterId}?project_id=${encodeURIComponent(projectId)}`, {
        headers: {
          ...authHeaders
        }
      })

      if (response.ok) {
        const data = await response.json()
        const chapterData = data.chapter ?? data
        
        // Batch all state updates to prevent multiple re-renders
        startTransition(() => {
          setChapter(chapterData)
          setTitle(chapterData.title || `Chapter ${chapterData.chapter_number}`)
          setContent(chapterData.content)
          setStage(chapterData.metadata.stage)
        })
      } else {
        throw new Error('Failed to load chapter')
      }
    } catch (error) {
      console.error('Error loading chapter:', error)
      toast({
        title: "Looks like we hit a snag",
        description: "We're having trouble loading your chapter. Let's try again!",
        variant: "destructive"
      })
    } finally {
      setIsLoading(false)
    }
  }

  const saveChapter = async () => {
    if (!user || !chapter) return

    try {
      setIsSaving(true)
      const authHeaders = await getAuthHeaders()
      const response = await fetchApi(`/api/chapters/${chapterId}?project_id=${encodeURIComponent(projectId)}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders
        },
        body: JSON.stringify({
          title,
          content,
          stage
        })
      })

      if (response.ok) {
        const data = await response.json()
        toast({
          title: "Beautiful work! ✨",
          description: "Your chapter has been saved. Keep blooming!"
        })
        
        // Reload the chapter to get updated data
        await loadChapter()
        
        if (onSave && chapter) {
          onSave({ ...chapter, title, content, metadata: { ...chapter.metadata, stage } })
        }
      } else {
        throw new Error('Failed to save chapter')
      }
    } catch (error) {
      console.error('Error saving chapter:', error)
      toast({
        title: "Looks like we hit a snag",
        description: "We couldn't save your chapter right now. Let's try again!",
        variant: "destructive"
      })
    } finally {
      setIsSaving(false)
    }
  }

  const rebuildArtifacts = async () => {
    if (!chapterId) return
    setIsRebuildingArtifacts(true)
    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetchApi(`/api/v2/chapters/${chapterId}/rebuild-artifacts`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders
        }
      })
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData?.detail || errorData?.error || 'Failed to rebuild continuity artifacts')
      }
      toast({
        title: 'Rebuild scheduled',
        description: 'Canon log and chapter ledger rebuild has been scheduled.'
      })
    } catch (error) {
      console.error('Error rebuilding artifacts:', error)
      toast({
        title: 'Rebuild failed',
        description: "We couldn't schedule that rebuild. Please try again.",
        variant: 'destructive'
      })
    } finally {
      setIsRebuildingArtifacts(false)
    }
  }

  const approveChapter = async () => {
    await saveChapter()
    setStage('complete')
    toast({
      title: "Chapter Approved",
      description: "Chapter has been marked as complete."
    })
  }

  const requestRewrite = async () => {
    try {
      if (!chapter) return
      setIsRewriting(true)

      toast({
        title: "Rewrite Requested",
        description: "Chapter rewrite has been queued. This may take a few minutes."
      })

      const authHeaders = await getAuthHeaders()
      const response = await fetchApi('/api/v2/chapters/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders
        },
        body: JSON.stringify({
          project_id: projectId,
          chapter_number: chapter.chapter_number,
          target_word_count: chapter.metadata?.target_word_count || 2000,
          stage: 'complete'
        })
      })

      if (!response.ok && response.status !== 202) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.message || 'Failed to start rewrite')
      }

      await loadChapter()
      setStage('revision')
      toast({
        title: "Rewrite Complete",
        description: "Chapter has been rewritten. Please review the changes."
      })
    } catch (error) {
      console.error('Error requesting rewrite:', error)
      toast({
        title: "Looks like we hit a snag",
        description: "We couldn't start the rewrite just now. Let's try again!",
        variant: "destructive"
      })
    } finally {
      setIsRewriting(false)
    }
  }

  const getCaretCoords = (textarea: HTMLTextAreaElement, position: number) => {
    const style = window.getComputedStyle(textarea)
    const div = document.createElement('div')
    div.style.position = 'absolute'
    div.style.visibility = 'hidden'
    div.style.whiteSpace = 'pre-wrap'
    div.style.wordBreak = 'break-word'
    div.style.top = '0'
    div.style.left = '-9999px'
    div.style.width = style.width
    div.style.padding = style.padding
    div.style.border = style.border
    div.style.boxSizing = style.boxSizing
    div.style.fontFamily = style.fontFamily
    div.style.fontSize = style.fontSize
    div.style.lineHeight = style.lineHeight
    div.style.letterSpacing = style.letterSpacing

    div.textContent = textarea.value.substring(0, position)
    const span = document.createElement('span')
    span.textContent = textarea.value.substring(position) || '.'
    div.appendChild(span)
    document.body.appendChild(div)

    const top = textarea.getBoundingClientRect().top + span.offsetTop - textarea.scrollTop
    const left = textarea.getBoundingClientRect().left + span.offsetLeft - textarea.scrollLeft

    document.body.removeChild(div)
    return { top, left }
  }

  const updateSelectionFromTextarea = () => {
    if (!contentRef.current) return
    const start = contentRef.current.selectionStart
    const end = contentRef.current.selectionEnd
    if (start === null || end === null) return
    if (start === end) {
      setSelectedText('')
      setSelectedPosition(undefined)
      setSelectedRange(null)
      setBubblePos(null)
      setBubbleStyle(null)
      return
    }
    const selected = content.substring(start, end)
    setSelectedText(selected)
    setSelectedPosition(start)
    setSelectedRange({ start, end })
    const coords = getCaretCoords(contentRef.current, end)
    setBubblePos(coords)
  }

  const handleTextSelection = () => {
    if (selectionTimerRef.current !== null) {
      window.clearTimeout(selectionTimerRef.current)
    }
    selectionTimerRef.current = window.setTimeout(() => {
      updateSelectionFromTextarea()
    }, 0)
  }

  const addDirectorNote = async () => {
    if (!user || !newNote.trim()) return

    try {
          const authHeaders = await getAuthHeaders()
      const response = await fetchApi(`/api/chapters/${chapterId}/notes`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders
        },
        body: JSON.stringify({
          content: newNote,
          position: selectedPosition,
          selection_start: selectedRange?.start,
          selection_end: selectedRange?.end,
          selection_text: selectedText,
          apply_to_future: applyToFuture,
              scope: noteScope
        })
      })

      if (!response.ok) {
        throw new Error('Failed to add note')
      }

      if (rewriteSelectionNow && selectedRange) {
        await applySelectedRewrite(newNote, selectedRange.start, selectedRange.end)
      }

      // Batch state updates to prevent multiple re-renders
      startTransition(() => {
        setNewNote('')
        setSelectedText('')
      })
      setSelectedPosition(undefined)
      setSelectedRange(null)
      setRewriteSelectionNow(false)
      setNoteScope('chapter')
      setSelectionInstruction('')
      await loadNotes()
      
      toast({
        title: "Note Added",
        description: rewriteSelectionNow ? "Note applied and chapter updated." : "Director's note has been added successfully."
      })
    } catch (error) {
      console.error('Error adding director note:', error)
      toast({
        title: "Looks like we hit a snag",
        description: "We couldn't save your note right now. Let's try again!",
        variant: "destructive"
      })
    }
  }

  const applySelectedRewrite = async (instruction: string, start: number, end: number) => {
    try {
      setIsRewriting(true)
      const authHeaders = await getAuthHeaders()
      const response = await fetchApi(`/api/v2/chapters/${chapterId}/rewrite-section`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders
        },
        body: JSON.stringify({
          selection_start: start,
          selection_end: end,
          instruction
        })
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.message || 'Failed to rewrite selection')
      }

      const data = await response.json()
      startTransition(() => {
        setContent(data.content || content)
        setStage('revision')
      })
      await loadChapter()
      setSelectedText('')
      setSelectedRange(null)
      setSelectedPosition(undefined)
      setSelectionInstruction('')
      setBubblePos(null)
      setBubbleStyle(null)
    } catch (error) {
      console.error('Error rewriting selected section:', error)
      toast({
        title: "Rewrite failed",
        description: "We couldn't rewrite that selection right now.",
        variant: "destructive"
      })
    } finally {
      setIsRewriting(false)
    }
  }

  const findUpdatedSelection = (original: string, updated: string, range: { start: number; end: number }) => {
    const prefix = original.slice(Math.max(0, range.start - 40), range.start)
    const suffix = original.slice(range.end, Math.min(original.length, range.end + 40))
    let startIdx = -1
    let endIdx = -1
    if (prefix) {
      startIdx = updated.indexOf(prefix)
      if (startIdx !== -1) {
        startIdx += prefix.length
      }
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

  const previewSelectionRewrite = async () => {
    if (!chapter || !selectedRange || !selectionInstruction.trim()) return
    try {
      setPreviewLoading(true)
      const authHeaders = await getAuthHeaders()
      const response = await fetchApi(`/api/v2/chapters/${chapter.id}/rewrite-section`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders
        },
        body: JSON.stringify({
          selection_start: selectedRange.start,
          selection_end: selectedRange.end,
          instruction: selectionInstruction
        })
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.message || 'Failed to rewrite selection')
      }

      const data = await response.json()
      const proposed = findUpdatedSelection(content, data.content || '', selectedRange)
      setPreviewOriginal(selectedText)
      setPreviewProposed(proposed)
      setPreviewContent(data.content || '')
      setPreviewOpen(true)
    } catch (error) {
      console.error('Preview rewrite failed:', error)
      toast({
        title: "Preview failed",
        description: "We couldn't preview that rewrite just now.",
        variant: "destructive"
      })
    } finally {
      setPreviewLoading(false)
    }
  }

  const resolveNote = async (noteId: string) => {
    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetchApi(`/api/chapters/${chapterId}/notes/${noteId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders
        },
        body: JSON.stringify({ resolved: true })
      })

      if (!response.ok) {
        throw new Error('Failed to resolve note')
      }

      await loadNotes()
      toast({
        title: "Note Resolved",
        description: "Director's note has been marked as resolved."
      })
    } catch (error) {
      console.error('Error resolving note:', error)
      toast({
        title: "Looks like we hit a snag",
        description: "We couldn't resolve that note just now.",
        variant: "destructive"
      })
    }
  }

  const formatNoteDate = (timestamp: any) => {
    if (!timestamp) return 'Unknown'
    if (timestamp?.toDate) return timestamp.toDate().toLocaleDateString()
    if (timestamp?.seconds) return new Date(timestamp.seconds * 1000).toLocaleDateString()
    return new Date(timestamp).toLocaleDateString()
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-pulse text-gray-500">Loading chapter...</div>
      </div>
    )
  }

  if (!chapter) {
    return (
      <div className="text-center text-gray-500 p-8">
        Chapter not found
      </div>
    )
  }

  const notesPanel = (
    <Card>
      <CardHeader>
        <CardTitle>Director's Notes</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Add New Note */}
        <div className="border-b pb-4">
          <Label htmlFor="new-note">Add Note</Label>
          {selectedText && (
            <div className="mt-2 rounded-lg border border-brand-lavender/20 bg-brand-beige/20 p-3 text-xs text-gray-600 space-y-2">
              <div className="flex items-start justify-between gap-3">
                <div className="font-semibold text-gray-700">Selected highlight</div>
                <button
                  type="button"
                  className="text-brand-soft-purple hover:underline"
                  onClick={() => {
                    setSelectedText('')
                    setSelectedRange(null)
                    setSelectedPosition(undefined)
                    setRewriteSelectionNow(false)
                    setSelectionInstruction('')
                    setPreviewOpen(false)
                    setPreviewOriginal('')
                    setPreviewProposed('')
                    setPreviewContent('')
                    setBubblePos(null)
                    setBubbleStyle(null)
                  }}
                >
                  Clear
                </button>
              </div>
              <div className="leading-relaxed">"{selectedText.substring(0, 160)}{selectedText.length > 160 ? '…' : ''}"</div>
              <label className="flex items-center gap-2 text-xs text-gray-600">
                <input
                  type="checkbox"
                  checked={rewriteSelectionNow}
                  onChange={(e) => setRewriteSelectionNow(e.target.checked)}
                />
                Rewrite this selection now with AI
              </label>
            </div>
          )}
          {selectedRange && (
            <div className="mt-3 space-y-3">
              <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">AI Highlight Tools</div>
              <div className="flex flex-wrap gap-2">
                {selectionPresets.map((preset) => (
                  <button
                    key={preset.label}
                    type="button"
                    onClick={() => setSelectionInstruction(preset.value)}
                    className="px-3 py-1 rounded-full border border-gray-200 text-xs font-semibold text-gray-700 hover:bg-gray-50"
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
              <Textarea
                value={selectionInstruction}
                onChange={(e) => setSelectionInstruction(e.target.value)}
                placeholder="Tell AI how to rewrite the selected text."
                rows={3}
              />
              <div className="flex flex-col sm:flex-row gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={previewSelectionRewrite}
                  disabled={previewLoading || !selectionInstruction.trim()}
                  className="w-full sm:w-auto"
                >
                  {previewLoading ? 'Preparing…' : 'Preview Rewrite'}
                </Button>
                <Button
                  type="button"
                  onClick={() => {
                    if (!selectedRange) return
                    applySelectedRewrite(selectionInstruction, selectedRange.start, selectedRange.end)
                  }}
                  disabled={!selectionInstruction.trim() || isRewriting}
                  className="w-full sm:w-auto"
                >
                  {isRewriting ? 'Rewriting...' : 'Apply AI Rewrite'}
                </Button>
              </div>
              {previewOpen && (
                <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-3 space-y-3">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                      <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">Before</div>
                      <div className="mt-1 rounded-lg border border-gray-200 bg-white p-2 text-sm text-gray-800 whitespace-pre-wrap">
                        {previewOriginal || selectedText}
                      </div>
                    </div>
                    <div>
                      <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">After</div>
                      <div className="mt-1 rounded-lg border border-emerald-200 bg-white p-2 text-sm text-gray-800 whitespace-pre-wrap">
                        {previewProposed}
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-col sm:flex-row gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => setPreviewOpen(false)}
                      className="w-full sm:w-auto"
                    >
                      Discard
                    </Button>
                    <Button
                      type="button"
                      onClick={() => {
                        if (previewContent) {
                          startTransition(() => {
                            setContent(previewContent)
                            setStage('revision')
                          })
                        }
                        setPreviewOpen(false)
                  setSelectedText('')
                  setSelectedRange(null)
                  setSelectedPosition(undefined)
                  setSelectionInstruction('')
                  setBubblePos(null)
                  setBubbleStyle(null)
                      }}
                      className="w-full sm:w-auto bg-emerald-600 hover:bg-emerald-700 text-white"
                    >
                      Apply Preview
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
          <Textarea
            id="new-note"
            value={newNote}
            onChange={(e) => setNewNote(e.target.value)}
            placeholder="Add feedback, suggestions, or revision notes for this chapter."
            rows={3}
            className="mb-2"
          />
          <div className="space-y-2 mb-3">
            <label className="flex items-center gap-2 text-xs text-gray-600">
              <input
                type="checkbox"
                checked={applyToFuture}
                onChange={(e) => setApplyToFuture(e.target.checked)}
                disabled={noteScope === 'global'}
              />
              Apply to future chapters
            </label>
            <div className="flex items-center gap-2 text-xs text-gray-600">
              <Label className="text-xs">Scope</Label>
              <select
                value={noteScope}
                onChange={(e) => setNoteScope(e.target.value as 'chapter' | 'global')}
                className="border border-gray-300 rounded px-2 py-1 text-xs"
              >
                <option value="chapter">Chapter only</option>
                <option value="global">Global guidance</option>
              </select>
            </div>
          </div>
          <Button
            onClick={addDirectorNote}
            disabled={!newNote.trim()}
            size="sm"
            className="w-full"
          >
            Add Note
          </Button>
        </div>

        {/* Existing Notes */}
        <div className="space-y-3">
          <label className="flex items-center gap-2 text-xs text-gray-600">
            <input
              type="checkbox"
              checked={showResolvedNotes}
              onChange={(e) => setShowResolvedNotes(e.target.checked)}
            />
            Show resolved notes
          </label>
          {isLoadingNotes ? (
            <p className="text-gray-500 text-sm">Loading notes...</p>
          ) : notes.length === 0 ? (
            <p className="text-gray-500 text-sm">No notes yet</p>
          ) : (
            notes.map((note) => (
              <div
                key={note.note_id}
                className={`p-3 rounded-lg border ${
                  note.resolved ? 'bg-green-50 border-green-200' : 'bg-yellow-50 border-yellow-200'
                }`}
              >
                <div className="text-sm mb-2">{note.content}</div>
                {note.selection_text && (
                  <div className="text-xs text-gray-600 bg-white/70 border border-gray-200 rounded p-2 mb-2">
                    "{note.selection_text.substring(0, 120)}{note.selection_text.length > 120 ? '…' : ''}"
                  </div>
                )}
                <div className="flex items-center justify-between text-xs text-gray-500">
                  <span>
                    {formatNoteDate(note.created_at)}
                    {note.position !== undefined && ` • Position ${note.position}`}
                    {note.apply_to_future && ' • Future'}
                    {note.scope === 'global' && ' • Global'}
                  </span>
                  {!note.resolved && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => resolveNote(note.note_id)}
                      className="h-6 px-2 text-xs"
                    >
                      Resolve
                    </Button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  )

  return (
    <div className="max-w-7xl mx-auto p-4 md:p-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-6">
        <div>
          <h1 className="text-3xl font-bold">Chapter Editor</h1>
          <p className="text-gray-600">
            Chapter {chapter.chapter_number} • {chapter.metadata.word_count} words • {stage}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {onClose && (
            <Button variant="outline" onClick={onClose} className="w-full sm:w-auto">
              Close
            </Button>
          )}
          {!focusMode && (
            <>
              <Button
                variant="outline"
                onClick={() => setVersionsOpen(true)}
                className="w-full sm:w-auto"
                aria-label="Open chapter version history"
              >
                Versions
              </Button>
              <Button
                variant="outline"
                onClick={rebuildArtifacts}
                disabled={isRebuildingArtifacts}
                className="w-full sm:w-auto"
                aria-label="Rebuild continuity artifacts (canon log and chapter ledger)"
              >
                {isRebuildingArtifacts ? 'Rebuilding…' : 'Rebuild continuity'}
              </Button>
              <Button 
                variant="outline" 
                onClick={() => setShowNotesPanel(!showNotesPanel)}
                className="w-full sm:w-auto"
              >
                {showNotesPanel ? 'Hide Notes' : 'Show Notes'} ({notes.length})
              </Button>
              <Button
                variant="outline"
                onClick={() => setShowReferencePanel(!showReferencePanel)}
                className="w-full sm:w-auto"
              >
                {showReferencePanel ? 'Hide References' : 'Show References'} ({referenceFiles.length})
              </Button>
            </>
          )}
        </div>
      </div>

      <ChapterVersionHistoryDialog
        open={versionsOpen}
        onOpenChange={setVersionsOpen}
        chapterId={chapterId}
        currentContent={content}
        onRestore={async nextContent => {
          setContent(nextContent)
          await saveChapter()
        }}
      />

      <AutoSaveConflictDialog
        open={conflictOpen}
        onOpenChange={setConflictOpen}
        localPreview={conflictLocalPreview}
        onUseLocal={() => {
          conflictResolverRef.current?.('use_local')
          conflictResolverRef.current = null
          setConflictOpen(false)
        }}
        onDiscard={() => {
          conflictResolverRef.current?.('discard')
          conflictResolverRef.current = null
          setConflictOpen(false)
        }}
      />

      <div className={`grid grid-cols-1 ${!focusMode ? 'md:grid-cols-3' : ''} gap-6`}>
        {/* Main Editor */}
        <div className={focusMode ? 'md:col-span-3' : 'md:col-span-2'}>
          <Card>
            <CardHeader>
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                <CardTitle>Chapter Content</CardTitle>
                <div className="flex flex-wrap gap-2">
                  {/* Auto-save status indicator */}
                  <div className="flex items-center text-sm text-gray-500">
                    {autoSave.isSaving ? (
                      <span>Auto-saving...</span>
                    ) : autoSave.lastSaved ? (
                      <span>Last saved: {autoSave.lastSaved.toLocaleTimeString()}</span>
                    ) : autoSave.hasUnsavedChanges ? (
                      <span className="text-orange-600">Unsaved changes</span>
                    ) : (
                      <span>All changes saved</span>
                    )}
                  </div>
                  <Button
                    variant="outline"
                    onClick={requestRewrite}
                    disabled={isRewriting}
                    className="w-full sm:w-auto"
                  >
                    {isRewriting ? 'Rewriting...' : 'Request Rewrite'}
                  </Button>
                  <Button
                    variant="outline"
                    onClick={autoSave.manualSave}
                    disabled={autoSave.isSaving}
                    className="w-full sm:w-auto"
                  >
                    {autoSave.isSaving ? 'Saving...' : 'Save Now'}
                  </Button>
                  <Button
                    onClick={approveChapter}
                    disabled={autoSave.isSaving}
                    className="w-full sm:w-auto bg-green-600 hover:bg-green-700"
                  >
                    Approve Chapter
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => setFocusMode((prev) => !prev)}
                    className="w-full sm:w-auto lg:hidden"
                  >
                    {focusMode ? 'Exit Player Mode' : 'Player Mode'}
                  </Button>
                  {focusMode && (
                    <Button
                      variant="outline"
                      onClick={() => setShowNotesPanel((prev) => !prev)}
                      className="w-full sm:w-auto"
                    >
                      {showNotesPanel ? 'Hide Highlight Tools' : 'Highlight Tools'}
                    </Button>
                  )}
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Title */}
              <div className="space-y-2">
                <Label htmlFor="title">Title</Label>
                <Input
                  id="title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder={`Chapter ${chapter.chapter_number}`}
                />
              </div>

              {/* Stage */}
              <div className="space-y-2">
                <Label htmlFor="stage">Stage</Label>
                <select
                  id="stage"
                  value={stage}
                  onChange={(e) => setStage(e.target.value as 'draft' | 'revision' | 'complete')}
                  className="w-full p-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="draft">Draft</option>
                  <option value="revision">Revision</option>
                  <option value="complete">Complete</option>
                </select>
              </div>

              {/* Content */}
              <div className="space-y-2">
                <Label htmlFor="content">Content</Label>
                {selectedRange && bubbleStyle && (
                  <div
                    ref={bubbleRef}
                    className="fixed z-50 flex flex-wrap items-center gap-2 rounded-full border border-brand-lavender/30 bg-white/95 px-3 py-2 text-xs font-semibold text-brand-forest shadow-lg max-w-[calc(100vw-16px)]"
                    style={{ top: bubbleStyle.top, left: bubbleStyle.left }}
                  >
                    <button
                      type="button"
                      onClick={() => setShowNotesPanel(true)}
                      className="rounded-full px-3 py-1 border border-gray-200 text-gray-700 hover:bg-gray-50"
                    >
                      Notes
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setShowNotesPanel(true)
                        if (!selectionInstruction) {
                          setSelectionInstruction('Clarify the intent and improve flow.')
                        }
                      }}
                      className="rounded-full px-3 py-1 border border-gray-200 text-gray-700 hover:bg-gray-50"
                    >
                      AI
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedText('')
                        setSelectedRange(null)
                        setSelectedPosition(undefined)
                        setRewriteSelectionNow(false)
                        setSelectionInstruction('')
                        setPreviewOpen(false)
                        setPreviewOriginal('')
                        setPreviewProposed('')
                        setPreviewContent('')
                        setBubblePos(null)
                        setBubbleStyle(null)
                      }}
                      className="rounded-full px-3 py-1 border border-gray-200 text-gray-600 hover:bg-gray-50"
                    >
                      Clear
                    </button>
                  </div>
                )}
                <Textarea
                  ref={contentRef}
                  id="content"
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  onMouseUp={handleTextSelection}
                  onKeyUp={handleTextSelection}
                  onTouchEnd={handleTextSelection}
                  onSelect={handleTextSelection}
                  onPointerUp={handleTextSelection}
                  placeholder="Chapter content..."
                  rows={25}
                  className="font-mono text-sm leading-relaxed pb-24"
                  style={{ paddingBottom: 'calc(5rem + env(safe-area-inset-bottom))' }}
                />
                <div className="text-sm text-gray-500">
                  {content.split(/\s+/).filter(Boolean).length} words • Target: {chapter.metadata.target_word_count} words
                </div>
              </div>

              {/* Quality Scores */}
              {chapter.quality_scores && (
                <div className="border-t pt-4">
                  <h4 className="font-semibold mb-3">Quality Scores</h4>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
                    <div>Overall: {chapter.quality_scores.overall_rating}/10</div>
                    <div>Prose: {chapter.quality_scores.prose}/10</div>
                    <div>Character: {chapter.quality_scores.character}/10</div>
                    <div>Story: {chapter.quality_scores.story}/10</div>
                    <div>Emotion: {chapter.quality_scores.emotion}/10</div>
                    <div>Freshness: {chapter.quality_scores.freshness}/10</div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
          {focusMode && showNotesPanel && (
            <div className="mt-6">
              {notesPanel}
            </div>
          )}
        </div>

        {/* Director's Notes Panel */}
        {!focusMode && showNotesPanel && (
          <div className="md:col-span-1">
            {notesPanel}
          </div>
        )}

        {/* Reference Files Panel */}
      {!focusMode && showReferencePanel && (
          <div className="md:col-span-1">
            <Card>
              <CardHeader>
                <CardTitle>Reference Files</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {isLoadingReferences ? (
                  <div className="text-center text-gray-500">Loading references...</div>
                ) : referenceFiles.length === 0 ? (
                  <div className="text-center text-gray-500">No reference files found</div>
                ) : (
                  <div className="space-y-3">
                    {referenceFiles.map((file: any, index: number) => (
                      <div key={index} className="border-b pb-3">
                        <div className="flex items-center justify-between mb-2">
                          <h4 className="font-medium text-sm">{file.name}</h4>
                          <span className="text-xs text-gray-500">
                            {Math.round(file.size / 1024)}KB
                          </span>
                        </div>
                        {file.preview && (
                          <div className="text-xs text-gray-600 bg-gray-50 p-2 rounded max-h-20 overflow-y-auto">
                            {file.preview.substring(0, 200)}
                            {file.preview.length > 200 && '...'}
                          </div>
                        )}
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => window.open(`/api/v2/projects/${projectId}/references/${file.name}`, '_blank')}
                          className="mt-2 h-6 px-2 text-xs"
                        >
                          View Full
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}
      </div>


      {/* Session Recovery Prompt */}
      <SessionRecoveryPrompt
        isOpen={sessionRecovery.hasRecoverableData}
        onAccept={sessionRecovery.acceptRecovery}
        onReject={sessionRecovery.rejectRecovery}
        dataPreview={sessionRecovery.recoveredData?.content?.substring(0, 100)}
      />
    </div>
  )
}

export default ChapterEditor 