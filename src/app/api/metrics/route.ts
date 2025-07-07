import { NextRequest, NextResponse } from 'next/server'
import { readdirSync, readFileSync, statSync } from 'fs'
import path from 'path'

export async function GET(request: NextRequest) {
  try {
    const projectRoot = process.cwd()
    const chaptersDir = path.join(projectRoot, 'chapters')
    const logsDir = path.join(projectRoot, 'logs')

    // Initialize metrics
    const metrics = {
      total_chapters: 0,
      total_cost: 0,
      average_cost_per_chapter: 0,
      monthly_cost: 0,
      average_quality: 0,
      quality_distribution: {
        excellent: 0,
        good: 0,
        fair: 0,
        poor: 0
      },
      quality_trend: [] as Array<{ chapter: number; score: number; date: string }>,
      cost_trend: [] as Array<{ chapter: number; cost: number; date: string }>,
      budget_remaining: 100
    }

    // Check if chapters directory exists
    try {
      statSync(chaptersDir)
    } catch {
      return NextResponse.json(metrics)
    }

    // Get all chapter files
    const files = readdirSync(chaptersDir)
    const chapterFiles = files.filter(file => 
      file.startsWith('chapter-') && file.endsWith('.md')
    )

    if (chapterFiles.length === 0) {
      return NextResponse.json(metrics)
    }

    let totalCost = 0
    let totalQuality = 0
    let qualityCount = 0
    const qualityTrend: Array<{ chapter: number; score: number; date: string }> = []
    const costTrend: Array<{ chapter: number; cost: number; date: string }> = []
    const currentMonth = new Date().getMonth()
    const currentYear = new Date().getFullYear()
    let monthlyCost = 0

    for (const file of chapterFiles) {
      // Extract chapter number
      const match = file.match(/chapter-(\d+)\.md/)
      if (!match) continue
      
      const chapterNumber = parseInt(match[1])
      
      // Try to read metadata from logs
      try {
        const logFile = path.join(logsDir, `chapter_${chapterNumber}_metadata.json`)
        const logContent = readFileSync(logFile, 'utf8')
        const logData = JSON.parse(logContent)
        
        const cost = logData.total_cost || 0
        const qualityScore = logData.quality_score
        const createdAt = new Date(logData.timestamp || logData.created_at || Date.now())
        
        totalCost += cost
        
        // Check if this chapter was created this month
        if (createdAt.getMonth() === currentMonth && createdAt.getFullYear() === currentYear) {
          monthlyCost += cost
        }
        
        // Quality metrics
        if (qualityScore !== undefined && qualityScore !== null) {
          totalQuality += qualityScore
          qualityCount++
          
          // Quality distribution
          if (qualityScore >= 80) {
            metrics.quality_distribution.excellent++
          } else if (qualityScore >= 70) {
            metrics.quality_distribution.good++
          } else if (qualityScore >= 60) {
            metrics.quality_distribution.fair++
          } else {
            metrics.quality_distribution.poor++
          }
          
          // Quality trend
          qualityTrend.push({
            chapter: chapterNumber,
            score: qualityScore,
            date: createdAt.toISOString()
          })
        }
        
        // Cost trend
        costTrend.push({
          chapter: chapterNumber,
          cost: cost,
          date: createdAt.toISOString()
        })
        
      } catch {
        // Log file doesn't exist or is invalid
      }
    }

    // Calculate final metrics
    metrics.total_chapters = chapterFiles.length
    metrics.total_cost = totalCost
    metrics.average_cost_per_chapter = chapterFiles.length > 0 ? totalCost / chapterFiles.length : 0
    metrics.monthly_cost = monthlyCost
    metrics.average_quality = qualityCount > 0 ? totalQuality / qualityCount : 0
    
    // Sort trends by chapter number
    metrics.quality_trend = qualityTrend.sort((a, b) => a.chapter - b.chapter)
    metrics.cost_trend = costTrend.sort((a, b) => a.chapter - b.chapter)
    
    // Budget calculation (assuming $10/month budget)
    const monthlyBudget = 10.0
    metrics.budget_remaining = Math.max(0, ((monthlyBudget - monthlyCost) / monthlyBudget) * 100)

    return NextResponse.json(metrics)

  } catch (error: any) {
    console.error('Failed to get metrics:', error)
    return NextResponse.json(
      { error: `Failed to get metrics: ${error.message}` },
      { status: 500 }
    )
  }
} 