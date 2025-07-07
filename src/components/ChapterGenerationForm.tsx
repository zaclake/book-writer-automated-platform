'use client'

import { useState } from 'react'
import { PlayIcon, StopIcon } from '@heroicons/react/24/outline'

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
  const [chapterNumber, setChapterNumber] = useState(1)
  const [wordCount, setWordCount] = useState(3800)
  const [stage, setStage] = useState('complete')
  const [status, setStatus] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (isGenerating) return
    
    onGenerationStart()
    setStatus('Generating chapter...')
    
    try {
      const response = await fetch('/api/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          chapter: chapterNumber,
          words: wordCount,
          stage: stage
        })
      })
      
      const data = await response.json()
      
      if (response.ok) {
        setStatus(`✅ Chapter ${chapterNumber} generated successfully!`)
        setChapterNumber(prev => prev + 1)
        onGenerationComplete()
      } else {
        setStatus(`❌ Generation failed: ${data.error}`)
        onGenerationComplete()
      }
    } catch (error) {
      setStatus(`❌ Error: ${error instanceof Error ? error.message : 'Unknown error'}`)
      onGenerationComplete()
    }
  }

  const handleEstimate = async () => {
    try {
      const response = await fetch('/api/estimate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          chapter: chapterNumber,
          words: wordCount,
          stage: stage
        })
      })
      
      const data = await response.json()
      
      if (response.ok) {
        setStatus(`💰 Estimated cost: $${data.estimated_total_cost.toFixed(4)} (${data.estimated_total_tokens} tokens)`)
      } else {
        setStatus(`❌ Estimation failed: ${data.error}`)
      }
    } catch (error) {
      setStatus(`❌ Error: ${error instanceof Error ? error.message : 'Unknown error'}`)
    }
  }

  return (
    <div className="card">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">
        Generate New Chapter
      </h2>
      
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
            className="mt-1 block w-full rounded-md border-gray-300 border px-3 py-2 shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
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
            className="mt-1 block w-full rounded-md border-gray-300 border px-3 py-2 shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
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
            className="mt-1 block w-full rounded-md border-gray-300 border px-3 py-2 shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
          >
            <option value="spike">Spike (Quick Test)</option>
            <option value="complete">Complete (Standard)</option>
            <option value="5-stage">5-Stage (Premium)</option>
          </select>
        </div>
        
        <div className="flex space-x-3">
          <button
            type="submit"
            disabled={isGenerating}
            className="flex-1 btn-primary"
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
            disabled={isGenerating}
            className="btn-secondary"
          >
            Estimate
          </button>
        </div>
      </form>
      
      {status && (
        <div className="mt-4 p-3 bg-gray-50 rounded-md">
          <p className="text-sm text-gray-700">{status}</p>
        </div>
      )}
    </div>
  )
} 