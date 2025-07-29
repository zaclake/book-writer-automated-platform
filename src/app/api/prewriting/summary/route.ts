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

    // For now, return a basic summary structure that ProjectDashboard expects
    // This can be enhanced later to fetch real prewriting data from backend
    const summary = {
      project_id: projectId,
      title: "Project Summary",
      genre: "Fiction",
      premise: "A compelling story about...",
      main_characters: [
        {
          name: "Main Character",
          description: "The protagonist of the story"
        }
      ],
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

    return NextResponse.json({ summary })

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