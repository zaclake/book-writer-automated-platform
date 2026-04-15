'use client'

import { useParams } from 'next/navigation'
import { CoverArtGenerator } from '@/components/CoverArtGenerator'
import ProjectLayout from '@/components/layout/ProjectLayout'

export default function CoverArtPage() {
  const params = useParams()
  const projectId = params.projectId as string

  return (
    <ProjectLayout projectId={projectId}>
      <div className="container mx-auto px-4 sm:px-6 md:px-8 py-8">
        <div className="max-w-4xl md:max-w-5xl mx-auto">
          <div className="mb-8">
            <h1 className="text-3xl font-bold tracking-tight">Cover Art Generator</h1>
            <p className="text-gray-500 mt-2">
              Create professional book cover art using AI based on your story content.
            </p>
          </div>
          
          <CoverArtGenerator projectId={projectId} />
        </div>
      </div>
    </ProjectLayout>
  )
}
