import { NextRequest, NextResponse } from 'next/server'
import { readFileSync, writeFileSync, statSync } from 'fs'
import path from 'path'

export async function GET(
  request: NextRequest,
  { params }: { params: { filename: string } }
) {
  try {
    const filename = params.filename
    
    // Validate filename
    if (!filename.endsWith('.md')) {
      return NextResponse.json(
        { error: 'Invalid filename. Must be a .md file' },
        { status: 400 }
      )
    }

    const projectRoot = process.cwd()
    const filePath = path.join(projectRoot, 'references', filename)

    try {
      const content = readFileSync(filePath, 'utf8')
      const stats = statSync(filePath)

      return NextResponse.json({
        success: true,
        name: filename,
        content: content,
        lastModified: stats.mtime.toISOString(),
        size: stats.size
      })
    } catch (error: any) {
      if (error.code === 'ENOENT') {
        return NextResponse.json(
          { error: `Reference file '${filename}' not found` },
          { status: 404 }
        )
      }
      throw error
    }

  } catch (error: any) {
    console.error('Failed to get reference file:', error)
    return NextResponse.json(
      { error: `Failed to get reference file: ${error.message}` },
      { status: 500 }
    )
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: { filename: string } }
) {
  try {
    const filename = params.filename
    const { content } = await request.json()
    
    // Validate filename
    if (!filename.endsWith('.md')) {
      return NextResponse.json(
        { error: 'Invalid filename. Must be a .md file' },
        { status: 400 }
      )
    }

    if (!content) {
      return NextResponse.json(
        { error: 'Content is required' },
        { status: 400 }
      )
    }

    const projectRoot = process.cwd()
    const filePath = path.join(projectRoot, 'references', filename)

    // Check if file exists
    try {
      statSync(filePath)
    } catch (error: any) {
      if (error.code === 'ENOENT') {
        return NextResponse.json(
          { error: `Reference file '${filename}' not found` },
          { status: 404 }
        )
      }
      throw error
    }

    // Write the updated content
    writeFileSync(filePath, content, 'utf8')

    // Get updated file stats
    const stats = statSync(filePath)

    return NextResponse.json({
      success: true,
      message: `Reference file '${filename}' updated successfully`,
      name: filename,
      lastModified: stats.mtime.toISOString(),
      size: stats.size
    })

  } catch (error: any) {
    console.error('Failed to update reference file:', error)
    return NextResponse.json(
      { error: `Failed to update reference file: ${error.message}` },
      { status: 500 }
    )
  }
} 