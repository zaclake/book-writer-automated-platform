import { NextRequest, NextResponse } from 'next/server'
import { execSync } from 'child_process'

interface RouteParams {
  params: {
    jobId: string
  }
}

export async function POST(request: NextRequest, { params }: RouteParams) {
  try {
    const { jobId } = params
    const { action } = await request.json()

    if (!jobId) {
      return NextResponse.json(
        { error: 'Job ID is required' },
        { status: 400 }
      )
    }

    if (!action || !['pause', 'resume', 'cancel'].includes(action)) {
      return NextResponse.json(
        { error: 'Valid action is required (pause, resume, cancel)' },
        { status: 400 }
      )
    }

    const projectRoot = process.cwd()

    // Execute job control action
    const controlCommand = `cd "${projectRoot}" && python -c "
import asyncio
import sys
import json
sys.path.append('system')
from background_job_processor import get_job_processor

def control_job():
    processor = get_job_processor()
    
    # Check if job exists
    job = processor.get_job_status('${jobId}')
    if not job:
        print('JOB_NOT_FOUND')
        return False
    
    # Execute the requested action
    action = '${action}'
    success = False
    
    if action == 'pause':
        success = processor.pause_job('${jobId}')
    elif action == 'resume':
        success = processor.resume_job('${jobId}')
    elif action == 'cancel':
        success = processor.cancel_job('${jobId}')
    
    # Get updated job status
    updated_job = processor.get_job_status('${jobId}')
    result = {
        'success': success,
        'action': action,
        'previous_status': job.status.value,
        'new_status': updated_job.status.value if updated_job else 'unknown'
    }
    
    print(f'CONTROL_RESULT:{json.dumps(result)}')
    return success

control_job()
"`

    const output = execSync(controlCommand, { 
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

    // Extract control result from output
    const resultMatch = output.match(/CONTROL_RESULT:(.+)/)
    if (!resultMatch) {
      throw new Error('Failed to extract control result from processor output')
    }

    const controlResult = JSON.parse(resultMatch[1])

    if (!controlResult.success) {
      return NextResponse.json(
        { 
          error: `Failed to ${action} job. Job may not be in a valid state for this action.`,
          currentStatus: controlResult.new_status,
          details: `Cannot ${action} job in ${controlResult.previous_status} status`
        },
        { status: 400 }
      )
    }

    // Success response
    const actionMessages = {
      pause: 'paused',
      resume: 'resumed', 
      cancel: 'cancelled'
    }

    return NextResponse.json({
      success: true,
      jobId: jobId,
      action: action,
      message: `Job ${actionMessages[action as keyof typeof actionMessages]} successfully`,
      previousStatus: controlResult.previous_status,
      newStatus: controlResult.new_status,
      timestamp: new Date().toISOString()
    })

  } catch (error: any) {
    console.error('Auto-completion control error:', error)
    
    if (error.message.includes('timeout')) {
      return NextResponse.json(
        { error: 'Control action timed out. The system may be busy.' },
        { status: 503 }
      )
    }
    
    return NextResponse.json(
      { error: `Failed to control job: ${error.message}` },
      { status: 500 }
    )
  }
} 