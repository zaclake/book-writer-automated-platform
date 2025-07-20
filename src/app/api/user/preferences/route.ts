import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

interface UserPreferences {
  writing_style: string
  default_word_count: number
  preferred_genres: string[]
  notification_settings: {
    email_notifications: boolean
    auto_save_alerts: boolean
    quality_warnings: boolean
  }
}

// Helper function to call backend API
async function callBackendPreferences(method: 'GET' | 'PUT', authToken: string, data?: UserPreferences): Promise<any> {
  const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
  if (!backendBaseUrl) {
    throw new Error('Backend URL not configured')
  }

  const response = await fetch(`${backendBaseUrl}/users/v2/preferences`, {
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

    // Get preferences from backend
    const preferences = await callBackendPreferences('GET', authToken)
    
    return NextResponse.json(preferences)
  } catch (error) {
    console.error('GET /api/user/preferences error:', error)
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

    const preferencesData: UserPreferences = await request.json()

    // Basic validation (backend will do more thorough validation)
    if (preferencesData.default_word_count && 
        (preferencesData.default_word_count < 500 || preferencesData.default_word_count > 10000)) {
      return NextResponse.json(
        { error: 'Default word count must be between 500 and 10000' },
        { status: 400 }
      )
    }

    // Save to backend
    const result = await callBackendPreferences('PUT', authToken, preferencesData)

    return NextResponse.json(result)
  } catch (error) {
    console.error('PUT /api/user/preferences error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
} 