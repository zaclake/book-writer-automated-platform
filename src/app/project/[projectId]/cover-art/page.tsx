'use client'

import { useParams } from 'next/navigation'
import { CoverArtGenerator } from '@/components/CoverArtGenerator'
import ProjectLayout from '@/components/layout/ProjectLayout'

export default function CoverArtPage() {
  const params = useParams()
  const projectId = params.projectId as string

  return (
    <ProjectLayout projectId={projectId}>
      <div className="container mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-8">
        <div className="max-w-4xl md:max-w-5xl mx-auto">
          <CoverArtGenerator projectId={projectId} />
        </div>
      </div>
    </ProjectLayout>
  )
}
