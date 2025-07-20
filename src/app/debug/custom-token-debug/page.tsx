"use client"

import { useState } from 'react'
import { useUser } from '@clerk/nextjs'

export default function CustomTokenDebugPage() {
  const [debugResult, setDebugResult] = useState<any>(null)
  const [isLoading, setIsLoading] = useState(false)
  const { isSignedIn, user, isLoaded } = useUser()

  const debugCustomToken = async () => {
    if (!isSignedIn) {
      setDebugResult({
        error: 'Please sign in to test token generation',
        timestamp: new Date().toISOString()
      })
      return
    }

    setIsLoading(true)
    setDebugResult(null)

    try {
      console.log('🔧 [DEBUG] Starting custom token debug...')
      
      // Get custom token from API
      console.log('🔧 [DEBUG] Requesting custom token...')
      const response = await fetch('/api/firebase-auth', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          userId: user.id
        })
      })

      console.log('🔧 [DEBUG] Response status:', response.status)
      console.log('🔧 [DEBUG] Response headers:', [...response.headers.entries()])

      if (!response.ok) {
        const errorText = await response.text()
        console.error('🔥 [DEBUG] API Error:', errorText)
        throw new Error(`API Error ${response.status}: ${errorText}`)
      }

      const data = await response.json()
      console.log('🔧 [DEBUG] API Response:', data)

      if (!data.customToken) {
        throw new Error('No custom token in response')
      }

      // Decode the JWT header and payload (without verification)
      const token = data.customToken
      const parts = token.split('.')
      
      if (parts.length !== 3) {
        throw new Error('Invalid JWT format')
      }

      // Decode header
      const headerBase64 = parts[0]
      const headerPadded = headerBase64 + '='.repeat((4 - headerBase64.length % 4) % 4)
      const headerJson = Buffer.from(headerPadded, 'base64').toString('utf8')
      const header = JSON.parse(headerJson)

      // Decode payload
      const payloadBase64 = parts[1]
      const payloadPadded = payloadBase64 + '='.repeat((4 - payloadBase64.length % 4) % 4)
      const payloadJson = Buffer.from(payloadPadded, 'base64').toString('utf8')
      const payload = JSON.parse(payloadJson)

      console.log('🔧 [DEBUG] Token header:', header)
      console.log('🔧 [DEBUG] Token payload:', payload)

      // Check for common issues
      const issues = []
      
      if (!payload.iss) {
        issues.push('Missing issuer (iss)')
      } else if (!payload.iss.includes('writer-bloom')) {
        issues.push(`Issuer doesn't contain project ID: ${payload.iss}`)
      }
      
      if (!payload.aud) {
        issues.push('Missing audience (aud)')
      }
      
      if (!payload.sub) {
        issues.push('Missing subject (sub)')
      }
      
      if (!payload.exp) {
        issues.push('Missing expiration (exp)')
      } else {
        const now = Math.floor(Date.now() / 1000)
        if (payload.exp <= now) {
          issues.push(`Token expired: ${new Date(payload.exp * 1000).toISOString()}`)
        }
      }
      
      if (!payload.iat) {
        issues.push('Missing issued at (iat)')
      } else {
        const now = Math.floor(Date.now() / 1000)
        if (payload.iat > now + 60) {
          issues.push(`Token issued in future: ${new Date(payload.iat * 1000).toISOString()}`)
        }
      }

      setDebugResult({
        success: true,
        token: {
          header,
          payload,
          signature: parts[2]
        },
        tokenLength: token.length,
        issues: issues,
        projectCheck: {
          issuerContainsProject: payload.iss?.includes('writer-bloom'),
          audienceValue: payload.aud,
          expectedAudience: 'https://identitytoolkit.googleapis.com/google.identity.identitytoolkit.v1.IdentityToolkit'
        },
        timestamp: new Date().toISOString()
      })

    } catch (error) {
      console.error('🔥 [DEBUG] Token debug failed:', error)
      setDebugResult({
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
      <div className="max-w-6xl mx-auto">
        <h1 className="text-3xl font-bold mb-6 text-center text-orange-600">
          🔍 Custom Token Debug
        </h1>
        
        <div className="bg-orange-50 border border-orange-200 rounded-lg p-4 mb-6">
          <p className="text-orange-800">
            <strong>Deep Debug:</strong> Examine the custom token being generated to find why signInWithCustomToken() fails
          </p>
        </div>

        <div className="text-center mb-6">
          <button
            onClick={debugCustomToken}
            disabled={isLoading || !isLoaded || !isSignedIn}
            className="bg-orange-600 hover:bg-orange-700 disabled:bg-gray-400 text-white font-bold py-3 px-6 rounded-lg transition-colors"
          >
            {isLoading ? 'Debugging...' : 'Debug Custom Token'}
          </button>
        </div>

        {!isLoaded && (
          <div className="text-center text-gray-500">Loading authentication...</div>
        )}

        {isLoaded && !isSignedIn && (
          <div className="text-center text-red-600">Please sign in to debug custom token</div>
        )}

        {debugResult && (
          <div className="space-y-6">
            <div className="bg-white border border-gray-200 rounded-lg p-6">
              <h2 className="text-xl font-semibold mb-4">
                {debugResult.success ? '🔍 Token Analysis' : '❌ Debug Failed'}
              </h2>
              
              {debugResult.success ? (
                <div className="space-y-4">
                  {debugResult.issues.length > 0 && (
                    <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                      <h3 className="font-semibold text-red-800 mb-2">⚠️ Issues Found:</h3>
                      <ul className="list-disc list-inside text-red-700">
                        {debugResult.issues.map((issue: string, index: number) => (
                          <li key={index}>{issue}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <h3 className="font-semibold text-gray-700 mb-2">JWT Header:</h3>
                      <pre className="bg-gray-100 p-3 rounded text-sm overflow-auto">
                        {JSON.stringify(debugResult.token.header, null, 2)}
                      </pre>
                    </div>
                    
                    <div>
                      <h3 className="font-semibold text-gray-700 mb-2">JWT Payload:</h3>
                      <pre className="bg-gray-100 p-3 rounded text-sm overflow-auto">
                        {JSON.stringify(debugResult.token.payload, null, 2)}
                      </pre>
                    </div>
                  </div>
                  
                  <div>
                    <h3 className="font-semibold text-gray-700 mb-2">Project Check:</h3>
                    <pre className="bg-gray-100 p-3 rounded text-sm overflow-auto">
                      {JSON.stringify(debugResult.projectCheck, null, 2)}
                    </pre>
                  </div>
                </div>
              ) : (
                <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                  <div className="text-red-800 font-semibold">Error:</div>
                  <div className="text-red-700 mt-2">{debugResult.error}</div>
                </div>
              )}
            </div>
          </div>
        )}

        <div className="mt-8 bg-gray-50 border border-gray-200 rounded-lg p-6">
          <h2 className="text-lg font-semibold mb-4">🎯 What We're Checking</h2>
          <ul className="list-disc list-inside space-y-2 text-gray-700">
            <li><strong>Token Structure:</strong> Valid JWT format with header, payload, signature</li>
            <li><strong>Issuer (iss):</strong> Should be Firebase service account for writer-bloom</li>
            <li><strong>Audience (aud):</strong> Should be Identity Toolkit URL</li>
            <li><strong>Subject (sub):</strong> User ID for whom token is generated</li>
            <li><strong>Timing:</strong> Token not expired, not issued in future</li>
            <li><strong>Project ID:</strong> Matches writer-bloom project</li>
          </ul>
        </div>
      </div>
    </div>
  )
} 