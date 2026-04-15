'use client'

import { useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { AutoCompleteBookManager } from '@/components/AutoCompleteBookManager'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { BoltIcon, InformationCircleIcon, CheckCircleIcon, BookOpenIcon } from '@heroicons/react/24/outline'
import ProjectLayout from '@/components/layout/ProjectLayout'

export default function AutoCompletePage() {
  const params = useParams()
  const router = useRouter()
  const projectId = params?.projectId as string
  const [jobComplete, setJobComplete] = useState(false)

  if (!projectId) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 mb-4">Invalid Project</h1>
          <p className="text-gray-600">Project ID is required for Auto-Complete.</p>
        </div>
      </div>
    )
  }

  return (
    <ProjectLayout projectId={projectId}>
      <div className="py-8">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 md:px-8 lg:px-8">
          {/* Header Section */}
          <div className="mb-8">
            <div className="flex items-center space-x-3 mb-4">
              <div className="w-12 h-12 bg-gray-900 rounded-xl flex items-center justify-center">
                <BoltIcon className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-3xl font-bold text-gray-900 tracking-tight">Auto-Complete</h1>
                <p className="text-gray-500">Let AI write your entire book automatically</p>
              </div>
            </div>

            {/* Info Card */}
            <Card className="bg-white border border-gray-200">
              <CardContent className="p-6">
                <div className="flex items-start space-x-3">
                  <InformationCircleIcon className="w-6 h-6 text-gray-400 mt-1 flex-shrink-0" />
                  <div className="space-y-2">
                    <h3 className="font-semibold text-gray-900">How Auto-Complete Works</h3>
                    <div className="text-sm text-gray-600 space-y-1">
                      <p>• AI analyzes your book bible and generates a complete manuscript</p>
                      <p>• Each chapter goes through multiple quality passes for consistency</p>
                      <p>• You'll receive cost estimates before any work begins</p>
                      <p>• Progress is tracked in real-time with the ability to pause/resume</p>
                    </div>
                    <div className="mt-3 p-3 bg-gray-50 rounded-lg">
                      <p className="text-xs text-gray-600 font-medium">
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
                <BoltIcon className="w-5 h-5 text-indigo-500" />
                <span>Auto-Complete Manager</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {jobComplete ? (
                <div className="text-center py-12">
                  <div className="w-20 h-20 mx-auto bg-gradient-to-br from-emerald-100 to-emerald-200 rounded-full flex items-center justify-center mb-6">
                    <CheckCircleIcon className="w-10 h-10 text-emerald-600" />
                  </div>
                  <h3 className="text-2xl font-bold text-gray-900 mb-3">Your Book Is Complete!</h3>
                  <p className="text-gray-600 mb-8 max-w-md mx-auto">
                    All chapters have been generated and passed quality checks. You can review, edit, and publish your manuscript.
                  </p>
                  <div className="flex flex-col sm:flex-row gap-3 justify-center">
                    <button
                      onClick={() => router.push(`/project/${projectId}/chapters`)}
                      className="inline-flex items-center justify-center gap-2 px-6 py-3 bg-gray-900 text-white rounded-xl font-semibold hover:bg-gray-800 transition shadow-lg"
                    >
                      <BookOpenIcon className="w-5 h-5" />
                      Review Chapters
                    </button>
                    <button
                      onClick={() => router.push(`/project/${projectId}/publish`)}
                      className="inline-flex items-center justify-center gap-2 px-6 py-3 bg-white text-gray-700 border border-gray-200 rounded-xl font-semibold hover:bg-gray-50 transition"
                    >
                      Publish Book
                    </button>
                    <button
                      onClick={() => setJobComplete(false)}
                      className="inline-flex items-center justify-center gap-2 px-6 py-3 text-gray-500 hover:text-gray-700 transition text-sm"
                    >
                      Start Another Run
                    </button>
                  </div>
                </div>
              ) : (
                <AutoCompleteBookManager
                  projectId={projectId}
                  onJobStarted={(jobId) => {
                    console.log('Auto-complete job started:', jobId)
                  }}
                  onJobCompleted={(jobId) => {
                    console.log('Auto-complete job completed:', jobId)
                    setJobComplete(true)
                  }}
                />
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </ProjectLayout>
  )
}