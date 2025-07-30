'use client'

import { useParams } from 'next/navigation'
import { CoverArtGenerator } from '@/components/CoverArtGenerator'
import ProjectLayout from '@/components/layout/ProjectLayout'
import { useProject } from '@/hooks/useFirestore'

export default function CoverArtPage() {
  const params = useParams()
  const projectId = params.projectId as string
  
  // Get project data for the navigation title
  const { project } = useProject(projectId)

  return (
    <ProjectLayout 
      projectId={projectId} 
      projectTitle={project?.metadata?.title || project?.title || `Project ${projectId}`}
    >
      <div className="container mx-auto px-4 py-8">
        <div className="max-w-4xl mx-auto">
          <div className="mb-8">
            <h1 className="text-3xl font-bold tracking-tight">Cover Art Generator</h1>
            <p className="text-muted-foreground mt-2">
              Create professional book cover art using AI based on your story content.
            </p>
          </div>
          
          <CoverArtGenerator projectId={projectId} />
        </div>
      </div>
    </ProjectLayout>
  )
} 