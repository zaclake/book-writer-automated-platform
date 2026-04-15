import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

function resolveAuth(request: NextRequest): string | null {
  const authHeader = request.headers.get('Authorization')
  if (authHeader) return authHeader
  const session = request.cookies.get('user_session')?.value
  return session ? `Bearer ${session}` : null
}

export async function GET(request: NextRequest, { params }: { params: { projectId: string } }) {
  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      return NextResponse.json({ error: 'Backend URL not configured' }, { status: 500 })
    }

    const targetUrl = `${backendBaseUrl}/v2/library/book/${encodeURIComponent(params.projectId)}/reader`

    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    const auth = resolveAuth(request)
    if (auth) headers['Authorization'] = auth

    const res = await fetch(targetUrl, { headers, cache: 'no-store' })
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch (err) {
    return NextResponse.json({ error: 'Reader payload request failed', details: err instanceof Error ? err.message : String(err) }, { status: 500 })
  }
}
