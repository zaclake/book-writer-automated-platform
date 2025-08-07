'use client'

import { useParams } from 'next/navigation'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import ProjectLayout from '@/components/layout/ProjectLayout'
import { useProject } from '@/hooks/useFirestore'

export default function ProjectBookBiblePage() {
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
          <h1 className="text-2xl font-bold text-gray-900">Book Bible</h1>
          <p className="text-gray-600 mt-1">
            Manage your project foundation and guidelines
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Project Foundation</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-sm text-gray-600">
              Uploading a book bible has been deprecated. Use the References and Guided tools to evolve your project foundation.
            </div>
          </CardContent>
        </Card>
      </div>
    </ProjectLayout>
  )
} 