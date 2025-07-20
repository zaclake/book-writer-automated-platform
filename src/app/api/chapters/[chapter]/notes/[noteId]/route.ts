import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

interface UpdateNoteRequest {
  content?: string
  resolved?: boolean
}

// This would be imported from the main storage in production
const notesStorage = new Map<string, any>()

export async function PUT(
  request: NextRequest,
  { params }: { params: { chapter: string, noteId: string } }
) {
  try {
    const { userId } = auth()
    
    if (!userId) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const { noteId } = params
    const updateData: UpdateNoteRequest = await request.json()

    // Get existing note
    const note = notesStorage.get(noteId)

    if (!note) {
      return NextResponse.json(
        { error: 'Note not found' },
        { status: 404 }
      )
    }

    // Check ownership (users can only update their own notes)
    if (note.created_by !== userId) {
      return NextResponse.json(
        { error: 'Access denied' },
        { status: 403 }
      )
    }

    // Update note data
    if (updateData.content !== undefined) {
      note.content = updateData.content.trim()
    }

    if (updateData.resolved !== undefined) {
      note.resolved = updateData.resolved
      if (updateData.resolved) {
        note.resolved_at = new Date().toISOString()
      } else {
        note.resolved_at = undefined
      }
    }

    // Save updated note
    notesStorage.set(noteId, note)

    console.log(`Director note updated for user ${userId}:`, {
      noteId,
      updatedFields: Object.keys(updateData),
      resolved: note.resolved
    })

    return NextResponse.json({
      success: true,
      message: 'Director note updated successfully',
      note: {
        note_id: note.note_id,
        content: note.content,
        resolved: note.resolved,
        resolved_at: note.resolved_at,
        position: note.position
      }
    })

  } catch (error) {
    console.error(`PUT /api/chapters/${params.chapter}/notes/${params.noteId} error:`, error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: { chapter: string, noteId: string } }
) {
  try {
    const { userId } = auth()
    
    if (!userId) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const { noteId } = params

    // Get note to verify ownership
    const note = notesStorage.get(noteId)

    if (!note) {
      return NextResponse.json(
        { error: 'Note not found' },
        { status: 404 }
      )
    }

    // Check ownership (users can only delete their own notes)
    if (note.created_by !== userId) {
      return NextResponse.json(
        { error: 'Access denied' },
        { status: 403 }
      )
    }

    // Delete note
    notesStorage.delete(noteId)

    console.log(`Director note deleted for user ${userId}:`, {
      noteId,
      chapterId: note.chapter_id
    })

    return NextResponse.json({
      success: true,
      message: 'Director note deleted successfully'
    })

  } catch (error) {
    console.error(`DELETE /api/chapters/${params.chapter}/notes/${params.noteId} error:`, error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
} 