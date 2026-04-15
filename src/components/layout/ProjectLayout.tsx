'use client'

import React from 'react'
import { ProjectNavigation } from './ProjectNavigation'

interface ProjectLayoutProps {
  children: React.ReactNode
  projectId: string
  projectTitle?: string
  className?: string
  hideNavigation?: boolean
}

export function ProjectLayout({ 
  children, 
  projectId, 
  projectTitle, 
  className = '',
  hideNavigation = false
}: ProjectLayoutProps) {
  return (
    <div className={`min-h-screen bg-gray-50 ${className}`}>
      {/* Project Navigation */}
      {!hideNavigation && <ProjectNavigation projectTitle={projectTitle} />}
      
      {/* Main Content */}
      <main className="relative">
        {children}
      </main>
    </div>
  )
}

export default ProjectLayout 