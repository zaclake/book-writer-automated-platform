import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function POST(
  request: NextRequest,
  { params }: { params: { jobId: string } }
) {
  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      return NextResponse.json(
        { error: 'Backend URL not configured (NEXT_PUBLIC_BACKEND_URL missing)' },
        { status: 500 }
      )
    }

    const body = await request.text()
    const targetUrl = `${backendBaseUrl}/auto-complete/${encodeURIComponent(params.jobId)}/control`
    const sessionToken = request.cookies.get('user_session')?.value
    const authHeader = request.headers.get('authorization') || undefined
    const res = await fetch(targetUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(authHeader ? { Authorization: authHeader } : {}),
        ...(!authHeader && sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {})
      },
      body,
      cache: 'no-store',
    })

    const contentType = res.headers.get('content-type') || ''
    if (!res.ok) {
      if (contentType.includes('application/json')) {
        const data = await res.json()
        return NextResponse.json(data, { status: res.status })
      }
      const text = await res.text()
      return NextResponse.json({ error: text }, { status: res.status })
    }

    const data = await res.json()
    return NextResponse.json(data, { status: 200 })
  } catch (err) {
    return NextResponse.json(
      { error: 'Failed to proxy control request', details: err instanceof Error ? err.message : String(err) },
      { status: 500 }
    )
  }
}
