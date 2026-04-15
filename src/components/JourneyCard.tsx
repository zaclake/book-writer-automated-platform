'use client'

import React from 'react'
import { useRouter } from 'next/navigation'
import { TrashIcon } from '@heroicons/react/24/outline'

interface Project {
  id: string
  title: string
  genre?: string
  status: 'active' | 'completed' | 'archived' | 'paused'
  created_at: string
  progress?: {
    chapters_completed?: number
    current_word_count?: number
    completion_percentage?: number
  }
  settings?: {
    target_chapters?: number
    word_count_per_chapter?: number
  }
  metadata?: {
    title?: string
    genre?: string
    status?: string
  }
}

interface JourneyCardProps {
  project: Project
  onDelete?: (projectId: string) => void
}

const STATUS_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  active: { bg: 'bg-emerald-50', text: 'text-emerald-700', label: 'In Progress' },
  completed: { bg: 'bg-indigo-50', text: 'text-indigo-700', label: 'Complete' },
  paused: { bg: 'bg-amber-50', text: 'text-amber-700', label: 'Paused' },
  archived: { bg: 'bg-gray-100', text: 'text-gray-500', label: 'Archived' },
}

function getSpineColor(title: string): string {
  const colors = [
    'from-indigo-400 to-indigo-600',
    'from-violet-400 to-violet-600',
    'from-emerald-400 to-emerald-600',
    'from-amber-400 to-amber-600',
    'from-rose-400 to-rose-600',
    'from-sky-400 to-sky-600',
    'from-teal-400 to-teal-600',
  ]
  let hash = 0
  for (let i = 0; i < title.length; i++) {
    hash = ((hash << 5) - hash) + title.charCodeAt(i)
    hash |= 0
  }
  return colors[Math.abs(hash) % colors.length]
}

function formatWords(count: number): string {
  if (count === 0) return '0'
  if (count >= 1000) return `${Math.round(count / 1000)}k`
  return count.toLocaleString()
}

function formatDate(dateString: string): string | null {
  try {
    const date = new Date(dateString)
    if (isNaN(date.getTime())) return null
    const now = new Date()
    const diffDays = Math.ceil(Math.abs(now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24))
    if (diffDays <= 1) return 'Today'
    if (diffDays < 7) return `${diffDays} days ago`
    if (diffDays < 30) return `${Math.ceil(diffDays / 7)}w ago`
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  } catch {
    return null
  }
}

const JourneyCard: React.FC<JourneyCardProps> = ({ project, onDelete }) => {
  const router = useRouter()

  const title = project.metadata?.title || project.title || 'Untitled'
  const genre = project.metadata?.genre || project.genre
  const resolvedStatus = project.status || (project.metadata?.status as any) || 'active'
  const status = STATUS_STYLES[resolvedStatus] || STATUS_STYLES.active
  const chaptersWritten = project.progress?.chapters_completed || 0
  const targetChapters = project.settings?.target_chapters || 25
  const totalWords = project.progress?.current_word_count || 0
  const progressPct = Math.min(100, Math.round((chaptersWritten / targetChapters) * 100))
  const spineColor = getSpineColor(title)
  const created = formatDate(project.created_at || (project.metadata as any)?.created_at)

  return (
    <div className="group relative">
      <div className="bg-white rounded-xl border border-gray-200 hover:border-gray-300 hover:shadow-lg transition-all duration-200 overflow-hidden">
        {/* Delete button */}
        {onDelete && (
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(project.id) }}
            className="absolute top-3 right-3 z-10 p-1.5 rounded-lg bg-white/90 border border-gray-200 text-gray-400 hover:text-red-500 hover:border-red-200 sm:opacity-0 sm:group-hover:opacity-100 sm:focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-red-500 transition"
            aria-label={`Delete ${title}`}
          >
            <TrashIcon className="w-3.5 h-3.5" />
          </button>
        )}

        {/* Card body */}
        <div className="p-5">
          <div className="flex items-start gap-3.5 mb-4">
            {/* Book spine */}
            <div className={`shrink-0 w-10 h-14 bg-gradient-to-b ${spineColor} rounded-md shadow-md`}>
              <div className="w-full h-full bg-gradient-to-r from-white/20 to-transparent rounded-md" />
            </div>

            {/* Title + meta */}
            <div className="flex-1 min-w-0 pr-6">
              <h3 className="text-base font-semibold text-gray-900 leading-snug line-clamp-2 mb-1">
                {title}
              </h3>
              <div className="flex items-center gap-2 flex-wrap">
                {genre && (
                  <span className="text-xs text-gray-500">{genre}</span>
                )}
                <span className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${status.bg} ${status.text}`}>
                  {status.label}
                </span>
              </div>
              {created && (
                <p className="text-[11px] text-gray-400 mt-1">Started {created}</p>
              )}
            </div>
          </div>

          {/* Progress */}
          <div className="mb-4">
            <div className="flex items-center justify-between text-xs text-gray-500 mb-1.5">
              <span>{chaptersWritten} of {targetChapters} chapters</span>
              <span className="font-medium text-gray-700">{progressPct}%</span>
            </div>
            <div className="h-1.5 w-full bg-gray-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-indigo-500 rounded-full transition-all duration-500 ease-out"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>

          {/* Stats */}
          <div className="flex items-center gap-4 text-xs text-gray-500 mb-4">
            <div>
              <span className="font-semibold text-gray-900 text-sm">{chaptersWritten}</span>
              <span className="ml-1">{chaptersWritten === 1 ? 'chapter' : 'chapters'}</span>
            </div>
            <div>
              <span className="font-semibold text-gray-900 text-sm">{formatWords(totalWords)}</span>
              <span className="ml-1">words</span>
            </div>
          </div>

          {/* CTA */}
          <button
            onClick={() => router.push(`/project/${project.id}/overview`)}
            className="w-full py-2.5 px-4 bg-gray-900 text-white rounded-lg text-sm font-medium hover:bg-gray-800 focus-visible:ring-2 focus-visible:ring-gray-900 focus-visible:ring-offset-2 transition"
          >
            {progressPct === 0 ? 'Get started' : progressPct >= 100 ? 'View project' : 'Continue writing'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default JourneyCard
