'use client'

import { useParams, useRouter } from 'next/navigation'
import { useState } from 'react'
import ProjectDashboard from '@/components/ProjectDashboard'
import ProjectLayout from '@/components/layout/ProjectLayout'

export default function ProjectOverviewPage() {
  const params = useParams()
  const router = useRouter()
  const projectId = params.projectId as string
  const [titleOverride, setTitleOverride] = useState<string | null>(null)

  if (!projectId) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <h2 className="text-xl font-semibold text-gray-900 mb-2">Invalid Project</h2>
          <p className="text-gray-600">No project ID provided</p>
        </div>
      </div>
    )
  }

  return (
    <ProjectLayout
      projectId={projectId}
      projectTitle={titleOverride || undefined}
    >
      <ProjectDashboard
        projectId={projectId}
        onTitleUpdated={(title) => {
          setTitleOverride(title)
        }}
        onEditChapter={(_chapterId, chapterNumber) => {
          router.push(`/project/${projectId}/chapters?chapter=${chapterNumber}`)
        }}
        onCreateChapter={(chapterNumber) => {
          router.push(`/project/${projectId}/chapters?chapter=${chapterNumber}`)
        }}
      />
    </ProjectLayout>
  )
}
