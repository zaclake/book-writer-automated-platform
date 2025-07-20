'use client'

import { useParams } from 'next/navigation'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ReferenceFileManager } from '@/components/ReferenceFileManager'

export default function ProjectReferencesPage() {
  const params = useParams()
  const projectId = params.projectId as string

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">References</h1>
        <p className="text-gray-600 mt-1">
          Manage character sheets, outlines, and world-building documents
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Reference Files</CardTitle>
        </CardHeader>
        <CardContent>
          <ReferenceFileManager />
        </CardContent>
      </Card>
    </div>
  )
} 