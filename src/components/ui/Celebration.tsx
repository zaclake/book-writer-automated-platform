'use client'

import React from 'react'

interface CelebrationProps {
  isVisible: boolean
  message?: string
}

export default function Celebration({ isVisible, message }: CelebrationProps) {
  if (!isVisible) return null
  return (
    <div className="fixed inset-0 z-[60] pointer-events-none">
      {/* Soft backdrop */}
      <div className="absolute inset-0 bg-gradient-to-br from-black/20 via-black/10 to-transparent" />

      {/* Center checkmark */}
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="relative">
          <div className="w-24 h-24 rounded-full bg-white/90 shadow-2xl border-2 border-white flex items-center justify-center overflow-hidden">
            <svg className="w-14 h-14 text-brand-forest animate-[pop_280ms_ease-out]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M20 6L9 17l-5-5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            {/* shimmer */}
            <div className="absolute -left-16 -top-16 w-24 h-24 rotate-45 bg-gradient-to-r from-transparent via-white/50 to-transparent animate-[sweep_1.2s_ease-in-out]" />
          </div>
          {message && (
            <div className="mt-3 text-center text-white font-semibold drop-shadow">{message}</div>
          )}
        </div>
      </div>

      {/* lightweight confetti particles */}
      {[...Array(16)].map((_, i) => (
        <span
          key={i}
          className="absolute w-1.5 h-1.5 rounded-full"
          style={{
            left: `${6 + (i * 6)}%`,
            top: '55%',
            background: i % 3 === 0 ? '#a78bfa' : i % 3 === 1 ? '#f97316' : '#34d399',
            opacity: 0.95,
            animation: `rise ${700 + (i % 5) * 120}ms ease-out ${i * 20}ms forwards`
          }}
        />
      ))}

      <style jsx global>{`
        @keyframes pop {
          0% { transform: scale(0.6); opacity: 0 }
          100% { transform: scale(1); opacity: 1 }
        }
        @keyframes sweep {
          0% { transform: translateX(-120%) translateY(120%); opacity: 0 }
          50% { opacity: .9 }
          100% { transform: translateX(160%) translateY(-160%); opacity: 0 }
        }
        @keyframes rise {
          0% { transform: translateY(0) scale(0.9); opacity: .95 }
          100% { transform: translateY(-120px) scale(1.05); opacity: 0 }
        }
      `}</style>
    </div>
  )
}


