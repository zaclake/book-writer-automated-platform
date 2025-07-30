'use client'

import React, { useState, useEffect } from 'react'
import { getRandomNudge, UI_STRINGS } from '@/lib/strings'

interface NudgeCardProps {
  onDismiss?: () => void
  className?: string
}

const NudgeCard: React.FC<NudgeCardProps> = ({ onDismiss, className = '' }) => {
  const [nudge, setNudge] = useState<string>('')
  const [isVisible, setIsVisible] = useState(true)

  useEffect(() => {
    // Get a random nudge on mount
    setNudge(getRandomNudge())
  }, [])

  const handleDismiss = () => {
    setIsVisible(false)
    onDismiss?.()
  }

  const handleNewNudge = () => {
    setNudge(getRandomNudge())
  }

  if (!isVisible || !nudge) return null

  return (
    <div className={`bg-gradient-to-r from-brand-soft-purple/10 to-brand-leaf/10 border border-brand-soft-purple/20 rounded-xl p-6 ${className}`}>
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center space-x-2 mb-3">
            <span className="text-2xl">🌱</span>
            <h3 className="text-sm font-semibold text-brand-soft-purple uppercase tracking-wide">
              Daily Inspiration
            </h3>
          </div>
          
          <p className="text-gray-700 leading-relaxed mb-4 italic">
            "{nudge}"
          </p>
          
          <div className="flex items-center space-x-3">
            <button
              onClick={handleNewNudge}
              className="text-sm text-brand-soft-purple hover:text-brand-soft-purple/80 font-medium transition-colors"
            >
              ✨ Another one
            </button>
            <button
              onClick={handleDismiss}
              className="text-sm text-gray-500 hover:text-gray-700 transition-colors"
            >
              Dismiss
            </button>
          </div>
        </div>
        
        <button
          onClick={handleDismiss}
          className="text-gray-400 hover:text-gray-600 transition-colors ml-4"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  )
}

export default NudgeCard 