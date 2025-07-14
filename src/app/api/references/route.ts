import { NextRequest, NextResponse } from 'next/server'
import { readdirSync, statSync } from 'fs'
import path from 'path'

// Force dynamic rendering/runtime so we can access the filesystem at request time
export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

/**
 * Determine the absolute path to the references directory for the given project.
 * Falls back to the same TEMP_PROJECTS_DIR convention used by the FastAPI backend.
 */
function getReferencesDir(projectId: string | null): string {
  if (!projectId) {
    throw new Error('Missing "project_id" query parameter')
  }

  // Mirror logic in backend/utils/paths.py – default to /tmp/book_writer/temp_projects
  const tempRoot = process.env.TEMP_PROJECTS_DIR?.trim() || '/tmp/book_writer/temp_projects'
  return path.join(tempRoot, projectId, 'references')
}

export async function GET(request: NextRequest) {
  try {
    const projectId = request.nextUrl.searchParams.get('project_id')
    const referencesDir = getReferencesDir(projectId)

    // Check if references directory exists
    try {
      statSync(referencesDir)
    } catch {
      return NextResponse.json({
        success: true,
        files: []
      })
    }

    // Get all reference files
    const files = readdirSync(referencesDir)
    const referenceFiles = files.filter(file => file.endsWith('.md'))

    const fileList = []

    for (const file of referenceFiles) {
      const filePath = path.join(referencesDir, file)
      const stats = statSync(filePath)
      
      fileList.push({
        name: file,
        lastModified: stats.mtime.toISOString(),
        size: stats.size
      })
    }

    // Sort by name
    fileList.sort((a, b) => a.name.localeCompare(b.name))

    return NextResponse.json({
      success: true,
      files: fileList,
      total: fileList.length
    })

  } catch (error: any) {
    console.error('Failed to list reference files:', error)
    return NextResponse.json(
      { error: `Failed to list reference files: ${error.message}` },
      { status: 500 }
    )
  }
} 