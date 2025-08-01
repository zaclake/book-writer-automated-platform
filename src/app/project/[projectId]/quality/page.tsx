'use client'

import { useParams } from 'next/navigation'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import ProjectLayout from '@/components/layout/ProjectLayout'
import { useProject } from '@/hooks/useFirestore'

export default function ProjectQualityPage() {
  const params = useParams()
  const projectId = params.projectId as string
  
  // Get project data for the navigation title
  const { project } = useProject(projectId)

  return (
    <ProjectLayout 
      projectId={projectId} 
      projectTitle={project?.metadata?.title || project?.title || `Project ${projectId}`}
    >
      <div className="space-y-6 p-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Quality Assessment</h1>
          <p className="text-gray-600 mt-1">
            Review and improve your writing quality
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Quality Tools</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-center py-8">
              <div className="text-4xl mb-4">⭐</div>
              <h3 className="text-lg font-medium text-gray-900 mb-2">Quality Assessment Tools</h3>
              <p className="text-gray-600">
                Quality assessment tools will be available here to analyze and improve your chapters.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </ProjectLayout>
  )
} 