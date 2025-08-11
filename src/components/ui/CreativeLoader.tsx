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
  fullScreen?: boolean
  messageIntervalMs?: number // NEW: how often to rotate messages
}

// A rich pool of rotating messages including whimsical loaders, fun facts, and famous-author insights.
// Keep messages short (<120 chars) so they fit nicely on small screens.
const DEFAULT_MESSAGES = [
  // — Whimsical activity messages —
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
  "🌊 Surfing waves of imagination...",

  // — Fun facts & trivia about writing —
  "📖 Fun fact: Agatha Christie wrote more than 2 billion books—third only to Shakespeare & the Bible.",
  "⌨️ George R.R. Martin still writes on a 1980s DOS machine using WordStar 4.0.",
  "📝 Stephen King threw the first pages of *Carrie* away; his wife rescued them.",
  "🏃 Haruki Murakami runs a marathon every year to keep his writing discipline sharp.",
  "📚 J.K. Rowling’s original *Harry Potter* pitch was rejected by 12 publishers.",
  "✉️ Marcel Proust wrote some sentences that ran longer than 400 words.",
  "🕰️ Victor Hugo wrote *Les Misérables* over 12 years—and in exile.",
  "✂️ Hemingway revised the ending of *A Farewell to Arms* 39 times.",
  "📏 Nabokov plotted *Lolita* on index cards he could shuffle at will.",
  "🐈 Edgar Allan Poe had a beloved cat named Catterina who sat on his shoulder while he wrote.",
  "📅 Maya Angelou drafted nearly every book in a tiny hotel room—then rewrote by hand.",
  "✍️ Douglas Adams famously said: ‘I love deadlines. I like the whooshing sound they make as they fly by.’",
  "🔍 Sir Arthur Conan Doyle based Sherlock Holmes on his medical school professor, Dr. Joseph Bell.",
  "🚂 Agatha Christie once disappeared for 11 days; the mystery has never been solved.",
  "🗺️ Tolkien created Middle-earth languages before writing the stories.",
  "🛑 Mark Twain popularised the saying ‘Kill your darlings’ (cut beloved lines for clarity).",
  "🦉 Kafka wrote *The Metamorphosis* in three weeks but edited it for months.",
  "💡 Isaac Asimov published in every category of the Dewey Decimal System except Philosophy.",
  "📜 The longest novel ever written is *In Search of Lost Time* (~1.2 million words).",
  "🎖️ Kurt Vonnegut tried (and failed) to sell the film rights to *Slaughterhouse-Five* for $100 early on.",
  "🪶 Shakespeare invented over 1,700 words still used today, including ‘bedazzled’.",

  // — Motivational quotes —
  "🖋️ ‘You can, you should, and if you’re brave enough to start, you will.’ – Stephen King",
  "📚 ‘The first draft is just you telling yourself the story.’ – Terry Pratchett",
  "✨ ‘A word after a word after a word is power.’ – Margaret Atwood",
  "🔧 ‘Easy reading is damn hard writing.’ – Nathaniel Hawthorne",
  "🎨 ‘Creativity is intelligence having fun.’ – Albert Einstein"
] as const

export function CreativeLoader({
  isVisible,
  progress,
  stage,
  customMessages,
  showProgress = true,
  size = 'md',
  onTimeout,
  timeoutMs = 120000, // 2 minutes default
  fullScreen = false,
  messageIntervalMs = 10000 // Default: change message every 10 seconds
}: CreativeLoaderProps) {
  console.log('🎭 CreativeLoader render called with:', { isVisible, progress, stage, size })
  
  const [currentMessageIndex, setCurrentMessageIndex] = useState(0)
  const [timeElapsed, setTimeElapsed] = useState(0)

  const messages = customMessages || DEFAULT_MESSAGES

  // Rotate messages at the configured interval (default 10s)
  useEffect(() => {
    if (!isVisible) return

    const interval = setInterval(() => {
      setCurrentMessageIndex((prev) => (prev + 1) % messages.length)
    }, messageIntervalMs)

    return () => clearInterval(interval)
  }, [isVisible, messages.length, messageIntervalMs])

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
  const estimatedRemainingMs = progressPercentage > 1
    ? Math.max(0, Math.round((timeElapsed * (100 - progressPercentage)) / progressPercentage))
    : undefined
  const etaMinutes = estimatedRemainingMs ? Math.floor(estimatedRemainingMs / 60000) : undefined
  const etaSeconds = estimatedRemainingMs ? Math.floor((estimatedRemainingMs % 60000) / 1000) : undefined

  const LoaderCard = (
    <div className={`relative bg-white/95 rounded-2xl border border-white/60 ${classes.container} text-center shadow-2xl backdrop-blur-md`}>
      {/* Decorative brand orbs */}
      <div className="pointer-events-none absolute -top-10 -right-10 w-28 h-28 bg-gradient-to-br from-brand-lavender to-brand-leaf opacity-20 rounded-full blur-2xl" />
      <div className="pointer-events-none absolute -bottom-12 -left-12 w-32 h-32 bg-gradient-to-tr from-brand-blush-orange to-brand-ink-blue opacity-10 rounded-full blur-2xl" />

      {/* Spinner */}
      <div className="flex justify-center mb-6 relative">
        <ArrowPathIcon className={`${classes.spinner} text-blue-600 animate-spin`} />
        <div className="absolute inset-0 rounded-full animate-ping opacity-10 bg-gradient-to-br from-brand-lavender to-brand-leaf" />
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
          <div className={`w-full bg-white rounded-full border border-gray-200 ${classes.progress} overflow-hidden`}>
            <div 
              className="bg-gradient-to-r from-brand-lavender via-brand-leaf to-brand-blush-orange h-full transition-all duration-700 ease-out shadow-sm"
              style={{ width: `${Math.min(100, Math.max(0, progressPercentage))}%` }}
            />
          </div>
          <div className="text-sm text-gray-600 mt-2 flex items-center justify-center gap-3">
            {estimatedRemainingMs !== undefined && (
              <span className="text-gray-500">ETA {etaMinutes}m {String(etaSeconds).padStart(2,'0')}s</span>
            )}
            <span className="font-semibold">{progressPercentage.toFixed(0)}% complete</span>
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

  if (fullScreen) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-white/80 backdrop-blur-sm">
        {LoaderCard}
      </div>
    )
  }

  return LoaderCard
} 