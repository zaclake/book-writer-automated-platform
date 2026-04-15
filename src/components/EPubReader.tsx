'use client'

import React, { useCallback, useEffect, useRef, useState } from 'react'

interface EPubReaderProps {
  epubUrl: string
  title?: string
  projectId?: string
}

interface TocItem {
  label: string
  href: string
  subitems?: TocItem[]
}

type Theme = 'light' | 'sepia' | 'dark'

const THEME_STYLES: Record<Theme, {
  bg: string; text: string; textMuted: string; headerBg: string; headerBorder: string;
  tocBg: string; tocActive: string; controlBg: string; controlText: string;
  progressBg: string; progressFill: string; overlay: string; btnBg: string; btnBorder: string;
}> = {
  light: {
    bg: '#ffffff', text: '#1a1a1a', textMuted: '#6b7280', headerBg: 'rgba(255,255,255,0.95)',
    headerBorder: '#e5e7eb', tocBg: '#ffffff', tocActive: '#eef2ff',
    controlBg: '#f9fafb', controlText: '#374151', progressBg: '#e5e7eb', progressFill: '#6366f1',
    overlay: 'rgba(0,0,0,0.25)', btnBg: 'rgba(255,255,255,0.9)', btnBorder: '#e5e7eb',
  },
  sepia: {
    bg: '#faf4e8', text: '#3d3229', textMuted: '#7a6c5d', headerBg: 'rgba(245,237,216,0.95)',
    headerBorder: '#d4c9a8', tocBg: '#f5edd8', tocActive: '#e8dbb8',
    controlBg: '#efe5cc', controlText: '#5c4b32', progressBg: '#d4c9a8', progressFill: '#8b6914',
    overlay: 'rgba(0,0,0,0.2)', btnBg: 'rgba(245,237,216,0.9)', btnBorder: '#d4c9a8',
  },
  dark: {
    bg: '#121212', text: '#e0e0e0', textMuted: '#888', headerBg: 'rgba(18,18,18,0.95)',
    headerBorder: '#2a2a2a', tocBg: '#181818', tocActive: '#2d2d4a',
    controlBg: '#1e1e1e', controlText: '#a1a1aa', progressBg: '#2a2a2a', progressFill: '#818cf8',
    overlay: 'rgba(0,0,0,0.5)', btnBg: 'rgba(30,30,30,0.9)', btnBorder: '#333',
  },
}

const FONT_SIZES = [14, 16, 18, 20, 22, 24, 28]
const LINE_HEIGHTS = [1.5, 1.6, 1.7, 1.8, 1.9, 2.0]
const DEFAULT_FONT_INDEX = 2
const DEFAULT_LH_INDEX = 3

function getStored<T>(key: string, fallback: T, parse?: (v: string) => T): T {
  if (typeof window === 'undefined') return fallback
  try {
    const v = localStorage.getItem(key)
    if (v === null) return fallback
    return parse ? parse(v) : (v as unknown as T)
  } catch { return fallback }
}

function positionKey(projectId?: string) {
  return projectId ? `reader-pos-${projectId}` : null
}

