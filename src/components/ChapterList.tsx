'use client'

import { useState } from 'react'
import { DocumentTextIcon, EyeIcon, TrashIcon, ArrowPathIcon, BeakerIcon } from '@heroicons/react/24/outline'
import { format } from 'date-fns'

interface Chapter {
  chapter: number
  filename: string
  word_count: number
  generation_time: number
  cost: number
  quality_score?: number
  created_at: string
  status: 'completed' | 'failed' | 'generating'
}

interface ChapterListProps {
  chapters: Chapter[]
  onRefresh: () => void
}

export function ChapterList({ chapters, onRefresh }: ChapterListProps) {
  const [selectedChapter, setSelectedChapter] = useState<Chapter | null>(null)
  const [chapterContent, setChapterContent] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isAssessing, setIsAssessing] = useState<number | null>(null)
  const [assessmentResults, setAssessmentResults] = useState<any>(null)

  const viewChapter = async (chapter: Chapter) => {
    setIsLoading(true)
    try {
      const response = await fetch(`/api/chapters/${chapter.chapter}`)
      if (response.ok) {
        const data = await response.json()
        setChapterContent(data.content)
        setSelectedChapter(chapter)
      }
    } catch (error) {
      console.error('Failed to load chapter:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const deleteChapter = async (chapterNumber: number) => {
    if (confirm(`Are you sure you want to delete Chapter ${chapterNumber}?`)) {
      try {
        const response = await fetch(`/api/chapters/${chapterNumber}`, {
          method: 'DELETE'
        })
        if (response.ok) {
          onRefresh()
        }
      } catch (error) {
        console.error('Failed to delete chapter:', error)
      }
    }
  }

  const assessChapter = async (chapterNumber: number) => {
    setIsAssessing(chapterNumber)
    setAssessmentResults(null)
    try {
      const response = await fetch('/api/quality/assess', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          chapterNumber: chapterNumber
        })
      })

      if (response.ok) {
        const data = await response.json()
        setAssessmentResults(data)
      } else {
        const errorData = await response.json()
        console.error('Assessment failed:', errorData.error)
      }
    } catch (error) {
      console.error('Failed to assess chapter:', error)
    } finally {
      setIsAssessing(null)
    }
  }

  const getQualityBadge = (score?: number) => {
    if (!score) return <span className="text-gray-400">No score</span>
    
    if (score >= 80) return <span className="px-2 py-1 text-xs bg-green-100 text-green-800 rounded-full">Excellent ({score})</span>
    if (score >= 70) return <span className="px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded-full">Good ({score})</span>
    if (score >= 60) return <span className="px-2 py-1 text-xs bg-yellow-100 text-yellow-800 rounded-full">Fair ({score})</span>
    return <span className="px-2 py-1 text-xs bg-red-100 text-red-800 rounded-full">Poor ({score})</span>
  }

  return (
    <div className="card">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold text-gray-900">
          Generated Chapters ({chapters.length})
        </h2>
        <button
          onClick={onRefresh}
          className="btn-secondary"
        >
          <ArrowPathIcon className="w-4 h-4 mr-1" />
          Refresh
        </button>
      </div>

      {chapters.length === 0 ? (
        <div className="text-center py-8">
          <DocumentTextIcon className="w-12 h-12 text-gray-400 mx-auto mb-4" />
          <p className="text-gray-500">No chapters generated yet</p>
          <p className="text-sm text-gray-400 mt-1">
            Use the form to generate your first chapter
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {chapters.map((chapter) => (
            <div
              key={chapter.chapter}
              className="border rounded-lg p-4 hover:bg-gray-50 transition-colors"
            >
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <div className="flex items-center space-x-3">
                    <h3 className="font-medium text-gray-900">
                      Chapter {chapter.chapter}
                    </h3>
                    {getQualityBadge(chapter.quality_score)}
                  </div>
                  
                  <div className="mt-2 grid grid-cols-2 gap-4 text-sm text-gray-600">
                    <div>
                      <span className="font-medium">Words:</span> {chapter.word_count?.toLocaleString() || 'Unknown'}
                    </div>
                    <div>
                      <span className="font-medium">Cost:</span> ${chapter.cost?.toFixed(4) || '0.0000'}
                    </div>
                    <div>
                      <span className="font-medium">Time:</span> {chapter.generation_time?.toFixed(1) || '0'}s
                    </div>
                    <div>
                      <span className="font-medium">Created:</span> {format(new Date(chapter.created_at), 'MMM dd, HH:mm')}
                    </div>
                  </div>
                </div>
                
                <div className="flex space-x-2 ml-4">
                  <button
                    onClick={() => viewChapter(chapter)}
                    className="p-2 text-gray-400 hover:text-gray-600"
                    title="View chapter"
                  >
                    <EyeIcon className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => assessChapter(chapter.chapter)}
                    disabled={isAssessing === chapter.chapter}
                    className="p-2 text-gray-400 hover:text-blue-600 disabled:opacity-50"
                    title="Quality assessment"
                  >
                    {isAssessing === chapter.chapter ? (
                      <div className="w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
                    ) : (
                      <BeakerIcon className="w-4 h-4" />
                    )}
                  </button>
                  <button
                    onClick={() => deleteChapter(chapter.chapter)}
                    className="p-2 text-gray-400 hover:text-red-600"
                    title="Delete chapter"
                  >
                    <TrashIcon className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Chapter Modal */}
      {selectedChapter && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg max-w-4xl w-full max-h-[90vh] overflow-hidden">
            <div className="px-6 py-4 border-b flex justify-between items-center">
              <h3 className="text-lg font-semibold">
                Chapter {selectedChapter.chapter}
              </h3>
              <button
                onClick={() => setSelectedChapter(null)}
                className="text-gray-400 hover:text-gray-600"
              >
                <span className="sr-only">Close</span>
                ✕
              </button>
            </div>
            <div className="p-6 overflow-y-auto max-h-[70vh]">
              {isLoading ? (
                <div className="text-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mx-auto"></div>
                  <p className="mt-2 text-gray-500">Loading chapter content...</p>
                </div>
              ) : (
                <div className="prose max-w-none">
                  <pre className="whitespace-pre-wrap font-serif text-gray-800">
                    {chapterContent}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Assessment Results Modal */}
      {assessmentResults && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg max-w-2xl w-full max-h-[90vh] overflow-hidden">
            <div className="px-6 py-4 border-b flex justify-between items-center">
              <h3 className="text-lg font-semibold">
                Quality Assessment - Chapter {assessmentResults.chapterNumber}
              </h3>
              <button
                onClick={() => setAssessmentResults(null)}
                className="text-gray-400 hover:text-gray-600"
              >
                <span className="sr-only">Close</span>
                ✕
              </button>
            </div>
            <div className="p-6 overflow-y-auto max-h-[70vh]">
              <div className="space-y-6">
                {/* Overall Score */}
                <div className="text-center">
                  <div className="text-3xl font-bold text-gray-900 mb-2">
                    {assessmentResults.overallScore?.toFixed(1) || '0.0'}
                  </div>
                  <p className="text-gray-600">Overall Quality Score</p>
                </div>

                {/* Individual Assessments */}
                <div className="grid grid-cols-1 gap-4">
                  {assessmentResults.assessment.brutalAssessment && (
                    <div className="p-4 bg-gray-50 rounded-lg">
                      <h4 className="font-medium text-gray-900 mb-2">Brutal Assessment</h4>
                      <div className="text-2xl font-bold text-blue-600 mb-1">
                        {assessmentResults.assessment.brutalAssessment.score?.toFixed(1) || 'N/A'}
                      </div>
                      {assessmentResults.assessment.brutalAssessment.error && (
                        <p className="text-sm text-red-600">
                          {assessmentResults.assessment.brutalAssessment.error}
                        </p>
                      )}
                    </div>
                  )}

                  {assessmentResults.assessment.engagementScore && (
                    <div className="p-4 bg-gray-50 rounded-lg">
                      <h4 className="font-medium text-gray-900 mb-2">Reader Engagement</h4>
                      <div className="text-2xl font-bold text-green-600 mb-1">
                        {assessmentResults.assessment.engagementScore.score?.toFixed(1) || 'N/A'}
                      </div>
                      {assessmentResults.assessment.engagementScore.error && (
                        <p className="text-sm text-red-600">
                          {assessmentResults.assessment.engagementScore.error}
                        </p>
                      )}
                    </div>
                  )}

                  {assessmentResults.assessment.qualityGates && (
                    <div className="p-4 bg-gray-50 rounded-lg">
                      <h4 className="font-medium text-gray-900 mb-2">Quality Gates</h4>
                      <div className="text-2xl font-bold text-purple-600 mb-1">
                        {assessmentResults.assessment.qualityGates.passed || 0} / {assessmentResults.assessment.qualityGates.total || 0}
                      </div>
                      <p className="text-sm text-gray-600">
                        Pass Rate: {((assessmentResults.assessment.qualityGates.passRate || 0) * 100).toFixed(1)}%
                      </p>
                      {assessmentResults.assessment.qualityGates.error && (
                        <p className="text-sm text-red-600">
                          {assessmentResults.assessment.qualityGates.error}
                        </p>
                      )}
                    </div>
                  )}
                </div>

                <div className="text-xs text-gray-500">
                  Assessment completed at: {new Date(assessmentResults.timestamp).toLocaleString()}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
} 