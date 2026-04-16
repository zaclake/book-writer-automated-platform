'use client'

import React, { useCallback, useMemo, useState } from 'react'
import { useParams, useRouter, usePathname } from 'next/navigation'
import { 
  HomeIcon,
  DocumentTextIcon,
  BookOpenIcon,
  PhotoIcon,
  ArrowLeftIcon,
  RocketLaunchIcon,
  BoltIcon
} from '@heroicons/react/24/outline'
import { useUserProjects } from '@/hooks/useFirestore'

interface NavigationItem {
  id: string
  label: string
  href: string
  icon: React.ComponentType<{ className?: string }>
  description: string
}

interface ProjectNavigationProps {
  projectTitle?: string
  className?: string
}

function JourneySelector({
  projectId,
  projects,
  pathname,
  onNavigate,
}: {
  projectId: string
  projects: any[]
  pathname: string
  onNavigate: (href: string) => void
}) {
  const buildTargetHref = useCallback((newId: string) => {
    const parts = pathname.split('/')
    let sub = ''
    if (parts.length > 3) {
      sub = '/' + parts.slice(3).join('/')
    }
    if (!sub) sub = '/overview'
    return `/project/${newId}${sub}`
  }, [pathname])

  return (
    <div className="flex items-center gap-2 min-w-0">
      <select
        name="projectJourney"
        value={projectId}
        onChange={(e) => onNavigate(buildTargetHref(e.target.value))}
        className="min-w-[12rem] max-w-[50vw] bg-white border border-gray-300 rounded-md px-2 py-1 text-sm font-medium text-gray-900 focus:outline-none focus:ring-2 focus:ring-brand-soft-purple truncate"
        aria-label="Select current journey"
      >
        {projects.map((p: any) => (
          <option key={p.id} value={p.id}>
            {p.metadata?.title || `Project ${p.id}`}
          </option>
        ))}
        {projectId && !projects.find((p: any) => p.id === projectId) && (
          <option value={projectId}>{projectId}</option>
        )}
      </select>
    </div>
  )
}

export function ProjectNavigation({ projectTitle, className = '' }: ProjectNavigationProps) {
  const params = useParams()
  const router = useRouter()
  const pathname = usePathname()
  const projectId = params?.projectId as string
  const { projects } = useUserProjects()

  const projectList = useMemo(() => projects || [], [projects])

  const resolvedTitle = useMemo(() => {
    if (projectTitle) return projectTitle
    const match = projectList.find((p: any) => p.id === projectId)
    if (match?.metadata?.title) return match.metadata.title
    if (typeof localStorage !== 'undefined') {
      const cached = localStorage.getItem(`projectTitle-${projectId}`)
      if (cached) return cached
    }
    return 'Project'
  }, [projectTitle, projectList, projectId])

  const navigationItems: NavigationItem[] = useMemo(() => [
    { id: 'overview', label: 'Overview', href: `/project/${projectId}/overview`, icon: HomeIcon, description: 'Project dashboard and progress' },
    { id: 'chapters', label: 'Chapters', href: `/project/${projectId}/chapters`, icon: DocumentTextIcon, description: 'Write and manage chapters' },
    { id: 'auto-complete', label: 'Auto-Complete', href: `/project/${projectId}/auto-complete`, icon: BoltIcon, description: 'AI-powered automatic book completion' },
    { id: 'references', label: 'References', href: `/project/${projectId}/references`, icon: BookOpenIcon, description: 'Story bible and reference materials' },
    { id: 'cover-art', label: 'Cover Art', href: `/project/${projectId}/cover-art`, icon: PhotoIcon, description: 'Generate and manage book covers' },
    { id: 'publish', label: 'Publish', href: `/project/${projectId}/publish`, icon: RocketLaunchIcon, description: 'Export and publish your book' },
  ], [projectId])

  const isActiveHref = useCallback((href: string) => {
    if (!pathname) return false
    if (pathname === href) return true
    if (!pathname.startsWith(href)) return false
    const nextChar = pathname[href.length]
    return nextChar === '/' || nextChar === '?' || nextChar === '#' || nextChar === undefined
  }, [pathname])

  const handleNavigation = useCallback((href: string) => {
    router.push(href)
  }, [router])

  const handleBackToDashboard = useCallback(() => {
    router.push('/dashboard')
  }, [router])

  return (
    <div className={`bg-white border-b border-gray-200 ${className}`}>
      <div className="w-full px-4 sm:px-6 md:px-8 lg:px-12">
        {/* Breadcrumb Bar */}
        <div className="flex flex-col gap-3 py-4 border-b border-gray-100 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2 sm:gap-3 min-w-0">
            <button
              onClick={handleBackToDashboard}
              className="flex items-center space-x-2 text-sm sm:text-base text-gray-500 hover:text-gray-900 transition-colors group shrink-0"
            >
              <ArrowLeftIcon className="w-5 h-5 group-hover:-translate-x-1 transition-transform duration-200" />
              <span className="font-semibold whitespace-nowrap">Dashboard</span>
            </button>
            <span className="hidden sm:inline text-gray-300 shrink-0">/</span>
            <div className="text-gray-900 font-bold truncate text-sm sm:text-base min-w-0 max-w-[40vw]">
              {resolvedTitle}
            </div>
            {projectList.length > 1 && (
              <div className="hidden md:flex items-center gap-2 min-w-0">
                <JourneySelector
                  projectId={projectId}
                  projects={projectList}
                  pathname={pathname}
                  onNavigate={handleNavigation}
                />
              </div>
            )}
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="relative py-3">
          <div className="overflow-x-auto scrollbar-none">
          <nav className="flex items-center gap-1 min-w-max">
            {navigationItems.map((item) => {
              const Icon = item.icon
              const isActive = isActiveHref(item.href)
              
              return (
                <button
                  key={item.id}
                  onClick={() => handleNavigation(item.href)}
                  className={`group relative flex items-center space-x-1.5 sm:space-x-2 px-3 sm:px-4 py-2 rounded-lg font-semibold text-xs sm:text-sm whitespace-nowrap transition-all duration-200 ${
                    isActive
                      ? 'bg-gray-900 text-white shadow-sm'
                      : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                  }`}
                  title={item.description}
                  aria-current={isActive ? 'page' : undefined}
                >
                  <Icon className={`w-4 h-4 sm:w-5 sm:h-5 ${isActive ? 'scale-110' : ''}`} />
                  <span>{item.label}</span>
                </button>
              )
            })}
          </nav>
          </div>
          <div className="absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-white to-transparent pointer-events-none md:hidden" aria-hidden="true" />
          {projectList.length > 1 && (
            <div className="md:hidden pt-2">
              <JourneySelector
                projectId={projectId}
                projects={projectList}
                pathname={pathname}
                onNavigate={handleNavigation}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default ProjectNavigation
