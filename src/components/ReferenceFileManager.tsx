'use client'

import { useState, useEffect } from 'react'
import { useAuthToken } from '@/lib/auth'
import { DocumentTextIcon, PencilIcon, EyeIcon, CheckCircleIcon, SparklesIcon, ArrowPathIcon } from '@heroicons/react/24/outline'
import { GlobalLoader } from '@/stores/useGlobalLoaderStore'

interface ReferenceFile {
  name: string
  content: string
  lastModified: string
}

interface GenerationStatus {
  isGenerating: boolean
  currentFile?: string
  message?: string
}

interface ReferenceFileManagerProps {
  projectId?: string | null
}

export function ReferenceFileManager({ projectId: propProjectId }: ReferenceFileManagerProps = {}) {
  const { getAuthHeaders, isLoaded, isSignedIn } = useAuthToken()
  const [files, setFiles] = useState<ReferenceFile[]>([])
  const [selectedFile, setSelectedFile] = useState<ReferenceFile | null>(null)
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [status, setStatus] = useState('')
  const [generationStatus, setGenerationStatus] = useState<GenerationStatus>({ isGenerating: false })

  useEffect(() => {
    // Only fetch if user is authenticated
    if (isLoaded && isSignedIn) {
      fetchReferenceFiles()
    }
  }, [isLoaded, isSignedIn])

  const getProjectId = () => {
    // Use prop first, then fall back to localStorage
    if (propProjectId) return propProjectId
    if (typeof window === 'undefined') return null
    return localStorage.getItem('lastProjectId')
  }

  const fetchReferenceFiles = async () => {
    if (!isSignedIn) return
    
    setIsLoading(true)
    try {
      const projectId = getProjectId()
      if (!projectId) {
        setFiles([])
        setStatus('⚠️ No project selected - upload or select a Book Bible first')
        setIsLoading(false)
        return
      }
      const authHeaders = await getAuthHeaders()
      const response = await fetch(`/api/v2/projects/${projectId}/references`, {
        headers: authHeaders
      })
      if (response.ok) {
        const data = await response.json()
        const files = data.references ?? data.files
        if (data.success && files) {
          const fileDetails = await Promise.all(
            files.map(async (fileInfo: any) => {
              try {
                const fileResponse = await fetch(`/api/v2/projects/${projectId}/references/${fileInfo.name}`, {
                  headers: authHeaders
                })
                if (fileResponse.ok) {
                  const fileData = await fileResponse.json()
                  return {
                    name: fileData.name,
                    content: fileData.content,
                    lastModified: fileData.lastModified
                  }
                } else if (fileResponse.status === 404) {
                  console.log(`Reference file ${fileInfo.name} not found (still generating)`)
                  return {
                    name: fileInfo.name,
                    content: '⏳ This reference file is being generated in the background...\n\nPlease wait a few minutes and refresh the page.',
                    lastModified: new Date().toISOString(),
                    isGenerating: true
                  }
                }
              } catch (error) {
                console.error(`Failed to load ${fileInfo.name}:`, error)
              }
              return null
            })
          )
          
          setFiles(fileDetails.filter(Boolean) as ReferenceFile[])
          setStatus('')
        } else {
          setFiles([])
          const message = data.message || 'No reference files found'
          if (message.includes('not found') || message.includes('No reference files')) {
            setStatus('📝 Reference files are being generated in the background. Click "Generate References" or wait a few minutes and refresh.')
          } else {
            setStatus('⚠️ ' + message)
          }
        }
      } else if (response.status === 404) {
        setFiles([])
        setStatus('📝 Reference files are being generated in the background. Please wait a few minutes and try again.')
      } else {
        setFiles([])
        setStatus('❌ Failed to load reference files')
      }
    } catch (error) {
      console.error('Error loading reference files:', error)
      setFiles([])
      setStatus('❌ Error loading reference files')
    } finally {
      setIsLoading(false)
    }
  }

  const handleFileSelect = async (fileName: string) => {
    if (!isSignedIn) return
    
    const projectId = getProjectId()
    if (!projectId) return

    try {
      const authHeaders = await getAuthHeaders()
          const response = await fetch(`/api/v2/projects/${projectId}/references/${fileName}`, {
      headers: authHeaders
    })
      
      if (response.ok) {
        const fileData = await response.json()
        setSelectedFile({
          name: fileData.name,
          content: fileData.content,
          lastModified: fileData.lastModified
        })
        setEditContent(fileData.content)
        setIsEditing(false)
        setStatus('')
      } else {
        setStatus('❌ Failed to load file content')
      }
    } catch (error) {
      console.error('Error loading file:', error)
      setStatus('❌ Error loading file')
    }
  }

  const handleSave = async () => {
    if (!selectedFile || !isSignedIn) return

    const projectId = getProjectId()
    if (!projectId) return

    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetch(`/api/v2/projects/${projectId}/references/${selectedFile.name}`, {
        method: 'PUT',
        headers: {
          ...authHeaders,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ content: editContent })
      })

      if (response.ok) {
        const updatedFile = await response.json()
        setSelectedFile(prev => prev ? {
          ...prev,
          content: editContent,
          lastModified: updatedFile.lastModified
        } : null)
        
        // Update the file in the list
        setFiles(prev => prev.map(file => 
          file.name === selectedFile.name 
            ? { ...file, content: editContent, lastModified: updatedFile.lastModified }
            : file
        ))
        
        setIsEditing(false)
        setStatus('✅ File saved successfully')
      } else {
        setStatus('❌ Failed to save file')
      }
    } catch (error) {
      console.error('Error saving file:', error)
      setStatus('❌ Error saving file')
    }
  }

  const handleCancel = () => {
    if (selectedFile) {
      setEditContent(selectedFile.content)
    }
    setIsEditing(false)
  }

  const handleGenerateAllReferences = async () => {
    if (!isSignedIn) return
    
    const projectId = getProjectId()
    if (!projectId) {
      setStatus('⚠️ No project selected')
      return
    }

    setGenerationStatus({ isGenerating: true, message: 'Generating AI-powered reference content...' })
    GlobalLoader.show({
      title: 'Generating References',
      stage: 'Starting...',
      showProgress: true,
      size: 'md',
      customMessages: [
        '🖋️ Sharpening pencils for epic writing...',
        '📚 Consulting the storytelling gods...',
        "🎭 Giving your characters personality...",
        "🗺️ Drawing your story's treasure map...",
        '🔮 Gazing into plot crystal balls...',
      ],
      timeoutMs: 1800000,
    })
    setStatus('')

    try {
      const authHeaders = await getAuthHeaders()
      // Start polling for progress updates
      const poll = async () => {
        try {
          const res = await fetch(`/api/v2/projects/${projectId}/references/progress`, { headers: authHeaders })
          if (!res.ok) return
          const data = await res.json()
          if (typeof data.progress === 'number') {
            GlobalLoader.update({ progress: data.progress, stage: data.stage })
          } else if (data.progress?.percentage != null) {
            GlobalLoader.update({ progress: data.progress.percentage, stage: data.stage })
          }
          if (data.status === 'completed' || data.progress === 100) {
            clearInterval(progressInterval)
            GlobalLoader.hide()
            await fetchReferenceFiles()
          }
          if (data.status === 'failed' || data.status === 'failed-rate-limit') {
            clearInterval(progressInterval)
            GlobalLoader.hide()
            setStatus(`❌ Reference generation failed${data.message ? `: ${data.message}` : ''}`)
          }
        } catch {}
      }
      const progressInterval = setInterval(poll, 3000)
      await poll()
      const response = await fetch(`/api/v2/projects/${projectId}/references/generate`, {
        method: 'POST',
        headers: {
          ...authHeaders,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({})
      })

      if (response.ok) {
        const result = await response.json()
        if (result.success) {
          setStatus(`✅ Generated ${result.generated_files} reference files successfully`)
          // Refresh the file list
          await fetchReferenceFiles()
          // Hide handled by polling completion
        } else {
          setStatus(`⚠️ Generation completed with ${result.failed_files} errors: ${result.message}`)
          // Still refresh to show any successful files
          await fetchReferenceFiles()
          GlobalLoader.hide()
        }
      } else {
        const errorData = await response.json()
        if (response.status === 503) {
          setStatus('⚠️ AI content generation not available - OpenAI API key not configured')
        } else {
          setStatus(`❌ Generation failed: ${errorData.detail || 'Unknown error'}`)
        }
        GlobalLoader.hide()
      }
    } catch (error) {
      console.error('Error generating reference content:', error)
      setStatus('❌ Error generating reference content')
      GlobalLoader.hide()
    } finally {
      setGenerationStatus({ isGenerating: false })
    }
  }

  const handleRegenerateFile = async (fileName: string) => {
    if (!isSignedIn) return
    
    const projectId = getProjectId()
    if (!projectId) {
      setStatus('⚠️ No project selected')
      return
    }

    setGenerationStatus({ 
      isGenerating: true, 
      currentFile: fileName,
      message: `Regenerating ${fileName}...` 
    })
    GlobalLoader.show({
      title: `Regenerating ${fileName}`,
      stage: 'Creating new content...',
      showProgress: false,
      size: 'md',
      customMessages: [
        '🧠 Re-composing details...',
        '🧵 Maintaining continuity...',
        '✨ Polishing style...',
      ],
      timeoutMs: 900000,
    })
    setStatus('')

    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetch(`/api/v2/projects/${projectId}/references/generate`, {
        method: 'POST',
        headers: {
          ...authHeaders,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ regenerate: true, filename: fileName })
      })

      if (response.ok) {
        const result = await response.json()
        if (result.success) {
          setStatus(`✅ Successfully regenerated ${fileName}`)
          // Refresh the file list and update selected file if it's the current one
          await fetchReferenceFiles()
          if (selectedFile?.name === fileName) {
            await handleFileSelect(fileName)
          }
          GlobalLoader.hide()
        } else {
          setStatus(`❌ Failed to regenerate ${fileName}: ${result.message || result.error}`)
          GlobalLoader.hide()
        }
      } else {
        const errorData = await response.json()
        if (response.status === 503) {
          setStatus('⚠️ AI content generation not available - OpenAI API key not configured')
        } else {
          setStatus(`❌ Regeneration failed: ${errorData.detail || 'Unknown error'}`)
        }
        GlobalLoader.hide()
      }
    } catch (error) {
      console.error('Error regenerating reference file:', error)
      setStatus(`❌ Error regenerating ${fileName}`)
      GlobalLoader.hide()
    } finally {
      setGenerationStatus({ isGenerating: false })
    }
  }

  const referenceFileTypes = [
    { name: 'characters.md', icon: '👥', description: 'Character profiles and development' },
    { name: 'outline.md', icon: '📋', description: 'Story structure and plot outline' },
    { name: 'world-building.md', icon: '🌍', description: 'Setting details and world rules' },
    { name: 'style-guide.md', icon: '✍️', description: 'Writing style and tone guidelines' },
    { name: 'plot-timeline.md', icon: '📅', description: 'Chronological story timeline' }
  ]

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900">
          Reference Files
        </h2>
        
        {/* Generation Controls */}
        {isLoaded && isSignedIn && !isLoading && (
          <div className="flex space-x-2">
            <button
              onClick={handleGenerateAllReferences}
              disabled={generationStatus.isGenerating}
              className="btn-primary text-sm"
            >
              {generationStatus.isGenerating && !generationStatus.currentFile ? (
                <>
                  <ArrowPathIcon className="w-4 h-4 mr-1 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <SparklesIcon className="w-4 h-4 mr-1" />
                  Generate AI Content
                </>
              )}
            </button>
          </div>
        )}
      </div>

      {/* Generation Status */}
      {generationStatus.isGenerating && (
        <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-md">
          <div className="flex items-center">
            <ArrowPathIcon className="w-4 h-4 text-blue-600 animate-spin mr-2" />
            <span className="text-sm text-blue-800">
              {generationStatus.message || 'Generating content...'}
            </span>
          </div>
        </div>
      )}

      {/* Show loading state while auth is initializing */}
      {!isLoaded && (
        <div className="card">
          <div className="text-center py-8">
            <div className="animate-pulse">
              <div className="h-4 bg-gray-200 rounded w-3/4 mx-auto mb-2"></div>
              <div className="h-4 bg-gray-200 rounded w-1/2 mx-auto"></div>
            </div>
          </div>
        </div>
      )}
 
      {/* Show sign-in prompt if user is not authenticated */}
      {isLoaded && !isSignedIn && (
        <div className="text-center py-8">
          <div className="text-gray-500 mb-4">Please sign in to view reference files</div>
          <p className="text-sm text-gray-400">
            Authentication is required to access reference files.
          </p>
        </div>
      )}
 
      {/* Show content only if user is authenticated */}
      {isLoaded && isSignedIn && (
        <>
      {isLoading && (
        <div className="flex items-center justify-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
        </div>
      )}

      {!isLoading && files.length === 0 && (
        <div className="text-center py-8 text-gray-500">
          <DocumentTextIcon className="w-12 h-12 mx-auto mb-4 text-gray-400" />
          <p>No reference files found.</p>
          <p className="text-sm mt-2">Upload and initialize a Book Bible to generate reference files.</p>
          <p className="text-sm mt-1">Or click "Generate AI Content" to create rich reference files.</p>
        </div>
      )}

      {!isLoading && files.length > 0 && (
        <div className="space-y-4">
          {/* File List */}
          <div className="grid grid-cols-1 gap-2">
            {referenceFileTypes.map((fileType) => {
              const file = files.find(f => f.name === fileType.name)
              const isRegenerating = generationStatus.isGenerating && generationStatus.currentFile === fileType.name
              
              return (
                <div key={fileType.name} className="flex items-center">
                  <button
                    onClick={() => file && handleFileSelect(fileType.name)}
                    className={`flex items-center p-3 rounded-lg border text-left transition-colors flex-1 mr-2 ${
                      selectedFile?.name === fileType.name
                        ? 'border-primary-300 bg-primary-50'
                        : file
                        ? 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                        : 'border-gray-100 bg-gray-50 opacity-50 cursor-not-allowed'
                    }`}
                    disabled={!file || isRegenerating}
                  >
                    <span className="text-2xl mr-3">{fileType.icon}</span>
                    <div className="flex-1">
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-gray-900">{fileType.name}</span>
                        {file && (
                          <CheckCircleIcon className="w-4 h-4 text-green-600" />
                        )}
                      </div>
                      <p className="text-sm text-gray-600">{fileType.description}</p>
                      {file && (
                        <p className="text-xs text-gray-500 mt-1">
                          Modified: {new Date(file.lastModified).toLocaleDateString()}
                        </p>
                      )}
                    </div>
                  </button>
                  
                  {/* Regenerate Button */}
                  {file && (
                    <button
                      onClick={() => handleRegenerateFile(fileType.name)}
                      disabled={generationStatus.isGenerating}
                      className="btn-secondary text-xs p-2"
                      title={`Regenerate ${fileType.name} with AI`}
                    >
                      {isRegenerating ? (
                        <ArrowPathIcon className="w-4 h-4 animate-spin" />
                      ) : (
                        <SparklesIcon className="w-4 h-4" />
                      )}
                    </button>
                  )}
                </div>
              )
            })}
          </div>

          {/* File Content */}
          {selectedFile && (
            <div className="border-t pt-4">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-md font-medium text-gray-900">
                  {selectedFile.name}
                </h3>
                <div className="flex space-x-2">
                  {!isEditing ? (
                    <button
                      onClick={() => setIsEditing(true)}
                      className="btn-secondary"
                    >
                      <PencilIcon className="w-4 h-4 mr-1" />
                      Edit
                    </button>
                  ) : (
                    <>
                      <button
                        onClick={handleCancel}
                        className="btn-secondary"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleSave}
                        className="btn-primary"
                      >
                        Save
                      </button>
                    </>
                  )}
                </div>
              </div>

              {isEditing ? (
                <textarea
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  className="w-full h-96 p-3 border border-gray-300 rounded-md font-mono text-sm"
                  placeholder="Edit file content..."
                />
              ) : (
                <div className="max-h-96 overflow-y-auto p-3 bg-gray-50 rounded-md">
                  <pre className="whitespace-pre-wrap text-sm text-gray-800">
                    {selectedFile.content}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {status && (
        <div className="mt-4 p-3 bg-gray-50 rounded-md">
          <p className="text-sm text-gray-700">{status}</p>
        </div>
      )}
         </>
       )}
    </div>
  )
} 