'use client'

import React, { useEffect, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useUser, UserButton, useAuth } from '@clerk/nextjs'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { SyncStatusIndicator } from '@/lib/firestore-offline'
import { ensureFirebaseInitialized } from '@/lib/firestore-client'

interface NavigationTab {
  id: string
  label: string
  icon: string
  href: string
  description: string
  disabled?: boolean
}

interface AppLayoutProps {
  children: React.ReactNode
  currentProject?: {
    id: string
    title: string
    status: 'active' | 'completed' | 'archived' | 'paused'
  }
  showProjectNavigation?: boolean
}

const mainTabs: NavigationTab[] = [
  {
    id: 'dashboard',
    label: 'Dashboard',
    icon: '🏠',
    href: '/dashboard',
    description: 'Project overview and quick actions'
  },
  {
    id: 'create',
    label: 'Create Project',
    icon: '✨',
    href: '/create',
    description: 'Start a new book project'
  },
  {
    id: 'profile',
    label: 'Profile',
    icon: '👤',
    href: '/profile',
    description: 'Manage your profile and preferences'
  }
]

const projectTabs: NavigationTab[] = [
  {
    id: 'overview',
    label: 'Overview',
    icon: '📊',
    href: '/project/overview',
    description: 'Project dashboard and progress'
  },
  {
    id: 'chapters',
    label: 'Chapters',
    icon: '📝',
    href: '/project/chapters',
    description: 'Write and edit chapters'
  },
  {
    id: 'references',
    label: 'References',
    icon: '🗂️',
    href: '/project/references',
    description: 'Character sheets, outlines, and world-building'
  },
  {
    id: 'cover-art',
    label: 'Cover Art',
    icon: '🎨',
    href: '/project/cover-art',
    description: 'Generate professional book covers with AI'
  },
  {
    id: 'publish',
    label: 'Publish',
    icon: '📚',
    href: '/project/publish',
    description: 'Convert your book to EPUB, PDF, and other formats'
  },
  {
    id: 'quality',
    label: 'Quality',
    icon: '⭐',
    href: '/project/quality',
    description: 'Quality assessment and improvement suggestions'
  },
  {
    id: 'settings',
    label: 'Settings',
    icon: '⚙️',
    href: '/project/settings',
    description: 'Project configuration and preferences'
  }
]

