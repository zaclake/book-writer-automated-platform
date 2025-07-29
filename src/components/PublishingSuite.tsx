'use client'

import React, { useState, useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { CreativeLoader } from '@/components/ui/CreativeLoader'
import { Book, Download, FileText, Settings, Eye, CheckCircle } from 'lucide-react'
import { usePublishJob } from '@/hooks/usePublishJob'
import { Project } from '@/types/project'
import { useAuth } from '@clerk/nextjs'

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
}

export default function PublishingSuite({ projectId, project }: PublishingSuiteProps) {
  const [activeTab, setActiveTab] = useState('details')
  const { startPublishJob, jobStatus, isLoading, error, downloadUrls } = usePublishJob()
  const { getToken } = useAuth()

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
      use_existing_cover: true,
      include_toc: true
    }
  })

  const handlePublish = async (data: PublishFormData) => {
    try {
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
        include_toc: data.include_toc
      })
    } catch (err) {
      console.error('Failed to start publish job:', err)
    }
  }

  const [projectStats, setProjectStats] = useState({ chapterCount: 0, wordCount: 0 })

  // Fetch real chapter statistics on mount
  useEffect(() => {
    const fetchChapterStats = async () => {
      try {
        const token = await getToken()
        if (!token) return
        
        const response = await fetch(`/api/projects/${projectId}/chapters`, {
          headers: { 'Authorization': `Bearer ${token}` }
        })
        
        if (response.ok) {
          const data = await response.json()
          const chapters = data.chapters || []
          const chapterCount = chapters.length
          
          // Calculate total word count from chapter metadata
          const wordCount = chapters.reduce((total: number, chapter: any) => {
            return total + (chapter.word_count || chapter.metadata?.word_count || 0)
          }, 0)
          
          setProjectStats({ chapterCount, wordCount })
        } else {
          // Fallback to project progress data
          setProjectStats({
            chapterCount: project.progress?.chapters_completed || 0,
            wordCount: project.progress?.current_word_count || 0,
          })
        }
      } catch (error) {
        console.error('Failed to fetch chapter stats:', error)
        // Fallback to project progress data
        setProjectStats({
          chapterCount: project.progress?.chapters_completed || 0,
          wordCount: project.progress?.current_word_count || 0,
        })
      }
    }
    
    fetchChapterStats()
  }, [projectId, getToken, project.progress])

  const { chapterCount, wordCount } = projectStats

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
        
        <CreativeLoader data-cy="creative-loader" />
        
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
  if (jobStatus?.status === 'completed' && downloadUrls) {
    return (
      <div className="space-y-6" data-cy="publish-success">
        <div className="text-center">
          <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-4" />
          <h3 className="text-xl font-semibold mb-2">Book Published Successfully!</h3>
          <p className="text-muted-foreground">
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
              <div className="flex items-center justify-between p-3 border rounded-lg">
                <div className="flex items-center gap-3">
                  <Book className="h-5 w-5" />
                  <div>
                    <p className="font-medium">EPUB Format</p>
                    <p className="text-sm text-muted-foreground">Kindle and e-reader compatible</p>
                  </div>
                </div>
                <Button asChild variant="outline">
                  <a href={downloadUrls.epub} download data-cy="download-epub">
                    <Download className="h-4 w-4 mr-2" />
                    Download
                  </a>
                </Button>
              </div>
            )}
            
            {downloadUrls.pdf && (
              <div className="flex items-center justify-between p-3 border rounded-lg">
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
    return (
      <div className="space-y-6">
        <Alert variant="destructive" data-cy="publish-error">
          <AlertDescription>
            Publishing failed: {error?.message || jobStatus?.error || 'Unknown error'}
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
          <div className="grid grid-cols-3 gap-4 text-center">
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
          
          {project.cover_art?.image_url && (
            <div className="mt-4 flex items-center gap-2">
              <Badge variant="secondary" data-cy="cover-art-badge">Cover art available</Badge>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Publishing Form */}
      <Form {...form}>
        <form onSubmit={form.handleSubmit(handlePublish)} className="space-y-6">
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="grid grid-cols-4 w-full">
              <TabsTrigger value="details" data-cy="tab-details">Book Details</TabsTrigger>
              <TabsTrigger value="sections" data-cy="tab-sections">Optional Sections</TabsTrigger>
              <TabsTrigger value="engagement" data-cy="tab-engagement">Reader Engagement</TabsTrigger>
              <TabsTrigger value="settings" data-cy="tab-settings">Settings</TabsTrigger>
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
                  <div className="grid grid-cols-2 gap-4">
                    <FormField
                      control={form.control}
                      name="title"
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
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Author</FormLabel>
                          <FormControl>
                            <Input {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>

                  <div className="grid grid-cols-3 gap-4">
                    <FormField
                      control={form.control}
                      name="publisher"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Publisher (Optional)</FormLabel>
                          <FormControl>
                            <Input {...field} placeholder="Self-published" />
                          </FormControl>
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
                            <Input {...field} placeholder="978-0-123456-78-9" />
                          </FormControl>
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
                    { name: 'dedication', label: 'Dedication', placeholder: 'To my family...' },
                    { name: 'acknowledgments', label: 'Acknowledgments', placeholder: 'I would like to thank...' },
                    { name: 'foreword', label: 'Foreword', placeholder: 'This book explores...' },
                    { name: 'preface', label: 'Preface', placeholder: 'When I began writing this book...' },
                    { name: 'epilogue', label: 'Epilogue', placeholder: 'As we conclude this journey...' },
                    { name: 'about_author', label: 'About the Author', placeholder: 'John Doe is a...' }
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
                              placeholder={section.placeholder}
                              rows={3}
                            />
                          </FormControl>
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
                    { name: 'call_to_action', label: 'Author Notes / Call to Action', placeholder: 'Thank you for reading! Please leave a review...' },
                    { name: 'other_books', label: 'Other Books by Author', placeholder: 'Also by this author: Title 1, Title 2...' },
                    { name: 'connect_author', label: 'Connect with Author', placeholder: 'Follow me on social media...' },
                    { name: 'book_club_questions', label: 'Book Club Discussion Questions', placeholder: '1. What did you think of...?' }
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
                              placeholder={section.placeholder}
                              rows={4}
                            />
                          </FormControl>
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
                    <div className="grid grid-cols-2 gap-4 mt-2">
                      <FormField
                        control={form.control}
                        name="formats"
                        render={({ field }) => (
                          <FormItem className="flex flex-row items-start space-x-3 space-y-0">
                            <FormControl>
                              <Checkbox
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
                              checked={field.value}
                              onCheckedChange={field.onChange}
                              disabled={!project.cover_art?.image_url}
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
          </Tabs>

          <div className="flex justify-end space-x-4 pt-6 border-t">
            <Button type="button" variant="outline" onClick={() => window.history.back()}>
              Cancel
            </Button>
            <Button 
              type="submit" 
              disabled={isLoading || !form.watch('formats')?.length}
              className="gap-2"
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