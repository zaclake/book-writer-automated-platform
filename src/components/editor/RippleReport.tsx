'use client'

import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { fetchApi } from '@/lib/api-client'
import { useAuthToken } from '@/lib/auth'
import {
  ExclamationTriangleIcon,
  ExclamationCircleIcon,
  InformationCircleIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  XMarkIcon,
  ChevronRightIcon,
} from '@heroicons/react/24/outline'

interface AffectedChapter {
  chapter_number: number
  chapter_id: string
  severity: 'low' | 'medium' | 'high'
  issues: string[]
  suggested_fix: string
}

interface RippleReportProps {
  affectedChapters: AffectedChapter[]
  sourceChapter: number
  totalChecked: number
  onNavigateToChapter: (chapterNumber: number) => void
  onDismiss: () => void
  onFixComplete?: () => void
}

const severityConfig = {
  high: {
    icon: ExclamationCircleIcon,
    bg: 'bg-red-50',
    border: 'border-red-200',
    text: 'text-red-800',
    badge: 'bg-red-100 text-red-700',
    label: 'High',
  },
  medium: {
    icon: ExclamationTriangleIcon,
    bg: 'bg-amber-50',
    border: 'border-amber-200',
    text: 'text-amber-800',
    badge: 'bg-amber-100 text-amber-700',
    label: 'Medium',
  },
  low: {
    icon: InformationCircleIcon,
    bg: 'bg-blue-50',
    border: 'border-blue-200',
    text: 'text-blue-800',
    badge: 'bg-blue-100 text-blue-700',
    label: 'Low',
  },
}

