import { NextRequest } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

function resolveAuth(request: NextRequest): string | null {
  const authHeader = request.headers.get('Authorization')
  if (authHeader) return authHeader
  const session = request.cookies.get('user_session')?.value
  return session ? `Bearer ${session}` : null
}

export async function GET(request: NextRequest, { params }: { params: { projectId: string } }) {
  const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
  if (!backendBaseUrl) {
    return new Response('Backend URL not configured', { status: 500 })
  }

  const targetUrl = `${backendBaseUrl}/v2/library/book/${encodeURIComponent(params.projectId)}/cover`

  const headers: Record<string, string> = {}
  const auth = resolveAuth(request)
  if (auth) headers['Authorization'] = auth

  const res = await fetch(targetUrl, { headers })
  if (!res.ok) {
    const text = await res.text()
    return new Response(text, { status: res.status })
  }

  const contentType = res.headers.get('Content-Type') || 'image/jpeg'
  const contentLength = res.headers.get('Content-Length')
  const respHeaders: Record<string, string> = {
    'Content-Type': contentType,
    'Content-Disposition': res.headers.get('Content-Disposition') || `attachment; filename="cover-${params.projectId}.jpg"`,
    'Cache-Control': 'private, max-age=3600',
  }
  if (contentLength) respHeaders['Content-Length'] = contentLength
  return new Response(res.body, { status: 200, headers: respHeaders })
}
