import { NextRequest, NextResponse } from 'next/server'
import { readdirSync, statSync, readFileSync } from 'fs'
import path from 'path'

export async function GET(request: NextRequest) {
  try {
    const projectRoot = process.cwd()
    const chaptersDir = path.join(projectRoot, 'chapters')
    const logsDir = path.join(projectRoot, 'logs')

    // Check if chapters directory exists
    try {
      statSync(chaptersDir)
    } catch {
      return NextResponse.json({
        success: true,
        chapters: []
      })
    }

    // Get all chapter files
    const files = readdirSync(chaptersDir)
    const chapterFiles = files.filter(file => 
      file.startsWith('chapter-') && file.endsWith('.md')
    )

    const chapters = []

    for (const file of chapterFiles) {
      const filePath = path.join(chaptersDir, file)
      const stats = statSync(filePath)
      
      // Extract chapter number from filename
      const match = file.match(/chapter-(\d+)\.md/)
      if (!match) continue
      
      const chapterNumber = parseInt(match[1])
      
      // Read chapter content to get word count
      const content = readFileSync(filePath, 'utf8')
      const wordCount = content.split(/\s+/).filter(word => word.length > 0).length

      // Try to read metadata from logs
      let metadata = {
        generation_time: 0,
        cost: 0,
        quality_score: undefined
      }

      try {
        const logFile = path.join(logsDir, `chapter_${chapterNumber}_metadata.json`)
        const logContent = readFileSync(logFile, 'utf8')
        const logData = JSON.parse(logContent)
        metadata = {
          generation_time: logData.generation_time || 0,
          cost: logData.total_cost || 0,
          quality_score: logData.quality_score
        }
      } catch {
        // Log file doesn't exist or is invalid, use defaults
      }

      chapters.push({
        chapter: chapterNumber,
        filename: file,
        word_count: wordCount,
        created_at: stats.mtime.toISOString(),
        status: 'completed',
        ...metadata
      })
    }

    // Sort chapters by chapter number
    chapters.sort((a, b) => a.chapter - b.chapter)

    return NextResponse.json({
      success: true,
      chapters: chapters,
      total: chapters.length
    })

  } catch (error: any) {
    console.error('Failed to list chapters:', error)
    return NextResponse.json(
      { error: `Failed to list chapters: ${error.message}` },
      { status: 500 }
    )
  }
} 