const AppLayout: React.FC<AppLayoutProps> = ({
  children,
  currentProject: propCurrentProject,
  showProjectNavigation: propShowProjectNavigation = false
}) => {
  const { user, isLoaded } = useUser()
  const { getToken } = useAuth()
  const router = useRouter()
  const pathname = usePathname()
  
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [activeTabs, setActiveTabs] = useState<NavigationTab[]>(mainTabs)

  // Auto-detect project context from URL
  const isInProjectContext = pathname.startsWith('/project/')
  const projectIdFromUrl = isInProjectContext ? pathname.split('/')[2] : null
  
  // Load real project data when in project context
  const [fetchedProject, setFetchedProject] = useState<{ id: string; title: string; status: string } | null>(null)
  
  useEffect(() => {
    if (projectIdFromUrl && !propCurrentProject) {
      const loadProjectData = async () => {
        try {
          // Get auth headers for the API call
          const token = await getToken()
          if (!token) {
            console.log('📚 No auth token, using localStorage fallback')
            const storedTitle = localStorage.getItem(`projectTitle-${projectIdFromUrl}`)
            setFetchedProject({
              id: projectIdFromUrl,
              title: storedTitle || `Project ${projectIdFromUrl}`,
              status: 'active'
            })
            return
          }
          
          const response = await fetch('/api/projects', {
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json'
            }
          })
          if (response.ok) {
            const data = await response.json()
            console.log('📚 Loaded all projects for header, looking for:', projectIdFromUrl)
            
            // Find the specific project
            const project = data.projects?.find((p: any) => p.id === projectIdFromUrl)
            if (project) {
              console.log('📚 Found project in list:', project)
              setFetchedProject({
                id: projectIdFromUrl,
                title: project.metadata?.title || `Project ${projectIdFromUrl}`,
                status: project.metadata?.status || 'active'
              })
            } else {
              console.log('📚 Project not found in list, using localStorage fallback')
              // Fallback to localStorage
              const storedTitle = localStorage.getItem(`projectTitle-${projectIdFromUrl}`)
              setFetchedProject({
                id: projectIdFromUrl,
                title: storedTitle || `Project ${projectIdFromUrl}`,
                status: 'active'
              })
            }
          } else {
            // Fallback to localStorage
            const storedTitle = localStorage.getItem(`projectTitle-${projectIdFromUrl}`)
            setFetchedProject({
              id: projectIdFromUrl,
              title: storedTitle || `Project ${projectIdFromUrl}`,
              status: 'active'
            })
          }
        } catch (error) {
          console.error('Failed to load project data for header:', error)
          // Fallback
          setFetchedProject({
            id: projectIdFromUrl,
            title: `Project ${projectIdFromUrl}`,
            status: 'active'
          })
        }
      }
      
      loadProjectData()
    }
  }, [projectIdFromUrl, propCurrentProject])
  
  // Navigation tabs with dynamic 'active' property
  const showProjectNavigation = propShowProjectNavigation || isInProjectContext
  const currentProject = propCurrentProject || fetchedProject

  // Update active tabs based on project context
  useEffect(() => {
    if (showProjectNavigation && currentProject) {
      setActiveTabs(projectTabs)
    } else {
      setActiveTabs(mainTabs)
    }
  }, [showProjectNavigation, currentProject])

  // Ensure Firebase is initialized when user signs in
  useEffect(() => {
    if (isLoaded && user) {
      // When user is loaded and signed in, ensure Firebase is properly initialized
      // This helps with offline-to-online sync
      ensureFirebaseInitialized().then((success) => {
        if (success) {
          console.log('🔄 Firebase reinitialization check completed')
        } else {
          console.warn('⚠️ Firebase reinitialization failed or not needed')
        }
      })
    }
  }, [isLoaded, user])

  // Get current active tab
  const getActiveTab = () => {
    return activeTabs.find(tab => pathname.startsWith(tab.href)) || activeTabs[0]
  }

  const handleTabClick = (tab: NavigationTab) => {
    if (tab.disabled) return
    
    let fullHref = tab.href
    if (showProjectNavigation && currentProject) {
      fullHref = tab.href.replace('/project', `/project/${currentProject.id}`)
    }
    
    router.push(fullHref)
  }

  if (!isLoaded) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-pulse text-gray-500">Loading...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top Navigation */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Logo and Project Info */}
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-2">
                <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
                  <span className="text-white font-bold text-sm">BW</span>
                </div>
                <span className="font-semibold text-gray-900">Book Writer</span>
              </div>
              
              {currentProject && (
                <>
                  <div className="h-6 w-px bg-gray-300" />
                  <div className="flex items-center space-x-2">
                    <span className="text-sm text-gray-600">Project:</span>
                    <span className="font-medium text-gray-900">{currentProject.title}</span>
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                      currentProject.status === 'active' ? 'bg-green-100 text-green-800' :
                      currentProject.status === 'completed' ? 'bg-blue-100 text-blue-800' :
                      currentProject.status === 'paused' ? 'bg-yellow-100 text-yellow-800' :
                      'bg-gray-100 text-gray-800'
                    }`}>
                      {currentProject.status}
                    </span>
                  </div>
                </>
              )}
            </div>

            {/* Right side controls */}
            <div className="flex items-center space-x-4">
              <SyncStatusIndicator showDetails />
              
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
                className="lg:hidden"
              >
                ☰
              </Button>
              
              {user && <UserButton afterSignOutUrl="/" />}
            </div>
          </div>
        </div>
      </header>

      <div className="flex">
        {/* Sidebar Navigation */}
        <aside className={`bg-white border-r border-gray-200 transition-all duration-300 ${
          sidebarCollapsed ? 'w-16' : 'w-64'
        } lg:relative fixed inset-y-0 left-0 z-30 lg:translate-x-0 ${
          sidebarCollapsed ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        }`}>
          <div className="h-full flex flex-col pt-16 lg:pt-0">
            {/* Navigation Tabs */}
            <nav className="flex-1 px-3 py-6 space-y-2">
              <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-4">
                {showProjectNavigation ? 'Project' : 'Main'} Navigation
              </div>
              
              {activeTabs.map((tab) => {
                const isActive = getActiveTab()?.id === tab.id
                
                return (
                  <button
                    key={tab.id}
                    onClick={() => handleTabClick(tab)}
                    disabled={tab.disabled}
                    className={`w-full flex items-center px-3 py-2 text-sm font-medium rounded-lg transition-colors ${
                      isActive
                        ? 'bg-blue-100 text-blue-700 border border-blue-200'
                        : tab.disabled
                        ? 'text-gray-400 cursor-not-allowed'
                        : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                    }`}
                  >
                    <span className="text-lg mr-3">{tab.icon}</span>
                    {!sidebarCollapsed && (
                      <div className="flex-1 text-left">
                        <div>{tab.label}</div>
                        <div className="text-xs text-gray-500 mt-0.5">
                          {tab.description}
                        </div>
                      </div>
                    )}
                  </button>
                )
              })}
            </nav>

            {/* Bottom Actions */}
            <div className="p-3 border-t border-gray-200">
              {!sidebarCollapsed && (
                <div className="space-y-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full justify-start"
                    onClick={() => router.push('/help')}
                  >
                    <span className="mr-2">❓</span>
                    Help & Support
                  </Button>
                  
                  <Button
                    variant="ghost"
                    size="sm"
                    className="w-full justify-start"
                    onClick={() => setSidebarCollapsed(true)}
                  >
                    <span className="mr-2">📁</span>
                    Collapse
                  </Button>
                </div>
              )}
            </div>
          </div>
        </aside>

        {/* Overlay for mobile */}
        {!sidebarCollapsed && (
          <div
            className="fixed inset-0 bg-black bg-opacity-50 z-20 lg:hidden"
            onClick={() => setSidebarCollapsed(true)}
          />
        )}

        {/* Main Content */}
        <main className="flex-1 overflow-hidden">
          <div className="h-full">
            {/* Content Header */}
            <div className="bg-white border-b border-gray-200 px-6 py-4">
              <div className="flex items-center justify-between">
                <div>
                  <h1 className="text-xl font-semibold text-gray-900">
                    {getActiveTab()?.label}
                  </h1>
                  <p className="text-sm text-gray-600 mt-1">
                    {getActiveTab()?.description}
                  </p>
                </div>
                
                {/* Tab Actions */}
                <div className="flex items-center space-x-2">
                  {showProjectNavigation && currentProject && (
                    <>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => router.push('/dashboard')}
                      >
                        ← Back to Dashboard
                      </Button>
                      
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => router.push(`/project/${currentProject.id}/export`)}
                      >
                        📤 Export
                      </Button>
                    </>
                  )}
                </div>
              </div>
            </div>

            {/* Content Area */}
            <div className="h-full overflow-auto">
              <div className="p-6">
                {children}
              </div>
            </div>
          </div>
        </main>
      </div>

      {/* Keyboard shortcuts info */}
      <div className="hidden">
        <kbd className="px-2 py-1 text-xs font-semibold text-gray-800 bg-gray-100 border border-gray-200 rounded-lg">
          Ctrl+S
        </kbd>
        <span className="ml-2 text-sm text-gray-600">Save</span>
      </div>
    </div>
  )
}

export default AppLayout 