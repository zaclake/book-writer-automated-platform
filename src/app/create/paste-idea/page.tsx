'use client'

import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthToken } from '@/lib/auth'
import { createBookBibleProject } from '@/lib/book-bible-client'
import { fetchApi } from '@/lib/api-client'
import { BookBibleData, BookLengthTier, BookLengthSpecs } from '@/lib/types'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import Celebration from '@/components/ui/Celebration'
import { GlobalLoader } from '@/stores/useGlobalLoaderStore'

export default function PasteIdeaPage() {
  const router = useRouter()
  const { getAuthHeaders, isSignedIn } = useAuthToken()

  const [title, setTitle] = useState('')
  const [genre, setGenre] = useState('Fiction')
  const [content, setContent] = useState('')
  const [bookLengthTier, setBookLengthTier] = useState<BookLengthTier>(BookLengthTier.STANDARD_NOVEL)
  const [pacingPreference, setPacingPreference] = useState<'fast' | 'balanced' | 'expansive' | ''>('')
  const [targetAudience, setTargetAudience] = useState('')
  const [writingStyle, setWritingStyle] = useState('')
  const [involvementLevel, setInvolvementLevel] = useState<'hands_off' | 'balanced' | 'hands_on' | ''>('')
  const [purpose, setPurpose] = useState<'personal' | 'commercial' | 'educational' | ''>('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showCelebration, setShowCelebration] = useState(false)
  const [clarifyMode, setClarifyMode] = useState<'brief' | 'extended'>('brief')
  const [clarifyRound, setClarifyRound] = useState(1)
  const [questions, setQuestions] = useState<Array<{ id: string; question: string; why?: string }>>([])
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [followupQuestions, setFollowupQuestions] = useState<Array<{ id: string; question: string; why?: string }>>([])
  const [refinedContent, setRefinedContent] = useState('')
  const [refinedSummary, setRefinedSummary] = useState('')
  const [useRefinedContent, setUseRefinedContent] = useState(true)
  const [scriptNotes, setScriptNotes] = useState('')
  const [isClarifying, setIsClarifying] = useState(false)
  const [isRefining, setIsRefining] = useState(false)
  
  // Character limit constants
  const MAX_CHARACTERS = 100000
  const WARNING_THRESHOLD = 90000

  // Character count helpers
  const activeContent = useRefinedContent && refinedContent ? refinedContent : content
  const baseIdeaContent = content.trim().length > 0 ? content : activeContent
  const baseClarifyContent = scriptNotes.trim()
    ? `${baseIdeaContent.trim()}\n\n## Script & Non-negotiables\n${scriptNotes.trim()}`
    : baseIdeaContent
  const submissionContent = scriptNotes.trim()
    ? `${activeContent.trim()}\n\n## Script & Non-negotiables\n${scriptNotes.trim()}`
    : activeContent
  const currentCharCount = submissionContent.length
  const isNearLimit = currentCharCount >= WARNING_THRESHOLD
  const isOverLimit = currentCharCount > MAX_CHARACTERS
  const remainingChars = MAX_CHARACTERS - currentCharCount

  const getCharCountColor = () => {
    if (isOverLimit) return 'text-red-600'
    if (isNearLimit) return 'text-orange-600'
    return 'text-gray-500'
  }

  const deriveTitleFromContent = (text: string): string => {
    const lines = text.split('\n').map(l => l.trim()).filter(Boolean)
    if (lines.length === 0) return 'Untitled Idea'
    let candidate = lines[0]
    if (candidate.length > 100) candidate = candidate.slice(0, 100)
    return candidate
  }

  const progressIntervalRef = useRef<NodeJS.Timeout | null>(null)

  useEffect(() => {
    return () => {
      if (progressIntervalRef.current) {
        clearInterval(progressIntervalRef.current)
        progressIntervalRef.current = null
      }
      GlobalLoader.forceHide()
    }
  }, [])

  const BOOK_LENGTH_SPECS: Record<BookLengthTier, BookLengthSpecs> = {
    [BookLengthTier.NOVELLA]: {
      word_count_min: 17500,
      word_count_max: 40000,
      word_count_target: 28750,
      chapter_count_min: 8,
      chapter_count_max: 15,
      chapter_count_target: 12,
      avg_words_per_chapter: 2400
    },
    [BookLengthTier.SHORT_NOVEL]: {
      word_count_min: 40000,
      word_count_max: 60000,
      word_count_target: 50000,
      chapter_count_min: 15,
      chapter_count_max: 20,
      chapter_count_target: 18,
      avg_words_per_chapter: 2800
    },
    [BookLengthTier.STANDARD_NOVEL]: {
      word_count_min: 60000,
      word_count_max: 90000,
      word_count_target: 75000,
      chapter_count_min: 20,
      chapter_count_max: 30,
      chapter_count_target: 25,
      avg_words_per_chapter: 3000
    },
    [BookLengthTier.LONG_NOVEL]: {
      word_count_min: 90000,
      word_count_max: 120000,
      word_count_target: 105000,
      chapter_count_min: 25,
      chapter_count_max: 35,
      chapter_count_target: 30,
      avg_words_per_chapter: 3500
    },
    [BookLengthTier.EPIC_NOVEL]: {
      word_count_min: 120000,
      word_count_max: 200000,
      word_count_target: 160000,
      chapter_count_min: 30,
      chapter_count_max: 50,
      chapter_count_target: 40,
      avg_words_per_chapter: 4000
    }
  }

  const deriveLengthSettings = () => {
    const specs = BOOK_LENGTH_SPECS[bookLengthTier]
    const pacingFactor = pacingPreference === 'fast' ? 0.85 : pacingPreference === 'expansive' ? 1.2 : 1.0
    const avgWords = Math.round(specs.avg_words_per_chapter * pacingFactor)
    const targetWordCount = specs.word_count_target
    const rawChapterTarget = Math.round(targetWordCount / Math.max(1, avgWords))
    const targetChapters = Math.min(
      specs.chapter_count_max,
      Math.max(specs.chapter_count_min, rawChapterTarget)
    )
    const wordCountPerChapter = Math.round(targetWordCount / Math.max(1, targetChapters))
    return {
      targetWordCount,
      targetChapters,
      wordCountPerChapter,
      specs
    }
  }

  const startReferenceProgressPolling = async (projectId: string) => {
    const authHeaders = await getAuthHeaders()
    let sawRunning = false
    const startedAt = Date.now()

    const poll = async () => {
      try {
        const res = await fetchApi(`/api/v2/projects/${projectId}/references/progress`, {
          headers: authHeaders
        })
        if (!res.ok) return
        const data = await res.json()
        const progressNum = typeof data.progress === 'number' ? data.progress
          : data.progress?.percentage ?? 0
        const filesCompleted = data.files_completed || 0
        const filesTotal = data.files_total || 0

        if (data.status === 'running') {
          sawRunning = true
        }

        const stageLabel = filesTotal > 0
          ? `${data.stage || 'Generating'} — ${filesCompleted} of ${filesTotal} files`
          : sawRunning
            ? data.stage || 'Generating references...'
            : 'Initializing generation...'
        GlobalLoader.update({ progress: progressNum, stage: stageLabel })

        // Only treat completed as genuine if we saw running first or
        // the response has files_total (real job record, not fallback)
        const isGenuineCompletion = data.status === 'completed' && (sawRunning || filesTotal > 0)

        if (isGenuineCompletion) {
          if (progressIntervalRef.current) {
            clearInterval(progressIntervalRef.current)
            progressIntervalRef.current = null
          }
          GlobalLoader.hide()
          router.push(`/project/${projectId}/references`)
          return
        }

        if (data.status === 'failed' || data.status === 'failed-rate-limit') {
          if (progressIntervalRef.current) {
            clearInterval(progressIntervalRef.current)
            progressIntervalRef.current = null
          }
          GlobalLoader.hide()
          setError(data.message || 'Reference generation failed')
          return
        }

        // Safety timeout after 45 minutes
        if (Date.now() - startedAt > 2700000) {
          if (progressIntervalRef.current) {
            clearInterval(progressIntervalRef.current)
            progressIntervalRef.current = null
          }
          GlobalLoader.hide()
          router.push(`/project/${projectId}/references`)
        }
      } catch {}
    }
    await poll()
    progressIntervalRef.current = setInterval(poll, 3000)
  }

  const resetClarification = () => {
    setQuestions([])
    setFollowupQuestions([])
    setAnswers({})
    setRefinedSummary('')
    setRefinedContent('')
    setClarifyRound(1)
    setUseRefinedContent(true)
  }

  const handleGenerateQuestions = async (roundOverride?: number) => {
    setError(null)
    if (!baseClarifyContent.trim() || baseClarifyContent.trim().length < 50) {
      setError('Please paste at least 50 characters before clarifying.')
      return
    }
    setIsClarifying(true)
    try {
      const authHeaders = await getAuthHeaders()
      const roundIndex = roundOverride ?? clarifyRound
      const res = await fetch('/api/prewriting/clarify', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders
        },
        body: JSON.stringify({
          idea: baseClarifyContent,
          mode: clarifyMode,
          previous_answers: answers,
          round_index: roundIndex
        })
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      const incomingQuestions = data.questions || []
      if (roundIndex === 1) {
        setQuestions(incomingQuestions)
      } else {
        setFollowupQuestions(incomingQuestions)
      }
      setClarifyRound(roundIndex)
    } catch (e) {
      console.error('Clarification question generation failed', e)
      setError(e instanceof Error ? e.message : 'Failed to generate questions')
    } finally {
      setIsClarifying(false)
    }
  }

  const handleRefineIdea = async () => {
    setError(null)
    if (!baseClarifyContent.trim() || baseClarifyContent.trim().length < 50) {
      setError('Please paste at least 50 characters before refining.')
      return
    }
    setIsRefining(true)
    try {
      const authHeaders = await getAuthHeaders()
      const res = await fetch('/api/prewriting/refine', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders
        },
        body: JSON.stringify({
          idea: baseClarifyContent,
          mode: clarifyMode,
          answers
        })
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setRefinedSummary(data.summary || '')
      setRefinedContent(data.refined_content || '')
      setFollowupQuestions(data.followup_questions || [])
      setUseRefinedContent(true)
    } catch (e) {
      console.error('Refine idea failed', e)
      setError(e instanceof Error ? e.message : 'Failed to refine idea')
    } finally {
      setIsRefining(false)
    }
  }

  const handleSubmit = async () => {
    setError(null)
    if (!isSignedIn) { setError('Please sign in'); return }
    if (!submissionContent.trim() || submissionContent.trim().length < 50) { setError('Please paste at least 50 characters.'); return }
    if (isOverLimit) { setError(`Content is too long. Please reduce it by ${Math.abs(remainingChars).toLocaleString()} characters.`); return }
    const finalTitle = (title.trim() || deriveTitleFromContent(submissionContent)).trim()
    if (!finalTitle) { setError('Unable to derive a title from your idea. Please enter a title.'); return }
    if (finalTitle.length > 100) { setError('Title is too long. Please shorten it.'); return }
    setIsSubmitting(true)
    GlobalLoader.show({
      title: 'Creating Your Project',
      stage: 'Setting up your project...',
      showProgress: false,
      safeToLeave: false,
      canMinimize: false,
      customMessages: [
        'Analyzing your concept...',
        'Building book foundation...',
        'Preparing workspace...',
      ],
      timeoutMs: 900000,
    })
    try {
      const authHeaders = await getAuthHeaders()
      const lengthSettings = deriveLengthSettings()
      const openDialoguePreferences = {
        book_length_tier: bookLengthTier,
        pacing_preference: pacingPreference || undefined,
        target_audience: targetAudience.trim() || undefined,
        writing_style: writingStyle.trim() || undefined,
        involvement_level: involvementLevel || undefined,
        purpose: purpose || undefined
      }

      const payload: BookBibleData = {
        title: finalTitle,
        genre,
        target_chapters: lengthSettings.targetChapters,
        word_count_per_chapter: lengthSettings.wordCountPerChapter,
        content: submissionContent,
        must_include_sections: [],
        creation_mode: 'paste',
        book_length_tier: bookLengthTier,
        estimated_chapters: lengthSettings.targetChapters,
        target_word_count: lengthSettings.targetWordCount,
        source_data: {
          open_dialogue: openDialoguePreferences
        }
      } as BookBibleData

      const res = await createBookBibleProject(payload, authHeaders)
      if (!res.ok) throw new Error(await res.text())
      const result = await res.json()
      const projectId = result?.project?.id
      if (!projectId) throw new Error('No project id returned')

      localStorage.setItem('lastProjectId', projectId)
      localStorage.setItem(`projectTitle-${projectId}`, finalTitle)
      setShowCelebration(true)
      setTimeout(() => setShowCelebration(false), 3000)

      GlobalLoader.update({
        title: 'Generating References',
        stage: 'Starting generation...',
        showProgress: true,
        progress: 0,
        safeToLeave: true,
        canMinimize: true,
      })
      const genRes = await fetchApi(`/api/v2/projects/${projectId}/references/generate`, {
        method: 'POST',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      })
      if (!genRes.ok) {
        const err = await genRes.json().catch(() => ({}))
        throw new Error(err.error || err.detail || 'Failed to start reference generation')
      }

      startReferenceProgressPolling(projectId)
    } catch (e) {
      console.error('Paste idea creation failed', e)
      setError(e instanceof Error ? e.message : 'Unknown error')
      setIsSubmitting(false)
      GlobalLoader.hide()
    }
  }

  return (
    <div className="min-h-screen bg-brand-off-white">
      {/* Hero */}
      <div className="relative min-h-[28vh] bg-gradient-to-br from-gray-900 via-indigo-950 to-gray-900 overflow-hidden">
        <div className="absolute top-0 right-0 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl" />
        <div className="absolute bottom-0 left-0 w-80 h-80 bg-violet-500/10 rounded-full blur-3xl" />
        <div className="relative z-10 flex items-center justify-center min-h-[28vh] px-4 sm:px-6 md:px-8 lg:px-12">
          <div className="text-center max-w-3xl">
            <h1 className="text-3xl sm:text-4xl font-bold text-white mb-3 tracking-tight">Open Dialogue</h1>
            <p className="text-white/60 text-base sm:text-lg">Tell us what you want in any format and we&apos;ll create your project and auto-generate references.</p>
            <div className="mt-4 mx-auto max-w-xl rounded-xl bg-white/10 backdrop-blur-sm border border-white/10 px-4 py-3 text-sm text-white/70">
              <div className="font-semibold text-white/90 mb-1">Easy ways to use it</div>
              <div className="space-y-1">
                <div>• Paste notes, bullets, or a messy brain dump</div>
                <div>• Drop in an outline or chapter beats</div>
                <div>• Write a few paragraphs like you&apos;re texting a friend</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="w-full px-4 sm:px-6 md:px-8 lg:px-12 py-10">
        <Card className="bg-white border border-gray-200 shadow-sm max-w-4xl md:max-w-5xl mx-auto rounded-xl">
          <CardContent className="p-4 sm:p-6 md:p-8 space-y-6">
            <div className="grid md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Title (optional)</Label>
                <Input value={title} onChange={e => setTitle(e.target.value)} placeholder="Auto-derived if left blank" />
              </div>
              <div className="space-y-2">
                <Label>Genre</Label>
                <select className="w-full p-3 min-h-[44px] border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-base" value={genre} onChange={e => setGenre(e.target.value)}>
                  <option>Fiction</option>
                  <option>Mystery</option>
                  <option>Romance</option>
                  <option>Science Fiction</option>
                  <option>Fantasy</option>
                  <option>Thriller</option>
                  <option>Horror</option>
                  <option>Literary</option>
                  <option>Young Adult</option>
                  <option>Non-Fiction</option>
                </select>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Book Length *</Label>
              <select
                className="w-full p-3 min-h-[44px] border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-base"
                value={bookLengthTier}
                onChange={(e) => setBookLengthTier(e.target.value as BookLengthTier)}
              >
                <option value={BookLengthTier.NOVELLA}>Short Novella (17.5k–40k)</option>
                <option value={BookLengthTier.SHORT_NOVEL}>Short Novel (40k–60k)</option>
                <option value={BookLengthTier.STANDARD_NOVEL}>Full-Length Novel (60k–90k)</option>
                <option value={BookLengthTier.LONG_NOVEL}>Long Novel (90k–120k)</option>
                <option value={BookLengthTier.EPIC_NOVEL}>Epic / Longform (120k+)</option>
              </select>
              <div className="text-xs text-gray-500">
                Target: {deriveLengthSettings().targetWordCount.toLocaleString()} words • About {deriveLengthSettings().targetChapters} chapters
              </div>
            </div>

            <div className="space-y-3 rounded-xl border border-gray-200 bg-white/70 p-4">
              <div>
                <div className="text-sm font-semibold text-gray-900">Quick preferences (optional)</div>
                <div className="text-xs text-gray-500">These help auto-configure pacing and writing system defaults.</div>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-1">
                  <Label className="text-sm">Target Audience</Label>
                  <Input
                    value={targetAudience}
                    onChange={(e) => setTargetAudience(e.target.value)}
                    placeholder="e.g., Adult, YA, Literary"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-sm">Writing Style</Label>
                  <Input
                    value={writingStyle}
                    onChange={(e) => setWritingStyle(e.target.value)}
                    placeholder="e.g., Cinematic, Lyrical, Direct"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-sm">Pacing Preference</Label>
                  <select
                    className="w-full p-3 min-h-[44px] border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-base"
                    value={pacingPreference}
                    onChange={(e) => setPacingPreference(e.target.value as typeof pacingPreference)}
                  >
                    <option value="">No preference</option>
                    <option value="fast">Fast</option>
                    <option value="balanced">Balanced</option>
                    <option value="expansive">Expansive</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <Label className="text-sm">Involvement Level</Label>
                  <select
                    className="w-full p-3 min-h-[44px] border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-base"
                    value={involvementLevel}
                    onChange={(e) => setInvolvementLevel(e.target.value as typeof involvementLevel)}
                  >
                    <option value="">No preference</option>
                    <option value="hands_off">Hands Off</option>
                    <option value="balanced">Balanced</option>
                    <option value="hands_on">Hands On</option>
                  </select>
                </div>
                <div className="space-y-1 md:col-span-2">
                  <Label className="text-sm">Project Purpose</Label>
                  <select
                    className="w-full p-3 min-h-[44px] border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-base"
                    value={purpose}
                    onChange={(e) => setPurpose(e.target.value as typeof purpose)}
                  >
                    <option value="">No preference</option>
                    <option value="personal">Personal</option>
                    <option value="commercial">Commercial</option>
                    <option value="educational">Educational</option>
                  </select>
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                <Label>Your Idea *</Label>
                <div className={`text-sm ${getCharCountColor()}`}>
                  Active content: {currentCharCount.toLocaleString()} / {MAX_CHARACTERS.toLocaleString()} characters
                  {isNearLimit && !isOverLimit && (
                    <span className="ml-2 text-orange-600">({remainingChars.toLocaleString()} remaining)</span>
                  )}
                  {isOverLimit && (
                    <span className="ml-2 text-red-600 font-medium">Limit exceeded!</span>
                  )}
                </div>
              </div>
              <Textarea 
                className={`font-mono ${isOverLimit ? 'border-red-300 focus:border-red-500 focus:ring-red-500' : ''}`}
                rows={12} 
                value={content} 
                onChange={e => setContent(e.target.value)} 
                placeholder="Paste any outline, premise, character notes, or freeform idea (up to 100,000 characters)..." 
              />
              {isNearLimit && (
                <div className={`text-sm ${isOverLimit ? 'text-red-600' : 'text-orange-600'} bg-orange-50 border border-orange-200 rounded-md p-3`}>
                  {isOverLimit ? (
                    <>
                      <strong>⚠️ Content too long!</strong> Please reduce your content by {Math.abs(remainingChars).toLocaleString()} characters to continue.
                    </>
                  ) : (
                    <>
                      <strong>⚠️ Approaching limit!</strong> You have {remainingChars.toLocaleString()} characters remaining.
                    </>
                  )}
                </div>
              )}
              <p className="text-xs text-gray-500">We'll structure this into a proper book bible and kick off reference generation.</p>
            </div>

            <div className="space-y-2">
              <Label>Script / Non-negotiables (optional)</Label>
              <Textarea
                rows={4}
                value={scriptNotes}
                onChange={(e) => setScriptNotes(e.target.value)}
                placeholder="Paste any must-follow beats, outline checkpoints, or script constraints you want the story to obey."
              />
              <p className="text-xs text-gray-500">These are treated as hard constraints during generation.</p>
            </div>

            <div className="border-t pt-6 space-y-4">
              <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                <div>
                  <h3 className="text-base font-semibold text-gray-900">Refine Your Idea</h3>
                  <p className="text-sm text-gray-600">We&apos;ll ask a few targeted questions to sharpen your concept before building references.</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button variant="outline" onClick={resetClarification} disabled={isClarifying || isRefining}>
                    Reset
                  </Button>
                  <Button onClick={() => handleGenerateQuestions()} disabled={isClarifying || !content.trim()}>
                    {isClarifying ? 'Generating…' : 'Generate Questions'}
                  </Button>
                </div>
              </div>

              <div className="flex flex-wrap gap-2 items-center">
                <Label className="text-sm">Mode</Label>
                <Button
                  type="button"
                  variant={clarifyMode === 'brief' ? 'default' : 'outline'}
                  onClick={() => setClarifyMode('brief')}
                  size="sm"
                >
                  Brief (4–5)
                </Button>
                <Button
                  type="button"
                  variant={clarifyMode === 'extended' ? 'default' : 'outline'}
                  onClick={() => setClarifyMode('extended')}
                  size="sm"
                >
                  Extended (7–8)
                </Button>
                <span className="text-xs text-gray-500">Round {clarifyRound}</span>
              </div>

              {questions.length > 0 && (
                <div className="space-y-4">
                  <div className="text-sm font-medium text-gray-700">Answer these to tighten the brief</div>
                  {questions.map((q, index) => (
                    <div key={q.id || index} className="space-y-2">
                      <Label className="text-sm">{index + 1}. {q.question}</Label>
                      {q.why && <div className="text-xs text-gray-500">{q.why}</div>}
                      <Textarea
                        rows={2}
                        value={answers[q.id] || ''}
                        onChange={(e) => setAnswers(prev => ({ ...prev, [q.id]: e.target.value }))}
                        placeholder="Your answer..."
                      />
                    </div>
                  ))}
                  <div className="flex flex-wrap gap-2">
                    <Button onClick={handleRefineIdea} disabled={isRefining}>
                      {isRefining ? 'Refining…' : 'Refine Story Brief'}
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => handleGenerateQuestions(clarifyRound + 1)}
                      disabled={isClarifying || clarifyRound >= 2}
                    >
                      {clarifyRound >= 2 ? 'Follow-up Limit Reached' : 'Ask One Follow-up Round'}
                    </Button>
                  </div>
                </div>
              )}

              {followupQuestions.length > 0 && (
                <div className="space-y-4">
                  <div className="text-sm font-medium text-gray-700">Follow-up questions</div>
                  {followupQuestions.map((q, index) => (
                    <div key={q.id || index} className="space-y-2">
                      <Label className="text-sm">{index + 1}. {q.question}</Label>
                      {q.why && <div className="text-xs text-gray-500">{q.why}</div>}
                      <Textarea
                        rows={2}
                        value={answers[q.id] || ''}
                        onChange={(e) => setAnswers(prev => ({ ...prev, [q.id]: e.target.value }))}
                        placeholder="Your answer..."
                      />
                    </div>
                  ))}
                  <Button onClick={handleRefineIdea} disabled={isRefining}>
                    {isRefining ? 'Refining…' : 'Apply Follow-ups'}
                  </Button>
                </div>
              )}

              {refinedContent && (
                <div className="space-y-3 border rounded-lg p-4 bg-gray-50">
                  <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2">
                    <div>
                      <div className="text-sm font-semibold text-gray-800">Refined Story Brief</div>
                      {refinedSummary && <div className="text-xs text-gray-600">{refinedSummary}</div>}
                    </div>
                    <label className="flex items-center gap-2 text-sm text-gray-700">
                      <input
                        type="checkbox"
                        checked={useRefinedContent}
                        onChange={(e) => setUseRefinedContent(e.target.checked)}
                      />
                      Use refined version for project creation
                    </label>
                  </div>
                  <Textarea
                    rows={8}
                    value={refinedContent}
                    onChange={(e) => setRefinedContent(e.target.value)}
                    className="font-mono text-sm"
                  />
                </div>
              )}
            </div>

            {error && (
              <div className="text-sm text-red-600">{error}</div>
            )}

            <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-3 pt-2">
              <Button variant="outline" onClick={() => router.back()} className="w-full sm:w-auto">Cancel</Button>
              <Button 
                onClick={handleSubmit} 
                disabled={isSubmitting || !activeContent.trim() || isOverLimit}
                className={`w-full sm:w-auto ${isOverLimit ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                {isSubmitting ? 'Creating…' : 'Create and Generate References'}
              </Button>
            </div>
          </CardContent>
        </Card>
        <Celebration isVisible={showCelebration} message="Project created — generating references..." />
      </div>
    </div>
  )
}


