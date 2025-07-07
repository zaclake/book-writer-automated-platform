import { NextRequest, NextResponse } from 'next/server'
import { execSync, spawn } from 'child_process'

interface RouteParams {
  params: {
    jobId: string
  }
}

export async function GET(request: NextRequest, { params }: RouteParams) {
  const { jobId } = params

  if (!jobId) {
    return NextResponse.json(
      { error: 'Job ID is required' },
      { status: 400 }
    )
  }

  // Create SSE stream
  const stream = new ReadableStream({
    start(controller) {
      const projectRoot = process.cwd()
      
      // Function to send SSE data
      const sendEvent = (data: any, event = 'progress') => {
        const message = `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
        controller.enqueue(new TextEncoder().encode(message))
      }

      // Send initial connection event
      sendEvent({ 
        type: 'connected', 
        jobId: jobId, 
        timestamp: new Date().toISOString() 
      }, 'connection')

      // Function to get job status
      const getJobStatus = () => {
        try {
          const statusCommand = `cd "${projectRoot}" && python -c "
import sys
import json
sys.path.append('system')
from background_job_processor import get_job_processor

def get_job_status():
    processor = get_job_processor()
    job = processor.get_job_status('${jobId}')
    
    if not job:
        print('JOB_NOT_FOUND')
        return None
    
    # Create progress update
    progress_data = {
        'job_id': job.job_id,
        'status': job.status.value,
        'progress_percentage': job.progress.progress_percentage,
        'current_step': job.progress.current_step,
        'current_chapter': job.progress.current_chapter,
        'chapters_completed': job.progress.chapters_completed,
        'total_chapters': job.progress.total_chapters,
        'estimated_time_remaining': job.progress.estimated_time_remaining,
        'last_update': job.progress.last_update,
        'error': job.error,
        'result': job.result if job.status.value == 'completed' else None
    }
    
    print(f'PROGRESS_DATA:{json.dumps(progress_data)}')
    return progress_data

get_job_status()
"`

          const output = execSync(statusCommand, { 
            encoding: 'utf8', 
            timeout: 5000,
            cwd: projectRoot
          })

          if (output.includes('JOB_NOT_FOUND')) {
            sendEvent({ 
              type: 'error', 
              message: 'Job not found',
              timestamp: new Date().toISOString()
            }, 'error')
            return null
          }

          const progressMatch = output.match(/PROGRESS_DATA:(.+)/)
          if (progressMatch) {
            const progressData = JSON.parse(progressMatch[1])
            progressData.timestamp = new Date().toISOString()
            return progressData
          }

        } catch (error) {
          console.error('Error getting job status:', error)
          sendEvent({ 
            type: 'error', 
            message: 'Failed to get job status',
            error: error.message,
            timestamp: new Date().toISOString()
          }, 'error')
          return null
        }
        return null
      }

      // Send initial status
      const initialStatus = getJobStatus()
      if (initialStatus) {
        sendEvent(initialStatus, 'progress')
      }

      // Set up polling for progress updates
      const pollInterval = setInterval(() => {
        const status = getJobStatus()
        if (status) {
          sendEvent(status, 'progress')
          
          // Stop polling if job is completed, failed, or cancelled
          if (['completed', 'failed', 'cancelled'].includes(status.status)) {
            sendEvent({ 
              type: 'final', 
              status: status.status,
              message: `Job ${status.status}`,
              timestamp: new Date().toISOString()
            }, 'completion')
            
            clearInterval(pollInterval)
            controller.close()
          }
        }
      }, 2000) // Poll every 2 seconds

      // Clean up on client disconnect
      request.signal.addEventListener('abort', () => {
        clearInterval(pollInterval)
        controller.close()
      })

      // Send keep-alive every 30 seconds to prevent connection timeout
      const keepAliveInterval = setInterval(() => {
        sendEvent({ 
          type: 'keep-alive', 
          timestamp: new Date().toISOString() 
        }, 'keep-alive')
      }, 30000)

      // Clean up keep-alive on close
      request.signal.addEventListener('abort', () => {
        clearInterval(keepAliveInterval)
      })
    }
  })

  // Return SSE response
  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Headers': 'Cache-Control'
    }
  })
} 