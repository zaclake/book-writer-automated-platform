'use client'

import { BookBibleCreator } from '@/components/BookBibleCreator'
import { BookBibleData } from '@/lib/types'
import { useRouter } from 'next/navigation'
import { useAuth } from '@clerk/nextjs'

export default function CreateProjectPage() {
  const router = useRouter()
  const { getToken, isSignedIn } = useAuth()

  const handleComplete = async (data: BookBibleData) => {
    if (!isSignedIn) {
      console.error('User not signed in')
      router.push('/sign-in')
      return
    }

    try {
      // Get authentication token
      const token = await getToken()
      if (!token) {
        console.error('No auth token available')
        router.push('/sign-in')
        return
      }

      // The BookBibleCreator component only creates the book bible content.
      // We need to create the actual project by calling the create API.
      // This now includes synchronous reference generation.
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

      if (response.ok) {
        const result = await response.json()
        if (result.project?.id) {
          // Check if references were generated
          if (result.references_generated) {
            // Redirect to the reference review page
            router.push(`/project/${result.project.id}/references`)
          } else {
            // If no references generated, redirect to overview with a note
            router.push(`/project/${result.project.id}/overview?note=no-references`)
          }
        } else {
          // Fallback to dashboard
          router.push('/dashboard')
        }
      } else {
        console.error('Failed to create project:', await response.text())
        // Still redirect to dashboard so user can see their projects
        router.push('/dashboard')
      }
    } catch (error) {
      console.error('Error creating project:', error)
      // Fallback to dashboard
      router.push('/dashboard')
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