export default function EPubReader({ epubUrl, title, projectId }: EPubReaderProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const renditionRef = useRef<any>(null)
  const bookRef = useRef<any>(null)

  const [ready, setReady] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toc, setToc] = useState<TocItem[]>([])
  const [tocOpen, setTocOpen] = useState(false)
  const [theme, setTheme] = useState<Theme>(() => getStored('reader-theme', 'light' as Theme))
  const [fontIndex, setFontIndex] = useState(() => getStored('reader-font-index', DEFAULT_FONT_INDEX, v => Math.min(Math.max(parseInt(v, 10), 0), FONT_SIZES.length - 1)))
  const [lhIndex, setLhIndex] = useState(() => getStored('reader-lh-index', DEFAULT_LH_INDEX, v => Math.min(Math.max(parseInt(v, 10), 0), LINE_HEIGHTS.length - 1)))
  const [showControls, setShowControls] = useState(false)
  const [headerVisible, setHeaderVisible] = useState(false)
  const [currentChapter, setCurrentChapter] = useState('')
  const [progress, setProgress] = useState(0)
  const [totalLocations, setTotalLocations] = useState(0)
  const [atStart, setAtStart] = useState(true)
  const [atEnd, setAtEnd] = useState(false)
  const [resumed, setResumed] = useState(false)

  const styles = THEME_STYLES[theme]

  const applyTheme = useCallback((rendition: any, t: Theme, fi: number, li: number) => {
    if (!rendition) return
    const s = THEME_STYLES[t]
    const fontSize = FONT_SIZES[fi]
    const lineHeight = LINE_HEIGHTS[li]
    rendition.themes.default({
      'body': {
        'color': `${s.text} !important`,
        'background': `${s.bg} !important`,
        'font-family': '"Georgia", "Palatino Linotype", "Book Antiqua", Palatino, serif !important',
        'font-size': `${fontSize}px !important`,
        'line-height': `${lineHeight} !important`,
        'padding': '0 4% !important',
        'max-width': '42em',
        'margin': '0 auto',
        '-webkit-text-size-adjust': '100%',
      },
      'p': { 'text-indent': '1.5em', 'margin': '0.35em 0', 'orphans': '2', 'widows': '2' },
      'h1, h2, h3, h4, h5, h6': {
        'color': `${s.text} !important`, 'text-indent': '0 !important',
        'margin-top': '1.8em', 'margin-bottom': '0.5em', 'line-height': '1.3',
      },
      'h1': { 'font-size': '1.6em', 'text-align': 'center', 'letter-spacing': '0.03em' },
      'img': { 'max-width': '100%', 'height': 'auto' },
      'a': { 'color': s.progressFill },
      'blockquote': {
        'border-left': `3px solid ${s.headerBorder}`, 'padding-left': '1em',
        'margin': '1em 0', 'font-style': 'italic', 'opacity': '0.9',
      },
    })
  }, [])

  const goNext = useCallback(() => { renditionRef.current?.next() }, [])
  const goPrev = useCallback(() => { renditionRef.current?.prev() }, [])

  const goToHref = useCallback((href: string) => {
    renditionRef.current?.display(href)
    setTocOpen(false)
    setHeaderVisible(false)
    setShowControls(false)
  }, [])

  const savePosition = useCallback((cfi: string) => {
    const key = positionKey(projectId)
    if (key && cfi) {
      try { localStorage.setItem(key, cfi) } catch {}
    }
  }, [projectId])

  const getSavedPosition = useCallback((): string | null => {
    const key = positionKey(projectId)
    if (!key) return null
    try { return localStorage.getItem(key) } catch { return null }
  }, [projectId])

  // ── Load EPUB ──
  useEffect(() => {
    let book: any
    let rendition: any
    let destroyed = false

    async function load() {
      try {
        const ePubMod = await import('epubjs')
        const ePub: any = ePubMod.default
        if (destroyed) return

        const resp = await fetch(epubUrl)
        if (!resp.ok) throw new Error(`Failed to fetch EPUB: ${resp.status}`)
        const buf = await resp.arrayBuffer()

        book = ePub()
        await book.open(buf, 'binary')
        if (destroyed || !containerRef.current) return
        bookRef.current = book

        rendition = book.renderTo(containerRef.current, {
          width: '100%',
          height: '100%',
          allowScriptedContent: true,
          flow: 'paginated',
          spread: 'none',
        })
        renditionRef.current = rendition

        applyTheme(rendition, theme, fontIndex, lhIndex)

        // ── Track position on every page turn ──
        rendition.on('relocated', (location: any) => {
          if (destroyed) return
          try {
            const start = location?.start
            if (!start) return
            const displayed = start.displayed
            setAtStart(start.index === 0 && (!displayed || displayed.page <= 1))
            setAtEnd(!!location.atEnd)
            if (start.cfi) savePosition(start.cfi)
            if (book.locations && book.locations.length()) {
              const pct = book.locations.percentageFromCfi(start.cfi)
              setProgress(Math.round(pct * 100))
            }
          } catch {}
        })

        // ── Swipe gestures inside the iframe (epubjs built-in touch events) ──
        rendition.on('swipeleft', () => { if (!destroyed) goNext() })
        rendition.on('swiperight', () => { if (!destroyed) goPrev() })

        // ── Tap inside iframe: toggle header overlay ──
        rendition.on('click', () => {
          if (destroyed) return
          setHeaderVisible(prev => {
            if (prev) {
              setShowControls(false)
              setTocOpen(false)
            }
            return !prev
          })
        })

        // ── Inject touch event forwarding into each iframe for swipe ──
        rendition.hooks.content.register((contents: any) => {
          if (destroyed) return
          const doc = contents?.document
          if (!doc) return
          let startX = 0
          let startY = 0
          let startT = 0
          doc.addEventListener('touchstart', (e: TouchEvent) => {
            const t = e.touches[0]
            startX = t.clientX; startY = t.clientY; startT = Date.now()
          }, { passive: true })
          doc.addEventListener('touchend', (e: TouchEvent) => {
            const t = e.changedTouches[0]
            const dx = t.clientX - startX
            const dy = t.clientY - startY
            const dt = Date.now() - startT
            if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy) * 1.2 && dt < 500) {
              if (dx < 0) goNext()
              else goPrev()
            }
          }, { passive: true })
        })

        // ── Restore position or start at first chapter ──
        const savedCfi = getSavedPosition()
        if (savedCfi) {
          try {
            await rendition.display(savedCfi)
            setResumed(true)
            setTimeout(() => setResumed(false), 3000)
          } catch {
            await rendition.display()
          }
        } else {
          let preferredHref: string | null = null
          try {
            const spine = await book.loaded.spine
            const items: any[] = spine?.items || []
            const hrefs: string[] = items.map((it: any) => it?.href).filter(Boolean)
            const isFront = (s: string) => {
              const x = s.toLowerCase()
              return ['cover', 'title', 'copyright', 'toc', 'nav', 'acknowled', 'dedicat', 'imprint', 'front', 'colophon'].some(k => x.includes(k))
            }
            const isChapter = (s: string) => /chapter|\bch\d+\b|prologue|epilogue|section|part/i.test(s)
            preferredHref = hrefs.find(h => isChapter(h) && !isFront(h)) ||
                            hrefs.find(h => !isFront(h)) ||
                            (hrefs.length > 0 ? hrefs[0] : null)
          } catch {}
          await rendition.display(preferredHref || undefined)
        }

        // ── Load TOC ──
        try {
          const nav = await book.loaded.navigation
          if (nav?.toc) {
            const mapToc = (items: any[]): TocItem[] =>
              items.map(item => ({
                label: item.label?.trim() || 'Untitled',
                href: item.href,
                subitems: item.subitems?.length ? mapToc(item.subitems) : undefined,
              }))
            setToc(mapToc(nav.toc))
          }
        } catch {}

        // ── Generate locations for progress bar ──
        book.locations.generate(1024).then(() => {
          if (destroyed) return
          setTotalLocations(book.locations.length())
          try {
            const loc = rendition.currentLocation()
            if (loc?.start?.cfi && book.locations.length()) {
              setProgress(Math.round(book.locations.percentageFromCfi(loc.start.cfi) * 100))
            }
          } catch {}
        }).catch(() => {})

        setReady(true)
      } catch (e: any) {
        console.error('EPUB load error', e)
        if (!destroyed) setError(e?.message || 'Failed to load book')
      }
    }
    load()

    return () => {
      destroyed = true
      try { renditionRef.current?.destroy() } catch {}
      try { bookRef.current?.destroy() } catch {}
      renditionRef.current = null
      bookRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [epubUrl])

  // ── Persist settings ──
  useEffect(() => {
    applyTheme(renditionRef.current, theme, fontIndex, lhIndex)
    try {
      localStorage.setItem('reader-theme', theme)
      localStorage.setItem('reader-font-index', String(fontIndex))
      localStorage.setItem('reader-lh-index', String(lhIndex))
    } catch {}
  }, [theme, fontIndex, lhIndex, applyTheme])

  // ── Track current chapter name ──
  useEffect(() => {
    if (toc.length === 0 || !renditionRef.current) return
    const handler = (section: any) => {
      try {
        const href = section?.href
        if (!href) return
        const flat = [...toc, ...(toc.flatMap(t => t.subitems || []))]
        const match = flat.find(t => href.includes(t.href) || t.href.includes(href))
        if (match) setCurrentChapter(match.label)
      } catch {}
    }
    renditionRef.current.on('displayed', handler)
    return () => { try { renditionRef.current?.off('displayed', handler) } catch {} }
  }, [toc])

  // ── Keyboard navigation ──
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight' || e.key === 'PageDown') { e.preventDefault(); goNext() }
      if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); goPrev() }
      if (e.key === 'Escape') { setTocOpen(false); setShowControls(false); setHeaderVisible(false) }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [goNext, goPrev])

  // ── Error state ──
  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4" style={{ paddingTop: 'env(safe-area-inset-top)', paddingBottom: 'env(safe-area-inset-bottom)' }}>
        <div className="text-center max-w-md">
          <div className="text-5xl mb-4">📖</div>
          <h2 className="text-xl font-semibold text-gray-900 mb-2">Unable to Load Book</h2>
          <p className="text-gray-600 mb-6">{error}</p>
          <button onClick={() => window.location.reload()} className="px-6 py-2.5 bg-gray-900 text-white rounded-lg hover:bg-gray-800 transition">
            Try Again
          </button>
        </div>
      </div>
    )
  }

  return (
    <div
      className="fixed inset-0 flex flex-col select-none"
      style={{
        background: styles.bg,
        paddingBottom: 'env(safe-area-inset-bottom)',
        paddingLeft: 'env(safe-area-inset-left)',
        paddingRight: 'env(safe-area-inset-right)',
      }}
    >
      {/* ═══ Header - overlay, hidden by default, shown on tap ═══ */}
      <header
        className="absolute top-0 left-0 right-0 z-30 backdrop-blur-md"
        style={{
          background: styles.headerBg,
          borderBottom: `1px solid ${styles.headerBorder}`,
          paddingTop: 'env(safe-area-inset-top)',
          transform: headerVisible ? 'translateY(0)' : 'translateY(-100%)',
          transition: 'transform 0.25s ease',
          pointerEvents: headerVisible ? 'auto' : 'none',
        }}
      >
        <div className="flex items-center justify-between px-3 sm:px-5 h-12">
          <div className="flex items-center gap-2.5 min-w-0 flex-1">
            <button
              onClick={() => window.history.back()}
              className="p-2 -ml-1 rounded-xl hover:opacity-80 transition shrink-0 active:scale-95"
              style={{ color: styles.text }}
              aria-label="Go back"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5"/><path d="m12 19-7-7 7-7"/></svg>
            </button>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold truncate" style={{ color: styles.text }}>
                {title || 'Reader'}
              </div>
              {currentChapter && (
                <div className="text-[11px] truncate" style={{ color: styles.textMuted }}>
                  {currentChapter}
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center gap-0.5">
            <button
              onClick={() => { setTocOpen(!tocOpen); setShowControls(false) }}
              className="p-2.5 rounded-xl hover:opacity-80 transition active:scale-95"
              style={{ color: styles.text }}
              aria-label="Table of contents"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M3 12h18"/><path d="M3 6h18"/><path d="M3 18h18"/></svg>
            </button>
            <button
              onClick={() => { setShowControls(!showControls); setTocOpen(false) }}
              className="p-2.5 rounded-xl hover:opacity-80 transition active:scale-95"
              style={{ color: styles.text }}
              aria-label="Reading settings"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/></svg>
            </button>
          </div>
        </div>

        {/* ═══ Controls panel (inside header so it slides with it) ═══ */}
        {showControls && (
          <div
            className="px-4 sm:px-5 py-3.5 border-t"
            style={{ background: styles.controlBg, borderColor: styles.headerBorder }}
          >
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium" style={{ color: styles.textMuted }}>Font Size</span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setFontIndex(i => Math.max(i - 1, 0))}
                disabled={fontIndex === 0}
                className="w-9 h-9 rounded-xl border flex items-center justify-center text-xs font-bold disabled:opacity-20 transition active:scale-95"
                style={{ color: styles.controlText, borderColor: styles.headerBorder }}
                aria-label="Decrease font size"
              >A</button>
              <span className="text-xs w-7 text-center tabular-nums" style={{ color: styles.controlText }}>{FONT_SIZES[fontIndex]}</span>
              <button
                onClick={() => setFontIndex(i => Math.min(i + 1, FONT_SIZES.length - 1))}
                disabled={fontIndex === FONT_SIZES.length - 1}
                className="w-9 h-9 rounded-xl border flex items-center justify-center text-base font-bold disabled:opacity-20 transition active:scale-95"
                style={{ color: styles.controlText, borderColor: styles.headerBorder }}
                aria-label="Increase font size"
              >A</button>
            </div>
          </div>

          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium" style={{ color: styles.textMuted }}>Line Spacing</span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setLhIndex(i => Math.max(i - 1, 0))}
                disabled={lhIndex === 0}
                className="w-9 h-9 rounded-xl border flex items-center justify-center disabled:opacity-20 transition active:scale-95"
                style={{ color: styles.controlText, borderColor: styles.headerBorder }}
                aria-label="Decrease line spacing"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M3 8h18"/><path d="M3 16h18"/></svg>
              </button>
              <span className="text-xs w-7 text-center tabular-nums" style={{ color: styles.controlText }}>{LINE_HEIGHTS[lhIndex].toFixed(1)}</span>
              <button
                onClick={() => setLhIndex(i => Math.min(i + 1, LINE_HEIGHTS.length - 1))}
                disabled={lhIndex === LINE_HEIGHTS.length - 1}
                className="w-9 h-9 rounded-xl border flex items-center justify-center disabled:opacity-20 transition active:scale-95"
                style={{ color: styles.controlText, borderColor: styles.headerBorder }}
                aria-label="Increase line spacing"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M3 6h18"/><path d="M3 18h18"/></svg>
              </button>
            </div>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-xs font-medium" style={{ color: styles.textMuted }}>Theme</span>
            <div className="flex items-center gap-2">
              {(['light', 'sepia', 'dark'] as Theme[]).map(t => (
                <button
                  key={t}
                  onClick={() => setTheme(t)}
                  className="w-9 h-9 rounded-full border-2 transition active:scale-95 flex items-center justify-center"
                  style={{
                    background: THEME_STYLES[t].bg,
                    borderColor: theme === t ? styles.progressFill : styles.headerBorder,
                    boxShadow: theme === t ? `0 0 0 2px ${styles.bg}, 0 0 0 4px ${styles.progressFill}` : 'none',
                  }}
                  aria-label={`${t} theme`}
                >
                  {theme === t && (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={THEME_STYLES[t].progressFill} strokeWidth="3" strokeLinecap="round"><path d="M20 6 9 17l-5-5"/></svg>
                  )}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
      </header>

      {/* ═══ TOC Drawer ═══ */}
      {tocOpen && (
        <>
          <div className="fixed inset-0 z-40" style={{ background: styles.overlay }} onClick={() => setTocOpen(false)} />
          <div
            className="fixed top-0 left-0 bottom-0 w-[280px] sm:w-80 z-50 overflow-y-auto shadow-2xl"
            style={{ background: styles.tocBg, paddingTop: 'env(safe-area-inset-top)', paddingBottom: 'env(safe-area-inset-bottom)' }}
          >
            <div className="flex items-center justify-between px-4 h-12 border-b sticky top-0 z-10" style={{ borderColor: styles.headerBorder, background: styles.tocBg }}>
              <span className="text-sm font-semibold" style={{ color: styles.text }}>Contents</span>
              <button onClick={() => setTocOpen(false)} className="p-2 rounded-xl hover:opacity-80 active:scale-95" style={{ color: styles.text }} aria-label="Close contents">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
              </button>
            </div>
            <nav className="py-1">
              {toc.map((item, i) => (
                <div key={i}>
                  <button
                    onClick={() => goToHref(item.href)}
                    className="w-full text-left px-4 py-3 text-sm transition active:scale-[0.98]"
                    style={{ color: styles.text, background: currentChapter === item.label ? styles.tocActive : 'transparent', fontWeight: currentChapter === item.label ? 600 : 400 }}
                  >
                    {item.label}
                  </button>
                  {item.subitems?.map((sub, j) => (
                    <button
                      key={j}
                      onClick={() => goToHref(sub.href)}
                      className="w-full text-left pl-8 pr-4 py-2.5 text-xs transition active:scale-[0.98]"
                      style={{ color: styles.textMuted, background: currentChapter === sub.label ? styles.tocActive : 'transparent' }}
                    >
                      {sub.label}
                    </button>
                  ))}
                </div>
              ))}
              {toc.length === 0 && (
                <p className="px-4 py-8 text-sm text-center" style={{ color: styles.textMuted }}>No table of contents available.</p>
              )}
            </nav>
          </div>
        </>
      )}

      {/* ═══ Loading overlay ═══ */}
      {!ready && !error && (
        <div className="absolute inset-0 flex items-center justify-center z-10" style={{ background: styles.bg }}>
          <div className="text-center px-6">
            <div className="w-10 h-10 border-2 border-t-transparent rounded-full animate-spin mx-auto mb-4" style={{ borderColor: styles.progressFill, borderTopColor: 'transparent' }} />
            <p className="text-sm font-medium" style={{ color: styles.text }}>Opening your book...</p>
            <p className="text-xs mt-1" style={{ color: styles.textMuted }}>This may take a moment for larger books</p>
          </div>
        </div>
      )}

      {/* ═══ Resumed reading toast ═══ */}
      {resumed && (
        <div
          className="absolute top-4 left-1/2 -translate-x-1/2 z-40 px-4 py-2 rounded-full text-xs font-medium shadow-lg animate-in fade-in slide-in-from-top-4 duration-300"
          style={{ background: styles.progressFill, color: '#fff', marginTop: 'env(safe-area-inset-top)' }}
        >
          Resumed where you left off
        </div>
      )}

      {/* ═══ Reader content area ═══ */}
      <div
        ref={containerRef}
        className="flex-1 relative overflow-hidden"
        style={{ background: styles.bg }}
      />

      {/* ═══ Desktop side navigation ═══ */}
      {ready && (
        <>
          <button
            onClick={goPrev}
            disabled={atStart}
            className="hidden sm:flex fixed left-3 top-1/2 -translate-y-1/2 z-20 w-11 h-24 items-center justify-center rounded-xl transition-all hover:scale-105 disabled:opacity-10 active:scale-95"
            style={{ background: styles.btnBg, color: styles.text, border: `1px solid ${styles.btnBorder}`, backdropFilter: 'blur(8px)' }}
            aria-label="Previous page"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="m15 18-6-6 6-6"/></svg>
          </button>
          <button
            onClick={goNext}
            disabled={atEnd}
            className="hidden sm:flex fixed right-3 top-1/2 -translate-y-1/2 z-20 w-11 h-24 items-center justify-center rounded-xl transition-all hover:scale-105 disabled:opacity-10 active:scale-95"
            style={{ background: styles.btnBg, color: styles.text, border: `1px solid ${styles.btnBorder}`, backdropFilter: 'blur(8px)' }}
            aria-label="Next page"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="m9 18 6-6-6-6"/></svg>
          </button>
        </>
      )}

      {/* ═══ Footer - always visible ═══ */}
      {ready && (
        <footer
          className="shrink-0 z-30 border-t backdrop-blur-sm"
          style={{ background: styles.headerBg, borderColor: styles.headerBorder }}
        >
          {/* Progress bar */}
          <div className="h-[3px] w-full" style={{ background: styles.progressBg }}>
            <div className="h-full rounded-r-full" style={{ width: `${progress}%`, background: styles.progressFill, transition: 'width 0.5s ease' }} />
          </div>

          <div className="flex items-center justify-between px-2 sm:px-5 h-12">
            {/* Prev */}
            <button
              onClick={goPrev}
              disabled={atStart}
              className="p-3 rounded-xl disabled:opacity-15 transition active:scale-90"
              style={{ color: styles.text }}
              aria-label="Previous page"
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="m15 18-6-6 6-6"/></svg>
            </button>

            {/* Progress */}
            <div className="flex-1 text-center">
              <span className="text-xs tabular-nums font-medium" style={{ color: styles.textMuted }}>
                {progress}%
              </span>
              {totalLocations > 0 && (
                <span className="text-[10px] ml-1.5" style={{ color: styles.textMuted, opacity: 0.6 }}>
                  · {totalLocations} pages
                </span>
              )}
            </div>

            {/* Next */}
            <button
              onClick={goNext}
              disabled={atEnd}
              className="p-3 rounded-xl disabled:opacity-15 transition active:scale-90"
              style={{ color: styles.text }}
              aria-label="Next page"
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="m9 18 6-6-6-6"/></svg>
            </button>
          </div>
        </footer>
      )}
    </div>
  )
}
