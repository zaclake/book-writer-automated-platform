import { useState, useEffect } from 'react'

interface CreativeLoaderProps {
  isVisible: boolean
  progress?: number
  stage?: string
  customMessages?: string[]
  showProgress?: boolean
  size?: 'sm' | 'md' | 'lg'
  onTimeout?: () => void
  timeoutMs?: number
  fullScreen?: boolean
  messageIntervalMs?: number
}

const DEFAULT_MESSAGES = [
  'Preparing your content...',
  'Building structure...',
  'Refining details...',
  'Polishing output...',
  'Almost there...',
]

function formatDuration(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000)
  if (totalSeconds < 60) return `${totalSeconds}s`
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  if (minutes < 60) return `${minutes}m ${String(seconds).padStart(2, '0')}s`
  const hours = Math.floor(minutes / 60)
  const remainMinutes = minutes % 60
  return `${hours}h ${String(remainMinutes).padStart(2, '0')}m`
}

export function CreativeLoader({
  isVisible,
  progress,
  stage,
  customMessages,
  showProgress = true,
  size = 'md',
  onTimeout,
  timeoutMs = 120000,
  fullScreen = false,
  messageIntervalMs = 8000,
}: CreativeLoaderProps) {
  const [currentMessageIndex, setCurrentMessageIndex] = useState(0)
  const [timeElapsed, setTimeElapsed] = useState(0)

  const messages = customMessages || DEFAULT_MESSAGES

  useEffect(() => {
    if (!isVisible) return
    const interval = setInterval(() => {
      setCurrentMessageIndex((prev) => (prev + 1) % messages.length)
    }, messageIntervalMs)
    return () => clearInterval(interval)
  }, [isVisible, messages.length, messageIntervalMs])

  useEffect(() => {
    if (!isVisible) { setTimeElapsed(0); return }
    const interval = setInterval(() => {
      setTimeElapsed((prev) => {
        const next = prev + 1000
        if (next >= timeoutMs && onTimeout) onTimeout()
        return next
      })
    }, 1000)
    return () => clearInterval(interval)
  }, [isVisible, timeoutMs, onTimeout])

  if (!isVisible) return null

  const pct = Math.min(100, Math.max(0, progress ?? 0))
  const hasProgress = showProgress && pct > 0
  const etaMs = pct > 2 && timeElapsed > 3000
    ? Math.round((timeElapsed / pct) * (100 - pct))
    : null

  const sizing = {
    sm: { container: 'p-5', text: 'text-sm', bar: 'h-1.5' },
    md: { container: 'p-6', text: 'text-base', bar: 'h-2' },
    lg: { container: 'p-8', text: 'text-lg', bar: 'h-2.5' },
  }[size]

  const card = (
    <div className={`bg-white rounded-xl border border-gray-100 shadow-xl ${sizing.container} text-center max-w-sm w-full mx-auto`}>
      {/* Spinner */}
      <div className="flex justify-center mb-5">
        <div className="relative w-10 h-10">
          <svg className="w-10 h-10 animate-spin" viewBox="0 0 40 40" fill="none">
            <circle cx="20" cy="20" r="16" stroke="#e5e7eb" strokeWidth="2.5" />
            <path
              d="M20 4a16 16 0 0 1 16 16"
              stroke="url(#cl-grad)"
              strokeWidth="2.5"
              strokeLinecap="round"
            />
            <defs>
              <linearGradient id="cl-grad" x1="20" y1="4" x2="36" y2="20">
                <stop stopColor="#6366f1" />
                <stop offset="1" stopColor="#8b5cf6" />
              </linearGradient>
            </defs>
          </svg>
          {hasProgress && (
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="text-[10px] font-bold text-gray-600">{pct.toFixed(0)}%</span>
            </div>
          )}
        </div>
      </div>

      {/* Stage */}
      {stage && (
        <p className={`${sizing.text} font-medium text-gray-800 mb-1`}>{stage}</p>
      )}

      {/* Rotating message */}
      <p className="text-sm text-gray-500 mb-4 min-h-[1.25em] transition-opacity duration-300">
        {messages[currentMessageIndex]}
      </p>

      {/* Progress bar */}
      {hasProgress && (
        <div className="mb-3">
          <div className={`w-full bg-gray-100 rounded-full overflow-hidden ${sizing.bar}`}>
            <div
              className="h-full bg-gradient-to-r from-indigo-500 to-violet-500 rounded-full transition-all duration-700 ease-out"
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="flex items-center justify-between mt-1.5 text-xs text-gray-400">
            <span>{formatDuration(timeElapsed)}</span>
            {etaMs !== null && etaMs > 1000 && (
              <span>~{formatDuration(etaMs)} left</span>
            )}
          </div>
        </div>
      )}

      {!hasProgress && timeElapsed > 0 && (
        <p className="text-xs text-gray-400">{formatDuration(timeElapsed)}</p>
      )}
    </div>
  )

  if (fullScreen) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-white/80 backdrop-blur-sm p-4">
        {card}
      </div>
    )
  }

  return card
}
