'use client'

import { useState, useEffect } from 'react'
import { useAuthToken } from '@/lib/auth'
import { useProject } from '@/hooks/useFirestore'
import { CheckCircleIcon, ExclamationTriangleIcon, InformationCircleIcon, FolderIcon } from '@heroicons/react/24/outline'

interface ProjectStatusProps {
  projectId?: string | null
}

export function ProjectStatus({ projectId }: ProjectStatusProps) {
  const { getAuthHeaders, isLoaded, isSignedIn } = useAuthToken()
  const [apiStatus, setApiStatus] = useState<any>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  
  // Get real-time project data from Firestore
  const { project, loading: projectLoading, error: projectError } = useProject(projectId || null)

  useEffect(() => {
    // Only fetch API status if user is authenticated and we have a project
    if (isLoaded && isSignedIn && projectId) {
      fetchProjectStatus()
    }
  }, [isLoaded, isSignedIn, projectId])

  const fetchProjectStatus = async () => {
    if (!isSignedIn || !projectId) return
    
    setIsLoading(true)
    setError('')
    
    try {
      const authHeaders = await getAuthHeaders()
      
      const statusUrl = `/api/project/status?project_id=${projectId}`
      
      const response = await fetch(statusUrl, {
        headers: authHeaders
      })
      
      if (response.ok) {
        const data = await response.json()
        setApiStatus(data)
      } else {
        const errorData = await response.json()
        setError(errorData.error || 'Failed to fetch project status')
      }
    } catch (error) {
      console.error('ProjectStatus - network error:', error)
      setError('Network error fetching project status')
    } finally {
      setIsLoading(false)
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

  // Show project selection prompt if no project is selected
  if (!projectId) {
    return (
      <div className="card">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Project Status
        </h2>
        <div className="text-center py-8">
          <div className="text-gray-500 mb-4">No project selected</div>
          <p className="text-sm text-gray-400">
            Upload a book bible or select a project to view status.
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

  // Determine overall project readiness from Firestore data
  const hasBookBible = !!project?.book_bible?.content
  const hasMetadata = !!project?.metadata
  const hasSettings = !!project?.settings
  const isProjectReady = hasBookBible && hasMetadata && hasSettings

  // Combine Firestore and API status
  const combinedLoading = projectLoading || isLoading
  const combinedError = projectError || error

  return (
    <div className="card">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">
        Project Status
        {combinedLoading && (
          <span className="ml-2 text-sm text-blue-600">
            <div className="inline-block w-2 h-2 bg-blue-600 rounded-full animate-pulse"></div>
            Syncing...
          </span>
        )}
      </h2>

      {combinedLoading && !project && (
        <div className="flex items-center justify-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
        </div>
      )}

      {combinedError && (
        <div className="p-4 bg-red-50 rounded-md">
          <div className="flex">
            <ExclamationTriangleIcon className="w-5 h-5 text-red-400 mr-2" />
            <p className="text-sm text-red-800">{combinedError instanceof Error ? combinedError.message : combinedError}</p>
          </div>
        </div>
      )}

      {project && (
        <div className="space-y-4">
          {/* Overall Status */}
          <div className={`p-4 rounded-lg ${getStatusBg(isProjectReady)}`}>
            <div className="flex items-center">
              {getStatusIcon(isProjectReady)}
              <div className="ml-3">
                <h3 className={`text-sm font-medium ${getStatusColor(isProjectReady)}`}>
                  {isProjectReady ? 'Project Ready' : 'Project Setup Incomplete'}
                </h3>
                <p className={`text-sm ${getStatusColor(isProjectReady)}`}>
                  {isProjectReady 
                    ? 'All components are configured and ready for generation'
                    : 'Some required components are missing'
                  }
                </p>
              </div>
            </div>
          </div>

          {/* Project Metadata from Firestore */}
          {project.metadata && (
            <div className="p-4 bg-blue-50 rounded-lg">
              <h3 className="text-sm font-medium text-blue-900 mb-2">Project Information</h3>
              <div className="space-y-1 text-sm text-blue-800">
                {project.metadata.title && <p><strong>Title:</strong> {project.metadata.title}</p>}
                {project.settings?.genre && <p><strong>Genre:</strong> {project.settings.genre}</p>}
                {project.metadata.status && <p><strong>Status:</strong> {project.metadata.status}</p>}
                {project.metadata.created_at && (
                  <p><strong>Created:</strong> {new Date(project.metadata.created_at.seconds * 1000).toLocaleDateString()}</p>
                )}
                {project.progress && (
                  <p><strong>Progress:</strong> {project.progress.chapters_completed || 0} chapters completed</p>
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
                  {getStatusIcon(hasBookBible)}
                  <span className="ml-2 text-sm font-medium text-gray-900">Book Bible</span>
                </div>
                <span className={`text-xs px-2 py-1 rounded-full ${
                  hasBookBible ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                }`}>
                  {hasBookBible ? 'Present' : 'Missing'}
                </span>
              </div>

              <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div className="flex items-center">
                  {getStatusIcon(hasSettings)}
                  <span className="ml-2 text-sm font-medium text-gray-900">Project Settings</span>
                </div>
                <span className={`text-xs px-2 py-1 rounded-full ${
                  hasSettings ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                }`}>
                  {hasSettings ? 'Configured' : 'Missing'}
                </span>
              </div>

              <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div className="flex items-center">
                  {getStatusIcon(hasMetadata)}
                  <span className="ml-2 text-sm font-medium text-gray-900">Project Metadata</span>
                </div>
                <span className={`text-xs px-2 py-1 rounded-full ${
                  hasMetadata ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                }`}>
                  {hasMetadata ? 'Present' : 'Missing'}
                </span>
              </div>
            </div>
          </div>

          {/* Reference Files from API Status (fallback) */}
          {apiStatus?.referenceFiles && Array.isArray(apiStatus.referenceFiles) && apiStatus.referenceFiles.length > 0 && (
            <div className="pt-4 border-t">
              <h3 className="text-sm font-medium text-gray-900 mb-2">Reference Files</h3>
              <div className="space-y-1">
                {apiStatus.referenceFiles.map((file: string) => (
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
            disabled={combinedLoading}
            className="w-full btn-secondary"
          >
            {combinedLoading ? 'Refreshing...' : 'Refresh Status'}
          </button>
        </div>
      )}
    </div>
  )
} 