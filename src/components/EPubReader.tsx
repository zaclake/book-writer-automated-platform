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
  const lastTextLenRef = useRef<number>(0)
  const iframeObserverRef = useRef<MutationObserver | null>(null)
  const reloadTimerRef = useRef<any>(null)
  const guardIntervalRef = useRef<any>(null)

  useEffect(() => {
    let book: any
    let rendition: any
    let destroyed = false

    async function load() {
      try {
        const ePubMod = await import('epubjs')
        const ePub: any = ePubMod.default
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
        // Ensure iframe permissions as early as possible via render hook (runs per view before display)
        try {
          rendition.hooks.render.register((view: any) => {
            try {
              const iframe: HTMLIFrameElement | null = (view && (view.iframe || view.document?.defaultView?.frameElement)) || null
              if (iframe) {
                if (iframe.hasAttribute('sandbox')) iframe.removeAttribute('sandbox')
                iframe.setAttribute('allow', 'fullscreen; clipboard-read; clipboard-write; encrypted-media')
              }
            } catch {}
          })
        } catch {}
        // Periodic guard while navigating between chapters
        guardIntervalRef.current = window.setInterval(() => {
          try {
            const ifrs = Array.from(containerRef.current?.querySelectorAll('iframe') || [])
            let changed = false
            for (const ifr of ifrs as HTMLIFrameElement[]) {
              if (ifr.hasAttribute('sandbox')) { ifr.removeAttribute('sandbox'); changed = true }
              ifr.setAttribute('allow', 'fullscreen; clipboard-read; clipboard-write; encrypted-media')
            }
            if (changed) {
              // Re-display current CFI so the unsandboxed frame renders content
              const currentCfi = rendition?.currentLocation()?.start?.cfi
              if (currentCfi) { void rendition.display(currentCfi) }
            }
          } catch {}
        }, 500)
        // Ensure iframe in which epub renders is allowed to execute scripts
        const applyIframePermissions = () => {
          try {
            const iframes = Array.from(containerRef.current?.querySelectorAll('iframe') || []) as HTMLIFrameElement[]
            for (const ifr of iframes) {
              // Prefer removing sandbox entirely to avoid UA defaults overriding tokens
              if (ifr.hasAttribute('sandbox')) {
                ifr.removeAttribute('sandbox')
              }
              // Also set permissive allow features
              ifr.setAttribute('allow', 'fullscreen; clipboard-read; clipboard-write; encrypted-media')
            }
            setDebug(d => (d && !d.includes('sandbox')) ? `${d} | iframe sandbox removed` : (d || 'iframe sandbox removed'))
          } catch {}
        }
        const relaunchAfterFix = () => {
          try {
            if (reloadTimerRef.current) window.clearTimeout(reloadTimerRef.current)
            reloadTimerRef.current = window.setTimeout(() => {
              try {
                const current = rendition?.currentLocation()
                const cfi = current?.start?.cfi
                void rendition.display(cfi || undefined)
              } catch {}
            }, 50)
          } catch {}
        }
        // Apply immediately and watch for future iframe replacements
        applyIframePermissions()
        relaunchAfterFix()
        try {
          if (iframeObserverRef.current) iframeObserverRef.current.disconnect()
          iframeObserverRef.current = new MutationObserver(() => { applyIframePermissions(); relaunchAfterFix() })
          iframeObserverRef.current.observe(containerRef.current!, { childList: true, subtree: true, attributes: true, attributeFilter: ['sandbox'] })
        } catch {}
        // Ensure readable theme and track text length to avoid blank pages
        try {
          rendition.flow('scrolled-doc')
          rendition.themes.default({
            body: { color: '#111', background: '#ffffff' },
            img: { maxWidth: '100%' }
          })
          rendition.hooks.content.register((contents: any) => {
            try {
              const text = (contents?.document?.body?.innerText || '').replace(/\s+/g, '')
              lastTextLenRef.current = text.length
            } catch {
              lastTextLenRef.current = 0
            }
          })
        } catch {}
        // Ensure we open a meaningful location; if empty, iterate to next spine entries
        const tryDisplay = async () => {
          let opened = false
          try {
            const spine = await book.loaded.spine
            const hrefs: string[] = (spine?.items || []).map((it: any) => it?.href).filter(Boolean)
            const candidates = [preferredHref, ...hrefs].filter((v, i, a) => v && a.indexOf(v) === i) as string[]
            for (const href of candidates) {
              await rendition.display(href)
              await new Promise(r => setTimeout(r, 250))
              if (lastTextLenRef.current > 200) {
                setDebug(d => (d ? `${d} | Opened: ${href} (len ${lastTextLenRef.current})` : `Opened: ${href}`))
                opened = true
                break
              }
            }
          } catch {}
          if (!opened) {
            await rendition.display()
          }
        }
        await tryDisplay()
        try {
          const nav = await book.loaded.navigation
          if (nav && nav.toc && nav.toc.length > 0 && !preferredHref) {
            // As a last resort, try first TOC entry that isn't obvious front matter
            const lower = (s: string) => (s || '').toLowerCase()
            const isFront = (s: string) => [
              'cover','title','copyright','toc','nav','acknowled','dedicat','imprint','front','back','colophon'
            ].some(k => lower(s).includes(k))
            const tocHref = nav.toc.map((t: any) => t.href).find((h: string) => h && !isFront(h))
            if (tocHref) {
              await rendition.display(tocHref)
              await new Promise(r => setTimeout(r, 200))
              if (lastTextLenRef.current < 150) {
                // If still empty, iterate forward in spine until text appears
                const spine = await book.loaded.spine
                const hrefs: string[] = (spine?.items || []).map((it: any) => it?.href).filter(Boolean)
                const startIdx = Math.max(0, hrefs.indexOf(tocHref))
                for (let i = startIdx; i < hrefs.length; i++) {
                  await rendition.display(hrefs[i])
                  await new Promise(r => setTimeout(r, 250))
                  if (lastTextLenRef.current > 200) break
                }
              }
            }
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
      try { iframeObserverRef.current?.disconnect() } catch {}
      try { window.clearInterval(guard as any) } catch {}
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


