'use client'

import React from 'react'
import { Progress } from '@/components/ui/progress'
import { Card, CardContent } from '@/components/ui/card'
import { Clock, BookOpen, CheckCircle, AlertCircle } from 'lucide-react'

interface JobProgressBannerProps {
  jobId: string
  status: 'running' | 'completed' | 'failed' | 'pending'
  progressPercentage?: number
  currentChapter?: number
  totalChapters?: number
  estimatedTimeRemaining?: string
  detailedStatus?: string
  onDismiss?: () => void
}

export default function JobProgressBanner({
  jobId,
  status,
  progressPercentage = 0,
  currentChapter = 0,
  totalChapters = 0,
  estimatedTimeRemaining,
  detailedStatus,
  onDismiss
}: JobProgressBannerProps) {
  const getStatusIcon = () => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="h-5 w-5 text-green-600" />
      case 'failed':
        return <AlertCircle className="h-5 w-5 text-red-600" />
      case 'running':
      case 'pending':
        return <BookOpen className="h-5 w-5 text-blue-600 animate-pulse" />
      default:
        return <BookOpen className="h-5 w-5 text-gray-600" />
    }
  }

  const getStatusMessage = () => {
    switch (status) {
      case 'completed':
        return 'Book generation completed successfully!'
      case 'failed':
        return 'Book generation encountered an error.'
      case 'running':
        return 'Book generation in progress'
      case 'pending':
        return 'Book generation starting...'
      default:
        return 'Processing...'
    }
  }

  const getStatusColor = () => {
    switch (status) {
      case 'completed':
        return 'border-green-200 bg-green-50'
      case 'failed':
        return 'border-red-200 bg-red-50'
      case 'running':
      case 'pending':
        return 'border-blue-200 bg-blue-50'
      default:
        return 'border-gray-200 bg-gray-50'
    }
  }

  return (
    <Card className={`mb-6 ${getStatusColor()}`}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div className="flex items-center space-x-3 flex-1">
            {getStatusIcon()}
            <div className="flex-1">
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-medium text-gray-900">
                  {getStatusMessage()}
                </h3>
                {onDismiss && (status === 'completed' || status === 'failed') && (
                  <button
                    onClick={onDismiss}
                    className="text-gray-400 hover:text-gray-600 text-sm"
                  >
                    ✕
                  </button>
                )}
              </div>

              {status === 'running' && (
                <>
                  <div className="mb-3">
                    <div className="flex items-center justify-between text-sm text-gray-600 mb-1">
                      <span>
                        Chapter {currentChapter} of {totalChapters}
                      </span>
                      <span>{Math.round(progressPercentage)}% complete</span>
                    </div>
                    <Progress value={progressPercentage} className="h-2" />
                  </div>

                  <div className="text-sm text-gray-600 space-y-1">
                    {detailedStatus && (
                      <p className="flex items-center space-x-2">
                        <BookOpen className="h-4 w-4" />
                        <span>{detailedStatus}</span>
                      </p>
                    )}
                    
                    {estimatedTimeRemaining && (
                      <p className="flex items-center space-x-2">
                        <Clock className="h-4 w-4" />
                        <span>Estimated time remaining: {estimatedTimeRemaining}</span>
                      </p>
                    )}

                    <div className="mt-2 p-3 bg-blue-100 rounded-md">
                      <p className="text-sm text-blue-800">
                        💡 <strong>You can safely navigate away!</strong> This process typically takes 30-45 minutes. 
                        Feel free to close this tab or browse other pages – your book generation continues on the server. 
                        Come back anytime to check progress.
                      </p>
                    </div>
                  </div>
                </>
              )}

              {status === 'pending' && (
                <div className="text-sm text-gray-600">
                  <div className="mt-2 p-3 bg-blue-100 rounded-md">
                    <p className="text-sm text-blue-800">
                      🚀 Starting your book generation... This typically takes 30-45 minutes. 
                      You can safely close this tab and return later.
                    </p>
                  </div>
                </div>
              )}

              {status === 'completed' && (
                <p className="text-sm text-green-600">
                  Your book has been generated successfully! Check the chapters section to review your content.
                </p>
              )}

              {status === 'failed' && (
                <p className="text-sm text-red-600">
                  Something went wrong during generation. Please try again or contact support if the issue persists.
                </p>
              )}

              <div className="mt-2 text-xs text-gray-500">
                Job ID: {jobId}
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
