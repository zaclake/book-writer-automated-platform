import { NextRequest, NextResponse } from 'next/server'
import { readFileSync, unlinkSync, statSync } from 'fs'
import path from 'path'

export async function GET(
  request: NextRequest,
  { params }: { params: { chapter: string } }
) {
  try {
    const chapterNumber = parseInt(params.chapter)
    
    if (isNaN(chapterNumber) || chapterNumber < 1) {
      return NextResponse.json(
        { error: 'Invalid chapter number' },
        { status: 400 }
      )
    }

    const projectRoot = process.cwd()
    const chapterFile = path.join(projectRoot, 'chapters', `chapter-${chapterNumber.toString().padStart(2, '0')}.md`)

    try {
      const content = readFileSync(chapterFile, 'utf8')
      const stats = statSync(chapterFile)

      return NextResponse.json({
        success: true,
        chapter: chapterNumber,
        content: content,
        last_modified: stats.mtime.toISOString()
      })
    } catch (error: any) {
      if (error.code === 'ENOENT') {
        return NextResponse.json(
          { error: `Chapter ${chapterNumber} not found` },
          { status: 404 }
        )
      }
      throw error
    }

  } catch (error: any) {
    console.error('Failed to get chapter:', error)
    return NextResponse.json(
      { error: `Failed to get chapter: ${error.message}` },
      { status: 500 }
    )
  }
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: { chapter: string } }
) {
  try {
    const chapterNumber = parseInt(params.chapter)
    
    if (isNaN(chapterNumber) || chapterNumber < 1) {
      return NextResponse.json(
        { error: 'Invalid chapter number' },
        { status: 400 }
      )
    }

    const projectRoot = process.cwd()
    const chapterFile = path.join(projectRoot, 'chapters', `chapter-${chapterNumber.toString().padStart(2, '0')}.md`)
    const logFile = path.join(projectRoot, 'logs', `chapter_${chapterNumber}_metadata.json`)

    try {
      // Delete the chapter file
      unlinkSync(chapterFile)
    } catch (error: any) {
      if (error.code === 'ENOENT') {
        return NextResponse.json(
          { error: `Chapter ${chapterNumber} not found` },
          { status: 404 }
        )
      }
      throw error
    }

    // Try to delete the log file (optional)
    try {
      unlinkSync(logFile)
    } catch {
      // Log file doesn't exist, that's fine
    }

    return NextResponse.json({
      success: true,
      message: `Chapter ${chapterNumber} deleted successfully`
    })

  } catch (error: any) {
    console.error('Failed to delete chapter:', error)
    return NextResponse.json(
      { error: `Failed to delete chapter: ${error.message}` },
      { status: 500 }
    )
  }
} 