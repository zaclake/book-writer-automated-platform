'use client'

import React, { useEffect, useRef, useState } from 'react'

interface EPubReaderProps {
  epubUrl: string
  title?: string
}

export default function EPubReader({ epubUrl, title }: EPubReaderProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [ready, setReady] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let book: any
    let rendition: any
    let destroyed = false

    async function load() {
      try {
        const ePubMod = await import('epubjs')
        const ePub = ePubMod.default
        if (destroyed) return

        // Fetch EPUB as ArrayBuffer to avoid path resolution to container.xml under the API directory
        const resp = await fetch(epubUrl)
        if (!resp.ok) throw new Error(`Failed to fetch EPUB: ${resp.status}`)
        const buf = await resp.arrayBuffer()

        // Use a Blob URL for maximum compatibility with epub.js
        // Open explicitly as binary to prevent any network lookups for META-INF/container.xml
        book = ePub()
        await book.open(buf, 'binary')
        rendition = book.renderTo(containerRef.current!, {
          width: '100%',
          height: '100%'
        })
        // Ensure we open the first spine item explicitly
        await rendition.display()
        try {
          const nav = await book.loaded.navigation
          if (nav && nav.toc && nav.toc.length > 0) {
            // No-op: default opening should work; leaving hook for debugging
          }
        } catch {}
        setReady(true)
      } catch (e: any) {
        console.error('EPUB load error', e)
        setError(e?.message || 'Failed to load book')
      }
    }
    load()

    return () => {
      destroyed = true
      try { rendition?.destroy() } catch {}
      try { book?.destroy() } catch {}
      // Revoke any blob URLs created by epub.js if accessible
      try {
        const ifr = containerRef.current?.querySelector('iframe') as HTMLIFrameElement | null
        const src = ifr?.src
        if (src && src.startsWith('blob:')) URL.revokeObjectURL(src)
      } catch {}
    }
  }, [epubUrl])

  return (
    <div className="w-full h-full flex flex-col">
      <div className="px-4 py-2 border-b bg-white flex items-center justify-between">
        <div className="font-medium text-gray-900 truncate">{title || 'Reader'}</div>
        <div className="text-sm text-gray-500">{error ? `Error: ${error}` : (ready ? 'Ready' : 'Loading...')}</div>
      </div>
      <div ref={containerRef} className="flex-1 bg-white" style={{ height: 'calc(100vh - 44px)' }} />
    </div>
  )
}


