'use client'

import { BookBibleCreator } from '@/components/BookBibleCreator'
import { BookBibleData } from '@/lib/types'
import { useRouter } from 'next/navigation'
import { useAuth } from '@clerk/nextjs'
import { Card, CardContent } from '@/components/ui/card'

export default function CreateProjectPage() {
  const router = useRouter()
  const { getToken, isSignedIn, userId } = useAuth()

  const handleComplete = async (data: BookBibleData) => {
    if (!isSignedIn) {
      console.error('User not signed in')
      return { success: false }
    }

    try {
      const token = await getToken()
      if (!token) {
        console.error('No auth token available')
        return { success: false }
      }

      const response = await fetch('/api/book-bible/create', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          title: data.title,
          genre: data.genre,
          content: data.content,
          target_chapters: data.target_chapters,
          word_count_per_chapter: data.word_count_per_chapter,
          book_length_tier: data.book_length_tier,
          target_word_count: data.target_word_count,
          must_include_sections: data.must_include_sections || [],
          creation_mode: data.creation_mode || 'quickstart',
          estimated_chapters: data.estimated_chapters,
          include_series_bible: data.include_series_bible || false,
          source_data: data.source_data,
        }),
      })

      if (!response.ok) {
        console.error('Failed to create project:', await response.text())
        return { success: false }
      }

      const result = await response.json()

      if (!result.project?.id) {
        console.error('[book-bible/create] No project ID in response')
        return { success: false }
      }

      // Store basic project info for quick header display
      localStorage.setItem('lastProjectId', result.project.id)
      localStorage.setItem(`projectTitle-${result.project.id}`, data.title)

      return {
        success: true,
        projectId: result.project.id as string,
        referencesGenerated: !!result.references_generated
      }

    } catch (error) {
      console.error('Error creating project:', error)
      return { success: false }
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
            <h1 className="text-4xl font-black text-white mb-3 tracking-tight">Start from My Idea</h1>
            <p className="text-white/90 text-lg font-medium">Use QuickStart or the full Guided Wizard to transform your idea into a book bible.</p>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="w-full px-6 md:px-8 lg:px-12 py-10">
        <Card className="bg-white/60 backdrop-blur-sm border border-white/50 shadow-xl max-w-5xl mx-auto">
          <CardContent className="p-0 md:p-2">
            <BookBibleCreator onComplete={handleComplete} />
          </CardContent>
        </Card>
      </div>
    </div>
  )
} 