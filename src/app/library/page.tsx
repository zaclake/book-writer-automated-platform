'use client'

import React, { useEffect, useMemo, useState } from 'react'
import { useUser } from '@clerk/nextjs'
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
}

export default function LibraryPage() {
  const { user } = useUser()
  const [myBooks, setMyBooks] = useState<BookCard[]>([])
  const [publicBooks, setPublicBooks] = useState<BookCard[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [publishing, setPublishing] = useState<Record<string, boolean>>({})

  useEffect(() => {
    let mounted = true
    async function load() {
      try {
        const res = await fetch('/api/v2/library')
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
    if (!nextCursor) return
    const url = new URL('/api/v2/library', window.location.origin)
    url.searchParams.set('cursor', nextCursor)
    const res = await fetch(url.toString())
    if (!res.ok) return
    const json = await res.json()
    setPublicBooks(prev => [...prev, ...(json.public_projects || [])])
    setNextCursor(json.next_cursor || null)
  }

  const isOwner = useMemo(() => new Set(myBooks.map(b => b.owner_id)), [myBooks])

  const reload = async () => {
    try {
      const res = await fetch('/api/v2/library')
      if (!res.ok) return
      const json = await res.json()
      setMyBooks(json.my_projects || [])
      setPublicBooks(json.public_projects || [])
      setNextCursor(json.next_cursor || null)
    } catch {}
  }

  const startPublish = async (projectId: string, title: string) => {
    try {
      setPublishing(prev => ({ ...prev, [projectId]: true }))
      const author = user ? [user.firstName, user.lastName].filter(Boolean).join(' ') : ''
      const res = await fetch(`/api/v2/publish/project/${encodeURIComponent(projectId)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          config: {
            title,
            author,
            formats: ['epub']
          }
        })
      })
      if (!res.ok) throw new Error(await res.text())
      const { job_id } = await res.json()

      if (job_id) {
        // Poll job status
        const poll = async () => {
          const st = await fetch(`/api/v2/publish/${encodeURIComponent(job_id)}`)
          if (!st.ok) return setTimeout(poll, 4000)
          const data = await st.json()
          if (data.status === 'completed') {
            await reload()
            setPublishing(prev => ({ ...prev, [projectId]: false }))
          } else if (data.status === 'failed') {
            setPublishing(prev => ({ ...prev, [projectId]: false }))
          } else {
            setTimeout(poll, 4000)
          }
        }
        poll()
      } else {
        setPublishing(prev => ({ ...prev, [projectId]: false }))
      }
    } catch {
      setPublishing(prev => ({ ...prev, [projectId]: false }))
    }
  }

  const BookTile: React.FC<{ book: BookCard; mine?: boolean }> = ({ book, mine }) => {
    const canDownload = Boolean(book.epub_url)
    return (
      <div
        className="group bg-white border border-gray-200 rounded-xl overflow-hidden hover:shadow-md transition cursor-pointer"
        onClick={() => window.location.href = `/reader/${encodeURIComponent(book.project_id)}`}
      >
        <div className="aspect-[3/4] bg-gray-50 flex items-center justify-center">
          {book.cover_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={`${book.cover_url}${book.cover_url.includes('?') ? '&' : '?'}t=${Date.now()}`}
              alt={book.title}
              className="w-full h-full object-cover"
              onError={(e) => {
                console.error('Failed to load cover image', book.cover_url)
                // @ts-ignore
                e.currentTarget.style.display = 'none'
              }}
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center p-6">
              <div className="text-center">
                <div className="text-lg font-semibold text-gray-900 line-clamp-3">{book.title}</div>
              </div>
            </div>
          )}
        </div>
        <div className="p-3">
          <div className="text-sm font-semibold text-gray-900 truncate" title={book.title}>{book.title}</div>
          <div className="text-xs text-gray-600 truncate">{book.author_name || ''}</div>
          {book.genre && <div className="text-xs text-gray-500">{book.genre}</div>}
          {mine && (
            <div className="mt-2">
              <LibraryVisibilityToggle projectId={book.project_id} current={book.visibility} onUpdated={reload as any} />
            </div>
          )}
          {/* Owner-only download links */}
          {mine && (book.epub_url || book.pdf_url) && (
            <div className="mt-2 flex gap-2">
              {book.epub_url && (
                <a
                  className="text-xs text-brand-soft-purple hover:underline"
                  href={`/api/v2/library/book/${encodeURIComponent(book.project_id)}/epub`}
                  download
                  onClick={(e) => e.stopPropagation()}
                >
                  Download EPUB
                </a>
              )}
              {book.pdf_url && (
                <a
                  className="text-xs text-orange-600 hover:underline"
                  href={`/api/v2/library/book/${encodeURIComponent(book.project_id)}/pdf`}
                  download
                  onClick={(e) => e.stopPropagation()}
                >
                  Download PDF
                </a>
              )}
            </div>
          )}
        </div>
      </div>
    )
  }

  if (error) {
    return <div className="min-h-screen flex items-center justify-center text-red-600">{error}</div>
  }

  return (
    <div className="min-h-screen bg-white py-10">
      <div className="max-w-6xl mx-auto px-6">
        <h1 className="text-3xl font-bold text-gray-900 mb-6">Library</h1>

        <section className="mb-10">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold text-gray-900">My Books</h2>
            {loading && <div className="text-sm text-gray-500">Loading…</div>}
          </div>
          {myBooks.length === 0 && !loading ? (
            <div className="text-gray-600">No books yet.</div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
              {myBooks.map((b) => (
                <BookTile key={`my-${b.project_id}`} book={b} mine />
              ))}
            </div>
          )}
        </section>

        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold text-gray-900">Public Library</h2>
          </div>
          {publicBooks.length === 0 && !loading ? (
            <div className="text-gray-600">No public books yet.</div>
          ) : (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
                {publicBooks.map((b) => (
                  <BookTile key={`pub-${b.project_id}`} book={b} />
                ))}
              </div>
              {nextCursor && (
                <div className="flex justify-center mt-6">
                  <button className="px-4 py-2 rounded border border-gray-300 hover:bg-gray-50" onClick={loadMore}>Load more</button>
                </div>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  )
}