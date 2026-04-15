'use client'

import React, { useState } from 'react'
import { useUserJobs } from '@/hooks/useFirestore'
import { useAuthToken } from '@/lib/auth'

const ACTIVE_STATUSES = new Set(['pending', 'initializing', 'running', 'generating', 'retrying', 'quality_checking', 'paused'])

function formatJobType(type: string): string {
  if (!type) return 'Job'
  return type
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())
}

function formatEta(progress: number, elapsedMs: number): string | null {
  if (progress <= 2 || progress >= 100 || elapsedMs < 5000) return null
  const remaining = Math.round((elapsedMs / progress) * (100 - progress))
  if (remaining < 2000) return 'Almost done'
  const totalSec = Math.floor(remaining / 1000)
  if (totalSec < 60) return `~${totalSec}s left`
  const min = Math.floor(totalSec / 60)
  if (min < 60) return `~${min}m left`
  const hr = Math.floor(min / 60)
  const rm = min % 60
  return `~${hr}h ${rm}m left`
}

export default function ActiveJobsBanner() {
  const { isLoaded, isSignedIn } = useAuthToken()
  const { jobs, loading } = useUserJobs(5, { enabled: isLoaded && isSignedIn })
  const [collapsed, setCollapsed] = useState(false)

  const active = (jobs || []).filter((j: any) => ACTIVE_STATUSES.has(String(j?.status || '').toLowerCase()))
  if (loading || active.length === 0) return null

  const topJob: any = active[0]
  const pct = topJob?.progress?.percentage ?? topJob?.progress?.progress_percentage ?? 0
  const step = topJob?.progress?.current_step || topJob?.progress?.detailed_status || ''
  const jobType = formatJobType(topJob?.job_type)
  const startedAt = topJob?.started_at || topJob?.created_at
  const elapsedMs = startedAt ? Date.now() - new Date(startedAt).getTime() : 0
  const eta = formatEta(pct, elapsedMs)

  if (collapsed) {
    return (
      <div className="fixed bottom-4 right-4 z-[55]">
        <button
          onClick={() => setCollapsed(false)}
          className="flex items-center gap-2 bg-white/95 backdrop-blur-md border border-gray-200 rounded-full px-3 py-1.5 shadow-lg hover:shadow-xl transition text-xs font-medium text-gray-700"
        >
          <div className="relative w-3.5 h-3.5">
            <svg className="w-3.5 h-3.5 animate-spin text-indigo-500" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity="0.2" />
              <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
            </svg>
          </div>
          <span>{active.length} active</span>
          {pct > 0 && <span className="font-mono">{Math.round(pct)}%</span>}
        </button>
      </div>
    )
  }

  return (
    <div className="fixed bottom-0 left-0 right-0 z-[35]">
      <div className="bg-white/95 backdrop-blur-md border-t border-gray-200 shadow-sm">
        <div className="max-w-5xl mx-auto px-4">
          <div className="flex items-center gap-3 py-2">
            {/* Spinner */}
            <div className="relative w-4 h-4 shrink-0">
              <svg className="w-4 h-4 animate-spin text-indigo-500" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2.5" opacity="0.2" />
                <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
              </svg>
            </div>

            {/* Info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 text-sm">
                <span className="font-medium text-gray-900 truncate">{jobType}</span>
                {step && (
                  <span className="text-gray-400 truncate hidden sm:inline">— {step}</span>
                )}
              </div>
            </div>

            {/* Progress + ETA */}
            <div className="flex items-center gap-3 shrink-0">
              {pct > 0 && (
                <div className="flex items-center gap-2">
                  <div className="w-24 h-1.5 bg-gray-100 rounded-full overflow-hidden hidden sm:block">
                    <div
                      className="h-full bg-indigo-500 rounded-full transition-all duration-700 ease-out"
                      style={{ width: `${Math.min(100, pct)}%` }}
                    />
                  </div>
                  <span className="text-xs font-mono text-gray-600 w-8 text-right">{Math.round(pct)}%</span>
                </div>
              )}
              {eta && <span className="text-xs text-gray-400 hidden md:inline">{eta}</span>}
              {active.length > 1 && (
                <span className="text-xs text-gray-400">+{active.length - 1} more</span>
              )}
              <button
                onClick={() => setCollapsed(true)}
                className="p-1 rounded hover:bg-gray-100 transition text-gray-400 hover:text-gray-600"
                aria-label="Collapse banner"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
