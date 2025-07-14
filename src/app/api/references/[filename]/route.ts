import { NextRequest, NextResponse } from 'next/server'
import { readFileSync, writeFileSync, statSync } from 'fs'
import path from 'path'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

// Helper to build the absolute file path for a project reference file
function resolveFilePath(projectId: string | null, filename: string): string {
  if (!projectId) {
    throw new Error('Missing "project_id" query parameter')
  }

  const tempRoot = process.env.TEMP_PROJECTS_DIR?.trim() || '/tmp/book_writer/temp_projects'
  return path.join(tempRoot, projectId, 'references', filename)
}

export async function GET(
  request: NextRequest,
  { params }: { params: { filename: string } }
) {
  try {
    const filename = params.filename
    const projectId = request.nextUrl.searchParams.get('project_id')
    
    // Validate filename
    if (!filename.endsWith('.md')) {
      return NextResponse.json(
        { error: 'Invalid filename. Must be a .md file' },
        { status: 400 }
      )
    }

    const filePath = resolveFilePath(projectId, filename)

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
    const projectId = request.nextUrl.searchParams.get('project_id')
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

    const filePath = resolveFilePath(projectId, filename)

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