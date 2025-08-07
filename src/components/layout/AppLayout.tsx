'use client'

import React, { useEffect, useState } from 'react'
import { usePathname } from 'next/navigation'
import { useUser, useAuth } from '@clerk/nextjs'
import TopNav from './TopNav'
import { SyncStatusIndicator } from '@/lib/firestore-offline'
import { ensureFirebaseInitialized } from '@/lib/firestore-client'
import { BuyCreditsModal, useGlobalBuyCreditsModal } from '@/components/BuyCreditsModal'
import { Toaster } from 'sonner'

interface AppLayoutProps {
  children: React.ReactNode
  currentProject?: {
    id: string
    title: string
    status: 'active' | 'completed' | 'archived' | 'paused'
  }
  showProjectNavigation?: boolean
}

const AppLayout: React.FC<AppLayoutProps> = ({
  children,
  currentProject: propCurrentProject,
  showProjectNavigation: propShowProjectNavigation = false
}) => {
  const { user, isLoaded } = useUser()
  const { getToken } = useAuth()
  const pathname = usePathname()
  const { modalProps } = useGlobalBuyCreditsModal()
  
  // Feature flag for new layout (defaults to true, set to 'false' to rollback)
  const useNewLayout = process.env.NEXT_PUBLIC_USE_NEW_LAYOUT !== 'false'
  
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
          
          const response = await fetch('/api/v2/projects', {
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

  if (!isLoaded) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-brand-sand">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-soft-purple mx-auto mb-4"></div>
          <p className="text-gray-600">Loading your creative space...</p>
        </div>
      </div>
    )
  }

  // Feature flag check - if disabled, show minimal layout for emergency rollback
  if (!useNewLayout) {
    return (
      <div className="min-h-screen bg-gray-50">
        <div className="bg-white border-b border-gray-200 p-4">
          <div className="max-w-7xl mx-auto">
            <h1 className="text-xl font-semibold">WriterBloom (Legacy Mode)</h1>
            <p className="text-sm text-gray-600">New layout disabled via feature flag</p>
          </div>
        </div>
        <main className="max-w-7xl mx-auto p-4">
          {children}
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      {/* Top Navigation */}
      <TopNav currentProject={currentProject} />

      {/* Main Content */}
      <main className="flex-1">
        <div className="w-full">
          {/* Sync Status Indicator - moved to top of content */}
          {user && (
            <div className="px-4 sm:px-6 lg:px-8 py-2">
              <SyncStatusIndicator showDetails />
            </div>
          )}
          
          {/* Content Area - No padding, let pages handle their own layout */}
          <div>
            {children}
          </div>
        </div>
      </main>

      {/* Global Buy Credits Modal */}
      <BuyCreditsModal {...modalProps} />

      {/* Global Toast Notifications */}
      <Toaster position="top-right" richColors />
    </div>
  )
}

export default AppLayout 