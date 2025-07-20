import { NextRequest } from 'next/server'
import { auth } from '@clerk/nextjs/server'

export async function GET(
  request: NextRequest,
  { params }: { params: { jobId: string } }
) {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 30000) // 30 second timeout
  
  try {
    const { userId, getToken } = await auth()
    
    if (!userId) {
      return new Response('Unauthorized', { status: 401 })
    }

    const { jobId } = params

    if (!jobId || !/^[a-zA-Z0-9-_]+$/.test(jobId)) {
      return new Response('Invalid Job ID format', { status: 400 })
    }

    // Get backend URL
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      return new Response('Backend URL not configured', { status: 500 })
    }

    // Create SSE stream by proxying to backend with timeout
    const backendUrl = `${backendBaseUrl}/auto-complete/${jobId}/progress`
    
    console.log(`[auto-complete/${jobId}/progress] Proxying to:`, backendUrl)

    const response = await fetch(backendUrl, {
      method: 'GET',
      signal: controller.signal,
      headers: {
        'Accept': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Authorization': `Bearer ${await getToken()}`
      }
    })

    clearTimeout(timeoutId)

    if (!response.ok) {
      const errorText = await response.text()
      console.error(`[auto-complete/${jobId}/progress] Backend error:`, errorText)
      return new Response(errorText, { status: response.status })
    }

    // Handle cleanup when client disconnects
    request.signal?.addEventListener('abort', () => {
      console.log(`[auto-complete/${jobId}/progress] Client disconnected`)
      controller.abort()
    })

    // Return the SSE stream from backend with proper cleanup
    return new Response(response.body, {
      status: 200,
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET',
        'Access-Control-Allow-Headers': 'Cache-Control',
        'X-Accel-Buffering': 'no' // Disable nginx buffering for SSE
      }
    })

  } catch (error) {
    clearTimeout(timeoutId)
    
    if (error instanceof Error && error.name === 'AbortError') {
      console.log(`[auto-complete/progress] Request aborted`)
      return new Response('Request timeout or cancelled', { status: 408 })
    }
    
    console.error(`[auto-complete/progress] Error:`, error)
    return new Response(
      `Failed to stream progress: ${error instanceof Error ? error.message : 'Unknown error'}`,
      { status: 500 }
    )
  }
} 