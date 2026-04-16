'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowPathIcon } from '@heroicons/react/24/outline'
import { InlineDiff, DiffStats } from '@/components/editor/InlineDiff'
import type { SelectionInfo, SelectionCoords } from '@/components/editor/ChapterTipTapEditor'

interface SelectionToolsPopoverProps {
  selectionInfo: SelectionInfo
  selectionMode: 'note' | 'rewrite'
  setSelectionMode: (mode: 'note' | 'rewrite') => void

  selectionNote: string
  setSelectionNote: (note: string) => void
  selectionInstruction: string
  setSelectionInstruction: (instruction: string) => void

  applyToFuture: boolean
  setApplyToFuture: (v: boolean) => void
  noteScope: 'chapter' | 'global'
  setNoteScope: (scope: 'chapter' | 'global') => void

  selectionBusy: boolean
  previewOpen: boolean
  previewOriginal: string
  previewProposed: string
  previewLoading: boolean

  selectionPresets: Array<{ label: string; value: string }>

  saveSelectionNote: () => void
  previewRewriteSelection: () => void
  rewriteSelection: () => void
  resetSelection: () => void
  onAcceptPreview: () => void
  onDiscardPreview: () => void

  anchorCoords: SelectionCoords | null
  editorContainerRef: React.RefObject<HTMLDivElement | null>
}

