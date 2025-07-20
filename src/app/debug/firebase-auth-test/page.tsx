"use client"

import { useEffect, useState } from 'react'
import { getApps, initializeApp } from 'firebase/app'
import { getAuth, signInWithCustomToken } from 'firebase/auth'
import { useUser } from '@clerk/nextjs'

export default function FirebaseAuthTestPage() {
  const [logs, setLogs] = useState<string[]>([])
  const [config, setConfig] = useState<any>(null)
  const [authResult, setAuthResult] = useState<any>(null)
  const { isSignedIn, user, isLoaded } = useUser()

  const addLog = (message: string) => {
    console.log(message)
    setLogs(prev => [...prev, `${new Date().toISOString()}: ${message}`])
  }

  useEffect(() => {
    if (isLoaded) {
      if (isSignedIn) {
        addLog(`✅ User is signed in: ${user?.emailAddresses?.[0]?.emailAddress || user?.id}`)
        testFirebaseAuth()
      } else {
        addLog('❌ User not signed in - this test requires authentication')
        setAuthResult({
          error: 'User not authenticated with Clerk',
          needsSignIn: true,
          success: false
        })
      }
    }
  }, [isSignedIn, isLoaded])

  const testFirebaseAuth = async () => {
    try {
      addLog('🔄 Starting Firebase authentication test...')
      
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
      
      addLog(`📋 Config loaded: ${JSON.stringify(cfg, null, 2)}`)
      
      // Step 2: Initialize Firebase
      addLog('🔥 Initializing Firebase...')
      let app
      if (getApps().length === 0) {
        app = initializeApp(cfg)
        addLog('✅ Firebase app initialized')
      } else {
        app = getApps()[0]
        addLog('✅ Using existing Firebase app')
      }
      
      // Step 3: Get Auth instance
      addLog('🔐 Getting Firebase Auth instance...')
      const auth = getAuth(app)
      addLog('✅ Firebase Auth instance created')
      
      // Step 4: Get custom token
      addLog('🎫 Requesting custom token from API...')
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
      addLog(`✅ Custom token received (length: ${customToken.length})`)
      
      // Step 5: Attempt authentication
      addLog('🔑 Attempting to sign in with custom token...')
      const userCredential = await signInWithCustomToken(auth, customToken)
      
      addLog('🎉 SUCCESS! Authentication completed')
      setAuthResult({
        user: {
          uid: userCredential.user.uid,
          email: userCredential.user.email,
          displayName: userCredential.user.displayName
        },
        success: true
      })
      
    } catch (error: any) {
      addLog(`❌ ERROR: ${error.message}`)
      addLog(`📄 Error details: ${JSON.stringify(error, null, 2)}`)
      setAuthResult({
        error: error.message,
        code: error.code,
        success: false
      })
    }
  }

  if (!isLoaded) {
    return <div style={{ padding: '2rem' }}>Loading authentication state...</div>
  }

  return (
    <div style={{ padding: '2rem', maxWidth: '1000px' }}>
      <h2>Firebase Authentication Test</h2>
      
      <div style={{ 
        marginBottom: '2rem', 
        padding: '1rem', 
        background: isSignedIn ? '#d4edda' : '#f8d7da',
        color: isSignedIn ? '#155724' : '#721c24',
        border: `1px solid ${isSignedIn ? '#c3e6cb' : '#f5c6cb'}`,
        borderRadius: '4px'
      }}>
        <strong>Authentication Status:</strong> {isSignedIn ? 
          `✅ Signed in as ${user?.emailAddresses?.[0]?.emailAddress || user?.id}` : 
          `❌ Not signed in - please go to /sign-in first`
        }
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
      
      {isSignedIn && (
        <button 
          onClick={testFirebaseAuth}
          style={{
            marginTop: '1rem',
            padding: '0.5rem 1rem',
            background: '#007bff',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer'
          }}
        >
          Run Test Again
        </button>
      )}
      
      {!isSignedIn && (
        <div style={{ marginTop: '1rem' }}>
          <a href="/sign-in" style={{
            display: 'inline-block',
            padding: '0.5rem 1rem',
            background: '#28a745',
            color: 'white',
            textDecoration: 'none',
            borderRadius: '4px'
          }}>
            Go to Sign In
          </a>
        </div>
      )}
    </div>
  )
} 