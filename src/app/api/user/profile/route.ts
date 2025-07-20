import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

interface UserProfileData {
  name: string
  email: string
  bio?: string
  genre_preference?: string
  writing_experience?: string
  timezone?: string
  preferred_word_count?: number
  quality_strictness?: 'lenient' | 'standard' | 'strict'
  auto_backup_enabled?: boolean
  email_notifications?: boolean
}

// Helper function to call backend API
async function callBackendProfile(method: 'GET' | 'PUT', authToken: string, data?: UserProfileData): Promise<any> {
  const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
  if (!backendBaseUrl) {
    throw new Error('Backend URL not configured')
  }

  const response = await fetch(`${backendBaseUrl}/users/v2/profile`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${authToken}`
    },
    body: method === 'PUT' ? JSON.stringify(data) : undefined
  })

  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(`Backend API error: ${response.status} - ${errorText}`)
  }

  return response.json()
}

export async function GET(request: NextRequest) {
  try {
    const { userId, getToken } = auth()
    
    if (!userId) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    // Get auth token for backend API calls
    const authToken = await getToken()
    if (!authToken) {
      return NextResponse.json({ error: 'Failed to get auth token' }, { status: 401 })
    }

    // Get profile from backend
    const profile = await callBackendProfile('GET', authToken)
    
    return NextResponse.json(profile)
  } catch (error) {
    console.error('GET /api/user/profile error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}

export async function PUT(request: NextRequest) {
  try {
    const { userId, getToken } = auth()
    
    if (!userId) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    // Get auth token for backend API calls
    const authToken = await getToken()
    if (!authToken) {
      return NextResponse.json({ error: 'Failed to get auth token' }, { status: 401 })
    }

    const profileData: UserProfileData = await request.json()

    // Basic validation (backend will do more thorough validation)
    if (!profileData.name || !profileData.email) {
      return NextResponse.json(
        { error: 'Name and email are required' },
        { status: 400 }
      )
    }

    // Save to backend
    const result = await callBackendProfile('PUT', authToken, profileData)

    return NextResponse.json(result)
  } catch (error) {
    console.error('PUT /api/user/profile error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
} 