'use client'

import React, { useState, useEffect, useRef, startTransition } from 'react'
import { useUser } from '@clerk/nextjs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { toast } from '@/components/ui/use-toast'
import { useAutoSave, useSessionRecovery, SessionRecoveryPrompt } from '@/hooks/useAutoSave'
import { getOfflineManager } from '@/lib/firestore-offline'

interface Chapter {
  id: string
  project_id: string
  chapter_number: number
  title?: string
  content: string
  metadata: {
    word_count: number
    target_word_count: number
    stage: 'draft' | 'revision' | 'complete'
    created_at: string
    updated_at: string
  }
  quality_scores?: {
    overall_rating: number
    prose: number
    character: number
    story: number
    emotion: number
    freshness: number
  }
  director_notes: Array<{
    note_id: string
    content: string
    created_by: string
    created_at: string
    resolved: boolean
    position?: number
  }>
}

interface DirectorNote {
  content: string
  position?: number
}

interface ChapterEditorProps {
  chapterId: string
  projectId: string
  onSave?: (chapter: Chapter) => void
  onClose?: () => void
}

const ChapterEditor: React.FC<ChapterEditorProps> = ({ 
  chapterId, 
  projectId, 
  onSave, 
  onClose 
}) => {
  const { user, isLoaded } = useUser()
  const [chapter, setChapter] = useState<Chapter | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [isRewriting, setIsRewriting] = useState(false)
  
  // Editor state
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [stage, setStage] = useState<'draft' | 'revision' | 'complete'>('draft')
  
  // Director's notes state
  const [showNotesPanel, setShowNotesPanel] = useState(false)
  const [newNote, setNewNote] = useState('')
  const [selectedText, setSelectedText] = useState('')
  const [selectedPosition, setSelectedPosition] = useState<number | undefined>()
  
  // Reference files state
  const [showReferencePanel, setShowReferencePanel] = useState(false)
  const [referenceFiles, setReferenceFiles] = useState<any[]>([])
  const [isLoadingReferences, setIsLoadingReferences] = useState(false)
  
  const contentRef = useRef<HTMLTextAreaElement>(null)

  // Auto-save data structure
  const chapterData = {
    title,
    content,
    stage,
    chapterId,
    projectId
  }

  // Auto-save function for the hook
  const autoSaveFunction = async (data: typeof chapterData) => {
    if (!user || !chapter) return
    
    try {
      // Use offline manager for intelligent online/offline handling
              await getOfflineManager().updateDocument(
        `projects/${data.projectId}/chapters`,
        data.chapterId,
        {
          title: data.title,
          content: data.content,
          stage: data.stage,
          metadata: {
            ...chapter.metadata,
            updated_at: new Date().toISOString(),
            word_count: data.content.split(/\s+/).filter(word => word.length > 0).length
          }
        }
      )
    } catch (error) {
      console.error('Auto-save error:', error)
      throw error
    }
  }

  // Set up auto-save hook
  const autoSave = useAutoSave(chapterData, autoSaveFunction, {
    key: `chapter_${chapterId}`,
    interval: 30000, // Save every 30 seconds
    debounceDelay: 2000, // Wait 2 seconds after typing stops
    enableLocalStorage: true,
    enableFirestore: true
  })

  // Set up session recovery
  const sessionRecovery = useSessionRecovery(
    `chapter_${chapterId}`,
    chapterData,
    (recoveredData) => {
      // Batch state updates to prevent multiple re-renders
      startTransition(() => {
        setTitle(recoveredData.title)
        setContent(recoveredData.content)
        setStage(recoveredData.stage)
      })
    }
  )

  useEffect(() => {
    if (isLoaded && chapterId) {
      loadChapter()
      loadReferenceFiles()
    }
  }, [isLoaded, chapterId])

  const loadReferenceFiles = async () => {
    if (!user) return
    
    try {
      setIsLoadingReferences(true)
              const response = await fetch(`/api/v2/projects/${projectId}/references`)

      if (response.ok) {
        const data = await response.json()
        setReferenceFiles(data.files || [])
      } else {
        console.warn('Failed to load reference files')
      }
    } catch (error) {
      console.error('Error loading reference files:', error)
    } finally {
      setIsLoadingReferences(false)
    }
  }

  const loadChapter = async () => {
    if (!user) return
    
    try {
      setIsLoading(true)
      const response = await fetch(`/api/chapters/${chapterId}?project_id=${encodeURIComponent(projectId)}`, {
        headers: {}
      })

      if (response.ok) {
        const data = await response.json()
        const chapterData = data.chapter ?? data
        
        // Batch all state updates to prevent multiple re-renders
        startTransition(() => {
          setChapter(chapterData)
          setTitle(chapterData.title || `Chapter ${chapterData.chapter_number}`)
          setContent(chapterData.content)
          setStage(chapterData.metadata.stage)
        })
      } else {
        throw new Error('Failed to load chapter')
      }
    } catch (error) {
      console.error('Error loading chapter:', error)
      toast({
        title: "Looks like we hit a snag",
        description: "We're having trouble loading your chapter. Let's try again!",
        variant: "destructive"
      })
    } finally {
      setIsLoading(false)
    }
  }

  const saveChapter = async () => {
    if (!user || !chapter) return

    try {
      setIsSaving(true)
      const response = await fetch(`/api/chapters/${chapterId}?project_id=${encodeURIComponent(projectId)}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          title,
          content,
          stage
        })
      })

      if (response.ok) {
        const data = await response.json()
        toast({
          title: "Beautiful work! ✨",
          description: "Your chapter has been saved. Keep blooming!"
        })
        
        // Reload the chapter to get updated data
        await loadChapter()
        
        if (onSave && chapter) {
          onSave({ ...chapter, title, content, metadata: { ...chapter.metadata, stage } })
        }
      } else {
        throw new Error('Failed to save chapter')
      }
    } catch (error) {
      console.error('Error saving chapter:', error)
      toast({
        title: "Looks like we hit a snag",
        description: "We couldn't save your chapter right now. Let's try again!",
        variant: "destructive"
      })
    } finally {
      setIsSaving(false)
    }
  }

  const approveChapter = async () => {
    await saveChapter()
    setStage('complete')
    toast({
      title: "Chapter Approved",
      description: "Chapter has been marked as complete."
    })
  }

  const requestRewrite = async () => {
    try {
      setIsRewriting(true)
      
      // In production, this would call the backend to regenerate the chapter
      toast({
        title: "Rewrite Requested",
        description: "Chapter rewrite has been queued. This may take a few minutes."
      })
      
      // Mock rewrite process
      setTimeout(async () => {
        const rewrittenContent = content + "\n\n[REWRITTEN SECTION]\nThis section has been rewritten based on feedback and quality improvement suggestions. The new content maintains story continuity while addressing identified issues."
        
        // Batch state updates to prevent multiple re-renders
        startTransition(() => {
          setContent(rewrittenContent)
          setStage('revision')
        })
        setIsRewriting(false)
        
        toast({
          title: "Rewrite Complete",
          description: "Chapter has been rewritten. Please review the changes."
        })
      }, 3000)
      
    } catch (error) {
      console.error('Error requesting rewrite:', error)
      toast({
        title: "Looks like we hit a snag",
        description: "We couldn't start the rewrite just now. Let's try again!",
        variant: "destructive"
      })
      setIsRewriting(false)
    }
  }

  const handleTextSelection = () => {
    if (contentRef.current) {
      const start = contentRef.current.selectionStart
      const end = contentRef.current.selectionEnd
      
      if (start !== end) {
        const selected = content.substring(start, end)
        setSelectedText(selected)
        setSelectedPosition(start)
        setShowNotesPanel(true)
      }
    }
  }

  const addDirectorNote = async () => {
    if (!user || !newNote.trim()) return

    try {
      const response = await fetch(`/api/chapters/${chapterId}?project_id=${encodeURIComponent(projectId)}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          director_notes: [{
            content: newNote,
            position: selectedPosition
          }]
        })
      })

      if (response.ok) {
        // Batch state updates to prevent multiple re-renders
        startTransition(() => {
          setNewNote('')
          setSelectedText('')
        })
        setSelectedPosition(undefined)
        await loadChapter() // Reload to get updated notes
        
        toast({
          title: "Note Added",
          description: "Director's note has been added successfully."
        })
      } else {
        throw new Error('Failed to add note')
      }
    } catch (error) {
      console.error('Error adding director note:', error)
      toast({
        title: "Looks like we hit a snag",
        description: "We couldn't save your note right now. Let's try again!",
        variant: "destructive"
      })
    }
  }

  const resolveNote = async (noteId: string) => {
    // In production, this would call an API to mark the note as resolved
    toast({
      title: "Note Resolved",
      description: "Director's note has been marked as resolved."
    })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-pulse text-gray-500">Loading chapter...</div>
      </div>
    )
  }

  if (!chapter) {
    return (
      <div className="text-center text-gray-500 p-8">
        Chapter not found
      </div>
    )
  }

  return (
    <div className="max-w-7xl mx-auto p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold">Chapter Editor</h1>
          <p className="text-gray-600">
            Chapter {chapter.chapter_number} • {chapter.metadata.word_count} words • {stage}
          </p>
        </div>
        <div className="flex space-x-2">
          {onClose && (
            <Button variant="outline" onClick={onClose}>
              Close
            </Button>
          )}
          <Button 
            variant="outline" 
            onClick={() => setShowNotesPanel(!showNotesPanel)}
          >
            {showNotesPanel ? 'Hide Notes' : 'Show Notes'} ({chapter.director_notes.length})
          </Button>
          <Button
            variant="outline"
            onClick={() => setShowReferencePanel(!showReferencePanel)}
          >
            {showReferencePanel ? 'Hide References' : 'Show References'} ({referenceFiles.length})
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Editor */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Chapter Content</CardTitle>
                <div className="flex space-x-2">
                  {/* Auto-save status indicator */}
                  <div className="flex items-center text-sm text-gray-500">
                    {autoSave.isSaving ? (
                      <span>Auto-saving...</span>
                    ) : autoSave.lastSaved ? (
                      <span>Last saved: {autoSave.lastSaved.toLocaleTimeString()}</span>
                    ) : autoSave.hasUnsavedChanges ? (
                      <span className="text-orange-600">Unsaved changes</span>
                    ) : (
                      <span>All changes saved</span>
                    )}
                  </div>
                  <Button
                    variant="outline"
                    onClick={requestRewrite}
                    disabled={isRewriting}
                  >
                    {isRewriting ? 'Rewriting...' : 'Request Rewrite'}
                  </Button>
                  <Button
                    variant="outline"
                    onClick={autoSave.manualSave}
                    disabled={autoSave.isSaving}
                  >
                    {autoSave.isSaving ? 'Saving...' : 'Save Now'}
                  </Button>
                  <Button
                    onClick={approveChapter}
                    disabled={autoSave.isSaving}
                    className="bg-green-600 hover:bg-green-700"
                  >
                    Approve Chapter
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Title */}
              <div className="space-y-2">
                <Label htmlFor="title">Title</Label>
                <Input
                  id="title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder={`Chapter ${chapter.chapter_number}`}
                />
              </div>

              {/* Stage */}
              <div className="space-y-2">
                <Label htmlFor="stage">Stage</Label>
                <select
                  id="stage"
                  value={stage}
                  onChange={(e) => setStage(e.target.value as 'draft' | 'revision' | 'complete')}
                  className="w-full p-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="draft">Draft</option>
                  <option value="revision">Revision</option>
                  <option value="complete">Complete</option>
                </select>
              </div>

              {/* Content */}
              <div className="space-y-2">
                <Label htmlFor="content">Content</Label>
                <Textarea
                  ref={contentRef}
                  id="content"
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  onMouseUp={handleTextSelection}
                  onKeyUp={handleTextSelection}
                  placeholder="Chapter content..."
                  rows={25}
                  className="font-mono text-sm leading-relaxed"
                />
                <div className="text-sm text-gray-500">
                  {content.split(' ').length} words • Target: {chapter.metadata.target_word_count} words
                </div>
              </div>

              {/* Quality Scores */}
              {chapter.quality_scores && (
                <div className="border-t pt-4">
                  <h4 className="font-semibold mb-3">Quality Scores</h4>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
                    <div>Overall: {chapter.quality_scores.overall_rating}/10</div>
                    <div>Prose: {chapter.quality_scores.prose}/10</div>
                    <div>Character: {chapter.quality_scores.character}/10</div>
                    <div>Story: {chapter.quality_scores.story}/10</div>
                    <div>Emotion: {chapter.quality_scores.emotion}/10</div>
                    <div>Freshness: {chapter.quality_scores.freshness}/10</div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Director's Notes Panel */}
        {showNotesPanel && (
          <div className="lg:col-span-1">
            <Card>
              <CardHeader>
                <CardTitle>Director's Notes</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Add New Note */}
                <div className="border-b pb-4">
                  <Label htmlFor="new-note">Add Note</Label>
                  {selectedText && (
                    <div className="text-xs text-gray-500 mb-2">
                      Selected: "{selectedText.substring(0, 50)}..."
                    </div>
                  )}
                  <Textarea
                    id="new-note"
                    value={newNote}
                    onChange={(e) => setNewNote(e.target.value)}
                    placeholder="Add feedback, suggestions, or revision notes..."
                    rows={3}
                    className="mb-2"
                  />
                  <Button
                    onClick={addDirectorNote}
                    disabled={!newNote.trim()}
                    size="sm"
                    className="w-full"
                  >
                    Add Note
                  </Button>
                </div>

                {/* Existing Notes */}
                <div className="space-y-3">
                  {chapter.director_notes.length === 0 ? (
                    <p className="text-gray-500 text-sm">No notes yet</p>
                  ) : (
                    chapter.director_notes.map((note) => (
                      <div
                        key={note.note_id}
                        className={`p-3 rounded-lg border ${
                          note.resolved ? 'bg-green-50 border-green-200' : 'bg-yellow-50 border-yellow-200'
                        }`}
                      >
                        <div className="text-sm mb-2">{note.content}</div>
                        <div className="flex items-center justify-between text-xs text-gray-500">
                          <span>
                            {new Date(note.created_at).toLocaleDateString()}
                            {note.position !== undefined && ` • Position ${note.position}`}
                          </span>
                          {!note.resolved && (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => resolveNote(note.note_id)}
                              className="h-6 px-2 text-xs"
                            >
                              Resolve
                            </Button>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Reference Files Panel */}
        {showReferencePanel && (
          <div className="lg:col-span-1">
            <Card>
              <CardHeader>
                <CardTitle>Reference Files</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {isLoadingReferences ? (
                  <div className="text-center text-gray-500">Loading references...</div>
                ) : referenceFiles.length === 0 ? (
                  <div className="text-center text-gray-500">No reference files found</div>
                ) : (
                  <div className="space-y-3">
                    {referenceFiles.map((file: any, index: number) => (
                      <div key={index} className="border-b pb-3">
                        <div className="flex items-center justify-between mb-2">
                          <h4 className="font-medium text-sm">{file.name}</h4>
                          <span className="text-xs text-gray-500">
                            {Math.round(file.size / 1024)}KB
                          </span>
                        </div>
                        {file.preview && (
                          <div className="text-xs text-gray-600 bg-gray-50 p-2 rounded max-h-20 overflow-y-auto">
                            {file.preview.substring(0, 200)}
                            {file.preview.length > 200 && '...'}
                          </div>
                        )}
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => window.open(`/api/v2/projects/${projectId}/references/${file.name}`, '_blank')}
                          className="mt-2 h-6 px-2 text-xs"
                        >
                          View Full
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}
      </div>

      {/* Session Recovery Prompt */}
      <SessionRecoveryPrompt
        isOpen={sessionRecovery.hasRecoverableData}
        onAccept={sessionRecovery.acceptRecovery}
        onReject={sessionRecovery.rejectRecovery}
        dataPreview={sessionRecovery.recoveredData?.content?.substring(0, 100)}
      />
    </div>
  )
}

export default ChapterEditor 