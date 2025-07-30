'use client'

/**
 * @deprecated This component is being replaced by the new TopNav layout.
 * Still used in project pages but will be removed in a future update.
 * New development should use TopNav + AppLayout pattern.
 */

import React, { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import { 
  ChevronLeftIcon, 
  ChevronRightIcon,
  DocumentTextIcon,
  ChartBarIcon,
  InformationCircleIcon,
  CheckCircleIcon,
  ClockIcon
} from '@heroicons/react/24/outline'
import { useAuthToken } from '@/lib/auth'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

interface ReferenceQuickAccess {
  name: string
  type: string
  preview: string
  lastModified?: string
}

interface ProjectOverview {
  title: string
  genre: string
  status: string
  chaptersCompleted: number
  totalChapters: number
  wordCount: number
}

interface QualityMetrics {
  pacingScore: number
  continuityScore: number
  aiConfidence: number
}

interface CollapsibleSidebarProps {
  isOpen: boolean
  onToggle: () => void
  className?: string
}

export function CollapsibleSidebar({ isOpen, onToggle, className = '' }: CollapsibleSidebarProps) {
  const params = useParams()
  const projectId = params?.projectId as string
  const { getAuthHeaders, isSignedIn } = useAuthToken()

  const [references, setReferences] = useState<ReferenceQuickAccess[]>([])
  const [overview, setOverview] = useState<ProjectOverview | null>(null)
  const [metrics, setMetrics] = useState<QualityMetrics | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (isSignedIn && projectId && isOpen) {
      loadSidebarData()
    }
  }, [isSignedIn, projectId, isOpen])

  const loadSidebarData = async () => {
    if (!projectId) return

    setLoading(true)
    try {
      const authHeaders = await getAuthHeaders()

      // Load reference files for quick access
      const referencesResponse = await fetch(`/api/references?project_id=${projectId}`, {
        headers: authHeaders
      })
      
      if (referencesResponse.ok) {
        const referencesData = await referencesResponse.json()
        if (referencesData.success && referencesData.files) {
          const quickAccess = referencesData.files.slice(0, 3).map((file: any) => ({
            name: file.name.replace('.md', ''),
            type: file.name,
            preview: file.content?.substring(0, 100) + '...' || 'No content',
            lastModified: file.lastModified
          }))
          setReferences(quickAccess)
        }
      }

      // Load project overview
      const projectResponse = await fetch(`/api/project/status?project_id=${projectId}`, {
        headers: authHeaders
      })
      
      if (projectResponse.ok) {
        const projectData = await projectResponse.json()
        if (projectData.project_ready) {
          setOverview({
            title: projectData.metadata?.title || 'Untitled',
            genre: projectData.settings?.genre || 'Fiction',
            status: projectData.metadata?.status || 'active',
            chaptersCompleted: projectData.progress?.chapters_completed || 0,
            totalChapters: projectData.settings?.target_chapters || 25,
            wordCount: projectData.progress?.total_words || 0
          })
        }
      }

      // Mock quality metrics (would be real in production)
      setMetrics({
        pacingScore: 85,
        continuityScore: 92,
        aiConfidence: 88
      })

    } catch (error) {
      console.error('Error loading sidebar data:', error)
    } finally {
      setLoading(false)
    }
  }

  const formatNumber = (num: number) => {
    return num.toLocaleString()
  }

  const getScoreColor = (score: number) => {
    if (score >= 90) return 'text-green-600'
    if (score >= 80) return 'text-yellow-600'
    return 'text-red-600'
  }

  return (
    <>
      {/* Overlay for mobile */}
      {isOpen && (
        <div 
          className="fixed inset-0 bg-black bg-opacity-50 z-40 lg:hidden"
          onClick={onToggle}
        />
      )}

      {/* Sidebar */}
      <div className={`
        fixed top-0 right-0 h-full bg-white border-l border-gray-200 
        transform transition-transform duration-300 ease-in-out z-50
        ${isOpen ? 'translate-x-0' : 'translate-x-full'}
        w-80 shadow-lg
        ${className}
      `}>
        {/* Toggle Button */}
        <Button
          onClick={onToggle}
          variant="ghost"
          size="sm"
          className="absolute -left-10 top-4 bg-white border border-gray-200 rounded-l-md rounded-r-none shadow-md"
        >
          {isOpen ? (
            <ChevronRightIcon className="w-4 h-4" />
          ) : (
            <ChevronLeftIcon className="w-4 h-4" />
          )}
        </Button>

        {/* Sidebar Content */}
        <div className="h-full overflow-y-auto p-4 space-y-6">
          <div className="flex items-center justify-between border-b border-gray-200 pb-4">
            <h2 className="text-lg font-semibold text-gray-900">Quick Access</h2>
          </div>

          {loading ? (
            <div className="space-y-4">
              {[1, 2, 3].map(i => (
                <div key={i} className="animate-pulse">
                  <div className="h-4 bg-gray-200 rounded w-3/4 mb-2"></div>
                  <div className="h-3 bg-gray-200 rounded w-full"></div>
                </div>
              ))}
            </div>
          ) : (
            <>
              {/* Reference Quick Access */}
              <div className="space-y-3">
                <div className="flex items-center space-x-2">
                  <DocumentTextIcon className="w-5 h-5 text-gray-600" />
                  <h3 className="text-sm font-medium text-gray-900">References</h3>
                </div>
                
                {references.length > 0 ? (
                  <div className="space-y-2">
                    {references.map((ref, index) => (
                      <Card key={index} className="p-3 hover:bg-gray-50 cursor-pointer">
                        <div className="space-y-1">
                          <div className="flex items-center justify-between">
                            <h4 className="text-xs font-medium text-gray-900 capitalize">
                              {ref.name}
                            </h4>
                            <CheckCircleIcon className="w-3 h-3 text-green-600" />
                          </div>
                          <p className="text-xs text-gray-600 line-clamp-2">
                            {ref.preview}
                          </p>
                        </div>
                      </Card>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-gray-500">No references available</p>
                )}
              </div>

              {/* Project Overview */}
              {overview && (
                <div className="space-y-3">
                  <div className="flex items-center space-x-2">
                    <InformationCircleIcon className="w-5 h-5 text-gray-600" />
                    <h3 className="text-sm font-medium text-gray-900">Project Overview</h3>
                  </div>
                  
                  <Card className="p-3">
                    <div className="space-y-2">
                      <div>
                        <h4 className="text-sm font-medium text-gray-900">{overview.title}</h4>
                        <p className="text-xs text-gray-600">{overview.genre}</p>
                      </div>
                      
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-gray-600">Progress:</span>
                        <span className="font-medium">
                          {overview.chaptersCompleted}/{overview.totalChapters}
                        </span>
                      </div>
                      
                      <div className="w-full bg-gray-200 rounded-full h-1.5">
                        <div 
                          className="bg-blue-600 h-1.5 rounded-full"
                          style={{ 
                            width: `${(overview.chaptersCompleted / overview.totalChapters) * 100}%` 
                          }}
                        />
                      </div>
                      
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-gray-600">Words:</span>
                        <span className="font-medium">{formatNumber(overview.wordCount)}</span>
                      </div>
                      
                      <div className="flex items-center space-x-1 text-xs">
                        <div className={`w-2 h-2 rounded-full ${
                          overview.status === 'active' ? 'bg-green-500' : 'bg-gray-400'
                        }`} />
                        <span className="text-gray-600 capitalize">{overview.status}</span>
                      </div>
                    </div>
                  </Card>
                </div>
              )}

              {/* Quality Metrics */}
              {metrics && (
                <div className="space-y-3">
                  <div className="flex items-center space-x-2">
                    <ChartBarIcon className="w-5 h-5 text-gray-600" />
                    <h3 className="text-sm font-medium text-gray-900">Quality Metrics</h3>
                  </div>
                  
                  <Card className="p-3">
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-gray-600">Pacing</span>
                        <span className={`text-xs font-medium ${getScoreColor(metrics.pacingScore)}`}>
                          {metrics.pacingScore}%
                        </span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-1">
                        <div 
                          className="bg-blue-600 h-1 rounded-full"
                          style={{ width: `${metrics.pacingScore}%` }}
                        />
                      </div>
                      
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-gray-600">Continuity</span>
                        <span className={`text-xs font-medium ${getScoreColor(metrics.continuityScore)}`}>
                          {metrics.continuityScore}%
                        </span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-1">
                        <div 
                          className="bg-green-600 h-1 rounded-full"
                          style={{ width: `${metrics.continuityScore}%` }}
                        />
                      </div>
                      
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-gray-600">AI Confidence</span>
                        <span className={`text-xs font-medium ${getScoreColor(metrics.aiConfidence)}`}>
                          {metrics.aiConfidence}%
                        </span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-1">
                        <div 
                          className="bg-purple-600 h-1 rounded-full"
                          style={{ width: `${metrics.aiConfidence}%` }}
                        />
                      </div>
                    </div>
                  </Card>
                </div>
              )}

              {/* Last Updated */}
              <div className="pt-4 border-t border-gray-200">
                <div className="flex items-center space-x-2 text-xs text-gray-500">
                  <ClockIcon className="w-3 h-3" />
                  <span>Updated just now</span>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  )
}

export default CollapsibleSidebar 