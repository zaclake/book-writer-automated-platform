import { NextRequest, NextResponse } from 'next/server'

export async function POST(request: NextRequest) {
  try {
    const { chapter, words, stage, projectId, userId } = await request.json()

    if (!chapter || !words || !projectId || !userId) {
      return NextResponse.json(
        { error: 'Chapter number, word count, project ID, and user ID are required' },
        { status: 400 }
      )
    }

    // Validate inputs
    if (chapter < 1 || chapter > 200) {
      return NextResponse.json(
        { error: 'Chapter number must be between 1 and 200' },
        { status: 400 }
      )
    }

    if (words < 500 || words > 10000) {
      return NextResponse.json(
        { error: 'Word count must be between 500 and 10000' },
        { status: 400 }
      )
    }

    const validStages = ['spike', 'complete', '5-stage']
    if (stage && !validStages.includes(stage)) {
      return NextResponse.json(
        { error: 'Invalid stage. Must be one of: spike, complete, 5-stage' },
        { status: 400 }
      )
    }

    // For now, return a simple success response for deployment testing
    return NextResponse.json({
      success: true,
      message: 'Chapter generation initiated',
      chapter,
      words,
      stage: stage || 'complete',
      projectId,
      userId
    })

  } catch (error: any) {
    console.error('Generation error:', error)
    
    return NextResponse.json(
      { error: `Generation failed: ${error.message}` },
      { status: 500 }
    )
  }
}

 