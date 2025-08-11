'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@clerk/nextjs'
import { BookLengthTier, BookBibleData } from '@/lib/types'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import Celebration from '@/components/ui/Celebration'
import { GlobalLoader } from '@/stores/useGlobalLoaderStore'

export default function CreateGiftBookPage() {
  const router = useRouter()
  const { getToken, isSignedIn } = useAuth()

  const [isSubmitting, setIsSubmitting] = useState(false)
  const [showCelebration, setShowCelebration] = useState(false)

  const [form, setForm] = useState({
    recipient_name: '',
    relationship: 'Parent',
    age_range: 'Adult',
    occasion: 'Birthday',
    favorite_traits: '',
    favorite_themes: 'Superhero',
    tone: 'Heartwarming',
    length_tier: BookLengthTier.NOVELLA,
    custom_chapters: '',
    from_name: '',
    dedication: ''
  })

  const update = (field: keyof typeof form, value: string) => {
    setForm(prev => ({ ...prev, [field]: value }))
  }

  const generateGiftBookBible = () => {
    const title = `${form.recipient_name ? form.recipient_name + "'s " : ''}${form.favorite_themes} Adventure`
    const traits = form.favorite_traits
      .split('\n')
      .map(s => s.trim())
      .filter(Boolean)
      .map(t => `- ${t}`)
      .join('\n') || '- Kind'

    const dedication = form.dedication?.trim()
      ? `> ${form.dedication.trim()}\n\n— ${form.from_name || 'With love'}`
      : form.from_name?.trim() ? `> For ${form.recipient_name}, with love.\n\n— ${form.from_name}` : ''

    return `# ${title}

## Project Overview
- **Purpose:** Personalized gift book
- **Recipient:** ${form.recipient_name || 'Your Loved One'} (${form.relationship})
- **Occasion:** ${form.occasion}
- **Tone:** ${form.tone}
- **Theme:** ${form.favorite_themes}

${dedication ? `## Dedication\n${dedication}\n` : ''}

## Hero Profile
${form.recipient_name || 'Our Hero'} is portrayed as a courageous, caring lead inspired by real-life qualities.

### Signature Traits
${traits}

## Story Premise
In this heart-forward ${form.favorite_themes.toLowerCase()} tale, ${form.recipient_name || 'our hero'} rises to meet an unforgettable challenge—celebrating the spirit of ${form.relationship.toLowerCase()} and the joy of ${form.occasion.toLowerCase()}.

## Setting & World
- A vibrant city where wonder meets everyday life.
- Familiar places transformed into magical set pieces.

## Plot Arc (Three Acts)
1. Call to Adventure — A heartfelt need appears close to home.
2. Trials & Discovery — Lessons of kindness, courage, and creativity.
3. The Gift — A meaningful resolution that honors ${form.recipient_name || 'the hero'}.

## Chapter Outline (Initial)
*[Detailed outline will be generated to match the selected length and tone.]*
`
  }

  const handleSubmit = async () => {
    if (!isSignedIn) return
    if (!form.recipient_name.trim() || !form.favorite_themes.trim()) return
    setIsSubmitting(true)
    GlobalLoader.show({
      title: 'Creating Gift Project',
      stage: 'Preparing content...',
      showProgress: false,
      size: 'md',
      customMessages: [
        '🎁 Personalizing your story...',
        '📚 Building your book bible...',
        '✨ Setting up your creative space...',
      ],
      timeoutMs: 900000,
    })
    try {
      const token = await getToken()
      if (!token) throw new Error('No auth token')

      const content = generateGiftBookBible()
      const generatedTitle = `${form.recipient_name ? form.recipient_name + "'s " : ''}${form.favorite_themes} Adventure`
      if (generatedTitle.length > 100) {
        throw new Error('Title too long; please shorten inputs')
      }
      const targetChapters = form.custom_chapters
        ? Math.max(1, Math.min(50, parseInt(form.custom_chapters) || 10))
        : 12

      const payload: BookBibleData = {
        title: generatedTitle,
        genre: 'Gift Fiction',
        target_chapters: targetChapters,
        word_count_per_chapter: 2000,
        content,
        must_include_sections: [],
        creation_mode: 'paste',
        book_length_tier: form.length_tier,
        estimated_chapters: targetChapters,
        target_word_count: targetChapters * 2000,
        include_series_bible: false
      }

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

      localStorage.setItem('lastProjectId', projectId)
      localStorage.setItem(`projectTitle-${projectId}`, payload.title)
      setShowCelebration(true)
      setTimeout(() => {
        GlobalLoader.hide()
        router.push(`/project/${projectId}/references`)
      }, 800)
    } catch (e) {
      console.error('Gift book creation failed', e)
      setIsSubmitting(false)
      GlobalLoader.hide()
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
            <h1 className="text-4xl font-black text-white mb-3 tracking-tight">Create a Gift Book</h1>
            <p className="text-white/90 text-lg font-medium">Craft a personalized story — thoughtful, joyful, and uniquely theirs.</p>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="w-full px-6 md:px-8 lg:px-12 py-10">
        <Card className="bg-white/60 backdrop-blur-sm border border-white/50 shadow-xl max-w-4xl mx-auto">
          <CardContent className="p-6 md:p-8 space-y-6">
            <div className="grid md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Recipient Name *</Label>
                <Input value={form.recipient_name} onChange={e => update('recipient_name', e.target.value)} placeholder="e.g., Ava" />
              </div>
              <div className="space-y-2">
                <Label>Relationship</Label>
                <select className="w-full p-3 min-h-[44px] border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-base" value={form.relationship} onChange={e => update('relationship', e.target.value)}>
                  <option>Parent</option>
                  <option>Child</option>
                  <option>Partner</option>
                  <option>Friend</option>
                  <option>Grandparent</option>
                </select>
              </div>
            </div>

            <div className="grid md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Occasion</Label>
                <select className="w-full p-3 min-h-[44px] border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-base" value={form.occasion} onChange={e => update('occasion', e.target.value)}>
                  <option>Birthday</option>
                  <option>Holiday</option>
                  <option>Anniversary</option>
                  <option>Just Because</option>
                </select>
              </div>
              <div className="space-y-2">
                <Label>Age Range</Label>
                <select className="w-full p-3 min-h-[44px] border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-base" value={form.age_range} onChange={e => update('age_range', e.target.value)}>
                  <option>Child</option>
                  <option>Teen</option>
                  <option>Adult</option>
                </select>
              </div>
            </div>

            <div className="grid md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Favorite Theme *</Label>
                <select className="w-full p-3 min-h-[44px] border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-base" value={form.favorite_themes} onChange={e => update('favorite_themes', e.target.value)}>
                  <option>Superhero</option>
                  <option>Adventure</option>
                  <option>Fantasy</option>
                  <option>Space</option>
                  <option>Mystery</option>
                </select>
              </div>
              <div className="space-y-2">
                <Label>Tone</Label>
                <select className="w-full p-3 min-h-[44px] border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-base" value={form.tone} onChange={e => update('tone', e.target.value)}>
                  <option>Heartwarming</option>
                  <option>Playful</option>
                  <option>Epic</option>
                  <option>Inspirational</option>
                </select>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Favorite Traits (one per line)</Label>
              <Textarea value={form.favorite_traits} onChange={e => update('favorite_traits', e.target.value)} placeholder={"Brave\nKind\nCreative"} rows={4} />
            </div>

            <div className="grid md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Book Length</Label>
                <select className="w-full p-3 min-h-[44px] border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-base" value={form.length_tier} onChange={e => update('length_tier', e.target.value as unknown as BookLengthTier)}>
                  <option value={BookLengthTier.NOVELLA}>Novella</option>
                  <option value={BookLengthTier.SHORT_NOVEL}>Short Novel</option>
                  <option value={BookLengthTier.STANDARD_NOVEL}>Standard Novel</option>
                </select>
              </div>
              <div className="space-y-2">
                <Label>Custom Chapters (optional)</Label>
                <Input value={form.custom_chapters} onChange={e => update('custom_chapters', e.target.value)} placeholder="e.g., 12" />
              </div>
            </div>

            <div className="grid md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>From</Label>
                <Input value={form.from_name} onChange={e => update('from_name', e.target.value)} placeholder="Your name" />
              </div>
              <div className="space-y-2">
                <Label>Dedication (optional)</Label>
                <Input value={form.dedication} onChange={e => update('dedication', e.target.value)} placeholder="A short personal message" />
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <Button variant="outline" onClick={() => router.back()}>
                Cancel
              </Button>
              <Button onClick={handleSubmit} disabled={isSubmitting || !form.recipient_name.trim() || !form.favorite_themes.trim()}>
                {isSubmitting ? 'Creating…' : 'Create Gift Book'}
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
      <Celebration isVisible={showCelebration} message="Project created" />
    </div>
  )
}


