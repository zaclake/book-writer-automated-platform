'use client'

import { useMemo } from 'react'
import { diffWords } from 'diff'

interface InlineDiffProps {
  original: string
  proposed: string
  className?: string
}

export function InlineDiff({ original, proposed, className }: InlineDiffProps) {
  const changes = useMemo(() => diffWords(original, proposed), [original, proposed])

  if (!original && !proposed) return null

  return (
    <div className={`whitespace-pre-wrap leading-relaxed text-sm ${className ?? ''}`}>
      {changes.map((change, i) => {
        if (change.added) {
          return (
            <span
              key={i}
              className="bg-emerald-100 text-emerald-900 rounded-sm px-px underline decoration-emerald-400 decoration-2"
              aria-label="added text"
            >
              {change.value}
            </span>
          )
        }
        if (change.removed) {
          return (
            <span
              key={i}
              className="bg-red-100 text-red-700 line-through rounded-sm px-px opacity-70"
              aria-label="removed text"
            >
              {change.value}
            </span>
          )
        }
        return <span key={i}>{change.value}</span>
      })}
    </div>
  )
}

interface DiffStatsProps {
  original: string
  proposed: string
}

export function DiffStats({ original, proposed }: DiffStatsProps) {
  const stats = useMemo(() => {
    const changes = diffWords(original, proposed)
    let added = 0
    let removed = 0
    for (const c of changes) {
      if (c.added) added += c.value.split(/\s+/).filter(Boolean).length
      if (c.removed) removed += c.value.split(/\s+/).filter(Boolean).length
    }
    return { added, removed }
  }, [original, proposed])

  return (
    <div className="flex items-center gap-3 text-xs font-semibold">
      {stats.added > 0 && (
        <span className="text-emerald-700" aria-label={`${stats.added} words added`}>+{stats.added} added</span>
      )}
      {stats.removed > 0 && (
        <span className="text-red-600" aria-label={`${stats.removed} words removed`}>-{stats.removed} removed</span>
      )}
    </div>
  )
}
