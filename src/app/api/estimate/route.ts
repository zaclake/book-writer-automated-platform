import { NextRequest, NextResponse } from 'next/server'
import { execSync } from 'child_process'

export async function POST(request: NextRequest) {
  try {
    const { chapter, words, stage } = await request.json()

    if (!chapter || !words) {
      return NextResponse.json(
        { error: 'Chapter number and word count are required' },
        { status: 400 }
      )
    }

    // Validate inputs
    if (chapter < 1 || chapter > 200) {
      return NextResponse.json(
        { error: 'Chapter number must be between 1 and 200' },
        { status: 400 }
      )
    }

    if (words < 500 || words > 10000) {
      return NextResponse.json(
        { error: 'Word count must be between 500 and 10000' },
        { status: 400 }
      )
    }

    const validStages = ['spike', 'complete', '5-stage']
    if (stage && !validStages.includes(stage)) {
      return NextResponse.json(
        { error: 'Invalid stage. Must be one of: spike, complete, 5-stage' },
        { status: 400 }
      )
    }

    // Get the project root path
    const projectRoot = process.cwd()
    
    // Execute cost estimation
    const command = `cd "${projectRoot}" && python system/llm_orchestrator.py --estimate --chapter ${chapter} --words ${words} --stage ${stage || 'complete'}`
    
    console.log(`Executing estimate: ${command}`)

    const output = execSync(command, {
      encoding: 'utf8',
      timeout: 30000, // 30 seconds timeout for estimates
      env: {
        ...process.env,
        OPENAI_API_KEY: process.env.OPENAI_API_KEY
      }
    })

    // Parse the output to extract results
    const lines = output.trim().split('\n')
    const lastLine = lines[lines.length - 1]
    
    let result
    try {
      result = JSON.parse(lastLine)
    } catch (e) {
      // If JSON parsing fails, return basic estimate based on word count
      const baseTokens = Math.round(words * 1.3) // Rough estimate: 1.3 tokens per word
      const stageMult = stage === '5-stage' ? 5 : stage === 'spike' ? 1 : 2
      const totalTokens = baseTokens * stageMult
      
      result = {
        estimated_total_tokens: totalTokens,
        estimated_total_cost: totalTokens * 0.015 / 1000, // $0.015 per 1K tokens
        stage: stage || 'complete'
      }
    }

    return NextResponse.json({
      success: true,
      chapter: chapter,
      words: words,
      stage: stage || 'complete',
      ...result
    })

  } catch (error: any) {
    console.error('Estimation error:', error)
    
    // Handle timeout errors
    if (error.message?.includes('timeout')) {
      return NextResponse.json(
        { error: 'Estimation timed out' },
        { status: 408 }
      )
    }

    // Handle Python execution errors
    if (error.stderr) {
      console.error('Python stderr:', error.stderr)
      return NextResponse.json(
        { error: `Estimation failed: ${error.stderr}` },
        { status: 500 }
      )
    }

    return NextResponse.json(
      { error: `Estimation failed: ${error.message}` },
      { status: 500 }
    )
  }
} 