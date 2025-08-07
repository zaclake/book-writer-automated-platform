'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { useAuthToken } from '@/lib/auth'
import { CheckCircleIcon, PencilIcon, EyeIcon } from '@heroicons/react/24/outline'
import ProjectLayout from '@/components/layout/ProjectLayout'

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
  
  // Check for retry parameter in URL
  const [shouldShowRetry, setShouldShowRetry] = useState(false)
  
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const urlParams = new URLSearchParams(window.location.search)
      setShouldShowRetry(urlParams.get('retry') === 'true')
    }
  }, [])

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
        const response = await fetch('/api/v2/projects', {
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
  const [loading, setLoading] = useState(false)  // Changed from true to false
  const [isEditing, setIsEditing] = useState(false)
  const [editContent, setEditContent] = useState('')
  const [status, setStatus] = useState('')
  const [hasLoaded, setHasLoaded] = useState(false)

  // Reset hasLoaded when projectId changes
  useEffect(() => {
    setHasLoaded(false)
  }, [projectId])

  useEffect(() => {
    if (isSignedIn && projectId && !hasLoaded) {  // Removed !loading condition
      console.log('[useEffect] Loading reference files for projectId:', projectId)
      loadReferenceFiles()
    }
  }, [isSignedIn, projectId, hasLoaded])

  const loadReferenceFiles = async () => {
    setLoading(true)
    const filesData: Record<string, ReferenceFile> = {}

    console.log('[loadReferenceFiles] Starting to load files with projectId:', projectId)

    try {
      const authHeaders = await getAuthHeaders()
      
      // Load each reference file using the v2 backend endpoints
      for (const tab of REFERENCE_TABS) {
        try {
          const requestUrl = `/api/v2/projects/${projectId}/references/${tab.filename}`
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
          } else if (response.status === 404) {
            // File doesn't exist yet - create placeholder (don't log as error)
            console.log(`[loadReferenceFiles] ${tab.filename} not found (404) - creating placeholder`)
            filesData[tab.id] = {
              name: tab.filename,
              content: `# ${tab.label}\n\n*This reference file has not been generated yet.*\n\nClick "Generate References" to create AI-powered content for this section.`,
              approved: false
            }
          } else {
            // Other error
            console.error(`[loadReferenceFiles] Error loading ${tab.filename}: ${response.status} ${response.statusText}`)
            filesData[tab.id] = {
              name: tab.filename,
              content: `# ${tab.label}\n\n*Error loading this reference file (${response.status}).*`,
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
      setHasLoaded(true)
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

      const response = await fetch(`/api/v2/projects/${projectId}/references/${filename}`, {
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
    <ProjectLayout 
      projectId={actualProjectId || rawProjectId} 
      projectTitle={projectTitle}
    >
      <div className="bg-brand-off-white">
      {/* Beautiful Immersive Hero Section */}
      <div className="relative min-h-[40vh] bg-gradient-to-br from-brand-lavender via-brand-ink-blue to-brand-blush-orange overflow-hidden">
        {/* Animated background particles */}
        <div className="absolute inset-0">
          <div className="absolute top-1/4 left-1/4 w-2 h-2 bg-white/20 rounded-full animate-float"></div>
          <div className="absolute top-1/3 right-1/4 w-1 h-1 bg-white/30 rounded-full animate-float" style={{animationDelay: '2s'}}></div>
          <div className="absolute bottom-1/3 left-1/3 w-3 h-3 bg-white/10 rounded-full animate-float" style={{animationDelay: '4s'}}></div>
        </div>
        
        {/* Radial overlay for focus */}
        <div className="absolute inset-0 bg-gradient-radial from-transparent via-transparent to-black/10"></div>
        
        <div className="relative z-10 flex items-center justify-center min-h-[40vh] px-6 md:px-8 lg:px-12">
          <div className="text-center max-w-4xl">
            <h1 className="text-4xl md:text-5xl font-black text-white mb-4 drop-shadow-xl tracking-tight">
              Reference Materials
            </h1>
            <p className="text-white/90 text-lg md:text-xl font-medium mb-6">
              Your story's foundation: characters, world-building, and plot elements
            </p>
            <p className="text-white/80 text-base font-medium">
              Project: {projectTitle}
            </p>
          </div>
        </div>
      </div>

      {/* Main Content with New Theme */}
      <div className="w-full px-6 md:px-8 lg:px-12 py-12">
        {/* Show retry button if needed */}
        {shouldShowRetry && (
          <div className="mb-8 bg-gradient-to-r from-amber-50 to-orange-50 rounded-2xl p-6 backdrop-blur-sm border border-amber-200 shadow-lg">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-bold text-amber-800 mb-2">Generation Failed</h3>
                <p className="text-amber-700 font-medium">Would you like to retry creating the reference files?</p>
              </div>
              <button
                onClick={generateAllReferences} // Changed to generateAllReferences
                disabled={loading}
                className="bg-gradient-to-r from-amber-500 to-orange-500 text-white px-6 py-3 rounded-xl font-bold hover:shadow-lg transition-all hover:scale-105 disabled:opacity-50"
              >
                {loading ? 'Generating...' : 'Retry Generation'}
              </button>
            </div>
          </div>
        )}

        {/* Beautiful Tab Navigation */}
        <div className="mb-8">
          <div className="flex flex-wrap gap-2 p-2 bg-gradient-to-r from-white/40 to-brand-beige/30 rounded-2xl backdrop-blur-sm border border-white/50 shadow-xl">
            {REFERENCE_TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-6 py-3 font-bold text-sm rounded-xl transition-all duration-300 ${
                  activeTab === tab.id
                    ? 'bg-gradient-to-r from-brand-forest to-brand-lavender text-white shadow-xl'
                    : 'text-brand-forest/70 hover:text-brand-forest hover:bg-white/60'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
          
          {/* Tab Description */}
          <div className="mt-4 text-center">
            <p className="text-brand-forest/70 font-medium">
              {REFERENCE_TABS.find(tab => tab.id === activeTab)?.description}
            </p>
          </div>
        </div>

        {/* Content Area */}
        <div className="bg-gradient-to-br from-white/60 via-brand-beige/30 to-brand-lavender/10 rounded-2xl p-8 backdrop-blur-sm border border-white/50 shadow-xl">
          {loading ? (
            /* Beautiful Loading State */
            <div className="text-center py-16">
              <div className="mb-8">
                <div className="w-16 h-16 border-4 border-brand-lavender/30 border-t-brand-lavender rounded-full animate-spin mx-auto mb-6"></div>
              </div>
              <h3 className="text-2xl font-bold text-brand-forest mb-4">Loading Reference Files</h3>
              <p className="text-brand-forest/70 font-medium">
                Gathering your story's essential materials...
              </p>
            </div>
          ) : files[activeTab] ? (
            /* Enhanced File Display */
            <div className="space-y-6">
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-2xl font-black text-brand-forest">
                  {activeTabData?.label}
                </h3>
                <div className="text-sm text-brand-forest/60 font-medium">
                  Last updated: {new Date(files[activeTab].lastModified || '').toLocaleDateString()}
                </div>
              </div>
              
              <div className="bg-white/80 rounded-xl p-6 border border-brand-lavender/20 shadow-lg">
                <div className="prose prose-lg max-w-none text-brand-forest">
                  <div 
                    className="whitespace-pre-wrap leading-relaxed"
                    dangerouslySetInnerHTML={{ 
                      __html: files[activeTab].content.replace(/\n/g, '<br/>') 
                    }}
                  />
                </div>
              </div>
            </div>
          ) : (
            /* Beautiful Empty State */
            <div className="text-center py-16">
              <div className="mb-8">
                <div className="w-20 h-20 mx-auto bg-gradient-to-br from-brand-lavender/20 to-brand-forest/20 rounded-full flex items-center justify-center mb-6">
                  <span className="text-4xl">📚</span>
                </div>
              </div>
              <h3 className="text-2xl font-bold text-brand-forest mb-4">
                No {activeTabData?.label} Found
              </h3>
              <p className="text-brand-forest/70 font-medium mb-8 max-w-md mx-auto">
                Reference files for this category haven't been created yet. They'll appear here once your project generates them.
              </p>
              <div className="space-y-3 text-sm text-brand-forest/60">
                <p>Reference files are created when you:</p>
                <ul className="inline-block text-left space-y-1">
                  <li>• Upload a book bible</li>
                  <li>• Generate chapters with AI</li>
                  <li>• Use the reference generation tools</li>
                </ul>
              </div>
            </div>
          )}
        </div>

        {/* Enhanced Reference Generation Section */}
        <div className="mt-12 bg-gradient-to-br from-white/60 via-brand-beige/30 to-brand-lavender/10 rounded-2xl p-8 backdrop-blur-sm border border-white/50 shadow-xl">
          <h3 className="text-2xl font-black text-brand-forest mb-6">Reference Generation</h3>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-white/60 rounded-xl p-6 border border-brand-lavender/20">
              <h4 className="text-lg font-bold text-brand-forest mb-3">Manual Generation</h4>
              <p className="text-brand-forest/70 mb-4 font-medium">
                Trigger reference file generation based on your current project content.
              </p>
              <button
                onClick={generateAllReferences}
                disabled={loading}
                className="bg-gradient-to-r from-brand-forest to-brand-lavender text-white px-6 py-3 rounded-xl font-bold hover:shadow-lg transition-all hover:scale-105 disabled:opacity-50 w-full"
              >
                {loading ? 'Generating...' : 'Generate References'}
              </button>
            </div>
            
            <div className="bg-white/60 rounded-xl p-6 border border-brand-lavender/20">
              <h4 className="text-lg font-bold text-brand-forest mb-3">Auto-Generation</h4>
              <p className="text-brand-forest/70 mb-4 font-medium">
                Reference files are automatically created when you generate chapters or upload content.
              </p>
              <div className="text-sm text-brand-forest/60 font-medium">
                Current status: <span className="text-brand-forest font-bold">
                  {Object.keys(files).length > 0 ? 'Active' : 'Pending'}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
      </div>
    </ProjectLayout>
  )
} 