export default function SelectionToolsPopover({
  selectionInfo,
  selectionMode,
  setSelectionMode,
  selectionNote,
  setSelectionNote,
  selectionInstruction,
  setSelectionInstruction,
  applyToFuture,
  setApplyToFuture,
  noteScope,
  setNoteScope,
  selectionBusy,
  previewOpen,
  previewOriginal,
  previewProposed,
  previewLoading,
  selectionPresets,
  saveSelectionNote,
  previewRewriteSelection,
  rewriteSelection,
  resetSelection,
  onAcceptPreview,
  onDiscardPreview,
  anchorCoords,
  editorContainerRef,
}: SelectionToolsPopoverProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  const [layout, setLayout] = useState<'side' | 'bottom'>('bottom')
  const [position, setPosition] = useState<React.CSSProperties>({ position: 'fixed', opacity: 0 })

  const computePosition = useCallback(() => {
    const editorRect = editorContainerRef.current?.getBoundingClientRect()
    const panelHeight = panelRef.current?.offsetHeight ?? 400
    const panelWidth = 380

    const spaceRight = editorRect
      ? window.innerWidth - editorRect.right
      : 0

    const useSide = window.innerWidth >= 900 && spaceRight > panelWidth + 24

    if (useSide && anchorCoords && editorRect) {
      const minTop = 60
      const maxTop = window.innerHeight - panelHeight - 80
      const clampedTop = Math.max(minTop, Math.min(anchorCoords.top - 20, maxTop))

      setLayout('side')
      setPosition({
        position: 'fixed',
        top: clampedTop,
        left: editorRect.right + 16,
        width: panelWidth,
        maxHeight: 'calc(100vh - 140px)',
        overflowY: 'auto' as const,
        opacity: 1,
      })
    } else {
      setLayout('bottom')
      setPosition({
        position: 'fixed',
        bottom: 80,
        left: 16,
        right: 16,
        maxHeight: '50vh',
        overflowY: 'auto' as const,
        opacity: 1,
      })
    }
  }, [anchorCoords, editorContainerRef])

  useEffect(() => {
    computePosition()
  }, [computePosition])

  useEffect(() => {
    computePosition()
  }, [selectionMode, previewOpen])

  useEffect(() => {
    const handleScrollResize = () => computePosition()
    window.addEventListener('scroll', handleScrollResize, true)
    window.addEventListener('resize', handleScrollResize)
    return () => {
      window.removeEventListener('scroll', handleScrollResize, true)
      window.removeEventListener('resize', handleScrollResize)
    }
  }, [computePosition])

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (selectionBusy) return
      if (!panelRef.current) return
      if (panelRef.current.contains(e.target as Node)) return
      if (editorContainerRef.current?.contains(e.target as Node)) return
      resetSelection()
    }
    const timer = setTimeout(() => {
      document.addEventListener('mousedown', handleClickOutside)
    }, 100)
    return () => {
      clearTimeout(timer)
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [resetSelection, editorContainerRef, selectionBusy])

  const animationClass = layout === 'side'
    ? 'animate-in fade-in slide-in-from-right-4 duration-200'
    : 'animate-in fade-in slide-in-from-bottom-4 duration-200'

  return (
    <div
      ref={panelRef}
      className={`z-50 rounded-2xl border border-brand-lavender/20 bg-white/95 backdrop-blur-sm p-4 shadow-lg ${animationClass}`}
      style={position}
    >
      {/* Header: selected text + clear */}
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div className="min-w-0 flex-1">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-900/50">Selected text</div>
          <div className="text-sm font-semibold text-gray-900 mt-0.5 line-clamp-2">
            {selectionInfo.text.trim().length > 120
              ? `${selectionInfo.text.trim().slice(0, 120)}...`
              : selectionInfo.text.trim()}
          </div>
        </div>
        <button
          onClick={resetSelection}
          className="text-xs font-semibold text-indigo-500 hover:underline shrink-0"
        >
          Clear
        </button>
      </div>

      {/* Mode toggle */}
      <div className="flex gap-1.5 mb-3">
        <button
          onClick={() => setSelectionMode('note')}
          className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition-colors ${
            selectionMode === 'note'
              ? 'bg-brand-soft-purple text-white border-brand-soft-purple'
              : 'bg-white text-gray-900 border-gray-200 hover:bg-gray-50'
          }`}
        >
          Add note
        </button>
        <button
          onClick={() => setSelectionMode('rewrite')}
          className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition-colors ${
            selectionMode === 'rewrite'
              ? 'bg-brand-forest text-white border-brand-forest'
              : 'bg-white text-gray-900 border-gray-200 hover:bg-gray-50'
          }`}
        >
          AI rewrite
        </button>
      </div>

      {/* Note mode */}
      {selectionMode === 'note' ? (
        <div className="space-y-2.5">
          <textarea
            id="selection-note"
            name="selectionNote"
            value={selectionNote}
            onChange={(e) => setSelectionNote(e.target.value)}
            className="w-full min-h-[80px] rounded-lg border border-brand-lavender/20 p-2.5 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-brand-lavender/40 resize-none"
            placeholder="Add a note about this highlight (tone, continuity, change request)."
          />
          <div className="flex flex-wrap items-center gap-2.5 text-xs text-gray-500">
            <label className="flex items-center gap-1.5">
              <input
                id="selection-apply-to-future"
                name="applyToFuture"
                type="checkbox"
                checked={applyToFuture}
                onChange={(e) => setApplyToFuture(e.target.checked)}
                disabled={noteScope === 'global'}
              />
              Future chapters
            </label>
            <label className="flex items-center gap-1.5">
              <span>Scope</span>
              <select
                id="selection-note-scope"
                name="noteScope"
                value={noteScope}
                onChange={(e) => setNoteScope(e.target.value as 'chapter' | 'global')}
                className="rounded-md border border-gray-200 px-1.5 py-0.5 text-xs"
              >
                <option value="chapter">Chapter only</option>
                <option value="global">Global guidance</option>
              </select>
            </label>
          </div>
          <button
            onClick={saveSelectionNote}
            disabled={selectionBusy || !selectionNote.trim()}
            className="w-full bg-brand-soft-purple text-white px-4 py-2 rounded-lg text-sm font-semibold hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            {selectionBusy ? 'Saving...' : 'Save Note'}
          </button>
        </div>
      ) : (
        /* Rewrite mode */
        <div className="space-y-2.5">
          <div className="flex flex-wrap gap-1.5">
            {selectionPresets.map((preset) => (
              <button
                key={preset.label}
                onClick={() => setSelectionInstruction(preset.value)}
                className={`px-2.5 py-1 rounded-full border text-xs font-semibold transition-colors ${
                  selectionInstruction === preset.value
                    ? 'bg-brand-forest text-white border-brand-forest'
                    : 'border-gray-200 text-gray-900 hover:bg-gray-50'
                }`}
              >
                {preset.label}
              </button>
            ))}
          </div>
          <textarea
            id="selection-instruction"
            name="selectionInstruction"
            value={selectionInstruction}
            onChange={(e) => setSelectionInstruction(e.target.value)}
            className="w-full min-h-[80px] rounded-lg border border-brand-lavender/20 p-2.5 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-brand-lavender/40 resize-none"
            placeholder="Tell AI how to rewrite this selection (shorter, punchier, clarify voice, fix continuity)."
          />
          <div className="flex gap-2">
            <button
              onClick={previewRewriteSelection}
              disabled={previewLoading || !selectionInstruction.trim()}
              className="flex-1 border border-brand-forest text-gray-900 px-3 py-2 rounded-lg text-sm font-semibold hover:bg-brand-forest hover:text-white disabled:opacity-50 transition-colors"
            >
              {previewLoading ? (
                <>
                  <ArrowPathIcon className="w-3.5 h-3.5 mr-1 animate-spin inline" />
                  Preview...
                </>
              ) : (
                'Preview'
              )}
            </button>
            <button
              onClick={rewriteSelection}
              disabled={selectionBusy || !selectionInstruction.trim()}
              className="flex-1 bg-brand-forest text-white px-3 py-2 rounded-lg text-sm font-semibold hover:opacity-90 disabled:opacity-50 transition-opacity"
            >
              {selectionBusy ? 'Rewriting...' : 'Apply'}
            </button>
          </div>

          {/* Inline Diff Preview */}
          {previewOpen && (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50/30 p-3 space-y-2.5 animate-in fade-in slide-in-from-bottom-2 duration-200">
              <div className="flex items-center justify-between">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">
                  Diff Preview
                </div>
                <DiffStats original={previewOriginal} proposed={previewProposed} />
              </div>
              <div className="rounded-lg border border-emerald-200 bg-white p-2.5 max-h-48 overflow-y-auto">
                <InlineDiff original={previewOriginal} proposed={previewProposed} />
              </div>
              <div className="flex gap-2">
                <button
                  onClick={onDiscardPreview}
                  className="flex-1 border border-gray-200 text-gray-700 px-3 py-2 rounded-lg text-sm font-semibold hover:bg-gray-50 transition-colors"
                >
                  Discard
                </button>
                <button
                  onClick={onAcceptPreview}
                  disabled={selectionBusy}
                  className="flex-1 bg-emerald-600 text-white px-3 py-2 rounded-lg text-sm font-semibold hover:bg-emerald-700 transition-colors disabled:opacity-50"
                >
                  {selectionBusy ? 'Saving...' : 'Accept'}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
