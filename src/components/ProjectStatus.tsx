'use client'

import { useState, useEffect } from 'react'
import { useAuthToken } from '@/lib/auth'
import { CheckCircleIcon, ExclamationTriangleIcon, InformationCircleIcon, FolderIcon } from '@heroicons/react/24/outline'

interface ProjectStatusData {
  initialized: boolean
  hasBookBible: boolean
  hasReferences: boolean
  hasState: boolean
  referenceFiles: string[]
  metadata: any
  message: string
}

export function ProjectStatus() {
  const { getAuthHeaders, isLoaded, isSignedIn } = useAuthToken()
  const [status, setStatus] = useState<ProjectStatusData | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    // Only fetch if user is authenticated
    if (isLoaded && isSignedIn) {
      fetchProjectStatus()
    }
  }, [isLoaded, isSignedIn])

  const fetchProjectStatus = async () => {
    if (!isSignedIn) return
    
    setIsLoading(true)
    setError('')
    
    console.log('=== PROJECT STATUS DEBUG START ===')
    console.log('isSignedIn:', isSignedIn)
    console.log('isLoaded:', isLoaded)
    
    try {
      console.log('Getting auth headers...')
      const authHeaders = await getAuthHeaders()
      console.log('Auth headers received:', Object.keys(authHeaders))
      console.log('Has Authorization header:', !!authHeaders.Authorization)
      
      // Try to get project_id from localStorage (from successful book bible upload)
      const lastProjectId = localStorage.getItem('lastProjectId')
      console.log('Last project ID from localStorage:', lastProjectId)
      
      const statusUrl = lastProjectId 
        ? `/api/project/status?project_id=${lastProjectId}`
        : '/api/project/status'
      
      console.log('Making status request to:', statusUrl)
      
      const response = await fetch(statusUrl, {
        headers: authHeaders
      })
      console.log('ProjectStatus - response status:', response.status)
      console.log('ProjectStatus - response headers:', Object.fromEntries(response.headers.entries()))
      
      if (response.ok) {
        const data = await response.json()
        console.log('ProjectStatus - status data:', data)
        setStatus(data)
      } else {
        const errorData = await response.json()
        console.log('ProjectStatus - error data:', errorData)
        setError(errorData.error || 'Failed to fetch project status')
      }
    } catch (error) {
      console.error('ProjectStatus - network error:', error)
      setError('Network error fetching project status')
    } finally {
      setIsLoading(false)
      console.log('=== PROJECT STATUS DEBUG END ===')
    }
  }

  // Show loading state while auth is initializing
  if (!isLoaded) {
    return (
      <div className="card">
        <div className="text-center py-8">
          <div className="animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-3/4 mx-auto mb-2"></div>
            <div className="h-4 bg-gray-200 rounded w-1/2 mx-auto"></div>
          </div>
        </div>
      </div>
    )
  }

  // Show sign-in prompt if user is not authenticated
  if (!isSignedIn) {
    return (
      <div className="card">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Project Status
        </h2>
        <div className="text-center py-8">
          <div className="text-gray-500 mb-4">Please sign in to view project status</div>
          <p className="text-sm text-gray-400">
            Authentication is required to access project information.
          </p>
        </div>
      </div>
    )
  }

  const getStatusIcon = (hasFeature: boolean) => {
    return hasFeature ? (
      <CheckCircleIcon className="w-5 h-5 text-green-600" />
    ) : (
      <ExclamationTriangleIcon className="w-5 h-5 text-red-600" />
    )
  }

  const getStatusColor = (hasFeature: boolean) => {
    return hasFeature ? 'text-green-800' : 'text-red-800'
  }

  const getStatusBg = (hasFeature: boolean) => {
    return hasFeature ? 'bg-green-50' : 'bg-red-50'
  }

  return (
    <div className="card">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">
        Project Status
      </h2>

      {isLoading && (
        <div className="flex items-center justify-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
        </div>
      )}

      {error && (
        <div className="p-4 bg-red-50 rounded-md">
          <div className="flex">
            <ExclamationTriangleIcon className="w-5 h-5 text-red-400 mr-2" />
            <p className="text-sm text-red-800">{error}</p>
          </div>
        </div>
      )}

      {status && !isLoading && (
        <div className="space-y-4">
          {/* Overall Status */}
          <div className={`p-4 rounded-lg ${getStatusBg(status.initialized)}`}>
            <div className="flex items-center">
              {getStatusIcon(status.initialized)}
              <div className="ml-3">
                <h3 className={`text-sm font-medium ${getStatusColor(status.initialized)}`}>
                  {status.initialized ? 'Project Ready' : 'Project Not Ready'}
                </h3>
                <p className={`text-sm ${getStatusColor(status.initialized)}`}>
                  {status.message}
                </p>
              </div>
            </div>
          </div>

          {/* Project Metadata */}
          {status.metadata && (
            <div className="p-4 bg-blue-50 rounded-lg">
              <h3 className="text-sm font-medium text-blue-900 mb-2">Project Information</h3>
              <div className="space-y-1 text-sm text-blue-800">
                {status.metadata.title && <p><strong>Title:</strong> {status.metadata.title}</p>}
                {status.metadata.genre && <p><strong>Genre:</strong> {status.metadata.genre}</p>}
                {status.metadata.created_at && (
                  <p><strong>Created:</strong> {new Date(status.metadata.created_at).toLocaleDateString()}</p>
                )}
              </div>
            </div>
          )}

          {/* Component Status */}
          <div className="space-y-3">
            <h3 className="text-sm font-medium text-gray-900">Components</h3>
            
            <div className="grid grid-cols-1 gap-2">
              <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div className="flex items-center">
                  {getStatusIcon(status.hasBookBible)}
                  <span className="ml-2 text-sm font-medium text-gray-900">Book Bible</span>
                </div>
                <span className={`text-xs px-2 py-1 rounded-full ${
                  status.hasBookBible ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                }`}>
                  {status.hasBookBible ? 'Present' : 'Missing'}
                </span>
              </div>

              <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div className="flex items-center">
                  {getStatusIcon(status.hasReferences)}
                  <span className="ml-2 text-sm font-medium text-gray-900">Reference Files</span>
                </div>
                <span className={`text-xs px-2 py-1 rounded-full ${
                  status.hasReferences ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                }`}>
                  {status.hasReferences ? `${status.referenceFiles?.length || 0} files` : 'Missing'}
                </span>
              </div>

              <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div className="flex items-center">
                  {getStatusIcon(status.hasState)}
                  <span className="ml-2 text-sm font-medium text-gray-900">Project State</span>
                </div>
                <span className={`text-xs px-2 py-1 rounded-full ${
                  status.hasState ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                }`}>
                  {status.hasState ? 'Initialized' : 'Missing'}
                </span>
              </div>
            </div>
          </div>

          {/* Reference Files List */}
          {status.referenceFiles && Array.isArray(status.referenceFiles) && status.referenceFiles.length > 0 && (
            <div className="pt-4 border-t">
              <h3 className="text-sm font-medium text-gray-900 mb-2">Reference Files</h3>
              <div className="space-y-1">
                {status.referenceFiles.map((file) => (
                  <div key={file} className="flex items-center text-sm text-gray-600">
                    <FolderIcon className="w-4 h-4 mr-2" />
                    {file}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Refresh Button */}
          <button
            onClick={fetchProjectStatus}
            disabled={isLoading}
            className="w-full btn-secondary"
          >
            {isLoading ? 'Refreshing...' : 'Refresh Status'}
          </button>
        </div>
      )}
    </div>
  )
} 