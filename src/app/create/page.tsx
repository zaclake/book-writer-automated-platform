'use client'

import { BookBibleCreator } from '@/components/BookBibleCreator'
import { BookBibleData } from '@/lib/types'
import { useRouter } from 'next/navigation'
import { useAuth } from '@clerk/nextjs'

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
    <div className="container mx-auto px-4 py-8 max-w-4xl">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">
          Create New Project
        </h1>
        <p className="mt-2 text-lg text-gray-600">
          Set up a new book writing project with AI assistance
        </p>
      </div>

      <BookBibleCreator 
        onComplete={handleComplete}
      />
    </div>
  )
} 