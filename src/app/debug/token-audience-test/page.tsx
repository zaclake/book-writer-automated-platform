"use client"

import { useEffect, useState } from 'react'
import { getApps, initializeApp } from 'firebase/app'
import { getAuth, signInWithCustomToken } from 'firebase/auth'

// Auth disabled - using anonymous user
const user = { id: 'anonymous-user', emailAddresses: [{ emailAddress: 'anonymous@localhost' }] }
const isSignedIn = true
const isLoaded = true

interface TokenTest {
  customToken?: string
  customTokenPayload?: any
  idToken?: string
  idTokenPayload?: any
  audienceFormat?: string
  success?: boolean
  error?: string
  timestamp?: string
}

export default function TokenAudienceTestPage() {
  const [testResult, setTestResult] = useState<TokenTest | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  const runAudienceTest = async () => {
    setIsLoading(true)
    setTestResult(null)

    try {
      console.log('Testing Firebase custom token to ID token flow...')

      // Step 1: Get custom token from our API
      const response = await fetch('/api/firebase-auth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      })

      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`Token generation failed: ${response.status} - ${errorText}`)
      }

      const { customToken } = await response.json()

      // Step 2: Decode the custom token payload
      const customTokenParts = customToken.split('.')
      if (customTokenParts.length !== 3) {
        throw new Error('Invalid JWT format - custom token should have 3 parts')
      }

      const customPayloadBase64 = customTokenParts[1]
      const customPaddedPayload = customPayloadBase64 + '='.repeat((4 - customPayloadBase64.length % 4) % 4)
      const customPayloadJson = Buffer.from(customPaddedPayload, 'base64').toString('utf8')
      const customTokenPayload = JSON.parse(customPayloadJson)

      // Step 3: Initialize Firebase client with hardcoded config
      const firebaseConfig = {
        apiKey: "AIzaSyC2GJ6BHBQ0K53iND3GV7EVJNH4yAN8ddI",
        authDomain: "writer-bloom.firebaseapp.com",
        projectId: "writer-bloom",
        storageBucket: "writer-bloom.firebasestorage.app",
        messagingSenderId: "681297692294",
        appId: "1:681297692294:web:6bebc5668ea47c037cb307"
      }

      console.log('[TOKEN TEST] Firebase config:', firebaseConfig)
      console.log('[TOKEN TEST] Existing apps:', getApps().length)

      let app
      try {
        if (getApps().length === 0) {
          console.log('[TOKEN TEST] Initializing new Firebase app...')
          app = initializeApp(firebaseConfig, `token-test-${Date.now()}`)
          console.log('[TOKEN TEST] App initialized successfully:', app.name)
        } else {
          console.log('[TOKEN TEST] Using existing app...')
          app = getApps()[0]
        }
      } catch (initError) {
        console.error('[TOKEN TEST] Firebase init failed:', initError)
        throw new Error(`Firebase initialization failed: ${initError instanceof Error ? initError.message : 'Unknown error'}`)
      }

      console.log('[TOKEN TEST] Getting Firebase Auth...')
      const auth = getAuth(app)
      console.log('[TOKEN TEST] Firebase Auth instance:', !!auth)

      // Step 4: Exchange custom token for ID token
      console.log('Exchanging custom token for ID token...')
      const userCredential = await signInWithCustomToken(auth, customToken)
      console.log('[TOKEN TEST] Sign in successful:', !!userCredential)
      const idToken = await userCredential.user.getIdToken(true)

      // Step 5: Decode the ID token payload
      const idTokenParts = idToken.split('.')
      if (idTokenParts.length !== 3) {
        throw new Error('Invalid JWT format - ID token should have 3 parts')
      }

      const idPayloadBase64 = idTokenParts[1]
      const idPaddedPayload = idPayloadBase64 + '='.repeat((4 - idPayloadBase64.length % 4) % 4)
      const idPayloadJson = Buffer.from(idPaddedPayload, 'base64').toString('utf8')
      const idTokenPayload = JSON.parse(idPayloadJson)

      // Step 6: Check audience format of ID token (this is what matters)
      const idTokenAudience = idTokenPayload.aud
      let audienceFormat = 'unknown'

      if (idTokenAudience === 'writer-bloom') {
        audienceFormat = 'modern (project-based)'
      } else if (idTokenAudience === 'https://identitytoolkit.googleapis.com/google.identity.identitytoolkit.v1.IdentityToolkit') {
        audienceFormat = 'legacy (Identity Toolkit)'
      } else {
        audienceFormat = `other: ${idTokenAudience}`
      }

      setTestResult({
        customToken: customToken.substring(0, 50) + '...',
        customTokenPayload,
        idToken: idToken.substring(0, 50) + '...',
        idTokenPayload,
        audienceFormat,
        success: idTokenAudience === 'writer-bloom',
        timestamp: new Date().toISOString()
      })

      console.log('Token exchange test completed:', {
        customTokenAudience: customTokenPayload.aud,
        idTokenAudience,
        audienceFormat,
        success: idTokenAudience === 'writer-bloom'
      })

    } catch (error: any) {
      console.error('Token audience test failed:', error)
      setTestResult({
        error: error.message,
        timestamp: new Date().toISOString()
      })
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    // Auto-run the test
    runAudienceTest()
  }, [])

  return (
    <div className="min-h-screen bg-gray-50 py-12">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 md:px-8">
        <div className="bg-white rounded-lg shadow-lg p-6 sm:p-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            Firebase Token Flow Test
          </h1>
          <p className="text-gray-600 mb-8">
            Testing the complete custom token to ID token exchange flow to verify proper audience handling.
          </p>

          <div className="mb-6">
            <p className="text-sm text-gray-500 mb-2">User:</p>
            <p className="font-medium text-gray-900">
              anonymous-user (auth disabled)
            </p>
          </div>

          <button
            onClick={runAudienceTest}
            disabled={isLoading}
            className="bg-blue-600 text-white px-6 py-3 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors mb-8"
          >
            {isLoading ? 'Testing Token Flow...' : 'Run Token Flow Test'}
          </button>

          {testResult && (
            <div className="space-y-6">
              {testResult.success !== undefined && (
                <div className={`p-4 rounded-md ${testResult.success ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
                  <div className="flex">
                    <div className="ml-3">
                      <h3 className={`text-sm font-medium ${testResult.success ? 'text-green-800' : 'text-red-800'}`}>
                        {testResult.success ? 'SUCCESS: ID Token has correct modern audience!' : 'ISSUE: ID Token audience is incorrect'}
                      </h3>
                      <div className={`mt-2 text-sm ${testResult.success ? 'text-green-700' : 'text-red-700'}`}>
                        <p>
                          <strong>ID Token Audience:</strong> {testResult.audienceFormat}
                        </p>
                        <p>
                          <strong>Expected:</strong> modern (project-based) with audience = "writer-bloom"
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {testResult.error && (
                <div className="bg-red-50 border border-red-200 p-4 rounded-md">
                  <h3 className="text-sm font-medium text-red-800 mb-2">Error</h3>
                  <p className="text-sm text-red-700">{testResult.error}</p>
                </div>
              )}

              {testResult.customTokenPayload && testResult.idTokenPayload && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="bg-yellow-50 p-4 rounded-md">
                    <h3 className="text-sm font-medium text-yellow-800 mb-2">Custom Token (Temporary)</h3>
                    <div className="text-sm text-yellow-700 space-y-1">
                      <p><strong>Audience (aud):</strong> {testResult.customTokenPayload.aud}</p>
                      <p><strong>Issuer (iss):</strong> {testResult.customTokenPayload.iss}</p>
                      <p><strong>Subject (sub):</strong> {testResult.customTokenPayload.sub}</p>
                      <p><strong>Purpose:</strong> Exchange only</p>
                    </div>
                  </div>

                  <div className="bg-green-50 p-4 rounded-md">
                    <h3 className="text-sm font-medium text-green-800 mb-2">ID Token (Production)</h3>
                    <div className="text-sm text-green-700 space-y-1">
                      <p><strong>Audience (aud):</strong> {testResult.idTokenPayload.aud}</p>
                      <p><strong>Issuer (iss):</strong> {testResult.idTokenPayload.iss}</p>
                      <p><strong>Subject (sub):</strong> {testResult.idTokenPayload.sub}</p>
                      <p><strong>Purpose:</strong> Firebase API access</p>
                    </div>
                  </div>
                </div>
              )}

              <div className="bg-blue-50 p-4 rounded-md">
                <h3 className="text-sm font-medium text-blue-800 mb-2">Understanding Firebase Token Flow</h3>
                <div className="text-sm text-blue-700 space-y-2">
                  <p><strong>Step 1:</strong> Admin SDK creates a <em>custom token</em> with legacy audience (by design)</p>
                  <p><strong>Step 2:</strong> Client exchanges custom token for <em>ID token</em> via signInWithCustomToken()</p>
                  <p><strong>Step 3:</strong> ID token has modern audience = "writer-bloom" and is used for Firebase API calls</p>
                  <p><strong>Important:</strong> Custom tokens are temporary exchange credentials, not production tokens!</p>
                </div>
              </div>

              {testResult.timestamp && (
                <p className="text-xs text-gray-500">Test completed at: {testResult.timestamp}</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
