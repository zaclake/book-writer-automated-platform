'use client'

import { useState, useEffect } from 'react'
import { CheckCircleIcon, XCircleIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline'

export function SystemStatus() {
  const [status, setStatus] = useState<'checking' | 'healthy' | 'warning' | 'error'>('checking')
  const [details, setDetails] = useState<{
    api_connection?: boolean
    last_generation?: string
    system_load?: 'low' | 'medium' | 'high'
    errors_24h?: number
  }>({})
  const [error, setError] = useState('')
  const [lastChecked, setLastChecked] = useState<string>('')
  const [backendUrl, setBackendUrl] = useState('')
  const [fileOpsTest, setFileOpsTest] = useState<any>(null)
  const [isTestingFileOps, setIsTestingFileOps] = useState(false)

  useEffect(() => {
    checkSystemStatus()
    const interval = setInterval(checkSystemStatus, 30000) // Check every 30 seconds
    return () => clearInterval(interval)
  }, [])

  const checkSystemStatus = async () => {
    try {
      const response = await fetch('/api/status')
      if (response.ok) {
        const data = await response.json()
        setDetails(data)
        
        if (data.api_connection && data.errors_24h < 5) {
          setStatus('healthy')
        } else if (data.api_connection && data.errors_24h < 10) {
          setStatus('warning')
        } else {
          setStatus('error')
        }
      } else {
        setStatus('error')
      }
    } catch (error) {
      setStatus('error')
      console.error('Failed to check system status:', error)
    }
  }

  const testFileOperations = async () => {
    setIsTestingFileOps(true)
    setFileOpsTest(null)
    try {
      const response = await fetch('/api/debug/file-ops-test')
      if (response.ok) {
        const data = await response.json()
        setFileOpsTest(data)
      } else {
        const errorData = await response.json()
        setFileOpsTest({ error: errorData.error })
      }
    } catch (error) {
      setFileOpsTest({ error: 'Network error testing file operations' })
    } finally {
      setIsTestingFileOps(false)
    }
  }

  const getStatusIcon = () => {
    switch (status) {
      case 'healthy':
        return <CheckCircleIcon className="w-6 h-6 text-green-500" />
      case 'warning':
        return <ExclamationTriangleIcon className="w-6 h-6 text-yellow-500" />
      case 'error':
        return <XCircleIcon className="w-6 h-6 text-red-500" />
      default:
        return (
          <div className="w-6 h-6 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin"></div>
        )
    }
  }

  const getStatusText = () => {
    switch (status) {
      case 'healthy':
        return 'All Systems Operational'
      case 'warning':
        return 'Minor Issues Detected'
      case 'error':
        return 'System Issues'
      default:
        return 'Checking Status...'
    }
  }

  const getStatusColor = () => {
    switch (status) {
      case 'healthy':
        return 'text-green-600'
      case 'warning':
        return 'text-yellow-600'
      case 'error':
        return 'text-red-600'
      default:
        return 'text-gray-600'
    }
  }

  const getLoadColor = (load: string) => {
    switch (load) {
      case 'low':
        return 'text-green-600'
      case 'medium':
        return 'text-yellow-600'
      case 'high':
        return 'text-red-600'
      default:
        return 'text-gray-600'
    }
  }

  return (
    <div className="card">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">System Status</h2>
      
      <div className="space-y-4">
        {/* Overall Status */}
        <div className="flex items-center space-x-3">
          {getStatusIcon()}
          <div>
            <div className={`font-medium ${getStatusColor()}`}>
              {getStatusText()}
            </div>
            {status === 'checking' && (
              <div className="text-xs text-gray-500 mt-1">
                Verifying API connectivity...
              </div>
            )}
          </div>
        </div>

        {/* Status Details */}
        {status !== 'checking' && (
          <div className="space-y-3 pt-3 border-t">
            {/* API Connection */}
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-600">OpenAI API</span>
              <div className="flex items-center space-x-1">
                {details.api_connection ? (
                  <CheckCircleIcon className="w-4 h-4 text-green-500" />
                ) : (
                  <XCircleIcon className="w-4 h-4 text-red-500" />
                )}
                <span className="text-xs text-gray-500">
                  {details.api_connection ? 'Connected' : 'Disconnected'}
                </span>
              </div>
            </div>

            {/* Last Generation */}
            {details.last_generation && (
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-600">Last Generation</span>
                <span className="text-xs text-gray-500">
                  {details.last_generation}
                </span>
              </div>
            )}

            {/* System Load */}
            {details.system_load && (
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-600">System Load</span>
                <span className={`text-xs font-medium ${getLoadColor(details.system_load)}`}>
                  {details.system_load.toUpperCase()}
                </span>
              </div>
            )}

            {/* Error Count */}
            <div className="flex justify-between items-center">
              <span className="text-sm text-gray-600">Errors (24h)</span>
              <span className={`text-xs font-medium ${
                (details.errors_24h || 0) === 0 
                  ? 'text-green-600' 
                  : (details.errors_24h || 0) < 5 
                  ? 'text-yellow-600' 
                  : 'text-red-600'
              }`}>
                {details.errors_24h || 0}
              </span>
            </div>
          </div>
        )}

        {/* Quick Actions */}
        <div className="pt-3 border-t">
          <button
            onClick={checkSystemStatus}
            disabled={status === 'checking'}
            className="w-full btn-secondary text-xs py-1"
          >
            {status === 'checking' ? 'Checking...' : 'Refresh Status'}
          </button>
          
          <button
            onClick={testFileOperations}
            disabled={isTestingFileOps}
            className="w-full btn-secondary mt-2"
          >
            {isTestingFileOps ? 'Testing...' : 'Test File Operations'}
          </button>
        </div>
      </div>

      {/* File Operations Test Results */}
      {fileOpsTest && (
        <div className="mt-4 p-4 bg-gray-50 rounded-lg">
          <h3 className="text-sm font-medium text-gray-900 mb-2">File Operations Test</h3>
          {fileOpsTest.error ? (
            <div className="text-red-600 text-sm">{fileOpsTest.error}</div>
          ) : (
            <div className="space-y-2 text-sm">
              <div>
                <strong>Environment:</strong> {fileOpsTest.environment}
              </div>
              <div>
                <strong>DISABLE_FILE_OPERATIONS:</strong> {fileOpsTest.disable_file_ops_env}
              </div>
              <div>
                <strong>Recommendation:</strong> {fileOpsTest.overall?.recommendation}
              </div>
              <div className="mt-2">
                <strong>Test Results:</strong>
                <ul className="ml-4 mt-1">
                  {Object.entries(fileOpsTest.tests || {}).map(([test, result]: [string, any]) => (
                    <li key={test} className={result.success ? 'text-green-600' : 'text-red-600'}>
                      {test}: {result.success ? '✅ Pass' : '❌ Fail'}
                      {result.error && ` (${result.error})`}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
} 