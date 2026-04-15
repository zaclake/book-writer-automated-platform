'use client'

import React, { useState } from 'react'
import { useParams } from 'next/navigation'
import { useAuthToken } from '@/lib/auth'
import { fetchApi } from '@/lib/api-client'
import PublishingSuite from '@/components/PublishingSuite'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import ProjectLayout from '@/components/layout/ProjectLayout'

export default function PublishPage() {
  const params = useParams()
  const projectId = params?.projectId as string
  const { getAuthHeaders, isLoaded, isSignedIn } = useAuthToken()
  const [project, setProject] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  React.useEffect(() => {
    if (!isLoaded || !isSignedIn || !projectId) {
      if (isLoaded && !isSignedIn) setLoading(false)
      return
    }
    let cancelled = false
    async function load() {
      try {
        const authHeaders = await getAuthHeaders()
        const res = await fetchApi(`/api/v2/projects/${encodeURIComponent(projectId)}`, {
          headers: authHeaders
        })
        if (!res.ok) throw new Error(`Failed to load project: ${res.statusText}`)
        const data = await res.json()
        if (!cancelled) {
          setProject(data.project || data)
          setLoading(false)
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(err.message || 'Failed to load project')
          setLoading(false)
        }
      }
    }
    load()
    return () => { cancelled = true }
  }, [isLoaded, isSignedIn, projectId, getAuthHeaders])

  const title = project?.metadata?.title || project?.title || 'Project'

  if (loading) {
    return (
      <ProjectLayout projectId={projectId} projectTitle="Loading...">
        <div className="flex items-center justify-center min-h-[40vh]">
          <div className="text-center">
            <div className="w-10 h-10 border-2 border-gray-200 border-t-indigo-500 rounded-full animate-spin mx-auto mb-4" />
            <p className="text-gray-500 text-sm">Loading project...</p>
          </div>
        </div>
      </ProjectLayout>
    )
  }

  if (error || !project) {
    return (
      <ProjectLayout projectId={projectId} projectTitle="Error">
        <div className="flex items-center justify-center min-h-[40vh] px-6">
          <div className="text-center max-w-md">
            <h2 className="text-xl font-semibold text-gray-900 mb-3">{error || 'Project not found'}</h2>
            <button
              onClick={() => window.location.reload()}
              className="px-6 py-2.5 bg-gray-900 text-white rounded-lg hover:bg-gray-800 transition text-sm font-medium"
            >
              Try Again
            </button>
          </div>
        </div>
      </ProjectLayout>
    )
  }

  return (
    <ProjectLayout projectId={projectId} projectTitle={title}>
      <div className="container max-w-6xl mx-auto px-4 sm:px-6 md:px-8 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight">Publish Book</h1>
          <p className="text-gray-500 mt-2">
            Convert your book to professional EPUB and PDF formats ready for publishing.
          </p>
        </div>

        <Card className="mb-6">
          <CardHeader>
            <CardTitle>Project: {title}</CardTitle>
            <CardDescription>
              Prepare your book for publication with professional formatting
            </CardDescription>
          </CardHeader>
          <CardContent>
            <PublishingSuite projectId={projectId} project={project} />
          </CardContent>
        </Card>
      </div>
    </ProjectLayout>
  )
}
