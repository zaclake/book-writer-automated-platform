'use client'

import React from 'react'
import { useParams, useRouter, usePathname } from 'next/navigation'
import { 
  HomeIcon,
  DocumentTextIcon,
  BookOpenIcon,
  CogIcon,
  PhotoIcon,
  ArrowLeftIcon,
  RocketLaunchIcon,
  BoltIcon
} from '@heroicons/react/24/outline'

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

export function ProjectNavigation({ projectTitle, className = '' }: ProjectNavigationProps) {
  const params = useParams()
  const router = useRouter()
  const pathname = usePathname()
  const projectId = params?.projectId as string

  const navigationItems: NavigationItem[] = [
    {
      id: 'overview',
      label: 'Overview',
      href: `/project/${projectId}/overview`,
      icon: HomeIcon,
      description: 'Project dashboard and progress'
    },
    {
      id: 'chapters',
      label: 'Chapters',
      href: `/project/${projectId}/chapters`,
      icon: DocumentTextIcon,
      description: 'Write and manage chapters'
    },
    {
      id: 'auto-complete',
      label: 'Auto-Complete',
      href: `/project/${projectId}/auto-complete`,
      icon: BoltIcon,
      description: 'AI-powered automatic book completion'
    },
    {
      id: 'references',
      label: 'References',
      href: `/project/${projectId}/references`,
      icon: BookOpenIcon,
      description: 'Story bible and reference materials'
    },
    {
      id: 'cover-art',
      label: 'Cover Art',
      href: `/project/${projectId}/cover-art`,
      icon: PhotoIcon,
      description: 'Generate and manage book covers'
    },
    {
      id: 'publish',
      label: 'Publish',
      href: `/project/${projectId}/publish`,
      icon: RocketLaunchIcon,
      description: 'Export and publish your book'
    },
    {
      id: 'settings',
      label: 'Settings',
      href: `/project/${projectId}/settings`,
      icon: CogIcon,
      description: 'Project configuration'
    }
  ]

  const currentPath = pathname
  const activeItem = navigationItems.find(item => currentPath?.startsWith(item.href))

  const handleNavigation = (href: string) => {
    router.push(href)
  }

  const handleBackToDashboard = () => {
    router.push('/dashboard')
  }

  return (
    <div className={`bg-gradient-to-r from-white/60 via-brand-beige/30 to-white/60 backdrop-blur-sm border-b border-white/50 shadow-lg ${className}`}>
      <div className="w-full px-6 md:px-8 lg:px-12">
        {/* Top Breadcrumb Bar */}
        <div className="flex items-center justify-between py-4 border-b border-brand-lavender/20">
          <div className="flex items-center space-x-4">
            <button
              onClick={handleBackToDashboard}
              className="flex items-center space-x-2 text-brand-forest/70 hover:text-brand-forest transition-colors group"
            >
              <ArrowLeftIcon className="w-5 h-5 group-hover:-translate-x-1 transition-transform duration-200" />
              <span className="font-semibold">Back to Dashboard</span>
            </button>
            <span className="text-brand-forest/40">•</span>
            <div className="text-brand-forest font-bold">
              {projectTitle || 'Project'}
            </div>
          </div>
          
          <div className="flex items-center space-x-2 text-sm text-brand-forest/60">
            <span className="font-semibold">Project ID:</span>
            <code className="bg-brand-lavender/10 px-2 py-1 rounded font-mono text-xs">
              {projectId?.slice(0, 8)}...
            </code>
          </div>
        </div>

        {/* Navigation Menu */}
        <div className="py-3">
          <nav className="flex items-center space-x-1">
            {navigationItems.map((item) => {
              const Icon = item.icon
              const isActive = currentPath?.startsWith(item.href)
              
              return (
                <button
                  key={item.id}
                  onClick={() => handleNavigation(item.href)}
                  className={`group relative flex items-center space-x-2 px-4 py-2 rounded-xl font-semibold text-sm transition-all duration-300 ${
                    isActive
                      ? 'bg-gradient-to-r from-brand-forest to-brand-lavender text-white shadow-xl'
                      : 'text-brand-forest/70 hover:text-brand-forest hover:bg-white/60'
                  }`}
                  title={item.description}
                >
                  <Icon className={`w-5 h-5 transition-transform duration-200 ${
                    isActive ? 'scale-110' : 'group-hover:scale-105'
                  }`} />
                  <span>{item.label}</span>
                  
                  {/* Active indicator */}
                  {isActive && (
                    <div className="absolute -bottom-1 left-1/2 transform -translate-x-1/2 w-2 h-2 bg-white rounded-full shadow-lg"></div>
                  )}
                </button>
              )
            })}
          </nav>
        </div>
      </div>
    </div>
  )
}

export default ProjectNavigation 