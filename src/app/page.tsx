'use client'

import { useState, useEffect } from 'react'
import Image from 'next/image'

const SITE_PASSWORD = '8649924988'
const AUTH_COOKIE_NAME = 'site_access'

export default function PasswordGate() {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isChecking, setIsChecking] = useState(true)

  useEffect(() => {
    // Check if already authenticated
    const isAuthenticated = document.cookie.includes(`${AUTH_COOKIE_NAME}=granted`)
    if (isAuthenticated) {
      // Avoid App Router transitions that can stall (pending `?_rsc` fetch).
      window.location.replace('/dashboard')
    } else {
      setIsChecking(false)
    }
  }, [])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (password === SITE_PASSWORD) {
      // Set cookie for 30 days
      const expires = new Date()
      expires.setDate(expires.getDate() + 30)
      document.cookie = `${AUTH_COOKIE_NAME}=granted; expires=${expires.toUTCString()}; path=/`

      window.location.replace('/dashboard')
    } else {
      setError('Incorrect password')
      setPassword('')
    }
  }

  if (isChecking) {
    return (
      <div className="min-h-screen bg-brand-sand flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-soft-purple"></div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-brand-sand flex flex-col items-center justify-center px-4 sm:px-6 md:px-8">
      <div className="max-w-md md:max-w-lg w-full">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <Image
            src="/logo.png"
            alt="WriterBloom"
            width={80}
            height={80}
            className="w-20 h-20 object-contain mb-4"
            priority
          />
          <h1 className="text-3xl font-bold text-gray-900">WriterBloom</h1>
          <p className="text-gray-600 mt-2">Enter password to continue</p>
        </div>

        {/* Password Form */}
        <form onSubmit={handleSubmit} className="bg-white rounded-xl shadow-lg p-6 sm:p-8">
          <div className="mb-6">
            <label htmlFor="password" className="sr-only">
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter password"
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-soft-purple focus:border-transparent text-lg"
              autoFocus
              autoComplete="off"
            />
          </div>

          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
              {error}
            </div>
          )}

          <button
            type="submit"
            className="w-full bg-brand-soft-purple text-white py-3 px-4 rounded-lg font-medium hover:bg-opacity-90 transition-all text-lg"
          >
            Enter
          </button>
        </form>
      </div>
    </div>
  )
}
