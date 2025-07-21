'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import { useAuthToken } from '@/lib/auth'
import { useProjectChapters, useProject } from '@/hooks/useFirestore'
import { Button } from '@/components/ui/button'
import { CollapsibleSidebar } from '@/components/layout/CollapsibleSidebar'
import { 
  PencilIcon, 
  DocumentPlusIcon, 
  BookmarkIcon,
  Bars3Icon,
  ArrowPathIcon,
  CheckCircleIcon
} from '@heroicons/react/24/outline'

interface Chapter {
  id: string
  chapter_number: number
  content?: string
  metadata?: {
    word_count?: number
    status?: string
  }
}

export default function ChapterWritingPage() {
  const params = useParams()
  const projectId = params.projectId as string
  const { getAuthHeaders, isSignedIn } = useAuthToken()
  
  const [currentChapter, setCurrentChapter] = useState<number>(1)
  const [chapterContent, setChapterContent] = useState('')
  const [originalContent, setOriginalContent] = useState('')
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [status, setStatus] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [isEditing, setIsEditing] = useState(false)

  // Real-time Firestore hooks
  const { chapters, loading: chaptersLoading } = useProjectChapters(projectId)
  const { project } = useProject(projectId)

  useEffect(() => {
    loadChapter(currentChapter)
  }, [currentChapter, chapters])

  useEffect(() => {
    // Track changes
    setHasUnsavedChanges(chapterContent !== originalContent)
  }, [chapterContent, originalContent])

  const loadChapter = async (chapterNumber: number) => {
    // First check if chapter exists in Firestore data
    const existingChapter = chapters.find(ch => ch.chapter_number === chapterNumber)
    if (existingChapter?.content) {
      setChapterContent(existingChapter.content)
      setOriginalContent(existingChapter.content)
      setIsEditing(true)
      return
    }

    // If not in Firestore, try loading from API
    if (!isSignedIn || !projectId) return

    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetch(`/api/chapters/${chapterNumber}?project_id=${projectId}`, {
        headers: authHeaders
      })

      if (response.ok) {
        const data = await response.json()
        setChapterContent(data.content || '')
        setOriginalContent(data.content || '')
        setIsEditing(!!data.content)
      } else {
        // Chapter doesn't exist yet
        setChapterContent('')
        setOriginalContent('')
        setIsEditing(false)
      }
    } catch (error) {
      console.error('Error loading chapter:', error)
      setStatus('❌ Error loading chapter')
    }
  }

  const generateChapter = async () => {
    if (!isSignedIn || !projectId) return

    setIsGenerating(true)
    setStatus('🔄 Generating chapter...')

    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetch('/api/chapters/generate', {
        method: 'POST',
        headers: {
          ...authHeaders,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          project_id: projectId,
          chapter_number: currentChapter,
          words: 3800,
          stage: 'complete'
        })
      })

      if (response.ok) {
        const data = await response.json()
        setChapterContent(data.content)
        setOriginalContent(data.content)
        setIsEditing(true)
        setStatus('✅ Chapter generated successfully!')
      } else {
        const errorData = await response.json()
        setStatus(`❌ Generation failed: ${errorData.error || 'Unknown error'}`)
      }
    } catch (error) {
      console.error('Error generating chapter:', error)
      setStatus('❌ Error generating chapter')
    } finally {
      setIsGenerating(false)
    }
  }

  const saveChapter = async () => {
    if (!isSignedIn || !projectId || !chapterContent.trim()) return

    setIsSaving(true)
    setStatus('💾 Saving chapter...')

    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetch(`/api/chapters/${currentChapter}?project_id=${projectId}`, {
        method: 'PUT',
        headers: {
          ...authHeaders,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          content: chapterContent
        })
      })

      if (response.ok) {
        setOriginalContent(chapterContent)
        setStatus('✅ Chapter saved successfully!')
      } else {
        setStatus('❌ Failed to save chapter')
      }
    } catch (error) {
      console.error('Error saving chapter:', error)
      setStatus('❌ Error saving chapter')
    } finally {
      setIsSaving(false)
    }
  }

  const rewriteChapter = async () => {
    if (!isSignedIn || !projectId) return

    setIsGenerating(true)
    setStatus('🔄 Rewriting chapter...')

    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetch('/api/chapters/generate', {
        method: 'POST',
        headers: {
          ...authHeaders,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          project_id: projectId,
          chapter_number: currentChapter,
          words: 3800,
          stage: 'complete',
          existing_content: chapterContent
        })
      })

      if (response.ok) {
        const data = await response.json()
        setChapterContent(data.content)
        setStatus('✅ Chapter rewritten successfully!')
      } else {
        const errorData = await response.json()
        setStatus(`❌ Rewrite failed: ${errorData.error || 'Unknown error'}`)
      }
    } catch (error) {
      console.error('Error rewriting chapter:', error)
      setStatus('❌ Error rewriting chapter')
    } finally {
      setIsGenerating(false)
    }
  }

  const approveChapter = () => {
    setStatus('✅ Chapter approved! Ready for next chapter.')
    // Could implement actual approval logic here
  }

  const wordCount = chapterContent.split(/\s+/).filter(word => word.length > 0).length

  return (
    <div className="min-h-screen bg-clean focus-mode">
      {/* Minimal Top Bar */}
      <div className="sticky top-0 z-30 bg-white border-b border-gray-200 px-6 py-3">
        <div className="flex items-center justify-between max-w-none">
          <div className="flex items-center space-x-4">
            <h1 className="text-xl font-semibold text-gray-900">
              Chapter {currentChapter}: {project?.metadata?.title || 'Untitled'}
            </h1>
            <div className="text-sm text-gray-500">
              {wordCount.toLocaleString()} words
            </div>
          </div>
          
          <div className="flex items-center space-x-3">
            {/* Chapter Navigation */}
            <div className="flex items-center space-x-2">
              <Button
                onClick={() => setCurrentChapter(Math.max(1, currentChapter - 1))}
                variant="outline"
                size="sm"
                disabled={currentChapter <= 1}
              >
                ← Prev
              </Button>
              
              <select
                value={currentChapter}
                onChange={(e) => setCurrentChapter(Number(e.target.value))}
                className="px-3 py-1 border border-gray-300 rounded text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                {Array.from({ length: project?.settings?.target_chapters || 25 }, (_, i) => (
                  <option key={i + 1} value={i + 1}>
                    Chapter {i + 1}
                  </option>
                ))}
              </select>
              
              <Button
                onClick={() => setCurrentChapter(currentChapter + 1)}
                variant="outline"
                size="sm"
                disabled={currentChapter >= (project?.settings?.target_chapters || 25)}
              >
                Next →
              </Button>
            </div>

            {/* Sidebar Toggle */}
            <Button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              variant="ghost"
              size="sm"
              className="p-2"
            >
              <Bars3Icon className="w-5 h-5" />
            </Button>
          </div>
        </div>
      </div>

      {/* Status Bar */}
      {status && (
        <div className="bg-blue-50 border-b border-blue-200 px-6 py-2">
          <div className="text-sm text-blue-800">{status}</div>
        </div>
      )}

      {/* Main Content Area */}
      <div className="relative">
        {/* Generate Chapter Button (when no content) */}
        {!isEditing && !chapterContent && (
          <div className="flex items-center justify-center pt-24">
            <Button
              onClick={generateChapter}
              disabled={isGenerating}
              className="bg-blue-600 hover:bg-blue-700 text-white px-8 py-4 text-lg"
              size="lg"
            >
              {isGenerating ? (
                <>
                  <ArrowPathIcon className="w-5 h-5 mr-2 animate-spin" />
                  Generating Chapter {currentChapter}...
                </>
              ) : (
                <>
                  <DocumentPlusIcon className="w-5 h-5 mr-2" />
                  Generate Chapter {currentChapter}
                </>
              )}
            </Button>
          </div>
        )}

        {/* Full-Width Inline Editor */}
        {(isEditing || chapterContent) && (
          <div className="px-6 py-8">
            <div className="prose-clean">
              <textarea
                value={chapterContent}
                onChange={(e) => setChapterContent(e.target.value)}
                className="w-full min-h-screen p-8 border-none resize-none clean-editor"
                style={{
                  minHeight: 'calc(100vh - 200px)'
                }}
                placeholder="Start writing your chapter here..."
              />
            </div>
          </div>
        )}

        {/* Floating Bottom Action Bar */}
        {(isEditing || chapterContent) && (
          <div className="floating-bottom bg-white border-t border-gray-200 p-4">
            <div className="max-w-4xl mx-auto flex items-center justify-between">
              <div className="flex items-center space-x-2 text-sm text-gray-600">
                {hasUnsavedChanges && (
                  <div className="flex items-center space-x-1">
                    <div className="w-2 h-2 bg-orange-500 rounded-full"></div>
                    <span>Unsaved changes</span>
                  </div>
                )}
                <span>{wordCount.toLocaleString()} words</span>
              </div>

              <div className="flex items-center space-x-3">
                <Button
                  onClick={saveChapter}
                  disabled={!hasUnsavedChanges || isSaving}
                  variant="outline"
                  size="sm"
                >
                  {isSaving ? (
                    <>
                      <ArrowPathIcon className="w-4 h-4 mr-1 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <BookmarkIcon className="w-4 h-4 mr-1" />
                      Save
                    </>
                  )}
                </Button>

                <Button
                  onClick={rewriteChapter}
                  disabled={isGenerating}
                  variant="outline"
                  size="sm"
                >
                  {isGenerating ? (
                    <>
                      <ArrowPathIcon className="w-4 h-4 mr-1 animate-spin" />
                      Rewriting...
                    </>
                  ) : (
                    <>
                      <ArrowPathIcon className="w-4 h-4 mr-1" />
                      Rewrite
                    </>
                  )}
                </Button>

                <Button
                  onClick={approveChapter}
                  className="bg-green-600 hover:bg-green-700 text-white"
                  size="sm"
                >
                  <CheckCircleIcon className="w-4 h-4 mr-1" />
                  Approve Chapter
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Collapsible Sidebar */}
      <CollapsibleSidebar 
        isOpen={sidebarOpen} 
        onToggle={() => setSidebarOpen(!sidebarOpen)} 
      />
    </div>
  )
} 