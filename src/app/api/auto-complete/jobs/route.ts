import { NextRequest, NextResponse } from 'next/server'
import { execSync } from 'child_process'

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url)
    
    const userId = searchParams.get('userId')
    const status = searchParams.get('status')
    const limit = parseInt(searchParams.get('limit') || '20')
    const offset = parseInt(searchParams.get('offset') || '0')

    const projectRoot = process.cwd()

    // Get jobs list from background processor
    const listCommand = `cd "${projectRoot}" && python -c "
import asyncio
import sys
import json
sys.path.append('system')
from background_job_processor import get_job_processor, JobStatus

def list_jobs():
    processor = get_job_processor()
    
    # Get status filter if provided
    status_filter = None
    if '${status}':
        try:
            status_filter = JobStatus('${status}')
        except ValueError:
            pass
    
    # Get jobs list
    jobs = processor.list_jobs(
        user_id='${userId || ''}' if '${userId}' else None,
        status_filter=status_filter
    )
    
    # Convert jobs to dict format for JSON serialization
    jobs_data = []
    for job in jobs:
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
            'retries': job.retries,
            'max_retries': job.max_retries,
            'user_id': job.user_id,
            'project_path': job.project_path,
            'progress': {
                'current_step': job.progress.current_step,
                'progress_percentage': job.progress.progress_percentage,
                'estimated_time_remaining': job.progress.estimated_time_remaining,
                'current_chapter': job.progress.current_chapter,
                'chapters_completed': job.progress.chapters_completed,
                'total_chapters': job.progress.total_chapters,
                'last_update': job.progress.last_update
            }
        }
        jobs_data.append(job_dict)
    
    # Apply pagination
    total_jobs = len(jobs_data)
    start_idx = ${offset}
    end_idx = start_idx + ${limit}
    paginated_jobs = jobs_data[start_idx:end_idx]
    
    result = {
        'jobs': paginated_jobs,
        'pagination': {
            'total': total_jobs,
            'limit': ${limit},
            'offset': ${offset},
            'has_more': end_idx < total_jobs
        }
    }
    
    print(f'JOBS_DATA:{json.dumps(result)}')
    return result

list_jobs()
"`

    const output = execSync(listCommand, { 
      encoding: 'utf8', 
      timeout: 15000,
      cwd: projectRoot
    })

    // Extract jobs data from output
    const jobsDataMatch = output.match(/JOBS_DATA:(.+)/)
    if (!jobsDataMatch) {
      throw new Error('Failed to extract jobs data from processor output')
    }

    const jobsResult = JSON.parse(jobsDataMatch[1])

    // Add summary statistics
    const statusCounts = {
      pending: 0,
      queued: 0,
      running: 0,
      paused: 0,
      completed: 0,
      failed: 0,
      cancelled: 0
    }

    jobsResult.jobs.forEach((job: any) => {
      if (statusCounts.hasOwnProperty(job.status)) {
        statusCounts[job.status as keyof typeof statusCounts]++
      }
    })

    // Calculate system metrics
    const systemMetrics = {
      active_jobs: statusCounts.running + statusCounts.queued,
      total_jobs: jobsResult.pagination.total,
      success_rate: jobsResult.pagination.total > 0 
        ? Math.round((statusCounts.completed / jobsResult.pagination.total) * 100)
        : 0,
      last_activity: jobsResult.jobs.length > 0 
        ? jobsResult.jobs[0].progress.last_update
        : null
    }

    const response = {
      success: true,
      jobs: jobsResult.jobs,
      pagination: jobsResult.pagination,
      summary: {
        status_counts: statusCounts,
        system_metrics: systemMetrics
      },
      filters: {
        user_id: userId,
        status: status,
        limit: limit,
        offset: offset
      },
      timestamp: new Date().toISOString()
    }

    return NextResponse.json(response)

  } catch (error: any) {
    console.error('Auto-completion jobs list error:', error)
    
    if (error.message.includes('timeout')) {
      return NextResponse.json(
        { error: 'Jobs list request timed out. The system may be busy.' },
        { status: 503 }
      )
    }
    
    return NextResponse.json(
      { error: `Failed to get jobs list: ${error.message}` },
      { status: 500 }
    )
  }
} 