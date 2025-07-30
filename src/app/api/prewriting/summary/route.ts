import { NextRequest, NextResponse } from 'next/server'

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

    // Get auth token from request headers
    const authHeader = request.headers.get('authorization')
    if (!authHeader) {
      return NextResponse.json(
        { error: 'Authentication required' },
        { status: 401 }
      )
    }

    // Get backend URL
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      // Return default summary if backend not configured
      const defaultSummary = {
        project_id: projectId,
        title: "Project Summary",
        genre: "Fiction",
        premise: "A compelling story about...",
        main_characters: [],
        setting: {
          description: "The story takes place in...",
          time: "Present day",
          place: "Various locations"
        },
        themes: ["Adventure", "Growth", "Discovery"],
        chapter_outline: [],
        total_chapters: 25,
        word_count_target: 3800
      }
      return NextResponse.json({ summary: defaultSummary })
    }

    try {
      // Fetch project data from backend
      const projectUrl = `${backendBaseUrl}/v2/projects/${encodeURIComponent(projectId)}`
      
      const projectResponse = await fetch(projectUrl, {
        method: 'GET',
        headers: {
          'Authorization': authHeader,
          'Content-Type': 'application/json'
        }
      })

      if (!projectResponse.ok) {
        throw new Error(`Backend responded with ${projectResponse.status}`)
      }

      const projectData = await projectResponse.json()
      const project = projectData.project || projectData

      // Extract project settings and metadata
      const settings = project.settings || {}
      const metadata = project.metadata || {}
      
      // Build summary from actual project data
      const summary = {
        project_id: projectId,
        title: metadata.title || "Untitled Project",
        genre: settings.genre || "Fiction",
        premise: "A compelling story...", // Could be extracted from book bible
        main_characters: [],
        setting: {
          description: "The story takes place...",
          time: "Present day",
          place: "Various locations"
        },
        themes: ["Adventure", "Growth", "Discovery"],
        chapter_outline: [],
        total_chapters: settings.target_chapters || 25,
        word_count_target: settings.word_count_per_chapter || 3800
      }

      return NextResponse.json({ summary })

    } catch (backendError) {
      console.error('[prewriting-summary] Backend error:', backendError)
      
      // Fallback to default summary with some project ID context
      const fallbackSummary = {
        project_id: projectId,
        title: "Project Summary",
        genre: "Fiction",
        premise: "A compelling story about...",
        main_characters: [],
        setting: {
          description: "The story takes place in...",
          time: "Present day", 
          place: "Various locations"
        },
        themes: ["Adventure", "Growth", "Discovery"],
        chapter_outline: [],
        total_chapters: 25,
        word_count_target: 3800
      }
      
      return NextResponse.json({ summary: fallbackSummary })
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