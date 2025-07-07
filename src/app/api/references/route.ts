import { NextRequest, NextResponse } from 'next/server'
import { readdirSync, statSync } from 'fs'
import path from 'path'

export async function GET(request: NextRequest) {
  try {
    const projectRoot = process.cwd()
    const referencesDir = path.join(projectRoot, 'references')

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