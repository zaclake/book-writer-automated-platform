import { NextRequest, NextResponse } from 'next/server'
import { readFileSync, statSync, readdirSync } from 'fs'
import path from 'path'

export async function GET(request: NextRequest) {
  try {
    const projectRoot = process.cwd()
    
    // Check for book bible
    const bookBiblePath = path.join(projectRoot, 'book-bible.md')
    let hasBookBible = false
    try {
      statSync(bookBiblePath)
      hasBookBible = true
    } catch {}

    // Check for reference files
    const referencesDir = path.join(projectRoot, 'references')
    let hasReferences = false
    let referenceFiles: string[] = []
    try {
      statSync(referencesDir)
      hasReferences = true
      referenceFiles = readdirSync(referencesDir).filter(f => f.endsWith('.md'))
    } catch {}

    // Check for project state
    const stateDir = path.join(projectRoot, '.project-state')
    let hasState = false
    try {
      statSync(stateDir)
      hasState = true
    } catch {}

    // Check for project metadata
    const metadataPath = path.join(projectRoot, '.project-meta.json')
    let metadata = null
    try {
      const metadataContent = readFileSync(metadataPath, 'utf8')
      metadata = JSON.parse(metadataContent)
    } catch {}

    const initialized = hasBookBible && hasReferences && hasState
    
    const status = {
      initialized,
      hasBookBible,
      hasReferences,
      hasState,
      referenceFiles,
      metadata,
      message: initialized 
        ? 'Project fully initialized and ready for chapter generation'
        : `Project incomplete. Missing: ${[
            !hasBookBible && 'book-bible.md',
            !hasReferences && 'reference files',
            !hasState && 'project state'
          ].filter(Boolean).join(', ')}`
    }

    return NextResponse.json(status)

  } catch (error: any) {
    console.error('Failed to get project status:', error)
    return NextResponse.json(
      { error: `Failed to get project status: ${error.message}` },
      { status: 500 }
    )
  }
} 