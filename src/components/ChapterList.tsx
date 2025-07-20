'use client'

import { useState } from 'react'
import { 
  EyeIcon, 
  TrashIcon, 
  DocumentTextIcon, 
  ArrowPathIcon,
  BeakerIcon,
  XMarkIcon,
  DocumentArrowDownIcon,
  PencilIcon
} from '@heroicons/react/24/outline'
import { format } from 'date-fns'
import { useAuthToken } from '@/lib/auth'
import { Chapter } from '@/lib/firestore-client'
import ChapterEditor from '@/components/ChapterEditor'

interface ChapterListProps {
  chapters: Chapter[]
  loading?: boolean
  onRefresh: () => void
  projectId: string | null
}

export function ChapterList({ chapters, loading = false, onRefresh, projectId }: ChapterListProps) {
  const { getAuthHeaders } = useAuthToken()
  const [selectedChapter, setSelectedChapter] = useState<Chapter | null>(null)
  const [chapterContent, setChapterContent] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isAssessing, setIsAssessing] = useState<number | null>(null)
  const [assessmentResults, setAssessmentResults] = useState<any>(null)
  const [editMode, setEditMode] = useState(false)

  const viewChapter = async (chapter: Chapter) => {
    setEditMode(false)
    setIsLoading(true)
    try {
      if (!projectId) {
        console.error('No project ID found')
        return
      }
      
      // First try to use the content from Firestore
      if (chapter.content) {
        setChapterContent(chapter.content)
        setSelectedChapter(chapter)
        setIsLoading(false)
        return
      }
      
      // Fallback to API if content not available in Firestore
      const authHeaders = await getAuthHeaders()
      
      const response = await fetch(`/api/chapters/${chapter.chapter_number}?project_id=${encodeURIComponent(projectId)}`, {
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders
        }
      })
      
      if (response.ok) {
        const data = await response.json()
        setChapterContent(data.content)
        setSelectedChapter(chapter)
      } else {
        console.error('Failed to load chapter:', response.status, response.statusText)
        const errorData = await response.json().catch(() => ({}))
        console.error('Error details:', errorData)
      }
    } catch (error) {
      console.error('Failed to load chapter:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const editChapter = async (chapter: Chapter) => {
    setEditMode(true)
    setSelectedChapter(chapter)
  }

  const deleteChapter = async (chapterNumber: number) => {
    if (confirm(`Are you sure you want to delete Chapter ${chapterNumber}?`)) {
      try {
        if (!projectId) {
          console.error('No project ID found')
          return
        }
        
        // Get authentication headers
        const authHeaders = await getAuthHeaders()
        
        const response = await fetch(`/api/chapters/${chapterNumber}?project_id=${encodeURIComponent(projectId)}`, {
          method: 'DELETE',
          headers: {
            'Content-Type': 'application/json',
            ...authHeaders
          }
        })
        
        if (response.ok) {
          onRefresh()
        } else {
          console.error('Failed to delete chapter:', response.status, response.statusText)
        }
      } catch (error) {
        console.error('Failed to delete chapter:', error)
      }
    }
  }

  const assessChapter = async (chapterNumber: number) => {
    setIsAssessing(chapterNumber)
    try {
      // Get authentication headers
      const authHeaders = await getAuthHeaders()
      
      const response = await fetch('/api/quality/assess', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders
        },
        body: JSON.stringify({
          chapterNumber
        })
      })
      
      if (response.ok) {
        const results = await response.json()
        setAssessmentResults(results)
      } else {
        console.error('Assessment failed:', response.status, response.statusText)
      }
    } catch (error) {
      console.error('Assessment failed:', error)
    } finally {
      setIsAssessing(null)
    }
  }

  const downloadChapter = async (chapter: Chapter) => {
    try {
      if (!projectId) {
        console.error('No project ID found')
        return
      }
      
      let content = chapter.content
      
      // If content not available in Firestore, fetch from API
      if (!content) {
        const authHeaders = await getAuthHeaders()
        
        const response = await fetch(`/api/chapters/${chapter.chapter_number}?project_id=${encodeURIComponent(projectId)}`, {
          headers: {
            'Content-Type': 'application/json',
            ...authHeaders
          }
        })
        
        if (response.ok) {
          const data = await response.json()
          content = data.content
        } else {
          console.error('Failed to download chapter:', response.status, response.statusText)
          return
        }
      }
      
      // Create and download the file
      const blob = new Blob([content], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `chapter-${chapter.chapter_number.toString().padStart(2, '0')}.md`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (error) {
      console.error('Failed to download chapter:', error)
    }
  }

  const getQualityBadge = (qualityScores?: any) => {
    const score = qualityScores?.overall_rating
    if (!score) return <span className="text-gray-400">No score</span>
    
    if (score >= 80) return <span className="px-2 py-1 text-xs bg-green-100 text-green-800 rounded-full">Excellent ({score})</span>
    if (score >= 70) return <span className="px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded-full">Good ({score})</span>
    if (score >= 60) return <span className="px-2 py-1 text-xs bg-yellow-100 text-yellow-800 rounded-full">Fair ({score})</span>
    return <span className="px-2 py-1 text-xs bg-red-100 text-red-800 rounded-full">Poor ({score})</span>
  }

  const formatDate = (timestamp: any) => {
    if (!timestamp) return 'Unknown'
    
    // Handle Firestore timestamp or regular date string
    let date: Date
    if (timestamp?.toDate) {
      date = timestamp.toDate()
    } else if (timestamp?.seconds) {
      date = new Date(timestamp.seconds * 1000)
    } else {
      date = new Date(timestamp)
    }
    
    return format(date, 'MMM dd, HH:mm')
  }

  return (
    <div className="card">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold text-gray-900">
          Generated Chapters ({chapters.length})
          {loading && (
            <span className="ml-2 text-sm text-blue-600">
              <div className="inline-block w-2 h-2 bg-blue-600 rounded-full animate-pulse"></div>
              Syncing...
            </span>
          )}
        </h2>
        <button
          onClick={onRefresh}
          className="btn-secondary"
          disabled={loading}
        >
          <ArrowPathIcon className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {chapters.length === 0 && !loading ? (
        <div className="text-center py-8">
          <DocumentTextIcon className="w-12 h-12 text-gray-400 mx-auto mb-4" />
          <p className="text-gray-500">No chapters generated yet</p>
          <p className="text-sm text-gray-400 mt-1">
            Use the form to generate your first chapter
          </p>
        </div>
      ) : loading && chapters.length === 0 ? (
        <div className="text-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mx-auto"></div>
          <p className="mt-4 text-sm text-gray-500">Loading chapters...</p>
        </div>
      ) : (
        <div className="space-y-3">
          {chapters.map((chapter) => (
            <div
              key={chapter.id}
              className="border rounded-lg p-4 hover:bg-gray-50 transition-colors"
            >
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <div className="flex items-center space-x-3">
                    <h3 className="font-medium text-gray-900">
                      Chapter {chapter.chapter_number}
                      {chapter.title && (
                        <span className="ml-2 text-sm text-gray-600">- {chapter.title}</span>
                      )}
                    </h3>
                    {getQualityBadge(chapter.quality_scores)}
                  </div>
                  
                  <div className="mt-2 grid grid-cols-2 gap-4 text-sm text-gray-600">
                    <div>
                      <span className="font-medium">Words:</span> {chapter.metadata?.word_count?.toLocaleString() || 'Unknown'}
                    </div>
                    <div>
                      <span className="font-medium">Stage:</span> {chapter.metadata?.stage || 'draft'}
                    </div>
                    <div>
                      <span className="font-medium">Time:</span> {chapter.metadata?.generation_time?.toFixed(1) || '0'}s
                    </div>
                    <div>
                      <span className="font-medium">Created:</span> {formatDate(chapter.metadata?.created_at)}
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
                    onClick={() => editChapter(chapter)}
                    className="p-2 text-gray-400 hover:text-green-600"
                    title="Edit chapter"
                  >
                    <PencilIcon className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => assessChapter(chapter.chapter_number)}
                    disabled={isAssessing === chapter.chapter_number}
                    className="p-2 text-gray-400 hover:text-blue-600 disabled:opacity-50"
                    title="Quality assessment"
                  >
                    {isAssessing === chapter.chapter_number ? (
                      <div className="w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
                    ) : (
                      <BeakerIcon className="w-4 h-4" />
                    )}
                  </button>
                  <button
                    onClick={() => deleteChapter(chapter.chapter_number)}
                    className="p-2 text-gray-400 hover:text-red-600"
                    title="Delete chapter"
                  >
                    <TrashIcon className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => downloadChapter(chapter)}
                    className="p-2 text-gray-400 hover:text-purple-600"
                    title="Download chapter"
                  >
                    <DocumentArrowDownIcon className="w-4 h-4" />
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
          <div className={`bg-white rounded-lg w-full max-h-[90vh] overflow-hidden ${editMode ? 'max-w-6xl' : 'max-w-4xl'}`}>
            <div className="px-6 py-4 border-b flex justify-between items-center">
              <div className="flex items-center space-x-4">
                <h3 className="text-lg font-semibold">
                  Chapter {selectedChapter.chapter_number}
                  {selectedChapter.title && (
                    <span className="ml-2 text-base font-normal text-gray-600">- {selectedChapter.title}</span>
                  )}
                </h3>
                {!editMode && (
                  <button
                    onClick={() => editChapter(selectedChapter)}
                    className="px-3 py-1 text-sm bg-green-100 text-green-700 rounded-md hover:bg-green-200 flex items-center space-x-1"
                  >
                    <PencilIcon className="w-4 h-4" />
                    <span>Edit</span>
                  </button>
                )}
                {editMode && (
                  <button
                    onClick={() => viewChapter(selectedChapter)}
                    className="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 flex items-center space-x-1"
                  >
                    <EyeIcon className="w-4 h-4" />
                    <span>View Only</span>
                  </button>
                )}
              </div>
              <button
                onClick={() => {
                  setSelectedChapter(null)
                  setEditMode(false)
                }}
                className="text-gray-400 hover:text-gray-600"
              >
                <span className="sr-only">Close</span>
                ✕
              </button>
            </div>
            <div className={`${editMode ? 'h-[80vh]' : 'p-6 overflow-y-auto max-h-[70vh]'}`}>
              {editMode ? (
                <ChapterEditor
                  chapterId={selectedChapter.id}
                  projectId={projectId || ''}
                  onSave={(updatedChapter) => {
                    // Refresh the chapter list and close modal
                    onRefresh()
                    setSelectedChapter(null)
                    setEditMode(false)
                  }}
                  onClose={() => {
                    setSelectedChapter(null)
                    setEditMode(false)
                  }}
                />
              ) : isLoading ? (
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