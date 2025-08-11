'use client'

import React, { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useUser } from '@clerk/nextjs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { toast } from '@/components/ui/use-toast'
import { useAutoSave, useSessionRecovery, SessionRecoveryPrompt } from '@/hooks/useAutoSave'
import { CreativeLoader } from '@/components/ui/CreativeLoader'
import { GlobalLoader } from '@/stores/useGlobalLoaderStore'
import { useJobProgress } from '@/hooks/useJobProgress'
import { 
  BookLengthTier, 
  BookLengthSpecs, 
  CreationMode, 
  QuickStartData, 
  GuidedWizardData, 
  PasteData, 
  BookBibleData 
} from '@/lib/types'



const getBookLengthSpecs = (tier: BookLengthTier): BookLengthSpecs => {
  const specs: Record<BookLengthTier, BookLengthSpecs> = {
    [BookLengthTier.NOVELLA]: {
      word_count_min: 17500,
      word_count_max: 40000,
      word_count_target: 28750,
      chapter_count_min: 8,
      chapter_count_max: 15,
      chapter_count_target: 12,
      avg_words_per_chapter: 2400
    },
    [BookLengthTier.SHORT_NOVEL]: {
      word_count_min: 40000,
      word_count_max: 60000,
      word_count_target: 50000,
      chapter_count_min: 15,
      chapter_count_max: 20,
      chapter_count_target: 18,
      avg_words_per_chapter: 2800
    },
    [BookLengthTier.STANDARD_NOVEL]: {
      word_count_min: 60000,
      word_count_max: 90000,
      word_count_target: 75000,
      chapter_count_min: 20,
      chapter_count_max: 30,
      chapter_count_target: 25,
      avg_words_per_chapter: 3000
    },
    [BookLengthTier.LONG_NOVEL]: {
      word_count_min: 90000,
      word_count_max: 120000,
      word_count_target: 105000,
      chapter_count_min: 25,
      chapter_count_max: 35,
      chapter_count_target: 30,
      avg_words_per_chapter: 3500
    },
    [BookLengthTier.EPIC_NOVEL]: {
      word_count_min: 120000,
      word_count_max: 200000,
      word_count_target: 160000,
      chapter_count_min: 30,
      chapter_count_max: 50,
      chapter_count_target: 40,
      avg_words_per_chapter: 4000
    }
  }
  return specs[tier]
}

