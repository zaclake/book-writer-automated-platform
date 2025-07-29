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
  const [isLoading, setIsLoading] = useState(true)
  
  // UI state
  const [activeTab, setActiveTab] = useState<'overview' | 'chapters' | 'references' | 'progress' | 'cover-art'>('overview')
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
      
      // Load project details, chapters, and summary in parallel
      const [projectRes, chaptersRes, summaryRes] = await Promise.all([
        fetch(`/api/projects/${projectId}`, {
          headers: { 'Authorization': `Bearer ${await getToken()}` }
        }),
        fetch(`/api/projects/${projectId}/chapters`, {
          headers: { 'Authorization': `Bearer ${await getToken()}` }
        }),
        fetch(`/api/prewriting/summary?project_id=${projectId}`, {
          headers: { 'Authorization': `Bearer ${await getToken()}` }
        })
      ])

      // Handle project data
      if (projectRes.ok) {
        const data = await projectRes.json()
        // API may return { project: {...} } or the object itself
        const p = data.project || data
        console.log('[ProjectDashboard] Project data loaded:', p ? 'success' : 'no project')

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
        const ch = chaptersData.chapters || chaptersData // backend may return flat array
        console.log('[ProjectDashboard] Chapters loaded:', ch.length || 0, 'chapters')
        setChapters(ch)
      } else {
        console.error('[ProjectDashboard] Failed to load chapters:', chaptersRes.status, await chaptersRes.text())
        setChapters([]) // Empty is valid for new projects
      }

      // Handle summary data (might not exist for new projects)
      if (summaryRes.ok) {
        const summaryData = await summaryRes.json()
        console.log('[ProjectDashboard] Summary loaded:', summaryData.summary ? 'success' : 'no summary')
        setSummary(summaryData.summary)
      } else if (summaryRes.status === 404) {
        console.log('[ProjectDashboard] Summary not found (normal for new projects)')
        setSummary(null)
      } else {
        console.error('[ProjectDashboard] Failed to load summary:', summaryRes.status, await summaryRes.text())
        setSummary(null)
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
    if (!summary) return { completed: 0, total: 0, percentage: 0, totalWords: 0 }
    
    const completed = chapters.filter(c => c.stage === 'complete').length
    const total = summary.total_chapters
    const percentage = total > 0 ? (completed / total) * 100 : 0
    const totalWords = chapters.reduce((sum, c) => sum + c.word_count, 0)
    
    return { completed, total, percentage, totalWords }
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
      <div className="flex items-center justify-center h-64">
        <div className="animate-pulse text-gray-500">Loading project dashboard...</div>
      </div>
    )
  }

  if (!project) {
    return (
      <div className="text-center text-gray-500 p-8">
        Project not found
      </div>
    )
  }

  const progressStats = getProgressStats()

  return (
    <div className="max-w-7xl mx-auto p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold">{project.title}</h1>
          <p className="text-gray-600">
            {project.genre} • {project.status} • {progressStats.completed}/{progressStats.total} chapters complete
          </p>
        </div>
        <div className="flex space-x-2">
          <Button
            variant="outline"
            onClick={() => setShowReferencesSidebar(!showReferencesSidebar)}
          >
            {showReferencesSidebar ? 'Hide References' : 'Show References'}
          </Button>
          <Button onClick={() => setActiveTab('chapters')}>
            View Chapters
          </Button>
        </div>
      </div>

      {/* Progress Bar */}
      <Card className="mb-6">
        <CardContent className="p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium">Project Progress</span>
            <span className="text-sm text-gray-500">{Math.round(progressStats.percentage)}%</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progressStats.percentage}%` }}
            />
          </div>
          <div className="flex justify-between text-sm text-gray-500 mt-2">
            <span>{progressStats.completed} chapters complete</span>
            <span>{progressStats.totalWords.toLocaleString()} words written</span>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Main Content */}
        <div className={`${showReferencesSidebar ? 'lg:col-span-3' : 'lg:col-span-4'}`}>
          
          {/* Navigation Tabs */}
          <div className="flex space-x-1 mb-6 border-b">
            {(['overview', 'chapters', 'progress', 'references', 'cover-art'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 font-medium text-sm rounded-t-lg ${
                  activeTab === tab
                    ? 'bg-blue-100 text-blue-700 border-b-2 border-blue-500'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                {tab.charAt(0).toUpperCase() + tab.slice(1).replace('-', ' ')}
              </button>
            ))}
          </div>

          {/* Tab Content */}
          {activeTab === 'overview' && (
            <div className="space-y-6">
              {/* Quick Stats */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Card>
                  <CardContent className="p-4 text-center">
                    <div className="text-2xl font-bold text-blue-600">{progressStats.completed}</div>
                    <div className="text-sm text-gray-500">Chapters Complete</div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4 text-center">
                    <div className="text-2xl font-bold text-green-600">{progressStats.totalWords.toLocaleString()}</div>
                    <div className="text-sm text-gray-500">Words Written</div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4 text-center">
                    <div className="text-2xl font-bold text-purple-600">{Math.ceil(progressStats.totalWords / 250)}</div>
                    <div className="text-sm text-gray-500">Estimated Pages</div>
                  </CardContent>
                </Card>
              </div>

              {/* Chapter Status Grid */}
              <Card>
                <CardHeader>
                  <CardTitle>Chapter Status</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-4 md:grid-cols-8 gap-3">
                    {Array.from({ length: project.settings.target_chapters }, (_, i) => {
                      const chapterNumber = i + 1
                      const status = getChapterStatus(chapterNumber)
                      return (
                        <button
                          key={chapterNumber}
                          className={`aspect-square rounded-lg border-2 flex items-center justify-center text-sm font-medium transition-colors ${
                            status === 'complete' ? 'bg-green-100 border-green-300 text-green-800' :
                            status === 'revision' ? 'bg-yellow-100 border-yellow-300 text-yellow-800' :
                            status === 'draft' ? 'bg-blue-100 border-blue-300 text-blue-800' :
                            'bg-gray-50 border-gray-200 text-gray-400'
                          } hover:scale-105`}
                          onClick={() => handleChapterClick(chapterNumber)}
                        >
                          {chapterNumber}
                        </button>
                      )
                    })}
                  </div>
                </CardContent>
              </Card>

              {/* Recent Activity */}
              <Card>
                <CardHeader>
                  <CardTitle>Recent Chapters</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {chapters.slice(0, 5).map((chapter) => (
                      <div key={chapter.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                        <div>
                          <div className="font-medium">{chapter.title}</div>
                          <div className="text-sm text-gray-500">
                            {chapter.word_count} words • {chapter.stage}
                          </div>
                        </div>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => onEditChapter?.(chapter.id)}
                        >
                          Edit
                        </Button>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {activeTab === 'chapters' && (
            <div className="space-y-6">
              {/* Chapter Progress Overview */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <Card>
                  <CardContent className="p-4 text-center">
                    <div className="text-2xl font-bold text-blue-600">{chapters.filter(c => c.stage === 'draft').length}</div>
                    <div className="text-sm text-gray-500">Draft</div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4 text-center">
                    <div className="text-2xl font-bold text-yellow-600">{chapters.filter(c => c.stage === 'revision').length}</div>
                    <div className="text-sm text-gray-500">In Revision</div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4 text-center">
                    <div className="text-2xl font-bold text-green-600">{chapters.filter(c => c.stage === 'complete').length}</div>
                    <div className="text-sm text-gray-500">Complete</div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4 text-center">
                    <div className="text-2xl font-bold text-orange-600">{chapters.filter(c => c.director_notes_count > 0).length}</div>
                    <div className="text-sm text-gray-500">Has Notes</div>
                  </CardContent>
                </Card>
              </div>

              {/* Chapters List */}
              <Card>
                <CardHeader>
                  <CardTitle>All Chapters</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {chapters.map((chapter) => (
                      <div key={chapter.id} className="flex items-center justify-between p-4 border rounded-lg">
                        <div className="flex-1">
                          <div className="flex items-center space-x-3">
                            <span className="font-medium">Chapter {chapter.chapter_number}</span>
                            <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                              chapter.stage === 'complete' ? 'bg-green-100 text-green-800' :
                              chapter.stage === 'revision' ? 'bg-yellow-100 text-yellow-800' :
                              'bg-blue-100 text-blue-800'
                            }`}>
                              {chapter.stage.charAt(0).toUpperCase() + chapter.stage.slice(1)}
                            </span>
                          </div>
                          <div className="text-sm text-gray-600 mt-1">
                            {chapter.title}
                          </div>
                          <div className="text-xs text-gray-500 mt-1">
                            {chapter.word_count.toLocaleString()} words
                          </div>
                        </div>
                        
                        <div className="flex items-center space-x-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => onEditChapter && onEditChapter(chapter.id)}
                          >
                            Edit
                          </Button>
                        </div>
                      </div>
                    ))}
                    
                    {chapters.length === 0 && (
                      <div className="text-center text-gray-500 py-8">
                        No chapters found. Start by creating your first chapter.
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {activeTab === 'progress' && (
            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle>Writing Progress</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <div>
                      <div className="flex justify-between text-sm mb-1">
                        <span>Overall Progress</span>
                        <span>{Math.round(progressStats.percentage)}%</span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2">
                        <div 
                          className="bg-blue-600 h-2 rounded-full" 
                          style={{ width: `${progressStats.percentage}%` }}
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <span className="text-sm text-gray-500">Chapters Completed</span>
                        <div className="text-2xl font-bold">{progressStats.completed} / {progressStats.total}</div>
                      </div>
                      <div>
                        <span className="text-sm text-gray-500">Total Words</span>
                        <div className="text-2xl font-bold">{progressStats.totalWords.toLocaleString()}</div>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {activeTab === 'references' && (
            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle>Reference Materials</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-gray-600">Reference files and character sheets will be displayed here.</p>
                </CardContent>
              </Card>
            </div>
          )}

          {activeTab === 'cover-art' && (
            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle>Cover Art Generator</CardTitle>
                </CardHeader>
                <CardContent>
                  <CoverArtGenerator projectId={projectId} />
                </CardContent>
              </Card>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default ProjectDashboard