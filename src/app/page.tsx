'use client'

import { useUser } from '@clerk/nextjs'
import { useRouter } from 'next/navigation'
import { useEffect } from 'react'
import LandingPage from '@/components/LandingPage'

export default function Home() {
  const { user, isLoaded } = useUser()
  const router = useRouter()

  useEffect(() => {
    // If user is authenticated, redirect to dashboard
    if (isLoaded && user) {
      router.replace('/dashboard')
    }
  }, [isLoaded, user, router])

  // Show loading state while checking auth
  if (!isLoaded) {
    return (
      <div className="min-h-screen bg-brand-sand flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-soft-purple mx-auto mb-4"></div>
          <p className="text-gray-600">Loading your creative space...</p>
        </div>
      </div>
    )
  }

  // If authenticated user, let useEffect handle redirect (show nothing)
  if (user) {
    return null
  }

  // Show landing page for anonymous users
  return <LandingPage />
} 