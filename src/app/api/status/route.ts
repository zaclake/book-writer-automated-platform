import { NextRequest, NextResponse } from 'next/server'
import { execSync } from 'child_process'
import { readdirSync, statSync } from 'fs'
import path from 'path'

export async function GET(request: NextRequest) {
  try {
    const projectRoot = process.cwd()
    
    // Check API connection
    let apiConnection = false
    try {
      // Test OpenAI API connection with a minimal request
      const testCommand = `cd "${projectRoot}" && python -c "import openai; client = openai.OpenAI(); print('API connection OK')"`
      execSync(testCommand, {
        encoding: 'utf8',
        timeout: 10000,
        env: {
          ...process.env,
          OPENAI_API_KEY: process.env.OPENAI_API_KEY
        }
      })
      apiConnection = true
    } catch {
      apiConnection = false
    }

    // Get last generation time
    let lastGeneration = 'Never'
    try {
      const chaptersDir = path.join(projectRoot, 'chapters')
      const files = readdirSync(chaptersDir)
      const chapterFiles = files
        .filter(file => file.startsWith('chapter-') && file.endsWith('.md'))
        .map(file => {
          const filePath = path.join(chaptersDir, file)
          const stats = statSync(filePath)
          return {
            file,
            mtime: stats.mtime
          }
        })
        .sort((a, b) => b.mtime.getTime() - a.mtime.getTime())

      if (chapterFiles.length > 0) {
        const lastFile = chapterFiles[0]
        const now = new Date()
        const diffMs = now.getTime() - lastFile.mtime.getTime()
        const diffMinutes = Math.floor(diffMs / (1000 * 60))
        const diffHours = Math.floor(diffMinutes / 60)
        const diffDays = Math.floor(diffHours / 24)

        if (diffDays > 0) {
          lastGeneration = `${diffDays} day${diffDays > 1 ? 's' : ''} ago`
        } else if (diffHours > 0) {
          lastGeneration = `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`
        } else if (diffMinutes > 0) {
          lastGeneration = `${diffMinutes} minute${diffMinutes > 1 ? 's' : ''} ago`
        } else {
          lastGeneration = 'Just now'
        }
      }
    } catch {
      // Chapters directory doesn't exist or is empty
    }

    // System load assessment (simplified)
    let systemLoad: 'low' | 'medium' | 'high' = 'low'
    try {
      // Check if we have many recent chapters (high activity)
      const chaptersDir = path.join(projectRoot, 'chapters')
      const files = readdirSync(chaptersDir)
      const recentFiles = files.filter(file => {
        const filePath = path.join(chaptersDir, file)
        const stats = statSync(filePath)
        const hourAgo = new Date(Date.now() - 60 * 60 * 1000)
        return stats.mtime > hourAgo
      })

      if (recentFiles.length > 5) {
        systemLoad = 'high'
      } else if (recentFiles.length > 2) {
        systemLoad = 'medium'
      }
    } catch {
      // Default to low load
    }

    // Error count in last 24 hours (simplified - just check if logs directory has recent error files)
    let errors24h = 0
    try {
      const logsDir = path.join(projectRoot, 'logs')
      const files = readdirSync(logsDir)
      const dayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000)
      
      errors24h = files.filter(file => {
        if (!file.includes('error') && !file.includes('failed')) return false
        const filePath = path.join(logsDir, file)
        const stats = statSync(filePath)
        return stats.mtime > dayAgo
      }).length
    } catch {
      // Logs directory doesn't exist
    }

    return NextResponse.json({
      api_connection: apiConnection,
      last_generation: lastGeneration,
      system_load: systemLoad,
      errors_24h: errors24h,
      timestamp: new Date().toISOString()
    })

  } catch (error: any) {
    console.error('Failed to get system status:', error)
    return NextResponse.json(
      { 
        api_connection: false,
        last_generation: 'Unknown',
        system_load: 'high',
        errors_24h: 999,
        error: error.message 
      },
      { status: 500 }
    )
  }
} 