"use client"

import { useEffect, useState } from 'react'
import { getApps, initializeApp } from 'firebase/app'
import { getAuth, signInWithCustomToken } from 'firebase/auth'

// Auth disabled - using anonymous user
const user = { id: 'anonymous-user', emailAddresses: [{ emailAddress: 'anonymous@localhost' }] }
const isSignedIn = true
const isLoaded = true

export default function FirebaseAuthTestPage() {
  const [logs, setLogs] = useState<string[]>([])
  const [config, setConfig] = useState<any>(null)
  const [authResult, setAuthResult] = useState<any>(null)

  const addLog = (message: string) => {
    console.log(message)
    setLogs(prev => [...prev, `${new Date().toISOString()}: ${message}`])
  }

  useEffect(() => {
    addLog(`User: anonymous-user (auth disabled)`)
    testFirebaseAuth()
  }, [])

  const testFirebaseAuth = async () => {
    try {
      addLog('Starting Firebase authentication test...')

      // Step 1: Check config
      const cfg = {
        apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
        authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
        projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
        storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
        messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
        appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
      }
      setConfig(cfg)

      addLog(`Config loaded: ${JSON.stringify(cfg, null, 2)}`)

      // Step 2: Initialize Firebase
      addLog('Initializing Firebase...')
      let app
      if (getApps().length === 0) {
        app = initializeApp(cfg)
        addLog('Firebase app initialized')
      } else {
        app = getApps()[0]
        addLog('Using existing Firebase app')
      }

      // Step 3: Get Auth instance
      addLog('Getting Firebase Auth instance...')
      const auth = getAuth(app)
      addLog('Firebase Auth instance created')

      // Step 4: Get custom token
      addLog('Requesting custom token from API...')
      const response = await fetch('/api/firebase-auth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      })

      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`Token API failed: ${response.status} ${response.statusText}. Response: ${errorText}`)
      }

      const { customToken } = await response.json()
      addLog(`Custom token received (length: ${customToken.length})`)

      // Step 5: Attempt authentication
      addLog('Attempting to sign in with custom token...')
      const userCredential = await signInWithCustomToken(auth, customToken)

      addLog('SUCCESS! Authentication completed')
      setAuthResult({
        user: {
          uid: userCredential.user.uid,
          email: userCredential.user.email,
          displayName: userCredential.user.displayName
        },
        success: true
      })

    } catch (error: any) {
      addLog(`ERROR: ${error.message}`)
      addLog(`Error details: ${JSON.stringify(error, null, 2)}`)
      setAuthResult({
        error: error.message,
        code: error.code,
        success: false
      })
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 md:px-8">
        <div className="bg-white rounded-lg shadow p-6 sm:p-8">
          <h2 className="text-2xl font-bold text-gray-900">Firebase Authentication Test</h2>

      <div style={{
        marginBottom: '2rem',
        padding: '1rem',
        background: '#d4edda',
        color: '#155724',
        border: '1px solid #c3e6cb',
        borderRadius: '4px'
      }}>
        <strong>Authentication Status:</strong> Auth disabled - using anonymous user
      </div>

      {config && (
        <div style={{ marginBottom: '2rem' }}>
          <h3>Config:</h3>
          <pre style={{ background: '#f5f5f5', padding: '1rem', fontSize: '12px' }}>
            {JSON.stringify(config, null, 2)}
          </pre>
        </div>
      )}

      {authResult && (
        <div style={{ marginBottom: '2rem' }}>
          <h3>Result:</h3>
          <pre style={{
            background: authResult.success ? '#d4edda' : '#f8d7da',
            padding: '1rem',
            fontSize: '12px',
            color: authResult.success ? '#155724' : '#721c24'
          }}>
            {JSON.stringify(authResult, null, 2)}
          </pre>
        </div>
      )}

      <div>
        <h3>Logs:</h3>
        <div style={{
          background: '#f8f9fa',
          padding: '1rem',
          maxHeight: '400px',
          overflowY: 'auto',
          fontSize: '12px',
          fontFamily: 'monospace'
        }}>
          {logs.map((log, index) => (
            <div key={index} style={{ marginBottom: '0.5rem' }}>
              {log}
            </div>
          ))}
        </div>
      </div>

          <button
            onClick={testFirebaseAuth}
            className="mt-4 rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
          >
            Run Test Again
          </button>
        </div>
      </div>
    </div>
  )
}
