'use client'

import { useState, useEffect } from 'react'
import { useAuth } from '@clerk/nextjs'
import { useRouter } from 'next/navigation'
import { BookBibleUpload } from '@/components/BookBibleUpload'
import { BlankProjectCreator } from '@/components/BlankProjectCreator'
import { AutoCompleteBookManager } from '@/components/AutoCompleteBookManager'
import ProjectPublishPicker from '@/components/ProjectPublishPicker'
import OnboardingFlow from '@/components/OnboardingFlow'
import { useUserProjects, useProject, useProjectChapters } from '@/hooks/useFirestore'
import { useFocusTrap } from '@/hooks/useFocusTrap'
import { useAnalytics } from '@/lib/analytics'
import { useErrorMonitoring } from '@/lib/errorMonitoring'
import { SkeletonPlaceholder } from '@/components/ui/SkeletonPlaceholder'
import JourneyCard from '@/components/JourneyCard'

import ImmersiveHero from '@/components/ImmersiveHero'
import { UI_STRINGS } from '@/lib/strings'
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
  const { getToken, isLoaded, isSignedIn, userId, user } = useAuth()
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
  
  // Fetch chapters for all projects to show proper progress
  const [allProjectChapters, setAllProjectChapters] = useState<Record<string, any[]>>({})

  // Filter out optimistically removed projects
  const projects = rawProjects.filter(project => !optimisticallyRemovedProjects.has(project.id))
  
  // Fetch chapters for all projects for progress indicators
  useEffect(() => {
    const fetchAllChapters = async () => {
      if (!authReady || !projects.length) return
      
      const newChapters: Record<string, any[]> = {}
      
      await Promise.all(
        projects.map(async (project) => {
          try {
            const token = await getToken()
            if (!token) return
            
            const response = await fetch(`/api/projects/${project.id}/chapters`, {
              headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
              }
            })
            
            if (response.ok) {
              const data = await response.json()
              // Transform chapters to match JourneyCard interface
              const transformedChapters = (data.chapters || []).map((chapter: any) => {
                // More robust word count extraction - try multiple possible locations
                const wordCount = chapter.metadata?.word_count || 
                                  chapter.word_count || 
                                  (chapter.content ? chapter.content.split(' ').length : 0) ||
                                  0
                
                const stage = chapter.metadata?.stage || chapter.stage || 'draft'
                const targetWordCount = chapter.metadata?.target_word_count || 
                                       chapter.target_word_count || 
                                       2000
                
                return {
                  id: chapter.id,
                  chapter_number: chapter.chapter_number,
                  stage: stage,
                  word_count: wordCount,
                  target_word_count: targetWordCount
                }
              })
              newChapters[project.id] = transformedChapters
            }
          } catch (error) {
            console.error(`Failed to fetch chapters for project ${project.id}:`, error)
            newChapters[project.id] = []
          }
        })
      )
      
      setAllProjectChapters(newChapters)
    }
    
    fetchAllChapters()
  }, [projects.length, authReady]) // Remove getToken from dependencies

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

  // Track dashboard views and set user ID (stable dependencies)
  useEffect(() => {
    if (authReady && isSignedIn && userId) {
      analytics.setUserId(userId)
      analytics.pageViewed('dashboard')
      errorMonitoring.setUserId(userId)
    }
  }, [authReady, isSignedIn, userId]) // Remove unstable objects from dependencies

  const handleProjectInitialized = async (projectId?: string) => {
    if (projectId) {
      setCurrentProjectId(projectId)
      localStorage.setItem('lastProjectId', projectId)
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

  // Show loading state while auth is initializing
  if (!authReady) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-brand-lavender via-brand-ink-blue to-brand-blush-orange relative overflow-hidden">
        {/* Background floating elements */}
        <div className="absolute inset-0">
          <div className="absolute top-1/4 left-1/4 w-2 h-2 bg-white/20 rounded-full animate-float"></div>
          <div className="absolute top-1/3 right-1/4 w-1 h-1 bg-white/30 rounded-full animate-float" style={{animationDelay: '2s'}}></div>
          <div className="absolute bottom-1/3 left-1/3 w-3 h-3 bg-white/10 rounded-full animate-float" style={{animationDelay: '4s'}}></div>
        </div>
        
        <div className="relative z-10 flex items-center justify-center min-h-screen px-6">
          <div className="text-center">
            <div className="mb-8">
              <div className="w-16 h-16 border-4 border-white/30 border-t-white/80 rounded-full animate-spin mx-auto mb-6"></div>
            </div>
            <h1 className="text-2xl md:text-3xl font-bold text-white mb-3">
              Welcome back, <span className="font-serif italic">{user?.firstName || 'Writer'}</span>
            </h1>
            <p className="text-white/80 text-lg font-medium">
              Preparing your creative studio...
            </p>
          </div>
        </div>
      </div>
    )
  }

  // Show sign-in prompt if user is not authenticated
  if (!isSignedIn) {
    return (
      <div className="min-h-screen bg-brand-sand flex items-center justify-center">
        <div className="text-center max-w-md mx-auto px-6">
          <BookOpenIcon className="w-16 h-16 text-brand-soft-purple mx-auto mb-6" />
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
      <div className="min-h-screen bg-brand-off-white">
        {/* Immersive loading hero matching the real hero */}
        <div className="relative min-h-[45vh] bg-gradient-to-br from-brand-lavender via-brand-ink-blue to-brand-blush-orange overflow-hidden">
          {/* Animated background particles */}
          <div className="absolute inset-0">
            <div className="absolute top-1/4 left-1/4 w-2 h-2 bg-white/20 rounded-full animate-float"></div>
            <div className="absolute top-1/3 right-1/4 w-1 h-1 bg-white/30 rounded-full animate-float" style={{animationDelay: '2s'}}></div>
            <div className="absolute bottom-1/3 left-1/3 w-3 h-3 bg-white/10 rounded-full animate-float" style={{animationDelay: '4s'}}></div>
          </div>
          
          {/* Radial overlay for focus */}
          <div className="absolute inset-0 bg-gradient-radial from-transparent via-transparent to-black/10"></div>
          
          <div className="relative z-10 flex items-center justify-center min-h-[45vh] px-6">
            <div className="text-center">
              <div className="mb-6">
                <div className="w-12 h-12 border-3 border-white/30 border-t-white/80 rounded-full animate-spin mx-auto mb-4"></div>
              </div>
              <h1 className="text-3xl md:text-4xl lg:text-5xl font-bold text-white mb-3 drop-shadow-lg">
                Welcome back, <span className="font-serif italic">{user?.firstName || 'Writer'}</span>
              </h1>
              <p className="text-white/90 text-lg md:text-xl font-medium mb-6">
                Getting your journeys ready...
              </p>
            </div>
          </div>
        </div>
        
        {/* Loading bookshelf skeleton */}
        <div className="w-full px-6 md:px-8 lg:px-12 py-12">
          <div className="text-center mb-10">
            <div className="h-8 bg-gray-200 rounded w-64 mx-auto mb-3 animate-pulse"></div>
            <div className="h-6 bg-gray-100 rounded w-48 mx-auto animate-pulse"></div>
          </div>
          
          <div className="bg-gradient-to-br from-white/40 via-brand-beige/30 to-brand-lavender/10 rounded-2xl p-8 backdrop-blur-sm border border-white/50 shadow-xl">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              <SkeletonPlaceholder type="card" />
              <SkeletonPlaceholder type="card" />
              <SkeletonPlaceholder type="card" />
            </div>
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
          title: projects[0].title,
          id: projects[0].id
        } : undefined}
        onCreateProject={() => {
          setShowProjectCreation(true)
          analytics.modalOpened('project-creation')
        }}
      />

      <div className="w-full px-6 md:px-8 lg:px-12 py-12">
        {/* No Project State */}
        {projects.length === 0 ? (
          <div className="text-center py-16">
            {/* Enhanced Illustration */}
            <div className="mb-8">
              <div className="w-32 h-32 mx-auto bg-gradient-to-br from-brand-soft-purple/20 to-brand-leaf/20 rounded-full flex items-center justify-center mb-6">
                <span className="text-6xl">🌱</span>
              </div>
              <div className="relative">
                <div className="absolute -top-4 -left-8 w-8 h-8 bg-brand-leaf/30 rounded-full flex items-center justify-center">
                  <PencilIcon className="w-4 h-4 text-green-700" />
                </div>
                <div className="absolute -bottom-2 -left-8 w-6 h-6 bg-brand-soft-purple/30 rounded-full flex items-center justify-center">
                  <CheckCircleIcon className="w-3 h-3 text-purple-700" />
                </div>
              </div>
            </div>
            
            <h2 className="text-3xl font-bold text-gray-900 mb-4">
              {UI_STRINGS.projects.noProjects}
            </h2>
            <h3 className="text-xl font-semibold text-gray-700 mb-6">
              Your story is waiting to bloom
            </h3>
            
            <div className="max-w-2xl mx-auto mb-8">
              <p className="text-gray-600 leading-relaxed">
                Transform your ideas into beautiful, professional books with AI-powered assistance. 
                From initial concept to published masterpiece, we'll guide you through every step of your creative journey.
              </p>
            </div>
            
            <button
              onClick={() => {
                setShowProjectCreation(true)
                analytics.modalOpened('project-creation')
              }}
              className="inline-flex items-center px-8 py-4 bg-gradient-to-r from-brand-soft-purple to-brand-leaf text-white rounded-lg hover:opacity-90 transition-all transform hover:scale-105 shadow-lg font-medium text-lg"
            >
              <span className="mr-3 text-xl">🌱</span>
              {UI_STRINGS.projects.create}
            </button>
          </div>
        ) : (
          /* Journey Dashboard */
          <div className="space-y-8">
            {/* Enhanced Creative Studio Header */}
            <div className="text-center mb-10">
              <h2 className="text-4xl md:text-5xl font-black text-brand-forest mb-3 tracking-tight">
                Your Creative Studio
              </h2>
            </div>

            {/* Textured background for card grid */}
            <div className="relative">
              {/* Subtle textured background */}
              <div className="absolute inset-0 bg-gradient-to-br from-brand-off-white/50 via-brand-beige/30 to-white/20 rounded-3xl border border-brand-lavender/10 -mx-4 -my-6"></div>
              
              {/* Bookshelf Grid with enhanced spacing */}
              <div className="relative z-10 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 px-4 py-6">
              {/* Enhanced New Journey Card - most energetic and inviting */}
              <div className="bloom-in">
                <div className="group relative">
                  {/* Gradient border with animation */}
                  <div className="absolute -inset-0.5 bg-gradient-to-r from-brand-lavender via-purple-400 to-brand-forest rounded-2xl opacity-70 group-hover:opacity-100 transition duration-500 blur-sm group-hover:blur-none"></div>
                  
                  <div className="relative bg-gradient-to-br from-white via-brand-lavender/5 to-brand-forest/5 rounded-2xl p-6 hover:shadow-2xl transition-all duration-500 hover:-translate-y-4 hover:scale-[1.03] backdrop-blur-sm min-h-[320px] flex flex-col items-center justify-center text-center border border-white/50">
                    
                    {/* Floating animated elements */}
                    <div className="absolute top-4 left-4 w-2 h-2 bg-brand-lavender/40 rounded-full animate-pulse"></div>
                    <div className="absolute top-8 right-6 w-1.5 h-1.5 bg-purple-400/40 rounded-full animate-pulse" style={{animationDelay: '0.5s'}}></div>
                    <div className="absolute bottom-6 left-6 w-1 h-1 bg-brand-forest/40 rounded-full animate-pulse" style={{animationDelay: '1s'}}></div>
                    
                    {/* Plus icon with enhanced animation */}
                    <div className="w-20 h-20 bg-gradient-to-br from-brand-lavender via-purple-400 to-brand-forest rounded-full flex items-center justify-center mb-5 group-hover:scale-110 group-hover:rotate-180 transition-all duration-500 shadow-xl group-hover:shadow-2xl relative overflow-hidden">
                      <div className="absolute inset-0 bg-gradient-to-br from-white/30 to-transparent rounded-full"></div>
                      <svg className="w-10 h-10 text-white relative z-10 group-hover:scale-110 transition-transform duration-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
                      </svg>
                    </div>
                    
                    <h3 className="text-2xl font-black text-brand-forest mb-3 group-hover:text-brand-lavender transition-colors duration-300 tracking-tight">
                      Begin a New Journey
                    </h3>
                    
                    <p className="text-sm font-semibold text-brand-forest/80 mb-6 leading-relaxed max-w-xs">
                      Every great story starts with a single word. What will yours be?
                    </p>
                    
                    <button
                      onClick={() => {
                        setShowProjectCreation(true)
                        analytics.modalOpened('project-creation')
                      }}
                      className="group/btn bg-gradient-to-r from-brand-forest to-brand-lavender text-white px-8 py-3.5 rounded-xl text-sm font-bold hover:shadow-xl hover:shadow-brand-lavender/30 hover:scale-110 transition-all duration-300 flex items-center space-x-2 relative overflow-hidden"
                    >
                      <span className="relative z-10">Start Writing</span>
                      <svg className="w-5 h-5 relative z-10 group-hover/btn:translate-x-1 transition-transform duration-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                      </svg>
                      {/* Enhanced hover glow */}
                      <div className="absolute inset-0 bg-gradient-to-r from-white/30 to-white/20 opacity-0 group-hover/btn:opacity-100 transition-opacity duration-300"></div>
                    </button>
                  </div>
                </div>
              </div>

              {/* Existing Journey Cards */}
              {projects.map((project, index) => (
                <div key={project.id} className="bloom-in" style={{ animationDelay: `${(index + 1) * 100}ms` }}>
                  <JourneyCard
                    project={project}
                    chapters={allProjectChapters[project.id] || []}
                    onEdit={(projectId) => {
                      console.log('Edit project:', projectId)
                    }}
                  />
                </div>
                              ))}
               </div>
            </div>
            
            {/* Quick Stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-8">
              <div className="bg-white/60 backdrop-blur-sm rounded-lg p-4 text-center border border-brand-lavender/20 hover:bg-white/70 transition-all">
                <div className="text-2xl font-bold text-brand-lavender">{projects.length}</div>
                <div className="text-sm text-brand-forest/70">{UI_STRINGS.projects.plural}</div>
              </div>
              <div className="bg-white/60 backdrop-blur-sm rounded-lg p-4 text-center border border-brand-lavender/20 hover:bg-white/70 transition-all">
                <div className="text-2xl font-bold text-brand-forest">
                  {projects.filter(p => p.status === 'active').length}
                </div>
                <div className="text-sm text-brand-forest/70">Active</div>
              </div>
              <div className="bg-white/60 backdrop-blur-sm rounded-lg p-4 text-center border border-brand-lavender/20 hover:bg-white/70 transition-all">
                <div className="text-2xl font-bold text-brand-orange">
                  {projects.filter(p => p.status === 'completed').length}
                </div>
                <div className="text-sm text-brand-forest/70">Completed</div>
              </div>
              <div className="bg-white/60 backdrop-blur-sm rounded-lg p-4 text-center border border-brand-lavender/20 hover:bg-white/70 transition-all">
                <div className="text-2xl font-bold text-brand-forest">
                  {chapters.reduce((sum, c) => sum + c.word_count, 0).toLocaleString()}
                </div>
                <div className="text-sm text-brand-forest/70">Total Words</div>
              </div>
            </div>

            {/* Legacy project selector - hidden but functional */}
            <div className="hidden">
              <select
                value={currentProjectId || ''}
                onChange={(e) => {
                  const newProjectId = e.target.value
                  const selectedProject = projects.find(p => p.id === newProjectId)
                  setCurrentProjectId(newProjectId)
                  localStorage.setItem('lastProjectId', newProjectId)
                  analytics.projectSelected(newProjectId, selectedProject?.metadata?.title)
                }}
              >
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.metadata?.title || `Project ${project.id}`}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}

        {/* Project Creation Modal */}
        {showProjectCreation && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div 
              ref={projectCreationModalRef}
              className="bg-white rounded-lg max-w-4xl w-full max-h-[90vh] overflow-y-auto"
            >
              <div className="p-6 border-b border-gray-200">
                <div className="flex items-center justify-between">
                  <h2 className="text-xl font-semibold text-gray-900">{UI_STRINGS.projects.create}</h2>
                  <button
                    onClick={() => {
                      setShowProjectCreation(false)
                      setProjectCreationType(null)
                    }}
                    className="text-gray-400 hover:text-gray-600"
                  >
                    <span className="sr-only">Close</span>
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              </div>

              <div className="p-6">
                {!projectCreationType ? (
                  <div className="grid md:grid-cols-2 gap-6">
                    <button
                      onClick={() => setProjectCreationType('upload')}
                      className="p-6 border-2 border-gray-200 rounded-lg hover:border-brand-soft-purple hover:bg-brand-sand/20 transition-all text-left"
                    >
                      <div className="text-3xl mb-4">📚</div>
                      <h3 className="text-lg font-semibold text-gray-900 mb-2">Upload Book Bible</h3>
                      <p className="text-gray-600">Start with an existing outline, character sheets, or story bible.</p>
                    </button>
                    
                    <button
                      onClick={() => setProjectCreationType('blank')}
                      className="p-6 border-2 border-gray-200 rounded-lg hover:border-brand-soft-purple hover:bg-brand-sand/20 transition-all text-left"
                    >
                      <div className="text-3xl mb-4">✨</div>
                      <h3 className="text-lg font-semibold text-gray-900 mb-2">Start Fresh</h3>
                      <p className="text-gray-600">Begin with a blank canvas and build your story from scratch.</p>
                    </button>
                  </div>
                ) : projectCreationType === 'upload' ? (
                  <BookBibleUpload onProjectInitialized={handleProjectInitialized} />
                ) : (
                  <BlankProjectCreator onProjectInitialized={handleProjectInitialized} />
                )}
              </div>
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

            {/* Inspirational Footer */}
            <div className="mt-16 text-center border-t border-brand-lavender/20 pt-8">
              <div className="max-w-2xl mx-auto">
                <p className="text-brand-forest/60 text-sm font-medium italic mb-4">
                  "The secret to getting ahead is getting started." — Mark Twain
                </p>
                <div className="flex items-center justify-center space-x-6 text-xs text-brand-forest/50">
                  <span>✨ Keep writing, keep growing</span>
                  <span>•</span>
                  <button className="hover:text-brand-lavender transition-colors font-medium">
                    Invite a friend to write with you
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