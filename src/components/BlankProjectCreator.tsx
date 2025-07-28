'use client'

import { useState } from 'react'
import { PencilIcon, BookOpenIcon } from '@heroicons/react/24/outline'
import { useAuthToken } from '@/lib/auth'
import { CreativeLoader } from './ui/CreativeLoader'

interface BlankProjectCreatorProps {
  onProjectInitialized: (projectId?: string) => void
}

export function BlankProjectCreator({ onProjectInitialized }: BlankProjectCreatorProps) {
  const { getAuthHeaders, isLoaded, isSignedIn } = useAuthToken()
  const [projectInfo, setProjectInfo] = useState({
    title: '',
    genre: 'Fiction',
    target_audience: 'Adult',
    target_chapters: 25,
    writing_style: 'Narrative'
  })
  const [isCreating, setIsCreating] = useState(false)
  const [status, setStatus] = useState('')

  const handleCreateProject = async () => {
    if (!isSignedIn) {
      setStatus('❌ Please sign in to create projects')
      return
    }

    if (!projectInfo.title.trim()) {
      setStatus('❌ Project title cannot be empty')
      return
    }

    setIsCreating(true)
    setStatus('🚀 Creating your new project...')

    try {
      const authHeaders = await getAuthHeaders()
      const projectId = `project-${Date.now()}`
      
      // Create a minimal book bible for the blank project
      const basicBookBible = `# ${projectInfo.title}

## Project Overview
- **Title:** ${projectInfo.title}
- **Genre:** ${projectInfo.genre}
- **Target Audience:** ${projectInfo.target_audience}
- **Target Chapters:** ${projectInfo.target_chapters}
- **Writing Style:** ${projectInfo.writing_style}

## Story Summary
*To be developed...*

## Main Characters
*To be developed...*

## Plot Outline
*To be developed...*

## Setting & World
*To be developed...*

## Themes & Motifs
*To be developed...*

---
*This is a blank project template. Expand each section as you develop your story.*`

      const response = await fetch('/api/book-bible/initialize', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders
        },
        body: JSON.stringify({
          project_id: projectId,
          content: basicBookBible
        })
      })

      const data = await response.json()

      if (response.ok) {
        setStatus('✅ Project created successfully!')
        
        // Store project info
        if (projectId) {
          localStorage.setItem('lastProjectId', projectId)
          localStorage.setItem(`bookBible-${projectId}`, basicBookBible)
        }
        
        setTimeout(() => {
          onProjectInitialized(projectId)
        }, 1500)
      } else {
        setStatus(`❌ Creation failed: ${data.error}`)
        setIsCreating(false)
      }
    } catch (error) {
      setStatus(`❌ Creation error: ${error instanceof Error ? error.message : 'Unknown error'}`)
      setIsCreating(false)
    }
  }

  if (!isLoaded) {
    return (
      <div className="text-center py-8">
        <div className="animate-pulse">
          <div className="h-4 bg-gray-200 rounded w-3/4 mx-auto mb-2"></div>
          <div className="h-4 bg-gray-200 rounded w-1/2 mx-auto"></div>
        </div>
      </div>
    )
  }

  if (!isSignedIn) {
    return (
      <div className="text-center py-8">
        <div className="text-gray-500 mb-4">Please sign in to create projects</div>
        <p className="text-sm text-gray-400">
          Authentication is required to create and manage projects.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="text-center">
        <PencilIcon className="w-12 h-12 mx-auto text-green-600 mb-4" />
        <h3 className="text-xl font-semibold text-gray-900 mb-2">
          Start Your Writing Journey
        </h3>
        <p className="text-gray-600">
          Tell us a bit about your story and we'll create a project structure to get you started.
        </p>
      </div>

      <div className="space-y-4">
        {/* Project Title */}
        <div>
          <label htmlFor="title" className="block text-sm font-medium text-gray-700 mb-2">
            Project Title *
          </label>
          <input
            type="text"
            id="title"
            value={projectInfo.title}
            onChange={(e) => setProjectInfo({ ...projectInfo, title: e.target.value })}
            placeholder="Enter your book title..."
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>

        {/* Genre and Audience Row */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label htmlFor="genre" className="block text-sm font-medium text-gray-700 mb-2">
              Genre
            </label>
            <select
              id="genre"
              value={projectInfo.genre}
              onChange={(e) => setProjectInfo({ ...projectInfo, genre: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="Fiction">Fiction</option>
              <option value="Fantasy">Fantasy</option>
              <option value="Science Fiction">Science Fiction</option>
              <option value="Romance">Romance</option>
              <option value="Mystery">Mystery</option>
              <option value="Thriller">Thriller</option>
              <option value="Historical Fiction">Historical Fiction</option>
              <option value="Non-Fiction">Non-Fiction</option>
              <option value="Biography">Biography</option>
              <option value="Other">Other</option>
            </select>
          </div>

          <div>
            <label htmlFor="target_audience" className="block text-sm font-medium text-gray-700 mb-2">
              Target Audience
            </label>
            <select
              id="target_audience"
              value={projectInfo.target_audience}
              onChange={(e) => setProjectInfo({ ...projectInfo, target_audience: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="Adult">Adult</option>
              <option value="Young Adult">Young Adult</option>
              <option value="Middle Grade">Middle Grade</option>
              <option value="Children">Children</option>
            </select>
          </div>
        </div>

        {/* Target Chapters and Writing Style Row */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label htmlFor="target_chapters" className="block text-sm font-medium text-gray-700 mb-2">
              Target Chapters
            </label>
            <input
              type="number"
              id="target_chapters"
              value={projectInfo.target_chapters}
              onChange={(e) => setProjectInfo({ ...projectInfo, target_chapters: parseInt(e.target.value) || 25 })}
              min="1"
              max="100"
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          <div>
            <label htmlFor="writing_style" className="block text-sm font-medium text-gray-700 mb-2">
              Writing Style
            </label>
            <select
              id="writing_style"
              value={projectInfo.writing_style}
              onChange={(e) => setProjectInfo({ ...projectInfo, writing_style: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="Narrative">Narrative</option>
              <option value="Literary">Literary</option>
              <option value="Commercial">Commercial</option>
              <option value="Experimental">Experimental</option>
              <option value="Minimalist">Minimalist</option>
            </select>
          </div>
        </div>
      </div>

      {/* Create Button */}
      <div className="flex justify-end">
        <button
          onClick={handleCreateProject}
          disabled={!projectInfo.title.trim() || isCreating}
          className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
        >
          {isCreating ? (
            <>
              <BookOpenIcon className="w-4 h-4 mr-2 animate-spin inline" />
              Creating Project...
            </>
          ) : (
            <>
              <BookOpenIcon className="w-4 h-4 mr-2 inline" />
              Create Project
            </>
          )}
        </button>
      </div>

      {status && !isCreating && (
        <div className="mt-4 p-3 bg-gray-50 rounded-md">
          <p className="text-sm text-gray-700">{status}</p>
        </div>
      )}

      {/* Creative Loader for Project Creation */}
      <CreativeLoader
        isVisible={isCreating}
        progress={isCreating ? 50 : 0}
        stage={isCreating ? "Creating Project" : undefined}
        customMessages={[
          "🏗️ Building your creative workspace...",
          "📋 Organizing your story structure...",
          "🎨 Preparing your writing canvas...",
          "📚 Setting up your book bible template...",
          "✨ Adding a touch of inspiration...",
          "🔧 Configuring writing tools...",
          "🌟 Aligning creative energies...",
          "📝 Sharpening virtual pencils...",
          "🎭 Preparing character templates...",
          "🗂️ Organizing chapter frameworks..."
        ]}
        showProgress={false}
        size="md"
        timeoutMs={30000} // 30 seconds
      />
    </div>
  )
} 