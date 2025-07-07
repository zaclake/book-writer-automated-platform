'use client'

import { useState, useEffect } from 'react'
import { ChapterGenerationForm } from '@/components/ChapterGenerationForm'
import { ChapterList } from '@/components/ChapterList'
import { QualityMetrics } from '@/components/QualityMetrics'
import { CostTracker } from '@/components/CostTracker'
import { SystemStatus } from '@/components/SystemStatus'
import { BookBibleUpload } from '@/components/BookBibleUpload'
import { ReferenceFileManager } from '@/components/ReferenceFileManager'
import { ProjectStatus } from '@/components/ProjectStatus'
import { AutoCompleteBookManager } from '@/components/AutoCompleteBookManager'

// Force dynamic rendering to avoid static generation issues
export const dynamic = 'force-dynamic'

export default function Dashboard() {
  const [isGenerating, setIsGenerating] = useState(false)
  const [chapters, setChapters] = useState([])
  const [metrics, setMetrics] = useState(null)
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const [projectInitialized, setProjectInitialized] = useState(false)

  useEffect(() => {
    fetchChapters()
    fetchMetrics()
  }, [refreshTrigger])

  const fetchChapters = async () => {
    try {
      const response = await fetch('/api/chapters')
      if (response.ok) {
        const data = await response.json()
        setChapters(data.chapters || [])
      }
    } catch (error) {
      console.error('Failed to fetch chapters:', error)
    }
  }

  const fetchMetrics = async () => {
    try {
      const response = await fetch('/api/metrics')
      if (response.ok) {
        const data = await response.json()
        setMetrics(data)
      }
    } catch (error) {
      console.error('Failed to fetch metrics:', error)
    }
  }

  const handleGenerationComplete = () => {
    setIsGenerating(false)
    setRefreshTrigger(prev => prev + 1)
  }

  const handleProjectInitialized = () => {
    setProjectInitialized(true)
    setRefreshTrigger(prev => prev + 1)
  }

  const handleAutoCompleteJobStarted = (jobId: string) => {
    console.log('Auto-complete job started:', jobId)
    setRefreshTrigger(prev => prev + 1)
  }

  const handleAutoCompleteJobCompleted = (jobId: string, result: any) => {
    console.log('Auto-complete job completed:', jobId, result)
    setRefreshTrigger(prev => prev + 1)
  }

  return (
    <div className="px-4 py-6 sm:px-0">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">
          Chapter Generation Dashboard
        </h1>
        <p className="mt-2 text-lg text-gray-600">
          AI-powered book writing with automated quality assessment
        </p>
      </div>

      {/* Status Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 mb-8">
        <div className="lg:col-span-1">
          <ProjectStatus />
        </div>
        <div className="lg:col-span-1">
          <CostTracker metrics={metrics} />
        </div>
        <div className="lg:col-span-2">
          <QualityMetrics metrics={metrics} />
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 xl:grid-cols-4 gap-6">
        {/* Left Column - Book Bible Upload, Auto-Complete & Generation */}
        <div className="xl:col-span-1 space-y-6">
          <BookBibleUpload onProjectInitialized={handleProjectInitialized} />
          
          <AutoCompleteBookManager 
            onJobStarted={handleAutoCompleteJobStarted}
            onJobCompleted={handleAutoCompleteJobCompleted}
          />
          
          <ChapterGenerationForm
            onGenerationStart={() => setIsGenerating(true)}
            onGenerationComplete={handleGenerationComplete}
            isGenerating={isGenerating}
          />
        </div>

        {/* Middle Column - Reference Files */}
        <div className="xl:col-span-1">
          <ReferenceFileManager />
        </div>

        {/* Right Column - Chapter List */}
        <div className="xl:col-span-2">
          <ChapterList 
            chapters={chapters}
            onRefresh={() => setRefreshTrigger(prev => prev + 1)}
          />
        </div>
      </div>
    </div>
  )
} 