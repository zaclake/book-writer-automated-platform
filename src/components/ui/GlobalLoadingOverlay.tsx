'use client'

import React, { useEffect } from 'react'
import { useGlobalLoaderStore } from '@/stores/useGlobalLoaderStore'
import { CreativeLoader } from './CreativeLoader'

export function GlobalLoadingOverlay() {
  const {
    isVisible,
    title,
    stage,
    message,
    progress,
    showProgress,
    size,
    fullScreen,
    customMessages,
    timeoutMs,
    onTimeout,
  } = useGlobalLoaderStore()

  // Prevent scroll when visible
  useEffect(() => {
    if (!isVisible) return
    const original = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = original
    }
  }, [isVisible])

  if (!isVisible) return null

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center">
      {/* Elegant background */}
      <div className="absolute inset-0 bg-gradient-to-br from-white/80 via-white/70 to-white/80 backdrop-blur-sm" />
      <div className="absolute -top-20 -left-20 w-64 h-64 bg-gradient-to-br from-brand-lavender to-brand-leaf opacity-10 rounded-full blur-3xl" />
      <div className="absolute -bottom-24 -right-24 w-72 h-72 bg-gradient-to-tr from-brand-blush-orange to-brand-ink-blue opacity-10 rounded-full blur-3xl" />

      <div className="relative w-full max-w-xl px-6">
        {title && (
          <h3 className="text-xl font-semibold text-center mb-2 text-gray-800">{title}</h3>
        )}
        {message && (
          <p className="text-center text-gray-600 mb-4">{message}</p>
        )}
        <CreativeLoader
          isVisible
          progress={progress}
          stage={stage}
          customMessages={customMessages}
          showProgress={showProgress}
          size={size}
          onTimeout={onTimeout || undefined}
          timeoutMs={timeoutMs}
          fullScreen={fullScreen}
        />
      </div>
    </div>
  )
}

export default GlobalLoadingOverlay


