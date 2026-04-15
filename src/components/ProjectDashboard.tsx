'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { useAuthToken } from '@/lib/auth'
import { fetchApi } from '@/lib/api-client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toast } from '@/hooks/useAppToast'
import { CoverArtGenerator } from '@/components/CoverArtGenerator'
import { useRouter } from 'next/navigation'
import { GlobalLoader } from '@/stores/useGlobalLoaderStore'

interface Project {
  id: string
  title: string
  genre: string
  status: 'active' | 'completed' | 'archived' | 'paused'
  created_at: string
  settings: {
    target_chapters: number
    word_count_per_chapter: number
    involvement_level: string
    purpose: string
  }
}

interface Chapter {
  id: string
  chapter_number: number
  title: string
  word_count: number
  target_word_count: number
  stage: 'draft' | 'revision' | 'complete'
  created_at: string
  updated_at: string
  director_notes_count: number
  quality_scores?: {
    overall_rating: number
    prose: number
    character: number
    story: number
    emotion: number
    freshness: number
  }
}

interface PrewritingSummary {
  project_id: string
  title: string
  genre: string
  premise: string
  main_characters: Array<{
    name: string
    description: string
  }>
  setting: {
    description: string
    time?: string
    place?: string
  }
  themes: string[]
  chapter_outline: Array<{
    chapter: number
    description: string
    act: string
  }>
  total_chapters: number
  word_count_target: number
}

interface ProjectDashboardProps {
  projectId: string
  onEditChapter?: (chapterId: string, chapterNumber: number) => void
  onCreateChapter?: (chapterNumber: number) => void
  onTitleUpdated?: (title: string) => void
}

interface ReferenceFile {
  filename: string
  content: string
  summary: string
  last_modified: string
  modified_by: string
}

interface TitleRecommendation {
  title: string
  rationale: string
}

