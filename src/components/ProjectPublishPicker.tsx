'use client'

import React, { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useProjects } from '@/hooks/useProjects'
import { useAuth } from '@clerk/nextjs'
import { Project } from '@/types/project'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { BookOpen, Calendar, FileText, Loader2 } from 'lucide-react'

interface ProjectWithStats extends Project {
  chapterCount: number
  wordCount: number
  lastUpdated: string
}

// New prop interface to support modal dialog usage
interface ProjectPublishPickerProps {
  /**
   * If provided, the picker will render inside a Dialog that opens when this
   * element is clicked. When omitted the list is rendered inline.
   */
  trigger?: React.ReactNode
}

const ProjectPublishPicker: React.FC<ProjectPublishPickerProps> = ({ trigger }) => {
  const router = useRouter()
  const { getToken } = useAuth()
  const { projects, loading, error } = useProjects()
  const [projectsWithStats, setProjectsWithStats] = useState<ProjectWithStats[]>([])
  const [loadingStats, setLoadingStats] = useState(false)

  // Fetch chapter data for each project to calculate word counts
  useEffect(() => {
    const fetchProjectStats = async () => {
      if (!projects || projects.length === 0) return
      
      setLoadingStats(true)
      const token = await getToken()
      if (!token) return

      const projectStatsPromises = projects.map(async (project) => {
        try {
          // Fetch chapters for this project
          const chaptersResponse = await fetch(`/api/v2/projects/${encodeURIComponent(project.id)}/chapters`, {
            headers: { 'Authorization': `Bearer ${token}` }
          })

          let chapterCount = 0
          let wordCount = 0
          
          if (chaptersResponse.ok) {
            const chaptersData = await chaptersResponse.json()
            const chapters = chaptersData.chapters || []
            chapterCount = chapters.length
            
            // Calculate total word count from all chapters
            wordCount = chapters.reduce((total: number, chapter: any) => {
              return total + (chapter.word_count || 0)
            }, 0)
          } else {
            // Fallback to progress data
            chapterCount = project.progress?.chapters_completed || 0
            wordCount = project.progress?.current_word_count || 0
          }

          return {
            ...project,
            chapterCount,
            wordCount,
            lastUpdated: new Date(project.metadata.updated_at).toLocaleDateString()
          } as ProjectWithStats
        } catch (error) {
          console.warn(`Failed to fetch stats for project ${project.id}:`, error)
          return {
            ...project,
            chapterCount: project.progress?.chapters_completed || 0,
            wordCount: project.progress?.current_word_count || 0,
            lastUpdated: new Date(project.metadata.updated_at).toLocaleDateString()
          } as ProjectWithStats
        }
      })

      const projectsWithStatsData = await Promise.all(projectStatsPromises)
      setProjectsWithStats(projectsWithStatsData)
      setLoadingStats(false)
    }

    fetchProjectStats()
  }, [projects, getToken])

  // Filter projects that have chapters
  const publishableProjects = projectsWithStats.filter(project => project.chapterCount > 0)

  const handleSelectProject = (projectId: string) => {
    router.push(`/project/${projectId}/publish`)
  }

  if (loading || loadingStats) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-6 w-6 animate-spin mr-2" />
        <span>Loading projects...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-center py-8">
        <p className="text-red-600">Failed to load projects: {error.message}</p>
      </div>
    )
  }

  if (publishableProjects.length === 0) {
    return (
      <div className="text-center py-8">
        <BookOpen className="h-12 w-12 mx-auto text-gray-400 mb-4" />
        <h3 className="text-lg font-medium text-gray-900 mb-2">No Publishable Projects</h3>
        <p className="text-gray-600 mb-4">
          You need projects with chapters to publish. Start writing some chapters first!
        </p>
        <Button onClick={() => router.push('/dashboard')}>
          Go to Dashboard
        </Button>
      </div>
    )
  }

  // Build the core list UI once so it can be reused inline or inside a dialog
  const listContent = (
    <div className="space-y-6" data-cy="project-publish-picker">
      <div>
        <h2 className="text-2xl font-bold text-gray-900 mb-2">Select Project to Publish</h2>
        <p className="text-gray-600">
          Choose a project with chapters to convert to EPUB and PDF formats.
        </p>
      </div>

      <ScrollArea className="h-96">
        <div className="grid gap-4" data-cy="publishable-projects-list">
          {publishableProjects.map((project) => (
            <Card 
              key={project.id} 
              className="cursor-pointer hover:shadow-md transition-shadow"
              onClick={() => handleSelectProject(project.id)}
              data-cy={`project-card-${project.id}`}
            >
              <CardHeader>
                <CardTitle className="text-lg">{project.metadata.title}</CardTitle>
                <CardDescription>
                  Ready for publishing • {project.chapterCount} chapters • {project.wordCount.toLocaleString()} words
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between text-sm text-gray-600">
                  <div className="flex items-center space-x-4">
                    <div className="flex items-center">
                      <FileText className="h-4 w-4 mr-1" />
                      <span data-cy={`chapter-count-${project.id}`}>{project.chapterCount} chapters</span>
                    </div>
                    <div className="flex items-center">
                      <BookOpen className="h-4 w-4 mr-1" />
                      <span data-cy={`word-count-${project.id}`}>{project.wordCount.toLocaleString()} words</span>
                    </div>
                  </div>
                  <div className="flex items-center">
                    <Calendar className="h-4 w-4 mr-1" />
                    <span>Updated {project.lastUpdated}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </ScrollArea>
    </div>
  )

  // If trigger is supplied, render a dialog wrapper; otherwise render inline
  if (trigger) {
    return (
      <Dialog>
        <DialogTrigger asChild>{trigger}</DialogTrigger>
        <DialogContent className="max-w-3xl w-full">
          <DialogHeader>
            <DialogTitle>Select Project to Publish</DialogTitle>
            <DialogDescription>
              Choose a project with chapters to convert to EPUB and PDF formats.
            </DialogDescription>
          </DialogHeader>
          {listContent}
        </DialogContent>
      </Dialog>
    )
  }

  return listContent
}

export default ProjectPublishPicker 