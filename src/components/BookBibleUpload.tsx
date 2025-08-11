'use client'

import { useState, useRef } from 'react'
import { DocumentTextIcon, CloudArrowUpIcon, CheckCircleIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline'
import { useAuthToken } from '@/lib/auth'
import { CreativeLoader } from './ui/CreativeLoader'
import { GlobalLoader } from '@/stores/useGlobalLoaderStore'
import { useEffect } from 'react'
import { useJobProgress } from '@/hooks/useJobProgress'

interface BookBibleUploadProps {
  onProjectInitialized: (projectId?: string) => void
}

export function BookBibleUpload({ onProjectInitialized }: BookBibleUploadProps) {
  const { getAuthHeaders, isLoaded, isSignedIn } = useAuthToken()
  const [file, setFile] = useState<File | null>(null)
  const [content, setContent] = useState('')
  const [isUploading, setIsUploading] = useState(false)
  const [isInitializing, setIsInitializing] = useState(false)
  const [status, setStatus] = useState('')
  const [projectInfo, setProjectInfo] = useState<any>(null)
  const [currentProjectId, setCurrentProjectId] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Progress tracking for reference generation
  const { progress, isPolling } = useJobProgress(currentProjectId, {
    pollInterval: 3000, // Poll every 3 seconds
    timeout: 300000, // 5 minute timeout
    onComplete: (result) => {
      setIsInitializing(false)
      setStatus('✅ Project initialized successfully! References are ready.')
      
      // Dispatch event to clear AutoCompleteBookManager cache
      if (typeof window !== 'undefined' && currentProjectId) {
        window.dispatchEvent(new CustomEvent('bookBibleUpdated', {
          detail: { projectId: currentProjectId }
        }))
      }
      
      setTimeout(() => {
        onProjectInitialized(currentProjectId || undefined)
      }, 1500)
    },
    onError: (error) => {
      setIsInitializing(false)
      setStatus(`❌ Reference generation failed: ${error}`)
    },
    onTimeout: () => {
      setIsInitializing(false)
      setStatus('⏰ Reference generation is taking longer than expected. Check back in a few minutes.')
    }
  })

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0]
    if (selectedFile) {
      if (selectedFile.type === 'text/markdown' || selectedFile.name.endsWith('.md')) {
        setFile(selectedFile)
        readFileContent(selectedFile)
      } else {
        setStatus('❌ Please select a Markdown (.md) file')
      }
    }
  }

  const readFileContent = (file: File) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      const content = e.target?.result as string
      
      // Check character limit (same as backend validation)
      const MAX_CHARACTERS = 50000
      if (content.length > MAX_CHARACTERS) {
        setStatus(`❌ File too large: ${content.length.toLocaleString()} characters. Maximum allowed: ${MAX_CHARACTERS.toLocaleString()} characters. Please reduce the file size by ${(content.length - MAX_CHARACTERS).toLocaleString()} characters.`)
        setFile(null)
        setContent('')
        return
      }
      
      setContent(content)
      extractProjectInfo(content)
      setStatus(`✅ Book Bible loaded successfully (${content.length.toLocaleString()} characters)`)
    }
    reader.onerror = () => {
      setStatus('❌ Error reading file')
    }
    reader.readAsText(file)
  }

  const extractProjectInfo = (content: string) => {
    // Extract basic project info from the book bible content
    const lines = content.split('\n')
    let title = ''
    let genre = ''
    let logline = ''

    for (const line of lines) {
      if (line.includes('**Title:**') || line.includes('- **Title:**')) {
        title = line.split('**Title:**')[1]?.trim() || ''
      } else if (line.includes('**Genre:**') || line.includes('- **Genre:**')) {
        genre = line.split('**Genre:**')[1]?.trim() || ''
      } else if (line.includes('**Logline:**') || line.includes('- **Logline:**')) {
        logline = line.split('**Logline:**')[1]?.trim() || ''
      }
    }

    setProjectInfo({ title, genre, logline })
  }

  const handleUpload = async () => {
    if (!isSignedIn) {
      setStatus('❌ Please sign in to upload files')
      return
    }

    if (!file || !content) return

    setIsUploading(true)
    setStatus('📤 Uploading Book Bible...')

    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetch('/api/book-bible/upload', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders
        },
        body: JSON.stringify({
          filename: file.name,
          content: content,
          projectInfo: projectInfo
        })
      })

      const data = await response.json()

      if (response.ok) {
        setStatus('📝 Generating reference files...')
        // Give some time for reference generation
        setTimeout(() => {
          setStatus('✅ Book Bible uploaded successfully!')
          setIsUploading(false)
          const projectId = data.project_id || localStorage.getItem('lastProjectId')
          
          // Dispatch event to clear AutoCompleteBookManager cache
          if (typeof window !== 'undefined' && projectId) {
            window.dispatchEvent(new CustomEvent('bookBibleUpdated', {
              detail: { projectId }
            }))
          }
          
          onProjectInitialized(projectId) // Refresh project status
        }, 2000)
      } else {
        setStatus(`❌ Upload failed: ${data.error}`)
        setIsUploading(false)
      }
    } catch (error) {
      setStatus(`❌ Upload error: ${error instanceof Error ? error.message : 'Unknown error'}`)
      setIsUploading(false)
    }
  }

  const handleInitializeProject = async () => {
    console.log('=== INITIALIZE PROJECT DEBUG START ===')
    console.log('isSignedIn:', isSignedIn)
    console.log('isLoaded:', isLoaded)
    
    if (!isSignedIn) {
      setStatus('❌ Please sign in to initialize projects')
      console.log('ERROR: User not signed in')
      return
    }

    if (!file || !content) {
      console.log('ERROR: No file or content')
      return
    }

    setIsInitializing(true)
    setStatus('🚀 Initializing project from Book Bible...')

    try {
      console.log('Getting auth headers...')
      const authHeaders = await getAuthHeaders()
      console.log('Auth headers received:', authHeaders)
      console.log('Has Authorization header:', !!authHeaders.Authorization)
      
      const requestBody = {
        project_id: `project-${Date.now()}`, // Generate unique project ID
        content: content
      }
      console.log('Request body prepared:', { project_id: requestBody.project_id, contentLength: content.length })
      
      const requestHeaders = {
        'Content-Type': 'application/json',
        ...authHeaders
      }
      console.log('Final request headers:', Object.keys(requestHeaders))
      
      console.log('Making fetch request to /api/book-bible/initialize')
      const response = await fetch('/api/book-bible/initialize', {
        method: 'POST',
        headers: requestHeaders,
        body: JSON.stringify(requestBody)
      })

      console.log('Response status:', response.status)
      console.log('Response headers:', Object.fromEntries(response.headers.entries()))
      
      const data = await response.json()
      console.log('Response data:', data)

      if (response.ok) {
        const projectId = data.project_id
        setStatus('📝 Generating reference files...')
        
        // Store project_id and book bible content for project status component
        if (projectId) {
          localStorage.setItem('lastProjectId', projectId)
          localStorage.setItem(`bookBible-${projectId}`, content)
          console.log('Stored project_id and book bible in localStorage:', projectId)
          
          // Start tracking progress
          setCurrentProjectId(projectId)
        }
        
        // Note: Don't call onProjectInitialized yet - let the progress tracker handle completion
      } else {
        setStatus(`❌ Initialization failed: ${data.error}`)
        setIsInitializing(false)
      }
    } catch (error) {
      console.error('=== INITIALIZATION ERROR ===', error)
      setStatus(`❌ Initialization error: ${error instanceof Error ? error.message : 'Unknown error'}`)
      setIsInitializing(false)
    }
    console.log('=== INITIALIZE PROJECT DEBUG END ===')
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const droppedFile = e.dataTransfer.files[0]
    if (droppedFile) {
      if (droppedFile.type === 'text/markdown' || droppedFile.name.endsWith('.md')) {
        setFile(droppedFile)
        readFileContent(droppedFile)
      } else {
        setStatus('❌ Please select a Markdown (.md) file')
      }
    }
  }

  // If user is not authenticated, show sign-in prompt
  if (!isLoaded) {
    return (
      <div className="card">
        <div className="text-center py-8">
          <div className="animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-3/4 mx-auto mb-2"></div>
            <div className="h-4 bg-gray-200 rounded w-1/2 mx-auto"></div>
          </div>
        </div>
      </div>
    )
  }

  if (!isSignedIn) {
    return (
      <div className="card">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Book Bible Upload
        </h2>
        <div className="text-center py-8">
          <div className="text-gray-500 mb-4">Please sign in to upload your Book Bible</div>
          <p className="text-sm text-gray-400">
            Authentication is required to upload and initialize projects.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="card">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">
        Book Bible Upload
      </h2>
      
      {!file ? (
        <div
          onDragOver={handleDragOver}
          onDrop={handleDrop}
          className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center hover:border-primary-400 transition-colors cursor-pointer"
          onClick={() => fileInputRef.current?.click()}
        >
          <DocumentTextIcon className="w-12 h-12 mx-auto text-gray-400 mb-4" />
          <p className="text-lg font-medium text-gray-900 mb-2">
            Upload Your Book Bible
          </p>
          <p className="text-sm text-gray-600 mb-4">
            Drag and drop your book-bible.md file here, or click to browse
          </p>
          <button
            type="button"
            className="btn-primary"
          >
            <CloudArrowUpIcon className="w-4 h-4 mr-2" />
            Choose File
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center justify-between p-4 bg-green-50 rounded-lg">
            <div className="flex items-center">
              <CheckCircleIcon className="w-5 h-5 text-green-600 mr-2" />
              <span className="text-sm font-medium text-green-800">
                {file.name}
              </span>
            </div>
            <button
              onClick={() => {
                setFile(null)
                setContent('')
                setProjectInfo(null)
                setStatus('')
              }}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              Remove
            </button>
          </div>

          {projectInfo && (
            <div className="p-4 bg-blue-50 rounded-lg">
              <h3 className="text-sm font-medium text-blue-900 mb-2">Project Information</h3>
              <div className="space-y-1 text-sm text-blue-800">
                {projectInfo.title && <p><strong>Title:</strong> {projectInfo.title}</p>}
                {projectInfo.genre && <p><strong>Genre:</strong> {projectInfo.genre}</p>}
                {projectInfo.logline && <p><strong>Logline:</strong> {projectInfo.logline}</p>}
              </div>
            </div>
          )}

          <div className="flex space-x-3">
            <button
              onClick={handleUpload}
              disabled={isUploading || isInitializing}
              className="flex-1 btn-secondary"
            >
              {isUploading ? (
                <>
                  <CloudArrowUpIcon className="w-4 h-4 mr-2 animate-spin" />
                  Uploading...
                </>
              ) : (
                <>
                  <CloudArrowUpIcon className="w-4 h-4 mr-2" />
                  Upload Only
                </>
              )}
            </button>
            
            <button
              onClick={handleInitializeProject}
              disabled={isUploading || isInitializing}
              className="flex-1 btn-primary"
            >
              {isInitializing ? (
                <>
                  <DocumentTextIcon className="w-4 h-4 mr-2 animate-spin" />
                  Initializing...
                </>
              ) : (
                <>
                  <DocumentTextIcon className="w-4 h-4 mr-2" />
                  Initialize Project
                </>
              )}
            </button>
          </div>
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept=".md,.markdown"
        onChange={handleFileSelect}
        className="hidden"
      />

      {/* Sync to global loader */}
      {useEffect(() => {
        const visible = isInitializing || isPolling
        if (visible) {
          GlobalLoader.show({
            title: 'Generating References',
            stage: progress?.stage,
            progress: progress?.progress,
            showProgress: true,
            size: 'md',
            fullScreen: true,
            customMessages: [
              '🖋️ Sharpening pencils for epic writing...',
              '📚 Consulting the storytelling gods...',
              "🎭 Giving your characters personality...",
              "🗺️ Drawing your story's treasure map...",
              '🔮 Gazing into plot crystal balls...',
              '📖 Whispering secrets to the muses...',
              '✨ Sprinkling AI magic on your ideas...',
              '🎪 Teaching your words to dance...',
              '🌟 Aligning story constellations...',
              '🎨 Mixing the perfect emotional palette...'
            ],
            timeoutMs: 180000,
            onTimeout: () => setStatus('⏰ Taking longer than expected. Your references will be ready soon!'),
          })
        } else {
          GlobalLoader.hide()
        }
        // Update progress/stage as it changes
        if (visible && (progress?.progress != null || progress?.stage)) {
          GlobalLoader.update({
            progress: progress?.progress,
            stage: progress?.stage,
          })
        }
      }, [isInitializing, isPolling, progress?.progress, progress?.stage])}

      {status && !isPolling && !isInitializing && (
        <div className="mt-4 p-3 bg-gray-50 rounded-md">
          <p className="text-sm text-gray-700">{status}</p>
        </div>
      )}
    </div>
  )
} 