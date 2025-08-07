'use client'

import { useState } from 'react'
import { useAuthToken } from '@/lib/auth'
import { PlayIcon, StopIcon } from '@heroicons/react/24/outline'
import { CreativeLoader } from './ui/CreativeLoader'

interface ChapterGenerationFormProps {
  onGenerationStart: () => void
  onGenerationComplete: () => void
  isGenerating: boolean
}

export function ChapterGenerationForm({
  onGenerationStart,
  onGenerationComplete,
  isGenerating
}: ChapterGenerationFormProps) {
  const { getAuthHeaders, isLoaded, isSignedIn } = useAuthToken()
  const [chapterNumber, setChapterNumber] = useState(1)
  const [wordCount, setWordCount] = useState(3800)
  const [stage, setStage] = useState('complete')
  const [status, setStatus] = useState('')

  const getProjectId = () => {
    if (typeof window === 'undefined') return null
    return localStorage.getItem('lastProjectId')
  }

  const projectId = getProjectId()
  const hasProject = Boolean(projectId)
  const canInteract = isSignedIn && hasProject && !isGenerating

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (isGenerating) return
    if (!isSignedIn) {
      setStatus('❌ Please sign in to generate chapters')
      return
    }
    const projectId = getProjectId()
    if (!projectId) {
      setStatus('❌ No project selected - upload or select a Book Bible first')
      return
    }
    onGenerationStart()
    setStatus('Generating chapter...')
    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetch('/api/v2/chapters/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders
        },
        body: JSON.stringify({
          project_id: projectId,
          chapter_number: chapterNumber,
          target_word_count: wordCount,
          stage: stage
        })
      })
      const data = await response.json()
      if (response.ok) {
        setStatus(`✅ Chapter ${chapterNumber} generated successfully!`)
        setChapterNumber(prev => prev + 1)
        
        // Trigger credit balance refresh after successful generation
        window.dispatchEvent(new CustomEvent('refreshCreditBalance'))
        
        onGenerationComplete()
      } else {
        setStatus(`❌ Generation failed: ${data.error || JSON.stringify(data)}`)
        onGenerationComplete()
      }
    } catch (error) {
      console.error('Chapter generation error:', error)
      let errorMessage = 'Unknown error occurred'
      if (error instanceof Error) {
        errorMessage = error.message
      }
      setStatus(`❌ Generation Error: ${errorMessage}`)
      onGenerationComplete()
    }
  }

  const handleEstimate = async () => {
    try {
      const authHeaders = await getAuthHeaders()
      const projectId = getProjectId()
      if (!projectId) {
        setStatus('❌ No project selected - upload or select a Book Bible first')
        return
      }
      const response = await fetch('/api/estimate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders
        },
        body: JSON.stringify({
          project_id: projectId,
          chapter_number: chapterNumber,
          words: wordCount,
          stage: stage
        })
      })
      const data = await response.json()
      if (response.ok) {
        setStatus(`💰 Estimated cost: $${data.estimated_total_cost.toFixed(4)} (${data.estimated_total_tokens} tokens)`)
      } else {
        setStatus(`❌ Estimation failed: ${data.error || JSON.stringify(data)}`)
      }
    } catch (error) {
      console.error('Estimation error:', error)
      let errorMessage = 'Unknown error occurred'
      if (error instanceof Error) {
        errorMessage = error.message
      }
      setStatus(`❌ Estimation Error: ${errorMessage}`)
    }
  }

  return (
    <div className="card">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">
        Generate New Chapter
      </h2>
      
      {/* Project Status Indicator */}
      <div className="mb-4 p-3 rounded-md bg-gray-50 border">
        {hasProject ? (
          <div className="flex items-center">
            <div className="w-2 h-2 bg-green-500 rounded-full mr-2"></div>
            <span className="text-sm text-gray-700">
              Project: <span className="font-mono text-xs">{projectId}</span>
            </span>
          </div>
        ) : (
          <div className="flex items-center">
            <div className="w-2 h-2 bg-red-500 rounded-full mr-2"></div>
            <span className="text-sm text-red-700">
              No project selected - please upload a Book Bible first
            </span>
          </div>
        )}
      </div>

      {/* Auth Status Indicator */}
      {!isSignedIn && (
        <div className="mb-4 p-3 rounded-md bg-yellow-50 border border-yellow-200">
          <div className="flex items-center">
            <div className="w-2 h-2 bg-yellow-500 rounded-full mr-2"></div>
            <span className="text-sm text-yellow-700">
              Please sign in to generate chapters
            </span>
          </div>
        </div>
      )}
      
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="chapter" className="block text-sm font-medium text-gray-700">
            Chapter Number
          </label>
          <input
            type="number"
            id="chapter"
            min="1"
            value={chapterNumber}
            onChange={(e) => setChapterNumber(parseInt(e.target.value))}
            disabled={!canInteract}
            className="mt-1 block w-full rounded-md border-gray-300 border px-3 py-2 shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
          />
        </div>
        
        <div>
          <label htmlFor="words" className="block text-sm font-medium text-gray-700">
            Target Word Count
          </label>
          <input
            type="number"
            id="words"
            min="500"
            max="10000"
            step="100"
            value={wordCount}
            onChange={(e) => setWordCount(parseInt(e.target.value))}
            disabled={!canInteract}
            className="mt-1 block w-full rounded-md border-gray-300 border px-3 py-2 shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
          />
        </div>
        
        <div>
          <label htmlFor="stage" className="block text-sm font-medium text-gray-700">
            Generation Stage
          </label>
          <select
            id="stage"
            value={stage}
            onChange={(e) => setStage(e.target.value)}
            disabled={!canInteract}
            className="mt-1 block w-full rounded-md border-gray-300 border px-3 py-2 shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
          >
            <option value="spike">Spike (Quick Test)</option>
            <option value="complete">Complete (Standard)</option>
            <option value="5-stage">5-Stage (Premium)</option>
          </select>
        </div>
        
        <div className="flex space-x-3">
          <button
            type="submit"
            disabled={!canInteract}
            className="flex-1 btn-primary disabled:bg-gray-300 disabled:cursor-not-allowed"
          >
            {isGenerating ? (
              <>
                <StopIcon className="w-4 h-4 mr-2 animate-spin" />
                Generating...
              </>
            ) : (
              <>
                <PlayIcon className="w-4 h-4 mr-2" />
                Generate
              </>
            )}
          </button>
          
          <button
            type="button"
            onClick={handleEstimate}
            disabled={!canInteract}
            className="btn-secondary disabled:bg-gray-300 disabled:cursor-not-allowed"
          >
            Estimate
          </button>
        </div>
      </form>
      
      {/* Creative Loader for Chapter Generation */}
      <CreativeLoader
        isVisible={isGenerating}
        progress={undefined} // No specific progress for single chapter generation
        stage="Crafting Chapter"
        customMessages={[
          "🖋️ Weaving narrative threads...",
          "🎭 Developing character voices...",
          "📖 Building dramatic tension...",
          "✨ Polishing prose perfection...",
          "🎨 Painting vivid scenes...",
          "🔥 Forging compelling dialogue...",
          "🌟 Creating literary magic...",
          "📚 Consulting story wisdom...",
          "🎯 Aiming for the perfect word...",
          "⚡ Channeling creative energy..."
        ]}
        showProgress={false}
        size="md"
        onTimeout={() => {
          // Chapter generation timeout handled in the form submission
        }}
        timeoutMs={120000} // 2 minutes
      />

      {status && !isGenerating && (
        <div className="mt-4 p-3 bg-gray-50 rounded-md">
          <p className="text-sm text-gray-700">{status}</p>
        </div>
      )}
    </div>
  )
} 