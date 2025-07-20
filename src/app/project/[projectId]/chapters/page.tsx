'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import { ChapterList } from '@/components/ChapterList'
import { ChapterGenerationForm } from '@/components/ChapterGenerationForm'
import { useProjectChapters, useProject } from '@/hooks/useFirestore'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export default function ProjectChaptersPage() {
  const params = useParams()
  const projectId = params.projectId as string
  
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const [isGenerating, setIsGenerating] = useState(false)

  // Real-time Firestore hooks
  const { chapters, loading: chaptersLoading } = useProjectChapters(projectId)
  const { project } = useProject(projectId)

  const handleRefresh = () => {
    setRefreshTrigger(prev => prev + 1)
  }

  const handleGenerationComplete = () => {
    setIsGenerating(false)
    setRefreshTrigger(prev => prev + 1)
  }

  if (!projectId) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <h2 className="text-xl font-semibold text-gray-900 mb-2">Invalid Project</h2>
          <p className="text-gray-600">No project ID provided</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Chapters</h1>
          <p className="text-gray-600 mt-1">
            Write and edit chapters for {project?.metadata?.title || 'your project'}
          </p>
          {chapters.length > 0 && (
            <div className="mt-2 flex items-center space-x-4 text-sm text-gray-500">
              <span>{chapters.length} chapters</span>
              <span>•</span>
              <span>
                {chapters.reduce((total, ch) => total + (ch.metadata?.word_count || 0), 0).toLocaleString()} words total
              </span>
              {chaptersLoading && (
                <>
                  <span>•</span>
                  <div className="flex items-center">
                    <div className="w-2 h-2 bg-blue-600 rounded-full animate-pulse mr-1"></div>
                    <span>Syncing...</span>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Chapter Generation */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center space-x-2">
            <span>✨</span>
            <span>Generate New Chapter</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ChapterGenerationForm
            onGenerationStart={() => setIsGenerating(true)}
            onGenerationComplete={handleGenerationComplete}
            isGenerating={isGenerating}
            projectId={projectId}
          />
        </CardContent>
      </Card>

      {/* Chapter List */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <span>📚</span>
              <span>Your Chapters</span>
            </div>
            {chapters.length > 0 && (
              <button
                onClick={handleRefresh}
                className="text-sm text-gray-500 hover:text-gray-700 flex items-center space-x-1"
              >
                <span>🔄</span>
                <span>Refresh</span>
              </button>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {chapters.length === 0 && !chaptersLoading ? (
            <div className="text-center py-12">
              <div className="text-gray-400 text-4xl mb-4">📝</div>
              <h3 className="text-lg font-medium text-gray-900 mb-2">No chapters yet</h3>
              <p className="text-gray-600 mb-4">
                Start writing by generating your first chapter above.
              </p>
            </div>
          ) : (
            <ChapterList 
              chapters={chapters}
              loading={chaptersLoading}
              onRefresh={handleRefresh}
              projectId={projectId}
            />
          )}
        </CardContent>
      </Card>
    </div>
  )
} 