'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { useUser, useAuth } from '@clerk/nextjs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toast } from '@/components/ui/use-toast'

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
  const [activeTab, setActiveTab] = useState<'overview' | 'chapters' | 'references' | 'progress'>('overview')
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
      
      // Load project details, chapters, and summary in parallel
      const [projectRes, chaptersRes, summaryRes] = await Promise.all([
        fetch(`/api/book-bible/${projectId}`, {
          headers: { 'Authorization': `Bearer ${await getToken()}` }
        }),
        fetch(`/api/chapters?project_id=${projectId}`, {
          headers: { 'Authorization': `Bearer ${await getToken()}` }
        }),
        fetch(`/api/prewriting/summary?project_id=${projectId}`, {
          headers: { 'Authorization': `Bearer ${await getToken()}` }
        })
      ])

      if (projectRes.ok) {
        const projectData = await projectRes.json()
        setProject(projectData.project)
      }

      if (chaptersRes.ok) {
        const chaptersData = await chaptersRes.json()
        setChapters(chaptersData.chapters || [])
      }

      if (summaryRes.ok) {
        const summaryData = await summaryRes.json()
        setSummary(summaryData.summary)
      }

    } catch (error) {
      console.error('Error loading project data:', error)
      toast({
        title: "Error",
        description: "Failed to load project data. Please try again.",
        variant: "destructive"
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
            {[
              { id: 'overview', label: 'Overview' },
              { id: 'chapters', label: 'Chapters' },
              { id: 'progress', label: 'Progress' },
              { id: 'references', label: 'References' }
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === tab.id
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab Content */}
          {activeTab === 'overview' && (
            <div className="space-y-6">
              {/* Project Stats */}
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
                    <div className="text-2xl font-bold text-purple-600">{chapters.filter(c => c.director_notes_count > 0).length}</div>
                    <div className="text-sm text-gray-500">Chapters with Notes</div>
                  </CardContent>
                </Card>
              </div>

              {/* Recent Activity */}
              <Card>
                <CardHeader>
                  <CardTitle>Recent Activity</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {chapters
                      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
                      .slice(0, 5)
                      .map((chapter) => (
                        <div key={chapter.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                          <div>
                            <div className="font-medium">{chapter.title}</div>
                            <div className="text-sm text-gray-500">
                              {chapter.word_count} words • {chapter.stage} • 
                              Updated {new Date(chapter.updated_at).toLocaleDateString()}
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
              {/* Chapter Timeline */}
              <Card>
                <CardHeader>
                  <CardTitle>Chapter Timeline</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-4">
                    {Array.from({ length: summary?.total_chapters || 25 }, (_, i) => i + 1).map((chapterNumber) => {
                      const chapter = chapters.find(c => c.chapter_number === chapterNumber)
                      const status = getChapterStatus(chapterNumber)
                      const qualityColor = getChapterQualityColor(chapter?.quality_scores)

                      return (
                        <div
                          key={chapterNumber}
                          onClick={() => handleChapterClick(chapterNumber)}
                          className={`p-3 border rounded-lg cursor-pointer transition-all hover:shadow-md ${
                            status === 'complete' ? 'bg-green-50 border-green-200' :
                            status === 'revision' ? 'bg-yellow-50 border-yellow-200' :
                            status === 'draft' ? 'bg-blue-50 border-blue-200' :
                            'bg-gray-50 border-gray-200'
                          }`}
                        >
                          <div className="flex items-center justify-between mb-2">
                            <span className="font-medium">Ch. {chapterNumber}</span>
                            {chapter?.quality_scores && (
                              <div className={`w-3 h-3 rounded-full ${qualityColor}`} title={`Quality: ${chapter.quality_scores.overall_rating}/10`} />
                            )}
                          </div>
                          {chapter ? (
                            <div className="text-xs text-gray-600">
                              <div>{chapter.word_count} words</div>
                              <div className="capitalize">{chapter.stage}</div>
                              {chapter.director_notes_count > 0 && (
                                <div className="text-orange-600">{chapter.director_notes_count} notes</div>
                              )}
                            </div>
                          ) : (
                            <div className="text-xs text-gray-400">Not started</div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </CardContent>
              </Card>

              {/* Chapter List */}
              <Card>
                <CardHeader>
                  <CardTitle>Chapter Details</CardTitle>
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
                              {chapter.stage}
                            </span>
                            {chapter.quality_scores && (
                              <span className="text-sm text-gray-500">
                                Quality: {chapter.quality_scores.overall_rating}/10
                              </span>
                            )}
                          </div>
                          <div className="text-sm text-gray-600 mt-1">
                            {chapter.title} • {chapter.word_count}/{chapter.target_word_count} words
                            {chapter.director_notes_count > 0 && ` • ${chapter.director_notes_count} notes`}
                          </div>
                        </div>
                        <Button
                          size="sm"
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

          {activeTab === 'progress' && (
            <div className="space-y-6">
              {/* Progress Analytics */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <Card>
                  <CardHeader>
                    <CardTitle>Writing Progress</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-4">
                      <div className="flex justify-between">
                        <span>Chapters Draft</span>
                        <span>{chapters.filter(c => c.stage === 'draft').length}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Chapters in Revision</span>
                        <span>{chapters.filter(c => c.stage === 'revision').length}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Chapters Complete</span>
                        <span>{chapters.filter(c => c.stage === 'complete').length}</span>
                      </div>
                      <div className="flex justify-between font-medium">
                        <span>Total Progress</span>
                        <span>{Math.round(progressStats.percentage)}%</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>Quality Metrics</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-4">
                      {chapters.filter(c => c.quality_scores).length > 0 ? (
                        <>
                          <div className="flex justify-between">
                            <span>Average Quality</span>
                            <span>
                              {(chapters
                                .filter(c => c.quality_scores)
                                .reduce((sum, c) => sum + (c.quality_scores?.overall_rating || 0), 0) /
                                chapters.filter(c => c.quality_scores).length
                              ).toFixed(1)}/10
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span>High Quality (8+)</span>
                            <span>{chapters.filter(c => (c.quality_scores?.overall_rating || 0) >= 8).length}</span>
                          </div>
                          <div className="flex justify-between">
                            <span>Needs Improvement (&lt;6)</span>
                            <span>{chapters.filter(c => (c.quality_scores?.overall_rating || 0) < 6).length}</span>
                          </div>
                        </>
                      ) : (
                        <div className="text-gray-500 text-sm">No quality scores available yet</div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              </div>
            </div>
          )}

          {activeTab === 'references' && summary && (
            <div className="space-y-6">
              {/* Story Elements */}
              <Card>
                <CardHeader>
                  <CardTitle>Story Elements</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <h4 className="font-medium mb-2">Premise</h4>
                    <p className="text-gray-600">{summary.premise}</p>
                  </div>
                  <div>
                    <h4 className="font-medium mb-2">Setting</h4>
                    <p className="text-gray-600">{summary.setting.description}</p>
                  </div>
                  <div>
                    <h4 className="font-medium mb-2">Themes</h4>
                    <div className="flex flex-wrap gap-2">
                      {summary.themes.map((theme, index) => (
                        <span key={index} className="px-2 py-1 bg-blue-100 text-blue-800 rounded-full text-sm">
                          {theme}
                        </span>
                      ))}
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Characters */}
              <Card>
                <CardHeader>
                  <CardTitle>Characters</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {summary.main_characters.map((character, index) => (
                      <div key={index} className="p-3 bg-gray-50 rounded-lg">
                        <div className="font-medium">{character.name}</div>
                        <div className="text-sm text-gray-600">{character.description}</div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </div>

        {/* References Sidebar */}
        {showReferencesSidebar && summary && (
          <div className="lg:col-span-1">
            <Card className="sticky top-6">
              <CardHeader>
                <CardTitle>Quick Reference</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Project Info */}
                <div>
                  <h4 className="font-medium text-sm mb-2">Project</h4>
                  <div className="text-sm text-gray-600">
                    <div>{project.genre}</div>
                    <div>{summary.total_chapters} chapters planned</div>
                    <div>{summary.word_count_target} words per chapter</div>
                  </div>
                </div>

                {/* Characters */}
                <div>
                  <h4 className="font-medium text-sm mb-2">Main Characters</h4>
                  <div className="space-y-1">
                    {summary.main_characters.slice(0, 3).map((character, index) => (
                      <div key={index} className="text-sm text-gray-600">
                        {character.name}
                      </div>
                    ))}
                    {summary.main_characters.length > 3 && (
                      <div className="text-xs text-gray-500">+{summary.main_characters.length - 3} more</div>
                    )}
                  </div>
                </div>

                {/* Themes */}
                <div>
                  <h4 className="font-medium text-sm mb-2">Key Themes</h4>
                  <div className="space-y-1">
                    {summary.themes.slice(0, 3).map((theme, index) => (
                      <div key={index} className="text-sm text-gray-600">{theme}</div>
                    ))}
                  </div>
                </div>

                {/* Quick Stats */}
                <div className="border-t pt-4">
                  <h4 className="font-medium text-sm mb-2">Progress</h4>
                  <div className="text-sm text-gray-600 space-y-1">
                    <div>{progressStats.completed}/{progressStats.total} chapters</div>
                    <div>{progressStats.totalWords.toLocaleString()} words</div>
                    <div>{Math.round(progressStats.percentage)}% complete</div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </div>
  )
}

export default ProjectDashboard 