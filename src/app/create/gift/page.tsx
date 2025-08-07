'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@clerk/nextjs'
import { BookLengthTier, BookBibleData } from '@/lib/types'

export default function CreateGiftBookPage() {
  const router = useRouter()
  const { getToken, isSignedIn } = useAuth()

  const [isSubmitting, setIsSubmitting] = useState(false)

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
      router.push(`/project/${projectId}/references`)
    } catch (e) {
      console.error('Gift book creation failed', e)
      setIsSubmitting(false)
    }
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-3xl">
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-bold text-gray-900">Create a Gift Book</h1>
        <p className="mt-2 text-gray-600">Craft a personalized story as a gift — thoughtful, joyful, and uniquely theirs.</p>
      </div>

      <div className="bg-white rounded-xl border p-6 space-y-5">
        <div className="grid md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-2">Recipient Name *</label>
            <input className="w-full border rounded-md px-3 py-2" value={form.recipient_name} onChange={e => update('recipient_name', e.target.value)} placeholder="e.g., Ava" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">Relationship</label>
            <select className="w-full border rounded-md px-3 py-2" value={form.relationship} onChange={e => update('relationship', e.target.value)}>
              <option>Parent</option>
              <option>Child</option>
              <option>Partner</option>
              <option>Friend</option>
              <option>Grandparent</option>
            </select>
          </div>
        </div>

        <div className="grid md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-2">Occasion</label>
            <select className="w-full border rounded-md px-3 py-2" value={form.occasion} onChange={e => update('occasion', e.target.value)}>
              <option>Birthday</option>
              <option>Holiday</option>
              <option>Anniversary</option>
              <option>Just Because</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">Age Range</label>
            <select className="w-full border rounded-md px-3 py-2" value={form.age_range} onChange={e => update('age_range', e.target.value)}>
              <option>Child</option>
              <option>Teen</option>
              <option>Adult</option>
            </select>
          </div>
        </div>

        <div className="grid md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-2">Favorite Theme *</label>
            <select className="w-full border rounded-md px-3 py-2" value={form.favorite_themes} onChange={e => update('favorite_themes', e.target.value)}>
              <option>Superhero</option>
              <option>Adventure</option>
              <option>Fantasy</option>
              <option>Space</option>
              <option>Mystery</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">Tone</label>
            <select className="w-full border rounded-md px-3 py-2" value={form.tone} onChange={e => update('tone', e.target.value)}>
              <option>Heartwarming</option>
              <option>Playful</option>
              <option>Epic</option>
              <option>Inspirational</option>
            </select>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Favorite Traits (one per line)</label>
          <textarea className="w-full border rounded-md px-3 py-2 min-h-[100px]" value={form.favorite_traits} onChange={e => update('favorite_traits', e.target.value)} placeholder={"Brave\nKind\nCreative"} />
        </div>

        <div className="grid md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-2">Book Length</label>
            <select className="w-full border rounded-md px-3 py-2" value={form.length_tier} onChange={e => update('length_tier', e.target.value as unknown as BookLengthTier)}>
              <option value={BookLengthTier.NOVELLA}>Novella</option>
              <option value={BookLengthTier.SHORT_NOVEL}>Short Novel</option>
              <option value={BookLengthTier.STANDARD_NOVEL}>Standard Novel</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">Custom Chapters (optional)</label>
            <input className="w-full border rounded-md px-3 py-2" value={form.custom_chapters} onChange={e => update('custom_chapters', e.target.value)} placeholder="e.g., 12" />
          </div>
        </div>

        <div className="grid md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-2">From</label>
            <input className="w-full border rounded-md px-3 py-2" value={form.from_name} onChange={e => update('from_name', e.target.value)} placeholder="Your name" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">Dedication (optional)</label>
            <input className="w-full border rounded-md px-3 py-2" value={form.dedication} onChange={e => update('dedication', e.target.value)} placeholder="A short personal message" />
          </div>
        </div>

        <div className="flex justify-end gap-3">
          <button onClick={() => router.back()} className="px-4 py-2 border rounded-lg">Cancel</button>
          <button onClick={handleSubmit} disabled={isSubmitting || !form.recipient_name.trim() || !form.favorite_themes.trim()} className="px-6 py-2 bg-brand-forest text-white rounded-lg disabled:opacity-50">
            {isSubmitting ? 'Creating…' : 'Create Gift Book'}
          </button>
        </div>
      </div>
    </div>
  )
}


