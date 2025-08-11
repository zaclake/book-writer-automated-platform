import { NextRequest } from 'next/server'
import { auth } from '@clerk/nextjs/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(request: NextRequest, { params }: { params: { projectId: string } }) {
  const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
  if (!backendBaseUrl) {
    return new Response('Backend URL not configured', { status: 500 })
  }

  const headers: Record<string, string> = {}
  const { getToken } = await auth()
  const token = await getToken()
  if (!token) return new Response('Authentication required', { status: 401 })
  headers['Authorization'] = `Bearer ${token}`

  const targetUrl = `${backendBaseUrl}/v2/library/book/${encodeURIComponent(params.projectId)}/pdf`
  const res = await fetch(targetUrl, { headers })
  if (!res.ok) {
    const text = await res.text()
    return new Response(text, { status: res.status })
  }

  const contentType = res.headers.get('Content-Type') || 'application/pdf'
  const contentDisposition = res.headers.get('Content-Disposition') || `inline; filename=book-${params.projectId}.pdf`
  return new Response(res.body, {
    status: 200,
    headers: {
      'Content-Type': contentType,
      'Content-Disposition': contentDisposition,
    },
  })
}


