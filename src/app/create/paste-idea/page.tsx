'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@clerk/nextjs'
import { BookBibleData } from '@/lib/types'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import Celebration from '@/components/ui/Celebration'

export default function PasteIdeaPage() {
  const router = useRouter()
  const { getToken, isSignedIn } = useAuth()

  const [title, setTitle] = useState('')
  const [genre, setGenre] = useState('Fiction')
  const [content, setContent] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showCelebration, setShowCelebration] = useState(false)

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
      setShowCelebration(true)
      setTimeout(() => router.push(`/project/${projectId}/references`), 800)
    } catch (e) {
      console.error('Paste idea creation failed', e)
      setError(e instanceof Error ? e.message : 'Unknown error')
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-brand-off-white">
      {/* Hero */}
      <div className="relative min-h-[32vh] bg-gradient-to-br from-brand-lavender via-brand-ink-blue to-brand-blush-orange overflow-hidden">
        <div className="absolute inset-0">
          <div className="absolute top-1/4 left-1/4 w-2 h-2 bg-white/20 rounded-full animate-float"></div>
          <div className="absolute top-1/3 right-1/4 w-1 h-1 bg-white/30 rounded-full animate-float" style={{animationDelay: '2s'}}></div>
          <div className="absolute bottom-1/3 left-1/3 w-3 h-3 bg-white/10 rounded-full animate-float" style={{animationDelay: '4s'}}></div>
        </div>
        <div className="absolute inset-0 bg-gradient-radial from-transparent via-transparent to-black/10"></div>
        <div className="relative z-10 flex items-center justify-center min-h-[32vh] px-6 md:px-8 lg:px-12">
          <div className="text-center max-w-3xl">
            <h1 className="text-4xl font-black text-white mb-3 tracking-tight">Copy & Paste Idea</h1>
            <p className="text-white/90 text-lg font-medium">Paste your idea and we’ll create your project and auto-generate references.</p>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="w-full px-6 md:px-8 lg:px-12 py-10">
        <Card className="bg-white/60 backdrop-blur-sm border border-white/50 shadow-xl max-w-4xl mx-auto">
          <CardContent className="p-6 md:p-8 space-y-6">
            <div className="grid md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Title (optional)</Label>
                <Input value={title} onChange={e => setTitle(e.target.value)} placeholder="Auto-derived if left blank" />
              </div>
              <div className="space-y-2">
                <Label>Genre</Label>
                <select className="w-full p-3 min-h-[44px] border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-base" value={genre} onChange={e => setGenre(e.target.value)}>
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

            <div className="space-y-2">
              <Label>Your Idea *</Label>
              <Textarea className="font-mono" rows={12} value={content} onChange={e => setContent(e.target.value)} placeholder="Paste any outline, premise, character notes, or freeform idea..." />
              <p className="text-xs text-gray-500">We’ll structure this into a proper book bible and kick off reference generation.</p>
            </div>

            {error && (
              <div className="text-sm text-red-600">{error}</div>
            )}

            <div className="flex justify-end gap-3 pt-2">
              <Button variant="outline" onClick={() => router.back()}>Cancel</Button>
              <Button onClick={handleSubmit} disabled={isSubmitting || !content.trim()}>{isSubmitting ? 'Creating…' : 'Create and Generate References'}</Button>
            </div>
          </CardContent>
        </Card>
        <Celebration isVisible={showCelebration} message="Project created" />
      </div>
    </div>
  )
}


