'use client'

import React, { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import EPubReader from '@/components/EPubReader'
import { fetchApi } from '@/lib/api-client'

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
        const res = await fetchApi(`/api/v2/library/book/${encodeURIComponent(projectId)}/reader`)
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
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <div className="text-center max-w-md">
          <div className="text-5xl mb-4">📖</div>
          <h2 className="text-xl font-semibold text-gray-900 mb-2">Unable to Open Book</h2>
          <p className="text-gray-600 mb-6">{error}</p>
          <button
            onClick={() => window.history.back()}
            className="px-6 py-2.5 bg-gray-900 text-white rounded-lg hover:bg-gray-800 transition"
          >
            Go Back
          </button>
        </div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-sm text-gray-500">Loading book...</p>
        </div>
      </div>
    )
  }

  const epubUrl = `/api/v2/library/book/${encodeURIComponent(projectId)}/epub`

  return <EPubReader epubUrl={epubUrl} title={data.title} projectId={projectId} />
}
