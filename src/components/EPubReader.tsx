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
  const [debug, setDebug] = useState<string | null>(null)

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

        let preferredHref: string | null = null
        try {
          const spine = await book.loaded.spine
          const items: any[] = spine?.items || []
          const hrefs: string[] = items.map((it: any) => it?.href).filter(Boolean)
          const lower = (s: string) => (s || '').toLowerCase()
          const isFront = (s: string) => {
            const x = lower(s)
            return [
              'cover', 'title', 'copyright', 'toc', 'nav',
              'acknowled', 'dedicat', 'imprint', 'front', 'back', 'colophon'
            ].some(k => x.includes(k))
          }
          const looksLikeChapter = (s: string) => /chapter|\bch\d+\b|prologue|epilogue|section|part/i.test(s)
          preferredHref = hrefs.find(h => looksLikeChapter(h) && !isFront(h)) ||
                          hrefs.find(h => !isFront(h)) ||
                          (hrefs.length > 0 ? hrefs[0] : null)

          setDebug(`Spine items: ${hrefs.length} | First: ${hrefs[0] || 'n/a'} | Picked: ${preferredHref || 'n/a'}`)
        } catch (e) {
          console.warn('Failed to inspect spine', e)
        }
        rendition = book.renderTo(containerRef.current!, {
          width: '100%',
          height: '100%'
        })
        // Ensure we open a meaningful location (prefer computed chapter-ish href)
        if (preferredHref) {
          await rendition.display(preferredHref)
        } else {
          await rendition.display()
          try {
            const spine = await book.loaded.spine
            if (spine?.items?.length > 0) {
              await rendition.display(spine.items[0].href)
            }
          } catch {}
        }
        try {
          const nav = await book.loaded.navigation
          if (nav && nav.toc && nav.toc.length > 0 && !preferredHref) {
            // As a last resort, try first TOC entry that isn't obvious front matter
            const lower = (s: string) => (s || '').toLowerCase()
            const isFront = (s: string) => [
              'cover','title','copyright','toc','nav','acknowled','dedicat','imprint','front','back','colophon'
            ].some(k => lower(s).includes(k))
            const tocHref = nav.toc.map((t: any) => t.href).find((h: string) => h && !isFront(h))
            if (tocHref) await rendition.display(tocHref)
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
      {debug && (
        <div className="px-4 py-1 text-xs text-gray-500 border-b bg-gray-50">{debug}</div>
      )}
      <div ref={containerRef} className="flex-1 bg-white" style={{ height: 'calc(100vh - 60px)' }} />
    </div>
  )
}


