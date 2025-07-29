'use client'

import React from 'react'
import { useParams } from 'next/navigation'
import { useProject } from '@/hooks/useProject'
import PublishingSuite from '@/components/PublishingSuite'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Loader2 } from 'lucide-react'

export default function PublishPage() {
  const params = useParams()
  const projectId = params?.projectId as string

  const { project, loading, error } = useProject(projectId)

  if (loading) {
    return (
      <div className="container max-w-4xl mx-auto py-8">
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin" />
          <span className="ml-2">Loading project...</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="container max-w-4xl mx-auto py-8">
        <Alert variant="destructive">
          <AlertDescription>
            Failed to load project: {error.message}
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  if (!project) {
    return (
      <div className="container max-w-4xl mx-auto py-8">
        <Alert>
          <AlertDescription>
            Project not found.
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  return (
    <div className="container max-w-6xl mx-auto py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold">Publish Book</h1>
        <p className="text-muted-foreground mt-2">
          Convert your book to professional EPUB and PDF formats ready for publishing.
        </p>
      </div>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Project: {project.metadata?.title}</CardTitle>
          <CardDescription>
            Prepare your book for publication with professional formatting
          </CardDescription>
        </CardHeader>
        <CardContent>
          <PublishingSuite projectId={projectId} project={project} />
        </CardContent>
      </Card>
    </div>
  )
} 