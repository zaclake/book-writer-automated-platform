import { NextRequest, NextResponse } from 'next/server'
import { execSync } from 'child_process'
import path from 'path'

export async function POST(request: NextRequest) {
  try {
    const { config, projectPath, userId } = await request.json()

    // Validate required parameters
    if (!config) {
      return NextResponse.json(
        { error: 'Configuration is required' },
        { status: 400 }
      )
    }

    // Set default values
    const autoCompletionConfig = {
      target_word_count: config.targetWordCount || 80000,
      target_chapter_count: config.targetChapterCount || 20,
      minimum_quality_score: config.minimumQualityScore || 80.0,
      max_retries_per_chapter: config.maxRetriesPerChapter || 3,
      auto_pause_on_failure: config.autoPauseOnFailure ?? true,
      context_improvement_enabled: config.contextImprovementEnabled ?? true,
      quality_gates_enabled: config.qualityGatesEnabled ?? true,
      user_review_required: config.userReviewRequired ?? false
    }

    const projectRoot = process.cwd()
    const targetProjectPath = projectPath || projectRoot

    // Start the background job processor if not already running
    const initCommand = `cd "${projectRoot}" && python -c "
import asyncio
import sys
sys.path.append('system')
from background_job_processor import get_job_processor, AutoCompletionConfig, JobPriority

async def start_job():
    processor = get_job_processor()
    
    # Start processor if not running
    if not processor.running:
        await processor.start()
    
    # Create config
    config = AutoCompletionConfig(
        target_word_count=${autoCompletionConfig.target_word_count},
        target_chapter_count=${autoCompletionConfig.target_chapter_count},
        minimum_quality_score=${autoCompletionConfig.minimum_quality_score},
        max_retries_per_chapter=${autoCompletionConfig.max_retries_per_chapter},
        auto_pause_on_failure=${autoCompletionConfig.auto_pause_on_failure ? 'True' : 'False'},
        context_improvement_enabled=${autoCompletionConfig.context_improvement_enabled ? 'True' : 'False'},
        quality_gates_enabled=${autoCompletionConfig.quality_gates_enabled ? 'True' : 'False'},
        user_review_required=${autoCompletionConfig.user_review_required ? 'True' : 'False'}
    )
    
    # Submit job
    job_id = processor.submit_auto_complete_book_job(
        '${targetProjectPath}',
        config,
        user_id='${userId || 'anonymous'}',
        priority=JobPriority.NORMAL
    )
    
    print(f'JOB_ID:{job_id}')
    return job_id

asyncio.run(start_job())
"`

    const output = execSync(initCommand, { 
      encoding: 'utf8', 
      timeout: 30000,
      cwd: projectRoot
    })

    // Extract job ID from output
    const jobIdMatch = output.match(/JOB_ID:([a-f0-9-]+)/)
    if (!jobIdMatch) {
      throw new Error('Failed to extract job ID from processor output')
    }

    const jobId = jobIdMatch[1]

    return NextResponse.json({
      success: true,
      jobId: jobId,
      message: 'Auto-completion job started successfully',
      config: autoCompletionConfig,
      projectPath: targetProjectPath,
      timestamp: new Date().toISOString()
    })

  } catch (error: any) {
    console.error('Auto-completion start error:', error)
    
    // Handle specific error types
    if (error.message.includes('timeout')) {
      return NextResponse.json(
        { error: 'Job startup timed out. The system may be busy.' },
        { status: 503 }
      )
    }
    
    return NextResponse.json(
      { error: `Failed to start auto-completion: ${error.message}` },
      { status: 500 }
    )
  }
} 