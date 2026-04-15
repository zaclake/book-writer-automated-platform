'use client'

import { useEffect, useMemo, useState } from 'react'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { fetchApi } from '@/lib/api-client'
import { useAuthToken } from '@/lib/auth'
import { toast } from '@/hooks/useAppToast'
import { InlineDiff, DiffStats } from '@/components/editor/InlineDiff'

export type ChapterVersion = {
  version_number: number
  timestamp?: any
  reason?: string
  user_id?: string
  changes_summary?: string
  content?: string
}

function formatDate(ts: any): string {
  if (!ts) return ''
  try {
    if (ts?.toDate) return ts.toDate().toLocaleString()
    if (ts?.seconds) return new Date(ts.seconds * 1000).toLocaleString()
    if (typeof ts === 'string') return new Date(ts).toLocaleString()
  } catch {
    return ''
  }
  return ''
}

const reasonLabels: Record<string, string> = {
  initial_generation: 'Generated',
  quality_revision: 'Quality revision',
  user_edit: 'Manual edit',
  note_rewrite: 'AI rewrite',
  ai_rewrite: 'AI rewrite',
  ai_polish_rewrite: 'Polish',
  ai_full_regenerate: 'Full regenerate',
}

export function ChapterVersionHistoryDialog(props: {
  open: boolean
  onOpenChange: (open: boolean) => void
  chapterId: string
  currentContent: string
  onRestore: (nextContent: string) => Promise<void> | void
}) {
  const { open, onOpenChange, chapterId, currentContent, onRestore } = props
  const { getAuthHeaders } = useAuthToken()

  const [loading, setLoading] = useState(false)
  const [versions, setVersions] = useState<ChapterVersion[]>([])
  const [selected, setSelected] = useState<ChapterVersion | null>(null)
  const [restoring, setRestoring] = useState(false)
  const [viewMode, setViewMode] = useState<'diff' | 'side-by-side'>('diff')

  const selectedContent = selected?.content || ''
  const selectedMeta = useMemo(() => {
    if (!selected) return ''
    const bits = [
      `v${selected.version_number}`,
      selected.reason ? (reasonLabels[selected.reason] || selected.reason) : '',
      formatDate(selected.timestamp) || '',
    ].filter(Boolean)
    return bits.join(' \u00b7 ')
  }, [selected])

  async function loadVersions() {
    setLoading(true)
    try {
      const authHeaders = await getAuthHeaders()
      const resp = await fetchApi(`/api/v2/chapters/${chapterId}/versions`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders,
        },
      })
      if (!resp.ok) {
        throw new Error('Failed to load version history')
      }
      const data = (await resp.json()) as ChapterVersion[]
      const sorted = [...(Array.isArray(data) ? data : [])].sort(
        (a, b) => (b.version_number || 0) - (a.version_number || 0)
      )
      setVersions(sorted)
      setSelected(sorted[0] || null)
    } catch {
      toast({
        title: 'Could not load versions',
        description: 'Please try again.',
        variant: 'destructive',
      })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (open) {
      loadVersions()
    } else {
      setVersions([])
      setSelected(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, chapterId])

  async function handleRestore() {
    if (!selected || !selected.content) return
    if (selected.content === currentContent) {
      toast({ title: 'Already on this version', description: 'No changes to restore.' })
      return
    }
    setRestoring(true)
    try {
      await onRestore(selected.content)
      toast({ title: 'Version Restored', description: `Loaded v${selected.version_number} into editor. Save to keep this version.` })
      onOpenChange(false)
    } catch {
      toast({
        title: 'Restore failed',
        description: 'Please try again.',
        variant: 'destructive',
      })
    } finally {
      setRestoring(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl">
        <DialogHeader>
          <DialogTitle>Version history</DialogTitle>
        </DialogHeader>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {/* Version List */}
          <div className="md:col-span-1">
            <div className="text-sm text-muted-foreground mb-2">
              {loading ? 'Loading...' : `${versions.length} version(s)`}
            </div>
            <ScrollArea className="h-[52vh] rounded-md border">
              <div className="p-2 space-y-2">
                {versions.map(v => {
                  const active = selected?.version_number === v.version_number
                  return (
                    <button
                      key={v.version_number}
                      type="button"
                      onClick={() => setSelected(v)}
                      className={[
                        'w-full rounded-md border px-3 py-2 text-left text-sm transition',
                        active ? 'bg-brand-beige/30 border-brand-lavender/40' : 'bg-background hover:bg-gray-50',
                      ].join(' ')}
                      aria-label={`Select version ${v.version_number}`}
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-medium">v{v.version_number}</span>
                        {v.reason && (
                          <span className="text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded bg-brand-lavender/10 text-brand-forest/70">
                            {reasonLabels[v.reason] || v.reason}
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground mt-0.5">
                        {formatDate(v.timestamp) || 'No date'}
                      </div>
                      {v.changes_summary && (
                        <div className="mt-1 text-xs text-muted-foreground line-clamp-2">
                          {v.changes_summary}
                        </div>
                      )}
                    </button>
                  )
                })}
              </div>
            </ScrollArea>
          </div>

          {/* Content Comparison */}
          <div className="md:col-span-2">
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs text-muted-foreground">{selectedMeta}</div>
              <div className="flex items-center gap-1 bg-gray-100 rounded-full p-0.5">
                <button
                  onClick={() => setViewMode('diff')}
                  className={`px-3 py-1 rounded-full text-xs font-semibold transition-colors ${
                    viewMode === 'diff' ? 'bg-white shadow-sm text-brand-forest' : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  Diff
                </button>
                <button
                  onClick={() => setViewMode('side-by-side')}
                  className={`px-3 py-1 rounded-full text-xs font-semibold transition-colors ${
                    viewMode === 'side-by-side' ? 'bg-white shadow-sm text-brand-forest' : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  Side by side
                </button>
              </div>
            </div>

            {viewMode === 'diff' ? (
              <div>
                {selectedContent && currentContent !== selectedContent && (
                  <div className="mb-2">
                    <DiffStats original={currentContent} proposed={selectedContent} />
                  </div>
                )}
                <ScrollArea className="h-[52vh] rounded-md border">
                  <div className="p-3">
                    {selectedContent ? (
                      currentContent === selectedContent ? (
                        <div className="text-sm text-muted-foreground text-center py-8">
                          This version matches the current content.
                        </div>
                      ) : (
                        <InlineDiff original={currentContent} proposed={selectedContent} />
                      )
                    ) : (
                      <div className="text-sm text-muted-foreground text-center py-8">
                        Select a version to compare.
                      </div>
                    )}
                  </div>
                </ScrollArea>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <div>
                  <div className="text-sm font-medium mb-1">Current</div>
                  <ScrollArea className="h-[52vh] rounded-md border">
                    <pre className="whitespace-pre-wrap p-3 text-xs">{currentContent}</pre>
                  </ScrollArea>
                </div>
                <div>
                  <div className="text-sm font-medium mb-1">Selected</div>
                  <ScrollArea className="h-[52vh] rounded-md border">
                    <pre className="whitespace-pre-wrap p-3 text-xs">{selectedContent}</pre>
                  </ScrollArea>
                </div>
              </div>
            )}
          </div>
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          <Button onClick={handleRestore} disabled={!selected?.content || restoring}>
            {restoring ? 'Restoring...' : 'Restore selected'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
