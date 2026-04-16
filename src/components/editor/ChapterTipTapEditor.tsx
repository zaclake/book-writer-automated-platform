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

export interface SelectionCoords {
  top: number
  left: number
  bottom: number
}

interface ChapterTipTapEditorProps {
  content: string
  onChange: (text: string) => void
  onSelectionChange?: (selection: SelectionInfo | null) => void
  onSelectionCoords?: (coords: SelectionCoords | null) => void
  placeholder?: string
  editable?: boolean
  className?: string
  containerRef?: React.RefObject<HTMLDivElement | null>
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
  onSelectionCoords,
  placeholder = 'Start writing your chapter here... Let your creativity flow.',
  editable = true,
  className,
  containerRef,
}: ChapterTipTapEditorProps) {
  const lastSentRef = useRef(content)
  const suppressNextUpdate = useRef(false)
  const internalContainerRef = useRef<HTMLDivElement>(null)
  const editorContainerRef = containerRef ?? internalContainerRef

  const [hasSelection, setHasSelection] = useState(false)

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
        onSelectionCoords?.(null)
        setHasSelection(false)
        return
      }
      const doc = e.state.doc
      const beforeText = doc.textBetween(0, from, '\n\n')
      const selectedText = doc.textBetween(from, to, '\n\n')
      if (!selectedText.trim()) {
        onSelectionChange(null)
        onSelectionCoords?.(null)
        setHasSelection(false)
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
          onSelectionCoords?.({ top: coords.top, left: coords.left, bottom: coords.bottom })
          setHasSelection(true)
        } else {
          onSelectionCoords?.(null)
        }
      } catch {
        onSelectionCoords?.(null)
        setHasSelection(false)
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

  useEffect(() => {
    if (!hasSelection || !editor || editor.isDestroyed) return
    let rafId = 0
    const repositionCoords = () => {
      cancelAnimationFrame(rafId)
      rafId = requestAnimationFrame(() => {
        if (editor.isDestroyed) return
        const { to, empty } = editor.state.selection
        if (empty) {
          onSelectionCoords?.(null)
          setHasSelection(false)
          return
        }
        try {
          const coords = editor.view.coordsAtPos(to)
          if (coords) {
            onSelectionCoords?.({ top: coords.top, left: coords.left, bottom: coords.bottom })
          } else {
            onSelectionCoords?.(null)
          }
        } catch {
          onSelectionCoords?.(null)
          setHasSelection(false)
        }
      })
    }
    window.addEventListener('scroll', repositionCoords, true)
    window.addEventListener('resize', repositionCoords)
    return () => {
      cancelAnimationFrame(rafId)
      window.removeEventListener('scroll', repositionCoords, true)
      window.removeEventListener('resize', repositionCoords)
    }
  }, [hasSelection, editor, onSelectionCoords])

  if (!editor) return null

  return (
    <div ref={editorContainerRef} className={`relative ${className ?? ''}`}>
      <EditorContent editor={editor} />
    </div>
  )
}
