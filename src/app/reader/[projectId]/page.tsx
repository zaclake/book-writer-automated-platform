'use client'

import React, { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import EPubReader from '@/components/EPubReader'

interface ReaderPayload {
  title: string
  author_name?: string
  cover_url?: string
  genre?: string
  epub_stream_url: string
}

export default function ReaderPage() {
  const params = useParams<{ projectId: string }>()
  const projectId = params.projectId
  const [data, setData] = useState<ReaderPayload | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let mounted = true
    async function load() {
      try {
        const res = await fetch(`/api/v2/library/book/${encodeURIComponent(projectId)}/reader`)
        if (!res.ok) {
          throw new Error(await res.text())
        }
        const json = await res.json()
        if (mounted) setData(json)
      } catch (e: any) {
        if (mounted) setError(e?.message || 'Failed to load')
      }
    }
    load()
    return () => { mounted = false }
  }, [projectId])

  if (error) {
    return <div className="min-h-screen flex items-center justify-center text-red-600">{error}</div>
  }
  if (!data) {
    return (
      <div className="min-h-screen flex items-center justify-center text-gray-600">Loading reader...</div>
    )
  }

  return (
    <div className="min-h-screen">
      <EPubReader epubUrl={`/api/v2/library/book/${encodeURIComponent(projectId)}/epub`} title={data.title} />
    </div>
  )
}


