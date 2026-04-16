'use client'

import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchApi } from '@/lib/api-client'
import LibraryVisibilityToggle from '@/components/LibraryVisibilityToggle'

interface BookCard {
  project_id: string
  title: string
  author_name?: string
  owner_id: string
  genre?: string
  visibility: 'private' | 'shared' | 'public'
  cover_url?: string
  epub_url?: string
  pdf_url?: string
  kdp_kit_url?: string
  kdp_package_url?: string
  cover_art_download_url?: string
}

type SortKey = 'title' | 'genre' | 'recent'

const DownloadIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
)

function DownloadChip({
  href,
  label,
  colorClass,
}: {
  href: string
  label: string
  colorClass: string
}) {
  return (
    <a
      className={`inline-flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded-md transition ${colorClass}`}
      href={href}
      download
      onClick={(e) => e.stopPropagation()}
    >
      <DownloadIcon />
      {label}
    </a>
  )
}

function SkeletonTile() {
  return (
    <div className="bg-white rounded-2xl overflow-hidden shadow-sm border border-gray-100 animate-pulse">
      <div className="aspect-[2/3] bg-gray-100" />
      <div className="p-3 space-y-2">
        <div className="h-3.5 bg-gray-100 rounded w-3/4" />
        <div className="h-3 bg-gray-50 rounded w-1/2" />
      </div>
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="col-span-full flex flex-col items-center justify-center py-16 text-center">
      <div className="text-5xl mb-4 opacity-30">📚</div>
      <p className="text-gray-500 text-sm max-w-xs">{message}</p>
    </div>
  )
}

