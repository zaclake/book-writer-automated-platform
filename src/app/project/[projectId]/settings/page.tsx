'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'next/navigation'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { toast } from '@/hooks/useAppToast'
import ProjectLayout from '@/components/layout/ProjectLayout'
import { useProject } from '@/hooks/useFirestore'
import { useAuthToken } from '@/lib/auth'
import { fetchApi } from '@/lib/api-client'

type InvolvementLevel = 'hands_off' | 'balanced' | 'hands_on'
type Purpose = 'personal' | 'commercial' | 'educational'

interface SettingsFormState {
  genre: string
  target_chapters: number
  word_count_per_chapter: number
  target_audience: string
  writing_style: string
  quality_gates_enabled: boolean
  auto_completion_enabled: boolean
  involvement_level: InvolvementLevel
  purpose: Purpose
}

const DEFAULT_FORM_STATE: SettingsFormState = {
  genre: '',
  target_chapters: 25,
  word_count_per_chapter: 3800,
  target_audience: '',
  writing_style: '',
  quality_gates_enabled: true,
  auto_completion_enabled: true,
  involvement_level: 'balanced',
  purpose: 'personal',
}

export default function ProjectSettingsPage() {
  const params = useParams()
  const projectId = params.projectId as string
  
  // Get project data for the navigation title
  const { project, loading, refreshProject } = useProject(projectId)
  const { getAuthHeaders } = useAuthToken()
  const [formState, setFormState] = useState<SettingsFormState>(DEFAULT_FORM_STATE)
  const [hasLoadedFromProject, setHasLoadedFromProject] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [isDirty, setIsDirty] = useState(false)
  const lastLoadedProjectId = useRef<string | null>(null)

  const totalTargetWords = useMemo(() => {
    return Math.max(0, formState.target_chapters * formState.word_count_per_chapter)
  }, [formState])

  const pacingLabel = useMemo(() => {
    const wc = formState.word_count_per_chapter
    if (wc <= 1800) return 'Fast'
    if (wc <= 3200) return 'Balanced'
    return 'Expansive'
  }, [formState])

  useEffect(() => {
    if (!project) return
    const projectChanged = lastLoadedProjectId.current !== projectId
    if (!isDirty || projectChanged) {
      const settings = project.settings || ({} as any)
      setFormState({
        genre: settings.genre ?? DEFAULT_FORM_STATE.genre,
        target_chapters: settings.target_chapters ?? DEFAULT_FORM_STATE.target_chapters,
        word_count_per_chapter: settings.word_count_per_chapter ?? DEFAULT_FORM_STATE.word_count_per_chapter,
        target_audience: settings.target_audience ?? DEFAULT_FORM_STATE.target_audience,
        writing_style: settings.writing_style ?? DEFAULT_FORM_STATE.writing_style,
        quality_gates_enabled: settings.quality_gates_enabled ?? DEFAULT_FORM_STATE.quality_gates_enabled,
        auto_completion_enabled: settings.auto_completion_enabled ?? DEFAULT_FORM_STATE.auto_completion_enabled,
        involvement_level: (settings.involvement_level as InvolvementLevel) ?? DEFAULT_FORM_STATE.involvement_level,
        purpose: (settings.purpose as Purpose) ?? DEFAULT_FORM_STATE.purpose
      })
      setIsDirty(false)
      setHasLoadedFromProject(true)
      lastLoadedProjectId.current = projectId
    }
  }, [project, projectId, isDirty])

  const updateField = <K extends keyof SettingsFormState>(key: K, value: SettingsFormState[K]) => {
    setFormState((prev) => ({ ...prev, [key]: value }))
    setIsDirty(true)
  }

  const updateNumberField = (key: keyof SettingsFormState, value: string) => {
    const parsed = Number(value)
    if (Number.isNaN(parsed)) return
    const safeValue = Math.max(0, Math.floor(parsed))
    updateField(key as keyof SettingsFormState, safeValue as SettingsFormState[keyof SettingsFormState])
  }

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
        e.preventDefault()
        if (isDirty && !isSaving) {
          handleSave()
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDirty, isSaving, formState])

  const handleSave = async () => {
    if (isSaving) return
    if (!formState.genre.trim()) {
      toast({
        title: 'Genre required',
        description: 'Please provide a genre before saving.',
        variant: 'destructive'
      })
      return
    }
    if (!formState.target_audience.trim()) {
      toast({
        title: 'Target audience required',
        description: 'Please provide a target audience before saving.',
        variant: 'destructive'
      })
      return
    }
    if (!formState.writing_style.trim()) {
      toast({
        title: 'Writing style required',
        description: 'Please provide a writing style before saving.',
        variant: 'destructive'
      })
      return
    }

    try {
      setIsSaving(true)
      const authHeaders = await getAuthHeaders()
      const response = await fetchApi(`/api/v2/projects/${encodeURIComponent(projectId)}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders
        },
        body: JSON.stringify({ settings: formState })
      })

      if (!response.ok) {
        throw new Error(await response.text())
      }

      toast({
        title: 'Settings saved',
        description: 'Your project settings have been updated.'
      })
      setIsDirty(false)
      refreshProject()
    } catch (error: any) {
      console.error('Failed to save settings:', error)
      toast({
        title: 'Save failed',
        description: error?.message || 'Please try again.',
        variant: 'destructive'
      })
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <ProjectLayout 
      projectId={projectId} 
      projectTitle={project?.metadata?.title || project?.title || 'Project'}
    >
      <div className="space-y-6 px-4 sm:px-6 md:px-8 lg:px-12 py-6 pb-28 sm:pb-6">
        <div className="max-w-5xl mx-auto space-y-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              Project Settings
              {isDirty && <span className="ml-2 text-xs font-semibold text-orange-600">Unsaved changes</span>}
            </h1>
            <p className="text-gray-600 mt-1">
              Configure project preferences and settings
            </p>
          </div>

          {loading && !hasLoadedFromProject ? (
            <Card>
              <CardHeader>
                <CardTitle>Loading Settings</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="py-6 text-sm text-gray-600">Fetching project settings...</div>
              </CardContent>
            </Card>
          ) : (
            <>
              <Card>
                <CardHeader>
                  <CardTitle>Manuscript Targets</CardTitle>
                </CardHeader>
                <CardContent className="space-y-5">
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    <div>
                      <Label htmlFor="settings-target-chapters" className="text-sm font-semibold text-gray-700">
                        Target Chapters
                      </Label>
                      <Input
                        id="settings-target-chapters"
                        name="targetChapters"
                        type="number"
                        min={1}
                        value={formState.target_chapters}
                        onChange={(event) => updateNumberField('target_chapters', event.target.value)}
                      />
                    </div>
                    <div>
                      <Label htmlFor="settings-word-count" className="text-sm font-semibold text-gray-700">
                        Chapter Word Count (Pacing)
                      </Label>
                      <Input
                        id="settings-word-count"
                        name="wordCountPerChapter"
                        type="number"
                        min={300}
                        value={formState.word_count_per_chapter}
                        onChange={(event) => updateNumberField('word_count_per_chapter', event.target.value)}
                      />
                      <div className="mt-1 text-xs text-gray-500">Pacing: {pacingLabel}</div>
                    </div>
                    <div>
                      <Label className="text-sm font-semibold text-gray-700">Total Target Words</Label>
                      <div className="mt-2 rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700">
                        {totalTargetWords.toLocaleString()}
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Audience & Style</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <div>
                      <Label htmlFor="settings-genre" className="text-sm font-semibold text-gray-700">
                        Genre
                      </Label>
                      <Input
                        id="settings-genre"
                        name="genre"
                        value={formState.genre}
                        onChange={(event) => updateField('genre', event.target.value)}
                      />
                    </div>
                    <div>
                      <Label htmlFor="settings-target-audience" className="text-sm font-semibold text-gray-700">
                        Target Audience
                      </Label>
                      <Input
                        id="settings-target-audience"
                        name="targetAudience"
                        value={formState.target_audience}
                        onChange={(event) => updateField('target_audience', event.target.value)}
                      />
                    </div>
                    <div className="md:col-span-2">
                      <Label htmlFor="settings-writing-style" className="text-sm font-semibold text-gray-700">
                        Writing Style
                      </Label>
                      <Input
                        id="settings-writing-style"
                        name="writingStyle"
                        value={formState.writing_style}
                        onChange={(event) => updateField('writing_style', event.target.value)}
                      />
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Writing System</CardTitle>
                </CardHeader>
                <CardContent className="space-y-5">
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <div>
                      <Label className="text-sm font-semibold text-gray-700">Involvement Level</Label>
                      <Select
                        value={formState.involvement_level}
                        onValueChange={(value) => updateField('involvement_level', value as InvolvementLevel)}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="hands_off">Hands Off</SelectItem>
                          <SelectItem value="balanced">Balanced</SelectItem>
                          <SelectItem value="hands_on">Hands On</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="text-sm font-semibold text-gray-700">Project Purpose</Label>
                      <Select
                        value={formState.purpose}
                        onValueChange={(value) => updateField('purpose', value as Purpose)}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="personal">Personal</SelectItem>
                          <SelectItem value="commercial">Commercial</SelectItem>
                          <SelectItem value="educational">Educational</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <label className="flex items-center gap-3">
                      <Checkbox
                        id="settings-quality-gates"
                        name="qualityGatesEnabled"
                        checked={!!formState.quality_gates_enabled}
                        onChange={(event) => updateField('quality_gates_enabled', event.target.checked)}
                      />
                      <div>
                        <div className="text-sm font-semibold text-gray-800">Quality Gates</div>
                        <div className="text-xs text-gray-500">Apply quality checks before chapter completion.</div>
                      </div>
                    </label>
                    <label className="flex items-center gap-3">
                      <Checkbox
                        id="settings-auto-complete"
                        name="autoCompletionEnabled"
                        checked={!!formState.auto_completion_enabled}
                        onChange={(event) => updateField('auto_completion_enabled', event.target.checked)}
                      />
                      <div>
                        <div className="text-sm font-semibold text-gray-800">Auto-Complete Book</div>
                        <div className="text-xs text-gray-500">Allow full-book generation when launched.</div>
                      </div>
                    </label>
                  </div>
                </CardContent>
              </Card>

              <div className="hidden sm:flex flex-col gap-3 sm:flex-row sm:justify-end">
                <Button
                  onClick={handleSave}
                  disabled={isSaving || !isDirty}
                >
                  {isSaving ? 'Saving...' : 'Save Settings'}
                </Button>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Mobile sticky save bar */}
      <div
        className="sm:hidden fixed bottom-0 left-0 right-0 bg-white/95 backdrop-blur border-t border-gray-200 p-4 shadow-lg z-50"
        style={{ paddingBottom: 'calc(1rem + env(safe-area-inset-bottom))' }}
      >
        <Button
          onClick={handleSave}
          disabled={isSaving || !isDirty}
          className="w-full min-h-[44px]"
        >
          {isSaving ? 'Saving...' : 'Save Settings'}
        </Button>
      </div>
    </ProjectLayout>
  )
} 