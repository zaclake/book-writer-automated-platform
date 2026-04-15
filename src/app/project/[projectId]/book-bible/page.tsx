'use client'

import { useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'

export default function ProjectBookBiblePage() {
  const params = useParams()
  const router = useRouter()
  const projectId = params.projectId as string

  useEffect(() => {
    router.replace(`/project/${projectId}/references`)
  }, [router, projectId])

  return null
}
