import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function POST(
  request: NextRequest,
  { params }: { params: { chapterId: string } }
) {
  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      return NextResponse.json({ error: 'Backend URL not configured' }, { status: 500 })
    }

    const body = await request.text()
    const authHeader = request.headers.get('authorization')
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (authHeader) headers['Authorization'] = authHeader

    const targetUrl = `${backendBaseUrl}/v2/chapters/${params.chapterId}/ripple-analysis`
    const backendResponse = await fetch(targetUrl, {
      method: 'POST',
      headers,
      body,
      cache: 'no-store',
      signal: AbortSignal.timeout(120000),
    })

    const rawText = await backendResponse.text().catch(() => '')
    if (!rawText) {
      return NextResponse.json(null, { status: backendResponse.status })
    }
    try {
      const data = JSON.parse(rawText)
      return NextResponse.json(data, { status: backendResponse.status })
    } catch {
      return NextResponse.json(
        { error: 'Invalid response from backend', body_preview: rawText.slice(0, 2000) },
        { status: 502 }
      )
    }
  } catch (error) {
    console.error('[v2/chapters/ripple-analysis] Error:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
