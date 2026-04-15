'use client'

import React, { useEffect, useState } from 'react'
import { useGlobalLoaderStore } from '@/stores/useGlobalLoaderStore'

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

function estimateRemaining(elapsed: number, progress: number): string | null {
  if (progress <= 1 || progress >= 100 || elapsed < 3000) return null
  const remaining = Math.round((elapsed / progress) * (100 - progress))
  if (remaining < 1000) return 'Almost done'
  return `~${formatDuration(remaining)} remaining`
}

export function GlobalLoadingOverlay() {
  const {
    isVisible,
    minimized,
    title,
    stage,
    progress,
    showProgress,
    safeToLeave,
    canMinimize,
    customMessages,
    timeoutMs,
    onTimeout,
    startedAt,
    minimize,
    restore,
    forceHide,
  } = useGlobalLoaderStore()

  const [elapsed, setElapsed] = useState(0)
  const [messageIndex, setMessageIndex] = useState(0)

  useEffect(() => {
    if (!isVisible || !startedAt) { setElapsed(0); return }
    setElapsed(Date.now() - startedAt)
    const timer = setInterval(() => setElapsed(Date.now() - startedAt), 1000)
    return () => clearInterval(timer)
  }, [isVisible, startedAt])

  useEffect(() => {
    if (!isVisible || !customMessages?.length) { setMessageIndex(0); return }
    const timer = setInterval(() => {
      setMessageIndex(prev => (prev + 1) % customMessages.length)
    }, 4000)
    return () => clearInterval(timer)
  }, [isVisible, customMessages])

  useEffect(() => {
    if (!isVisible || !timeoutMs || timeoutMs <= 0 || !startedAt) return
    const timer = setTimeout(() => {
      if (onTimeout) onTimeout()
      else forceHide()
    }, timeoutMs)
    return () => clearTimeout(timer)
  }, [isVisible, timeoutMs, startedAt, onTimeout, forceHide])

  useEffect(() => {
    if (!isVisible || minimized) return
    const original = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = original }
  }, [isVisible, minimized])

  if (!isVisible) return null

  const pct = Math.min(100, Math.max(0, progress ?? 0))
  const etaText = estimateRemaining(elapsed, pct)
  const hasProgress = showProgress && pct > 0

  if (minimized) {
    return (
      <div className="fixed bottom-0 left-0 right-0 z-[100]">
        <div className="bg-white/95 backdrop-blur-md border-t border-gray-200 shadow-sm">
          <div className="max-w-4xl mx-auto px-4 py-2 flex items-center gap-3">
            <div className="relative w-5 h-5 shrink-0">
              <svg className="w-5 h-5 animate-spin text-indigo-500" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2.5" opacity="0.2" />
                <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
              </svg>
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-gray-900 truncate">{title || 'Processing'}</span>
                {stage && <span className="text-xs text-gray-500 truncate hidden sm:inline">— {stage}</span>}
              </div>
              {hasProgress && (
                <div className="mt-1 h-1.5 w-full bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-indigo-500 rounded-full transition-all duration-700 ease-out"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              )}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {hasProgress && <span className="text-xs font-mono text-gray-500">{pct.toFixed(0)}%</span>}
              {etaText && <span className="text-xs text-gray-400 hidden sm:inline">{etaText}</span>}
              <button
                onClick={restore}
                className="text-xs text-indigo-600 hover:text-indigo-800 font-medium px-2 py-1 rounded hover:bg-indigo-50 transition"
              >
                Show
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-white/80 backdrop-blur-sm" />

      <div className="relative w-full max-w-md">
        <div className="bg-white rounded-2xl shadow-2xl border border-gray-100 overflow-hidden">
          {/* Progress stripe at top */}
          {hasProgress && (
            <div className="h-1 w-full bg-gray-100">
              <div
                className="h-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all duration-700 ease-out"
                style={{ width: `${pct}%` }}
              />
            </div>
          )}

          <div className="p-8 text-center">
            {/* Spinner */}
            <div className="flex justify-center mb-6">
              <div className="relative w-12 h-12">
                <svg className="w-12 h-12 animate-spin" viewBox="0 0 48 48" fill="none">
                  <circle cx="24" cy="24" r="20" stroke="#e5e7eb" strokeWidth="3" />
                  <path
                    d="M24 4a20 20 0 0 1 20 20"
                    stroke="url(#loader-gradient)"
                    strokeWidth="3"
                    strokeLinecap="round"
                  />
                  <defs>
                    <linearGradient id="loader-gradient" x1="24" y1="4" x2="44" y2="24">
                      <stop stopColor="#6366f1" />
                      <stop offset="1" stopColor="#8b5cf6" />
                    </linearGradient>
                  </defs>
                </svg>
                {hasProgress && (
                  <div className="absolute inset-0 flex items-center justify-center">
                    <span className="text-xs font-semibold text-gray-700">{pct.toFixed(0)}%</span>
                  </div>
                )}
              </div>
            </div>

            {/* Title */}
            <h3 className="text-lg font-semibold text-gray-900 mb-1">
              {title || 'Processing'}
            </h3>

            {/* Stage */}
            {stage && (
              <p className="text-sm text-gray-500 mb-2">{stage}</p>
            )}

            {/* Rotating custom messages */}
            {customMessages && customMessages.length > 0 && (
              <p key={messageIndex} className="text-xs text-gray-400 mb-4 transition-opacity duration-300">
                {customMessages[messageIndex]}
              </p>
            )}
            {!customMessages?.length && stage && <div className="mb-2" />}

            {/* Progress bar */}
            {hasProgress && (
              <div className="mb-4">
                <div className="h-2 w-full bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-indigo-500 to-violet-500 rounded-full transition-all duration-700 ease-out"
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <div className="flex items-center justify-between mt-2 text-xs text-gray-400">
                  <span>{formatDuration(elapsed)} elapsed</span>
                  {etaText && <span>{etaText}</span>}
                </div>
              </div>
            )}

            {/* Elapsed time (when no progress) */}
            {!hasProgress && elapsed > 0 && (
              <p className="text-xs text-gray-400 mb-4">{formatDuration(elapsed)} elapsed</p>
            )}

            {/* Safe to leave message */}
            {safeToLeave && (
              <div className="flex items-center justify-center gap-2 px-4 py-2.5 bg-emerald-50 border border-emerald-200 rounded-lg mb-4">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#059669" strokeWidth="2" strokeLinecap="round">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" />
                </svg>
                <span className="text-sm text-emerald-800 font-medium">
                  Safe to leave — progress is saved automatically
                </span>
              </div>
            )}

            {/* Actions */}
            {canMinimize && (
              <button
                onClick={minimize}
                className="text-sm text-gray-500 hover:text-gray-700 font-medium px-4 py-2 rounded-lg hover:bg-gray-50 transition"
              >
                Minimize to banner
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default GlobalLoadingOverlay
