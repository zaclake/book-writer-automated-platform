'use client'

import React, { useState, useEffect } from 'react'
import { useAuth, useUser } from '@clerk/nextjs'
import { Button } from './ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card'
import { Textarea } from './ui/textarea'
import { CreativeLoader } from './ui/CreativeLoader'
import { Alert, AlertDescription } from './ui/alert'
import { Badge } from './ui/badge'
import { Download, Image as ImageIcon, RefreshCw, Sparkles, AlertCircle } from 'lucide-react'

interface CoverArtGeneratorProps {
  projectId: string
}

interface ReferenceProgress {
  status: string
  progress: number
  stage: string
  message: string
  completed: boolean
}

interface CoverArtStatus {
  job_id?: string
  status: string
  image_url?: string
  prompt?: string
  error?: string
  message: string
  created_at?: string
  completed_at?: string
  attempt_number?: number
  service_available?: boolean
}

export function CoverArtGenerator({ projectId }: CoverArtGeneratorProps) {
  const { getToken } = useAuth()
  
  // State management
  const [referenceProgress, setReferenceProgress] = useState<ReferenceProgress | null>(null)
  const [coverArtStatus, setCoverArtStatus] = useState<CoverArtStatus | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [isPolling, setIsPolling] = useState(false)
  const [userFeedback, setUserFeedback] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [showFeedbackForm, setShowFeedbackForm] = useState(false)
  const [includeTitle, setIncludeTitle] = useState(true)
  const [includeAuthor, setIncludeAuthor] = useState(true)
  const [titleText, setTitleText] = useState('')
  const [authorText, setAuthorText] = useState('')

  // Check reference progress on mount
  useEffect(() => {
    checkReferenceProgress()
    checkCoverArtStatus()
  }, [projectId])

  // After projectId effect, fetch project title and user name
  useEffect(() => {
    const initDefaults = async () => {
      try {
        const token = await getToken()
        // fetch project
        const projRes = await fetch(`/api/projects/${projectId}`, { headers: { 'Authorization': `Bearer ${token}` } })
        if (projRes.ok) {
          const data = await projRes.json()
          const p = data.project || data
          if (p?.metadata?.title) {
            setTitleText(p.metadata.title)
          }
        }
      } catch {}
    }
    initDefaults()
  }, [projectId, getToken])

  // also fetch user info via Clerk
  const { user } = useUser()
  useEffect(() => {
    if (user) {
      setAuthorText(user.fullName || user.username || '')
    }
  }, [user])

  // Polling for cover art status updates
  useEffect(() => {
    let pollInterval: NodeJS.Timeout | null = null
    
    if (isPolling && coverArtStatus?.status === 'pending') {
      pollInterval = setInterval(() => {
        checkCoverArtStatus()
      }, 3000) // Poll every 3 seconds
    }
    
    return () => {
      if (pollInterval) {
        clearInterval(pollInterval)
      }
    }
  }, [isPolling, coverArtStatus?.status])

  const checkReferenceProgress = async () => {
    try {
      const token = await getToken()
      const response = await fetch(`/api/projects/${projectId}/references/progress`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      })

      if (response.ok) {
        const data = await response.json()
        setReferenceProgress(data)
      }
    } catch (error) {
      console.error('Failed to check reference progress:', error)
    }
  }

  const checkCoverArtStatus = async () => {
    try {
      const token = await getToken()
      const response = await fetch(`/api/cover-art/${projectId}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      })

      if (response.ok) {
        const data = await response.json()
        setCoverArtStatus(data)
        
        // Stop polling if completed or failed
        if (data.status === 'completed' || data.status === 'failed') {
          setIsPolling(false)
          setIsGenerating(false)
        }
      }
    } catch (error) {
      console.error('Failed to check cover art status:', error)
    }
  }

  const generateCoverArt = async (regenerate = false) => {
    try {
      setError(null)
      setIsGenerating(true)
      setIsPolling(true)

      const token = await getToken()
      const requestBody: any = {
        user_feedback: regenerate ? userFeedback : undefined,
        regenerate,
        options: {
          include_title: includeTitle,
          include_author: includeAuthor,
          title_text: titleText,
          author_text: authorText
        }
      }

      const response = await fetch(`/api/cover-art/${projectId}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestBody)
      })

      const data = await response.json()

      if (response.ok) {
        setCoverArtStatus({
          job_id: data.job_id,
          status: 'pending',
          message: data.message
        })
        
        if (regenerate) {
          setUserFeedback('')
          setShowFeedbackForm(false)
        }
      } else {
        setError(data.error || 'Failed to start cover art generation')
        setIsGenerating(false)
        setIsPolling(false)
      }
    } catch (error) {
      console.error('Failed to generate cover art:', error)
      setError('Failed to start cover art generation')
      setIsGenerating(false)
      setIsPolling(false)
    }
  }

  const downloadCoverArt = () => {
    if (coverArtStatus?.image_url) {
      // Create a link element and trigger download
      const link = document.createElement('a')
      link.href = coverArtStatus.image_url
      link.download = `cover-art-${projectId}.jpg`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
    }
  }

  // Check if references are completed and service is available
  const referencesCompleted = referenceProgress?.completed === true
  const serviceAvailable = coverArtStatus?.service_available !== false // Default to true if unknown
  const canGenerateCoverArt = referencesCompleted && serviceAvailable && !isGenerating

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5" />
            AI Cover Art Generator
          </CardTitle>
          <CardDescription>
            Generate professional book cover art using AI based on your reference files and book content.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Reference Progress Check */}
          {referenceProgress && (
            <div className="flex items-center gap-2">
              <Badge variant={referencesCompleted ? "default" : "secondary"}>
                {referencesCompleted ? "✓ References Complete" : "References In Progress"}
              </Badge>
              {!referencesCompleted && (
                <span className="text-sm text-muted-foreground">
                  {referenceProgress.progress}% - {referenceProgress.stage}
                </span>
              )}
            </div>
          )}

          {/* Error Display */}
          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {/* Cover Art Status */}
          {coverArtStatus && (
            <div className="space-y-4">
              {coverArtStatus.status === 'pending' && (
                <div className="text-center py-8">
                  <CreativeLoader 
                    message="Generating your cover art..."
                    subMessage="This may take 30-60 seconds"
                  />
                </div>
              )}

              {coverArtStatus.status === 'completed' && coverArtStatus.image_url && (
                <div className="space-y-4">
                  <div className="text-center">
                    <img 
                      src={coverArtStatus.image_url} 
                      alt="Generated Cover Art"
                      className="max-w-sm mx-auto rounded-lg shadow-lg border"
                    />
                  </div>
                  
                  <div className="flex gap-2 justify-center">
                    <Button onClick={downloadCoverArt} variant="outline">
                      <Download className="h-4 w-4 mr-2" />
                      Download Cover
                    </Button>
                    <Button 
                      onClick={() => setShowFeedbackForm(true)}
                      variant="outline"
                    >
                      <RefreshCw className="h-4 w-4 mr-2" />
                      Regenerate
                    </Button>
                  </div>

                  {coverArtStatus.prompt && (
                    <details className="mt-4">
                      <summary className="text-sm font-medium cursor-pointer">
                        View AI Prompt Used
                      </summary>
                      <p className="text-sm text-muted-foreground mt-2 p-3 bg-muted rounded">
                        {coverArtStatus.prompt}
                      </p>
                    </details>
                  )}
                </div>
              )}

              {coverArtStatus.status === 'failed' && (
                <Alert variant="destructive">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>
                    {coverArtStatus.error || 'Cover art generation failed'}
                  </AlertDescription>
                </Alert>
              )}
            </div>
          )}

          {/* Feedback Form for Regeneration */}
          {showFeedbackForm && (
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Improve Your Cover Art</CardTitle>
                <CardDescription>
                  Describe what you'd like to change or improve in the next generation.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <Textarea
                  placeholder="e.g., Make it darker and more mysterious, add a castle in the background, use warmer colors..."
                  value={userFeedback}
                  onChange={(e) => setUserFeedback(e.target.value)}
                  rows={3}
                />
                <div className="flex gap-2">
                  <Button 
                    onClick={() => generateCoverArt(true)}
                    disabled={!canGenerateCoverArt}
                  >
                    <Sparkles className="h-4 w-4 mr-2" />
                    Generate New Version
                  </Button>
                  <Button 
                    variant="outline" 
                    onClick={() => setShowFeedbackForm(false)}
                  >
                    Cancel
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Initial Generation Button */}
          {(!coverArtStatus || coverArtStatus.status === 'not_started') && (
            <div className="text-center space-y-4">
              {/* Title/Author Options */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-left">
                <div className="space-y-2">
                  <label className="flex items-center gap-2 text-sm font-medium">
                    <input type="checkbox" checked={includeTitle} onChange={e=>setIncludeTitle(e.target.checked)} /> Include Title
                  </label>
                  {includeTitle && (
                    <Textarea value={titleText} onChange={e=>setTitleText(e.target.value)} rows={1} />
                  )}
                </div>
                <div className="space-y-2">
                  <label className="flex items-center gap-2 text-sm font-medium">
                    <input type="checkbox" checked={includeAuthor} onChange={e=>setIncludeAuthor(e.target.checked)} /> Include Author
                  </label>
                  {includeAuthor && (
                    <Textarea value={authorText} onChange={e=>setAuthorText(e.target.value)} rows={1} />
                  )}
                </div>
              </div>
              {!referencesCompleted && (
                <div className="p-4 bg-muted rounded-lg">
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <AlertCircle className="h-4 w-4" />
                    <span className="text-sm">
                      Cover art generation will be available once your reference files are completed.
                    </span>
                  </div>
                </div>
              )}
              
              {referencesCompleted && !serviceAvailable && (
                <div className="p-4 bg-muted rounded-lg">
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <AlertCircle className="h-4 w-4" />
                    <span className="text-sm">
                      Cover art generation service is currently unavailable. Please check configuration.
                    </span>
                  </div>
                </div>
              )}
              
              <Button 
                onClick={() => generateCoverArt(false)}
                disabled={!canGenerateCoverArt}
                size="lg"
                className="relative"
              >
                <ImageIcon className="h-4 w-4 mr-2" />
                Generate Cover Art
                {(!referencesCompleted || !serviceAvailable) && (
                  <span className="absolute -top-1 -right-1 h-3 w-3 bg-yellow-500 rounded-full animate-pulse" />
                )}
              </Button>
              
              {referencesCompleted && (
                <p className="text-sm text-muted-foreground">
                  AI will analyze your book content and reference files to create a professional cover design.
                </p>
              )}
            </div>
          )}

          {/* Technical Info */}
          <div className="text-xs text-muted-foreground space-y-1">
            <p>• Generated covers meet Kindle Direct Publishing specifications</p>
            <p>• 1600x2560 pixels, high resolution, professional quality</p>
            <p>• Based on your book's genre, characters, setting, and themes</p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
} 