'use client'

import React, { useState, useEffect, useRef } from 'react'
import { useForm } from 'react-hook-form'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { CreativeLoader } from '@/components/ui/CreativeLoader'
import { GlobalLoader } from '@/stores/useGlobalLoaderStore'
import { Book, Download, FileText, Settings, Eye, CheckCircle, Package, Image, Headphones, Play, Pause, Search, Plus, Trash2, Volume2 } from 'lucide-react'
import { usePublishJob } from '@/hooks/usePublishJob'
import {
  useAudiobookJob,
  useAudiobookVoices,
  useAudiobookEstimate,
  type PronunciationEntry,
  type AbbreviationSuggestion,
} from '@/hooks/useAudiobookJob'
import { Project } from '@/types/project'
import { useAuthToken } from '@/lib/auth'
import { fetchApi } from '@/lib/api-client'

interface PublishingSuiteProps {
  projectId: string
  project: Project
}

interface PublishFormData {
  title: string
  author: string
  publisher?: string
  isbn?: string
  date?: string
  rights: string
  
  // Optional sections
  dedication?: string
  acknowledgments?: string
  foreword?: string
  preface?: string
  epilogue?: string
  about_author?: string
  
  // Reader engagement
  call_to_action?: string
  other_books?: string
  connect_author?: string
  book_club_questions?: string
  
  // Publishing options
  formats: string[]
  use_existing_cover: boolean
  include_toc: boolean
  include_kdp_kit: boolean

  // KDP publishing kit
  kdp_description?: string
  kdp_keywords?: string
  kdp_categories?: string
  kdp_subtitle?: string
  kdp_series_name?: string
  kdp_series_number?: string
  kdp_language?: string
  kdp_primary_marketplace?: string
  kdp_author_bio?: string
  kdp_contributors?: string
  kdp_edition?: string
  kdp_reading_age_min?: string
  kdp_reading_age_max?: string
  kdp_imprint?: string
  kdp_pricing?: string
  kdp_adult_content: boolean
  kdp_drm: boolean
  kdp_select?: string
  kdp_territories: string
  kdp_publishing_rights: string
}

