'use client'

import { useState, useEffect, useRef, useMemo } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useAuthToken } from '@/lib/auth'
import { fetchApi } from '@/lib/api-client'
import { PencilIcon, SparklesIcon } from '@heroicons/react/24/outline'
import ProjectLayout from '@/components/layout/ProjectLayout'
import { GlobalLoader } from '@/stores/useGlobalLoaderStore'

interface ReferenceFile {
  name: string
  content: string
  lastModified?: string
  approved?: boolean
}

interface ReferenceTab {
  id: string
  label: string
  filename?: string
  description: string
  source: 'reference' | 'book-bible'
}

const REFERENCE_TABS: ReferenceTab[] = [
  {
    id: 'book-bible',
    label: 'Book Bible',
    description: 'Core story foundation, vision, and guiding details',
    source: 'book-bible'
  },
  {
    id: 'characters',
    label: 'Characters',
    filename: 'characters.md',
    description: 'Character profiles, entity registry, relationships, and development arcs',
    source: 'reference'
  },
  {
    id: 'outline',
    label: 'Plot Outline',
    filename: 'outline.md',
    description: 'Story structure, scene-level chapter breakdown, and subplot threading',
    source: 'reference'
  },
  {
    id: 'world-building',
    label: 'World Building',
    filename: 'world-building.md',
    description: 'Setting details, world rules, sensory palettes, and daily life',
    source: 'reference'
  },
  {
    id: 'style-guide',
    label: 'Style & Tone',
    filename: 'style-guide.md',
    description: 'Writing style, voice, and narrative preferences',
    source: 'reference'
  },
  {
    id: 'plot-timeline',
    label: 'Plot Timeline',
    filename: 'plot-timeline.md',
    description: 'Chronological timeline, key events, and continuity rules',
    source: 'reference'
  },
  {
    id: 'themes-and-motifs',
    label: 'Themes & Motifs',
    filename: 'themes-and-motifs.md',
    description: 'Central themes, recurring motifs, symbols, and implementation guidelines',
    source: 'reference'
  },
  {
    id: 'entity-registry',
    label: 'Entity Registry',
    filename: 'entity-registry.md',
    description: 'Canonical names, proper nouns, locations, factions, and world terms',
    source: 'reference'
  },
  {
    id: 'relationship-map',
    label: 'Relationships',
    filename: 'relationship-map.md',
    description: 'Character relationships, information states, and secret tracking',
    source: 'reference'
  },
  {
    id: 'director-guide',
    label: 'Director Guide',
    filename: 'director-guide.md',
    description: 'First-draft guidance, onramp strategy, and scene payloads',
    source: 'reference'
  },
  {
    id: 'research-notes',
    label: 'Research Notes',
    filename: 'research-notes.md',
    description: 'Research requirements, accuracy standards, and fact-checking',
    source: 'reference'
  },
  {
    id: 'target-audience-profile',
    label: 'Target Audience',
    filename: 'target-audience-profile.md',
    description: 'Audience demographics, motivations, and engagement strategies',
    source: 'reference'
  },
  {
    id: 'canon-log',
    label: 'Canon Log',
    filename: 'canon-log.md',
    description: 'Auto-updated canon decisions and continuity ledger',
    source: 'reference'
  }
]

interface ReferenceKeyValue {
  label: string
  value: string
}

interface CanonLogEntry {
  id: string
  source_type?: string
  source_label?: string
  instructions?: string
  mode?: string
  scope?: string
  status?: string
  created_at?: string
  applied_targets?: string[]
}

interface RewriteCandidate {
  chapter_id: string
  chapter_number?: number
  title?: string
}

interface ParsedSection {
  id: string
  title: string
  paragraphs: string[]
  bullets: string[]
  keyValues: ReferenceKeyValue[]
}

const stripMarkdownDecorations = (text: string) =>
  text
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/__(.*?)__/g, '$1')
    .replace(/`+/g, '')
    .replace(/[_>*]/g, '')
    .trim()

const stripListPrefix = (line: string) =>
  line.replace(/^[-*+]\s+/, '').replace(/^\d+\.\s+/, '').trim()

const parseReferenceContent = (content: string): ParsedSection[] => {
  const lines = content.split(/\r?\n/)
  const sections: ParsedSection[] = []
  let current: ParsedSection | null = null
  let sectionIndex = 0

  const startSection = (title: string) => {
    const newSection: ParsedSection = {
      id: `section-${sectionIndex++}`,
      title: title || 'Overview',
      paragraphs: [],
      bullets: [],
      keyValues: []
    }
    sections.push(newSection)
    current = newSection
  }

  const ensureSection = () => {
    if (!current) {
      startSection('Overview')
    }
  }

  for (let idx = 0; idx < lines.length; idx++) {
    const rawLine = lines[idx]
    const trimmed = rawLine.trim()
    if (!trimmed) {
      continue
    }

    if (/^#{1,6}\s+/.test(trimmed)) {
      const title = stripMarkdownDecorations(trimmed.replace(/^#{1,6}\s+/, ''))
      startSection(title)
      continue
    }

    const previousLine = idx > 0 ? lines[idx - 1].trim() : ''
    const nextLine = idx < lines.length - 1 ? lines[idx + 1].trim() : ''
    const looksLikeTitle =
      trimmed.length <= 60 &&
      !trimmed.includes(':') &&
      !/^[-*+]\s+/.test(trimmed) &&
      !/^\d+\.\s+/.test(trimmed) &&
      (previousLine === '' || nextLine === '')
    if (looksLikeTitle) {
      startSection(stripMarkdownDecorations(trimmed))
      continue
    }

    ensureSection()
    const cleanedLine = stripMarkdownDecorations(stripListPrefix(trimmed))
    if (!cleanedLine) {
      continue
    }

    const kvMatch = cleanedLine.match(/^([^:]{2,40}):\s*(.+)$/)
    if (kvMatch) {
      current?.keyValues.push({
        label: kvMatch[1].trim(),
        value: kvMatch[2].trim()
      })
      continue
    }

    if (/^[-*+]\s+/.test(trimmed) || /^\d+\.\s+/.test(trimmed)) {
      current?.bullets.push(cleanedLine)
      continue
    }

    current?.paragraphs.push(cleanedLine)
  }

  return sections
}

const sectionToEditableText = (section: ParsedSection) => {
  const lines: string[] = []
  section.keyValues.forEach(item => {
    lines.push(`${item.label}: ${item.value}`)
  })
  section.bullets.forEach(item => {
    lines.push(`- ${item}`)
  })
  section.paragraphs.forEach(item => {
    lines.push(item)
  })
  return lines.join('\n')
}

const parseSectionText = (text: string): ParsedSection => {
  const lines = text.split(/\r?\n/)
  const section: ParsedSection = {
    id: 'section-temp',
    title: '',
    paragraphs: [],
    bullets: [],
    keyValues: []
  }

  for (const rawLine of lines) {
    const trimmed = rawLine.trim()
    if (!trimmed) continue
    if (/^[-*+]\s+/.test(trimmed) || /^\d+\.\s+/.test(trimmed)) {
      section.bullets.push(stripListPrefix(trimmed))
      continue
    }
    const cleanedLine = stripMarkdownDecorations(trimmed)
    const kvMatch = cleanedLine.match(/^([^:]{2,40}):\s*(.+)$/)
    if (kvMatch) {
      section.keyValues.push({ label: kvMatch[1].trim(), value: kvMatch[2].trim() })
    } else {
      section.paragraphs.push(cleanedLine)
    }
  }
  return section
}

const buildDocumentFromSections = (sections: ParsedSection[]) => {
  return sections
    .map(section => {
      const lines: string[] = []
      const title = section.title || 'Overview'
      lines.push(`## ${title}`)
      section.keyValues.forEach(item => lines.push(`${item.label}: ${item.value}`))
      section.bullets.forEach(item => lines.push(`- ${item}`))
      section.paragraphs.forEach(item => lines.push(item))
      return lines.join('\n')
    })
    .join('\n\n')
    .trim()
}

