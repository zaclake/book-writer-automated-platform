'use client'

import { useParams, useRouter } from 'next/navigation'
import { useProject } from '@/hooks/useFirestore'
import ProjectDashboard from '@/components/ProjectDashboard'
import ProjectLayout from '@/components/layout/ProjectLayout'

export default function ProjectOverviewPage() {
  const params = useParams()
  const router = useRouter()
  const projectId = params.projectId as string
  
  // Get project data for the navigation title
  const { project } = useProject(projectId)

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
      projectTitle={project?.metadata?.title || project?.title || `Project ${projectId}`}
    >
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
    </ProjectLayout>
  )
} 