export default function PublishingSuite({ projectId, project }: PublishingSuiteProps) {
  const [activeTab, setActiveTab] = useState('details')
  const { startPublishJob, jobStatus, isLoading, error, downloadUrls } = usePublishJob()
  const { getAuthHeaders } = useAuthToken()

  const form = useForm<PublishFormData>({
    defaultValues: {
      title: project.metadata?.title || '',
      author: '', // Author will need to be filled in by user
      publisher: '',
      isbn: '',
      date: new Date().getFullYear().toString(),
      rights: 'All rights reserved.',
      dedication: '',
      acknowledgments: '',
      foreword: '',
      preface: '',
      epilogue: '',
      about_author: '',
      call_to_action: '',
      other_books: '',
      connect_author: '',
      book_club_questions: '',
      formats: ['epub', 'pdf'],
      use_existing_cover: !!project.cover_art?.image_url,
      include_toc: true,
      include_kdp_kit: true,
      kdp_description: '',
      kdp_keywords: '',
      kdp_categories: '',
      kdp_subtitle: '',
      kdp_series_name: '',
      kdp_series_number: '',
      kdp_language: '',
      kdp_primary_marketplace: '',
      kdp_author_bio: '',
      kdp_contributors: '',
      kdp_edition: '',
      kdp_reading_age_min: '',
      kdp_reading_age_max: '',
      kdp_imprint: '',
      kdp_pricing: '',
      kdp_adult_content: false,
      kdp_drm: true,
      kdp_select: '',
      kdp_territories: 'worldwide',
      kdp_publishing_rights: 'own_copyright'
    }
  })

  const handlePublish = async (data: PublishFormData) => {
    try {
      const missingFields: Array<{ name: keyof PublishFormData; message: string }> = []
      if (!data.title?.trim()) {
        missingFields.push({ name: 'title', message: 'Title is required' })
      }
      if (!data.author?.trim()) {
        missingFields.push({ name: 'author', message: 'Author is required' })
      }
      if (missingFields.length > 0) {
        missingFields.forEach((field) => {
          form.setError(field.name, { type: 'manual', message: field.message })
        })
        return
      }

      const kdpKeywords = (data.kdp_keywords || '').split(/[,;\n]/).map((k) => k.trim()).filter(Boolean)
      const kdpCategories = (data.kdp_categories || '').split(/[,;\n]/).map((c) => c.trim()).filter(Boolean)

      GlobalLoader.show({
        title: 'Publishing Your Book',
        stage: 'Preparing content...',
        progress: 0,
        showProgress: true,
        safeToLeave: true,
        canMinimize: true,
        customMessages: [
          'Collecting chapters...',
          'Building book structure...',
          'Creating table of contents...',
          'Integrating cover art...',
          'Generating EPUB and PDF...',
          'Uploading files...',
        ],
        timeoutMs: 1800000,
      })
      await startPublishJob(projectId, {
        title: data.title,
        author: data.author,
        publisher: data.publisher,
        isbn: data.isbn,
        date: data.date,
        rights: data.rights,
        dedication: data.dedication,
        acknowledgments: data.acknowledgments,
        foreword: data.foreword,
        preface: data.preface,
        epilogue: data.epilogue,
        about_author: data.about_author,
        call_to_action: data.call_to_action,
        other_books: data.other_books,
        connect_author: data.connect_author,
        book_club_questions: data.book_club_questions,
        formats: data.formats,
        use_existing_cover: data.use_existing_cover,
        include_toc: data.include_toc,
        include_kdp_kit: data.include_kdp_kit,
        kdp_description: data.kdp_description?.trim() || undefined,
        kdp_keywords: kdpKeywords,
        kdp_categories: kdpCategories,
        kdp_subtitle: data.kdp_subtitle?.trim() || undefined,
        kdp_series_name: data.kdp_series_name?.trim() || undefined,
        kdp_series_number: data.kdp_series_number?.trim() || undefined,
        kdp_language: data.kdp_language?.trim() || undefined,
        kdp_primary_marketplace: data.kdp_primary_marketplace?.trim() || undefined,
        kdp_author_bio: data.kdp_author_bio?.trim() || undefined,
        kdp_contributors: data.kdp_contributors?.trim() || undefined,
        kdp_edition: data.kdp_edition?.trim() || undefined,
        kdp_reading_age_min: data.kdp_reading_age_min ? parseInt(data.kdp_reading_age_min) : undefined,
        kdp_reading_age_max: data.kdp_reading_age_max ? parseInt(data.kdp_reading_age_max) : undefined,
        kdp_imprint: data.kdp_imprint?.trim() || undefined,
        kdp_pricing: data.kdp_pricing?.trim() || undefined,
        kdp_adult_content: data.kdp_adult_content,
        kdp_drm: data.kdp_drm,
        kdp_select: data.kdp_select === 'yes' ? true : data.kdp_select === 'no' ? false : undefined,
        kdp_territories: data.kdp_territories,
        kdp_publishing_rights: data.kdp_publishing_rights
      })
    } catch (err) {
      console.error('Failed to start publish job:', err)
    }
  }

  const [projectStats, setProjectStats] = useState({ chapterCount: 0, wordCount: 0 })
  const [coverArtUrl, setCoverArtUrl] = useState<string | null>(project.cover_art?.image_url || null)
  const hasCoverArt = !!coverArtUrl

  useEffect(() => {
    const fetchMountData = async () => {
      const authHeaders = await getAuthHeaders()

      const [chaptersRes, coverRes] = await Promise.all([
        fetchApi(`/api/v2/projects/${projectId}/chapters`, { headers: authHeaders }).catch(() => null),
        fetch(`/api/cover-art/${projectId}`, { headers: authHeaders }).catch(() => null),
      ])

      if (chaptersRes?.ok) {
        const data = await chaptersRes.json()
        const chapters = data.chapters || []
        setProjectStats({
          chapterCount: chapters.length,
          wordCount: chapters.reduce((total: number, ch: any) => total + (ch.word_count || ch.metadata?.word_count || 0), 0),
        })
      } else {
        setProjectStats({
          chapterCount: project.progress?.chapters_completed || 0,
          wordCount: project.progress?.current_word_count || 0,
        })
      }

      if (coverRes?.ok) {
        try {
          const coverData = await coverRes.json()
          if (coverData?.status === 'completed' && coverData?.image_url) {
            setCoverArtUrl(coverData.image_url)
            form.setValue('use_existing_cover', true)
          }
        } catch {}
      }
    }

    fetchMountData()
  }, [projectId])

  const { chapterCount, wordCount } = projectStats

  // Sync global loader with job progress
  const jobProgressPct = jobStatus?.progress?.progress_percentage
  const jobProgressStep = jobStatus?.progress?.current_step
  useEffect(() => {
    if (jobProgressPct != null) {
      GlobalLoader.update({
        stage: jobProgressStep || 'Publishing...',
        progress: jobProgressPct,
      })
    }
  }, [jobProgressPct, jobProgressStep])

  // Show progress if job is running
  if (isLoading || (jobStatus && !['completed', 'failed'].includes(jobStatus.status))) {
    return (
      <div className="space-y-6" data-cy="publishing-progress">
        <div className="text-center">
          <h3 className="text-xl font-semibold mb-2">Publishing Your Book</h3>
          <p className="text-muted-foreground mb-4">
            Converting your chapters to professional formats...
          </p>
        </div>
        
        {jobStatus && (
          <div className="bg-muted/50 rounded-lg p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium">Progress</span>
              <span className="text-sm text-muted-foreground">
                {Math.round(jobStatus.progress?.progress_percentage || 0)}%
              </span>
            </div>
            <div className="w-full bg-background rounded-full h-2">
              <div 
                className="bg-primary h-2 rounded-full transition-all duration-300"
                style={{ width: `${jobStatus.progress?.progress_percentage || 0}%` }}
              />
            </div>
            <p className="text-sm text-muted-foreground mt-2">
              {jobStatus.progress?.current_step || 'Processing...'}
            </p>
          </div>
        )}
      </div>
    )
  }

  // Show results if completed
  if (jobStatus?.status === 'completed' && downloadUrls && (downloadUrls.epub || downloadUrls.pdf || downloadUrls.html || downloadUrls.kdp_kit || downloadUrls.kdp_package)) {
    GlobalLoader.hide()
    return (
      <div className="space-y-6" data-cy="publish-success">
        <div className="text-center">
          <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-4" />
          <h3 className="text-xl font-semibold mb-2">Book Export Complete!</h3>
          <p className="text-gray-500">
            Your book has been converted to professional formats and is ready for download.
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Download Your Book</CardTitle>
            <CardDescription>
              Professional formats ready for distribution
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {downloadUrls.epub && (
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-3 border rounded-lg">
                <div className="flex items-center gap-3">
                  <Book className="h-5 w-5" />
                  <div>
                    <p className="font-medium">EPUB Format</p>
                    <p className="text-sm text-muted-foreground">Kindle and e-reader compatible</p>
                  </div>
                </div>
                <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2">
                  <Button asChild variant="outline">
                    <a href={downloadUrls.epub} download data-cy="download-epub">
                      <Download className="h-4 w-4 mr-2" />
                      Download
                    </a>
                  </Button>
                  <Button
                    variant="default"
                    onClick={async () => {
                      try {
                        if (!navigator.share || !('canShare' in navigator)) {
                          // Fallback: just open the file in a new tab
                          window.open(downloadUrls.epub as string, '_blank')
                          return
                        }
                        const res = await fetch(downloadUrls.epub as string)
                        const blob = await res.blob()
                        const file = new File([blob], `${(project.metadata?.title || 'book').replace(/\s+/g,'-')}.epub`, { type: 'application/epub+zip' })
                        // Check share capability with file
                        // @ts-ignore
                        if (navigator.canShare && !navigator.canShare({ files: [file] })) {
                          window.open(downloadUrls.epub as string, '_blank')
                          return
                        }
                        await navigator.share({
                          files: [file],
                          title: project.metadata?.title || 'EPUB',
                          text: 'Share to Kindle via the system share sheet'
                        })
                      } catch (err) {
                        console.error('Web Share failed', err)
                        window.open(downloadUrls.epub as string, '_blank')
                      }
                    }}
                    data-cy="share-epub"
                  >
                    Share to Kindle
                  </Button>
                </div>
              </div>
            )}
            
            {downloadUrls.pdf && (
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-3 border rounded-lg">
                <div className="flex items-center gap-3">
                  <FileText className="h-5 w-5" />
                  <div>
                    <p className="font-medium">PDF Format</p>
                    <p className="text-sm text-muted-foreground">Print-ready, Lulu.com compatible</p>
                  </div>
                </div>
                <Button asChild variant="outline">
                  <a href={downloadUrls.pdf} download data-cy="download-pdf">
                    <Download className="h-4 w-4 mr-2" />
                    Download
                  </a>
                </Button>
              </div>
            )}

            {downloadUrls.kdp_package && (
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-3 border rounded-lg bg-amber-50/50">
                <div className="flex items-center gap-3">
                  <Package className="h-5 w-5" />
                  <div>
                    <p className="font-medium">KDP Publishing Package</p>
                    <p className="text-sm text-muted-foreground">Complete ZIP with EPUB, PDF, cover art, and KDP metadata</p>
                  </div>
                </div>
                <Button asChild variant="default">
                  <a href={downloadUrls.kdp_package} download data-cy="download-kdp-package">
                    <Download className="h-4 w-4 mr-2" />
                    Download Package
                  </a>
                </Button>
              </div>
            )}

            {downloadUrls.kdp_kit && (
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-3 border rounded-lg">
                <div className="flex items-center gap-3">
                  <FileText className="h-5 w-5" />
                  <div>
                    <p className="font-medium">KDP Publishing Kit</p>
                    <p className="text-sm text-muted-foreground">Copy-ready KDP metadata and steps</p>
                  </div>
                </div>
                <Button asChild variant="outline">
                  <a href={downloadUrls.kdp_kit} download data-cy="download-kdp-kit">
                    <Download className="h-4 w-4 mr-2" />
                    Download
                  </a>
                </Button>
              </div>
            )}

            {downloadUrls.cover_art && (
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-3 border rounded-lg">
                <div className="flex items-center gap-3">
                  <Image className="h-5 w-5" />
                  <div>
                    <p className="font-medium">Cover Art (KDP Specs)</p>
                    <p className="text-sm text-muted-foreground">1600x2560 JPEG, 300 DPI, RGB</p>
                  </div>
                </div>
                <Button asChild variant="outline">
                  <a href={downloadUrls.cover_art} download data-cy="download-cover-art">
                    <Download className="h-4 w-4 mr-2" />
                    Download
                  </a>
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="flex justify-center">
          <Button 
            variant="outline" 
            onClick={() => window.location.reload()}
            data-cy="publish-another"
          >
            Publish Another Version
          </Button>
        </div>
      </div>
    )
  }

  // Show error if failed
  if (error || jobStatus?.status === 'failed') {
    GlobalLoader.hide()
    return (
      <div className="space-y-6">
        <Alert variant="destructive" data-cy="publish-error">
          <AlertDescription>
            Publishing failed: {error?.message || jobStatus?.error || (jobStatus as any)?.result?.error_message || 'Unknown error'}
          </AlertDescription>
        </Alert>
        
        <div className="flex justify-center">
          <Button 
            variant="outline" 
            onClick={() => window.location.reload()}
            data-cy="try-again-button"
          >
            Try Again
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Project Overview */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Eye className="h-5 w-5" />
            Project Overview
          </CardTitle>
        </CardHeader>
        <CardContent data-cy="project-overview">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-center">
            <div>
              <div className="text-2xl font-bold" data-cy="chapter-count">{chapterCount}</div>
              <div className="text-sm text-muted-foreground">Chapters</div>
            </div>
            <div>
              <div className="text-2xl font-bold" data-cy="word-count">{wordCount.toLocaleString()}</div>
              <div className="text-sm text-muted-foreground">Words</div>
            </div>
            <div>
              <div className="text-2xl font-bold" data-cy="page-count">{Math.ceil(wordCount / 250)}</div>
              <div className="text-sm text-muted-foreground">Est. Pages</div>
            </div>
          </div>
          
          {hasCoverArt && (
            <div className="mt-4 flex items-center gap-2">
              <Badge variant="secondary" data-cy="cover-art-badge">Cover art available</Badge>
            </div>
          )}
          {!hasCoverArt && (
            <div className="mt-4">
              <Alert data-cy="cover-art-missing">
                <AlertDescription>
                  No cover art found. You can publish without it, but KDP will require a cover upload.
                </AlertDescription>
              </Alert>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Publishing Form */}
      <Form {...form}>
        <form onSubmit={form.handleSubmit(handlePublish)} className="space-y-6">
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="grid grid-cols-2 md:grid-cols-6 w-full gap-2 h-auto">
              <TabsTrigger value="details" data-cy="tab-details">Book Details</TabsTrigger>
              <TabsTrigger value="sections" data-cy="tab-sections">Optional Sections</TabsTrigger>
              <TabsTrigger value="engagement" data-cy="tab-engagement">Reader Engagement</TabsTrigger>
              <TabsTrigger value="settings" data-cy="tab-settings">Settings</TabsTrigger>
              <TabsTrigger value="kdp" data-cy="tab-kdp">KDP Kit</TabsTrigger>
              <TabsTrigger value="audiobook" data-cy="tab-audiobook" className="gap-1.5">
                <Headphones className="h-3.5 w-3.5" />
                Audiobook
              </TabsTrigger>
            </TabsList>

            <TabsContent value="details" className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Book Information</CardTitle>
                  <CardDescription>
                    Basic metadata for your published book
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <FormField
                      control={form.control}
                      name="title"
                      rules={{ required: 'Title is required' }}
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Title</FormLabel>
                          <FormControl>
                            <Input {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    
                    <FormField
                      control={form.control}
                      name="author"
                      rules={{ required: 'Author is required' }}
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Author</FormLabel>
                          <FormControl>
                            <Input {...field} />
                          </FormControl>
                          <FormDescription>Name shown on the book cover and KDP listing.</FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <FormField
                      control={form.control}
                      name="publisher"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Publisher (Optional)</FormLabel>
                          <FormControl>
                            <Input {...field} />
                          </FormControl>
                          <FormDescription>Leave blank if you are self-publishing.</FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    
                    <FormField
                      control={form.control}
                      name="isbn"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>ISBN (Optional)</FormLabel>
                          <FormControl>
                            <Input {...field} />
                          </FormControl>
                          <FormDescription>Use your own ISBN or leave blank for KDP assigned.</FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    
                    <FormField
                      control={form.control}
                      name="date"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Publication Year</FormLabel>
                          <FormControl>
                            <Input {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>

                  <FormField
                    control={form.control}
                    name="rights"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Copyright Notice</FormLabel>
                        <FormControl>
                          <Input {...field} />
                        </FormControl>
                        <FormDescription>Used in the book metadata and KDP publishing rights.</FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="sections" className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Optional Book Sections</CardTitle>
                  <CardDescription>
                    Add professional sections to enhance your book
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {[
                    { name: 'dedication', label: 'Dedication' },
                    { name: 'acknowledgments', label: 'Acknowledgments' },
                    { name: 'foreword', label: 'Foreword' },
                    { name: 'preface', label: 'Preface' },
                    { name: 'epilogue', label: 'Epilogue' },
                    { name: 'about_author', label: 'About the Author' }
                  ].map((section) => (
                    <FormField
                      key={section.name}
                      control={form.control}
                      name={section.name as keyof PublishFormData}
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>{section.label}</FormLabel>
                          <FormControl>
                            <Textarea 
                              {...field} 
                              rows={3}
                            />
                          </FormControl>
                          <FormDescription>Optional.</FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  ))}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="engagement" className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Reader Engagement</CardTitle>
                  <CardDescription>
                    Connect with your readers and promote your work
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {[
                    { name: 'call_to_action', label: 'Author Notes / Call to Action' },
                    { name: 'other_books', label: 'Other Books by Author' },
                    { name: 'connect_author', label: 'Connect with Author' },
                    { name: 'book_club_questions', label: 'Book Club Discussion Questions' }
                  ].map((section) => (
                    <FormField
                      key={section.name}
                      control={form.control}
                      name={section.name as keyof PublishFormData}
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>{section.label}</FormLabel>
                          <FormControl>
                            <Textarea 
                              {...field} 
                              rows={4}
                            />
                          </FormControl>
                          <FormDescription>Optional.</FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  ))}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="settings" className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Publishing Settings</CardTitle>
                  <CardDescription>
                    Configure output formats and options
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div>
                    <FormLabel className="text-base">Output Formats</FormLabel>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-2">
                      <FormField
                        control={form.control}
                        name="formats"
                        render={({ field }) => (
                          <FormItem className="flex flex-row items-start space-x-3 space-y-0">
                            <FormControl>
                              <Checkbox
                                id="format-epub"
                                name="formats"
                                checked={field.value?.includes('epub')}
                                onCheckedChange={(checked) => {
                                  const value = field.value || []
                                  if (checked) {
                                    field.onChange([...value, 'epub'])
                                  } else {
                                    field.onChange(value.filter(v => v !== 'epub'))
                                  }
                                }}
                              />
                            </FormControl>
                            <div className="space-y-1 leading-none">
                              <FormLabel>EPUB</FormLabel>
                              <p className="text-sm text-muted-foreground">
                                Kindle and e-reader compatible
                              </p>
                            </div>
                          </FormItem>
                        )}
                      />
                      
                      <FormField
                        control={form.control}
                        name="formats"
                        render={({ field }) => (
                          <FormItem className="flex flex-row items-start space-x-3 space-y-0">
                            <FormControl>
                              <Checkbox
                                id="format-pdf"
                                name="formats"
                                checked={field.value?.includes('pdf')}
                                onCheckedChange={(checked) => {
                                  const value = field.value || []
                                  if (checked) {
                                    field.onChange([...value, 'pdf'])
                                  } else {
                                    field.onChange(value.filter(v => v !== 'pdf'))
                                  }
                                }}
                              />
                            </FormControl>
                            <div className="space-y-1 leading-none">
                              <FormLabel>PDF</FormLabel>
                              <p className="text-sm text-muted-foreground">
                                Print-ready, professional layout
                              </p>
                            </div>
                          </FormItem>
                        )}
                      />
                    </div>
                  </div>

                  <Separator />

                  <div className="space-y-4">
                    <FormField
                      control={form.control}
                      name="use_existing_cover"
                      render={({ field }) => (
                        <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                          <div className="space-y-0.5">
                            <FormLabel className="text-base">Use Existing Cover Art</FormLabel>
                            <p className="text-sm text-muted-foreground">
                              Include the cover art from your project
                            </p>
                          </div>
                          <FormControl>
                            <Checkbox
                              id="use-existing-cover"
                              name="use_existing_cover"
                              checked={field.value}
                              onCheckedChange={field.onChange}
                              disabled={!hasCoverArt}
                            />
                          </FormControl>
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="include_toc"
                      render={({ field }) => (
                        <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                          <div className="space-y-0.5">
                            <FormLabel className="text-base">Include Table of Contents</FormLabel>
                            <p className="text-sm text-muted-foreground">
                              Generate navigation for chapters
                            </p>
                          </div>
                          <FormControl>
                            <Checkbox
                              id="include-toc"
                              name="include_toc"
                              checked={field.value}
                              onCheckedChange={field.onChange}
                            />
                          </FormControl>
                        </FormItem>
                      )}
                    />
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="kdp" className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>KDP Publishing Kit</CardTitle>
                  <CardDescription>
                    Generate a ready-to-use publishing package for Amazon KDP. The kit PDF mirrors Amazon&apos;s 3-page submission flow so you can copy and paste directly.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <FormField
                    control={form.control}
                    name="include_kdp_kit"
                    render={({ field }) => (
                      <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                        <div className="space-y-0.5">
                          <FormLabel className="text-base">Include KDP Publishing Kit PDF</FormLabel>
                          <p className="text-sm text-muted-foreground">
                            Creates a PDF with copy-ready KDP fields and publishing steps.
                          </p>
                        </div>
                        <FormControl>
                          <Checkbox
                            id="include-kdp-kit"
                            name="include_kdp_kit"
                            checked={field.value}
                            onCheckedChange={field.onChange}
                          />
                        </FormControl>
                      </FormItem>
                    )}
                  />

                  {form.watch('include_kdp_kit') && (
                    <div className="space-y-6">
                      <Alert>
                        <AlertDescription>
                          Leave any field blank and we&apos;ll auto-generate it from your book content using AI. Fill in a field to override.
                        </AlertDescription>
                      </Alert>

                      {/* --- Section: Book Details --- */}
                      <div className="rounded-lg border p-5 space-y-4">
                        <div>
                          <h4 className="text-sm font-semibold">Book Details</h4>
                          <p className="text-xs text-muted-foreground mt-0.5">Title, series, and edition info for the KDP &quot;Book Details&quot; page.</p>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          <FormField
                            control={form.control}
                            name="kdp_subtitle"
                            render={({ field }) => {
                              const titleLen = (form.watch('title') || '').length
                              const subtitleLen = (field.value || '').length
                              const totalLen = titleLen + subtitleLen
                              return (
                                <FormItem>
                                  <FormLabel>Subtitle (Optional)</FormLabel>
                                  <FormControl>
                                    <Input {...field} />
                                  </FormControl>
                                  <div className="flex justify-between">
                                    <FormDescription>Combined with title, must be under 200 characters.</FormDescription>
                                    {subtitleLen > 0 && (
                                      <span className={`text-xs ${totalLen > 200 ? 'text-destructive font-medium' : 'text-muted-foreground'}`}>
                                        {totalLen}/200
                                      </span>
                                    )}
                                  </div>
                                  <FormMessage />
                                </FormItem>
                              )
                            }}
                          />
                          <FormField
                            control={form.control}
                            name="kdp_contributors"
                            render={({ field }) => (
                              <FormItem>
                                <FormLabel>Contributors (Optional)</FormLabel>
                                <FormControl>
                                  <Input {...field} placeholder="e.g. Editor: Jane Smith" />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          <FormField
                            control={form.control}
                            name="kdp_series_name"
                            render={({ field }) => (
                              <FormItem>
                                <FormLabel>Series Name (Optional)</FormLabel>
                                <FormControl>
                                  <Input {...field} />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                          <FormField
                            control={form.control}
                            name="kdp_series_number"
                            render={({ field }) => (
                              <FormItem>
                                <FormLabel>Series Number (Optional)</FormLabel>
                                <FormControl>
                                  <Input {...field} placeholder="e.g. 1" />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                          <FormField
                            control={form.control}
                            name="kdp_language"
                            render={({ field }) => (
                              <FormItem>
                                <FormLabel>Language</FormLabel>
                                <FormControl>
                                  <Input {...field} placeholder="Auto-detect" />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                          <FormField
                            control={form.control}
                            name="kdp_edition"
                            render={({ field }) => (
                              <FormItem>
                                <FormLabel>Edition (Optional)</FormLabel>
                                <FormControl>
                                  <Input {...field} placeholder="1st" />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                          <FormField
                            control={form.control}
                            name="kdp_imprint"
                            render={({ field }) => (
                              <FormItem>
                                <FormLabel>Imprint (Optional)</FormLabel>
                                <FormControl>
                                  <Input {...field} />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                        </div>

                        <FormField
                          control={form.control}
                          name="kdp_primary_marketplace"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Primary Marketplace</FormLabel>
                              <FormControl>
                                <Input {...field} placeholder="Auto-select (e.g. Amazon.com)" />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      </div>

                      {/* --- Section: Description, Keywords & Categories --- */}
                      <div className="rounded-lg border p-5 space-y-4">
                        <div>
                          <h4 className="text-sm font-semibold">Description, Keywords & Categories</h4>
                          <p className="text-xs text-muted-foreground mt-0.5">Your Amazon product listing content. These are the most important fields for discoverability.</p>
                        </div>

                        <FormField
                          control={form.control}
                          name="kdp_description"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Book Description</FormLabel>
                              <FormControl>
                                <Textarea {...field} rows={8} />
                              </FormControl>
                              <div className="flex justify-between">
                                <FormDescription>
                                  Leave blank to auto-generate a 300-500 word Amazon product description. HTML formatting is added automatically for KDP.
                                </FormDescription>
                                <span className={`text-xs whitespace-nowrap ml-4 ${(field.value?.length || 0) > 4000 ? 'text-destructive font-medium' : 'text-muted-foreground'}`}>
                                  {field.value?.length || 0} / 4,000
                                </span>
                              </div>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="kdp_keywords"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Keywords</FormLabel>
                              <FormControl>
                                <Textarea {...field} rows={3} placeholder='e.g. "medieval fantasy books", "epic adventure series"' />
                              </FormControl>
                              <FormDescription>
                                Up to 7 keyword phrases, each under 50 characters. Separate with commas or new lines.
                              </FormDescription>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="kdp_categories"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Amazon Store Categories</FormLabel>
                              <FormControl>
                                <Textarea {...field} rows={3} placeholder="e.g. Fiction > Thriller > Psychological" />
                              </FormControl>
                              <FormDescription>
                                Up to 3 categories. Use Amazon&apos;s format: Category &gt; Subcategory &gt; Placement.
                              </FormDescription>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="kdp_author_bio"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Author Bio (Optional)</FormLabel>
                              <FormControl>
                                <Textarea {...field} rows={3} />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      </div>

                      {/* --- Section: Content & Compliance --- */}
                      <div className="rounded-lg border p-5 space-y-4">
                        <div>
                          <h4 className="text-sm font-semibold">Content & Compliance</h4>
                          <p className="text-xs text-muted-foreground mt-0.5">Required KDP declarations. These rarely need changing for most books.</p>
                        </div>

                        <FormField
                          control={form.control}
                          name="kdp_publishing_rights"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Publishing Rights</FormLabel>
                              <FormControl>
                                <select
                                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                  value={field.value}
                                  onChange={field.onChange}
                                >
                                  <option value="own_copyright">I own the copyright and hold necessary publishing rights</option>
                                  <option value="public_domain">This is a public domain work</option>
                                </select>
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="kdp_adult_content"
                          render={({ field }) => (
                            <FormItem className="flex flex-row items-start space-x-3 space-y-0 rounded-md border p-4">
                              <div className="space-y-1 leading-none flex-1">
                                <FormLabel>Contains Sexually Explicit Content</FormLabel>
                                <FormDescription>
                                  Most books answer No. Amazon requires this declaration for all submissions.
                                </FormDescription>
                              </div>
                              <FormControl>
                                <Checkbox
                                  checked={field.value}
                                  onCheckedChange={field.onChange}
                                />
                              </FormControl>
                            </FormItem>
                          )}
                        />

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          <FormField
                            control={form.control}
                            name="kdp_reading_age_min"
                            render={({ field }) => (
                              <FormItem>
                                <FormLabel>Reading Age — Min</FormLabel>
                                <FormControl>
                                  <select
                                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                    value={field.value}
                                    onChange={field.onChange}
                                  >
                                    <option value="">Not specified</option>
                                    <option value="0">0 years</option>
                                    <option value="3">3 years</option>
                                    <option value="6">6 years</option>
                                    <option value="9">9 years</option>
                                    <option value="13">13 years</option>
                                    <option value="18">18 years</option>
                                  </select>
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                          <FormField
                            control={form.control}
                            name="kdp_reading_age_max"
                            render={({ field }) => (
                              <FormItem>
                                <FormLabel>Reading Age — Max</FormLabel>
                                <FormControl>
                                  <select
                                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                    value={field.value}
                                    onChange={field.onChange}
                                  >
                                    <option value="">Not specified</option>
                                    <option value="2">2 years</option>
                                    <option value="5">5 years</option>
                                    <option value="8">8 years</option>
                                    <option value="12">12 years</option>
                                    <option value="17">17 years</option>
                                    <option value="18">18+ years</option>
                                  </select>
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                        </div>
                        <p className="text-xs text-muted-foreground -mt-2">Only needed for children&apos;s or young adult books. Leave as &quot;Not specified&quot; for adult fiction. Standard KDP bands: 0-2, 3-5, 6-8, 9-12, 13-17.</p>
                      </div>

                      {/* --- Section: Distribution & Pricing --- */}
                      <div className="rounded-lg border p-5 space-y-4">
                        <div>
                          <h4 className="text-sm font-semibold">Distribution & Pricing</h4>
                          <p className="text-xs text-muted-foreground mt-0.5">DRM, Kindle Unlimited enrollment, territories, and pricing for the KDP &quot;Rights and Pricing&quot; page.</p>
                        </div>

                        <FormField
                          control={form.control}
                          name="kdp_drm"
                          render={({ field }) => (
                            <FormItem className="flex flex-row items-start space-x-3 space-y-0 rounded-md border p-4">
                              <div className="space-y-1 leading-none flex-1">
                                <FormLabel>Digital Rights Management (DRM)</FormLabel>
                                <FormDescription>
                                  Helps protect against unauthorized copying. Recommended for most books.
                                </FormDescription>
                              </div>
                              <FormControl>
                                <Checkbox
                                  checked={field.value}
                                  onCheckedChange={field.onChange}
                                />
                              </FormControl>
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="kdp_select"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>KDP Select / Kindle Unlimited</FormLabel>
                              <FormControl>
                                <select
                                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                  value={field.value}
                                  onChange={field.onChange}
                                >
                                  <option value="">Decide later</option>
                                  <option value="yes">Yes — enroll in Kindle Unlimited (90-day exclusivity)</option>
                                  <option value="no">No — sell on other platforms too</option>
                                </select>
                              </FormControl>
                              <FormDescription>
                                KDP Select gives access to Kindle Unlimited readers but requires 90-day exclusivity.
                              </FormDescription>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="kdp_territories"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Territories</FormLabel>
                              <FormControl>
                                <select
                                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                  value={field.value}
                                  onChange={field.onChange}
                                >
                                  <option value="worldwide">All territories (worldwide rights)</option>
                                  <option value="specific">Individual territories</option>
                                </select>
                              </FormControl>
                              <FormDescription>
                                Most authors choose worldwide. Select &quot;Individual territories&quot; only if you have restricted geographic rights.
                              </FormDescription>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="kdp_pricing"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Pricing Notes (Optional)</FormLabel>
                              <FormControl>
                                <Textarea {...field} rows={2} placeholder="e.g. $4.99 — 70% royalty tier ($2.99-$9.99 recommended)" />
                              </FormControl>
                              <FormDescription>
                                70% royalty for $2.99–$9.99. 35% royalty outside that range.
                              </FormDescription>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="audiobook" className="space-y-4">
              <AudiobookTab projectId={projectId} chapterCount={chapterCount} />
            </TabsContent>
          </Tabs>

          <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-3 pt-6 border-t">
            <Button type="button" variant="outline" onClick={() => window.history.back()} className="w-full sm:w-auto">
              Cancel
            </Button>
            <Button 
              type="submit" 
              disabled={isLoading || !form.watch('formats')?.length || chapterCount === 0}
              className="gap-2 w-full sm:w-auto"
              data-cy="publish-button"
            >
              <Settings className="h-4 w-4" />
              Publish Book
            </Button>
          </div>
        </form>
      </Form>
    </div>
  )
}

// ── Audiobook Tab Component ────────────────────────────────────────

interface AudiobookTabProps {
  projectId: string
  chapterCount: number
}

function AudiobookTab({ projectId, chapterCount }: AudiobookTabProps) {
  const { voices, isLoading: voicesLoading, error: voicesError } = useAudiobookVoices()
  const { estimate, isLoading: estimateLoading, error: estimateError } = useAudiobookEstimate(projectId)
  const {
    startAudiobookJob,
    generatePreview,
    scanAbbreviations,
    jobStatus,
    isLoading: jobLoading,
    error: jobError,
    downloadUrls,
  } = useAudiobookJob()

  const [selectedVoiceId, setSelectedVoiceId] = useState<string>('')
  const [glossary, setGlossary] = useState<PronunciationEntry[]>([])
  const [abbreviationSuggestions, setAbbreviationSuggestions] = useState<AbbreviationSuggestion[]>([])
  const [scanningAbbreviations, setScanningAbbreviations] = useState(false)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewPlaying, setPreviewPlaying] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [newEntry, setNewEntry] = useState({ abbreviation: '', spoken_form: '' })
  const previewUrlRef = useRef<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  useEffect(() => {
    const audio = new Audio()
    audio.onended = () => setPreviewPlaying(false)
    audio.onpause = () => setPreviewPlaying(false)
    audio.onplay = () => setPreviewPlaying(true)
    audioRef.current = audio

    return () => {
      audio.pause()
      audio.src = ''
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current)
    }
  }, [])

  const handleScanAbbreviations = async () => {
    setScanningAbbreviations(true)
    try {
      const suggestions = await scanAbbreviations(projectId)
      const existingAbbrevs = new Set(glossary.map(g => g.abbreviation))
      setAbbreviationSuggestions(suggestions.filter(s => !existingAbbrevs.has(s.abbreviation)))
    } finally {
      setScanningAbbreviations(false)
    }
  }

  const acceptSuggestion = (suggestion: AbbreviationSuggestion) => {
    setGlossary(prev => [...prev, { abbreviation: suggestion.abbreviation, spoken_form: suggestion.spoken_form }])
    setAbbreviationSuggestions(prev => prev.filter(s => s.abbreviation !== suggestion.abbreviation))
  }

  const dismissSuggestion = (abbreviation: string) => {
    setAbbreviationSuggestions(prev => prev.filter(s => s.abbreviation !== abbreviation))
  }

  const removeGlossaryEntry = (abbreviation: string) => {
    setGlossary(prev => prev.filter(e => e.abbreviation !== abbreviation))
  }

  const addGlossaryEntry = () => {
    if (!newEntry.abbreviation.trim() || !newEntry.spoken_form.trim()) return
    setGlossary(prev => [...prev, { abbreviation: newEntry.abbreviation.trim(), spoken_form: newEntry.spoken_form.trim() }])
    setNewEntry({ abbreviation: '', spoken_form: '' })
  }

  const handlePreview = async () => {
    if (!selectedVoiceId) return
    setPreviewLoading(true)
    try {
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current)
        previewUrlRef.current = null
        setPreviewUrl(null)
      }
      const url = await generatePreview(projectId, selectedVoiceId, undefined, glossary)
      if (url) {
        previewUrlRef.current = url
        setPreviewUrl(url)
        if (audioRef.current) {
          audioRef.current.src = url
          audioRef.current.play().catch(() => {})
        }
      }
    } finally {
      setPreviewLoading(false)
    }
  }

  const togglePlayPause = () => {
    if (!audioRef.current || !previewUrl) return
    if (previewPlaying) {
      audioRef.current.pause()
    } else {
      audioRef.current.play().catch(() => {})
    }
  }

  const handleGenerate = async () => {
    setShowConfirm(false)
    await startAudiobookJob(projectId, {
      voice_id: selectedVoiceId,
      model_id: 'eleven_multilingual_v2',
      pronunciation_glossary: glossary,
    })
  }

  const isJobRunning = jobLoading || (jobStatus && !['completed', 'failed'].includes(jobStatus.status))

  // Show results if completed
  if (jobStatus?.status === 'completed' && downloadUrls) {
    const result = jobStatus.result
    const chapterUrls = downloadUrls.chapters || {}
    const sortedChapters = Object.entries(chapterUrls).sort(([a], [b]) => Number(a) - Number(b))

    return (
      <div className="space-y-4">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <CheckCircle className="h-8 w-8 text-green-500" />
              <div>
                <CardTitle>Audiobook Ready</CardTitle>
                <CardDescription>
                  {result?.total_duration_seconds
                    ? `${Math.round(result.total_duration_seconds / 60)} minutes of audio`
                    : 'Your audiobook has been generated'}
                  {result?.credits_charged ? ` — ${result.credits_charged} credits used` : ''}
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {downloadUrls.full_book && (
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-4 border rounded-lg bg-muted/30">
                <div className="flex items-center gap-3">
                  <Headphones className="h-6 w-6" />
                  <div>
                    <p className="font-semibold">Complete Audiobook</p>
                    <p className="text-sm text-muted-foreground">
                      Full book MP3
                      {result?.file_sizes?.full_book
                        ? ` — ${(result.file_sizes.full_book / (1024 * 1024)).toFixed(1)} MB`
                        : ''}
                    </p>
                  </div>
                </div>
                <Button asChild>
                  <a href={downloadUrls.full_book} download>
                    <Download className="h-4 w-4 mr-2" />
                    Download
                  </a>
                </Button>
              </div>
            )}

            {sortedChapters.length > 0 && (
              <div className="space-y-2">
                <p className="text-sm font-medium text-muted-foreground">Individual Chapters</p>
                <div className="grid gap-2">
                  {sortedChapters.map(([chapterNum, url]) => (
                    <div key={chapterNum} className="flex items-center justify-between p-3 border rounded-lg">
                      <div className="flex items-center gap-2">
                        <Volume2 className="h-4 w-4 text-muted-foreground" />
                        <span className="text-sm">Chapter {chapterNum}</span>
                      </div>
                      <Button asChild variant="outline" size="sm">
                        <a href={url} download>
                          <Download className="h-3 w-3 mr-1" />
                          Download
                        </a>
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <Button
              variant="outline"
              onClick={() => window.location.reload()}
              className="w-full mt-4"
            >
              Generate Again
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  // Show failure state
  if (jobStatus?.status === 'failed') {
    const errorMessage = jobStatus.error || jobStatus.result?.error_message || 'Audiobook generation failed'
    return (
      <Card>
        <CardContent className="py-12 text-center space-y-4">
          <Headphones className="h-12 w-12 mx-auto text-destructive" />
          <h3 className="text-lg font-semibold">Audiobook Generation Failed</h3>
          <Alert variant="destructive" className="max-w-md mx-auto text-left">
            <AlertDescription>{errorMessage}</AlertDescription>
          </Alert>
          <Button
            variant="outline"
            onClick={() => window.location.reload()}
          >
            Try Again
          </Button>
        </CardContent>
      </Card>
    )
  }

  // Show progress if running
  if (isJobRunning) {
    return (
      <Card>
        <CardContent className="py-12 text-center space-y-4">
          <Headphones className="h-12 w-12 mx-auto text-muted-foreground animate-pulse" />
          <h3 className="text-lg font-semibold">Generating Audiobook</h3>
          <p className="text-muted-foreground">
            {jobStatus?.progress?.current_step || 'Preparing chapters...'}
          </p>
          {jobStatus?.progress?.progress_percentage != null && (
            <div className="max-w-md mx-auto">
              <div className="h-2 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary rounded-full transition-all duration-500"
                  style={{ width: `${jobStatus.progress.progress_percentage}%` }}
                />
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {Math.round(jobStatus.progress.progress_percentage)}%
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      {/* Voice Selection */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Headphones className="h-5 w-5" />
            Narrator Voice
          </CardTitle>
          <CardDescription>
            Choose a voice for your audiobook narration
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {voicesError ? (
            <Alert variant="destructive">
              <AlertDescription>Failed to load voices. Please try refreshing.</AlertDescription>
            </Alert>
          ) : voicesLoading ? (
            <p className="text-sm text-muted-foreground">Loading voices...</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {voices.map((voice) => (
                <button
                  key={voice.id}
                  type="button"
                  onClick={() => setSelectedVoiceId(voice.id)}
                  className={`p-4 border rounded-lg text-left transition-all hover:border-primary/50 ${
                    selectedVoiceId === voice.id
                      ? 'border-primary ring-2 ring-primary/20 bg-primary/5'
                      : 'border-border'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-medium">{voice.name}</span>
                    <div className="flex gap-1.5">
                      <Badge variant="outline" className="text-xs">
                        {voice.gender}
                      </Badge>
                      <Badge variant="secondary" className="text-xs">
                        {voice.accent}
                      </Badge>
                    </div>
                  </div>
                  <p className="text-sm text-muted-foreground">{voice.description}</p>
                </button>
              ))}
            </div>
          )}

          {selectedVoiceId && (
            <div className="flex items-center gap-3 pt-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handlePreview}
                disabled={previewLoading || chapterCount === 0}
                className="gap-2"
              >
                {previewLoading ? (
                  <>Loading...</>
                ) : (
                  <>
                    <Play className="h-3.5 w-3.5" />
                    Preview with my book
                  </>
                )}
              </Button>

              {previewUrl && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={togglePlayPause}
                  className="gap-2"
                >
                  {previewPlaying ? (
                    <><Pause className="h-3.5 w-3.5" /> Pause</>
                  ) : (
                    <><Play className="h-3.5 w-3.5" /> Play again</>
                  )}
                </Button>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pronunciation Glossary */}
      <Card>
        <CardHeader>
          <CardTitle>Pronunciation Glossary</CardTitle>
          <CardDescription>
            Define how abbreviations and special terms should be spoken
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleScanAbbreviations}
            disabled={scanningAbbreviations || chapterCount === 0}
            className="gap-2"
          >
            <Search className="h-3.5 w-3.5" />
            {scanningAbbreviations ? 'Scanning...' : 'Scan for Abbreviations'}
          </Button>

          {abbreviationSuggestions.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium">Suggestions</p>
              {abbreviationSuggestions.map((suggestion) => (
                <div key={suggestion.abbreviation} className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg text-sm">
                  <code className="font-mono bg-background px-1.5 py-0.5 rounded">
                    {suggestion.abbreviation}
                  </code>
                  <span className="text-muted-foreground">→</span>
                  <span>{suggestion.spoken_form}</span>
                  <Badge variant="secondary" className="text-xs ml-auto">
                    {suggestion.occurrences}x
                  </Badge>
                  <Button type="button" variant="ghost" size="sm" onClick={() => acceptSuggestion(suggestion)}>
                    Accept
                  </Button>
                  <Button type="button" variant="ghost" size="sm" onClick={() => dismissSuggestion(suggestion.abbreviation)}>
                    Dismiss
                  </Button>
                </div>
              ))}
            </div>
          )}

          {glossary.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium">Active Glossary</p>
              {glossary.map((entry) => (
                <div key={entry.abbreviation} className="flex items-center gap-2 p-2 border rounded-lg text-sm">
                  <code className="font-mono bg-muted px-1.5 py-0.5 rounded">
                    {entry.abbreviation}
                  </code>
                  <span className="text-muted-foreground">→</span>
                  <span className="flex-1">{entry.spoken_form}</span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => removeGlossaryEntry(entry.abbreviation)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
            </div>
          )}

          <div className="flex items-end gap-2">
            <div className="flex-1 space-y-1">
              <label className="text-xs text-muted-foreground">Abbreviation</label>
              <Input
                placeholder="e.g. DO"
                value={newEntry.abbreviation}
                onChange={(e) => setNewEntry(prev => ({ ...prev, abbreviation: e.target.value }))}
                className="h-9"
              />
            </div>
            <div className="flex-1 space-y-1">
              <label className="text-xs text-muted-foreground">Spoken Form</label>
              <Input
                placeholder="e.g. D. O."
                value={newEntry.spoken_form}
                onChange={(e) => setNewEntry(prev => ({ ...prev, spoken_form: e.target.value }))}
                className="h-9"
              />
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={addGlossaryEntry}
              disabled={!newEntry.abbreviation.trim() || !newEntry.spoken_form.trim()}
              className="h-9"
            >
              <Plus className="h-3.5 w-3.5" />
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Cost Estimate & Generate */}
      <Card>
        <CardHeader>
          <CardTitle>Generate Audiobook</CardTitle>
          <CardDescription>
            Review the estimate and generate your audiobook
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {estimateError ? (
            <Alert variant="destructive">
              <AlertDescription>Failed to load cost estimate.</AlertDescription>
            </Alert>
          ) : estimateLoading ? (
            <p className="text-sm text-muted-foreground">Calculating estimate...</p>
          ) : estimate ? (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 p-4 bg-muted/30 rounded-lg">
              <div>
                <p className="text-xs text-muted-foreground">Characters</p>
                <p className="text-lg font-semibold">{estimate.total_characters.toLocaleString()}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Chapters</p>
                <p className="text-lg font-semibold">{estimate.total_chapters}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Est. Cost</p>
                <p className="text-lg font-semibold">
                  {estimate.estimated_credits} credits
                  <span className="text-xs text-muted-foreground ml-1">
                    (~${estimate.estimated_cost_usd})
                  </span>
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Est. Time</p>
                <p className="text-lg font-semibold">{estimate.estimated_duration_minutes} min</p>
              </div>
            </div>
          ) : chapterCount === 0 ? (
            <Alert>
              <AlertDescription>No chapters found. Write some chapters first.</AlertDescription>
            </Alert>
          ) : null}

          {jobError && (
            <Alert variant="destructive">
              <AlertDescription>
                {jobError instanceof Error ? jobError.message : String(jobError)}
              </AlertDescription>
            </Alert>
          )}

          {!showConfirm ? (
            <Button
              type="button"
              onClick={() => setShowConfirm(true)}
              disabled={!selectedVoiceId || chapterCount === 0 || jobLoading}
              className="w-full gap-2"
            >
              <Headphones className="h-4 w-4" />
              Generate Audiobook
            </Button>
          ) : (
            <div className="p-4 border rounded-lg space-y-3">
              <p className="font-medium">Confirm audiobook generation</p>
              <p className="text-sm text-muted-foreground">
                This will use approximately{' '}
                <strong>{estimate?.estimated_credits || '—'} credits</strong>{' '}
                (~${estimate?.estimated_cost_usd || '—'}) and take about{' '}
                <strong>{estimate?.estimated_duration_minutes || '—'} minutes</strong>.
              </p>
              <div className="flex gap-2">
                <Button type="button" onClick={handleGenerate} className="gap-2">
                  <CheckCircle className="h-4 w-4" />
                  Confirm & Generate
                </Button>
                <Button type="button" variant="outline" onClick={() => setShowConfirm(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}