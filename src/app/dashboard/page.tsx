'use client'

import { useState, useEffect } from 'react'
import { useAuthToken } from '@/lib/auth'
import { fetchApi } from '@/lib/api-client'
import { useRouter } from 'next/navigation'
import OnboardingFlow from '@/components/OnboardingFlow'
import { useUserProjects } from '@/hooks/useFirestore'
import { useFocusTrap } from '@/hooks/useFocusTrap'
import { useAnalytics } from '@/lib/analytics'
import { useErrorMonitoring } from '@/lib/errorMonitoring'
import { SkeletonPlaceholder } from '@/components/ui/SkeletonPlaceholder'
import JourneyCard from '@/components/JourneyCard'

import ImmersiveHero from '@/components/ImmersiveHero'
import { UI_STRINGS } from '@/lib/strings'
import { 
  PencilIcon, 
  CheckCircleIcon,
  TrashIcon,
} from '@heroicons/react/24/outline'

export default function Dashboard() {
  const { getAuthHeaders, isLoaded, isSignedIn, user } = useAuthToken()
  const userId = user?.id
  const router = useRouter()
  const [authReady, setAuthReady] = useState(false)
  const [showOnboarding, setShowOnboarding] = useState(false)
  const [onboardingComplete, setOnboardingComplete] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<string | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [optimisticallyRemovedProjects, setOptimisticallyRemovedProjects] = useState<Set<string>>(new Set())

  const handleBeginNewJourney = () => {
    if (!isSignedIn) {
      window.location.href = '/sign-in'
      return
    }
    router.push('/create/paste-idea')
  }

  const { projects: rawProjects, loading: projectsLoading, refetch: refetchProjects } = useUserProjects()

  // Filter out optimistically removed projects
  const projects = rawProjects.filter(project => !optimisticallyRemovedProjects.has(project.id))
  
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

  // Track dashboard views and set user ID (stable dependencies)
  useEffect(() => {
    if (authReady && isSignedIn && userId) {
      analytics.setUserId(userId)
      analytics.pageViewed('dashboard')
      errorMonitoring.setUserId(userId)
    }
  }, [authReady, isSignedIn, userId]) // Remove unstable objects from dependencies

  const handleOnboardingComplete = async () => {
    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetch('/api/users/v2/onboarding', {
        headers: authHeaders
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

  const handleDeleteProject = async (projectId: string | null) => {
    if (!projectId) return
    try {
      setIsDeleting(true)
      // Optimistically hide the card
      setOptimisticallyRemovedProjects(prev => new Set(prev).add(projectId))

      const authHeaders = await getAuthHeaders()
      const response = await fetchApi(`/api/v2/projects/${encodeURIComponent(projectId)}`, {
        method: 'DELETE',
        headers: {
          ...authHeaders,
          'Content-Type': 'application/json'
        }
      })

      if (!response.ok) {
        // Revert optimistic removal
        setOptimisticallyRemovedProjects(prev => {
          const next = new Set(prev)
          next.delete(projectId)
          return next
        })
        console.error('Failed to delete project:', response.status, await response.text())
      }

      // If this was the last selected project, clear it
      try {
        const last = localStorage.getItem('lastProjectId')
        if (last === projectId) {
          localStorage.removeItem('lastProjectId')
        }
      } catch {}

      setShowDeleteConfirm(null)
      setIsDeleting(false)
      // Refresh projects list
      await refetchProjects()
    } catch (error) {
      console.error('Error deleting project:', error)
      // Revert optimistic removal on error
      setOptimisticallyRemovedProjects(prev => {
        const next = new Set(prev)
        if (projectId) next.delete(projectId)
        return next
      })
      setIsDeleting(false)
      setShowDeleteConfirm(null)
    }
  }

  // Show loading state while auth is initializing
  if (!authReady) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-900 via-indigo-950 to-gray-900 relative overflow-hidden">
        <div className="absolute top-0 right-0 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl" />
        <div className="absolute bottom-0 left-0 w-80 h-80 bg-violet-500/10 rounded-full blur-3xl" />
        <div className="relative z-10 flex items-center justify-center min-h-screen px-6">
          <div className="text-center">
            <div className="w-10 h-10 border-2 border-white/30 border-t-white/80 rounded-full animate-spin mx-auto mb-6"></div>
            <h1 className="text-2xl md:text-3xl font-bold text-white mb-3">
              Welcome back, <span className="text-indigo-300">{user?.firstName || 'Writer'}</span>
            </h1>
            <p className="text-white/60 text-base">
              Preparing your studio...
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

  if (projectsLoading) {
    return (
      <div className="min-h-screen bg-brand-off-white">
        <div className="relative w-full bg-gradient-to-br from-gray-900 via-indigo-950 to-gray-900 min-h-[32vh] flex items-center justify-center px-6 py-10">
          <div className="text-center">
            <div className="w-10 h-10 border-2 border-white/30 border-t-white/80 rounded-full animate-spin mx-auto mb-4"></div>
            <h1 className="text-2xl md:text-3xl font-bold text-white mb-2">
              Welcome back, <span className="text-indigo-300">{user?.firstName || 'Writer'}</span>
            </h1>
            <p className="text-white/60 text-base">Loading your books...</p>
          </div>
        </div>
        <div className="w-full px-4 sm:px-6 md:px-8 lg:px-12 py-10">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            <SkeletonPlaceholder type="card" />
            <SkeletonPlaceholder type="card" />
            <SkeletonPlaceholder type="card" />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-brand-off-white">
      {/* Immersive Hero Section */}
      <ImmersiveHero 
        projectCount={projects.length}
        mostActiveProject={projects.length > 0 ? {
          title: projects[0].metadata?.title || 'Untitled',
          id: projects[0].id
        } : undefined}
        onCreateProject={handleBeginNewJourney}
      />

      <div className="w-full px-4 sm:px-6 md:px-8 lg:px-12 py-10 sm:py-12">
        {/* No Project State */}
        {projects.length === 0 ? (
          <div className="text-center py-16 max-w-lg mx-auto">
            <div className="w-20 h-20 mx-auto bg-gray-100 rounded-2xl flex items-center justify-center mb-6">
              <PencilIcon className="w-8 h-8 text-gray-400" />
            </div>
            
            <h2 className="text-2xl font-bold text-gray-900 mb-3 tracking-tight">
              {UI_STRINGS.projects.noProjects}
            </h2>
            
            <p className="text-gray-500 leading-relaxed mb-8">
              Transform your ideas into professional books with AI-powered assistance.
              From concept to published manuscript — start your first project.
            </p>
            
            <button
              onClick={handleBeginNewJourney}
              className="inline-flex items-center gap-2 px-6 py-3 bg-indigo-500 text-white rounded-xl font-semibold text-sm hover:bg-indigo-400 transition shadow-lg shadow-indigo-500/25"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M12 5v14"/><path d="M5 12h14"/></svg>
              {UI_STRINGS.projects.create}
            </button>
          </div>
        ) : (
          <div className="space-y-8">
            <h2 className="text-2xl sm:text-3xl font-bold text-gray-900 tracking-tight">
              Your Books
            </h2>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              {projects.map((project) => (
                <JourneyCard
                  key={project.id}
                  project={project}
                  onDelete={(projectId) => {
                    setShowDeleteConfirm(projectId)
                    analytics.modalOpened('delete-confirmation')
                  }}
                />
              ))}
            </div>
            
            {/* Stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="bg-white rounded-lg border border-gray-200 p-4 text-center">
                <div className="text-2xl font-bold text-gray-900">{projects.length}</div>
                <div className="text-xs text-gray-500">{UI_STRINGS.projects.plural}</div>
              </div>
              <div className="bg-white rounded-lg border border-gray-200 p-4 text-center">
                <div className="text-2xl font-bold text-gray-900">
                  {projects.filter(p => p.status === 'active').length}
                </div>
                <div className="text-xs text-gray-500">Active</div>
              </div>
              <div className="bg-white rounded-lg border border-gray-200 p-4 text-center">
                <div className="text-2xl font-bold text-gray-900">
                  {projects.filter(p => p.status === 'completed').length}
                </div>
                <div className="text-xs text-gray-500">Completed</div>
              </div>
              <div className="bg-white rounded-lg border border-gray-200 p-4 text-center">
                <div className="text-2xl font-bold text-gray-900">
                  {projects.reduce((sum, p) => sum + (p.progress?.current_word_count || 0), 0).toLocaleString()}
                </div>
                <div className="text-xs text-gray-500">Total Words</div>
              </div>
            </div>

          </div>
        )}

        {/* Delete Confirmation Modal */}
        {showDeleteConfirm && (
          <div
            className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-modal-title"
          >
            <div ref={deleteConfirmModalRef} className="bg-white rounded-xl p-6 max-w-md w-full shadow-2xl">
              <div className="text-center">
                <TrashIcon className="w-12 h-12 mx-auto text-red-600 mb-4" />
                <h3 id="delete-modal-title" className="text-lg font-semibold text-gray-900 mb-2">
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
