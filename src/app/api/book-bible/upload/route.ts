import { NextRequest, NextResponse } from 'next/server'
import { writeFileSync, mkdirSync } from 'fs'
import path from 'path'

export async function POST(request: NextRequest) {
  try {
    const { filename, content, projectInfo } = await request.json()

    if (!filename || !content) {
      return NextResponse.json(
        { error: 'Filename and content are required' },
        { status: 400 }
      )
    }

    // Validate that it's a markdown file
    if (!filename.endsWith('.md')) {
      return NextResponse.json(
        { error: 'File must be a Markdown (.md) file' },
        { status: 400 }
      )
    }

    const projectRoot = process.cwd()
    
    // Ensure directories exist
    mkdirSync(path.join(projectRoot, 'references'), { recursive: true })
    mkdirSync(path.join(projectRoot, 'chapters'), { recursive: true })
    mkdirSync(path.join(projectRoot, 'notes'), { recursive: true })

    // Save the book bible file
    const bookBiblePath = path.join(projectRoot, 'book-bible.md')
    writeFileSync(bookBiblePath, content, 'utf8')

    // Save project metadata if provided
    if (projectInfo) {
      const metadataPath = path.join(projectRoot, '.project-meta.json')
      const metadata = {
        title: projectInfo.title || 'Untitled Project',
        genre: projectInfo.genre || 'Unknown',
        logline: projectInfo.logline || '',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        book_bible_uploaded: true
      }
      writeFileSync(metadataPath, JSON.stringify(metadata, null, 2), 'utf8')
    }

    return NextResponse.json({
      success: true,
      message: 'Book Bible uploaded successfully',
      filename: filename,
      projectInfo: projectInfo
    })

  } catch (error: any) {
    console.error('Book Bible upload error:', error)
    return NextResponse.json(
      { error: `Upload failed: ${error.message}` },
      { status: 500 }
    )
  }
} 