import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@/lib/server-auth'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(request: NextRequest) {
  try {
    // Get project_id from query params
    const { searchParams } = new URL(request.url)
    const projectId = searchParams.get('project_id')

    if (!projectId) {
      return NextResponse.json(
        { error: 'Project ID is required' },
        { status: 400 }
      )
    }

    // Get auth token from request headers or server session
    let authHeader = request.headers.get('authorization')
    if (!authHeader) {
      try {
        const { getToken } = await auth()
        const token = await getToken()
        if (token) {
          authHeader = `Bearer ${token}`
        }
      } catch (error) {
        console.error('[prewriting-summary] Failed to load server auth token:', error)
      }
    }

    if (!authHeader) {
      return NextResponse.json(
        { error: 'Authentication required' },
        { status: 401 }
      )
    }

    console.log('[prewriting-summary] Request for project:', projectId)

    // Get backend URL
    const backendBaseUrl =
      process.env.NEXT_PUBLIC_BACKEND_URL?.trim() || process.env.BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      return NextResponse.json(
        { error: 'Backend URL not configured' },
        { status: 500 }
      )
    }

    try {
      // Fetch project data from backend
      const projectUrl = `${backendBaseUrl}/v2/projects/${encodeURIComponent(projectId)}`
      console.log('[prewriting-summary] Fetching project from backend:', projectUrl)
      
      const projectResponse = await fetch(projectUrl, {
        method: 'GET',
        headers: {
          'Authorization': authHeader,
          'Content-Type': 'application/json'
        }
      })

      const projectText = await projectResponse.text()
      let projectData: any = {}
      if (projectText) {
        try {
          projectData = JSON.parse(projectText)
        } catch {
          projectData = { message: projectText }
        }
      }

      if (!projectResponse.ok) {
        console.error('[prewriting-summary] Backend error:', projectResponse.status, projectData)
        return NextResponse.json(
          { error: 'Backend request failed', details: projectData },
          { status: projectResponse.status }
        )
      }

      const project = projectData.project || projectData

      // Extract project settings and metadata
      const settings = project.settings || {}
      const metadata = project.metadata || {}
      
      // Build summary from actual project data
      const summary = {
        project_id: projectId,
        title: metadata.title || '',
        genre: settings.genre || '',
        premise: metadata.premise || '',
        main_characters: metadata.main_characters || [],
        setting: {
          description: metadata.setting_description || '',
          time: metadata.setting_time || '',
          place: metadata.setting_place || ''
        },
        themes: metadata.themes || [],
        chapter_outline: [],
        total_chapters: settings.target_chapters || 0,
        word_count_target: settings.word_count_per_chapter || 0
      }

      return NextResponse.json({ summary })

    } catch (backendError) {
      console.error('[prewriting-summary] Backend error:', backendError)
      return NextResponse.json(
        { error: 'Backend request failed' },
        { status: 502 }
      )
    }

  } catch (error) {
    console.error('[prewriting-summary] Error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}

export async function OPTIONS(request: NextRequest) {
  return NextResponse.json({
    message: 'Prewriting summary route is accessible'
  }, {
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    }
  })
} 