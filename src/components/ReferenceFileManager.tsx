'use client'

import { useState, useEffect } from 'react'
import { DocumentTextIcon, PencilIcon, EyeIcon, CheckCircleIcon } from '@heroicons/react/24/outline'

interface ReferenceFile {
  name: string
  content: string
  lastModified: string
}

export function ReferenceFileManager() {
  const [files, setFiles] = useState<ReferenceFile[]>([])
  const [selectedFile, setSelectedFile] = useState<ReferenceFile | null>(null)
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [status, setStatus] = useState('')

  useEffect(() => {
    fetchReferenceFiles()
  }, [])

  const fetchReferenceFiles = async () => {
    setIsLoading(true)
    try {
      const response = await fetch('/api/references')
      if (response.ok) {
        const data = await response.json()
        setFiles(data.files || [])
      }
    } catch (error) {
      console.error('Failed to fetch reference files:', error)
      setStatus('❌ Failed to load reference files')
    } finally {
      setIsLoading(false)
    }
  }

  const handleFileSelect = async (fileName: string) => {
    setIsLoading(true)
    try {
      const response = await fetch(`/api/references/${fileName}`)
      if (response.ok) {
        const data = await response.json()
        setSelectedFile(data)
        setEditContent(data.content)
        setIsEditing(false)
      }
    } catch (error) {
      console.error('Failed to fetch file content:', error)
      setStatus('❌ Failed to load file content')
    } finally {
      setIsLoading(false)
    }
  }

  const handleSave = async () => {
    if (!selectedFile) return

    setIsLoading(true)
    try {
      const response = await fetch(`/api/references/${selectedFile.name}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          content: editContent
        })
      })

      if (response.ok) {
        setStatus('✅ File saved successfully')
        setSelectedFile({ ...selectedFile, content: editContent })
        setIsEditing(false)
        fetchReferenceFiles()
      } else {
        const data = await response.json()
        setStatus(`❌ Save failed: ${data.error}`)
      }
    } catch (error) {
      setStatus(`❌ Save error: ${error instanceof Error ? error.message : 'Unknown error'}`)
    } finally {
      setIsLoading(false)
    }
  }

  const handleCancel = () => {
    if (selectedFile) {
      setEditContent(selectedFile.content)
    }
    setIsEditing(false)
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
      <h2 className="text-lg font-semibold text-gray-900 mb-4">
        Reference Files
      </h2>

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
        </div>
      )}

      {!isLoading && files.length > 0 && (
        <div className="space-y-4">
          {/* File List */}
          <div className="grid grid-cols-1 gap-2">
            {referenceFileTypes.map((fileType) => {
              const file = files.find(f => f.name === fileType.name)
              return (
                <button
                  key={fileType.name}
                  onClick={() => file && handleFileSelect(fileType.name)}
                  className={`flex items-center p-3 rounded-lg border text-left transition-colors ${
                    selectedFile?.name === fileType.name
                      ? 'border-primary-300 bg-primary-50'
                      : file
                      ? 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                      : 'border-gray-100 bg-gray-50 opacity-50 cursor-not-allowed'
                  }`}
                  disabled={!file}
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
    </div>
  )
} 