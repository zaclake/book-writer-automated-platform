'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'

export interface SelectionInfo {
  text: string
  from: number
  to: number
}

interface ChapterTipTapEditorProps {
  content: string
  onChange: (text: string) => void
  onSelectionChange?: (selection: SelectionInfo | null) => void
  placeholder?: string
  editable?: boolean
  className?: string
  onNoteMode?: () => void
  onRewriteMode?: () => void
  onClearSelection?: () => void
  selectionMode?: 'note' | 'rewrite'
}

function textToHtml(text: string): string {
  if (!text) return '<p></p>'
  return text
    .split('\n\n')
    .map((para) => {
      const escaped = para
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
      const withBreaks = escaped.replace(/\n/g, '<br/>')
      return `<p>${withBreaks}</p>`
    })
    .join('')
}

function editorToText(editor: ReturnType<typeof useEditor>): string {
  if (!editor) return ''
  const doc = editor.state.doc
  const blocks: string[] = []
  doc.forEach((node) => {
    let text = ''
    node.forEach((child) => {
      if (child.isText) {
        text += child.text ?? ''
      } else if (child.type.name === 'hardBreak') {
        text += '\n'
      }
    })
    blocks.push(text)
  })
  return blocks.join('\n\n')
}

export default function ChapterTipTapEditor({
  content,
  onChange,
  onSelectionChange,
  placeholder = 'Start writing your chapter here... Let your creativity flow.',
  editable = true,
  className,
  onNoteMode,
  onRewriteMode,
  onClearSelection,
  selectionMode,
}: ChapterTipTapEditorProps) {
  const lastSentRef = useRef(content)
  const suppressNextUpdate = useRef(false)
  const editorContainerRef = useRef<HTMLDivElement>(null)
  const bubbleRef = useRef<HTMLDivElement>(null)

  const [bubbleStyle, setBubbleStyle] = useState<{
    top: number
    left: number
    visible: boolean
  }>({ top: 0, left: 0, visible: false })

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        bold: false,
        italic: false,
        strike: false,
        code: false,
        codeBlock: false,
        blockquote: false,
        bulletList: false,
        orderedList: false,
        listItem: false,
        heading: false,
        horizontalRule: false,
      }),
      Placeholder.configure({ placeholder }),
    ],
    content: textToHtml(content),
    editable,
    editorProps: {
      attributes: {
        class: [
          'chapter-editor-content',
          'prose prose-lg max-w-none',
          'focus:outline-none',
          'min-h-[60vh]',
          'text-brand-forest',
          'leading-relaxed',
        ].join(' '),
      },
    },
    onUpdate({ editor: e }) {
      if (suppressNextUpdate.current) {
        suppressNextUpdate.current = false
        return
      }
      const text = editorToText(e)
      lastSentRef.current = text
      onChange(text)
    },
    onSelectionUpdate({ editor: e }) {
      const { from, to, empty } = e.state.selection
      if (empty || !onSelectionChange) {
        onSelectionChange?.(null)
        setBubbleStyle((prev) => ({ ...prev, visible: false }))
        return
      }
      const doc = e.state.doc
      const beforeText = doc.textBetween(0, from, '\n\n')
      const selectedText = doc.textBetween(from, to, '\n\n')
      if (!selectedText.trim()) {
        onSelectionChange(null)
        setBubbleStyle((prev) => ({ ...prev, visible: false }))
        return
      }
      onSelectionChange({
        text: selectedText,
        from: beforeText.length,
        to: beforeText.length + selectedText.length,
      })

      try {
        const coords = e.view.coordsAtPos(to)
        if (coords) {
          const bubbleWidth = bubbleRef.current?.offsetWidth ?? 180
          let left = coords.left - bubbleWidth / 2
          left = Math.max(8, Math.min(left, window.innerWidth - bubbleWidth - 8))
          let top = coords.top - 50
          if (top < 8) top = coords.top + 24
          setBubbleStyle({ top, left, visible: true })
        }
      } catch {
        setBubbleStyle((prev) => ({ ...prev, visible: false }))
      }
    },
  })

  useEffect(() => {
    if (!editor || editor.isDestroyed) return
    const currentText = editorToText(editor)
    if (content === currentText || content === lastSentRef.current) return
    suppressNextUpdate.current = true
    const { from } = editor.state.selection
    editor.commands.setContent(textToHtml(content))
    const maxPos = editor.state.doc.content.size
    const safePos = Math.min(from, maxPos)
    try {
      editor.commands.setTextSelection(safePos)
    } catch {
      // position may be invalid after content change
    }
    lastSentRef.current = content
  }, [content, editor])

  useEffect(() => {
    if (!editor || editor.isDestroyed) return
    editor.setEditable(editable)
  }, [editable, editor])

  // Reposition bubble on scroll so it stays anchored to the selected text
  useEffect(() => {
    if (!bubbleStyle.visible || !editor || editor.isDestroyed) return
    let rafId = 0
    const repositionBubble = () => {
      cancelAnimationFrame(rafId)
      rafId = requestAnimationFrame(() => {
        if (editor.isDestroyed) return
        const { to, empty } = editor.state.selection
        if (empty) {
          setBubbleStyle((prev) => ({ ...prev, visible: false }))
          return
        }
        try {
          const coords = editor.view.coordsAtPos(to)
          if (coords) {
            const bw = bubbleRef.current?.offsetWidth ?? 180
            let left = coords.left - bw / 2
            left = Math.max(8, Math.min(left, window.innerWidth - bw - 8))
            let top = coords.top - 50
            if (top < 8) top = coords.top + 24
            setBubbleStyle({ top, left, visible: true })
          }
        } catch {
          setBubbleStyle((prev) => ({ ...prev, visible: false }))
        }
      })
    }
    window.addEventListener('scroll', repositionBubble, true)
    window.addEventListener('resize', repositionBubble)
    return () => {
      cancelAnimationFrame(rafId)
      window.removeEventListener('scroll', repositionBubble, true)
      window.removeEventListener('resize', repositionBubble)
    }
  }, [bubbleStyle.visible, editor])

  const handleClear = useCallback(() => {
    if (editor && !editor.isDestroyed) {
      editor.commands.setTextSelection(editor.state.selection.from)
    }
    onClearSelection?.()
  }, [editor, onClearSelection])

  if (!editor) return null

  return (
    <div ref={editorContainerRef} className={`relative ${className ?? ''}`}>
      {/* Floating Selection Toolbar */}
      {bubbleStyle.visible && (
        <div
          ref={bubbleRef}
          className="fixed z-50 flex items-center gap-1.5 rounded-full border border-brand-lavender/30 bg-white/95 px-3 py-2 text-xs font-semibold text-brand-forest shadow-lg backdrop-blur-sm animate-in fade-in duration-150"
          style={{ top: bubbleStyle.top, left: bubbleStyle.left }}
        >
          <button
            type="button"
            onClick={onNoteMode}
            className={`rounded-full px-3 py-1 border transition-colors ${
              selectionMode === 'note'
                ? 'bg-brand-soft-purple text-white border-brand-soft-purple'
                : 'bg-white text-brand-forest border-gray-200 hover:bg-gray-50'
            }`}
          >
            Note
          </button>
          <button
            type="button"
            onClick={onRewriteMode}
            className={`rounded-full px-3 py-1 border transition-colors ${
              selectionMode === 'rewrite'
                ? 'bg-brand-forest text-white border-brand-forest'
                : 'bg-white text-brand-forest border-gray-200 hover:bg-gray-50'
            }`}
          >
            Rewrite
          </button>
          <button
            type="button"
            onClick={handleClear}
            className="rounded-full px-3 py-1 border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors"
          >
            Clear
          </button>
        </div>
      )}

      <EditorContent editor={editor} />
    </div>
  )
}
