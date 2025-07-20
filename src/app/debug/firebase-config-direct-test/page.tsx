"use client"

import { useState } from 'react'

export default function FirebaseConfigDirectTest() {
  const [configTest, setConfigTest] = useState<any>(null)
  const [isLoading, setIsLoading] = useState(false)

  const testFirebaseConfig = async () => {
    setIsLoading(true)
    try {
      // Test the environment variables directly
      const response = await fetch('/api/debug/env-check')
      const envData = await response.json()
      
      // Test Firebase config API
      const configResponse = await fetch('/api/debug/firebase-config')
      const configData = await configResponse.json()
      
      setConfigTest({
        envCheck: envData,
        configCheck: configData,
        timestamp: new Date().toISOString()
      })
    } catch (error) {
      setConfigTest({
        error: error instanceof Error ? error.message : 'Unknown error',
        timestamp: new Date().toISOString()
      })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold mb-6 text-center">
          🔧 Firebase Config Direct Test
        </h1>
        
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
          <p className="text-blue-800">
            <strong>Purpose:</strong> Test Firebase environment variables and configuration at the API level
          </p>
        </div>

        <div className="text-center mb-6">
          <button
            onClick={testFirebaseConfig}
            disabled={isLoading}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white font-bold py-3 px-6 rounded-lg transition-colors"
          >
            {isLoading ? 'Testing...' : 'Test Firebase Config'}
          </button>
        </div>

        {configTest && (
          <div className="space-y-6">
            <div className="bg-white border border-gray-200 rounded-lg p-6">
              <h2 className="text-xl font-semibold mb-4">🔍 Configuration Test Results</h2>
              
              {configTest.error ? (
                <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                  <div className="text-red-800 font-semibold">❌ Error</div>
                  <div className="text-red-700 mt-2">{configTest.error}</div>
                </div>
              ) : (
                <div className="space-y-4">
                  <div>
                    <h3 className="font-semibold text-gray-700 mb-2">Environment Variables Status:</h3>
                    <pre className="bg-gray-100 p-4 rounded-lg text-sm overflow-auto">
                      {JSON.stringify(configTest.envCheck, null, 2)}
                    </pre>
                  </div>
                  
                  <div>
                    <h3 className="font-semibold text-gray-700 mb-2">Firebase Config API Response:</h3>
                    <pre className="bg-gray-100 p-4 rounded-lg text-sm overflow-auto">
                      {JSON.stringify(configTest.configCheck, null, 2)}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        <div className="mt-8 bg-gray-50 border border-gray-200 rounded-lg p-6">
          <h2 className="text-lg font-semibold mb-4">📋 What We're Testing</h2>
          <ul className="list-disc list-inside space-y-2 text-gray-700">
            <li><strong>Environment Variables:</strong> Checking if NEXT_PUBLIC_FIREBASE_* vars are set</li>
            <li><strong>API Config:</strong> Testing Firebase configuration endpoint response</li>
            <li><strong>Value Validation:</strong> Ensuring config values are not "undefined" strings</li>
            <li><strong>Missing Keys:</strong> Identifying exactly which Firebase keys are missing or invalid</li>
          </ul>
        </div>
      </div>
    </div>
  )
} 