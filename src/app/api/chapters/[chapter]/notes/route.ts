import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

interface DirectorNoteRequest {
  content: string
  position?: number
}

interface DirectorNote {
  note_id: string
  chapter_id: string
  content: string
  created_by: string
  created_at: string
  resolved: boolean
  resolved_at?: string
  position?: number
}

// In-memory storage for development (replace with Firestore in production)
const notesStorage = new Map<string, DirectorNote>()

export async function POST(
  request: NextRequest,
  { params }: { params: { chapter: string } }
) {
  try {
    const { userId } = auth()
    
    if (!userId) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const { chapter: chapterId } = params
    const noteData: DirectorNoteRequest = await request.json()

    // Validate required fields
    if (!noteData.content || !noteData.content.trim()) {
      return NextResponse.json(
        { error: 'Note content is required' },
        { status: 400 }
      )
    }

    // Create director note
    const noteId = `note_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    const directorNote: DirectorNote = {
      note_id: noteId,
      chapter_id: chapterId,
      content: noteData.content.trim(),
      created_by: userId,
      created_at: new Date().toISOString(),
      resolved: false,
      position: noteData.position
    }

    // Store note (in production, this would save to Firestore)
    notesStorage.set(noteId, directorNote)

    console.log(`Director note created for user ${userId}:`, {
      noteId,
      chapterId,
      contentLength: noteData.content.length,
      hasPosition: noteData.position !== undefined
    })

    return NextResponse.json({
      success: true,
      message: 'Director note added successfully',
      note: {
        note_id: directorNote.note_id,
        content: directorNote.content,
        created_at: directorNote.created_at,
        resolved: directorNote.resolved,
        position: directorNote.position
      }
    })

  } catch (error) {
    console.error(`POST /api/chapters/${params.chapter}/notes error:`, error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}

export async function GET(
  request: NextRequest,
  { params }: { params: { chapter: string } }
) {
  try {
    const { userId } = auth()
    
    if (!userId) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const { chapter: chapterId } = params

    // Get all notes for the chapter
    const chapterNotes = Array.from(notesStorage.values())
      .filter(note => note.chapter_id === chapterId)
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      .map(note => ({
        note_id: note.note_id,
        content: note.content,
        created_by: note.created_by,
        created_at: note.created_at,
        resolved: note.resolved,
        resolved_at: note.resolved_at,
        position: note.position
      }))

    return NextResponse.json({
      success: true,
      notes: chapterNotes,
      total: chapterNotes.length
    })

  } catch (error) {
    console.error(`GET /api/chapters/${params.chapter}/notes error:`, error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
} 