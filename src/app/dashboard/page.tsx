'use client'

import { useState, useEffect } from 'react'
import { useAuth } from '@clerk/nextjs'
import { useRouter } from 'next/navigation'
import { BookBibleUpload } from '@/components/BookBibleUpload'
import { BlankProjectCreator } from '@/components/BlankProjectCreator'
import { CreativeLoader } from '@/components/ui/CreativeLoader'
import { AutoCompleteBookManager } from '@/components/AutoCompleteBookManager'
import OnboardingFlow from '@/components/OnboardingFlow'
import { useUserProjects, useProject, useProjectChapters } from '@/hooks/useFirestore'
import { useFocusTrap } from '@/hooks/useFocusTrap'
import { useAnalytics } from '@/lib/analytics'
import { useErrorMonitoring } from '@/lib/errorMonitoring'
import { SkeletonPlaceholder } from '@/components/ui/SkeletonPlaceholder'
import { 
  PencilIcon, 
  BookOpenIcon, 
  DocumentTextIcon,
  PlusCircleIcon,
  ArrowRightIcon,
  CheckCircleIcon,
  TrashIcon
} from '@heroicons/react/24/outline'

export default function Dashboard() {
  // Force dynamic rendering by using runtime timestamp
  const renderTime = Date.now()
  
  const { getToken, isLoaded, isSignedIn, userId } = useAuth()
  const router = useRouter()
  const [authReady, setAuthReady] = useState(false)
  const [currentProjectId, setCurrentProjectId] = useState<string | null>(null)
  const [showOnboarding, setShowOnboarding] = useState(false)
  const [onboardingComplete, setOnboardingComplete] = useState(false)
  const [showProjectCreation, setShowProjectCreation] = useState(false)
  const [projectCreationType, setProjectCreationType] = useState<'upload' | 'blank' | null>(null)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<string | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [optimisticallyRemovedProjects, setOptimisticallyRemovedProjects] = useState<Set<string>>(new Set())

  // Real-time Firestore hooks
  const { projects: rawProjects, loading: projectsLoading, refetch: refetchProjects } = useUserProjects()
  const { project: currentProject } = useProject(currentProjectId)
  const { chapters, loading: chaptersLoading } = useProjectChapters(currentProjectId)

  // Filter out optimistically removed projects
  const projects = rawProjects.filter(project => !optimisticallyRemovedProjects.has(project.id))

  // Focus trap for modals
  const projectCreationModalRef = useFocusTrap(showProjectCreation)
  const deleteConfirmModalRef = useFocusTrap(!!showDeleteConfirm)

  // Analytics and Error Monitoring
  const analytics = useAnalytics()
  const errorMonitoring = useErrorMonitoring()

  // Track when auth is ready
  useEffect(() => {
    if (isLoaded) {
      setAuthReady(true)
    }
  }, [isLoaded])

  // Track dashboard views and set user ID
  useEffect(() => {
    if (authReady && isSignedIn && userId) {
      analytics.setUserId(userId)
      errorMonitoring.setUserId(userId)
      analytics.dashboardViewed()
    }
  }, [authReady, isSignedIn, userId]) // analytics and errorMonitoring are stable instances

  // Check onboarding status
  useEffect(() => {
    const checkOnboardingStatus = async () => {
      if (authReady && isSignedIn && userId) {
        try {
          const response = await fetch('/api/users/v2/onboarding', {
            headers: {
              'Authorization': `Bearer ${await getToken()}`
            }
          })
          
          if (response.ok) {
            const data = await response.json()
            const completed = data.completed || false
            setOnboardingComplete(completed)
            setShowOnboarding(!completed)
          } else {
            setOnboardingComplete(false)
            setShowOnboarding(true)
          }
        } catch (error) {
          console.error('Error checking onboarding status:', error)
          setOnboardingComplete(false)
          setShowOnboarding(true)
        }
      }
    }

    checkOnboardingStatus()
  }, [authReady, isSignedIn, userId, getToken])

  // Clean up optimistically removed projects when backend data updates
  useEffect(() => {
    if (optimisticallyRemovedProjects.size > 0) {
      const stillExistingIds = Array.from(optimisticallyRemovedProjects).filter(id =>
        rawProjects.some(project => project.id === id)
      )
      
      if (stillExistingIds.length !== optimisticallyRemovedProjects.size) {
        setOptimisticallyRemovedProjects(new Set(stillExistingIds))
      }
    }
  }, [rawProjects, optimisticallyRemovedProjects])

  // Set current project from localStorage or latest project
  useEffect(() => {
    if (authReady && isSignedIn && projects.length > 0) {
      const savedProjectId = localStorage.getItem('lastProjectId')
      
      if (savedProjectId && projects.find(p => p.id === savedProjectId)) {
        setCurrentProjectId(savedProjectId)
      } else {
        const latestProject = projects[0]
        if (latestProject) {
          setCurrentProjectId(latestProject.id)
          localStorage.setItem('lastProjectId', latestProject.id)
        }
      }
    }
  }, [authReady, isSignedIn, projects])

  const handleProjectInitialized = async (projectId?: string) => {
    if (projectId) {
      setCurrentProjectId(projectId)
      localStorage.setItem('lastProjectId', projectId)
      
      // Optimistic update - refresh projects list
      refetchProjects()
    }
    setShowProjectCreation(false)
    setProjectCreationType(null)
  }

  const handleOnboardingComplete = async () => {
    try {
      const response = await fetch('/api/users/v2/onboarding', {
        headers: {
          'Authorization': `Bearer ${await getToken()}`
        }
      })
      
      if (response.ok) {
        const data = await response.json()
        if (data.completed) {
          setOnboardingComplete(true)
          setShowOnboarding(false)
        }
      }
    } catch (error) {
      console.error('Error verifying onboarding completion:', error)
      setOnboardingComplete(true)
      setShowOnboarding(false)
    }
  }

  const navigateToWriting = () => {
    if (currentProjectId) {
      analytics.navigationClicked('chapters', currentProjectId)
      router.push(`/project/${currentProjectId}/chapters`)
    }
  }

  const navigateToReferences = () => {
    if (currentProjectId) {
      analytics.navigationClicked('references', currentProjectId)
      router.push(`/project/${currentProjectId}/references`)
    }
  }

  const navigateToOverview = () => {
    if (currentProjectId) {
      analytics.navigationClicked('overview', currentProjectId)
      router.push(`/project/${currentProjectId}/overview`)
    }
  }

  const handleDeleteProject = async (projectId: string) => {
    if (!projectId || isDeleting) return

    setIsDeleting(true)
    
    // Optimistically remove project from UI
    setOptimisticallyRemovedProjects(prev => new Set([...prev, projectId]))
    
    try {
      const token = await getToken()
      const response = await fetch(`/api/projects/${projectId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      })

            if (response.ok) {
        const deletedProject = projects.find(p => p.id === projectId)
        analytics.projectDeleted(projectId, deletedProject?.metadata?.title)
        
        // Remove from localStorage
        localStorage.removeItem(`bookBible-${projectId}`)
        if (localStorage.getItem('lastProjectId') === projectId) {
          localStorage.removeItem('lastProjectId')
        }

        // If this was the current project, clear it
        if (currentProjectId === projectId) {
          setCurrentProjectId(null)
        }

        // Refresh projects list
        refetchProjects()

      } else {
        // Handle both JSON and non-JSON error responses
        let errorMessage = 'Unknown error occurred'
        try {
          const errorData = await response.json()
          errorMessage = errorData.error || errorData.detail || errorMessage
        } catch {
          // Response body is not JSON (e.g., plain text or empty)
          errorMessage = `HTTP ${response.status}: ${response.statusText}`
        }
        
        errorMonitoring.trackProjectDeletionError(projectId, new Error(errorMessage))
        console.error('Failed to delete project:', errorMessage)
        alert(`Failed to delete project: ${errorMessage}`)
        
        // Restore project in UI since deletion failed
        setOptimisticallyRemovedProjects(prev => {
          const newSet = new Set(prev)
          newSet.delete(projectId)
          return newSet
        })
      }
    } catch (error) {
      errorMonitoring.trackProjectDeletionError(projectId, error)
      console.error('Error deleting project:', error)
      alert('Error deleting project. Please try again.')
      
      // Restore project in UI since deletion failed
      setOptimisticallyRemovedProjects(prev => {
        const newSet = new Set(prev)
        newSet.delete(projectId)
        return newSet
      })
    } finally {
      setIsDeleting(false)
      setShowDeleteConfirm(null)
    }
  }

  // Show loading state while auth is initializing
  if (!authReady) {
    return (
      <div className="min-h-screen bg-clean flex items-center justify-center">
        <div className="text-center">
          <div className="animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-3/4 mx-auto mb-2"></div>
            <div className="h-4 bg-gray-200 rounded w-1/2 mx-auto"></div>
          </div>
          <p className="mt-4 text-sm text-gray-500">Starting your writing workspace...</p>
        </div>
      </div>
    )
  }

  // Show sign-in prompt if user is not authenticated
  if (!isSignedIn) {
    return (
      <div className="min-h-screen bg-clean flex items-center justify-center">
        <div className="text-center max-w-md mx-auto px-6">
          <BookOpenIcon className="w-16 h-16 text-blue-600 mx-auto mb-6" />
          <h1 className="text-3xl font-bold text-gray-900 mb-4">
            Welcome to WriterBloom
          </h1>
          <p className="text-lg text-gray-600 mb-8">
            Your AI-powered writing companion for creating beautiful, professional books.
          </p>
          <p className="text-sm text-gray-500">
            Sign in to begin your writing journey
          </p>
        </div>
      </div>
    )
  }

  // Show onboarding flow for new users
  if (showOnboarding && !onboardingComplete) {
    return <OnboardingFlow onComplete={handleOnboardingComplete} />
  }

  // Show loading state while projects are loading
  if (projectsLoading) {
    return (
      <div className="min-h-screen bg-clean">
        {/* Clean Header */}
        <div className="bg-white border-b border-gray-200">
          <div className="max-w-4xl mx-auto px-6 py-8">
            <div className="text-center">
              <h1 className="text-4xl font-bold text-gray-900 mb-2">
                WriterBloom
              </h1>
              <p className="text-lg text-gray-600">
                Your creative writing studio
              </p>
            </div>
          </div>
        </div>

        <div className="max-w-4xl mx-auto px-6 py-12">
          <div className="text-center mb-8">
            <SkeletonPlaceholder type="text" lines={1} width="w-1/3" height="h-8" className="mx-auto mb-4" />
            <SkeletonPlaceholder type="text" lines={1} width="w-1/4" height="h-4" className="mx-auto" />
          </div>

          {/* Loading skeleton for action cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <SkeletonPlaceholder type="card" />
            <SkeletonPlaceholder type="card" />
            <SkeletonPlaceholder type="card" />
          </div>
        </div>
      </div>
    )
  }

  // Main Dashboard - Clean and Writing-Focused
  return (
    <div className="min-h-screen bg-clean">
      
      {/* HARDCODED TEST LOADER - REMOVE AFTER VERIFICATION */}
      <div className="p-4 bg-red-100 border border-red-400">
        <h3 className="text-red-800 font-bold">HARDCODED LOADER TEST:</h3>
        <CreativeLoader
          isVisible={true}
          progress={50}
          stage="Testing"
          customMessages={["🧪 Testing if loader works...", "🔧 Debugging deployment..."]}
          showProgress={true}
          size="sm"
        />
      </div>
      
      {/* Clean Header */}
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-4xl mx-auto px-6 py-8">
          <div className="text-center">
            <h1 className="text-4xl font-bold text-gray-900 mb-2">
              WriterBloom
            </h1>
            <p className="text-lg text-gray-600">
              Your creative writing studio
            </p>
          </div>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-6 py-12">
        {/* No Project State */}
        {projects.length === 0 ? (
          <div className="text-center py-16">
            {/* Enhanced Illustration */}
            <div className="relative mb-8">
              <div className="w-32 h-32 mx-auto bg-gradient-to-br from-blue-100 to-purple-100 rounded-full flex items-center justify-center">
                <DocumentTextIcon className="w-16 h-16 text-blue-600" />
              </div>
              <div className="absolute -top-2 -right-8 w-8 h-8 bg-yellow-200 rounded-full flex items-center justify-center">
                <PencilIcon className="w-4 h-4 text-yellow-700" />
              </div>
              <div className="absolute -bottom-2 -left-8 w-6 h-6 bg-green-200 rounded-full flex items-center justify-center">
                <CheckCircleIcon className="w-3 h-3 text-green-700" />
              </div>
            </div>
            
            <h2 className="text-3xl font-bold text-gray-900 mb-4">
              Welcome to WriterBloom!
            </h2>
            <h3 className="text-xl font-semibold text-gray-700 mb-6">
              Your AI-Powered Writing Studio
            </h3>
            
            <div className="max-w-2xl mx-auto mb-8">
              <p className="text-gray-600 mb-6">
                Transform your ideas into captivating stories with AI assistance. Whether you're starting with a detailed book bible or just a spark of inspiration, WriterBloom helps you:
              </p>
              
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                <div className="p-4 bg-blue-50 rounded-lg">
                  <BookOpenIcon className="w-8 h-8 text-blue-600 mx-auto mb-2" />
                  <h4 className="font-semibold text-gray-900 mb-1">Generate References</h4>
                  <p className="text-sm text-gray-600">AI creates rich character profiles, plot outlines, and world-building materials</p>
                </div>
                
                <div className="p-4 bg-green-50 rounded-lg">
                  <PencilIcon className="w-8 h-8 text-green-600 mx-auto mb-2" />
                  <h4 className="font-semibold text-gray-900 mb-1">Write Chapters</h4>
                  <p className="text-sm text-gray-600">Clean writing interface with AI assistance and quality assessment</p>
                </div>
                
                <div className="p-4 bg-purple-50 rounded-lg">
                  <CheckCircleIcon className="w-8 h-8 text-purple-600 mx-auto mb-2" />
                  <h4 className="font-semibold text-gray-900 mb-1">Polish & Perfect</h4>
                  <p className="text-sm text-gray-600">Quality gates ensure each chapter meets professional standards</p>
                </div>
              </div>
              
              <p className="text-gray-600 font-medium">
                Ready to begin your writing journey?
              </p>
            </div>
            
            <button
              onClick={() => {
                setShowProjectCreation(true)
                analytics.modalOpened('project-creation')
              }}
              className="inline-flex items-center px-8 py-4 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-700 hover:to-purple-700 transition-all transform hover:scale-105 shadow-lg font-medium text-lg"
            >
              <PlusCircleIcon className="w-6 h-6 mr-3" />
              Create Your First Project
            </button>
          </div>
        ) : (
          /* Project Dashboard */
          <div className="space-y-12">
            {/* Current Project Header */}
            <div className="text-center">
              <div className="flex items-center justify-center space-x-4 mb-6">
                <select
                  value={currentProjectId || ''}
                  onChange={(e) => {
                    const newProjectId = e.target.value
                    const selectedProject = projects.find(p => p.id === newProjectId)
                    setCurrentProjectId(newProjectId)
                    localStorage.setItem('lastProjectId', newProjectId)
                    analytics.projectSelected(newProjectId, selectedProject?.metadata?.title)
                  }}
                  className="text-2xl font-semibold text-gray-900 bg-transparent border-none focus:ring-0 cursor-pointer hover:text-blue-600 transition-colors"
                >
                  {projects.map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.metadata?.title || `Project ${project.id}`}
                    </option>
                  ))}
                </select>
                
                <div className="flex items-center space-x-2">
                                  <button
                  onClick={() => {
                    setShowProjectCreation(true)
                    analytics.modalOpened('project-creation')
                  }}
                  className="p-2 text-gray-400 hover:text-blue-600 transition-colors"
                  title="Create new project"
                >
                    <PlusCircleIcon className="w-6 h-6" />
                  </button>
                  
                  {currentProjectId && projects.length > 1 && (
                    <button
                      onClick={() => setShowDeleteConfirm(currentProjectId)}
                      className="p-2 text-gray-400 hover:text-red-600 transition-colors"
                      title="Delete current project"
                    >
                      <TrashIcon className="w-6 h-6" />
                    </button>
                  )}
                </div>
              </div>
              
              {currentProject && (
                <div className="text-gray-600">
                  {currentProject.settings?.genre && (
                    <span className="inline-block px-3 py-1 bg-gray-100 rounded-full text-sm mr-2">
                      {currentProject.settings.genre}
                    </span>
                  )}
                  <span className="text-sm">
                    {currentProject.progress?.chapters_completed || 0} chapters written
                  </span>
                </div>
              )}
            </div>

            {/* Chapter Preview Section */}
            {currentProject && chapters.length > 0 && (
              <div className="bg-white rounded-xl border border-gray-200 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-gray-900">Recent Chapters</h3>
                  <button
                    onClick={navigateToWriting}
                    className="text-sm text-blue-600 hover:text-blue-700 font-medium"
                  >
                    View all chapters →
                  </button>
                </div>
                
                {chaptersLoading ? (
                  <div className="space-y-3">
                    <SkeletonPlaceholder type="text" lines={1} width="w-full" height="h-4" />
                    <SkeletonPlaceholder type="text" lines={1} width="w-3/4" height="h-4" />
                    <SkeletonPlaceholder type="text" lines={1} width="w-1/2" height="h-4" />
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {chapters.slice(0, 3).map((chapter) => (
                      <div 
                        key={chapter.id} 
                        className="p-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors cursor-pointer"
                        onClick={() => {
                          analytics.chapterClicked(chapter.chapter_number, currentProjectId)
                          router.push(`/project/${currentProjectId}/chapters#chapter-${chapter.chapter_number}`)
                        }}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <h4 className="font-medium text-gray-900">
                            {chapter.title || `Chapter ${chapter.chapter_number}`}
                          </h4>
                          <span className="text-xs text-gray-500">
                            #{chapter.chapter_number}
                          </span>
                        </div>
                        
                        <div className="flex items-center justify-between text-sm text-gray-600">
                          <span>{chapter.metadata.word_count.toLocaleString()} words</span>
                          <span>
                            {new Date(chapter.metadata.updated_at).toLocaleDateString()}
                          </span>
                        </div>
                        
                        {chapter.quality_scores.overall_rating > 0 && (
                          <div className="mt-2 flex items-center">
                            <div className="w-full bg-gray-200 rounded-full h-1.5">
                              <div 
                                className="bg-green-600 h-1.5 rounded-full" 
                                style={{ width: `${chapter.quality_scores.overall_rating * 10}%` }}
                              ></div>
                            </div>
                            <span className="text-xs text-gray-500 ml-2">
                              {chapter.quality_scores.overall_rating}/10
                            </span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Primary Actions - Clean and Focused */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* Start Writing */}
              <button
                onClick={navigateToWriting}
                disabled={!currentProjectId}
                className="group p-8 bg-white border-2 border-gray-200 rounded-xl hover:border-blue-300 hover:shadow-lg transition-all text-left disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <div className="flex items-center justify-between mb-4">
                  <PencilIcon className="w-8 h-8 text-blue-600" />
                  <ArrowRightIcon className="w-5 h-5 text-gray-400 group-hover:text-blue-600 transition-colors" />
                </div>
                <h3 className="text-xl font-semibold text-gray-900 mb-2">
                  Start Writing
                </h3>
                <p className="text-gray-600">
                  Enter the clean writing workspace and focus on your story
                </p>
              </button>

              {/* Review References */}
              <button
                onClick={navigateToReferences}
                disabled={!currentProjectId}
                className="group p-8 bg-white border-2 border-gray-200 rounded-xl hover:border-green-300 hover:shadow-lg transition-all text-left disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <div className="flex items-center justify-between mb-4">
                  <BookOpenIcon className="w-8 h-8 text-green-600" />
                  <ArrowRightIcon className="w-5 h-5 text-gray-400 group-hover:text-green-600 transition-colors" />
                </div>
                <h3 className="text-xl font-semibold text-gray-900 mb-2">
                  Story References
                </h3>
                <p className="text-gray-600">
                  Review characters, plot, and world-building materials
                </p>
              </button>

              {/* Project Overview */}
              <button
                onClick={navigateToOverview}
                disabled={!currentProjectId}
                className="group p-8 bg-white border-2 border-gray-200 rounded-xl hover:border-purple-300 hover:shadow-lg transition-all text-left disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <div className="flex items-center justify-between mb-4">
                  <DocumentTextIcon className="w-8 h-8 text-purple-600" />
                  <ArrowRightIcon className="w-5 h-5 text-gray-400 group-hover:text-purple-600 transition-colors" />
                </div>
                <h3 className="text-xl font-semibold text-gray-900 mb-2">
                  Project Settings
                </h3>
                <p className="text-gray-600">
                  Manage your project settings and automation
                </p>
              </button>
            </div>

            {/* Auto-Complete Section */}
            {currentProjectId && (
              <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl p-8">
                <div className="max-w-2xl mx-auto text-center mb-8">
                  <h3 className="text-2xl font-semibold text-gray-900 mb-4">
                    AI Auto-Complete
                  </h3>
                  <p className="text-gray-600">
                    Let our AI write entire chapters automatically while you focus on the creative direction
                  </p>
                </div>
                
                <AutoCompleteBookManager 
                  onJobStarted={() => {}}
                  onJobCompleted={() => {}}
                  projectId={currentProjectId}
                />
              </div>
            )}
          </div>
        )}

        {/* Project Creation Modal */}
        {showProjectCreation && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div ref={projectCreationModalRef} className="bg-white rounded-xl p-8 max-w-2xl w-full max-h-[90vh] overflow-y-auto">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-2xl font-semibold text-gray-900">
                  Create New Project
                </h2>
                <button
                  onClick={() => {
                    setShowProjectCreation(false)
                    setProjectCreationType(null)
                    analytics.modalClosed('project-creation')
                  }}
                  className="text-gray-400 hover:text-gray-600 transition-colors"
                  aria-label="Close"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              
              {/* Project Creation Options */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
                {/* Upload Book Bible Option */}
                <div className="border-2 border-gray-200 rounded-xl p-6 hover:border-blue-300 transition-colors">
                  <div className="text-center">
                    <DocumentTextIcon className="w-12 h-12 mx-auto text-blue-600 mb-4" />
                    <h3 className="text-lg font-semibold text-gray-900 mb-2">
                      Upload Book Bible
                    </h3>
                    <p className="text-sm text-gray-600 mb-4">
                      Start with your existing book bible document for rich AI-generated references
                    </p>
                    <button
                      onClick={() => setProjectCreationType('upload')}
                      className="btn-primary w-full"
                    >
                      Choose This Option
                    </button>
                  </div>
                </div>

                {/* Start Blank Option */}
                <div className="border-2 border-gray-200 rounded-xl p-6 hover:border-green-300 transition-colors">
                  <div className="text-center">
                    <PencilIcon className="w-12 h-12 mx-auto text-green-600 mb-4" />
                    <h3 className="text-lg font-semibold text-gray-900 mb-2">
                      Start from Scratch
                    </h3>
                    <p className="text-sm text-gray-600 mb-4">
                      Begin with a blank project and build your story step by step
                    </p>
                    <button
                      onClick={() => setProjectCreationType('blank')}
                      className="btn-secondary w-full"
                    >
                      Choose This Option
                    </button>
                  </div>
                </div>
              </div>

              {/* Show chosen creation method */}
              {projectCreationType === 'upload' && (
                <BookBibleUpload onProjectInitialized={handleProjectInitialized} />
              )}
              
              {projectCreationType === 'blank' && (
                <BlankProjectCreator onProjectInitialized={handleProjectInitialized} />
              )}
            </div>
          </div>
        )}

        {/* Delete Confirmation Modal */}
        {showDeleteConfirm && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div ref={deleteConfirmModalRef} className="bg-white rounded-xl p-6 max-w-md w-full">
              <div className="text-center">
                <TrashIcon className="w-12 h-12 mx-auto text-red-600 mb-4" />
                <h3 className="text-lg font-semibold text-gray-900 mb-2">
                  Delete Project
                </h3>
                <p className="text-gray-600 mb-6">
                  Are you sure you want to delete "{projects.find(p => p.id === showDeleteConfirm)?.metadata?.title || 'this project'}"? 
                  This action cannot be undone and will permanently remove all chapters, references, and data.
                </p>
                
                <div className="flex space-x-3">
                  <button
                    onClick={() => {
                      setShowDeleteConfirm(null)
                      analytics.modalClosed('delete-confirmation')
                    }}
                    disabled={isDeleting}
                    className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => handleDeleteProject(showDeleteConfirm)}
                    disabled={isDeleting}
                    className="flex-1 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50"
                  >
                    {isDeleting ? 'Deleting...' : 'Delete Project'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
} 

// Force this page to be dynamic to prevent build-time prerendering
export const dynamic = 'force-dynamic'
export const runtime = 'nodejs' 