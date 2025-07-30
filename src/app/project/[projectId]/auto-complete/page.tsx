'use client'

import { useParams } from 'next/navigation'
import { useState, useEffect } from 'react'
import { useAuth } from '@clerk/nextjs'
import { AutoCompleteBookManager } from '@/components/AutoCompleteBookManager'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { BoltIcon, InformationCircleIcon } from '@heroicons/react/24/outline'

export default function AutoCompletePage() {
  const params = useParams()
  const { isLoaded, isSignedIn } = useAuth()
  const projectId = params?.projectId as string

  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    if (isLoaded) {
      setIsLoading(false)
    }
  }, [isLoaded])

  if (isLoading) {
    return (
      <div className="min-h-screen bg-brand-off-white py-8">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="animate-pulse space-y-6">
            <div className="h-32 bg-gray-200 rounded-xl"></div>
            <div className="h-96 bg-gray-200 rounded-xl"></div>
          </div>
        </div>
      </div>
    )
  }

  if (!isSignedIn) {
    return (
      <div className="min-h-screen bg-brand-off-white flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 mb-4">Please Sign In</h1>
          <p className="text-gray-600">You need to be signed in to use Auto-Complete.</p>
        </div>
      </div>
    )
  }

  if (!projectId) {
    return (
      <div className="min-h-screen bg-brand-off-white flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 mb-4">Invalid Project</h1>
          <p className="text-gray-600">Project ID is required for Auto-Complete.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-brand-off-white py-8">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header Section */}
        <div className="mb-8">
          <div className="flex items-center space-x-3 mb-4">
            <div className="w-12 h-12 bg-gradient-to-r from-brand-forest to-brand-lavender rounded-xl flex items-center justify-center">
              <BoltIcon className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-brand-forest">Auto-Complete</h1>
              <p className="text-brand-forest/70">Let AI write your entire book automatically</p>
            </div>
          </div>

          {/* Info Card */}
          <Card className="bg-gradient-to-r from-blue-50 to-indigo-50 border-blue-200">
            <CardContent className="p-6">
              <div className="flex items-start space-x-3">
                <InformationCircleIcon className="w-6 h-6 text-blue-600 mt-1 flex-shrink-0" />
                <div className="space-y-2">
                  <h3 className="font-semibold text-blue-900">How Auto-Complete Works</h3>
                  <div className="text-sm text-blue-800 space-y-1">
                    <p>• AI analyzes your book bible and generates a complete manuscript</p>
                    <p>• Each chapter goes through multiple quality passes for consistency</p>
                    <p>• You'll receive cost estimates before any work begins</p>
                    <p>• Progress is tracked in real-time with the ability to pause/resume</p>
                  </div>
                  <div className="mt-3 p-3 bg-blue-100 rounded-lg">
                    <p className="text-xs text-blue-700 font-medium">
                      💡 <strong>Tip:</strong> Make sure your References are complete before starting Auto-Complete for best results.
                    </p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Auto-Complete Manager */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center space-x-2">
              <BoltIcon className="w-5 h-5 text-brand-soft-purple" />
              <span>Auto-Complete Manager</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <AutoCompleteBookManager 
              projectId={projectId}
              onJobStarted={(jobId) => {
                console.log('Auto-complete job started:', jobId)
              }}
              onJobCompleted={(jobId, result) => {
                console.log('Auto-complete job completed:', jobId, result)
              }}
            />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

// Force dynamic rendering to prevent build-time issues
export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'