const ProjectDashboard: React.FC<ProjectDashboardProps> = ({
  projectId,
  onEditChapter,
  onCreateChapter,
  onTitleUpdated
}) => {
  const router = useRouter()
  const { getAuthHeaders, isLoaded, isSignedIn, user } = useAuthToken()
  const [project, setProject] = useState<Project | null>(null)
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [summary, setSummary] = useState<PrewritingSummary | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [titleInput, setTitleInput] = useState('')
  const [isSavingTitle, setIsSavingTitle] = useState(false)
  const [titleRecommendations, setTitleRecommendations] = useState<TitleRecommendation[]>([])
  const [isLoadingRecommendations, setIsLoadingRecommendations] = useState(false)
  const [isClearingChapters, setIsClearingChapters] = useState(false)

  useEffect(() => {
    if (projectId) {
      loadProjectData()
    }
  }, [projectId])

  useEffect(() => {
    if (project?.title && !isSavingTitle) {
      setTitleInput(project.title)
    }
  }, [project?.title, isSavingTitle])

  const loadProjectData = async () => {
    if (!projectId) return

    try {
      setIsLoading(true)

      const authHeaders = await getAuthHeaders()

      const [projectRes, chaptersRes] = await Promise.all([
        fetch(`/api/v2/projects/${projectId}`, {
          headers: { ...authHeaders, 'Content-Type': 'application/json' }
        }),
        fetch(`/api/v2/projects/${projectId}/chapters`, {
          headers: { ...authHeaders, 'Content-Type': 'application/json' }
        })
      ])

      // Handle project data
      if (projectRes.ok) {
        const data = await projectRes.json()
        // API may return { project: {...} } or the object itself
        const p = data.project || data
        if (p) {
          const resolvedTitle = p.metadata?.title || p.title || `Project ${projectId}`
          setProject({
            id: p.id,
            title: resolvedTitle,
            genre: p.settings?.genre || p.genre || 'Fiction',
            status: p.metadata?.status || p.status || 'active',
            created_at: p.metadata?.created_at || p.created_at || new Date().toISOString(),
            settings: {
              target_chapters: p.settings?.target_chapters || 25,
              word_count_per_chapter: p.settings?.word_count_per_chapter || 3800,
              involvement_level: '',
              purpose: ''
            }
          })
          onTitleUpdated?.(resolvedTitle)
        } else {
          setProject(null)
        }
      } else {
        console.error('[ProjectDashboard] Failed to load project:', projectRes.status, await projectRes.text())
      }

      // Handle chapters data (empty is OK for new projects)
      if (chaptersRes.ok) {
        const chaptersData = await chaptersRes.json()
        const chapters = chaptersData.chapters || []
        
        // Ensure numeric values and consistent fields for chapter status
        const sanitizedChapters = chapters.map((chapter: any) => {
          // More robust word count extraction - try multiple possible locations
          const wordCount = Number(chapter.metadata?.word_count || chapter.word_count || 0)
          const targetWordCount = Number(chapter.metadata?.target_word_count || chapter.target_word_count || 2000)
          const directorNotesCount = Number(chapter.director_notes_count) || 0
          const stage = chapter.metadata?.stage || chapter.stage || 'draft'
          const chapterNumber = Number(chapter.chapter_number) || Number(chapter.metadata?.chapter_number) || 0
          
          return {
            ...chapter,
            chapter_number: chapterNumber,
            word_count: wordCount,
            target_word_count: targetWordCount,
            director_notes_count: directorNotesCount,
            stage
          }
        })
        
        setChapters(sanitizedChapters)
      } else {
        console.error('[ProjectDashboard] Failed to load chapters:', chaptersRes.status, await chaptersRes.text())
        setChapters([]) // Empty is valid for new projects
      }

    } catch (error) {
      console.error('Error loading project data:', error)
      toast({
        title: "Warning",
        description: "Some project data could not be loaded. The project is still accessible.",
        variant: "default"
      })
    } finally {
      setIsLoading(false)
    }

    // Load summary in the background to avoid blocking the UI
    try {
      const authHeaders = await getAuthHeaders()
      const summaryRes = await fetch(`/api/prewriting/summary?project_id=${projectId}`, {
        headers: authHeaders
      })

      if (summaryRes.ok) {
        const summaryData = await summaryRes.json()
        setSummary(summaryData.summary)
      } else if (summaryRes.status === 404) {
        setSummary(null)
      } else {
        console.error('[ProjectDashboard] Failed to load summary:', summaryRes.status, await summaryRes.text())
        setSummary(null)
      }
    } catch (error) {
      console.error('[ProjectDashboard] Failed to load summary:', error)
      setSummary(null)
    }
  }

  const getProgressStats = () => {
    // If no summary and no chapters, provide sensible defaults for new projects
    if (!summary && chapters.length === 0) {
      return { completed: 0, total: 25, percentage: 0, totalWords: 0, chaptersWritten: 0 }
    }
    
    if (!summary) {
      const completed = chapters.filter(c => c.stage === 'complete').length
      const chaptersWritten = chapters.length
      const total = Math.max(chaptersWritten, 25) // Assume 25 chapters if no summary
      const percentage = total > 0 ? Math.min(100, Math.max(0, (chaptersWritten / total) * 100)) : 0
      const totalWords = chapters.reduce((sum, c) => {
        const wordCount = Number(c.word_count) || 0
        return sum + wordCount
      }, 0)
      
      return { 
        completed: Number(completed) || 0, 
        total: Number(total) || 25, 
        percentage: Number(percentage) || 0, 
        totalWords: Number(totalWords) || 0,
        chaptersWritten: Number(chaptersWritten) || 0
      }
    }
    
    const completed = chapters.filter(c => c.stage === 'complete').length
    const chaptersWritten = chapters.length
    const total = summary.total_chapters || 25
    const percentage = total > 0 ? Math.min(100, Math.max(0, (chaptersWritten / total) * 100)) : 0
    const totalWords = chapters.reduce((sum, c) => {
      const wordCount = Number(c.word_count) || 0
      return sum + wordCount
    }, 0)
    
    // Ensure all values are valid numbers
    const result = { 
      completed: Number(completed) || 0, 
      total: Number(total) || 25, 
      percentage: Number(percentage) || 0, 
      totalWords: Number(totalWords) || 0,
      chaptersWritten: Number(chaptersWritten) || 0
    }
    
    return result
  }

  const getChapterStatus = (chapterNumber: number) => {
    const chapter = chapters.find(c => c.chapter_number === chapterNumber)
    if (!chapter) return 'not_started'
    return chapter.stage
  }

  const getChapterQualityColor = (scores?: Chapter['quality_scores']) => {
    if (!scores) return 'bg-gray-200'
    const overall = scores.overall_rating
    if (overall >= 8) return 'bg-green-500'
    if (overall >= 6) return 'bg-yellow-500'
    return 'bg-red-500'
  }

  const handleChapterClick = (chapterNumber: number) => {
    const chapter = chapters.find(c => c.chapter_number === chapterNumber)
    if (chapter && onEditChapter) {
      onEditChapter(chapter.id, chapterNumber)
    } else if (!chapter && onCreateChapter) {
      onCreateChapter(chapterNumber)
    }
  }

  const saveTitle = async (rawTitle: string) => {
    const nextTitle = rawTitle.trim()
    if (!nextTitle) {
      toast({
        title: 'Title required',
        description: 'Please enter a book title before saving.',
        variant: 'destructive'
      })
      return
    }
    if (nextTitle === project?.title?.trim()) {
      toast({
        title: 'No changes',
        description: 'The title is already up to date.'
      })
      return
    }

    try {
      setIsSavingTitle(true)
      const authHeaders = await getAuthHeaders()
      const resp = await fetchApi(`/api/v2/projects/${encodeURIComponent(projectId)}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders
        },
        body: JSON.stringify({ title: nextTitle })
      })

      if (resp.ok) {
        setProject((prev) => (prev ? { ...prev, title: nextTitle } : prev))
        setTitleInput(nextTitle)
        localStorage.setItem(`projectTitle-${projectId}`, nextTitle)
        onTitleUpdated?.(nextTitle)
        toast({
          title: 'Title updated',
          description: 'Your book title has been saved.'
        })
      } else {
        toast({
          title: 'Update failed',
          description: await resp.text(),
          variant: 'destructive'
        })
      }
    } catch (error) {
      console.error('Failed to update title:', error)
      toast({
        title: 'Update failed',
        description: 'Please try again in a moment.',
        variant: 'destructive'
      })
    } finally {
      setIsSavingTitle(false)
    }
  }

  const handleTitleSave = async () => {
    await saveTitle(titleInput)
  }

  const handleGenerateTitleRecommendations = async () => {
    try {
      setIsLoadingRecommendations(true)
      const authHeaders = await getAuthHeaders()
      const resp = await fetchApi(`/api/v2/projects/${encodeURIComponent(projectId)}/title-recommendations`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders
        },
        body: JSON.stringify({ count: 6 })
      })

      if (resp.ok) {
        const data = await resp.json()
        setTitleRecommendations(data.recommendations || [])
        if (!data.recommendations || data.recommendations.length === 0) {
          toast({
            title: 'No recommendations found',
            description: 'Try refining your book bible or reference files.'
          })
        }
      } else {
        toast({
          title: 'Recommendation failed',
          description: await resp.text(),
          variant: 'destructive'
        })
      }
    } catch (error) {
      console.error('Title recommendation error:', error)
      toast({
        title: 'Recommendation failed',
        description: 'Please try again in a moment.',
        variant: 'destructive'
      })
    } finally {
      setIsLoadingRecommendations(false)
    }
  }

  const handleUseRecommendation = async (recommendedTitle: string) => {
    setTitleInput(recommendedTitle)
    await saveTitle(recommendedTitle)
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-center">
          <div className="w-10 h-10 border-2 border-gray-200 border-t-indigo-500 rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-gray-500 text-sm">Loading project...</p>
        </div>
      </div>
    )
  }

  if (!project) {
    return (
      <div className="flex items-center justify-center min-h-[50vh] px-6">
        <div className="text-center max-w-md">
          <h2 className="text-xl font-semibold text-gray-900 mb-3">Project Not Found</h2>
          <p className="text-gray-600 mb-6">
            We couldn&apos;t load the project data. This might be due to permissions or connection issues.
          </p>
          <div className="flex items-center justify-center gap-3">
            <Button variant="outline" onClick={() => window.location.reload()}>
              Try Again
            </Button>
            <Button onClick={() => router.push('/dashboard')}>Back to Dashboard</Button>
          </div>
        </div>
      </div>
    )
  }

  const progressStats = getProgressStats()
  const titleUnchanged = (project?.title || '').trim() === titleInput.trim()

  return (
    <div className="w-full">
      {/* Project Summary Header */}
      <div className="relative bg-white px-4 sm:px-6 md:px-8 lg:px-12 py-6 sm:py-8 border-b border-gray-200">
        <div className="max-w-6xl mx-auto">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-2xl font-bold text-gray-900 tracking-tight mb-2">Project Overview</h2>
            </div>
            
            {/* Compact Progress Ring */}
            <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-6">
              <div className="flex flex-col sm:flex-row gap-2">
                <Button
                  variant="outline"
                  className="border-amber-200 text-amber-700 hover:bg-amber-50 w-full sm:w-auto"
                  disabled={isClearingChapters || chapters.length === 0}
                  onClick={async () => {
                    if (!window.confirm(
                      `Are you sure you want to clear all ${chapters.length} chapters? Your book bible and reference files will be preserved. This cannot be undone.`
                    )) return
                    try {
                      setIsClearingChapters(true)
                      const authHeaders = await getAuthHeaders()
                      const resp = await fetchApi(`/api/v2/projects/${encodeURIComponent(projectId)}/chapters`, {
                        method: 'DELETE',
                        headers: authHeaders
                      })
                      if (resp.ok) {
                        const data = await resp.json()
                        toast({ title: 'Chapters cleared', description: data.message || 'All chapters have been removed. You can start fresh.' })
                        setChapters([])
                        await loadProjectData()
                      } else {
                        toast({ title: 'Clear failed', description: await resp.text(), variant: 'destructive' })
                      }
                    } catch (err) {
                      console.error('Clear chapters error:', err)
                      toast({ title: 'Clear failed', description: 'Please try again later.', variant: 'destructive' })
                    } finally {
                      setIsClearingChapters(false)
                    }
                  }}
                >
                  {isClearingChapters ? 'Clearing...' : 'Clear All Chapters'}
                </Button>
                <Button
                  variant="outline"
                  className="border-red-200 text-red-700 hover:bg-red-50 w-full sm:w-auto"
                  onClick={async () => {
                    if (!window.confirm('Are you sure you want to delete this project? This action cannot be undone.')) return
                    try {
                      const authHeaders = await getAuthHeaders()
                      GlobalLoader.show({
                        title: 'Deleting Project',
                        stage: 'Removing data...',
                        showProgress: false,
                        safeToLeave: false,
                        canMinimize: false,
                        timeoutMs: 600000,
                      })
                      const resp = await fetchApi(`/api/v2/projects/${encodeURIComponent(projectId)}`, {
                        method: 'DELETE',
                        headers: authHeaders
                      })
                      GlobalLoader.hide()
                      if (resp.ok) {
                        toast({ title: 'Project deleted', description: 'The project was removed successfully.' })
                        router.push('/dashboard')
                      } else {
                        toast({ title: 'Delete failed', description: await resp.text(), variant: 'destructive' })
                      }
                    } catch (err) {
                      console.error('Delete project error:', err)
                      toast({ title: 'Delete failed', description: 'Please try again later.', variant: 'destructive' })
                      GlobalLoader.hide()
                    }
                  }}
                >
                  Delete Project
                </Button>
              </div>
              <div className="relative">
                <svg className="w-12 h-12 sm:w-16 sm:h-16 transform -rotate-90" viewBox="0 0 100 100">
                  <circle
                    cx="50" cy="50" r="40"
                    stroke="rgba(177, 142, 255, 0.3)"
                    strokeWidth="6"
                    fill="transparent"
                  />
                  <circle
                    cx="50" cy="50" r="40"
                    stroke="#B18EFF"
                    strokeWidth="6"
                    fill="transparent"
                    strokeLinecap="round"
                    strokeDasharray={`${2 * Math.PI * 40}`}
                    strokeDashoffset={`${2 * Math.PI * 40 * (1 - progressStats.percentage / 100)}`}
                    className="transition-all duration-700 ease-out"
                  />
                </svg>
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="text-xs sm:text-sm font-bold text-gray-900">
                    {Math.round(progressStats.percentage)}%
                  </span>
                </div>
              </div>
              
              
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="w-full px-4 sm:px-6 md:px-8 lg:px-12 py-6 sm:py-8">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
          {/* Main Content Area */}
          <div className="md:col-span-3">
            
            {/* Project Overview Content */}
              <div className="space-y-8">
                <div className="bg-white rounded-xl p-6 sm:p-7 border border-gray-200 shadow-sm">
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
                    <div className="w-full">
                      <Label htmlFor="project-title" className="text-sm font-bold text-gray-600">
                        Book Title
                      </Label>
                      <Input
                        id="project-title"
                        name="projectTitle"
                        value={titleInput}
                        onChange={(event) => setTitleInput(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter' && !titleUnchanged && titleInput.trim()) {
                            handleTitleSave()
                          }
                        }}
                        className="mt-2 bg-white border-gray-200/30"
                      />
                    </div>
                    <Button
                      onClick={handleTitleSave}
                      disabled={isSavingTitle || titleUnchanged || !titleInput.trim()}
                      className="w-full sm:w-auto"
                    >
                      {isSavingTitle ? 'Saving...' : 'Save Title'}
                    </Button>
                  </div>
                </div>

                <div className="bg-white rounded-xl p-6 sm:p-7 border border-gray-200 shadow-sm">
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <h3 className="text-lg font-bold text-gray-900">Recommended Titles</h3>
                      <p className="text-sm text-gray-500">
                        Generate title options from your book bible, references, and vector memory.
                      </p>
                    </div>
                    <Button
                      onClick={handleGenerateTitleRecommendations}
                      disabled={isLoadingRecommendations}
                      className="w-full sm:w-auto"
                    >
                      {isLoadingRecommendations ? 'Generating...' : 'Generate Titles'}
                    </Button>
                  </div>
                  {titleRecommendations.length > 0 && (
                    <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
                      {titleRecommendations.map((recommendation, index) => (
                        <div
                          key={`${recommendation.title}-${index}`}
                          className="flex flex-col gap-3 rounded-xl border border-gray-200/20 bg-white p-4 h-full"
                        >
                          <div>
                            <div className="text-base font-bold text-gray-900">{recommendation.title}</div>
                            <div className="text-sm text-gray-500">{recommendation.rationale}</div>
                          </div>
                          <Button
                            variant="outline"
                            className="border-gray-200/30 text-gray-900"
                            onClick={() => handleUseRecommendation(recommendation.title)}
                          >
                            Use This Title
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Beautiful Stats Cards */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div className="bg-white rounded-xl p-5 sm:p-6 border border-gray-200 shadow-sm text-center hover:shadow-md transition-all hover:-translate-y-0.5">
                    <div className="text-3xl font-bold text-gray-900 mb-2">{progressStats.chaptersWritten}</div>
                    <div className="text-sm font-bold text-gray-500 uppercase tracking-wide">Chapters Written</div>
                  </div>
                  <div className="bg-white rounded-xl p-5 sm:p-6 border border-gray-200 shadow-sm text-center hover:shadow-md transition-all hover:-translate-y-0.5">
                    <div className="text-3xl font-bold text-emerald-600 mb-2">{progressStats.totalWords.toLocaleString()}</div>
                    <div className="text-sm font-bold text-gray-500 uppercase tracking-wide">Words Written</div>
                  </div>
                  <div className="bg-white rounded-xl p-5 sm:p-6 border border-gray-200 shadow-sm text-center hover:shadow-md transition-all hover:-translate-y-0.5">
                    <div className="text-3xl font-bold text-purple-600 mb-2">{Math.ceil((progressStats.totalWords || 0) / 250)}</div>
                    <div className="text-sm font-bold text-gray-500 uppercase tracking-wide">Estimated Pages</div>
                  </div>
                </div>

                {/* Enhanced Chapter Status Grid */}
                <div className="bg-white rounded-xl p-8 border border-gray-200 shadow-sm">
                  <h3 className="text-2xl font-bold text-gray-900 mb-6">Chapter Status</h3>
                  <div className="grid grid-cols-5 sm:grid-cols-6 md:grid-cols-8 gap-3">
                    {Array.from({ length: project?.settings.target_chapters || 25 }, (_, i) => {
                      const chapterNumber = i + 1
                      const status = getChapterStatus(chapterNumber)
                      return (
                        <button
                          key={chapterNumber}
                          className={`aspect-square rounded-xl border-2 flex items-center justify-center text-sm font-bold transition-all hover:scale-110 ${
                            status === 'complete' ? 'bg-emerald-100 border-emerald-300 text-emerald-800 shadow-lg' :
                            status === 'revision' ? 'bg-amber-100 border-amber-300 text-amber-800 shadow-lg' :
                            status === 'draft' ? 'bg-blue-100 border-blue-300 text-blue-800 shadow-lg' :
                            'bg-gray-50 border-gray-200 text-gray-400 hover:bg-gray-100'
                          }`}
                          onClick={() => handleChapterClick(chapterNumber)}
                        >
                          {chapterNumber}
                        </button>
                      )
                    })}
                  </div>
                </div>

                {/* Recent Activity with Enhanced Design */}
                <div className="bg-white rounded-xl p-5 sm:p-6 lg:p-8 border border-gray-200 shadow-sm">
                  <h3 className="text-2xl font-bold text-gray-900 mb-6">Recent Chapters</h3>
                  <div className="space-y-4">
                    {chapters.slice(0, 5).map((chapter) => (
                      <div key={chapter.id} className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-4 bg-white rounded-xl border border-gray-200/20 hover:bg-white transition-all hover:shadow-lg">
                        <div>
                          <div className="font-bold text-gray-900">{chapter.title}</div>
                          <div className="text-sm text-gray-500 font-semibold">
                            {chapter.word_count.toLocaleString()} words • {chapter.stage}
                          </div>
                        </div>
                        <button
                          onClick={() => onEditChapter?.(chapter.id, chapter.chapter_number)}
                          className="bg-gray-900 text-white px-4 py-2 rounded-lg font-semibold hover:bg-gray-800 transition-all w-full sm:w-auto"
                        >
                          Edit
                        </button>
                      </div>
                    ))}
                    {chapters.length === 0 && (
                      <div className="text-center text-gray-900/60 py-8">
                        <div className="text-lg font-semibold mb-2">No chapters found</div>
                        <div className="text-sm">Start by creating your first chapter</div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
          </div>

          {/* Quick Start Sidebar */}
          <div className="md:col-span-1">
            <div className="bg-white rounded-xl p-6 border border-gray-200 shadow-sm">
              <h3 className="text-xl font-bold text-gray-900 mb-3">Quick Start</h3>
              <p className="text-sm text-gray-600 mb-4">
                A few tips to get the most out of your writing workspace.
              </p>
              <div className="space-y-4 text-sm text-gray-600">
                <div>
                  <div className="font-semibold text-gray-900 mb-1">1) Review your references</div>
                  <p>
                    Open the <span className="font-semibold">References</span> tab in the top navigation. Skim each document
                    (characters, outline, timeline, and more) and make updates so everything reflects your vision. These
                    guide every chapter the system writes.
                  </p>
                </div>
                <div>
                  <div className="font-semibold text-gray-900 mb-1">2) Write chapters your way</div>
                  <p>
                    Open the <span className="font-semibold">Chapters</span> tab to generate AI drafts <span className="font-semibold">one chapter at a time</span>,
                    then review and refine with inline edits — remember to save. Prefer a fully hands‑off run?
                    Use <span className="font-semibold">Auto‑Complete</span> to have the system draft the <span className="font-semibold">entire book in one go</span>.
                  </p>
                </div>
                <div>
                  <div className="font-semibold text-gray-900 mb-1">3) Explore cover art</div>
                  <p>
                    Try generating <span className="font-semibold">Cover Art</span> at any point. Refresh until it feels like your book.
                  </p>
                </div>
                <div>
                  <div className="font-semibold text-gray-900 mb-1">4) Publish when you’re ready</div>
                  <p>
                    In the <span className="font-semibold">Publish</span> tab, fill in as much or as little as you’d like and press
                    <span className="font-semibold"> Publish</span>. Your finished book appears in your Library. On mobile, tap
                    <span className="font-semibold"> Save</span>, then “Open with” to send it to Apple Books or Kindle.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default ProjectDashboard