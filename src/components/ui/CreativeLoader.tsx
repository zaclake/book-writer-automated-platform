import { useState, useEffect } from 'react'
import { ArrowPathIcon } from '@heroicons/react/24/outline'

interface CreativeLoaderProps {
  isVisible: boolean
  progress?: number // 0-100
  stage?: string
  customMessages?: string[]
  showProgress?: boolean
  size?: 'sm' | 'md' | 'lg'
  onTimeout?: () => void
  timeoutMs?: number
}

const DEFAULT_MESSAGES = [
  "🖋️ Sharpening pencils...",
  "☕ Brewing the perfect coffee...",
  "📚 Consulting the writing gods...", 
  "🎭 Giving characters personality...",
  "🗺️ Drawing treasure maps...",
  "🔮 Gazing into plot crystals...",
  "📖 Whispering to the muses...",
  "✨ Sprinkling literary magic...",
  "🎪 Teaching words to dance...",
  "🌟 Aligning story constellations...",
  "🎨 Mixing emotional paint...",
  "🎼 Composing dramatic symphonies...",
  "🏰 Building narrative castles...",
  "🦋 Catching inspiration butterflies...",
  "🌱 Growing story seeds...",
  "🔥 Forging plot twists...",
  "🎯 Aiming for the perfect word...",
  "🧪 Mixing character chemistry...",
  "⚡ Charging creative batteries...",
  "🌊 Surfing waves of imagination..."
]

export function CreativeLoader({
  isVisible,
  progress,
  stage,
  customMessages,
  showProgress = true,
  size = 'md',
  onTimeout,
  timeoutMs = 120000 // 2 minutes default
}: CreativeLoaderProps) {
  console.log('🎭 CreativeLoader render called with:', { isVisible, progress, stage, size })
  
  const [currentMessageIndex, setCurrentMessageIndex] = useState(0)
  const [timeElapsed, setTimeElapsed] = useState(0)

  const messages = customMessages || DEFAULT_MESSAGES

  // Rotate messages every 3 seconds
  useEffect(() => {
    if (!isVisible) return

    const interval = setInterval(() => {
      setCurrentMessageIndex((prev) => (prev + 1) % messages.length)
    }, 3000)

    return () => clearInterval(interval)
  }, [isVisible, messages.length])

  // Track elapsed time and handle timeout
  useEffect(() => {
    if (!isVisible) {
      setTimeElapsed(0)
      return
    }

    const interval = setInterval(() => {
      setTimeElapsed((prev) => {
        const newTime = prev + 1000
        if (newTime >= timeoutMs && onTimeout) {
          onTimeout()
        }
        return newTime
      })
    }, 1000)

    return () => clearInterval(interval)
  }, [isVisible, timeoutMs, onTimeout])

  if (!isVisible) {
    console.log('🎭 CreativeLoader: Not visible, returning null')
    return null
  }

  const sizeClasses = {
    sm: {
      container: 'p-6',
      spinner: 'w-6 h-6',
      text: 'text-base',
      progress: 'h-2'
    },
    md: {
      container: 'p-8',
      spinner: 'w-8 h-8',
      text: 'text-lg',
      progress: 'h-3'
    },
    lg: {
      container: 'p-12',
      spinner: 'w-12 h-12',
      text: 'text-xl',
      progress: 'h-4'
    }
  }

  const classes = sizeClasses[size]
  const progressPercentage = progress ?? 0
  const timeMinutes = Math.floor(timeElapsed / 60000)
  const timeSeconds = Math.floor((timeElapsed % 60000) / 1000)

  return (
    <div className={`bg-white rounded-xl border-2 border-blue-200 ${classes.container} text-center`}>
      {/* Spinner */}
      <div className="flex justify-center mb-6">
        <ArrowPathIcon className={`${classes.spinner} text-blue-600 animate-spin`} />
      </div>

      {/* Current Message */}
      <div className={`${classes.text} font-medium text-gray-800 mb-4 min-h-[1.5em] transition-all duration-500`}>
        {messages[currentMessageIndex]}
      </div>

      {/* Stage Information */}
      {stage && (
        <div className="text-sm text-gray-600 mb-4">
          {stage}
        </div>
      )}

      {/* Progress Bar */}
      {showProgress && progressPercentage > 0 && (
        <div className="mb-4">
          <div className={`w-full bg-gray-200 rounded-full ${classes.progress} overflow-hidden`}>
            <div 
              className="bg-gradient-to-r from-blue-500 to-green-500 h-full transition-all duration-1000 ease-out"
              style={{ width: `${Math.min(100, Math.max(0, progressPercentage))}%` }}
            />
          </div>
          <div className="text-sm text-gray-600 mt-2">
            {progressPercentage.toFixed(0)}% complete
          </div>
        </div>
      )}

      {/* Time Elapsed */}
      <div className="text-xs text-gray-500">
        {timeMinutes > 0 ? `${timeMinutes}m ${timeSeconds}s` : `${timeSeconds}s`}
        {timeMinutes > 1 && (
          <div className="mt-1 text-gray-400">
            Complex stories take time to craft perfectly...
          </div>
        )}
      </div>

      {/* Encouragement for longer waits */}
      {timeElapsed > 45000 && (
        <div className="mt-4 p-3 bg-blue-50 rounded-lg border border-blue-200">
          <div className="text-sm text-blue-800">
            🎭 Creating something truly spectacular...
          </div>
          <div className="text-xs text-blue-600 mt-1">
            Great art takes time. We're crafting every detail with care.
          </div>
        </div>
      )}
    </div>
  )
} 