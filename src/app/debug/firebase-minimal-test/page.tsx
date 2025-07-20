"use client"

import { useState } from 'react'

export default function FirebaseMinimalTest() {
  const [testResult, setTestResult] = useState<any>(null)
  const [isLoading, setIsLoading] = useState(false)

  const testFirebaseMinimal = async () => {
    setIsLoading(true)
    try {
      console.log('🔧 Starting minimal Firebase test...')
      
      // Import Firebase dynamically to avoid SSR issues
      const { initializeApp, getApps } = await import('firebase/app')
      const { getAuth, connectAuthEmulator } = await import('firebase/auth')
      
      console.log('🔧 Firebase modules loaded successfully')
      
      // Ultra-minimal config
      const config = {
        apiKey: "AIzaSyC2GJ6BHBQ0K53iND3GV7EVJNH4yAN8ddI",
        authDomain: "writer-bloom.firebaseapp.com", 
        projectId: "writer-bloom"
      }
      
      console.log('🔧 Config prepared:', config)
      
      // Clean slate
      const existingApps = getApps()
      console.log('🔧 Existing apps:', existingApps.length)
      
      // Initialize with unique name
      const appName = `test-${Date.now()}`
      const app = initializeApp(config, appName)
      console.log('🔧 App initialized:', app.name)
      
      // Get auth instance
      const auth = getAuth(app)
      console.log('🔧 Auth instance created:', !!auth)
      
      setTestResult({
        success: true,
        appName: app.name,
        authReady: !!auth,
        config: config,
        timestamp: new Date().toISOString()
      })
      
    } catch (error: any) {
      console.error('🔥 Firebase test failed:', error)
      setTestResult({
        success: false,
        error: error.message,
        errorCode: error.code,
        stack: error.stack,
        timestamp: new Date().toISOString()
      })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold mb-6 text-center text-red-600">
          🔥 MINIMAL Firebase Test
        </h1>
        
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
          <p className="text-red-800">
            <strong>CRITICAL TEST:</strong> Absolute minimal Firebase initialization to find the root cause
          </p>
        </div>

        <div className="text-center mb-6">
          <button
            onClick={testFirebaseMinimal}
            disabled={isLoading}
            className="bg-red-600 hover:bg-red-700 disabled:bg-gray-400 text-white font-bold py-3 px-6 rounded-lg transition-colors"
          >
            {isLoading ? 'Testing...' : 'RUN MINIMAL TEST'}
          </button>
        </div>

        {testResult && (
          <div className="bg-white border border-gray-200 rounded-lg p-6">
            <h2 className="text-xl font-semibold mb-4">
              {testResult.success ? '✅ SUCCESS' : '❌ FAILED'}
            </h2>
            
            <pre className="bg-gray-100 p-4 rounded-lg text-sm overflow-auto whitespace-pre-wrap">
              {JSON.stringify(testResult, null, 2)}
            </pre>
          </div>
        )}

        <div className="mt-6 bg-gray-50 border border-gray-200 rounded-lg p-6">
          <h2 className="text-lg font-semibold mb-4">🎯 This Test Will Show</h2>
          <ul className="list-disc list-inside space-y-2 text-gray-700">
            <li>If Firebase can initialize at all</li>
            <li>The exact error message and code</li>
            <li>Whether it's a config issue or something else</li>
            <li>Full error stack trace for debugging</li>
          </ul>
          
          <div className="mt-4 p-4 bg-yellow-50 border border-yellow-200 rounded">
            <p className="text-yellow-800 font-semibold">
              Check the browser console for detailed logs!
            </p>
          </div>
        </div>
      </div>
    </div>
  )
} 