'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import { useAuthToken } from '@/lib/auth'
import { useProjectChapters, useProject } from '@/hooks/useFirestore'
import { Button } from '@/components/ui/button'
import { CollapsibleSidebar } from '@/components/layout/CollapsibleSidebar'
import ProjectLayout from '@/components/layout/ProjectLayout'
import { GlobalLoader } from '@/stores/useGlobalLoaderStore'
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
    GlobalLoader.show({
      title: `Generating Chapter ${currentChapter}`,
      stage: 'Crafting chapter...',
      showProgress: false,
      size: 'md',
      customMessages: [
        '🖋️ Weaving narrative threads...',
        '🎭 Developing character voices...',
        '📖 Building dramatic tension...',
        '✨ Polishing prose perfection...',
      ],
      timeoutMs: 900000,
    })
    setStatus('🔄 Generating chapter...')

    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetch('/api/v2/chapters/generate', {
        method: 'POST',
        headers: {
          ...authHeaders,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          project_id: projectId,
          chapter_number: currentChapter,
          target_word_count: 3800,
          stage: 'complete'
        })
      })

      if (response.ok) {
        const data = await response.json()
        setChapterContent(data.content)
        setOriginalContent(data.content)
        setIsEditing(true)
        setStatus('✅ Chapter generated successfully!')
        
        // Trigger credit balance refresh after successful generation
        window.dispatchEvent(new CustomEvent('refreshCreditBalance'))
      } else {
        const errorData = await response.json()
        setStatus(`❌ Generation failed: ${errorData.error || 'Unknown error'}`)
      }
    } catch (error) {
      console.error('Error generating chapter:', error)
      setStatus('❌ Error generating chapter')
    } finally {
      setIsGenerating(false)
      GlobalLoader.hide()
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
    GlobalLoader.show({
      title: `Rewriting Chapter ${currentChapter}`,
      stage: 'Reimagining...',
      showProgress: false,
      size: 'md',
      customMessages: [
        '🧠 Exploring alternatives...',
        '🧵 Improving continuity...',
        '✨ Sharpening prose...',
      ],
      timeoutMs: 900000,
    })
    setStatus('🔄 Rewriting chapter...')

    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetch('/api/v2/chapters/generate', {
        method: 'POST',
        headers: {
          ...authHeaders,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          project_id: projectId,
          chapter_number: currentChapter,
          target_word_count: 3800,
          stage: 'simple'
        })
      })

      if (response.ok) {
        const data = await response.json()
        if (data.content) {
          // Use the content directly from the response
          setChapterContent(data.content)
          setOriginalContent(data.content)
          setIsEditing(true)
          setStatus('✅ Chapter rewritten successfully!')
        } else {
          // Fallback: refresh from database
          setStatus('✅ Chapter rewritten successfully! Refreshing content...')
          await loadChapter(currentChapter)
          setStatus('✅ Chapter rewritten and refreshed!')
        }
      } else {
        const errorData = await response.json()
        setStatus(`❌ Rewrite failed: ${errorData.error || 'Unknown error'}`)
      }
    } catch (error) {
      console.error('Error rewriting chapter:', error)
      setStatus('❌ Error rewriting chapter')
    } finally {
      setIsGenerating(false)
      GlobalLoader.hide()
    }
  }

  const approveChapter = () => {
    setStatus('✅ Chapter approved! Ready for next chapter.')
    // Could implement actual approval logic here
  }

  const wordCount = (chapterContent || '').split(/\s+/).filter(word => word.length > 0).length

  return (
    <ProjectLayout 
      projectId={projectId} 
      projectTitle={project?.metadata?.title || `Project ${projectId}`}
    >
      <div className="relative bg-brand-off-white">
      {/* Beautiful Immersive Header */}
      <div className="relative bg-gradient-to-r from-brand-lavender via-brand-ink-blue to-brand-blush-orange">
        <div className="absolute inset-0">
          <div className="absolute top-1/4 left-1/4 w-2 h-2 bg-white/20 rounded-full animate-float"></div>
          <div className="absolute top-1/3 right-1/4 w-1 h-1 bg-white/30 rounded-full animate-float" style={{animationDelay: '2s'}}></div>
          <div className="absolute bottom-1/3 left-1/3 w-3 h-3 bg-white/10 rounded-full animate-float" style={{animationDelay: '4s'}}></div>
        </div>
        
        <div className="relative z-10 px-6 md:px-8 lg:px-12 py-6">
          <div className="flex items-center justify-between max-w-none">
            <div className="flex items-center space-x-4">
              <h1 className="text-2xl md:text-3xl font-black text-white drop-shadow-lg">
                Chapter {currentChapter}: {(project?.metadata?.title && project.metadata.title.trim()) || `Project ${project?.id || 'Unknown'}`}
              </h1>
              <div className="bg-white/20 backdrop-blur-sm px-3 py-1 rounded-full text-sm font-bold text-white">
                {wordCount.toLocaleString()} words
              </div>
            </div>
            
            <div className="flex items-center space-x-3">
              {/* Enhanced Chapter Navigation */}
              <div className="flex items-center space-x-2 bg-white/10 backdrop-blur-sm rounded-xl p-2">
                <button
                  onClick={() => setCurrentChapter(Math.max(1, currentChapter - 1))}
                  disabled={currentChapter <= 1}
                  className="bg-white/20 text-white px-3 py-1 rounded-lg font-semibold hover:bg-white/30 transition-colors disabled:opacity-50"
                >
                  ← Prev
                </button>
                
                <select
                  value={currentChapter}
                  onChange={(e) => setCurrentChapter(Number(e.target.value))}
                  className="bg-white/20 backdrop-blur-sm text-white px-3 py-1 rounded-lg font-semibold border border-white/20 focus:bg-white/30 transition-colors"
                  style={{ color: 'white' }}
                >
                  {Array.from({ length: project?.settings?.target_chapters || 25 }, (_, i) => (
                    <option key={i + 1} value={i + 1} style={{ color: 'black' }}>
                      Chapter {i + 1}
                    </option>
                  ))}
                </select>
                
                <button
                  onClick={() => setCurrentChapter(currentChapter + 1)}
                  disabled={currentChapter >= (project?.settings?.target_chapters || 25)}
                  className="bg-white/20 text-white px-3 py-1 rounded-lg font-semibold hover:bg-white/30 transition-colors disabled:opacity-50"
                >
                  Next →
                </button>
              </div>

              {/* Sidebar Toggle */}
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="bg-white/10 backdrop-blur-sm text-white p-2 rounded-lg hover:bg-white/20 transition-colors"
              >
                <Bars3Icon className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Enhanced Status Bar */}
      {status && (
        <div className="bg-gradient-to-r from-blue-50 to-brand-lavender/10 border-b border-blue-200 px-6 md:px-8 lg:px-12 py-3">
          <div className="text-sm font-semibold text-blue-800">{status}</div>
        </div>
      )}

      {/* Main Content Area */}
      <div className="relative">
        {/* Enhanced Generate Chapter Button */}
        {!isEditing && !chapterContent && (
          <div className="flex items-center justify-center py-24">
            <div className="text-center max-w-lg">
              <div className="mb-8">
                <div className="w-24 h-24 mx-auto bg-gradient-to-br from-brand-lavender to-brand-forest rounded-full flex items-center justify-center mb-6 shadow-xl">
                  <DocumentPlusIcon className="w-12 h-12 text-white" />
                </div>
              </div>
              <h2 className="text-3xl font-black text-brand-forest mb-4">
                Ready to Write Chapter {currentChapter}?
              </h2>
              <p className="text-brand-forest/70 mb-8 font-medium">
                Let AI help you craft the next part of your story. Every great chapter starts with a single word.
              </p>
              <button
                onClick={generateChapter}
                disabled={isGenerating}
                className="bg-gradient-to-r from-brand-forest to-brand-lavender text-white px-10 py-4 rounded-2xl text-lg font-bold hover:shadow-2xl hover:scale-105 transition-all duration-300 shadow-xl"
              >
                {isGenerating ? (
                  <>
                    <ArrowPathIcon className="w-6 h-6 mr-3 animate-spin inline" />
                    Generating Chapter {currentChapter}...
                  </>
                ) : (
                  <>
                    <DocumentPlusIcon className="w-6 h-6 mr-3 inline" />
                    Generate Chapter {currentChapter}
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {/* Beautiful Inline Editor */}
        {(isEditing || chapterContent) && (
          <div className="px-6 md:px-8 lg:px-12 py-8">
            <div className="max-w-4xl mx-auto">
              <div className="bg-gradient-to-br from-white/80 via-brand-beige/20 to-white/60 rounded-2xl p-8 backdrop-blur-sm border border-white/50 shadow-2xl">
                <textarea
                  value={chapterContent}
                  onChange={(e) => setChapterContent(e.target.value)}
                  className="w-full min-h-screen bg-transparent text-brand-forest placeholder-brand-forest/40 border-none resize-none focus:outline-none text-lg leading-relaxed font-medium"
                  style={{
                    minHeight: 'calc(100vh - 300px)'
                  }}
                  placeholder="Start writing your chapter here... Let your creativity flow."
                />
              </div>
            </div>
          </div>
        )}

        {/* Enhanced Floating Bottom Action Bar */}
        {(isEditing || chapterContent) && (
          <div className="fixed bottom-0 left-0 right-0 bg-gradient-to-r from-white/95 via-brand-beige/20 to-white/95 backdrop-blur-lg border-t border-white/50 p-4 shadow-2xl">
            <div className="max-w-4xl mx-auto flex items-center justify-between">
              <div className="flex items-center space-x-4 text-sm text-brand-forest/80 font-semibold">
                {hasUnsavedChanges && (
                  <div className="flex items-center space-x-2 bg-orange-50 px-3 py-1 rounded-full border border-orange-200">
                    <div className="w-2 h-2 bg-orange-500 rounded-full animate-pulse"></div>
                    <span className="text-orange-700 font-bold">Unsaved changes</span>
                  </div>
                )}
                <div className="bg-brand-lavender/10 px-3 py-1 rounded-full border border-brand-lavender/20">
                  <span className="text-brand-forest font-bold">{wordCount.toLocaleString()} words</span>
                </div>
              </div>

              <div className="flex items-center space-x-3">
                <button
                  onClick={saveChapter}
                  disabled={!hasUnsavedChanges || isSaving}
                  className="bg-gradient-to-r from-emerald-500 to-emerald-600 text-white px-6 py-2 rounded-xl font-bold hover:shadow-lg transition-all hover:scale-105 disabled:opacity-50 disabled:hover:scale-100"
                >
                  {isSaving ? (
                    <>
                      <ArrowPathIcon className="w-4 h-4 mr-2 animate-spin inline" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <BookmarkIcon className="w-4 h-4 mr-2 inline" />
                      Save
                    </>
                  )}
                </button>

                <button
                  onClick={rewriteChapter}
                  disabled={isGenerating}
                  className="bg-gradient-to-r from-blue-500 to-blue-600 text-white px-6 py-2 rounded-xl font-bold hover:shadow-lg transition-all hover:scale-105 disabled:opacity-50"
                >
                  {isGenerating ? (
                    <>
                      <ArrowPathIcon className="w-4 h-4 mr-2 animate-spin inline" />
                      Rewriting...
                    </>
                  ) : (
                    <>
                      <ArrowPathIcon className="w-4 h-4 mr-2 inline" />
                      Rewrite
                    </>
                  )}
                </button>

                <button
                  onClick={approveChapter}
                  className="bg-gradient-to-r from-brand-forest to-brand-lavender text-white px-6 py-2 rounded-xl font-bold hover:shadow-lg transition-all hover:scale-105"
                >
                  <CheckCircleIcon className="w-4 h-4 mr-2 inline" />
                  Approve Chapter
                </button>
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
    </ProjectLayout>
  )
} 