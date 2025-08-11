'use client'

import React, { useState } from 'react'

type Visibility = 'private' | 'shared' | 'public'

interface Props {
  projectId: string
  current: Visibility
  onUpdated?: (next: Visibility) => void
}

export default function LibraryVisibilityToggle({ projectId, current, onUpdated }: Props) {
  const [value, setValue] = useState<Visibility>(current)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const update = async (next: Visibility) => {
    if (loading || next === value) return
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/api/v2/projects/${encodeURIComponent(projectId)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ visibility: next })
      })
      if (!res.ok) throw new Error(await res.text())
      setValue(next)
      onUpdated?.(next)
    } catch (e: any) {
      setError(e?.message || 'Update failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-gray-600">Visibility:</span>
      {(['private','public'] as Visibility[]).map(opt => (
        <button
          key={opt}
          disabled={loading}
          className={`px-2 py-1 rounded border ${value===opt ? 'bg-gray-900 text-white border-gray-900' : 'border-gray-300 hover:bg-gray-50'}`}
          onClick={() => update(opt)}
        >{opt}</button>
      ))}
      {error && <span className="text-red-600 ml-2">{error}</span>}
    </div>
  )
}