const BookTile = React.memo(function BookTile({
  book,
  mine,
  cacheBuster,
  onReload,
}: {
  book: BookCard
  mine?: boolean
  cacheBuster: string
  onReload: () => void
}) {
  const [showMore, setShowMore] = useState(false)

  const pid = encodeURIComponent(book.project_id)
  const hasSecondary = !!(book.kdp_package_url || book.kdp_kit_url || book.cover_art_download_url)

  return (
    <div
      role="link"
      tabIndex={0}
      onClick={() => { window.location.href = `/reader/${pid}` }}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); window.location.href = `/reader/${pid}` } }}
      className="group relative bg-white rounded-2xl overflow-hidden shadow-sm hover:shadow-xl focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 transition-all duration-300 border border-gray-100 hover:border-gray-200 hover:-translate-y-1 cursor-pointer"
      aria-label={`Read ${book.title}`}
    >
      <div className="aspect-[2/3] bg-gradient-to-br from-gray-50 to-gray-100 relative overflow-hidden">
        {book.cover_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={
              cacheBuster
                ? `${book.cover_url}${book.cover_url.includes('?') ? '&' : '?'}t=${cacheBuster}`
                : book.cover_url
            }
            alt={book.title}
            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = 'none'
            }}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center p-6 bg-gradient-to-br from-indigo-50 via-purple-50 to-pink-50">
            <div className="text-center">
              <div className="text-4xl mb-3 opacity-40">📖</div>
              <div className="text-sm font-semibold text-gray-700 line-clamp-3 leading-snug">{book.title}</div>
            </div>
          </div>
        )}
        {book.genre && (
          <div className="absolute top-2 right-2">
            <span className="px-2 py-0.5 text-[10px] font-medium bg-black/60 text-white rounded-full backdrop-blur-sm">
              {book.genre}
            </span>
          </div>
        )}
      </div>

      <div className="p-3 space-y-1">
        <h3 className="text-sm font-semibold text-gray-900 truncate leading-tight" title={book.title}>
          {book.title}
        </h3>
        {book.author_name && (
          <p className="text-xs text-gray-500 truncate">{book.author_name}</p>
        )}

        {mine && (
          <div className="pt-1.5 space-y-2">
            <div className="flex items-center gap-2">
              <LibraryVisibilityToggle projectId={book.project_id} current={book.visibility} onUpdated={onReload} />
              <a
                href={`/project/${pid}/publish`}
                onClick={(e) => e.stopPropagation()}
                className="inline-flex items-center gap-1 px-2 py-1 text-[11px] font-medium text-gray-600 hover:text-gray-900 bg-gray-50 hover:bg-gray-100 rounded-md transition"
                title="Edit project"
              >
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                Edit
              </a>
            </div>

            {(book.epub_url || book.pdf_url) && (
              <div className="flex gap-2 flex-wrap">
                {book.epub_url && (
                  <DownloadChip
                    href={`/api/v2/library/book/${pid}/epub`}
                    label="EPUB"
                    colorClass="text-indigo-700 bg-indigo-50 hover:bg-indigo-100"
                  />
                )}
                {book.pdf_url && (
                  <DownloadChip
                    href={`/api/v2/library/book/${pid}/pdf`}
                    label="PDF"
                    colorClass="text-orange-700 bg-orange-50 hover:bg-orange-100"
                  />
                )}

                {hasSecondary && (
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); setShowMore(v => !v) }}
                    className="inline-flex items-center gap-0.5 px-2 py-1 text-[11px] font-medium text-gray-500 hover:text-gray-700 bg-gray-50 hover:bg-gray-100 rounded-md transition"
                    aria-label={showMore ? 'Hide additional downloads' : 'Show additional downloads'}
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className={`transition-transform ${showMore ? 'rotate-180' : ''}`}><polyline points="6 9 12 15 18 9"/></svg>
                    More
                  </button>
                )}
              </div>
            )}

            {showMore && hasSecondary && (
              <div className="flex gap-2 flex-wrap">
                {book.kdp_package_url && (
                  <DownloadChip
                    href={`/api/v2/library/book/${pid}/kdp-package`}
                    label="KDP Package"
                    colorClass="text-amber-700 bg-amber-50 hover:bg-amber-100"
                  />
                )}
                {book.kdp_kit_url && (
                  <DownloadChip
                    href={`/api/v2/library/book/${pid}/kdp-kit`}
                    label="KDP Kit"
                    colorClass="text-violet-700 bg-violet-50 hover:bg-violet-100"
                  />
                )}
                {book.cover_art_download_url && (
                  <DownloadChip
                    href={`/api/v2/library/book/${pid}/cover`}
                    label="Cover"
                    colorClass="text-emerald-700 bg-emerald-50 hover:bg-emerald-100"
                  />
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
})

export default function LibraryPage() {
  const [myBooks, setMyBooks] = useState<BookCard[]>([])
  const [publicBooks, setPublicBooks] = useState<BookCard[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('recent')
  const [coverCacheBuster] = useState(() => Date.now().toString())

  useEffect(() => {
    let mounted = true
    async function load() {
      try {
        const res = await fetchApi('/api/v2/library')
        if (!res.ok) throw new Error(await res.text())
        const json = await res.json()
        if (!mounted) return
        setMyBooks(json.my_projects || [])
        setPublicBooks(json.public_projects || [])
        setNextCursor(json.next_cursor || null)
      } catch (e: any) {
        if (mounted) setError(e?.message || 'Failed to load library')
      } finally {
        if (mounted) setLoading(false)
      }
    }
    load()
    return () => { mounted = false }
  }, [])

  const loadMore = async () => {
    if (!nextCursor || loadingMore) return
    setLoadingMore(true)
    try {
      const url = new URL('/api/v2/library', window.location.origin)
      url.searchParams.set('cursor', nextCursor)
      const res = await fetchApi(url.toString())
      if (!res.ok) return
      const json = await res.json()
      setPublicBooks(prev => [...prev, ...(json.public_projects || [])])
      setNextCursor(json.next_cursor || null)
    } finally {
      setLoadingMore(false)
    }
  }

  const reload = useCallback(async () => {
    try {
      const res = await fetchApi('/api/v2/library')
      if (!res.ok) return
      const json = await res.json()
      setMyBooks(json.my_projects || [])
      setPublicBooks(json.public_projects || [])
      setNextCursor(json.next_cursor || null)
    } catch {}
  }, [])

  const applySortAndFilter = useCallback((books: BookCard[]) => {
    let filtered = books
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      filtered = books.filter(
        b => b.title?.toLowerCase().includes(q) ||
             b.author_name?.toLowerCase().includes(q) ||
             b.genre?.toLowerCase().includes(q)
      )
    }
    const sorted = [...filtered]
    if (sortKey === 'title') sorted.sort((a, b) => (a.title || '').localeCompare(b.title || ''))
    else if (sortKey === 'genre') sorted.sort((a, b) => (a.genre || '').localeCompare(b.genre || ''))
    else if (sortKey === 'recent') sorted.reverse()
    return sorted
  }, [searchQuery, sortKey])

  const filteredMyBooks = useMemo(() => applySortAndFilter(myBooks), [myBooks, applySortAndFilter])
  const filteredPublicBooks = useMemo(() => applySortAndFilter(publicBooks), [publicBooks, applySortAndFilter])

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <div className="text-center max-w-md">
          <div className="text-5xl mb-4">📚</div>
          <h2 className="text-xl font-semibold text-gray-900 mb-2">Unable to Load Library</h2>
          <p className="text-gray-600 mb-6">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="px-6 py-2.5 bg-gray-900 text-white rounded-lg hover:bg-gray-800 transition"
          >
            Try Again
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b border-gray-200 sticky top-0 z-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 py-4">
            <div>
              <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Library</h1>
              <p className="text-sm text-gray-500 mt-0.5">
                {loading
                  ? 'Loading your library...'
                  : `${filteredMyBooks.length + filteredPublicBooks.length} book${filteredMyBooks.length + filteredPublicBooks.length !== 1 ? 's' : ''}${searchQuery ? ' found' : ' available'}`
                }
              </p>
            </div>
            <div className="flex items-center gap-2">
              <div className="relative flex-1 sm:flex-none">
                <svg className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
                <input
                  type="text"
                  placeholder="Search books..."
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  aria-label="Search books"
                  className="w-full sm:w-64 pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-lg bg-gray-50 focus:bg-white focus:border-gray-300 focus:ring-1 focus:ring-gray-300 outline-none transition"
                />
              </div>
              <select
                value={sortKey}
                onChange={e => setSortKey(e.target.value as SortKey)}
                aria-label="Sort books"
                className="text-sm border border-gray-200 rounded-lg px-3 py-2 bg-gray-50 focus:bg-white focus:border-gray-300 outline-none transition cursor-pointer"
              >
                <option value="recent">Recent</option>
                <option value="title">Title</option>
                <option value="genre">Genre</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-12">
        <section>
          <div className="flex items-center gap-3 mb-5">
            <h2 className="text-lg font-semibold text-gray-900">My Books</h2>
            {!loading && (
              <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
                {filteredMyBooks.length}
              </span>
            )}
          </div>

          {loading ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
              {Array.from({ length: 6 }).map((_, i) => <SkeletonTile key={i} />)}
            </div>
          ) : filteredMyBooks.length === 0 ? (
            <EmptyState message={searchQuery ? 'No books match your search.' : 'No published books yet. Publish your first book to see it here.'} />
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
              {filteredMyBooks.map(b => <BookTile key={`my-${b.project_id}`} book={b} mine cacheBuster={coverCacheBuster} onReload={reload} />)}
            </div>
          )}
        </section>

        <section>
          <div className="flex items-center gap-3 mb-5">
            <h2 className="text-lg font-semibold text-gray-900">Public Library</h2>
            {!loading && (
              <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
                {filteredPublicBooks.length}
              </span>
            )}
          </div>

          {loading ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
              {Array.from({ length: 12 }).map((_, i) => <SkeletonTile key={i} />)}
            </div>
          ) : filteredPublicBooks.length === 0 ? (
            <EmptyState message={searchQuery ? 'No public books match your search.' : 'No public books available yet.'} />
          ) : (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
                {filteredPublicBooks.map(b => <BookTile key={`pub-${b.project_id}`} book={b} cacheBuster={coverCacheBuster} onReload={reload} />)}
              </div>
              {nextCursor && (
                <div className="flex justify-center mt-8">
                  <button
                    onClick={loadMore}
                    disabled={loadingMore}
                    className="px-6 py-2.5 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 hover:border-gray-300 transition disabled:opacity-50"
                  >
                    {loadingMore ? 'Loading...' : 'Load More'}
                  </button>
                </div>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  )
}
