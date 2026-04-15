"use client"

import { useEffect, useState } from 'react'
import { getApps, initializeApp } from 'firebase/app'
import { getAuth } from 'firebase/auth'

export default function FirebaseClientDebugPage() {
  const [config, setConfig] = useState<any | null>(null)
  const [initError, setInitError] = useState<string | null>(null)

  useEffect(() => {
    // Grab env vars (they are embedded at build-time)
    const cfg = {
      apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
      authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
      projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
      storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
      messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
      appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
    }
    setConfig(cfg)

    try {
      let app
      if (getApps().length === 0) {
        app = initializeApp(cfg)
      } else {
        app = getApps()[0]
      }
      const auth = getAuth(app)
      console.log('✅ Firebase client initialized:', { options: app.options, auth })
    } catch (err: any) {
      console.error('❌ Firebase init error:', err)
      setInitError(err?.message || String(err))
    }
  }, [])

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 md:px-8">
        <div className="bg-white rounded-lg shadow p-6 sm:p-8">
          <h2 className="text-2xl font-bold text-gray-900">Firebase Client Debug</h2>
          <pre className="mt-4 rounded-lg bg-gray-100 p-4 text-sm overflow-auto">
            {JSON.stringify({ config, initError }, null, 2)}
          </pre>
          <p className="mt-4 text-sm text-gray-600">Open the browser console for full logs.</p>
        </div>
      </div>
    </div>
  )
} 