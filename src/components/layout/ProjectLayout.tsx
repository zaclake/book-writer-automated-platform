'use client'

import React from 'react'
import { ProjectNavigation } from './ProjectNavigation'

interface ProjectLayoutProps {
  children: React.ReactNode
  projectId: string
  projectTitle?: string
  className?: string
}

export function ProjectLayout({ 
  children, 
  projectId, 
  projectTitle, 
  className = '' 
}: ProjectLayoutProps) {
  return (
    <div className={`min-h-screen bg-brand-off-white ${className}`}>
      {/* Project Navigation */}
      <ProjectNavigation projectTitle={projectTitle} />
      
      {/* Main Content */}
      <main className="relative">
        {children}
      </main>
    </div>
  )
}

export default ProjectLayout 