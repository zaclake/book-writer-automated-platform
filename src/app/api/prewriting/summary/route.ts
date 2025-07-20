import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

interface PrewritingSummaryRequest {
  project_id: string
  book_bible_content: string
  settings: {
    target_chapters: number
    word_count_per_chapter: number
    involvement_level?: string
    purpose?: string
  }
  must_include_sections: string[]
}

interface PrewritingSummary {
  project_id: string
  title: string
  genre: string
  premise: string
  main_characters: Array<{
    name: string
    description: string
    role?: string
  }>
  setting: {
    description: string
    time?: string
    place?: string
  }
  central_conflict: string
  themes: string[]
  story_structure: {
    act1: string
    act2: string
    act3: string
  }
  chapter_outline: Array<{
    chapter: number
    description: string
    act: string
  }>
  writing_guidelines: {
    tone: string
    target_audience: string
    writing_style: string
    pacing_strategy: string
  }
  must_include_elements: string[]
  generated_at: string
  word_count_target: number
  total_chapters: number
}

// In-memory storage for development (replace with Firestore in production)
const summaryStorage = new Map<string, PrewritingSummary>()

async function generatePrewritingSummary(
  request: PrewritingSummaryRequest,
  userId: string
): Promise<PrewritingSummary> {
  // In production, this would call the Python backend service
  // For now, return a structured mock response based on the content
  
  const { book_bible_content, settings, project_id, must_include_sections } = request
  
  // Parse basic information from book bible content
  const titleMatch = book_bible_content.match(/^#\s+(.+)/m)
  const title = titleMatch ? titleMatch[1].trim() : 'Untitled Project'
  
  const genreMatch = book_bible_content.match(/##\s*Genre\s*\n([^\n]+)/i)
  const genre = genreMatch ? genreMatch[1].trim() : 'Fiction'
  
  const premiseMatch = book_bible_content.match(/##\s*Premise\s*\n([\s\S]*?)(?=##|$)/i)
  const premise = premiseMatch ? premiseMatch[1].trim().substring(0, 500) : 'An engaging story premise'
  
  // Extract characters
  const charactersMatch = book_bible_content.match(/##\s*(?:Main\s+)?Characters?\s*\n([\s\S]*?)(?=##|$)/i)
  const main_characters = []
  if (charactersMatch) {
    const characterText = charactersMatch[1]
    const characterLines = characterText.split('\n').filter(line => line.trim())
    
    for (const line of characterLines.slice(0, 5)) { // Limit to 5 characters
      if (line.includes(':')) {
        const [name, description] = line.split(':', 2)
        main_characters.push({
          name: name.replace(/[*\-•]/, '').trim(),
          description: description.trim()
        })
      }
    }
  }
  
  if (main_characters.length === 0) {
    main_characters.push({
      name: 'Protagonist',
      description: 'Main character driving the story forward'
    })
  }
  
  // Extract setting
  const settingMatch = book_bible_content.match(/##\s*Setting\s*\n([\s\S]*?)(?=##|$)/i)
  const setting = {
    description: settingMatch ? settingMatch[1].trim().substring(0, 300) : 'Contemporary setting',
    time: 'Present day',
    place: 'Urban environment'
  }
  
  // Extract conflict
  const conflictMatch = book_bible_content.match(/##\s*(?:Central\s+)?Conflict\s*\n([\s\S]*?)(?=##|$)/i)
  const central_conflict = conflictMatch ? conflictMatch[1].trim().substring(0, 400) : 'Character faces compelling challenges'
  
  // Extract themes
  const themesMatch = book_bible_content.match(/##\s*Themes?\s*\n([\s\S]*?)(?=##|$)/i)
  let themes = ['Character growth', 'Conflict resolution']
  if (themesMatch) {
    const themeText = themesMatch[1]
    const extractedThemes = themeText.split(/[,\n•\-]/).map(t => t.trim()).filter(t => t.length > 3)
    if (extractedThemes.length > 0) {
      themes = extractedThemes.slice(0, 5)
    }
  }
  
  // Generate story structure
  const story_structure = {
    act1: 'Setup and introduction of characters and central conflict',
    act2: 'Development and escalation of conflict with complications',
    act3: 'Resolution and conclusion of character arcs'
  }
  
  // Generate chapter outline
  const chapter_outline = []
  const act1_end = Math.floor(settings.target_chapters / 3)
  const act2_end = Math.floor((settings.target_chapters * 2) / 3)
  
  for (let i = 1; i <= settings.target_chapters; i++) {
    let act = 'act1'
    let description = `Chapter ${i}: Story development`
    
    if (i <= act1_end) {
      act = 'act1'
      if (i === 1) description = `Chapter ${i}: Opening and character introduction`
      else if (i === act1_end) description = `Chapter ${i}: Inciting incident and plot setup`
      else description = `Chapter ${i}: Character and world establishment`
    } else if (i <= act2_end) {
      act = 'act2'
      if (i === Math.floor(settings.target_chapters / 2)) description = `Chapter ${i}: Midpoint revelation or reversal`
      else if (i === act2_end) description = `Chapter ${i}: Crisis and major setback`
      else description = `Chapter ${i}: Conflict development and complications`
    } else {
      act = 'act3'
      if (i === settings.target_chapters) description = `Chapter ${i}: Resolution and conclusion`
      else if (i === settings.target_chapters - 1) description = `Chapter ${i}: Climax and final confrontation`
      else description = `Chapter ${i}: Building to climax`
    }
    
    chapter_outline.push({
      chapter: i,
      description,
      act
    })
  }
  
  // Generate writing guidelines
  const writing_guidelines = {
    tone: 'Professional and engaging',
    target_audience: 'General adult readers',
    writing_style: 'Clear narrative with strong character focus',
    pacing_strategy: 'Balanced progression with tension building'
  }
  
  const summary: PrewritingSummary = {
    project_id,
    title,
    genre,
    premise,
    main_characters,
    setting,
    central_conflict,
    themes,
    story_structure,
    chapter_outline,
    writing_guidelines,
    must_include_elements: must_include_sections,
    generated_at: new Date().toISOString(),
    word_count_target: settings.word_count_per_chapter,
    total_chapters: settings.target_chapters
  }
  
  return summary
}

export async function POST(request: NextRequest) {
  try {
    const { userId } = auth()
    
    if (!userId) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const requestData: PrewritingSummaryRequest = await request.json()

    // Validate required fields
    if (!requestData.project_id || !requestData.book_bible_content) {
      return NextResponse.json(
        { error: 'Project ID and book bible content are required' },
        { status: 400 }
      )
    }

    // Generate the prewriting summary
    const summary = await generatePrewritingSummary(requestData, userId)

    // Store the summary (in production, this would save to Firestore)
    const summaryKey = `${userId}_${requestData.project_id}`
    summaryStorage.set(summaryKey, summary)

    console.log(`Prewriting summary generated for user ${userId}:`, {
      projectId: requestData.project_id,
      title: summary.title,
      characterCount: summary.main_characters.length,
      chapterCount: summary.total_chapters,
      themesCount: summary.themes.length
    })

    return NextResponse.json({
      success: true,
      message: 'Prewriting summary generated successfully',
      summary: {
        project_id: summary.project_id,
        title: summary.title,
        genre: summary.genre,
        premise: summary.premise,
        main_characters: summary.main_characters,
        setting: summary.setting,
        central_conflict: summary.central_conflict,
        themes: summary.themes,
        story_structure: summary.story_structure,
        chapter_outline: summary.chapter_outline,
        writing_guidelines: summary.writing_guidelines,
        must_include_elements: summary.must_include_elements,
        generated_at: summary.generated_at,
        word_count_target: summary.word_count_target,
        total_chapters: summary.total_chapters
      }
    })

  } catch (error) {
    console.error('POST /api/prewriting/summary error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}

export async function GET(request: NextRequest) {
  try {
    const { userId } = auth()
    
    if (!userId) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const { searchParams } = new URL(request.url)
    const projectId = searchParams.get('project_id')

    if (!projectId) {
      return NextResponse.json(
        { error: 'Project ID is required' },
        { status: 400 }
      )
    }

    // Get the summary from storage
    const summaryKey = `${userId}_${projectId}`
    const summary = summaryStorage.get(summaryKey)

    if (!summary) {
      return NextResponse.json(
        { error: 'Prewriting summary not found' },
        { status: 404 }
      )
    }

    return NextResponse.json({
      success: true,
      summary
    })

  } catch (error) {
    console.error('GET /api/prewriting/summary error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
} 