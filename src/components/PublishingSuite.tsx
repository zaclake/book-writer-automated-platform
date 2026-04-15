'use client'

import React, { useState, useEffect } from 'react'
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
import { Book, Download, FileText, Settings, Eye, CheckCircle } from 'lucide-react'
import { usePublishJob } from '@/hooks/usePublishJob'
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
  kdp_age_range?: string
  kdp_grade_range?: string
  kdp_imprint?: string
  kdp_pricing?: string
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
      include_kdp_kit: false,
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
      kdp_age_range: '',
      kdp_grade_range: '',
      kdp_imprint: '',
      kdp_pricing: ''
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
        kdp_age_range: data.kdp_age_range?.trim() || undefined,
        kdp_grade_range: data.kdp_grade_range?.trim() || undefined,
        kdp_imprint: data.kdp_imprint?.trim() || undefined,
        kdp_pricing: data.kdp_pricing?.trim() || undefined
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
  if (jobStatus?.status === 'completed' && downloadUrls && (downloadUrls.epub || downloadUrls.pdf || downloadUrls.html || downloadUrls.kdp_kit)) {
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
            <TabsList className="grid grid-cols-2 md:grid-cols-5 w-full gap-2 h-auto">
              <TabsTrigger value="details" data-cy="tab-details">Book Details</TabsTrigger>
              <TabsTrigger value="sections" data-cy="tab-sections">Optional Sections</TabsTrigger>
              <TabsTrigger value="engagement" data-cy="tab-engagement">Reader Engagement</TabsTrigger>
              <TabsTrigger value="settings" data-cy="tab-settings">Settings</TabsTrigger>
              <TabsTrigger value="kdp" data-cy="tab-kdp">KDP Kit</TabsTrigger>
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
                    Generate a copy-ready PDF with KDP fields and publishing steps. Leave fields blank to auto-generate from your book.
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
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <FormField
                          control={form.control}
                          name="kdp_subtitle"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Subtitle (Optional)</FormLabel>
                              <FormControl>
                                <Input {...field} />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                        <FormField
                          control={form.control}
                          name="kdp_contributors"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Contributors (Optional)</FormLabel>
                              <FormControl>
                                <Input {...field} />
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
                                <Input {...field} />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <FormField
                          control={form.control}
                          name="kdp_language"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Language</FormLabel>
                              <FormControl>
                                <Input {...field} />
                              </FormControl>
                              <FormDescription>Leave blank to auto-detect from book content.</FormDescription>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                        <FormField
                          control={form.control}
                          name="kdp_primary_marketplace"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Primary Marketplace</FormLabel>
                              <FormControl>
                                <Input {...field} />
                              </FormControl>
                              <FormDescription>Leave blank to auto-select based on language.</FormDescription>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      </div>

                      <FormField
                        control={form.control}
                        name="kdp_description"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>KDP Book Description</FormLabel>
                            <FormControl>
                              <Textarea {...field} rows={6} />
                            </FormControl>
                            <FormDescription>
                              Leave blank to auto-generate from your book content.
                            </FormDescription>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      <FormField
                        control={form.control}
                        name="kdp_keywords"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>KDP Keywords</FormLabel>
                            <FormControl>
                              <Textarea {...field} rows={3} />
                            </FormControl>
                            <FormDescription>
                              Leave blank to auto-generate (aim for 7). Separate with commas or new lines.
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
                            <FormLabel>KDP Categories (BISAC)</FormLabel>
                            <FormControl>
                              <Textarea {...field} rows={3} />
                            </FormControl>
                            <FormDescription>
                              Leave blank to auto-generate. Separate with commas or new lines.
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
                              <Textarea {...field} rows={4} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <FormField
                          control={form.control}
                          name="kdp_edition"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Edition (Optional)</FormLabel>
                              <FormControl>
                                <Input {...field} />
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

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <FormField
                          control={form.control}
                          name="kdp_age_range"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Age Range (Optional)</FormLabel>
                              <FormControl>
                                <Input {...field} />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                        <FormField
                          control={form.control}
                          name="kdp_grade_range"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Grade Range (Optional)</FormLabel>
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
                        name="kdp_pricing"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Pricing Notes (Optional)</FormLabel>
                            <FormControl>
                              <Textarea {...field} rows={3} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>
                  )}
                </CardContent>
              </Card>
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