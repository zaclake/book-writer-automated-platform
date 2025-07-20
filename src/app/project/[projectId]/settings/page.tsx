'use client'

import { useParams } from 'next/navigation'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export default function ProjectSettingsPage() {
  const params = useParams()
  const projectId = params.projectId as string

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Project Settings</h1>
        <p className="text-gray-600 mt-1">
          Configure project preferences and settings
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Project Configuration</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-8">
            <div className="text-4xl mb-4">⚙️</div>
            <h3 className="text-lg font-medium text-gray-900 mb-2">Project Settings</h3>
            <p className="text-gray-600">
              Project configuration options will be available here.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
} 