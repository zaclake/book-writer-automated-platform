'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { useUser, useAuth } from '@clerk/nextjs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toast } from '@/components/ui/use-toast'
import { CoverArtGenerator } from '@/components/CoverArtGenerator'

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
  onEditChapter?: (chapterId: string) => void
  onCreateChapter?: (chapterNumber: number) => void
}

interface ReferenceFile {
  filename: string
  content: string
  summary: string
  last_modified: string
  modified_by: string
}

const ProjectDashboard: React.FC<ProjectDashboardProps> = ({
  projectId,
  onEditChapter,
  onCreateChapter
}) => {
  const { user, isLoaded } = useUser()
  const { getToken } = useAuth()
  const [project, setProject] = useState<Project | null>(null)
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [summary, setSummary] = useState<PrewritingSummary | null>(null)
  const [references, setReferences] = useState<ReferenceFile[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [loadingReferences, setLoadingReferences] = useState(false)
  
  // UI state
  const [showReferencesSidebar, setShowReferencesSidebar] = useState(true)

  useEffect(() => {
    if (isLoaded && projectId) {
      loadProjectData()
    }
  }, [isLoaded, projectId])

  const loadProjectData = async () => {
    if (!user || !projectId || !getToken) return

    try {
      setIsLoading(true)
      
      console.log(`[ProjectDashboard] Loading data for project: ${projectId}`)
      console.log(`[ProjectDashboard] User ID: ${user.id}`)
      
      // Load project details, chapters, summary, and references in parallel
      const [projectRes, chaptersRes, summaryRes, referencesRes] = await Promise.all([
        fetch(`/api/v2/projects/${projectId}`, {
          headers: { 'Authorization': `Bearer ${await getToken()}` }
        }),
        fetch(`/api/v2/projects/${projectId}/chapters`, {
          headers: { 'Authorization': `Bearer ${await getToken()}` }
        }),
        fetch(`/api/prewriting/summary?project_id=${projectId}`, {
          headers: { 'Authorization': `Bearer ${await getToken()}` }
        }),
        fetch(`/api/v2/projects/${projectId}/references`, {
          headers: { 'Authorization': `Bearer ${await getToken()}` }
        })
      ])

      console.log(`[ProjectDashboard] Response status codes:`, {
        project: projectRes.status,
        chapters: chaptersRes.status,
        summary: summaryRes.status,
        references: referencesRes.status
      })

      // Handle project data
      if (projectRes.ok) {
        const data = await projectRes.json()
        // API may return { project: {...} } or the object itself
        const p = data.project || data
        console.log('[ProjectDashboard] Project data structure:', {
          hasProject: !!p,
          projectKeys: p ? Object.keys(p) : [],
          title: p?.metadata?.title || p?.title,
          settings: p?.settings
        })

        if (p) {
          setProject({
            id: p.id,
            title: p.metadata?.title || p.title || `Project ${projectId}`,
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
        
        console.log('[ProjectDashboard] Raw chapters data:', {
          responseStructure: Object.keys(chaptersData),
          chaptersArray: chapters,
          chaptersCount: chapters.length,
          firstChapterStructure: chapters[0] ? Object.keys(chapters[0]) : 'no chapters',
          firstChapterSample: chapters[0] ? {
            id: chapters[0].id,
            title: chapters[0].title,
            word_count: chapters[0].word_count,
            metadata: chapters[0].metadata
          } : 'no chapters'
        })
        
        // Ensure all word_count values are numeric to prevent NaN in calculations
        const sanitizedChapters = chapters.map((chapter: any) => {
          // More robust word count extraction - try multiple possible locations
          const wordCount = Number(chapter.metadata?.word_count || chapter.word_count || 0)
          const targetWordCount = Number(chapter.metadata?.target_word_count || chapter.target_word_count || 2000)
          const directorNotesCount = Number(chapter.director_notes_count) || 0
          
          console.log(`[ProjectDashboard] Sanitizing chapter ${chapter.id}:`, {
            originalWordCount: chapter.word_count,
            metadataWordCount: chapter.metadata?.word_count,
            sanitizedWordCount: wordCount,
            originalTargetWordCount: chapter.target_word_count,
            metadataTargetWordCount: chapter.metadata?.target_word_count,
            sanitizedTargetWordCount: targetWordCount
          })
          
          return {
            ...chapter,
            word_count: wordCount,
            target_word_count: targetWordCount,
            director_notes_count: directorNotesCount
          }
        })
        
        console.log('[ProjectDashboard] Chapters loaded:', sanitizedChapters.length, 'chapters')
        console.log('[ProjectDashboard] Sanitized chapters sample:', sanitizedChapters[0])
        setChapters(sanitizedChapters)
      } else {
        console.error('[ProjectDashboard] Failed to load chapters:', chaptersRes.status, await chaptersRes.text())
        setChapters([]) // Empty is valid for new projects
      }

      // Handle summary data (might not exist for new projects)
      if (summaryRes.ok) {
        const summaryData = await summaryRes.json()
        console.log('[ProjectDashboard] Summary data structure:', {
          hasData: !!summaryData,
          hasSummary: !!summaryData.summary,
          summaryKeys: summaryData.summary ? Object.keys(summaryData.summary) : [],
          totalChapters: summaryData.summary?.total_chapters
        })
        setSummary(summaryData.summary)
      } else if (summaryRes.status === 404) {
        console.log('[ProjectDashboard] Summary not found (normal for new projects)')
        setSummary(null)
      } else {
        console.error('[ProjectDashboard] Failed to load summary:', summaryRes.status, await summaryRes.text())
        setSummary(null)
      }

      // Handle references data  
      setLoadingReferences(false)
      if (referencesRes.ok) {
        const referencesData = await referencesRes.json()
        console.log('[ProjectDashboard] References data:', referencesData)
        
        // API now returns array directly
        const references = Array.isArray(referencesData) ? referencesData : []
        setReferences(references)
        console.log(`[ProjectDashboard] Loaded ${references.length} reference files`)
      } else {
        console.warn('[ProjectDashboard] Failed to load references:', referencesRes.status)
        setReferences([])
      }

      console.log('[ProjectDashboard] Data loading completed')

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
  }

  const getProgressStats = () => {
    console.log('[ProjectDashboard] getProgressStats called with:', {
      hasSummary: !!summary,
      summary: summary,
      chaptersCount: chapters.length,
      chaptersArray: chapters
    })
    
    // If no summary and no chapters, provide sensible defaults for new projects
    if (!summary && chapters.length === 0) {
      console.log('[ProjectDashboard] No summary and no chapters, returning default stats for new project')
      return { completed: 0, total: 25, percentage: 0, totalWords: 0, chaptersWritten: 0 }
    }
    
    if (!summary) {
      console.log('[ProjectDashboard] No summary but have chapters, calculating from chapters')
      const completed = chapters.filter(c => c.stage === 'complete').length
      const chaptersWritten = chapters.length
      const total = Math.max(chaptersWritten, 25) // Assume 25 chapters if no summary
      const percentage = total > 0 ? Math.min(100, Math.max(0, (chaptersWritten / total) * 100)) : 0
      const totalWords = chapters.reduce((sum, c) => {
        const wordCount = Number(c.word_count) || 0
        console.log(`[ProjectDashboard] Adding chapter ${c.chapter_number} word count: ${wordCount}`)
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
      console.log(`[ProjectDashboard] Adding chapter ${c.chapter_number} word count: ${wordCount}`)
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
    
    console.log('[ProjectDashboard] getProgressStats result:', result)
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
      onEditChapter(chapter.id)
    } else if (!chapter && onCreateChapter) {
      onCreateChapter(chapterNumber)
    }
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-brand-off-white">
        {/* Immersive loading hero matching the main dashboard */}
        <div className="relative min-h-[40vh] bg-gradient-to-br from-brand-lavender via-brand-ink-blue to-brand-blush-orange overflow-hidden">
          {/* Animated background particles */}
          <div className="absolute inset-0">
            <div className="absolute top-1/4 left-1/4 w-2 h-2 bg-white/20 rounded-full animate-float"></div>
            <div className="absolute top-1/3 right-1/4 w-1 h-1 bg-white/30 rounded-full animate-float" style={{animationDelay: '2s'}}></div>
            <div className="absolute bottom-1/3 left-1/3 w-3 h-3 bg-white/10 rounded-full animate-float" style={{animationDelay: '4s'}}></div>
          </div>
          
          <div className="relative z-10 flex items-center justify-center min-h-[40vh] px-6">
            <div className="text-center">
              <div className="mb-6">
                <div className="w-12 h-12 border-3 border-white/30 border-t-white/80 rounded-full animate-spin mx-auto mb-4"></div>
              </div>
              <h1 className="text-3xl md:text-4xl font-bold text-white mb-3 drop-shadow-lg">
                Loading your creative project...
              </h1>
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (!project) {
    return (
      <div className="min-h-screen bg-brand-off-white">
        {/* Hero section for error state */}
        <div className="relative min-h-[40vh] bg-gradient-to-br from-brand-lavender via-brand-ink-blue to-brand-blush-orange overflow-hidden">
          <div className="relative z-10 flex items-center justify-center min-h-[40vh] px-6">
            <div className="text-center text-white">
              <h2 className="text-2xl font-bold mb-4">Project Not Found</h2>
              <p className="text-white/90 mb-6">
                We couldn't load the project data. This might be due to permissions or connection issues.
              </p>
              <button 
                onClick={() => window.location.reload()}
                className="bg-white/20 backdrop-blur-sm text-white px-6 py-3 rounded-xl font-semibold hover:bg-white/30 transition-colors"
              >
                Try Again
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  const progressStats = getProgressStats()

  return (
    <div className="w-full">
      {/* Project Summary Header */}
      <div className="relative bg-gradient-to-r from-brand-lavender/10 via-white/60 to-brand-blush-orange/10 px-6 md:px-8 lg:px-12 py-8 border-b border-brand-lavender/20">
        <div className="max-w-6xl mx-auto">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-black text-brand-forest mb-2">Project Overview</h2>
              <p className="text-brand-forest/70 font-medium">
                {project.genre} • {progressStats.completed}/{progressStats.total} chapters complete • {progressStats.totalWords.toLocaleString()} words
              </p>
            </div>
            
            {/* Compact Progress Ring */}
            <div className="flex items-center space-x-6">
              <div className="relative">
                <svg className="w-16 h-16 transform -rotate-90" viewBox="0 0 100 100">
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
                  <span className="text-sm font-black text-brand-forest">
                    {Math.round(progressStats.percentage)}%
                  </span>
                </div>
              </div>
              
              <button
                onClick={() => setShowReferencesSidebar(!showReferencesSidebar)}
                className="bg-white/60 backdrop-blur-sm text-brand-forest px-4 py-2 rounded-xl font-semibold hover:bg-white/80 transition-all border border-brand-lavender/20"
              >
                {showReferencesSidebar ? 'Hide References' : 'Show References'}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="w-full px-6 md:px-8 lg:px-12 py-8">
        <div className={`grid grid-cols-1 ${showReferencesSidebar ? 'lg:grid-cols-4' : ''} gap-8`}>
          {/* Main Content Area */}
          <div className={`${showReferencesSidebar ? 'lg:col-span-3' : ''}`}>
            
            {/* Project Overview Content */}
              <div className="space-y-8">
                {/* Beautiful Stats Cards */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div className="bg-gradient-to-br from-white/60 via-brand-beige/40 to-brand-lavender/10 rounded-2xl p-6 backdrop-blur-sm border border-white/50 shadow-xl text-center hover:shadow-2xl transition-all hover:-translate-y-1">
                    <div className="text-3xl font-black text-brand-forest mb-2">{progressStats.chaptersWritten}</div>
                    <div className="text-sm font-bold text-brand-forest/70 uppercase tracking-wide">Chapters Written</div>
                  </div>
                  <div className="bg-gradient-to-br from-white/60 via-brand-beige/40 to-emerald-50 rounded-2xl p-6 backdrop-blur-sm border border-white/50 shadow-xl text-center hover:shadow-2xl transition-all hover:-translate-y-1">
                    <div className="text-3xl font-black text-emerald-600 mb-2">{progressStats.totalWords.toLocaleString()}</div>
                    <div className="text-sm font-bold text-brand-forest/70 uppercase tracking-wide">Words Written</div>
                  </div>
                  <div className="bg-gradient-to-br from-white/60 via-brand-beige/40 to-purple-50 rounded-2xl p-6 backdrop-blur-sm border border-white/50 shadow-xl text-center hover:shadow-2xl transition-all hover:-translate-y-1">
                    <div className="text-3xl font-black text-purple-600 mb-2">{Math.ceil((progressStats.totalWords || 0) / 250)}</div>
                    <div className="text-sm font-bold text-brand-forest/70 uppercase tracking-wide">Estimated Pages</div>
                  </div>
                </div>

                {/* Enhanced Chapter Status Grid */}
                <div className="bg-gradient-to-br from-white/60 via-brand-beige/30 to-brand-lavender/10 rounded-2xl p-8 backdrop-blur-sm border border-white/50 shadow-xl">
                  <h3 className="text-2xl font-black text-brand-forest mb-6">Chapter Status</h3>
                  <div className="grid grid-cols-4 md:grid-cols-8 gap-3">
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
                <div className="bg-gradient-to-br from-white/60 via-brand-beige/30 to-brand-lavender/10 rounded-2xl p-8 backdrop-blur-sm border border-white/50 shadow-xl">
                  <h3 className="text-2xl font-black text-brand-forest mb-6">Recent Chapters</h3>
                  <div className="space-y-4">
                    {chapters.slice(0, 5).map((chapter) => (
                      <div key={chapter.id} className="flex items-center justify-between p-4 bg-white/60 rounded-xl border border-brand-lavender/20 hover:bg-white/80 transition-all hover:shadow-lg">
                        <div>
                          <div className="font-bold text-brand-forest">{chapter.title}</div>
                          <div className="text-sm text-brand-forest/70 font-semibold">
                            {chapter.word_count.toLocaleString()} words • {chapter.stage}
                          </div>
                        </div>
                        <button
                          onClick={() => onEditChapter?.(chapter.id)}
                          className="bg-gradient-to-r from-brand-forest to-brand-lavender text-white px-4 py-2 rounded-lg font-semibold hover:shadow-lg transition-all hover:scale-105"
                        >
                          Edit
                        </button>
                      </div>
                    ))}
                    {chapters.length === 0 && (
                      <div className="text-center text-brand-forest/60 py-8">
                        <div className="text-lg font-semibold mb-2">No chapters found</div>
                        <div className="text-sm">Start by creating your first chapter</div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
          </div>

          {/* Enhanced References Sidebar */}
          {showReferencesSidebar && (
            <div className="lg:col-span-1">
              <div className="bg-gradient-to-br from-white/60 via-brand-beige/30 to-brand-lavender/10 rounded-2xl p-6 backdrop-blur-sm border border-white/50 shadow-xl">
                <h3 className="text-xl font-black text-brand-forest mb-4">References</h3>
                {loadingReferences ? (
                  <div className="animate-pulse space-y-3">
                    <div className="h-4 bg-gray-200 rounded w-3/4"></div>
                    <div className="h-4 bg-gray-200 rounded w-1/2"></div>
                    <div className="h-4 bg-gray-200 rounded w-5/6"></div>
                  </div>
                ) : references.length > 0 ? (
                  <div className="space-y-3">
                    {references.map((ref, index) => (
                      <div key={index} className="p-3 bg-white/60 rounded-xl border border-brand-lavender/20 hover:bg-white/80 transition-all cursor-pointer">
                        <div className="font-bold text-sm text-brand-forest">
                          {ref.filename}
                        </div>
                        <div className="text-xs text-brand-forest/60 mt-1 line-clamp-2">
                          {ref.summary}
                        </div>
                        <div className="text-xs text-brand-forest/40 mt-2">
                          Modified {new Date(ref.last_modified).toLocaleDateString()}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center text-brand-forest/60 py-6">
                    <div className="text-sm font-semibold">No reference files found</div>
                    <div className="text-xs mt-1">Reference files will appear here when available</div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default ProjectDashboard