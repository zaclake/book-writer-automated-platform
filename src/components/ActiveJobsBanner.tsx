'use client'

import React from 'react'
import { useUserJobs } from '@/hooks/useFirestore'

export default function ActiveJobsBanner() {
  const { jobs, loading } = useUserJobs(5)

  const active = (jobs || []).filter((j: any) => ['pending', 'running'].includes(j.status))
  if (loading || active.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-[60]">
      <div className="bg-white/95 backdrop-blur-md rounded-xl shadow-2xl border border-white/60 min-w-[280px]">
        <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
          <div className="text-sm font-semibold text-gray-800">Background activity</div>
          <div className="text-xs text-gray-500">{active.length} running</div>
        </div>
        <div className="p-3 space-y-3">
          {active.map((job: any) => {
            const pct = job.progress?.percentage ?? job.progress?.progress_percentage ?? 0
            const step = job.progress?.current_step || job.progress?.detailed_status || 'Working...'
            return (
              <div key={job.job_id || job.id} className="space-y-1">
                <div className="flex items-center justify-between text-xs text-gray-600">
                  <span className="font-medium">{job.job_type?.replace(/_/g,' ') || 'Job'}</span>
                  <span className="font-semibold">{Math.round(pct)}%</span>
                </div>
                <div className="h-2 w-full bg-white border border-gray-200 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-brand-lavender via-brand-leaf to-brand-blush-orange transition-all duration-700"
                    style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
                  />
                </div>
                <div className="text-[11px] text-gray-500 truncate">{step}</div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}


