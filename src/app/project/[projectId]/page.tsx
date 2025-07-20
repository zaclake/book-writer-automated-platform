'use client'

import { useParams, useRouter } from 'next/navigation'
import { useEffect } from 'react'

export default function ProjectPage() {
  const params = useParams()
  const router = useRouter()
  const projectId = params.projectId as string

  useEffect(() => {
    // Redirect to the overview page
    if (projectId) {
      router.replace(`/project/${projectId}/overview`)
    }
  }, [projectId, router])

  return (
    <div className="flex items-center justify-center h-64">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mx-auto mb-4"></div>
        <p className="text-gray-600">Redirecting to project overview...</p>
      </div>
    </div>
  )
} 