'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { useAuthToken } from '@/lib/auth'
import { CheckCircleIcon, PencilIcon, EyeIcon } from '@heroicons/react/24/outline'

interface ReferenceFile {
  name: string
  content: string
  lastModified?: string
  approved?: boolean
}

interface ReferenceTab {
  id: string
  label: string
  filename: string
  description: string
}

const REFERENCE_TABS: ReferenceTab[] = [
  {
    id: 'characters',
    label: 'Characters',
    filename: 'characters.md',
    description: 'Character profiles, relationships, and development arcs'
  },
  {
    id: 'outline',
    label: 'Plot Outline',
    filename: 'outline.md',
    description: 'Story structure, chapter breakdown, and key plot points'
  },
  {
    id: 'world-building',
    label: 'World/Glossary',
    filename: 'world-building.md',
    description: 'Setting details, world rules, and location descriptions'
  },
  {
    id: 'style-guide',
    label: 'Style & Tone',
    filename: 'style-guide.md',
    description: 'Writing style, voice, and narrative preferences'
  },
  {
    id: 'plot-timeline',
    label: 'Must-Includes',
    filename: 'plot-timeline.md',
    description: 'Timeline, key events, and essential story elements'
  }
]

export default function ReferenceReviewPage() {
  const params = useParams()
  const router = useRouter()
  const rawProjectId = params.projectId as string
  const { getAuthHeaders, isSignedIn } = useAuthToken()

  // Decode the project ID from URL and handle project name vs actual ID
  const decodedProjectName = decodeURIComponent(rawProjectId)
  const [actualProjectId, setActualProjectId] = useState<string | null>(null)
  const [projectTitle, setProjectTitle] = useState<string>(decodedProjectName)

  // Debug logging
  console.log('[ReferenceReviewPage] Debug info:', {
    params,
    rawProjectId,
    decodedProjectName,
    actualProjectId,
    currentURL: typeof window !== 'undefined' ? window.location.href : 'SSR'
  })

  // Find the actual project ID based on the project name from URL
  useEffect(() => {
    const findProjectId = async () => {
      try {
        const authHeaders = await getAuthHeaders()
        const response = await fetch('/api/projects', {
          method: 'GET',
          headers: authHeaders
        })
        
        if (response.ok) {
          const data = await response.json()
          const projects = data.projects || []
          
          // Try to find project by ID first (in case it's a real UUID)
          let project = projects.find((p: any) => p.project_id === rawProjectId || p.id === rawProjectId)
          
          // If not found by ID, try to find by title
          if (!project) {
            project = projects.find((p: any) => 
              p.title === decodedProjectName || 
              p.metadata?.title === decodedProjectName
            )
          }
          
          if (project) {
            const realProjectId = project.project_id || project.id
            setActualProjectId(realProjectId)
            setProjectTitle(project.title || project.metadata?.title || decodedProjectName)
            console.log('[ReferenceReviewPage] Found project:', { realProjectId, title: project.title })
          } else {
            console.error('[ReferenceReviewPage] Project not found for:', decodedProjectName)
            setActualProjectId(rawProjectId) // Fallback to raw ID
          }
        }
      } catch (error) {
        console.error('[ReferenceReviewPage] Error finding project:', error)
        setActualProjectId(rawProjectId) // Fallback to raw ID
      }
    }

    if (isSignedIn && rawProjectId) {
      findProjectId()
    }
  }, [isSignedIn, rawProjectId, decodedProjectName, getAuthHeaders])

  // Use the actual project ID for API calls
  const projectId = actualProjectId || rawProjectId

  const [activeTab, setActiveTab] = useState(REFERENCE_TABS[0].id)
  const [files, setFiles] = useState<Record<string, ReferenceFile>>({})
  const [loading, setLoading] = useState(true)
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState('')
  const [status, setStatus] = useState('')

  useEffect(() => {
    if (isSignedIn && projectId) {
      loadReferenceFiles()
    }
  }, [isSignedIn, projectId])

  const loadReferenceFiles = async () => {
    setLoading(true)
    const filesData: Record<string, ReferenceFile> = {}

    console.log('[loadReferenceFiles] Starting to load files with projectId:', projectId)

    try {
      const authHeaders = await getAuthHeaders()
      
      // Load each reference file
      for (const tab of REFERENCE_TABS) {
        try {
          const requestUrl = `/api/references/${tab.filename}?project_id=${projectId}`
          console.log('[loadReferenceFiles] Making request to:', requestUrl)
          
          const response = await fetch(requestUrl, {
            headers: authHeaders
          })
          
          if (response.ok) {
            const fileData = await response.json()
            filesData[tab.id] = {
              name: fileData.name,
              content: fileData.content,
              lastModified: fileData.lastModified,
              approved: false // Default to not approved
            }
          } else {
            // File doesn't exist yet - create placeholder
            filesData[tab.id] = {
              name: tab.filename,
              content: `# ${tab.label}\n\n*This reference file has not been generated yet.*\n\nClick "Generate References" to create AI-powered content for this section.`,
              approved: false
            }
          }
        } catch (error) {
          console.error(`Failed to load ${tab.filename}:`, error)
          filesData[tab.id] = {
            name: tab.filename,
            content: `# ${tab.label}\n\n*Error loading this reference file.*`,
            approved: false
          }
        }
      }
      
      setFiles(filesData)
    } catch (error) {
      console.error('Error loading reference files:', error)
      setStatus('❌ Failed to load reference files')
    } finally {
      setLoading(false)
    }
  }

  const handleEdit = () => {
    const currentFile = files[activeTab]
    if (currentFile) {
      setEditContent(currentFile.content)
      setIsEditing(true)
    }
  }

  const handleSave = async () => {
    if (!files[activeTab]) return

    try {
      const authHeaders = await getAuthHeaders()
      const filename = REFERENCE_TABS.find(t => t.id === activeTab)?.filename
      if (!filename) return

      const response = await fetch(`/api/references/${filename}?project_id=${projectId}`, {
        method: 'PUT',
        headers: {
          ...authHeaders,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ content: editContent })
      })

      if (response.ok) {
        setFiles(prev => ({
          ...prev,
          [activeTab]: {
            ...prev[activeTab],
            content: editContent
          }
        }))
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
    setIsEditing(false)
    setEditContent('')
  }

  const handleApprove = () => {
    setFiles(prev => ({
      ...prev,
      [activeTab]: {
        ...prev[activeTab],
        approved: true
      }
    }))
    setStatus(`✅ ${REFERENCE_TABS.find(t => t.id === activeTab)?.label} approved`)
  }

  const handleFinishReview = () => {
    // Redirect to the chapter writing workspace
    router.push(`/project/${projectId}/chapters`)
  }

  const generateAllReferences = async () => {
    setStatus('🔄 Generating AI-powered reference content...')
    
    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetch(`/api/v2/projects/${projectId}/references/generate`, {
        method: 'POST',
        headers: authHeaders
      })

      if (response.ok) {
        const result = await response.json()
        setStatus(`✅ Generated ${result.files?.length || 0} reference files`)
        await loadReferenceFiles() // Reload the files
      } else {
        const errorData = await response.json()
        setStatus(`❌ Generation failed: ${errorData.detail || 'Unknown error'}`)
      }
    } catch (error) {
      console.error('Error generating references:', error)
      setStatus('❌ Error generating references')
    }
  }

  const activeTabData = REFERENCE_TABS.find(t => t.id === activeTab)
  const currentFile = files[activeTab]
  const allApproved = REFERENCE_TABS.every(tab => files[tab.id]?.approved)

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 p-6">
        <div className="max-w-4xl mx-auto">
          <div className="animate-pulse space-y-4">
            <div className="h-8 bg-gray-200 rounded w-1/3"></div>
            <div className="h-4 bg-gray-200 rounded w-2/3"></div>
            <div className="h-64 bg-gray-200 rounded"></div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-clean">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="max-w-4xl mx-auto">
          <h1 className="text-2xl font-bold text-gray-900">📘 Story Reference Review - {projectTitle}</h1>
          <p className="text-gray-600 mt-1">
            Review and approve your reference files before starting to write
          </p>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="bg-white border-b border-gray-200 px-6">
        <div className="max-w-4xl mx-auto">
          <nav className="flex space-x-8">
            {REFERENCE_TABS.map((tab) => {
              const isActive = activeTab === tab.id
              const isApproved = files[tab.id]?.approved
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`py-4 px-1 border-b-2 font-medium text-sm flex items-center space-x-2 ${
                    isActive
                      ? 'border-blue-500 text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                  }`}
                >
                  <span>{tab.label}</span>
                  {isApproved && (
                    <CheckCircleIcon className="w-4 h-4 text-green-600" />
                  )}
                </button>
              )
            })}
          </nav>
        </div>
      </div>

      {/* Content Area */}
      <div className="prose-clean p-6 pb-24">
        {status && (
          <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg text-blue-800 text-sm">
            {status}
          </div>
        )}

        <Card>
          <CardHeader className="border-b border-gray-200">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-lg font-semibold">
                  {activeTabData?.label}
                </CardTitle>
                <p className="text-sm text-gray-600 mt-1">
                  {activeTabData?.description}
                </p>
              </div>
              <div className="flex items-center space-x-2">
                {!isEditing ? (
                  <>
                    <Button
                      onClick={handleEdit}
                      variant="outline"
                      size="sm"
                      className="flex items-center space-x-1"
                    >
                      <PencilIcon className="w-4 h-4" />
                      <span>Edit</span>
                    </Button>
                    <Button
                      onClick={handleApprove}
                      variant="default"
                      size="sm"
                      className="flex items-center space-x-1 bg-green-600 hover:bg-green-700"
                      disabled={files[activeTab]?.approved}
                    >
                      <CheckCircleIcon className="w-4 h-4" />
                      <span>{files[activeTab]?.approved ? 'Approved' : 'Approve'}</span>
                    </Button>
                  </>
                ) : (
                  <>
                    <Button
                      onClick={handleCancel}
                      variant="outline"
                      size="sm"
                    >
                      Cancel
                    </Button>
                    <Button
                      onClick={handleSave}
                      variant="default"
                      size="sm"
                    >
                      Save Changes
                    </Button>
                  </>
                )}
              </div>
            </div>
          </CardHeader>
          <CardContent className="p-6">
            {!currentFile ? (
              <div className="text-center py-8">
                <p className="text-gray-500 mb-4">No reference file found</p>
                <Button onClick={generateAllReferences} className="bg-blue-600 hover:bg-blue-700">
                  Generate References
                </Button>
              </div>
            ) : isEditing ? (
              <textarea
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                className="w-full h-96 p-4 border border-gray-300 rounded-lg resize-none focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm"
                placeholder="Edit your reference content here..."
              />
            ) : (
              <div className="prose max-w-none">
                <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">
                  {currentFile.content}
                </pre>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Sticky Bottom CTA */}
      <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 p-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div className="text-sm text-gray-600">
            {allApproved 
              ? "✅ All references approved - ready to start writing!"
              : `${REFERENCE_TABS.filter(tab => files[tab.id]?.approved).length} of ${REFERENCE_TABS.length} references approved`
            }
          </div>
          <Button
            onClick={handleFinishReview}
            className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2"
            size="lg"
          >
            Finish Review & Start Writing
          </Button>
        </div>
      </div>
    </div>
  )
} 