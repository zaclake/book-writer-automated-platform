'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@clerk/nextjs'
import { BookBibleData } from '@/lib/types'

export default function PasteIdeaPage() {
  const router = useRouter()
  const { getToken, isSignedIn } = useAuth()

  const [title, setTitle] = useState('')
  const [genre, setGenre] = useState('Fiction')
  const [content, setContent] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const deriveTitleFromContent = (text: string): string => {
    const lines = text.split('\n').map(l => l.trim()).filter(Boolean)
    if (lines.length === 0) return 'Untitled Idea'
    let candidate = lines[0]
    if (candidate.length > 100) candidate = candidate.slice(0, 100)
    return candidate
  }

  const handleSubmit = async () => {
    setError(null)
    if (!isSignedIn) { setError('Please sign in'); return }
    if (!content.trim() || content.trim().length < 50) { setError('Please paste at least 50 characters.'); return }
    const finalTitle = (title.trim() || deriveTitleFromContent(content)).trim()
    if (!finalTitle) { setError('Unable to derive a title from your idea. Please enter a title.'); return }
    if (finalTitle.length > 100) { setError('Title is too long. Please shorten it.'); return }
    setIsSubmitting(true)
    try {
      const token = await getToken()
      if (!token) throw new Error('No auth token')

      const payload: BookBibleData = {
        title: finalTitle,
        genre,
        target_chapters: 25,
        word_count_per_chapter: 2000,
        content,
        must_include_sections: [],
        creation_mode: 'paste'
      } as BookBibleData

      const res = await fetch('/api/book-bible/create', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(payload)
      })
      if (!res.ok) throw new Error(await res.text())
      const result = await res.json()
      const projectId = result?.project?.id
      if (!projectId) throw new Error('No project id returned')

      // Start generating references immediately
      await fetch(`/api/v2/projects/${projectId}/references/generate`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      })

      localStorage.setItem('lastProjectId', projectId)
      localStorage.setItem(`projectTitle-${projectId}`, finalTitle)
      router.push(`/project/${projectId}/references`)
    } catch (e) {
      console.error('Paste idea creation failed', e)
      setError(e instanceof Error ? e.message : 'Unknown error')
      setIsSubmitting(false)
    }
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-3xl">
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-bold text-gray-900">Copy & Paste Idea</h1>
        <p className="mt-2 text-gray-600">Paste your idea text and we’ll create your project and start generating reference files.</p>
      </div>

      <div className="bg-white rounded-xl border p-6 space-y-5">
        <div className="grid md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-2">Title (optional)</label>
            <input className="w-full border rounded-md px-3 py-2" value={title} onChange={e => setTitle(e.target.value)} placeholder="Auto-derived if left blank" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">Genre</label>
            <select className="w-full border rounded-md px-3 py-2" value={genre} onChange={e => setGenre(e.target.value)}>
              <option>Fiction</option>
              <option>Mystery</option>
              <option>Romance</option>
              <option>Science Fiction</option>
              <option>Fantasy</option>
              <option>Thriller</option>
              <option>Horror</option>
              <option>Literary</option>
              <option>Young Adult</option>
              <option>Non-Fiction</option>
            </select>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Your Idea *</label>
          <textarea className="w-full border rounded-md px-3 py-2 min-h-[240px] font-mono text-sm" value={content} onChange={e => setContent(e.target.value)} placeholder="Paste any outline, premise, character notes, or freeform idea..." />
          <p className="text-xs text-gray-500 mt-1">We’ll structure this into a proper book bible and kick off reference generation.</p>
        </div>

        {error && (
          <div className="text-sm text-red-600">{error}</div>
        )}

        <div className="flex justify-end gap-3">
          <button onClick={() => router.back()} className="px-4 py-2 border rounded-lg">Cancel</button>
          <button onClick={handleSubmit} disabled={isSubmitting || !content.trim()} className="px-6 py-2 bg-brand-forest text-white rounded-lg disabled:opacity-50">
            {isSubmitting ? 'Creating…' : 'Create and Generate References'}
          </button>
        </div>
      </div>
    </div>
  )
}


