import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

// This would be imported from the main storage in production
const projectStorage = new Map<string, any>()

interface UpdateBookBibleData {
  title?: string
  genre?: string
  book_bible_content?: string
  must_include_sections?: string[]
  settings?: {
    target_chapters?: number
    word_count_per_chapter?: number
    involvement_level?: string
    purpose?: string
  }
}

export async function GET(
  request: NextRequest,
  { params }: { params: { projectId: string } }
) {
  try {
    const { userId } = auth()
    
    if (!userId) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const { projectId } = params

    // Get project from storage (in production, this would be Firestore)
    const project = projectStorage.get(projectId)

    if (!project) {
      return NextResponse.json(
        { error: 'Project not found' },
        { status: 404 }
      )
    }

    // Check ownership
    if (project.owner_id !== userId) {
      return NextResponse.json(
        { error: 'Access denied' },
        { status: 403 }
      )
    }

    return NextResponse.json({
      success: true,
      project: {
        id: project.id,
        title: project.title,
        genre: project.genre,
        book_bible_content: project.book_bible_content,
        must_include_sections: project.must_include_sections,
        settings: project.settings,
        status: project.status,
        created_at: project.created_at,
        updated_at: project.updated_at
      }
    })

  } catch (error) {
    console.error(`GET /api/book-bible/${params.projectId} error:`, error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: { projectId: string } }
) {
  try {
    const { userId } = auth()
    
    if (!userId) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const { projectId } = params
    const updateData: UpdateBookBibleData = await request.json()

    // Get existing project
    const project = projectStorage.get(projectId)

    if (!project) {
      return NextResponse.json(
        { error: 'Project not found' },
        { status: 404 }
      )
    }

    // Check ownership
    if (project.owner_id !== userId) {
      return NextResponse.json(
        { error: 'Access denied' },
        { status: 403 }
      )
    }

    // Update project data
    const updatedProject = {
      ...project,
      ...updateData,
      settings: {
        ...project.settings,
        ...updateData.settings
      },
      updated_at: new Date().toISOString()
    }

    // Save updated project
    projectStorage.set(projectId, updatedProject)

    console.log(`Book Bible updated for user ${userId}:`, {
      projectId,
      title: updatedProject.title,
      updatedFields: Object.keys(updateData)
    })

    return NextResponse.json({
      success: true,
      message: 'Book Bible updated successfully',
      project: {
        id: updatedProject.id,
        title: updatedProject.title,
        genre: updatedProject.genre,
        status: updatedProject.status,
        updated_at: updatedProject.updated_at,
        settings: updatedProject.settings
      }
    })

  } catch (error) {
    console.error(`PUT /api/book-bible/${params.projectId} error:`, error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: { projectId: string } }
) {
  try {
    const { userId } = auth()
    
    if (!userId) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const { projectId } = params

    // Get project to verify ownership
    const project = projectStorage.get(projectId)

    if (!project) {
      return NextResponse.json(
        { error: 'Project not found' },
        { status: 404 }
      )
    }

    // Check ownership
    if (project.owner_id !== userId) {
      return NextResponse.json(
        { error: 'Access denied' },
        { status: 403 }
      )
    }

    // Delete project
    projectStorage.delete(projectId)

    console.log(`Book Bible deleted for user ${userId}:`, {
      projectId,
      title: project.title
    })

    // In production, this would also:
    // 1. Delete all associated chapters
    // 2. Delete reference files
    // 3. Clean up any background jobs
    // 4. Remove from pattern database

    return NextResponse.json({
      success: true,
      message: 'Book Bible deleted successfully'
    })

  } catch (error) {
    console.error(`DELETE /api/book-bible/${params.projectId} error:`, error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
} 