export function RippleReport({
  affectedChapters,
  sourceChapter,
  totalChecked,
  onNavigateToChapter,
  onDismiss,
  onFixComplete,
}: RippleReportProps) {
  const { getAuthHeaders } = useAuthToken()
  const [fixing, setFixing] = useState(false)
  const [fixedIds, setFixedIds] = useState<Set<string>>(new Set())
  const [fixingId, setFixingId] = useState<string | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const fixChapter = async (chapter: AffectedChapter) => {
    setFixingId(chapter.chapter_id)
    setErrorMsg(null)
    try {
      const authHeaders = await getAuthHeaders()
      const resp = await fetchApi('/api/v2/chapters/propagate-edits', {
        method: 'POST',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chapter_ids: [chapter.chapter_id],
          source_chapter_number: sourceChapter,
          edit_summary: chapter.suggested_fix || `Fix consistency issues from chapter ${sourceChapter} edit`,
        }),
      })
      if (!resp.ok) throw new Error('Server returned an error')
      setFixedIds((prev) => {
        const next = new Set(prev)
        next.add(chapter.chapter_id)
        return next
      })
    } catch (error) {
      console.error('Failed to fix chapter:', error)
      setErrorMsg(`Failed to queue Chapter ${chapter.chapter_number}. Try again.`)
    } finally {
      setFixingId(null)
    }
  }

  const fixAll = async () => {
    setFixing(true)
    setErrorMsg(null)
    const unfixed = affectedChapters.filter((ch) => !fixedIds.has(ch.chapter_id))
    try {
      const authHeaders = await getAuthHeaders()
      const resp = await fetchApi('/api/v2/chapters/propagate-edits', {
        method: 'POST',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chapter_ids: unfixed.map((ch) => ch.chapter_id),
          source_chapter_number: sourceChapter,
          edit_summary: `Align with changes from chapter ${sourceChapter}`,
        }),
      })
      if (!resp.ok) throw new Error('Server returned an error')
      setFixedIds(new Set(affectedChapters.map((ch) => ch.chapter_id)))
      onFixComplete?.()
    } catch (error) {
      console.error('Failed to fix all chapters:', error)
      setErrorMsg('Failed to queue fixes. Please try again.')
    } finally {
      setFixing(false)
    }
  }

  const unfixedCount = affectedChapters.filter((ch) => !fixedIds.has(ch.chapter_id)).length
  const highCount = affectedChapters.filter((ch) => ch.severity === 'high').length
  const mediumCount = affectedChapters.filter((ch) => ch.severity === 'medium').length

  return (
    <div className="rounded-2xl border border-brand-lavender/30 bg-white shadow-xl overflow-hidden">
      {/* Header */}
      <div className="bg-gradient-to-r from-brand-lavender/10 via-white to-brand-blush-orange/10 px-5 py-4 border-b border-brand-lavender/20">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-bold text-brand-forest">
              Ripple Analysis
            </h3>
            <p className="text-xs text-brand-forest/60 mt-0.5">
              {affectedChapters.length} of {totalChecked} downstream chapters may be affected
            </p>
          </div>
          <button
            onClick={onDismiss}
            className="p-1.5 rounded-full hover:bg-gray-100 transition-colors"
          >
            <XMarkIcon className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* Summary badges */}
        <div className="flex items-center gap-2 mt-3">
          {highCount > 0 && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-100 text-red-700 text-xs font-semibold">
              {highCount} high
            </span>
          )}
          {mediumCount > 0 && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 text-xs font-semibold">
              {mediumCount} medium
            </span>
          )}
          {unfixedCount > 0 && (
            <button
              onClick={fixAll}
              disabled={fixing}
              className="ml-auto inline-flex items-center gap-1 px-3 py-1 rounded-full bg-brand-forest text-white text-xs font-semibold hover:opacity-90 disabled:opacity-50 transition-opacity"
            >
              {fixing ? (
                <>
                  <ArrowPathIcon className="w-3.5 h-3.5 animate-spin" />
                  Fixing all...
                </>
              ) : (
                `Fix all (${unfixedCount})`
              )}
            </button>
          )}
        </div>

        {errorMsg && (
          <div className="mt-2 px-3 py-1.5 rounded-lg bg-red-50 border border-red-200 text-xs text-red-700 font-medium">
            {errorMsg}
          </div>
        )}
      </div>

      {/* Chapter list */}
      <div className="max-h-[40vh] overflow-y-auto">
        <AnimatePresence>
          {affectedChapters.map((chapter, idx) => {
            const config = severityConfig[chapter.severity]
            const Icon = config.icon
            const isFixed = fixedIds.has(chapter.chapter_id)
            const isFixing = fixingId === chapter.chapter_id

            return (
              <motion.div
                key={chapter.chapter_id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: idx * 0.05 }}
                className={`px-5 py-3 border-b border-gray-100 last:border-b-0 ${
                  isFixed ? 'bg-emerald-50/50' : ''
                }`}
              >
                <div className="flex items-start gap-3">
                  <div className={`mt-0.5 p-1 rounded-full ${config.bg}`}>
                    {isFixed ? (
                      <CheckCircleIcon className="w-4 h-4 text-emerald-600" />
                    ) : (
                      <Icon className={`w-4 h-4 ${config.text}`} />
                    )}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold text-brand-forest">
                        Chapter {chapter.chapter_number}
                      </span>
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase ${config.badge}`}>
                        {config.label}
                      </span>
                      {isFixed && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase bg-emerald-100 text-emerald-700">
                          Queued
                        </span>
                      )}
                    </div>

                    {chapter.issues.length > 0 && (
                      <ul className="mt-1 space-y-0.5">
                        {chapter.issues.slice(0, 3).map((issue, i) => (
                          <li key={i} className="text-xs text-gray-600 leading-relaxed">
                            {issue}
                          </li>
                        ))}
                        {chapter.issues.length > 3 && (
                          <li className="text-xs text-gray-400">
                            +{chapter.issues.length - 3} more
                          </li>
                        )}
                      </ul>
                    )}
                  </div>

                  <div className="flex items-center gap-1.5 shrink-0">
                    {!isFixed && (
                      <button
                        onClick={() => fixChapter(chapter)}
                        disabled={isFixing}
                        className="px-2.5 py-1 rounded-lg border border-brand-forest text-brand-forest text-xs font-semibold hover:bg-brand-forest hover:text-white disabled:opacity-50 transition-colors"
                      >
                        {isFixing ? (
                          <ArrowPathIcon className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          'Fix'
                        )}
                      </button>
                    )}
                    <button
                      onClick={() => onNavigateToChapter(chapter.chapter_number)}
                      className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors"
                      title="Go to chapter"
                    >
                      <ChevronRightIcon className="w-4 h-4 text-gray-400" />
                    </button>
                  </div>
                </div>
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>

      {affectedChapters.length === 0 && (
        <div className="px-5 py-8 text-center">
          <CheckCircleIcon className="w-10 h-10 mx-auto text-emerald-500 mb-2" />
          <p className="text-sm font-semibold text-brand-forest">All clear!</p>
          <p className="text-xs text-brand-forest/60 mt-1">
            No downstream chapters appear affected by this edit.
          </p>
        </div>
      )}
    </div>
  )
}
