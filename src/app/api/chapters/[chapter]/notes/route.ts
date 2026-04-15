import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

const getBackendUrl = () => process.env.NEXT_PUBLIC_BACKEND_URL?.trim()

const buildHeaders = (request: NextRequest) => {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const authHeader = request.headers.get('authorization')
  if (authHeader) headers['Authorization'] = authHeader
  return headers
}

const safeParseBackendJson = async (backendResponse: Response) => {
  const rawText = await backendResponse.text().catch(() => '')
  if (!rawText) return { ok: true as const, data: null, rawText: '' }
  try {
    return { ok: true as const, data: JSON.parse(rawText), rawText }
  } catch {
    return { ok: false as const, data: null, rawText }
  }
}

export async function GET(
  request: NextRequest,
  { params }: { params: { chapter: string } }
) {
  try {
    const backendBaseUrl = getBackendUrl()
    if (!backendBaseUrl) {
      return NextResponse.json({ error: 'Backend URL not configured' }, { status: 500 })
    }

    const url = new URL(request.url)
    const query = url.searchParams.toString()
    const targetUrl = `${backendBaseUrl}/v2/chapters/${params.chapter}/notes${query ? `?${query}` : ''}`

    const backendResponse = await fetch(targetUrl, {
      method: 'GET',
      headers: buildHeaders(request),
      cache: 'no-store',
      signal: AbortSignal.timeout(45000),
    })

    const parsed = await safeParseBackendJson(backendResponse)
    if (!parsed.ok) {
      return NextResponse.json(
        { error: 'Invalid response from backend', status: backendResponse.status, body_preview: parsed.rawText.slice(0, 2000) },
        { status: 502 }
      )
    }
    return NextResponse.json(parsed.data, { status: backendResponse.status })
  } catch (error) {
    console.error(`[chapters/notes] GET error:`, error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}

export async function POST(
  request: NextRequest,
  { params }: { params: { chapter: string } }
) {
  try {
    const backendBaseUrl = getBackendUrl()
    if (!backendBaseUrl) {
      return NextResponse.json({ error: 'Backend URL not configured' }, { status: 500 })
    }

    const body = await request.text()
    const targetUrl = `${backendBaseUrl}/v2/chapters/${params.chapter}/notes`

    const backendResponse = await fetch(targetUrl, {
      method: 'POST',
      headers: buildHeaders(request),
      body,
      cache: 'no-store',
      signal: AbortSignal.timeout(45000),
    })

    const parsed = await safeParseBackendJson(backendResponse)
    if (!parsed.ok) {
      return NextResponse.json(
        { error: 'Invalid response from backend', status: backendResponse.status, body_preview: parsed.rawText.slice(0, 2000) },
        { status: 502 }
      )
    }
    return NextResponse.json(parsed.data, { status: backendResponse.status })
  } catch (error) {
    console.error(`[chapters/notes] POST error:`, error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}