import { NextRequest, NextResponse } from 'next/server'
import { execSync } from 'child_process'
import { statSync } from 'fs'
import path from 'path'

export async function POST(request: NextRequest) {
  try {
    const { chapterNumber, chapterFile } = await request.json()

    if (!chapterNumber) {
      return NextResponse.json(
        { error: 'Chapter number is required' },
        { status: 400 }
      )
    }

    const projectRoot = process.cwd()
    
    // Determine chapter file path
    let filePath: string
    if (chapterFile) {
      filePath = path.join(projectRoot, chapterFile)
    } else {
      filePath = path.join(projectRoot, 'chapters', `chapter-${chapterNumber.toString().padStart(2, '0')}.md`)
    }

    // Check if chapter file exists
    try {
      statSync(filePath)
    } catch (error) {
      return NextResponse.json(
        { error: `Chapter file not found: ${filePath}` },
        { status: 404 }
      )
    }

    // Run quality assessment using the Python system
    const results: any = {}
    
    try {
      // Run brutal assessment scorer
      const brutalCommand = `cd "${projectRoot}" && python system/brutal-assessment-scorer.py assess --chapter-file "${filePath}"`
      const brutalOutput = execSync(brutalCommand, { encoding: 'utf8', timeout: 60000 })
      results.brutalAssessment = parseBrutalAssessmentOutput(brutalOutput)
    } catch (error) {
      console.warn('Brutal assessment failed:', error)
      results.brutalAssessment = { error: 'Assessment failed', score: 0 }
    }

    try {
      // Run reader engagement scorer
      const engagementCommand = `cd "${projectRoot}" && python system/reader-engagement-scorer.py assess --chapter-file "${filePath}"`
      const engagementOutput = execSync(engagementCommand, { encoding: 'utf8', timeout: 60000 })
      results.engagementScore = parseEngagementOutput(engagementOutput)
    } catch (error) {
      console.warn('Engagement scoring failed:', error)
      results.engagementScore = { error: 'Scoring failed', score: 0 }
    }

    try {
      // Run quality gate validator
      const qualityCommand = `cd "${projectRoot}" && python system/quality-gate-validator.py validate --chapter-file "${filePath}"`
      const qualityOutput = execSync(qualityCommand, { encoding: 'utf8', timeout: 60000 })
      results.qualityGates = parseQualityGateOutput(qualityOutput)
    } catch (error) {
      console.warn('Quality gate validation failed:', error)
      results.qualityGates = { error: 'Validation failed', passed: 0, total: 0 }
    }

    // Calculate overall score
    const overallScore = calculateOverallScore(results)

    return NextResponse.json({
      success: true,
      chapterNumber: chapterNumber,
      filePath: filePath,
      assessment: results,
      overallScore: overallScore,
      timestamp: new Date().toISOString()
    })

  } catch (error: any) {
    console.error('Quality assessment error:', error)
    return NextResponse.json(
      { error: `Quality assessment failed: ${error.message}` },
      { status: 500 }
    )
  }
}

function parseBrutalAssessmentOutput(output: string): any {
  try {
    // Look for JSON output or score patterns
    const lines = output.split('\n')
    let score = 0
    let details = {}
    
    for (const line of lines) {
      if (line.includes('Overall Score:') || line.includes('Total Score:')) {
        const match = line.match(/(\d+\.?\d*)/);
        if (match) {
          score = parseFloat(match[1])
        }
      }
      
      // Try to parse JSON if present
      if (line.trim().startsWith('{')) {
        try {
          details = JSON.parse(line)
          if (details.hasOwnProperty('score')) {
            score = (details as any).score
          }
        } catch {}
      }
    }
    
    return { score, details, rawOutput: output }
  } catch (error) {
    return { score: 0, error: 'Failed to parse output', rawOutput: output }
  }
}

function parseEngagementOutput(output: string): any {
  try {
    const lines = output.split('\n')
    let score = 0
    let details = {}
    
    for (const line of lines) {
      if (line.includes('Engagement Score:')) {
        const match = line.match(/(\d+\.?\d*)/);
        if (match) {
          score = parseFloat(match[1])
        }
      }
      
      if (line.trim().startsWith('{')) {
        try {
          details = JSON.parse(line)
          if (details.hasOwnProperty('engagement_score')) {
            score = (details as any).engagement_score
          }
        } catch {}
      }
    }
    
    return { score, details, rawOutput: output }
  } catch (error) {
    return { score: 0, error: 'Failed to parse output', rawOutput: output }
  }
}

function parseQualityGateOutput(output: string): any {
  try {
    const lines = output.split('\n')
    let passed = 0
    let total = 0
    let details = {}
    
    for (const line of lines) {
      if (line.includes('Passed:') && line.includes('Total:')) {
        const passedMatch = line.match(/Passed:\s*(\d+)/);
        const totalMatch = line.match(/Total:\s*(\d+)/);
        if (passedMatch) passed = parseInt(passedMatch[1])
        if (totalMatch) total = parseInt(totalMatch[1])
      }
      
      if (line.trim().startsWith('{')) {
        try {
          details = JSON.parse(line)
          if (details.hasOwnProperty('passed') && details.hasOwnProperty('total')) {
            passed = (details as any).passed
            total = (details as any).total
          }
        } catch {}
      }
    }
    
    return { passed, total, passRate: total > 0 ? passed / total : 0, details, rawOutput: output }
  } catch (error) {
    return { passed: 0, total: 0, passRate: 0, error: 'Failed to parse output', rawOutput: output }
  }
}

function calculateOverallScore(results: any): number {
  try {
    let totalScore = 0
    let components = 0
    
    if (results.brutalAssessment && results.brutalAssessment.score > 0) {
      totalScore += results.brutalAssessment.score
      components++
    }
    
    if (results.engagementScore && results.engagementScore.score > 0) {
      totalScore += results.engagementScore.score
      components++
    }
    
    if (results.qualityGates && results.qualityGates.passRate > 0) {
      totalScore += results.qualityGates.passRate * 10 // Convert to 0-10 scale
      components++
    }
    
    return components > 0 ? totalScore / components : 0
  } catch (error) {
    return 0
  }
} 