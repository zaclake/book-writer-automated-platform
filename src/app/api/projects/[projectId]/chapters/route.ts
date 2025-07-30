import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

// Transform backend chapter data to frontend-expected format
function transformChapterData(chapter: any) {
  const metadata = chapter.metadata || {}
  const qualityScores = chapter.quality_scores || {}
  
  return {
    id: chapter.id,
    chapter_number: chapter.chapter_number || 0,
    title: chapter.title || `Chapter ${chapter.chapter_number || 'Unknown'}`,
    word_count: metadata.word_count || 0,
    target_word_count: metadata.target_word_count || 2000,
    stage: metadata.stage || 'draft',
    created_at: metadata.created_at || chapter.created_at || new Date().toISOString(),
    updated_at: metadata.updated_at || chapter.updated_at || new Date().toISOString(),
    director_notes_count: metadata.director_notes_count || 0,
    quality_scores: qualityScores.craft_scores ? {
      overall_rating: qualityScores.overall_rating || 0,
      prose: qualityScores.craft_scores.prose || 0,
      character: qualityScores.craft_scores.character || 0,
      story: qualityScores.craft_scores.story || 0,
      emotion: qualityScores.craft_scores.emotion || 0,
      freshness: qualityScores.craft_scores.freshness || 0
    } : undefined
  }
}

export async function GET(
  request: NextRequest,
  { params }: { params: { projectId: string } }
) {
  try {
    const { projectId } = params

    if (!projectId) {
      return NextResponse.json(
        { error: 'Project ID is required' },
        { status: 400 }
      )
    }

    // Get backend URL
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      return NextResponse.json(
        { error: 'Backend URL not configured' },
        { status: 500 }
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

    // Make request to backend v2 endpoint
    const backendUrl = `${backendBaseUrl}/v2/projects/${encodeURIComponent(projectId)}/chapters`
    
    const backendResponse = await fetch(backendUrl, {
      method: 'GET',
      headers: {
        'Authorization': authHeader,
        'Content-Type': 'application/json'
      }
    })

    if (!backendResponse.ok) {
      const errorData = await backendResponse.text()
      console.error('[project-chapters] Backend error:', errorData)
      
      try {
        const errorJson = JSON.parse(errorData)
        return NextResponse.json(
          { error: errorJson.detail || 'Failed to get chapters' },
          { status: backendResponse.status }
        )
      } catch {
        return NextResponse.json(
          { error: 'Failed to get chapters' },
          { status: backendResponse.status }
        )
      }
    }

    const responseData = await backendResponse.json()
    
    // Transform the chapter data to match frontend expectations
    const chapters = responseData.chapters || []
    const transformedChapters = chapters.map(transformChapterData)
    
    return NextResponse.json({
      chapters: transformedChapters,
      total: transformedChapters.length,
      project_id: projectId
    })

  } catch (error) {
    console.error('[project-chapters] Error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
} 