const BookBibleCreator: React.FC<{ onComplete: (data: BookBibleData) => Promise<{ success: boolean; projectId?: string; referencesGenerated?: boolean }> }> = ({ onComplete }) => {
  const { user, isLoaded } = useUser()
  const [mode, setMode] = useState<CreationMode>('select')
  const [isLoading, setIsLoading] = useState(false)
  
  // Track project creation progress
  const [currentProjectId, setCurrentProjectId] = useState<string | null>(null)

  const router = useRouter()

  const { progress: jobProgress, isPolling } = useJobProgress(currentProjectId, {
    pollInterval: 3000,
    timeout: 600000, // 10-minute safety timeout
    onComplete: async () => {
      // Add small grace period so backend finishes writing files
      await new Promise((r) => setTimeout(r, 5000))
      if (currentProjectId) {
        router.push(`/project/${currentProjectId}/references`)
      }
    },
    onError: async (err) => {
      console.error('Reference generation error:', err)
      
      // Check if this is a rate limit error - if so, show different message
      if (jobProgress?.status === 'failed-rate-limit') {
        toast.error('Reference generation failed due to rate limits. You can retry from the References page.', {
          duration: 6000,
        })
        // Still navigate to references page so user can see retry option
        await new Promise((r) => setTimeout(r, 2000))
        if (currentProjectId) {
          router.push(`/project/${currentProjectId}/references?retry=true`)
        }
      } else {
        // Regular error handling
        await new Promise((r) => setTimeout(r, 2000))
        if (currentProjectId) {
          router.push(`/project/${currentProjectId}/overview?note=reference-error`)
        }
      }
    },
    onTimeout: async () => {
      console.warn('Reference generation timed out')
      await new Promise((r) => setTimeout(r, 2000))
      if (currentProjectId) {
        router.push(`/project/${currentProjectId}/overview?note=reference-timeout`)
      }
    }
  })

  // Loader progress/stage helpers reusable across render paths
  const loaderProgressValue = isLoading ? (jobProgress?.progress ?? 20) : 0
  const loaderStage = isLoading ? (jobProgress?.stage || (isPolling ? 'Generating References' : 'Creating Book Bible')) : undefined
  
  // Book configuration state
  const [bookLengthTier, setBookLengthTier] = useState<BookLengthTier>(BookLengthTier.STANDARD_NOVEL)
  const [customChapters, setCustomChapters] = useState<number | null>(null)
  const [includeSeriesBible, setIncludeSeriesBible] = useState(false)
  
  // Mode-specific state
  const [quickStartData, setQuickStartData] = useState<QuickStartData>({
    title: '',
    genre: 'Fiction',
    brief_premise: '',
    main_character: '',
    setting: '',
    conflict: ''
  })

  const [guidedData, setGuidedData] = useState<GuidedWizardData>({
    title: '',
    genre: 'Fiction',
    premise: '',
    main_characters: '',
    setting_time: '',
    setting_place: '',
    central_conflict: '',
    themes: '',
    target_audience: '',
    tone: '',
    key_plot_points: ''
  })

  const [pasteData, setPasteData] = useState({
    title: '',
    genre: 'Fiction',
    content: ''
  })

  const [mustInclude, setMustInclude] = useState<string>('')
  
  // Character limit constants (same as backend validation)
  const MAX_CHARACTERS = 50000
  const WARNING_THRESHOLD = 45000
  
  // Character count helpers for paste content
  const currentCharCount = pasteData.content.length
  const isNearLimit = currentCharCount >= WARNING_THRESHOLD
  const isOverLimit = currentCharCount > MAX_CHARACTERS
  const remainingChars = MAX_CHARACTERS - currentCharCount

  const getCharCountColor = () => {
    if (isOverLimit) return 'text-red-600'
    if (isNearLimit) return 'text-orange-600'
    return 'text-gray-500'
  }
  
  // Guided wizard step
  const [guidedStep, setGuidedStep] = useState(1)
  const totalGuidedSteps = 4

  // Auto-save data structure - combines all important form data
  const bookBibleFormData = {
    mode,
    bookLengthTier,
    customChapters,
    includeSeriesBible,
    quickStartData,
    guidedData,
    pasteData,
    mustInclude,
    guidedStep
  }

  // Auto-save function for the hook
  const autoSaveFunction = async (data: typeof bookBibleFormData) => {
    // For Book Bible Creator, we mainly want localStorage backup
    // since this is creation flow, not editing existing data
    // The actual creation happens when user submits the form
    return Promise.resolve()
  }

  // Set up auto-save hook
  const autoSave = useAutoSave(bookBibleFormData, autoSaveFunction, {
    key: `book_bible_creator`,
    interval: 60000, // Save every 60 seconds (less frequent for creation flow)
    debounceDelay: 3000, // Wait 3 seconds after typing stops
    enableLocalStorage: true,
    enableFirestore: false // Only local storage for creation flow
  })

  // Set up session recovery
  const sessionRecovery = useSessionRecovery(
    `book_bible_creator`,
    bookBibleFormData,
    (recoveredData) => {
      setMode(recoveredData.mode)
      setBookLengthTier(recoveredData.bookLengthTier)
      setCustomChapters(recoveredData.customChapters)
      setIncludeSeriesBible(recoveredData.includeSeriesBible)
      setQuickStartData(recoveredData.quickStartData)
      setGuidedData(recoveredData.guidedData)
      setPasteData(recoveredData.pasteData)
      setMustInclude(recoveredData.mustInclude)
      setGuidedStep(recoveredData.guidedStep)
    }
  )

  const handleModeSelect = (selectedMode: CreationMode) => {
    setMode(selectedMode)
  }

  const generateFromQuickStart = async (): Promise<string> => {
    // This will be replaced with an AI expansion call in the backend
    const specs = getBookLengthSpecs(bookLengthTier)
    return `# ${quickStartData.title}

## Genre
${quickStartData.genre}

## Book Structure
- **Target Length**: ${specs.word_count_target.toLocaleString()} words
- **Target Chapters**: ${customChapters || specs.chapter_count_target}
- **Words per Chapter**: ${specs.avg_words_per_chapter.toLocaleString()}
- **Book Category**: ${bookLengthTier.replace('_', ' ')}

## Premise
${quickStartData.brief_premise}

## Main Character
${quickStartData.main_character}

## Setting
${quickStartData.setting}

## Central Conflict
${quickStartData.conflict}

${includeSeriesBible ? `## Series Bible Information
This project includes series bible planning for multi-book development.

` : ''}## Must Include Elements
${mustInclude.split('\n').filter(line => line.trim()).map(item => `- ${item.trim()}`).join('\n') || 'None specified'}

## Story Structure
*[This section will be expanded with AI assistance to include detailed plot structure, character development, and world-building based on your inputs]*

## Character Profiles  
*[Detailed character backgrounds and relationships will be generated]*

## World Building
*[Expanded setting details and rules will be created]*

## Themes and Motifs
*[Core themes will be identified and developed]*

## Chapter Outline
*[Detailed chapter-by-chapter breakdown will be generated for ${customChapters || specs.chapter_count_target} chapters]*
`
  }

  const generateFromGuided = async (): Promise<string> => {
    // This will be replaced with an AI expansion call in the backend
    const specs = getBookLengthSpecs(bookLengthTier)
    return `# ${guidedData.title}

## Genre
${guidedData.genre}

## Book Structure
- **Target Length**: ${specs.word_count_target.toLocaleString()} words
- **Target Chapters**: ${customChapters || specs.chapter_count_target}
- **Words per Chapter**: ${specs.avg_words_per_chapter.toLocaleString()}
- **Book Category**: ${bookLengthTier.replace('_', ' ')}

## Premise
${guidedData.premise}

## Main Characters
${guidedData.main_characters}

## Setting
**Time:** ${guidedData.setting_time}
**Place:** ${guidedData.setting_place}

## Central Conflict
${guidedData.central_conflict}

## Themes
${guidedData.themes}

## Target Audience
${guidedData.target_audience}

## Tone
${guidedData.tone}

## Key Plot Points
${guidedData.key_plot_points}

${includeSeriesBible ? `## Series Bible Information
This project includes series bible planning for multi-book development.

` : ''}## Must Include Elements
${mustInclude.split('\n').filter(line => line.trim()).map(item => `- ${item.trim()}`).join('\n') || 'None specified'}

## Detailed Character Development
*[Character profiles will be expanded with backstories, motivations, and arcs based on your character descriptions]*

## World Building
*[Comprehensive setting details, rules, and history will be developed from your time/place specifications]*

## Plot Structure
*[Detailed three-act structure with chapter breakdown will be generated for ${customChapters || specs.chapter_count_target} chapters]*

## Writing Guidelines
*[Style guide will be created based on your specified tone "${guidedData.tone}" and target audience "${guidedData.target_audience}"]*
`
  }

  const handleComplete = async () => {
    // Track if we've successfully kicked off reference generation (i.e. received a projectId)
    let projectInitialized = false // NEW FLAG
    const loadStart = Date.now() // Track when loading began so we can enforce a minimum display time
    console.log('🏗️ BookBibleCreator: handleComplete called, isLoading:', isLoading)
    
    setIsLoading(true)
    console.log('🏗️ BookBibleCreator: setIsLoading(true) called')
    
    try {
      // Validate character count for paste mode
      if (mode === 'paste' && pasteData.content.length > MAX_CHARACTERS) {
        toast({
          title: "Content Too Long",
          description: `Content exceeds maximum of ${MAX_CHARACTERS.toLocaleString()} characters. Please reduce by ${(pasteData.content.length - MAX_CHARACTERS).toLocaleString()} characters.`,
          variant: "destructive"
        })
        setIsLoading(false)
        return
      }
      
      // Validate chapter count
      const lengthSpecs = getBookLengthSpecs(bookLengthTier)
      if (customChapters) {
        if (customChapters < 1 || customChapters > 100) {
          toast({
            title: "Invalid Chapter Count",
            description: "Chapter count must be between 1 and 100.",
            variant: "destructive"
          })
          setIsLoading(false)
          return
        }
        
        if (customChapters < lengthSpecs.chapter_count_min || customChapters > lengthSpecs.chapter_count_max) {
          toast({
            title: "Chapter Count Warning",
            description: `For ${bookLengthTier.replace('_', ' ')} books, recommended range is ${lengthSpecs.chapter_count_min}-${lengthSpecs.chapter_count_max} chapters. Current: ${customChapters}`,
            variant: "destructive"
          })
          setIsLoading(false)
          return
        }
      }

      let content = ''
      let title = ''
      let genre = 'Fiction'

      if (mode === 'quickstart') {
        if (!quickStartData.title?.trim()) {
          toast({
            title: "Title Required",
            description: "Please enter a title for your book.",
            variant: "destructive"
          })
          return
        }
        if (!quickStartData.brief_premise?.trim()) {
          toast({
            title: "Premise Required", 
            description: "Please provide a brief premise for your story.",
            variant: "destructive"
          })
          return
        }
        if (quickStartData.title.length > 100) {
          toast({
            title: "Title Too Long",
            description: "Title must be 100 characters or less.",
            variant: "destructive"
          })
          return
        }
        content = await generateFromQuickStart()
        title = quickStartData.title
        genre = quickStartData.genre
      } else if (mode === 'guided') {
        if (!guidedData.title?.trim()) {
          toast({
            title: "Title Required",
            description: "Please enter a title for your book.",
            variant: "destructive"
          })
          return
        }
        if (!guidedData.premise?.trim()) {
          toast({
            title: "Premise Required",
            description: "Please provide a detailed premise for your story.",
            variant: "destructive"
          })
          return
        }
        if (guidedData.title.length > 100) {
          toast({
            title: "Title Too Long",
            description: "Title must be 100 characters or less.",
            variant: "destructive"
          })
          return
        }
        if (guidedData.premise.length < 50) {
          toast({
            title: "Premise Too Short",
            description: "Please provide more detail in your premise (at least 50 characters).",
            variant: "destructive"
          })
          return
        }
        content = await generateFromGuided()
        title = guidedData.title
        genre = guidedData.genre
      } else if (mode === 'paste') {
        if (!pasteData.title?.trim()) {
          toast({
            title: "Title Required",
            description: "Please enter a title for your book.",
            variant: "destructive"
          })
          return
        }
        if (!pasteData.content?.trim()) {
          toast({
            title: "Content Required",
            description: "Please paste your book bible content.",
            variant: "destructive"
          })
          return
        }
        if (pasteData.title.length > 100) {
          toast({
            title: "Title Too Long",
            description: "Title must be 100 characters or less.",
            variant: "destructive"
          })
          return
        }
        if (pasteData.content.length < 100) {
          toast({
            title: "Content Too Short",
            description: "Please provide more substantial content (at least 100 characters).",
            variant: "destructive"
          })
          return
        }
        content = pasteData.content
        title = pasteData.title
        genre = pasteData.genre
      }

      // Parse must-include sections
      const mustIncludeSections = mustInclude
        .split('\n')
        .map(line => line.trim())
        .filter(line => line.length > 0)

      // Get book length specifications
      const specs = getBookLengthSpecs(bookLengthTier)
      const finalChapterCount = customChapters || specs.chapter_count_target

      const bookBibleData: BookBibleData = {
        title,
        genre,
        target_chapters: finalChapterCount,
        word_count_per_chapter: specs.avg_words_per_chapter,
        content,
        must_include_sections: mustIncludeSections,
        creation_mode: mode,
        source_data: mode === 'quickstart' ? quickStartData : mode === 'guided' ? guidedData : pasteData,
        book_length_tier: bookLengthTier,
        estimated_chapters: finalChapterCount,
        target_word_count: specs.word_count_target,
        include_series_bible: includeSeriesBible
      }

      // Wait for the parent callback (which performs the network request & navigation)
      const createResult = await onComplete(bookBibleData)

      if (!createResult?.success) {
        throw new Error('Project creation failed')
      }

      const { projectId, referencesGenerated } = createResult

      if (!projectId) {
        throw new Error('No project ID returned')
      }

      if (referencesGenerated) {
        // References already generated – we can navigate now after a minimal delay
        await new Promise((resolve) => setTimeout(resolve, 1000))
        setIsLoading(false)
        router.push(`/project/${projectId}/references`)
      } else {
        // Start polling reference generation progress
        setCurrentProjectId(projectId)
        projectInitialized = true // ✅ Mark that the project ID has been set
      }
    } catch (error) {
      console.error('Book Bible creation error:', error)
      toast({
        title: "Looks like we hit a snag",
        description: "We couldn't create your book bible just now. Let's try again!",
        variant: "destructive"
      })
    } finally {
      // Note: don't automatically hide loader here – it will be cleared when the reference job finishes or errors.
      // We only enforce minimum visibility if reference generation finished instantly.
      const MIN_DISPLAY_MS = 5000
      const elapsed = Date.now() - loadStart
      if (elapsed < MIN_DISPLAY_MS) {
        await new Promise((resolve) => setTimeout(resolve, MIN_DISPLAY_MS - elapsed))
      }
      // Keep loader visible until reference generation concludes. It will hide on route change.
      if (!projectInitialized) {
        setIsLoading(false)
      }
    }
  }

  if (!isLoaded) {
    return <div className="animate-pulse">Loading...</div>
  }

  // Mode Selection
  if (mode === 'select') {
    return (
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-4 sm:py-6">
        <div className="text-center mb-6 sm:mb-8">
          <h2 className="text-2xl sm:text-3xl font-bold mb-3 sm:mb-4">Create Your Book Bible</h2>
          <p className="text-sm sm:text-base text-gray-600">Choose how you&apos;d like to get started</p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-6">
          {/* QuickStart Mode */}
          <Card className="cursor-pointer hover:shadow-lg transition-shadow" onClick={() => handleModeSelect('quickstart')}>
            <CardHeader>
              <CardTitle className="text-xl text-blue-600">⚡ QuickStart</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <p className="text-gray-600">Perfect for getting started quickly with basic story elements.</p>
                <ul className="text-sm text-gray-500 space-y-1">
                  <li>• Basic premise and characters</li>
                  <li>• AI expands your ideas</li>
                  <li>• 5-10 minutes to complete</li>
                  <li>• Great for new writers</li>
                </ul>
                <Button className="w-full">Start QuickStart</Button>
              </div>
            </CardContent>
          </Card>

          {/* Guided Wizard Mode */}
          <Card className="cursor-pointer hover:shadow-lg transition-shadow border-blue-200" onClick={() => handleModeSelect('guided')}>
            <CardHeader>
              <CardTitle className="text-xl text-purple-600">🧙‍♂️ Guided Wizard</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <p className="text-gray-600">Comprehensive step-by-step guidance for detailed planning.</p>
                <ul className="text-sm text-gray-500 space-y-1">
                  <li>• Detailed character development</li>
                  <li>• World-building assistance</li>
                  <li>• 15-20 minutes to complete</li>
                  <li>• Best for detailed planners</li>
                </ul>
                <Button className="w-full bg-purple-600 hover:bg-purple-700">Start Guided Wizard</Button>
              </div>
            </CardContent>
          </Card>

          {/* Paste-In Mode */}
          <Card className="cursor-pointer hover:shadow-lg transition-shadow" onClick={() => handleModeSelect('paste')}>
            <CardHeader>
              <CardTitle className="text-xl text-green-600">📋 Paste-In</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <p className="text-gray-600">Already have content? Paste it in and we'll format it properly.</p>
                <ul className="text-sm text-gray-500 space-y-1">
                  <li>• Import existing outlines</li>
                  <li>• Preserve your work</li>
                  <li>• 2-5 minutes to complete</li>
                  <li>• For experienced writers</li>
                </ul>
                <Button className="w-full bg-green-600 hover:bg-green-700">Start Paste-In</Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    )
  }

  // QuickStart Mode
  if (mode === 'quickstart') {
    return (
      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-4 sm:py-6">
        <div className="mb-4 sm:mb-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-4 gap-3 sm:gap-0">
            <h2 className="text-xl sm:text-2xl font-bold">⚡ QuickStart Mode</h2>
            <Button variant="outline" onClick={() => setMode('select')} className="self-start sm:self-auto">← Back</Button>
          </div>
          <p className="text-gray-600">Provide basic information and we'll help expand it into a full book bible.</p>
        </div>

        <Card>
          <CardContent className="p-4 sm:p-6 space-y-4 sm:space-y-6">
            <div className="grid gap-4">
              <div className="space-y-2">
                <Label htmlFor="title">Book Title *</Label>
                <Input
                  id="title"
                  placeholder="Enter your book title"
                  value={quickStartData.title}
                  onChange={(e) => setQuickStartData(prev => ({ ...prev, title: e.target.value }))}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="genre">Genre</Label>
                <select
                  id="genre"
                  value={quickStartData.genre}
                  onChange={(e) => setQuickStartData(prev => ({ ...prev, genre: e.target.value }))}
                  className="w-full p-3 min-h-[44px] border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-base"
                >
                  <option value="Fiction">Fiction</option>
                  <option value="Mystery">Mystery</option>
                  <option value="Romance">Romance</option>
                  <option value="Science Fiction">Science Fiction</option>
                  <option value="Fantasy">Fantasy</option>
                  <option value="Thriller">Thriller</option>
                  <option value="Horror">Horror</option>
                  <option value="Literary">Literary</option>
                  <option value="Young Adult">Young Adult</option>
                  <option value="Non-Fiction">Non-Fiction</option>
                </select>
              </div>

              {/* Book Length Configuration */}
              <div className="border-t pt-4 mt-4">
                <h3 className="text-lg font-semibold mb-4">📏 Book Length & Structure</h3>
                
                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="book-length-tier">Book Length Category</Label>
                    <select
                      id="book-length-tier"
                      value={bookLengthTier}
                      onChange={(e) => {
                        const tier = e.target.value as BookLengthTier
                        setBookLengthTier(tier)
                        setCustomChapters(null) // Reset custom chapters when tier changes
                      }}
                      className="w-full p-3 min-h-[44px] border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-base"
                    >
                      <option value={BookLengthTier.NOVELLA}>📖 Novella (17.5k-40k words, 8-15 chapters)</option>
                      <option value={BookLengthTier.SHORT_NOVEL}>📗 Short Novel (40k-60k words, 15-20 chapters)</option>
                      <option value={BookLengthTier.STANDARD_NOVEL}>📘 Standard Novel (60k-90k words, 20-30 chapters)</option>
                      <option value={BookLengthTier.LONG_NOVEL}>📙 Long Novel (90k-120k words, 25-35 chapters)</option>
                      <option value={BookLengthTier.EPIC_NOVEL}>📚 Epic Novel (120k+ words, 30-50+ chapters)</option>
                    </select>
                  </div>

                  {/* Display current specifications */}
                  <div className="bg-gray-50 p-3 rounded-lg text-sm">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-4">
                      <div className="break-words">
                        <strong>Target Word Count:</strong> {getBookLengthSpecs(bookLengthTier).word_count_target.toLocaleString()} words
                      </div>
                      <div className="break-words">
                        <strong>Suggested Chapters:</strong> {customChapters || getBookLengthSpecs(bookLengthTier).chapter_count_target}
                      </div>
                      <div className="break-words">
                        <strong>Avg Words/Chapter:</strong> {getBookLengthSpecs(bookLengthTier).avg_words_per_chapter.toLocaleString()}
                      </div>
                      <div className="break-words">
                        <strong>Word Range:</strong> {getBookLengthSpecs(bookLengthTier).word_count_min.toLocaleString()}-{getBookLengthSpecs(bookLengthTier).word_count_max.toLocaleString()}
                      </div>
                    </div>
                  </div>

                  {/* Custom chapter count option */}
                  <div className="space-y-2">
                    <Label htmlFor="custom-chapters">Custom Chapter Count (Optional)</Label>
                    <Input
                      id="custom-chapters"
                      type="number"
                      placeholder={`Leave blank for default (${getBookLengthSpecs(bookLengthTier).chapter_count_target})`}
                      value={customChapters || ''}
                      onChange={(e) => setCustomChapters(e.target.value ? parseInt(e.target.value) : null)}
                      min={getBookLengthSpecs(bookLengthTier).chapter_count_min}
                      max={getBookLengthSpecs(bookLengthTier).chapter_count_max}
                    />
                    <p className="text-xs text-gray-500">
                      Recommended range: {getBookLengthSpecs(bookLengthTier).chapter_count_min}-{getBookLengthSpecs(bookLengthTier).chapter_count_max} chapters
                    </p>
                  </div>

                  {/* Series Bible Option */}
                  <div className="flex items-center space-x-2">
                    <input
                      type="checkbox"
                      id="include-series-bible"
                      checked={includeSeriesBible}
                      onChange={(e) => setIncludeSeriesBible(e.target.checked)}
                      className="w-4 h-4 text-blue-600 rounded focus:ring-blue-500"
                    />
                    <Label htmlFor="include-series-bible" className="text-sm">
                      Include Series Bible (for multi-book projects)
                    </Label>
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="premise">Brief Premise *</Label>
                <Textarea
                  id="premise"
                  placeholder="In 2-3 sentences, what is your story about?"
                  value={quickStartData.brief_premise}
                  onChange={(e) => setQuickStartData(prev => ({ ...prev, brief_premise: e.target.value }))}
                  rows={3}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="character">Main Character</Label>
                <Input
                  id="character"
                  placeholder="Who is your protagonist?"
                  value={quickStartData.main_character}
                  onChange={(e) => setQuickStartData(prev => ({ ...prev, main_character: e.target.value }))}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="setting">Setting</Label>
                <Input
                  id="setting"
                  placeholder="Where and when does your story take place?"
                  value={quickStartData.setting}
                  onChange={(e) => setQuickStartData(prev => ({ ...prev, setting: e.target.value }))}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="conflict">Central Conflict</Label>
                <Textarea
                  id="conflict"
                  placeholder="What problem or challenge drives your story?"
                  value={quickStartData.conflict}
                  onChange={(e) => setQuickStartData(prev => ({ ...prev, conflict: e.target.value }))}
                  rows={2}
                />
              </div>

              {/* Must Include Section */}
              <div className="border-t pt-4 space-y-2">
                <Label htmlFor="must-include">Must Include Elements (Optional)</Label>
                <Textarea
                  id="must-include"
                  placeholder="List specific scenes, characters, or plot points that must be included (one per line)"
                  value={mustInclude}
                  onChange={(e) => setMustInclude(e.target.value)}
                  rows={4}
                />
                <p className="text-sm text-gray-500">
                  Add any specific elements you want to ensure are included in your story
                </p>
              </div>
            </div>

            <div className="flex flex-col sm:flex-row justify-end gap-3 sm:gap-2">
              <Button variant="outline" onClick={() => setMode('select')} className="min-h-[44px] w-full sm:w-auto">
                Cancel
              </Button>
              <Button onClick={handleComplete} disabled={isLoading} className="min-h-[44px] w-full sm:w-auto">
                {isLoading ? 'Generating...' : 'Create Book Bible'}
              </Button>
            </div>
          </CardContent>
        </Card>

        {(() => {
          // Side-effectful: wrap in setTimeout to avoid render strict-mode double-call
          if (isLoading) {
            setTimeout(() => {
              GlobalLoader.show({
                title: 'Creating Book Bible',
                stage: loaderStage,
                progress: loaderProgressValue,
                showProgress: true,
                size: 'md',
                fullScreen: true,
                customMessages: [
                  '🖋️ Crafting your story foundation...',
                  '📚 Organizing narrative elements...',
                  '🎭 Developing character frameworks...',
                  '🗺️ Mapping plot structures...',
                  '✨ Weaving creative magic...',
                  '🔮 Consulting the storytelling muses...',
                  "📖 Building your writer's bible...",
                  '🎨 Painting your story landscape...',
                  '🌟 Aligning creative constellations...',
                  '🎪 Teaching your story to dance...'
                ],
                timeoutMs: 600000,
              })
            }, 0)
          } else {
            setTimeout(() => GlobalLoader.hide(), 0)
          }
          return null
        })()}
      </div>
    )
  }

  // Guided Wizard Mode
  if (mode === 'guided') {
    return (
      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-4 sm:py-6">
        <div className="mb-4 sm:mb-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-4 gap-3 sm:gap-0">
            <h2 className="text-xl sm:text-2xl font-bold">🧙‍♂️ Guided Wizard</h2>
            <Button variant="outline" onClick={() => setMode('select')} className="self-start sm:self-auto">← Back</Button>
          </div>
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-2 gap-1 sm:gap-0">
            <p className="text-sm sm:text-base text-gray-600">Step-by-step comprehensive book planning</p>
            <span className="text-sm text-gray-500">Step {guidedStep} of {totalGuidedSteps}</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div 
              className="bg-purple-600 h-2 rounded-full transition-all duration-300"
              style={{ width: `${(guidedStep / totalGuidedSteps) * 100}%` }}
            />
          </div>
        </div>

        <Card>
          <CardContent className="p-4 sm:p-6">
            {/* Step 1: Basic Info */}
            {guidedStep === 1 && (
              <div className="space-y-6">
                <div className="text-center">
                  <h3 className="text-xl font-semibold mb-2">Basic Information</h3>
                  <p className="text-gray-600">Let's start with the fundamentals of your story</p>
                </div>
                
                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="guided-title">Book Title *</Label>
                    <Input
                      id="guided-title"
                      placeholder="Enter your book title"
                      value={guidedData.title}
                      onChange={(e) => setGuidedData(prev => ({ ...prev, title: e.target.value }))}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="guided-genre">Genre *</Label>
                    <select
                      id="guided-genre"
                      value={guidedData.genre}
                      onChange={(e) => setGuidedData(prev => ({ ...prev, genre: e.target.value }))}
                      className="w-full p-3 min-h-[44px] border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-base"
                    >
                      <option value="Fiction">Fiction</option>
                      <option value="Mystery">Mystery</option>
                      <option value="Romance">Romance</option>
                      <option value="Science Fiction">Science Fiction</option>
                      <option value="Fantasy">Fantasy</option>
                      <option value="Thriller">Thriller</option>
                      <option value="Horror">Horror</option>
                      <option value="Literary">Literary</option>
                      <option value="Young Adult">Young Adult</option>
                      <option value="Non-Fiction">Non-Fiction</option>
                    </select>
                  </div>

                  {/* Book Length Configuration */}
                  <div className="border-t pt-4 mt-4">
                    <h4 className="text-md font-semibold mb-3">📏 Book Length & Structure</h4>
                    
                    <div className="space-y-4">
                      <div className="space-y-2">
                        <Label htmlFor="guided-book-length-tier">Book Length Category</Label>
                        <select
                          id="guided-book-length-tier"
                          value={bookLengthTier}
                          onChange={(e) => {
                            const tier = e.target.value as BookLengthTier
                            setBookLengthTier(tier)
                            setCustomChapters(null)
                          }}
                          className="w-full p-3 min-h-[44px] border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-base"
                        >
                          <option value={BookLengthTier.NOVELLA}>📖 Novella (17.5k-40k words, 8-15 chapters)</option>
                          <option value={BookLengthTier.SHORT_NOVEL}>📗 Short Novel (40k-60k words, 15-20 chapters)</option>
                          <option value={BookLengthTier.STANDARD_NOVEL}>📘 Standard Novel (60k-90k words, 20-30 chapters)</option>
                          <option value={BookLengthTier.LONG_NOVEL}>📙 Long Novel (90k-120k words, 25-35 chapters)</option>
                          <option value={BookLengthTier.EPIC_NOVEL}>📚 Epic Novel (120k+ words, 30-50+ chapters)</option>
                        </select>
                      </div>

                      <div className="bg-gray-50 p-3 rounded-lg text-sm">
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-3">
                          <div className="break-words"><strong>Target:</strong> {getBookLengthSpecs(bookLengthTier).word_count_target.toLocaleString()} words</div>
                          <div className="break-words"><strong>Chapters:</strong> {customChapters || getBookLengthSpecs(bookLengthTier).chapter_count_target}</div>
                        </div>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="guided-custom-chapters">Custom Chapter Count (Optional)</Label>
                        <Input
                          id="guided-custom-chapters"
                          type="number"
                          placeholder={`Default: ${getBookLengthSpecs(bookLengthTier).chapter_count_target}`}
                          value={customChapters || ''}
                          onChange={(e) => setCustomChapters(e.target.value ? parseInt(e.target.value) : null)}
                          min={getBookLengthSpecs(bookLengthTier).chapter_count_min}
                          max={getBookLengthSpecs(bookLengthTier).chapter_count_max}
                        />
                      </div>

                      <div className="flex items-center space-x-2">
                        <input
                          type="checkbox"
                          id="guided-include-series-bible"
                          checked={includeSeriesBible}
                          onChange={(e) => setIncludeSeriesBible(e.target.checked)}
                          className="w-4 h-4 text-blue-600 rounded focus:ring-blue-500"
                        />
                        <Label htmlFor="guided-include-series-bible" className="text-sm">
                          Include Series Bible (for multi-book projects)
                        </Label>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="guided-premise">Detailed Premise *</Label>
                    <Textarea
                      id="guided-premise"
                      placeholder="Describe your story in detail. What happens? Why is it compelling?"
                      value={guidedData.premise}
                      onChange={(e) => setGuidedData(prev => ({ ...prev, premise: e.target.value }))}
                      rows={4}
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Step 2: Characters & Setting */}
            {guidedStep === 2 && (
              <div className="space-y-6">
                <div className="text-center">
                  <h3 className="text-xl font-semibold mb-2">Characters & Setting</h3>
                  <p className="text-gray-600">Who are your characters and where does your story take place?</p>
                </div>
                
                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="guided-characters">Main Characters</Label>
                    <Textarea
                      id="guided-characters"
                      placeholder="Describe your main characters, their personalities, and relationships"
                      value={guidedData.main_characters}
                      onChange={(e) => setGuidedData(prev => ({ ...prev, main_characters: e.target.value }))}
                      rows={3}
                    />
                  </div>

                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="guided-time">Time Period</Label>
                      <Input
                        id="guided-time"
                        placeholder="When does your story take place?"
                        value={guidedData.setting_time}
                        onChange={(e) => setGuidedData(prev => ({ ...prev, setting_time: e.target.value }))}
                      />
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="guided-place">Location</Label>
                      <Input
                        id="guided-place"
                        placeholder="Where does your story take place?"
                        value={guidedData.setting_place}
                        onChange={(e) => setGuidedData(prev => ({ ...prev, setting_place: e.target.value }))}
                      />
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Step 3: Story Elements */}
            {guidedStep === 3 && (
              <div className="space-y-6">
                <div className="text-center">
                  <h3 className="text-xl font-semibold mb-2">Story Elements</h3>
                  <p className="text-gray-600">What drives your story and what themes will you explore?</p>
                </div>
                
                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="guided-conflict">Central Conflict</Label>
                    <Textarea
                      id="guided-conflict"
                      placeholder="What is the main problem or challenge in your story?"
                      value={guidedData.central_conflict}
                      onChange={(e) => setGuidedData(prev => ({ ...prev, central_conflict: e.target.value }))}
                      rows={3}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="guided-themes">Themes</Label>
                    <Textarea
                      id="guided-themes"
                      placeholder="What themes or messages will your story explore?"
                      value={guidedData.themes}
                      onChange={(e) => setGuidedData(prev => ({ ...prev, themes: e.target.value }))}
                      rows={2}
                    />
                  </div>

                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="guided-audience">Target Audience</Label>
                      <Input
                        id="guided-audience"
                        placeholder="Who is your target reader?"
                        value={guidedData.target_audience}
                        onChange={(e) => setGuidedData(prev => ({ ...prev, target_audience: e.target.value }))}
                      />
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="guided-tone">Tone</Label>
                      <Input
                        id="guided-tone"
                        placeholder="What's the overall mood/tone?"
                        value={guidedData.tone}
                        onChange={(e) => setGuidedData(prev => ({ ...prev, tone: e.target.value }))}
                      />
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Step 4: Plot & Must Include */}
            {guidedStep === 4 && (
              <div className="space-y-6">
                <div className="text-center">
                  <h3 className="text-xl font-semibold mb-2">Plot Structure & Must-Include</h3>
                  <p className="text-gray-600">Map out key plot points and essential elements</p>
                </div>
                
                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="guided-plot">Key Plot Points</Label>
                    <Textarea
                      id="guided-plot"
                      placeholder="Outline the major events and turning points in your story"
                      value={guidedData.key_plot_points}
                      onChange={(e) => setGuidedData(prev => ({ ...prev, key_plot_points: e.target.value }))}
                      rows={4}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="guided-must-include">Must Include Elements</Label>
                    <Textarea
                      id="guided-must-include"
                      placeholder="List specific scenes, characters, or plot points that must be included (one per line)"
                      value={mustInclude}
                      onChange={(e) => setMustInclude(e.target.value)}
                      rows={4}
                    />
                    <p className="text-sm text-gray-500">
                      Add any specific elements you want to ensure are included in your story
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Navigation */}
            <div className="flex flex-col sm:flex-row justify-between mt-6 sm:mt-8 pt-4 sm:pt-6 border-t gap-3 sm:gap-0">
              <Button
                variant="outline"
                onClick={() => setGuidedStep(Math.max(1, guidedStep - 1))}
                disabled={guidedStep === 1}
                className="min-h-[44px] w-full sm:w-auto order-2 sm:order-1"
              >
                Previous
              </Button>

              {guidedStep < totalGuidedSteps ? (
                <Button onClick={() => setGuidedStep(guidedStep + 1)} className="min-h-[44px] w-full sm:w-auto order-1 sm:order-2">
                  Next
                </Button>
              ) : (
                <Button onClick={handleComplete} disabled={isLoading} className="min-h-[44px] w-full sm:w-auto order-1 sm:order-2">
                  {isLoading ? 'Generating...' : 'Create Book Bible'}
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
        {/* Creative Loader for Guided Mode */}
        <CreativeLoader
          isVisible={isLoading}
          progress={loaderProgressValue}
          stage={loaderStage}
          customMessages={[
            "🧙‍♂️ Summoning story wizards...",
            "📚 Gathering arcane plot scrolls...",
            "🎭 Sculpting intricate characters...",
            "🌌 Expanding narrative cosmos...",
            "✨ Infusing pages with magic...",
            "🔮 Probing story possibilities...",
            "🗺️ Charting epic journeys..."
          ]}
          showProgress={true}
          size="md"
          timeoutMs={600000}
          fullScreen
        />
      </div>
    )
  }

  // Paste-In Mode
  if (mode === 'paste') {
    return (
      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-4 sm:py-6">
        <div className="mb-4 sm:mb-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-4 gap-3 sm:gap-0">
            <h2 className="text-xl sm:text-2xl font-bold">📋 Paste-In Mode</h2>
            <Button variant="outline" onClick={() => setMode('select')} className="self-start sm:self-auto">← Back</Button>
          </div>
          <p className="text-gray-600">Already have content? Paste it here and we'll format it as a book bible.</p>
        </div>

        <Card>
          <CardContent className="p-4 sm:p-6 space-y-4 sm:space-y-6">
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="paste-title">Book Title *</Label>
                <Input
                  id="paste-title"
                  placeholder="Enter your book title"
                  value={pasteData.title}
                  onChange={(e) => setPasteData(prev => ({ ...prev, title: e.target.value }))}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="paste-genre">Genre</Label>
                <select
                  id="paste-genre"
                  value={pasteData.genre}
                  onChange={(e) => setPasteData(prev => ({ ...prev, genre: e.target.value }))}
                  className="w-full p-3 min-h-[44px] border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-base"
                >
                  <option value="Fiction">Fiction</option>
                  <option value="Mystery">Mystery</option>
                  <option value="Romance">Romance</option>
                  <option value="Science Fiction">Science Fiction</option>
                  <option value="Fantasy">Fantasy</option>
                  <option value="Thriller">Thriller</option>
                  <option value="Horror">Horror</option>
                  <option value="Literary">Literary</option>
                  <option value="Young Adult">Young Adult</option>
                  <option value="Non-Fiction">Non-Fiction</option>
                </select>
              </div>

              {/* Book Length Configuration */}
              <div className="border-t pt-4 mt-4">
                <h3 className="text-lg font-semibold mb-4">📏 Book Length & Structure</h3>
                
                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="paste-book-length-tier">Book Length Category</Label>
                    <select
                      id="paste-book-length-tier"
                      value={bookLengthTier}
                      onChange={(e) => {
                        const tier = e.target.value as BookLengthTier
                        setBookLengthTier(tier)
                        setCustomChapters(null)
                      }}
                      className="w-full p-3 min-h-[44px] border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-base"
                    >
                      <option value={BookLengthTier.NOVELLA}>📖 Novella (17.5k-40k words, 8-15 chapters)</option>
                      <option value={BookLengthTier.SHORT_NOVEL}>📗 Short Novel (40k-60k words, 15-20 chapters)</option>
                      <option value={BookLengthTier.STANDARD_NOVEL}>📘 Standard Novel (60k-90k words, 20-30 chapters)</option>
                      <option value={BookLengthTier.LONG_NOVEL}>📙 Long Novel (90k-120k words, 25-35 chapters)</option>
                      <option value={BookLengthTier.EPIC_NOVEL}>📚 Epic Novel (120k+ words, 30-50+ chapters)</option>
                    </select>
                  </div>

                  <div className="bg-gray-50 p-3 rounded-lg text-sm">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-4">
                      <div className="break-words"><strong>Target:</strong> {getBookLengthSpecs(bookLengthTier).word_count_target.toLocaleString()} words</div>
                      <div className="break-words"><strong>Chapters:</strong> {customChapters || getBookLengthSpecs(bookLengthTier).chapter_count_target}</div>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="paste-custom-chapters">Custom Chapter Count (Optional)</Label>
                    <Input
                      id="paste-custom-chapters"
                      type="number"
                      placeholder={`Default: ${getBookLengthSpecs(bookLengthTier).chapter_count_target}`}
                      value={customChapters || ''}
                      onChange={(e) => setCustomChapters(e.target.value ? parseInt(e.target.value) : null)}
                      min={getBookLengthSpecs(bookLengthTier).chapter_count_min}
                      max={getBookLengthSpecs(bookLengthTier).chapter_count_max}
                    />
                  </div>

                  <div className="flex items-center space-x-2">
                    <input
                      type="checkbox"
                      id="paste-include-series-bible"
                      checked={includeSeriesBible}
                      onChange={(e) => setIncludeSeriesBible(e.target.checked)}
                      className="w-4 h-4 text-blue-600 rounded focus:ring-blue-500"
                    />
                    <Label htmlFor="paste-include-series-bible" className="text-sm">
                      Include Series Bible (for multi-book projects)
                    </Label>
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex justify-between items-center">
                  <Label htmlFor="paste-content">Book Bible Content *</Label>
                  <div className={`text-sm ${getCharCountColor()}`}>
                    {currentCharCount.toLocaleString()} / {MAX_CHARACTERS.toLocaleString()} characters
                    {isNearLimit && !isOverLimit && (
                      <span className="ml-2 text-orange-600">({remainingChars.toLocaleString()} remaining)</span>
                    )}
                    {isOverLimit && (
                      <span className="ml-2 text-red-600 font-medium">Limit exceeded!</span>
                    )}
                  </div>
                </div>
                <Textarea
                  id="paste-content"
                  placeholder="Paste your existing outline, character descriptions, plot summary, or any other book-related content here..."
                  value={pasteData.content}
                  onChange={(e) => setPasteData(prev => ({ ...prev, content: e.target.value }))}
                  rows={15}
                  className={`font-mono text-sm ${isOverLimit ? 'border-red-300 focus:border-red-500 focus:ring-red-500' : ''}`}
                />
                {isNearLimit && (
                  <div className={`text-sm ${isOverLimit ? 'text-red-600' : 'text-orange-600'} bg-orange-50 border border-orange-200 rounded-md p-3`}>
                    {isOverLimit ? (
                      <>
                        <strong>⚠️ Content too long!</strong> Please reduce your content by {Math.abs(remainingChars).toLocaleString()} characters to continue.
                      </>
                    ) : (
                      <>
                        <strong>⚠️ Approaching limit!</strong> You have {remainingChars.toLocaleString()} characters remaining.
                      </>
                    )}
                  </div>
                )}
                <p className="text-sm text-gray-500">
                  You can paste outlines, character descriptions, plot summaries, or any markdown/text content
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="paste-must-include">Additional Must Include Elements (Optional)</Label>
                <Textarea
                  id="paste-must-include"
                  placeholder="List any additional specific elements that must be included (one per line)"
                  value={mustInclude}
                  onChange={(e) => setMustInclude(e.target.value)}
                  rows={3}
                />
              </div>
            </div>

            <div className="flex flex-col sm:flex-row justify-end gap-3 sm:gap-2">
              <Button variant="outline" onClick={() => setMode('select')} className="min-h-[44px] w-full sm:w-auto">
                Cancel
              </Button>
              <Button 
                onClick={handleComplete} 
                disabled={isLoading || isOverLimit} 
                className={`min-h-[44px] w-full sm:w-auto ${isOverLimit ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                {isLoading ? 'Processing...' : 'Create Book Bible'}
              </Button>
            </div>
          </CardContent>
        </Card>
        {/* Creative Loader for Paste-In Mode */}
        <CreativeLoader
          isVisible={isLoading}
          progress={loaderProgressValue}
          stage={loaderStage}
          customMessages={[
            "📋 Integrating your content...",
            "🖋️ Formatting book bible sections...",
            "🔍 Parsing narrative elements...",
            "✨ Enhancing storytelling magic...",
            "🎨 Harmonizing style and tone...",
            "📚 Building reference library..."
          ]}
          showProgress={true}
          size="md"
          timeoutMs={600000}
          fullScreen
        />
      </div>
    )
  }

  return (
    <>
      {/* Session Recovery Prompt */}
      <SessionRecoveryPrompt
        isOpen={sessionRecovery.hasRecoverableData}
        onAccept={sessionRecovery.acceptRecovery}
        onReject={sessionRecovery.rejectRecovery}
        dataPreview={sessionRecovery.recoveredData?.quickStartData?.title || sessionRecovery.recoveredData?.guidedData?.title || sessionRecovery.recoveredData?.pasteData?.title}
      />
    </>
  )
}

export { BookBibleCreator }
export default BookBibleCreator 