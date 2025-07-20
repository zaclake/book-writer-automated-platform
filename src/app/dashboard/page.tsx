'use client'

import { useState, useEffect } from 'react'
import { useAuth } from '@clerk/nextjs'
import { ChapterGenerationForm } from '@/components/ChapterGenerationForm'
import { ChapterList } from '@/components/ChapterList'
import { QualityMetrics } from '@/components/QualityMetrics'
import { CostTracker } from '@/components/CostTracker'
import { SystemStatus } from '@/components/SystemStatus'
import { BookBibleUpload } from '@/components/BookBibleUpload'
import { ReferenceFileManager } from '@/components/ReferenceFileManager'
import { ProjectStatus } from '@/components/ProjectStatus'
import { AutoCompleteBookManager } from '@/components/AutoCompleteBookManager'
import OnboardingFlow from '@/components/OnboardingFlow'
import { useUserProjects, useProjectChapters, useProject } from '@/hooks/useFirestore'

export default function Dashboard() {
  const { getToken, isLoaded, isSignedIn, userId } = useAuth()
  const [isGenerating, setIsGenerating] = useState(false)
  const [metrics, setMetrics] = useState(null)
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const [projectInitialized, setProjectInitialized] = useState(false)
  const [authReady, setAuthReady] = useState(false)
  const [currentProjectId, setCurrentProjectId] = useState<string | null>(null)
  const [showOnboarding, setShowOnboarding] = useState(false)
  const [onboardingComplete, setOnboardingComplete] = useState(false)

  // Real-time Firestore hooks
  const { projects, loading: projectsLoading } = useUserProjects()
  const { chapters, loading: chaptersLoading } = useProjectChapters(currentProjectId)
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
          console.log('🔍 Checking onboarding status...')
          
          // Check if user has completed onboarding
          const response = await fetch('/api/users/v2/onboarding', {
            headers: {
              'Authorization': `Bearer ${await getToken()}`
            }
          })
          
          if (response.ok) {
            const data = await response.json()
            const completed = data.completed || false
            console.log(`📋 Onboarding status: ${completed ? 'completed' : 'pending'}`)
            
            setOnboardingComplete(completed)
            setShowOnboarding(!completed)
          } else if (response.status === 404 || response.status === 401) {
            // User profile doesn't exist yet or auth issue, show onboarding
            console.log('📋 No onboarding data found, showing onboarding flow')
            setOnboardingComplete(false)
            setShowOnboarding(true)
          } else {
            console.warn(`⚠️ Unexpected response status: ${response.status}`)
            // Default to showing onboarding for safety
            setOnboardingComplete(false)
            setShowOnboarding(true)
          }
        } catch (error) {
          console.error('❌ Error checking onboarding status:', error)
          // Default to showing onboarding for new users
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
        // Use saved project if it exists
        setCurrentProjectId(savedProjectId)
      } else {
        // Use the most recent project
        const latestProject = projects[0] // Projects are ordered by updated_at desc
        if (latestProject) {
          setCurrentProjectId(latestProject.id)
          localStorage.setItem('lastProjectId', latestProject.id)
        }
      }
    }
  }, [authReady, isSignedIn, projects])

  // Fetch metrics (keeping this as API call for now since it's calculated data)
  useEffect(() => {
    if (authReady && isSignedIn && currentProjectId) {
      fetchMetrics()
    }
  }, [refreshTrigger, authReady, isSignedIn, currentProjectId])

  const getAuthHeaders = async (): Promise<Record<string, string>> => {
    if (!isLoaded || !isSignedIn) {
      return {}
    }
    
    try {
      const token = await getToken()
      return token ? { Authorization: `Bearer ${token}` } : {}
    } catch (error) {
      console.error('Failed to get auth token:', error)
      return {}
    }
  }

  const fetchMetrics = async () => {
    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetch('/api/metrics', {
        headers: authHeaders
      })
      if (response.ok) {
        const data = await response.json()
        setMetrics(data)
      }
    } catch (error) {
      console.error('Failed to fetch metrics:', error)
    }
  }

  const handleGenerationComplete = () => {
    setIsGenerating(false)
    setRefreshTrigger(prev => prev + 1)
  }

  const handleProjectInitialized = (projectId?: string) => {
    setProjectInitialized(true)
    if (projectId) {
      setCurrentProjectId(projectId)
      localStorage.setItem('lastProjectId', projectId)
    }
    setRefreshTrigger(prev => prev + 1)
  }

  const handleAutoCompleteJobStarted = (jobId: string) => {
    console.log('Auto-complete job started:', jobId)
    setRefreshTrigger(prev => prev + 1)
  }

  const handleAutoCompleteJobCompleted = (jobId: string, result: any) => {
    console.log('Auto-complete job completed:', jobId, result)
    setRefreshTrigger(prev => prev + 1)
  }

  const handleOnboardingComplete = async () => {
    try {
      // Verify onboarding was actually saved on the server
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
          console.log('✅ Onboarding completed and verified')
        } else {
          console.warn('⚠️ Onboarding completion not confirmed by server')
          // Don't hide onboarding if server doesn't confirm completion
        }
      } else {
        console.error('❌ Failed to verify onboarding completion')
        // Don't hide onboarding if we can't verify
      }
    } catch (error) {
      console.error('Error verifying onboarding completion:', error)
      // Fallback to optimistic update
      setOnboardingComplete(true)
      setShowOnboarding(false)
    }
  }

  // Show loading state while auth is initializing
  if (!authReady) {
    return (
      <div className="px-4 py-6 sm:px-0">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">
            Chapter Generation Dashboard
          </h1>
          <p className="mt-2 text-lg text-gray-600">
            AI-powered book writing with automated quality assessment
          </p>
        </div>
        <div className="text-center py-8">
          <div className="animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-3/4 mx-auto mb-2"></div>
            <div className="h-4 bg-gray-200 rounded w-1/2 mx-auto"></div>
          </div>
          <p className="mt-4 text-sm text-gray-500">Loading authentication...</p>
        </div>
      </div>
    )
  }

  // Show sign-in prompt if user is not authenticated
  if (!isSignedIn) {
    return (
      <div className="px-4 py-6 sm:px-0">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">
            Chapter Generation Dashboard
          </h1>
          <p className="mt-2 text-lg text-gray-600">
            AI-powered book writing with automated quality assessment
          </p>
        </div>
        <div className="text-center py-16">
          <div className="max-w-md mx-auto">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">
              Please sign in to continue
            </h2>
            <p className="text-gray-600 mb-6">
              You need to be authenticated to access the book writing dashboard and its features.
            </p>
            <p className="text-sm text-gray-500">
              Click the &ldquo;Sign In&rdquo; button in the top right corner to get started.
            </p>
          </div>
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
      <div className="px-4 py-6 sm:px-0">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">
            Chapter Generation Dashboard
          </h1>
          <p className="mt-2 text-lg text-gray-600">
            AI-powered book writing with automated quality assessment
          </p>
        </div>
        <div className="text-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mx-auto"></div>
          <p className="mt-4 text-sm text-gray-500">Loading your projects...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="px-4 py-6 sm:px-0">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">
          Chapter Generation Dashboard
        </h1>
        <p className="mt-2 text-lg text-gray-600">
          AI-powered book writing with automated quality assessment
        </p>
        
        {/* Real-time sync indicator */}
        {(projectsLoading || chaptersLoading) && (
          <div className="mt-2 flex items-center text-sm text-blue-600">
            <div className="w-2 h-2 bg-blue-600 rounded-full animate-pulse mr-2"></div>
            Syncing data...
          </div>
        )}
        
        {/* Current project indicator */}
        {currentProject && (
          <div className="mt-2 text-sm text-gray-600">
            Current project: <span className="font-medium">{currentProject.metadata?.title || `Project ${currentProject.id}`}</span>
            <span className="mx-2">•</span>
            <span className="text-green-600">{chapters.length} chapters</span>
          </div>
        )}

        {/* Project Selector */}
        {projects.length > 0 && (
          <div className="mt-4 flex items-center space-x-4">
            <label htmlFor="project-select" className="text-sm font-medium text-gray-700">
              Switch Project:
            </label>
            <select
              id="project-select"
              value={currentProjectId || ''}
              onChange={(e) => {
                const newProjectId = e.target.value
                setCurrentProjectId(newProjectId)
                localStorage.setItem('lastProjectId', newProjectId)
              }}
              className="block w-64 px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
            >
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.metadata?.title || `Project ${project.id}`} 
                  {project.progress && ` (${project.progress.chapters_completed || 0} chapters)`}
                </option>
              ))}
            </select>
            
            {/* Real-time status indicator */}
            <div className="flex items-center text-xs text-gray-500">
              <div className="w-2 h-2 bg-green-500 rounded-full mr-1 animate-pulse"></div>
              Live sync enabled
            </div>
          </div>
        )}
      </div>

      {/* Status Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 mb-8">
        <div className="lg:col-span-1">
          <ProjectStatus projectId={currentProjectId} />
        </div>
        <div className="lg:col-span-1">
          <CostTracker metrics={metrics} />
        </div>
        <div className="lg:col-span-1">
          {/* Real-time Projects Overview */}
          <div className="card">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              Projects Overview
              {projectsLoading && (
                <span className="ml-2 text-sm text-blue-600">
                  <div className="inline-block w-2 h-2 bg-blue-600 rounded-full animate-pulse"></div>
                </span>
              )}
            </h2>
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-600">Total Projects</span>
                <span className="font-semibold text-lg">{projects.length}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-600">Active Projects</span>
                <span className="font-semibold text-lg text-green-600">
                  {projects.filter(p => p.metadata?.status === 'active').length}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-600">Total Chapters</span>
                <span className="font-semibold text-lg text-blue-600">
                  {projects.reduce((total, p) => total + (p.progress?.chapters_completed || 0), 0)}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-600">Current Project</span>
                <span className="font-semibold text-sm text-purple-600">
                  {chapters.length} chapters
                </span>
              </div>
            </div>
          </div>
        </div>
        <div className="lg:col-span-1">
          <QualityMetrics metrics={metrics} />
        </div>
      </div>

      {/* Quick Actions */}
      <div className="mb-8">
        <h2 className="text-xl font-semibold text-gray-900 mb-4">Quick Actions</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <button
            onClick={() => window.location.href = '/profile'}
            className="p-4 bg-white border border-gray-200 rounded-lg hover:border-blue-300 hover:shadow-md transition-all text-left"
          >
            <div className="text-2xl mb-2">👤</div>
            <div className="font-medium text-gray-900">User Profile</div>
            <div className="text-sm text-gray-600">Manage preferences</div>
          </button>
          
          <button
            onClick={() => {
              if (currentProjectId) {
                window.location.href = `/project/${currentProjectId}/chapters`
              }
            }}
            className="p-4 bg-white border border-gray-200 rounded-lg hover:border-green-300 hover:shadow-md transition-all text-left"
            disabled={!currentProjectId}
          >
            <div className="text-2xl mb-2">📝</div>
            <div className="font-medium text-gray-900">Chapter Editor</div>
            <div className="text-sm text-gray-600">Write & edit chapters</div>
          </button>
          
          <button
            onClick={() => {
              if (currentProjectId) {
                window.location.href = `/project/${currentProjectId}/references`
              }
            }}
            className="p-4 bg-white border border-gray-200 rounded-lg hover:border-purple-300 hover:shadow-md transition-all text-left"
            disabled={!currentProjectId}
          >
            <div className="text-2xl mb-2">🗂️</div>
            <div className="font-medium text-gray-900">References</div>
            <div className="text-sm text-gray-600">Characters & world-building</div>
          </button>
          
          <button
            onClick={() => {
              if (currentProjectId) {
                window.location.href = `/project/${currentProjectId}/overview`
              }
            }}
            className="p-4 bg-white border border-gray-200 rounded-lg hover:border-indigo-300 hover:shadow-md transition-all text-left"
            disabled={!currentProjectId}
          >
            <div className="text-2xl mb-2">📊</div>
            <div className="font-medium text-gray-900">Project Management</div>
            <div className="text-sm text-gray-600">Overview & settings</div>
          </button>
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 xl:grid-cols-4 gap-6">
        {/* Left Column - Book Bible Upload, Auto-Complete & Generation */}
        <div className="xl:col-span-1 space-y-6">
          <BookBibleUpload onProjectInitialized={handleProjectInitialized} />
          
          <AutoCompleteBookManager 
            onJobStarted={handleAutoCompleteJobStarted}
            onJobCompleted={handleAutoCompleteJobCompleted}
            projectId={currentProjectId}
          />
          
          <ChapterGenerationForm
            onGenerationStart={() => setIsGenerating(true)}
            onGenerationComplete={handleGenerationComplete}
            isGenerating={isGenerating}
          />
        </div>

        {/* Middle Column - Reference Files */}
        <div className="xl:col-span-1">
          <ReferenceFileManager />
        </div>

        {/* Right Column - Chapter List */}
        <div className="xl:col-span-2">
          <ChapterList 
            chapters={chapters}
            loading={chaptersLoading}
            onRefresh={() => setRefreshTrigger(prev => prev + 1)}
            projectId={currentProjectId}
          />
        </div>
      </div>
    </div>
  )
} 