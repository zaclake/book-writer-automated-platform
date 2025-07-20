'use client'

import { useParams, useRouter } from 'next/navigation'
import ProjectDashboard from '@/components/ProjectDashboard'

export default function ProjectOverviewPage() {
  const params = useParams()
  const router = useRouter()
  const projectId = params.projectId as string

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
    <ProjectDashboard
      projectId={projectId}
      onEditChapter={(chapterId) => {
        // Navigate to chapters page where editing can happen
        router.push(`/project/${projectId}/chapters`)
      }}
      onCreateChapter={(chapterNumber) => {
        // Navigate to chapters page for creation
        router.push(`/project/${projectId}/chapters`)
      }}
    />
  )
} 