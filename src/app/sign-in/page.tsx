'use client'

import { useRouter } from 'next/navigation'
import { useState } from 'react'
import Link from 'next/link'

export default function SignInPage() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')

  const setAuthCookies = (sessionToken: string, user: { id?: string; email?: string; name?: string }) => {
    const maxAge = 60 * 60 * 24 * 30
    const base = `; Max-Age=${maxAge}; Path=/; SameSite=Lax`
    document.cookie = `user_session=${encodeURIComponent(sessionToken || '')}${base}`
    document.cookie = `user_id=${encodeURIComponent(user?.id || '')}${base}`
    document.cookie = `user_email=${encodeURIComponent(user?.email || '')}${base}`
    document.cookie = `user_name=${encodeURIComponent(user?.name || '')}${base}`
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setIsSubmitting(true)

    try {
      let response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })

      if (response.status === 404) {
        const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
        if (!backendBaseUrl) {
          setError('Backend URL not configured')
          setIsSubmitting(false)
          return
        }
        response = await fetch(`${backendBaseUrl}/v2/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        })
        const data = await response.json()
        if (!response.ok) {
          setError(data?.detail || data?.error || 'Login failed')
          setIsSubmitting(false)
          return
        }
        setAuthCookies(data.session_token, data.user || {})
      window.location.href = '/dashboard'
      return
    }

      const data = await response.json()
      if (!response.ok) {
        setError(data?.detail || data?.error || 'Login failed')
        setIsSubmitting(false)
        return
      }

      window.location.href = '/dashboard'
    } catch (err) {
      console.error('Login failed:', err)
      setError('Login failed')
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-brand-sand flex items-center justify-center px-4 sm:px-6 md:px-8">
      <div className="w-full max-w-md md:max-w-lg bg-white rounded-xl shadow-lg p-6 sm:p-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Sign in</h1>
        <p className="text-sm text-gray-600 mb-6">
          Access your personal projects and drafts.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-soft-purple"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1">
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-soft-purple"
            />
          </div>

          <div role="alert" aria-live="polite">
            {error && (
              <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                {error}
              </div>
            )}
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full bg-brand-soft-purple text-white py-3 px-4 rounded-lg font-medium hover:bg-opacity-90 transition-all disabled:opacity-60"
          >
            {isSubmitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="text-sm text-gray-600 mt-6 text-center">
          New here?{' '}
          <Link href="/sign-up" className="text-brand-soft-purple hover:underline">
            Create an account
          </Link>
        </p>
      </div>
    </div>
  )
}
