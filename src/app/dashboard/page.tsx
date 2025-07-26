'use client'

import { useState, useEffect } from 'react'
import { useAuth } from '@clerk/nextjs'
import { useRouter } from 'next/navigation'
import { BookBibleUpload } from '@/components/BookBibleUpload'
import { AutoCompleteBookManager } from '@/components/AutoCompleteBookManager'
import OnboardingFlow from '@/components/OnboardingFlow'
import { useUserProjects, useProject } from '@/hooks/useFirestore'
import { SkeletonPlaceholder } from '@/components/ui/SkeletonPlaceholder'
import { 
  PencilIcon, 
  BookOpenIcon, 
  DocumentTextIcon,
  PlusCircleIcon,
  ArrowRightIcon,
  CheckCircleIcon
} from '@heroicons/react/24/outline'

export default function Dashboard() {
  const { getToken, isLoaded, isSignedIn, userId } = useAuth()
  const router = useRouter()
  const [authReady, setAuthReady] = useState(false)
  const [currentProjectId, setCurrentProjectId] = useState<string | null>(null)
  const [showOnboarding, setShowOnboarding] = useState(false)
  const [onboardingComplete, setOnboardingComplete] = useState(false)
  const [showProjectCreation, setShowProjectCreation] = useState(false)

  // Real-time Firestore hooks
  const { projects, loading: projectsLoading } = useUserProjects()
  const { project: currentProject } = useProject(currentProjectId)

  // Track when auth is ready
  useEffect(() => {
    if (isLoaded) {
      setAuthReady(true)
    }
  }, [isLoaded])

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

  const handleProjectInitialized = (projectId?: string) => {
    if (projectId) {
      setCurrentProjectId(projectId)
      localStorage.setItem('lastProjectId', projectId)
    }
    setShowProjectCreation(false)
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
      router.push(`/project/${currentProjectId}/chapters`)
    }
  }

  const navigateToReferences = () => {
    if (currentProjectId) {
      router.push(`/project/${currentProjectId}/references`)
    }
  }

  const navigateToOverview = () => {
    if (currentProjectId) {
      router.push(`/project/${currentProjectId}/overview`)
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
            <DocumentTextIcon className="w-24 h-24 text-gray-300 mx-auto mb-8" />
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">
              Start Your First Book
            </h2>
            <p className="text-gray-600 mb-8 max-w-lg mx-auto">
              Create your first project by uploading a book bible or starting from scratch. 
              Our AI will help you generate reference materials and begin writing immediately.
            </p>
            
            <button
              onClick={() => setShowProjectCreation(true)}
              className="inline-flex items-center px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
            >
              <PlusCircleIcon className="w-5 h-5 mr-2" />
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
                    setCurrentProjectId(newProjectId)
                    localStorage.setItem('lastProjectId', newProjectId)
                  }}
                  className="text-2xl font-semibold text-gray-900 bg-transparent border-none focus:ring-0 cursor-pointer hover:text-blue-600 transition-colors"
                >
                  {projects.map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.metadata?.title || `Project ${project.id}`}
                    </option>
                  ))}
                </select>
                
                <button
                  onClick={() => setShowProjectCreation(true)}
                  className="p-2 text-gray-400 hover:text-blue-600 transition-colors"
                  title="Create new project"
                >
                  <PlusCircleIcon className="w-6 h-6" />
                </button>
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
            <div className="bg-white rounded-xl p-8 max-w-2xl w-full max-h-[90vh] overflow-y-auto">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-2xl font-semibold text-gray-900">
                  Create New Project
                </h2>
                <button
                  onClick={() => setShowProjectCreation(false)}
                  className="text-gray-400 hover:text-gray-600 transition-colors"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              
              <BookBibleUpload onProjectInitialized={handleProjectInitialized} />
            </div>
          </div>
        )}
      </div>
    </div>
  )
} 