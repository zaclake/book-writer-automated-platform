import { NextRequest } from 'next/server'
import { auth } from '@clerk/nextjs/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

// Note: Next.js will stream the backend SSE through this route
export async function GET(
  request: NextRequest,
  { params }: { params: { jobId: string } }
) {
  const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
  if (!backendBaseUrl) {
    return new Response('Backend URL not configured', { status: 500 })
  }

  const { getToken } = await auth()
  const token = await getToken()
  if (!token) return new Response('Authentication required', { status: 401 })

  const targetUrl = `${backendBaseUrl}/auto-complete/${encodeURIComponent(params.jobId)}/progress?token=${encodeURIComponent(token)}`

  const backendResponse = await fetch(targetUrl, {
    headers: {
      Accept: 'text/event-stream'
    }
  })

  // Pass through status and headers for SSE
  const headers = new Headers(backendResponse.headers)
  // Ensure CORS is not required since this is same-origin to client
  headers.set('Access-Control-Allow-Origin', '*')

  return new Response(backendResponse.body, {
    status: backendResponse.status,
    headers
  })
}


