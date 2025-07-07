'use client'

import { useState, useRef } from 'react'
import { DocumentTextIcon, CloudArrowUpIcon, CheckCircleIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline'

interface BookBibleUploadProps {
  onProjectInitialized: () => void
}

export function BookBibleUpload({ onProjectInitialized }: BookBibleUploadProps) {
  const [file, setFile] = useState<File | null>(null)
  const [content, setContent] = useState('')
  const [isUploading, setIsUploading] = useState(false)
  const [isInitializing, setIsInitializing] = useState(false)
  const [status, setStatus] = useState('')
  const [projectInfo, setProjectInfo] = useState<any>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

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
      setContent(content)
      extractProjectInfo(content)
      setStatus('✅ Book Bible loaded successfully')
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
    if (!file || !content) return

    setIsUploading(true)
    setStatus('📤 Uploading Book Bible...')

    try {
      const response = await fetch('/api/book-bible/upload', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          filename: file.name,
          content: content,
          projectInfo: projectInfo
        })
      })

      const data = await response.json()

      if (response.ok) {
        setStatus('✅ Book Bible uploaded successfully!')
        setIsUploading(false)
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
    if (!file || !content) return

    setIsInitializing(true)
    setStatus('🚀 Initializing project from Book Bible...')

    try {
      const response = await fetch('/api/book-bible/initialize', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          filename: file.name,
          content: content,
          projectInfo: projectInfo
        })
      })

      const data = await response.json()

      if (response.ok) {
        setStatus('✅ Project initialized successfully!')
        setIsInitializing(false)
        onProjectInitialized()
      } else {
        setStatus(`❌ Initialization failed: ${data.error}`)
        setIsInitializing(false)
      }
    } catch (error) {
      setStatus(`❌ Initialization error: ${error instanceof Error ? error.message : 'Unknown error'}`)
      setIsInitializing(false)
    }
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

      {status && (
        <div className="mt-4 p-3 bg-gray-50 rounded-md">
          <p className="text-sm text-gray-700">{status}</p>
        </div>
      )}
    </div>
  )
} 