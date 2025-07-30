'use client'

import { useState, useEffect } from 'react'
import { SparklesIcon, PencilSquareIcon } from '@heroicons/react/24/outline'

interface DashboardHeroProps {
  userName?: string
  projectCount: number
}

const inspirationalQuotes = [
  "Great writers aren't born, they're grown. Keep writing.",
  "Every word you write is a step toward your story.",
  "Your voice matters. The world needs your story.",
  "Writing is thinking on paper. Let your thoughts flow.",
  "Books are dreams that you hold in your hand."
]

export default function DashboardHero({ userName, projectCount }: DashboardHeroProps) {
  const [currentQuote, setCurrentQuote] = useState(0)
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    setIsVisible(true)
    const interval = setInterval(() => {
      setCurrentQuote(prev => (prev + 1) % inspirationalQuotes.length)
    }, 8000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="relative overflow-hidden">
      {/* Gradient Background */}
      <div className="absolute inset-0 bg-gradient-to-br from-brand-lavender/10 via-brand-beige to-brand-off-white" />
      
      {/* Decorative Elements */}
      <div className="absolute top-0 right-0 w-64 h-64 bg-gradient-to-bl from-brand-lavender/5 to-transparent rounded-full blur-3xl animate-float" />
      <div className="absolute bottom-0 left-0 w-48 h-48 bg-gradient-to-tr from-brand-orange/5 to-transparent rounded-full blur-2xl animate-float" style={{ animationDelay: '2s' }} />
      
      <div className={`relative px-6 py-12 md:py-16 lg:py-20 transition-all duration-600 ${isVisible ? 'animate-fade-in-up' : 'opacity-0'}`}>
        <div className="max-w-4xl mx-auto text-center">
          {/* Main Heading */}
          <div className="flex items-center justify-center mb-4">
            <SparklesIcon className="h-8 w-8 text-brand-lavender mr-3 animate-pulse" />
            <h1 className="text-display-lg md:text-display-lg bg-gradient-to-r from-brand-forest to-brand-lavender bg-clip-text text-transparent">
              Welcome back{userName ? `, ${userName}` : ''}
            </h1>
            <PencilSquareIcon className="h-8 w-8 text-brand-orange ml-3 animate-float" />
          </div>
          
          {/* Subheading */}
          <p className="text-xl md:text-2xl text-brand-forest/80 font-medium mb-6 leading-relaxed">
            Your creative sanctuary awaits
          </p>
          
          {/* Progress Indicator */}
          <div className="inline-flex items-center bg-white/40 backdrop-blur-sm rounded-full px-6 py-3 border border-brand-lavender/20 mb-8">
            <div className="flex items-center space-x-2">
              <div className="w-2 h-2 bg-brand-lavender rounded-full animate-pulse" />
              <span className="text-brand-forest font-semibold">
                {projectCount} {projectCount === 1 ? 'journey' : 'journeys'} in progress
              </span>
            </div>
          </div>
          
          {/* Inspirational Quote */}
          <div className="relative">
            <div 
              className="text-lg text-brand-forest/70 italic font-medium transition-all duration-500 bg-gradient-to-r from-transparent via-brand-lavender/10 to-transparent bg-size-200 animate-shimmer"
              style={{
                backgroundImage: 'linear-gradient(90deg, transparent, rgba(177, 142, 255, 0.1), transparent)',
                backgroundSize: '200px 100%',
              }}
            >
              "{inspirationalQuotes[currentQuote]}"
            </div>
          </div>
        </div>
      </div>
    </div>
  )
} 