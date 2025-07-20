"use client"

import { useState } from 'react'
import { getApps, initializeApp } from 'firebase/app'
import { getAuth } from 'firebase/auth'

export default function FirebaseRawTest() {
  const [testResult, setTestResult] = useState<any>(null)
  const [isLoading, setIsLoading] = useState(false)

  const testFirebaseRaw = () => {
    setIsLoading(true)
    try {
      // Test with hardcoded config first
      const hardcodedConfig = {
        apiKey: "AIzaSyC2GJ6BHBQ0K53iND3GV7EVJNH4yAN8ddI",
        authDomain: "writer-bloom.firebaseapp.com",
        projectId: "writer-bloom",
        storageBucket: "writer-bloom.firebasestorage.app",
        messagingSenderId: "681297692294",
        appId: "1:681297692294:web:6bebc5668ea47c037cb307"
      }

      console.log('🔧 Testing Firebase with hardcoded config:', hardcodedConfig)

      // Clean up any existing apps
      const apps = getApps()
      console.log('🔧 Existing Firebase apps:', apps.length)

      let app
      if (apps.length === 0) {
        console.log('🔧 No existing apps, creating new one...')
        app = initializeApp(hardcodedConfig, 'test-app')
      } else {
        console.log('🔧 Using existing app...')
        app = apps[0]
      }

      // Test auth
      const auth = getAuth(app)
      console.log('🔧 Firebase Auth initialized:', !!auth)

      setTestResult({
        success: true,
        config: hardcodedConfig,
        appName: app.name,
        authEnabled: !!auth,
        timestamp: new Date().toISOString()
      })

    } catch (error) {
      console.error('🔥 Firebase initialization failed:', error)
      setTestResult({
        success: false,
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
          🔧 Firebase Raw Test
        </h1>
        
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-6">
          <p className="text-yellow-800">
            <strong>Purpose:</strong> Test Firebase initialization with hardcoded config to isolate the issue
          </p>
        </div>

        <div className="text-center mb-6">
          <button
            onClick={testFirebaseRaw}
            disabled={isLoading}
            className="bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white font-bold py-3 px-6 rounded-lg transition-colors"
          >
            {isLoading ? 'Testing...' : 'Test Firebase Raw'}
          </button>
        </div>

        {testResult && (
          <div className="bg-white border border-gray-200 rounded-lg p-6">
            <h2 className="text-xl font-semibold mb-4">
              {testResult.success ? '✅ Test Results' : '❌ Test Results'}
            </h2>
            
            <pre className="bg-gray-100 p-4 rounded-lg text-sm overflow-auto">
              {JSON.stringify(testResult, null, 2)}
            </pre>
          </div>
        )}

        <div className="mt-6 bg-gray-50 border border-gray-200 rounded-lg p-6">
          <h2 className="text-lg font-semibold mb-4">🎯 Test Strategy</h2>
          <ul className="list-disc list-inside space-y-2 text-gray-700">
            <li>Use hardcoded Firebase config (bypass environment variable issues)</li>
            <li>Test Firebase app initialization directly</li>
            <li>Test Firebase Auth initialization</li>
            <li>Check browser console for detailed logs</li>
          </ul>
        </div>
      </div>
    </div>
  )
} 