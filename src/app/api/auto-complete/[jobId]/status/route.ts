import { NextRequest, NextResponse } from 'next/server'
import { execSync } from 'child_process'

interface RouteParams {
  params: {
    jobId: string
  }
}

export async function GET(request: NextRequest, { params }: RouteParams) {
  try {
    const { jobId } = params

    if (!jobId) {
      return NextResponse.json(
        { error: 'Job ID is required' },
        { status: 400 }
      )
    }

    const projectRoot = process.cwd()

    // Get job status from background processor
    const statusCommand = `cd "${projectRoot}" && python -c "
import asyncio
import sys
import json
sys.path.append('system')
from background_job_processor import get_job_processor

def get_job_status():
    processor = get_job_processor()
    
    # Get job status
    job = processor.get_job_status('${jobId}')
    if not job:
        print('JOB_NOT_FOUND')
        return None
    
    # Convert job to dict for JSON serialization
    job_dict = {
        'job_id': job.job_id,
        'job_type': job.job_type,
        'status': job.status.value,
        'priority': job.priority.value,
        'created_at': job.created_at.isoformat(),
        'started_at': job.started_at.isoformat() if job.started_at else None,
        'completed_at': job.completed_at.isoformat() if job.completed_at else None,
        'config': job.config,
        'error': job.error,
        'result': job.result,
        'retries': job.retries,
        'max_retries': job.max_retries,
        'user_id': job.user_id,
        'project_path': job.project_path,
        'progress': {
            'job_id': job.progress.job_id,
            'current_step': job.progress.current_step,
            'total_steps': job.progress.total_steps,
            'completed_steps': job.progress.completed_steps,
            'progress_percentage': job.progress.progress_percentage,
            'estimated_time_remaining': job.progress.estimated_time_remaining,
            'current_chapter': job.progress.current_chapter,
            'chapters_completed': job.progress.chapters_completed,
            'total_chapters': job.progress.total_chapters,
            'last_update': job.progress.last_update,
            'detailed_status': job.progress.detailed_status
        }
    }
    
    print(f'JOB_DATA:{json.dumps(job_dict)}')
    return job_dict

get_job_status()
"`

    const output = execSync(statusCommand, { 
      encoding: 'utf8', 
      timeout: 10000,
      cwd: projectRoot
    })

    // Check if job was not found
    if (output.includes('JOB_NOT_FOUND')) {
      return NextResponse.json(
        { error: 'Job not found' },
        { status: 404 }
      )
    }

    // Extract job data from output
    const jobDataMatch = output.match(/JOB_DATA:(.+)/)
    if (!jobDataMatch) {
      throw new Error('Failed to extract job data from processor output')
    }

    const jobData = JSON.parse(jobDataMatch[1])

    // Calculate additional metrics
    const currentTime = new Date()
    let elapsedTime = null
    let estimatedTotalTime = null

    if (jobData.started_at) {
      const startTime = new Date(jobData.started_at)
      elapsedTime = Math.floor((currentTime.getTime() - startTime.getTime()) / 1000) // seconds
    }

    if (jobData.progress.progress_percentage > 0 && elapsedTime) {
      estimatedTotalTime = Math.floor((elapsedTime / jobData.progress.progress_percentage) * 100)
    }

    // Enhanced response with calculated metrics
    const response = {
      success: true,
      job: jobData,
      metrics: {
        elapsed_time_seconds: elapsedTime,
        estimated_total_time_seconds: estimatedTotalTime,
        completion_rate: jobData.progress.chapters_completed > 0 && elapsedTime 
          ? Math.round(jobData.progress.chapters_completed / (elapsedTime / 3600) * 100) / 100 // chapters per hour
          : null,
        quality_trend: 'stable', // Could be calculated from detailed_status
        last_activity: jobData.progress.last_update
      },
      timestamp: new Date().toISOString()
    }

    return NextResponse.json(response)

  } catch (error: any) {
    console.error('Auto-completion status error:', error)
    
    if (error.message.includes('timeout')) {
      return NextResponse.json(
        { error: 'Status check timed out. The system may be busy.' },
        { status: 503 }
      )
    }
    
    return NextResponse.json(
      { error: `Failed to get job status: ${error.message}` },
      { status: 500 }
    )
  }
} 