const getEditableSectionsFromContent = (content: string) => {
  const parsed = parseReferenceContent(content)
  if (parsed.length > 0) {
    return parsed.map(section => ({ ...section, text: sectionToEditableText(section) }))
  }
  const fallback = content.trim()
  return [
    {
      id: 'section-0',
      title: 'Overview',
      paragraphs: fallback ? [fallback] : [],
      bullets: [],
      keyValues: [],
      text: fallback
    }
  ]
}

export default function ReferenceReviewPage() {
  const params = useParams()
  const router = useRouter()
  const rawProjectId = params.projectId as string
  const { getAuthHeaders, isSignedIn } = useAuthToken()
  
  // Check for retry parameter in URL
  const [shouldShowRetry, setShouldShowRetry] = useState(false)
  
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const urlParams = new URLSearchParams(window.location.search)
      setShouldShowRetry(urlParams.get('retry') === 'true')
    }
  }, [])

  // Decode the project ID from URL and handle project name vs actual ID
  const decodedProjectName = decodeURIComponent(rawProjectId)
  const [actualProjectId, setActualProjectId] = useState<string | null>(null)
  const [projectTitle, setProjectTitle] = useState<string>(decodedProjectName)

  // Find the actual project ID based on the project name from URL
  useEffect(() => {
    const findProjectId = async () => {
      try {
        const authHeaders = await getAuthHeaders()
        const response = await fetchApi('/api/v2/projects', {
          method: 'GET',
          headers: authHeaders
        })
        
        if (response.ok) {
          const data = await response.json()
          const projects = data.projects || []
          
          // Try to find project by ID first (in case it's a real UUID)
          let project = projects.find((p: any) => p.project_id === rawProjectId || p.id === rawProjectId)
          
          // If not found by ID, try to find by title
          if (!project) {
            project = projects.find((p: any) => 
              p.title === decodedProjectName || 
              p.metadata?.title === decodedProjectName
            )
          }
          
          if (project) {
            const realProjectId = project.project_id || project.id
            setActualProjectId(realProjectId)
            setProjectTitle(project.title || project.metadata?.title || decodedProjectName)
          } else {
                setActualProjectId(rawProjectId)
          }
        }
      } catch (error) {
          setActualProjectId(rawProjectId)
      }
    }

    if (isSignedIn && rawProjectId) {
      findProjectId()
    }
  }, [isSignedIn, rawProjectId, decodedProjectName, getAuthHeaders])

  // Use the actual project ID for API calls
  const projectId = actualProjectId || rawProjectId

  const [activeTab, setActiveTab] = useState(REFERENCE_TABS[0].id)
  const [files, setFiles] = useState<Record<string, ReferenceFile>>({})
  const [loading, setLoading] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editableSections, setEditableSections] = useState<Array<ParsedSection & { text: string }>>([])
  const [aiEditOpen, setAiEditOpen] = useState(false)
  const [aiEditPrompt, setAiEditPrompt] = useState('')
  const [aiEditHistory, setAiEditHistory] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([])
  const [aiEditLoading, setAiEditLoading] = useState(false)
  const [sectionEditOpen, setSectionEditOpen] = useState(false)
  const [sectionEditMode, setSectionEditMode] = useState<'manual' | 'ai'>('manual')
  const [sectionEditId, setSectionEditId] = useState<string | null>(null)
  const [sectionEditTitle, setSectionEditTitle] = useState('')
  const [sectionEditText, setSectionEditText] = useState('')
  const [sectionEditPrompt, setSectionEditPrompt] = useState('')
  const [sectionEditHistory, setSectionEditHistory] = useState<
    Array<{ role: 'user' | 'assistant'; content: string }>
  >([])
  const [sectionEditLoading, setSectionEditLoading] = useState(false)
  const [status, setStatus] = useState('')
  const [hasLoaded, setHasLoaded] = useState(false)
  const [canonLogs, setCanonLogs] = useState<CanonLogEntry[]>([])
  const [canonLogLoading, setCanonLogLoading] = useState(false)
  const [rewriteDialogOpen, setRewriteDialogOpen] = useState(false)
  const [rewriteCandidates, setRewriteCandidates] = useState<RewriteCandidate[]>([])
  const [rewriteSelected, setRewriteSelected] = useState<Record<string, boolean>>({})
  const [rewriteLoading, setRewriteLoading] = useState(false)
  const [rewriteSubmitting, setRewriteSubmitting] = useState(false)
  const [rewriteSourceEntry, setRewriteSourceEntry] = useState<CanonLogEntry | null>(null)

  // Reset hasLoaded when projectId changes
  useEffect(() => {
    setHasLoaded(false)
  }, [projectId])

  useEffect(() => {
    if (isSignedIn && projectId && !hasLoaded) {
      loadReferenceFiles()
      loadCanonLogs()
    }
  }, [isSignedIn, projectId, hasLoaded])

  useEffect(() => {
    if (!hasLoaded) return
    const lastRefreshRef = { time: Date.now() }
    const COOLDOWN = 15000

    const handleVisibility = () => {
      if (document.visibilityState === 'visible' && Date.now() - lastRefreshRef.time > COOLDOWN) {
        lastRefreshRef.time = Date.now()
        loadReferenceFiles()
        loadCanonLogs()
      }
    }

    document.addEventListener('visibilitychange', handleVisibility)
    return () => document.removeEventListener('visibilitychange', handleVisibility)
  }, [hasLoaded, projectId])

  // Clean up polling interval on unmount
  useEffect(() => {
    return () => {
      if (progressIntervalRef.current) {
        clearInterval(progressIntervalRef.current)
        progressIntervalRef.current = null
      }
    }
  }, [])

  const loadReferenceFiles = async () => {
    setLoading(true)
    const filesData: Record<string, ReferenceFile> = {}

    const normalizeFilename = (name: string) => (name.endsWith('.md') ? name : `${name}.md`)
    const referenceTabs = REFERENCE_TABS.filter(
      (tab): tab is ReferenceTab & { filename: string } => tab.source === 'reference' && !!tab.filename
    )
    const bookBibleTab = REFERENCE_TABS.find(tab => tab.source === 'book-bible')

    try {
      const authHeaders = await getAuthHeaders()

      const listResponse = await fetchApi(`/api/v2/projects/${projectId}/references`, {
        headers: authHeaders
      })

      if (!listResponse.ok) {
        console.error(`[loadReferenceFiles] Failed to list references: ${listResponse.status} ${listResponse.statusText}`)
        setStatus('❌ Failed to load reference files')
      } else {
        const listData = await listResponse.json()
        const availableFiles = new Set<string>()
        const listFiles = Array.isArray(listData?.files) ? listData.files : []

        for (const file of listFiles) {
          const rawName = file?.filename || file?.name || file?.file_name
          if (typeof rawName === 'string' && rawName.trim()) {
            availableFiles.add(normalizeFilename(rawName.trim()))
          }
        }

        if (availableFiles.size > 0) {
          const fetches = referenceTabs
            .map((tab) => {
              const normalizedFilename = normalizeFilename(tab.filename)
              if (!availableFiles.has(normalizedFilename)) return null
              const requestUrl = `/api/v2/projects/${projectId}/references/${normalizedFilename}`
              return (async () => {
                try {
                  const response = await fetchApi(requestUrl, { headers: authHeaders })
                  if (!response.ok) {
                    console.error(`[loadReferenceFiles] Error loading ${normalizedFilename}: ${response.status} ${response.statusText}`)
                    return null
                  }
                  const fileData = await response.json()
                  return {
                    tabId: tab.id,
                    file: {
                      name: fileData.name || fileData.filename || normalizedFilename,
                      content: fileData.content || '',
                      lastModified: fileData.lastModified || fileData.last_modified,
                      approved: false
                    } as ReferenceFile
                  }
                } catch (error) {
                  console.error(`Failed to load ${normalizedFilename}:`, error)
                  return null
                }
              })()
            })
            .filter(Boolean) as Array<Promise<{ tabId: string; file: ReferenceFile } | null>>

          const results = await Promise.all(fetches)
          for (const result of results) {
            if (result) filesData[result.tabId] = result.file
          }
        }
      }

      if (bookBibleTab) {
        try {
          const response = await fetch(`/api/book-bible/${projectId}`, {
            headers: authHeaders
          })

          if (response.ok) {
            const data = await response.json()
            const bookBibleContent =
              data?.book_bible?.content ??
              data?.book_bible_content ??
              data?.book_bible?.text ??
              ''
            const bookBibleLastModified =
              data?.book_bible?.last_modified ||
              data?.book_bible?.lastModified ||
              data?.book_bible?.updated_at ||
              null

            filesData[bookBibleTab.id] = {
              name: 'book-bible',
              content: bookBibleContent,
              lastModified: bookBibleLastModified || new Date().toISOString(),
              approved: false
            }
          } else {
            console.error(`[loadReferenceFiles] Error loading book bible: ${response.status} ${response.statusText}`)
          }
        } catch (error) {
          console.error('Failed to load book bible:', error)
        }
      }

      setFiles(filesData)
      setHasLoaded(true)
    } catch (error) {
      console.error('Error loading reference files:', error)
      setStatus('❌ Failed to load reference files')
    } finally {
      setLoading(false)
    }
  }

  const loadCanonLogs = async () => {
    if (!projectId) return
    setCanonLogLoading(true)
    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetchApi(`/api/v2/projects/${projectId}/canon-log?limit=12`, {
        headers: authHeaders
      })
      if (response.ok) {
        const data = await response.json()
        setCanonLogs(Array.isArray(data?.entries) ? data.entries : [])
      }
    } catch (error) {
      console.error('Failed to load canon logs:', error)
    } finally {
      setCanonLogLoading(false)
    }
  }

  const openRewriteDialog = async (entry: CanonLogEntry) => {
    if (!projectId) return
    setRewriteSourceEntry(entry)
    setRewriteDialogOpen(true)
    setRewriteLoading(true)
    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetchApi(`/api/v2/projects/${projectId}/steering/rewrite-candidates`, {
        method: 'POST',
        headers: {
          ...authHeaders,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ canon_log_id: entry.id })
      })
      if (response.ok) {
        const data = await response.json()
        const candidates: RewriteCandidate[] = Array.isArray(data?.candidates) ? data.candidates : []
        setRewriteCandidates(candidates)
        const selections: Record<string, boolean> = {}
        candidates.forEach(item => {
          selections[item.chapter_id] = true
        })
        setRewriteSelected(selections)
      } else {
        setRewriteCandidates([])
      }
    } catch (error) {
      console.error('Failed to load rewrite candidates:', error)
      setRewriteCandidates([])
    } finally {
      setRewriteLoading(false)
    }
  }

  const submitRewriteRequest = async () => {
    if (!projectId || !rewriteSourceEntry) return
    const selectedIds = rewriteCandidates
      .filter(item => rewriteSelected[item.chapter_id])
      .map(item => item.chapter_id)
    if (!selectedIds.length) {
      setStatus('❌ Select at least one chapter to rewrite')
      return
    }
    setRewriteSubmitting(true)
    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetchApi(`/api/v2/projects/${projectId}/steering/rewrite-chapters`, {
        method: 'POST',
        headers: {
          ...authHeaders,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          canon_log_id: rewriteSourceEntry.id,
          chapter_ids: selectedIds
        })
      })
      if (response.ok) {
        setStatus('✅ Chapter rewrites queued')
        setRewriteDialogOpen(false)
        loadCanonLogs()
      } else {
        const errorData = await response.json().catch(() => ({}))
        setStatus(`❌ Failed to queue rewrites: ${errorData.detail || 'Unknown error'}`)
      }
    } catch (error) {
      console.error('Failed to queue rewrites:', error)
      setStatus('❌ Failed to queue rewrites')
    } finally {
      setRewriteSubmitting(false)
    }
  }

  const handleEdit = () => {
    const currentFile = files[activeTab]
    if (currentFile) {
      setEditableSections(getEditableSectionsFromContent(currentFile.content))
      setIsEditing(true)
    }
  }

  const saveReferenceContent = async (content: string) => {
    if (!files[activeTab]) return

    try {
      const authHeaders = await getAuthHeaders()
      const tabData = REFERENCE_TABS.find(t => t.id === activeTab)
      if (!tabData) return false

      if (tabData.source === 'book-bible') {
        const response = await fetch(`/api/book-bible/${projectId}`, {
          method: 'PUT',
          headers: {
            ...authHeaders,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ book_bible_content: content })
        })

        if (response.ok) {
          setFiles(prev => ({
            ...prev,
            [activeTab]: {
              ...prev[activeTab],
              content,
              lastModified: new Date().toISOString()
            }
          }))
          setStatus('✅ Book bible saved successfully')
          loadCanonLogs()
          return true
        }

        setStatus('❌ Failed to save book bible')
        return false
      }

      const filename = tabData.filename
      if (!filename) return false

      const response = await fetchApi(`/api/v2/projects/${projectId}/references/${filename}`, {
        method: 'PUT',
        headers: {
          ...authHeaders,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ content })
      })

      if (response.ok) {
        const data = await response.json()
        setFiles(prev => ({
          ...prev,
          [activeTab]: {
            ...prev[activeTab],
            content,
            lastModified: data.lastModified || prev[activeTab].lastModified
          }
        }))
        setStatus('✅ File saved successfully')
        loadCanonLogs()
        return true
      }

      setStatus('❌ Failed to save file')
      return false
    } catch (error) {
      console.error('Error saving file:', error)
      setStatus('❌ Error saving file')
      return false
    }
  }

  const handleSave = async () => {
    const updatedSections = editableSections.map(section => {
      const parsedSection = parseSectionText(section.text)
      return {
        ...section,
        paragraphs: parsedSection.paragraphs,
        bullets: parsedSection.bullets,
        keyValues: parsedSection.keyValues
      }
    })
    const nextContent = buildDocumentFromSections(updatedSections)
    const saved = await saveReferenceContent(nextContent)
    if (saved) {
      setIsEditing(false)
      setEditableSections([])
    }
  }

  const handleCancel = () => {
    setIsEditing(false)
    setEditableSections([])
  }

  const handleAiEdit = async () => {
    if (!files[activeTab]) return
    const instructions = aiEditPrompt.trim()
    if (!instructions) {
      setStatus('❌ Please describe the changes you want to make')
      return
    }

    try {
      setAiEditLoading(true)
      setAiEditHistory(prev => [...prev, { role: 'user', content: instructions }])
      const authHeaders = await getAuthHeaders()
      const tabData = REFERENCE_TABS.find(t => t.id === activeTab)
      if (!tabData) return
      const aiEditUrl =
        tabData.source === 'book-bible'
          ? `/api/v2/projects/${projectId}/book-bible/ai-edit`
          : `/api/v2/projects/${projectId}/references/${tabData.filename}/ai-edit`

      const response = await fetchApi(
        aiEditUrl,
        {
          method: 'POST',
          headers: {
            ...authHeaders,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            instructions,
            current_content: files[activeTab].content
          })
        }
      )

      if (response.ok) {
        const data = await response.json()
        const updatedContent = data.content || ''
        setFiles(prev => ({
          ...prev,
          [activeTab]: {
            ...prev[activeTab],
            content: updatedContent,
            lastModified: data.lastModified || prev[activeTab].lastModified
          }
        }))
        setIsEditing(false)
        setAiEditPrompt('')
        setAiEditOpen(false)
        setAiEditHistory(prev => [...prev, { role: 'assistant', content: 'Applied your changes.' }])
        setStatus('✅ AI edits applied successfully')
        loadCanonLogs()
      } else {
        const errorData = await response.json()
        setStatus(`❌ AI edit failed: ${errorData.detail || errorData.error || 'Unknown error'}`)
      }
    } catch (error) {
      console.error('Error applying AI edit:', error)
      setStatus('❌ Error applying AI edits')
    } finally {
      setAiEditLoading(false)
    }
  }

  const handleApprove = () => {
    setFiles(prev => ({
      ...prev,
      [activeTab]: {
        ...prev[activeTab],
        approved: true
      }
    }))
    setStatus(`✅ ${REFERENCE_TABS.find(t => t.id === activeTab)?.label} approved`)
  }

  const handleFinishReview = () => {
    // Redirect to the chapter writing workspace
    router.push(`/project/${projectId}/chapters`)
  }

  const [isGeneratingRefs, setIsGeneratingRefs] = useState(false)
  const [showRegenerateConfirm, setShowRegenerateConfirm] = useState(false)

  const generateAllReferences = async () => {
    if (isGeneratingRefs) return
    setIsGeneratingRefs(true)
    setStatus('')

    try {
      const authHeaders = await getAuthHeaders()

      GlobalLoader.show({
        title: 'Regenerating Reference Files',
        stage: 'Starting generation...',
        progress: 0,
        showProgress: true,
        safeToLeave: true,
        canMinimize: true,
        customMessages: [
          'Building character profiles and entity registry...',
          'Constructing world-building and sensory palettes...',
          'Mapping plot outline and scene breakdowns...',
          'Charting plot timeline and continuity rules...',
          'Extracting entity registry for consistency...',
          'Crafting style guide and voice samples...',
          'Developing themes, motifs, and symbols...',
          'Creating director guide for first drafts...',
          'Mapping character relationships and secrets...',
          'Compiling research notes...',
          'Profiling target audience...',
        ],
        timeoutMs: 1800000,
      })

      const response = await fetchApi(`/api/v2/projects/${projectId}/references/generate`, {
        method: 'POST',
        headers: authHeaders
      })

      if (response.ok) {
        startReferenceProgressPolling(projectId, authHeaders)
      } else {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }))
        setStatus(`Generation failed: ${errorData.detail || 'Unknown error'}`)
        setIsGeneratingRefs(false)
        GlobalLoader.hide()
        setTimeout(() => GlobalLoader.forceHide?.(), 500)
      }
    } catch (error) {
      console.error('Error generating references:', error)
      setStatus('Error starting reference generation. Please try again.')
      setIsGeneratingRefs(false)
      GlobalLoader.hide()
      setTimeout(() => GlobalLoader.forceHide?.(), 500)
    }
  }

  const progressIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const generationStartedAtRef = useRef<number>(0)

  const startReferenceProgressPolling = (
    projectId: string,
    authHeaders: Record<string, string>
  ) => {
    if (progressIntervalRef.current) {
      clearInterval(progressIntervalRef.current)
      progressIntervalRef.current = null
    }
    generationStartedAtRef.current = Date.now()

    const poll = async () => {
      try {
        const res = await fetchApi(`/api/v2/projects/${projectId}/references/progress`, {
          headers: authHeaders,
        })
        if (!res.ok) return
        const data = await res.json()

        // Ignore stale "completed" responses that arrive before the new job
        // has had time to register (the fallback returns "completed" if old
        // files exist). Give the backend 8 seconds to start the new job.
        const elapsed = Date.now() - generationStartedAtRef.current
        if (data.status === 'completed' && elapsed < 8000 && !data.files_total) {
          GlobalLoader.update({ stage: 'Initializing generation...' })
          return
        }

        const progressNum = typeof data.progress === 'number' ? data.progress
          : data.progress?.percentage ?? 0
        const filesCompleted = data.files_completed || 0
        const filesTotal = data.files_total || 0
        const stageLabel = filesTotal > 0
          ? `${data.stage || 'Generating'} — ${filesCompleted} of ${filesTotal} files complete`
          : data.stage || 'Initializing...'
        GlobalLoader.update({ progress: progressNum, stage: stageLabel })

        if (data.status === 'completed' && (elapsed >= 8000 || data.files_total > 0)) {
          clearInterval(progressIntervalRef.current as NodeJS.Timeout)
          progressIntervalRef.current = null
          setIsGeneratingRefs(false)
          setStatus(`✅ Successfully generated ${filesCompleted || 'all'} reference files`)
          GlobalLoader.hide()
          setTimeout(() => GlobalLoader.forceHide?.(), 1000)
          await loadReferenceFiles()
        }
        if (data.status === 'failed' || data.status === 'failed-rate-limit') {
          clearInterval(progressIntervalRef.current as NodeJS.Timeout)
          progressIntervalRef.current = null
          setIsGeneratingRefs(false)
          GlobalLoader.hide()
          setTimeout(() => GlobalLoader.forceHide?.(), 1000)
          setStatus(`Reference generation failed${data.message ? `: ${data.message}` : ''}`)
        }
      } catch (e) {
        // Keep trying quietly; network hiccups are expected
      }
    }
    progressIntervalRef.current = setInterval(poll, 3000)
  }

  const activeTabData = REFERENCE_TABS.find(t => t.id === activeTab)
  const isBookBibleTab = activeTabData?.source === 'book-bible'
  const activeLastUpdated = files[activeTab]?.lastModified
    ? new Date(files[activeTab].lastModified as string).toLocaleDateString()
    : 'Not yet saved'
  const currentFile = files[activeTab]
  const parsedSections = useMemo(() => {
    if (!currentFile?.content) return []
    const parsed = parseReferenceContent(currentFile.content)
    if (parsed.length > 0) return parsed
    return [
      {
        id: 'section-0',
        title: 'Overview',
        paragraphs: [currentFile.content],
        bullets: [],
        keyValues: []
      }
    ]
  }, [currentFile?.content])

  const renderKeyValues = (items: ReferenceKeyValue[]) => {
    if (!items.length) return null
    return (
      <div className="space-y-2">
        {items.map((item, idx) => (
          <div key={`${item.label}-${idx}`} className="flex flex-col gap-0.5">
            <span className="text-xs font-medium uppercase tracking-wide text-gray-400">
              {item.label}
            </span>
            <span className="text-sm text-gray-700">{item.value}</span>
          </div>
        ))}
      </div>
    )
  }

  const renderBullets = (items: string[]) => {
    if (!items.length) return null
    return (
      <ul className="space-y-1.5 text-sm text-gray-700">
        {items.map((item, idx) => (
          <li key={`${item}-${idx}`} className="flex gap-2">
            <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-gray-300 shrink-0" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    )
  }

  const renderParagraphs = (items: string[]) => {
    if (!items.length) return null
    return (
      <div className="space-y-2 text-sm text-gray-700 leading-relaxed">
        {items.map((item, idx) => (
          <p key={`${item}-${idx}`}>{item}</p>
        ))}
      </div>
    )
  }

  const renderSectionCard = (section: ParsedSection) => (
    <div key={section.id} className="rounded-xl border border-gray-200 bg-white p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h4 className="text-base font-semibold text-gray-900">{section.title}</h4>
        {!isEditing && (
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setSectionEditMode('manual')
                setSectionEditId(section.id)
                setSectionEditTitle(section.title)
                setSectionEditText(sectionToEditableText(section))
                setSectionEditPrompt('')
                setSectionEditHistory([])
                setSectionEditOpen(true)
              }}
            >
              <PencilIcon className="mr-2 h-3.5 w-3.5" />
              Edit
            </Button>
            <Button
              variant="default"
              size="sm"
              onClick={() => {
                setSectionEditMode('ai')
                setSectionEditId(section.id)
                setSectionEditTitle(section.title)
                setSectionEditText(sectionToEditableText(section))
                setSectionEditPrompt('')
                setSectionEditHistory([])
                setSectionEditOpen(true)
              }}
            >
              <SparklesIcon className="mr-2 h-3.5 w-3.5" />
              AI Edit
            </Button>
          </div>
        )}
      </div>
      <div className="mt-4 space-y-4">
        {renderKeyValues(section.keyValues)}
        {renderBullets(section.bullets)}
        {renderParagraphs(section.paragraphs)}
      </div>
    </div>
  )

  const useGridLayout = ['characters', 'world-building', 'plot-timeline', 'canon-log'].includes(activeTab)

  const renderReferenceContent = () => {
    if (!parsedSections.length) {
      return (
        <div className="text-center py-12">
          <p className="text-sm text-gray-500">
            This reference file is empty. Use Manual Edit or AI Edit to add content.
          </p>
        </div>
      )
    }

    return (
      <div className={useGridLayout ? 'grid gap-4 grid-cols-1 sm:grid-cols-2' : 'space-y-4'}>
        {parsedSections.map(renderSectionCard)}
      </div>
    )
  }

  const renderEditingSections = () => (
    <div className="space-y-4">
      {editableSections.map(section => (
        <div key={section.id} className="rounded-xl border border-gray-200 bg-white p-5">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-base font-semibold text-gray-900">{section.title}</h4>
            <span className="text-xs text-gray-400">Editing</span>
          </div>
          <Textarea
            id={`reference-section-${section.id}`}
            name={`referenceSection-${section.id}`}
            value={section.text}
            onChange={(event) => {
              const value = event.target.value
              setEditableSections(prev =>
                prev.map(item => (item.id === section.id ? { ...item, text: value } : item))
              )
            }}
            className="min-h-[180px] max-h-[400px] overflow-y-auto text-sm"
            placeholder="Write clear, human text. Use 'Label: value' for structured items."
          />
        </div>
      ))}
    </div>
  )

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 p-6">
        <div className="max-w-4xl mx-auto">
          <div className="animate-pulse space-y-4">
            <div className="h-8 bg-gray-200 rounded w-1/3"></div>
            <div className="h-4 bg-gray-200 rounded w-2/3"></div>
            <div className="h-64 bg-gray-200 rounded"></div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <ProjectLayout 
      projectId={actualProjectId || rawProjectId} 
      projectTitle={projectTitle}
    >
      <div className="bg-gray-50 min-h-screen">
      <div className="w-full px-4 sm:px-6 md:px-8 lg:px-12 py-6 sm:py-8">
        <div className="max-w-6xl mx-auto">
        {/* Page header */}
        <div className="mb-6 flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 tracking-tight">Reference Materials</h1>
            <p className="text-sm text-gray-500 mt-1">
              Your story&apos;s foundation — characters, world-building, and plot elements
            </p>
          </div>
          <button
            onClick={() => setShowRegenerateConfirm(true)}
            disabled={isGeneratingRefs}
            className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 hover:border-gray-400 transition-all disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
          >
            {isGeneratingRefs ? (
              <svg className="animate-spin h-4 w-4 text-blue-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
            ) : (
              <SparklesIcon className="h-4 w-4" />
            )}
            {isGeneratingRefs ? 'Regenerating...' : 'Regenerate All References'}
          </button>
        </div>

        {/* Regenerate confirmation dialog */}
        <Dialog open={showRegenerateConfirm} onOpenChange={setShowRegenerateConfirm}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Regenerate All References?</DialogTitle>
            </DialogHeader>
            <p className="text-sm text-gray-600 py-2">
              This will regenerate all reference files using the latest AI system. Your current book bible will be preserved, but all reference documents (characters, outline, world-building, etc.) will be replaced with freshly generated versions.
            </p>
            <p className="text-sm text-gray-500">
              Any manual edits to reference files will be overwritten. This process takes 2-5 minutes.
            </p>
            <DialogFooter>
              <Button variant="outline" onClick={() => setShowRegenerateConfirm(false)}>
                Cancel
              </Button>
              <Button
                onClick={() => {
                  setShowRegenerateConfirm(false)
                  generateAllReferences()
                }}
              >
                Regenerate All
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
        {/* Show retry button if needed */}
        {shouldShowRetry && (
          <div className="mb-8 bg-amber-50 rounded-xl p-4 sm:p-6 border border-amber-200">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div>
                <h3 className="text-lg font-bold text-amber-800 mb-2">Generation Failed</h3>
                <p className="text-amber-700 font-medium">Would you like to retry creating the reference files?</p>
              </div>
              <button
                onClick={generateAllReferences}
                disabled={isGeneratingRefs}
                className="bg-amber-600 text-white px-6 py-3 rounded-xl font-semibold hover:bg-amber-700 transition-all disabled:opacity-50 w-full sm:w-auto"
              >
                {isGeneratingRefs ? 'Generating...' : 'Retry Generation'}
              </button>
            </div>
          </div>
        )}

        {/* Inline generation progress banner */}
        {isGeneratingRefs && (
          <div className="mb-6 bg-blue-50 rounded-xl p-4 sm:p-5 border border-blue-200 animate-in fade-in duration-300">
            <div className="flex items-center gap-3">
              <div className="shrink-0">
                <svg className="animate-spin h-5 w-5 text-blue-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-blue-900">Regenerating reference files...</p>
                <p className="text-xs text-blue-700 mt-0.5">This takes 2-5 minutes. You can safely navigate away — progress is saved automatically.</p>
              </div>
            </div>
          </div>
        )}

        {/* Tab Navigation */}
        <div className="mb-6">
          <div className="flex gap-1 overflow-x-auto scrollbar-none pb-1">
            {REFERENCE_TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-3 sm:px-4 py-2 font-medium text-xs sm:text-sm rounded-lg whitespace-nowrap transition-all duration-200 ${
                  activeTab === tab.id
                    ? 'bg-gray-900 text-white shadow-sm'
                    : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                }`}
                aria-current={activeTab === tab.id ? 'page' : undefined}
              >
                {tab.label}
              </button>
            ))}
          </div>
          {activeTabData?.description && (
            <p className="mt-2 text-sm text-gray-500">
              {activeTabData.description}
            </p>
          )}
        </div>

        {/* Content Area */}
        <div className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-16">
              <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mb-4" />
              <p className="text-sm text-gray-500">Loading reference files...</p>
            </div>
          ) : files[activeTab] ? (
            <div className="space-y-5">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h3 className="text-lg font-semibold text-gray-900">
                    {activeTabData?.label}
                  </h3>
                  <p className="text-xs text-gray-400">
                    Updated {activeLastUpdated}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {!isEditing ? (
                    <>
                      <Button variant="outline" onClick={handleEdit}>
                        <PencilIcon className="mr-2 h-4 w-4" />
                        Manual Edit
                      </Button>
                      <Button variant="default" onClick={() => setAiEditOpen(true)}>
                        <SparklesIcon className="mr-2 h-4 w-4" />
                        AI Edit
                      </Button>
                    </>
                  ) : (
                    <>
                      <Button variant="outline" onClick={handleCancel}>
                        Cancel
                      </Button>
                      <Button variant="default" onClick={handleSave}>
                        Save Changes
                      </Button>
                    </>
                  )}
                </div>
              </div>

              {isEditing ? (
                <div className="space-y-4">
                  {renderEditingSections()}
                  <div className="text-sm text-gray-400">
                    Tip: Use short paragraphs and clear labels to keep sections readable.
                  </div>
                </div>
              ) : (
                <div className="space-y-6">{renderReferenceContent()}</div>
              )}
            </div>
          ) : (
            <div className="text-center py-16">
              <div className="mb-8">
                <div className="w-20 h-20 mx-auto bg-gradient-to-br from-brand-lavender/20 to-brand-forest/20 rounded-full flex items-center justify-center mb-6">
                  <span className="text-4xl">📚</span>
                </div>
              </div>
              <h3 className="text-2xl font-bold text-gray-900 mb-4">
                No {activeTabData?.label} Yet
              </h3>
              {isBookBibleTab ? (
                <p className="text-gray-500 font-medium mb-8 max-w-md mx-auto">
                  Your project does not have a book bible yet. Create one to establish the story foundation and unlock deeper reference generation.
                </p>
              ) : (
                <p className="text-gray-500 font-medium mb-8 max-w-md mx-auto">
                  This reference hasn&apos;t been generated yet. You can create it manually or generate all references at once.
                </p>
              )}
              <div className="flex flex-col sm:flex-row gap-3 justify-center">
                <Button variant="default" onClick={handleEdit}>
                  <PencilIcon className="mr-2 h-4 w-4" />
                  Create Manually
                </Button>
                <Button variant="outline" onClick={() => setAiEditOpen(true)}>
                  <SparklesIcon className="mr-2 h-4 w-4" />
                  Create with AI
                </Button>
              </div>
            </div>
          )}
        </div>

        <Dialog open={aiEditOpen} onOpenChange={setAiEditOpen}>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>
                AI Edit: {activeTabData?.label}
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div className="rounded-xl bg-gray-50 p-4 text-sm text-gray-600">
                Describe the changes you want, and the AI will update the entire reference document.
              </div>

              {aiEditHistory.length > 0 && (
                <div className="max-h-48 space-y-3 overflow-y-auto rounded-xl border border-gray-200/20 bg-white/70 p-4">
                  {aiEditHistory.map((message, idx) => (
                    <div
                      key={`${message.role}-${idx}`}
                      className={`rounded-lg px-3 py-2 text-sm ${
                        message.role === 'user'
                          ? 'bg-brand-forest/10 text-gray-900'
                          : 'bg-brand-lavender/20 text-gray-600'
                      }`}
                    >
                      <span className="block text-xs font-semibold uppercase tracking-wide text-gray-400">
                        {message.role === 'user' ? 'You' : 'AI'}
                      </span>
                      <p className="mt-1">{message.content}</p>
                    </div>
                  ))}
                </div>
              )}

              <Textarea
                id="reference-ai-edit-prompt"
                name="referenceAiEditPrompt"
                value={aiEditPrompt}
                onChange={(event) => setAiEditPrompt(event.target.value)}
                className="min-h-[140px] border-gray-200/30 bg-white/90 text-sm text-gray-900"
                placeholder="Describe the changes you want to make to this reference document."
              />
            </div>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => {
                  setAiEditOpen(false)
                  setAiEditPrompt('')
                }}
                disabled={aiEditLoading}
              >
                Cancel
              </Button>
              <Button onClick={handleAiEdit} disabled={aiEditLoading}>
                {aiEditLoading ? 'Applying...' : 'Apply AI Edit'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={sectionEditOpen} onOpenChange={setSectionEditOpen}>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>
                {sectionEditMode === 'ai' ? 'AI Edit' : 'Manual Edit'}: {sectionEditTitle}
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              {sectionEditMode === 'ai' ? (
                <>
                  <div className="rounded-xl bg-gray-50 p-4 text-sm text-gray-600">
                    Describe the exact changes for this section only.
                  </div>
                  {sectionEditHistory.length > 0 && (
                    <div className="max-h-48 space-y-3 overflow-y-auto rounded-xl border border-gray-200/20 bg-white/70 p-4">
                      {sectionEditHistory.map((message, idx) => (
                        <div
                          key={`${message.role}-${idx}`}
                          className={`rounded-lg px-3 py-2 text-sm ${
                            message.role === 'user'
                              ? 'bg-brand-forest/10 text-gray-900'
                              : 'bg-brand-lavender/20 text-gray-600'
                          }`}
                        >
                          <span className="block text-xs font-semibold uppercase tracking-wide text-gray-400">
                            {message.role === 'user' ? 'You' : 'AI'}
                          </span>
                          <p className="mt-1">{message.content}</p>
                        </div>
                      ))}
                    </div>
                  )}
                  <Textarea
                    id="reference-section-ai-prompt"
                    name="referenceSectionAiPrompt"
                    value={sectionEditPrompt}
                    onChange={(event) => setSectionEditPrompt(event.target.value)}
                    className="min-h-[140px] border-gray-200/30 bg-white/90 text-sm text-gray-900"
                    placeholder="Describe the changes you want to make to this section."
                  />
                </>
              ) : (
                <Textarea
                  id="reference-section-edit-text"
                  name="referenceSectionEditText"
                  value={sectionEditText}
                  onChange={(event) => setSectionEditText(event.target.value)}
                  className="min-h-[220px] border-gray-200/30 bg-white/90 text-sm text-gray-900"
                  placeholder="Write clear, human text. Use 'Label: value' for structured items."
                />
              )}
            </div>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => {
                  setSectionEditOpen(false)
                  setSectionEditPrompt('')
                  setSectionEditText('')
                }}
                disabled={sectionEditLoading}
              >
                Cancel
              </Button>
              <Button
                onClick={async () => {
                  if (!currentFile || !sectionEditId) return
                  const baseSections = parseReferenceContent(currentFile.content)
                  const targetIndex = baseSections.findIndex(section => section.id === sectionEditId)
                  if (targetIndex < 0) {
                    setStatus('❌ Unable to find that section')
                    return
                  }

                  if (sectionEditMode === 'manual') {
                    const parsedSection = parseSectionText(sectionEditText)
                    const updatedSections = baseSections.map(section =>
                      section.id === sectionEditId
                        ? {
                            ...section,
                            paragraphs: parsedSection.paragraphs,
                            bullets: parsedSection.bullets,
                            keyValues: parsedSection.keyValues
                          }
                        : section
                    )
                    const nextContent = buildDocumentFromSections(updatedSections)
                    setSectionEditLoading(true)
                    const saved = await saveReferenceContent(nextContent)
                    setSectionEditLoading(false)
                    if (saved) {
                      setSectionEditOpen(false)
                      setSectionEditText('')
                    }
                    return
                  }

                  const instructions = sectionEditPrompt.trim()
                  if (!instructions) {
                    setStatus('❌ Please describe the changes you want to make')
                    return
                  }
                  try {
                    setSectionEditLoading(true)
                    setSectionEditHistory(prev => [...prev, { role: 'user', content: instructions }])
                    const authHeaders = await getAuthHeaders()
                    const tabData = REFERENCE_TABS.find(t => t.id === activeTab)
                    if (!tabData) return
                    const aiEditUrl =
                      tabData.source === 'book-bible'
                        ? `/api/v2/projects/${projectId}/book-bible/ai-edit`
                        : `/api/v2/projects/${projectId}/references/${tabData.filename}/ai-edit`
                    const response = await fetchApi(
                      aiEditUrl,
                      {
                        method: 'POST',
                        headers: {
                          ...authHeaders,
                          'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                          instructions,
                          current_content: sectionEditText,
                          scope: 'section',
                          section_title: sectionEditTitle
                        })
                      }
                    )
                    if (response.ok) {
                      const data = await response.json()
                      const updatedSectionText = data.content || ''
                      const parsedSection = parseSectionText(updatedSectionText)
                      const updatedSections = baseSections.map(section =>
                        section.id === sectionEditId
                          ? {
                              ...section,
                              paragraphs: parsedSection.paragraphs,
                              bullets: parsedSection.bullets,
                              keyValues: parsedSection.keyValues
                            }
                          : section
                      )
                      const nextContent = buildDocumentFromSections(updatedSections)
                      const saved = await saveReferenceContent(nextContent)
                      if (saved) {
                        setSectionEditHistory(prev => [
                          ...prev,
                          { role: 'assistant', content: 'Applied your changes.' }
                        ])
                        setSectionEditPrompt('')
                        setSectionEditText(updatedSectionText)
                        setSectionEditOpen(false)
                      }
                    } else {
                      const errorData = await response.json()
                      setStatus(`❌ AI edit failed: ${errorData.detail || errorData.error || 'Unknown error'}`)
                    }
                  } catch (error) {
                    console.error('Error applying section AI edit:', error)
                    setStatus('❌ Error applying AI edits')
                  } finally {
                    setSectionEditLoading(false)
                  }
                }}
                disabled={sectionEditLoading}
              >
                {sectionEditLoading
                  ? sectionEditMode === 'ai'
                    ? 'Applying...'
                    : 'Saving...'
                  : sectionEditMode === 'ai'
                  ? 'Apply AI Edit'
                  : 'Save Section'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={rewriteDialogOpen} onOpenChange={setRewriteDialogOpen}>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>
                Rewrite Prior Chapters
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div className="rounded-xl bg-gray-50 p-4 text-sm text-gray-600">
                Would you like to rewrite prior chapters to incorporate this canon update fully?
                {rewriteSourceEntry?.source_label ? (
                  <span className="block mt-2 text-xs text-gray-400">
                    Canon update: {rewriteSourceEntry.source_label}
                  </span>
                ) : null}
              </div>
              {rewriteLoading ? (
                <div className="text-sm text-gray-400">Checking for impacted chapters...</div>
              ) : rewriteCandidates.length === 0 ? (
                <div className="text-sm text-gray-400">
                  No prior chapters appear to mention this update. No rewrite needed.
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-gray-400">
                    <span>
                      {rewriteCandidates.length} chapters flagged, {Object.values(rewriteSelected).filter(Boolean).length} selected
                    </span>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          const selections: Record<string, boolean> = {}
                          rewriteCandidates.forEach(item => {
                            selections[item.chapter_id] = true
                          })
                          setRewriteSelected(selections)
                        }}
                      >
                        Select all
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          const selections: Record<string, boolean> = {}
                          rewriteCandidates.forEach(item => {
                            selections[item.chapter_id] = false
                          })
                          setRewriteSelected(selections)
                        }}
                      >
                        Clear
                      </Button>
                    </div>
                  </div>
                  {rewriteCandidates.map(candidate => (
                    <label
                      key={candidate.chapter_id}
                      className="flex items-center gap-3 rounded-lg border border-gray-200/20 bg-white/70 px-3 py-2 text-sm text-gray-600"
                    >
                      <input
                        id={`rewrite-${candidate.chapter_id}`}
                        name={`rewriteSelected-${candidate.chapter_id}`}
                        type="checkbox"
                        checked={rewriteSelected[candidate.chapter_id] || false}
                        onChange={(event) =>
                          setRewriteSelected(prev => ({
                            ...prev,
                            [candidate.chapter_id]: event.target.checked
                          }))
                        }
                      />
                      <span className="font-medium">
                        {candidate.title || `Chapter ${candidate.chapter_number ?? ''}`}
                      </span>
                    </label>
                  ))}
                  <div className="text-xs text-gray-400">
                    Rewrites use AI and can take a few minutes.
                  </div>
                </div>
              )}
            </div>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setRewriteDialogOpen(false)}
                disabled={rewriteSubmitting}
              >
                Cancel
              </Button>
              <Button
                onClick={submitRewriteRequest}
                disabled={rewriteSubmitting || rewriteCandidates.length === 0}
              >
                {rewriteSubmitting ? 'Queuing...' : 'Rewrite Selected Chapters'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {status && (
        <div className="mt-6 rounded-2xl border border-gray-200/20 bg-white/80 p-4 text-sm font-medium text-gray-600 shadow-sm">
            {status}
          </div>
        )}

        {/* Canon Log */}
        <div className="mt-10 bg-white rounded-xl p-5 sm:p-6 lg:p-8 border border-gray-200 shadow-sm">
          <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div>
              <h3 className="text-2xl font-bold text-gray-900">Canon Log</h3>
              <p className="text-sm text-gray-500 font-medium">
                Steering updates applied across your book bible and references.
              </p>
            </div>
            <Button variant="outline" size="sm" onClick={loadCanonLogs} disabled={canonLogLoading}>
              {canonLogLoading ? 'Refreshing...' : 'Refresh'}
            </Button>
          </div>

          <div className="mt-6 space-y-4">
            {canonLogLoading ? (
              <div className="text-sm text-gray-400">Loading canon log...</div>
            ) : canonLogs.length === 0 ? (
              <div className="text-sm text-gray-400">
                No steering updates yet. Edits will appear here once saved.
              </div>
            ) : (
              canonLogs.map(entry => (
                <div key={entry.id} className="rounded-xl border border-gray-200/20 bg-white/80 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-sm font-semibold text-gray-900">
                      {entry.source_label || entry.source_type || 'Update'}
                    </div>
                    <div className="text-xs font-semibold uppercase tracking-wide text-gray-400">
                      {entry.status || 'queued'}
                    </div>
                  </div>
                  <div className="mt-2 text-xs text-gray-400">
                    {entry.created_at ? new Date(entry.created_at).toLocaleString() : 'Time unavailable'}
                    {entry.mode ? ` • ${entry.mode}` : ''}
                    {entry.scope ? ` • ${entry.scope}` : ''}
                  </div>
                  {entry.instructions && (
                    <p className="mt-3 text-sm text-gray-600">
                      {entry.instructions}
                    </p>
                  )}
                  {entry.applied_targets && entry.applied_targets.length > 0 && (
                    <div className="mt-3 text-xs text-gray-400">
                      Updated: {entry.applied_targets.slice(0, 5).join(', ')}
                      {entry.applied_targets.length > 5 ? '…' : ''}
                    </div>
                  )}
                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => openRewriteDialog(entry)}
                      disabled={entry.status !== 'completed' || entry.source_type === 'chapter_rewrite'}
                    >
                      Check impacted chapters
                    </Button>
                    {entry.status !== 'completed' && (
                      <span className="text-xs text-gray-400">Waiting for canon update</span>
                    )}
                    {entry.source_type === 'chapter_rewrite' && (
                      <span className="text-xs text-gray-400">Rewrite batch</span>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Enhanced Reference Generation Section */}
        <div className="mt-12 bg-white rounded-xl p-5 sm:p-6 lg:p-8 border border-gray-200 shadow-sm">
          <h3 className="text-2xl font-bold text-gray-900 mb-6">Reference Generation</h3>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-white/60 rounded-xl p-6 border border-gray-200/20">
              <h4 className="text-lg font-bold text-gray-900 mb-3">Manual Generation</h4>
              <p className="text-gray-500 mb-4 font-medium">
                Trigger reference file generation based on your current project content.
              </p>
              <button
                onClick={generateAllReferences}
                disabled={loading || isGeneratingRefs}
                className="bg-gray-900 text-white px-6 py-3 rounded-xl font-semibold hover:bg-gray-800 transition-all disabled:opacity-50 w-full"
              >
                {isGeneratingRefs ? 'Generating...' : 'Generate References'}
              </button>
            </div>
            
            <div className="bg-white/60 rounded-xl p-6 border border-gray-200/20">
              <h4 className="text-lg font-bold text-gray-900 mb-3">Auto-Generation</h4>
              <p className="text-gray-500 mb-4 font-medium">
                Reference files are automatically created when you generate chapters or upload content.
              </p>
              <div className="text-sm text-gray-400 font-medium">
                Current status: <span className="text-gray-900 font-bold">
                  {Object.keys(files).length > 0 ? 'Active' : 'Pending'}
                </span>
              </div>
            </div>
          </div>
        </div>
        </div>
      </div>
      </div>
    </ProjectLayout>
  )
} 