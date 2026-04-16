'use client'

import React, { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
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
          <Link
            href="/library"
            className="px-6 py-2.5 bg-gray-900 text-white rounded-lg hover:bg-gray-800 transition inline-block"
          >
            Back to Library
          </Link>
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

  const pid = encodeURIComponent(projectId)
  const epubUrl = `/api/v2/library/book/${pid}/epub`

  return (
    <div className="min-h-screen flex flex-col bg-white">
      <div className="sticky top-0 z-30 bg-white/95 backdrop-blur-sm border-b border-gray-200">
        <div className="max-w-5xl mx-auto px-4 flex items-center justify-between h-11">
          <Link
            href="/library"
            className="inline-flex items-center gap-1.5 text-sm text-gray-600 hover:text-gray-900 transition"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
            Library
          </Link>

          <h1 className="text-sm font-medium text-gray-900 truncate max-w-[50%]" title={data.title}>
            {data.title}
          </h1>

          <a
            href={epubUrl}
            download
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-indigo-700 bg-indigo-50 hover:bg-indigo-100 rounded-md transition"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            Download
          </a>
        </div>
      </div>

      <div className="flex-1">
        <EPubReader epubUrl={epubUrl} title={data.title} projectId={projectId} />
      </div>
    </div>
  )
}
