'use client'

import { useParams } from 'next/navigation'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { BookBibleUpload } from '@/components/BookBibleUpload'

export default function ProjectBookBiblePage() {
  const params = useParams()
  const projectId = params.projectId as string

  return (
    <div className="space-y-6">
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
          <BookBibleUpload onProjectInitialized={() => {}} />
        </CardContent>
      </Card>
    </div>
  )
} 