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

const buildTargetUrl = (backendBaseUrl: string, chapterParam: string, request: NextRequest) => {
  const url = new URL(request.url)
  const projectId = url.searchParams.get('project_id')
  const isNumericChapter = /^[0-9]+$/.test(chapterParam)
  const queryParams = new URLSearchParams(url.searchParams)
  queryParams.delete('project_id')
  const queryString = queryParams.toString()

  if (isNumericChapter && projectId) {
    return `${backendBaseUrl}/v2/chapters/project/${projectId}/chapter/${chapterParam}${queryString ? `?${queryString}` : ''}`
  }

  return `${backendBaseUrl}/v2/chapters/${chapterParam}${queryString ? `?${queryString}` : ''}`
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

    const targetUrl = buildTargetUrl(backendBaseUrl, params.chapter, request)

    const backendResponse = await fetch(targetUrl, {
      method: 'GET',
      headers: buildHeaders(request),
      cache: 'no-store',
      signal: AbortSignal.timeout(45000),
    })

    const parsed = await safeParseBackendJson(backendResponse)
    if (!parsed.ok) {
      return NextResponse.json(
        {
          error: 'Invalid response from backend',
          status: backendResponse.status,
          body_preview: parsed.rawText.slice(0, 2000),
        },
        { status: 502 }
      )
    }
    return NextResponse.json(parsed.data, { status: backendResponse.status })
  } catch (error) {
    console.error('[chapters] GET error:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: { chapter: string } }
) {
  try {
    const backendBaseUrl = getBackendUrl()
    if (!backendBaseUrl) {
      return NextResponse.json({ error: 'Backend URL not configured' }, { status: 500 })
    }

    const body = await request.text()
    const targetUrl = buildTargetUrl(backendBaseUrl, params.chapter, request)

    const backendResponse = await fetch(targetUrl, {
      method: 'PUT',
      headers: buildHeaders(request),
      body,
      cache: 'no-store',
      signal: AbortSignal.timeout(45000),
    })

    const parsed = await safeParseBackendJson(backendResponse)
    if (!parsed.ok) {
      return NextResponse.json(
        {
          error: 'Invalid response from backend',
          status: backendResponse.status,
          body_preview: parsed.rawText.slice(0, 2000),
        },
        { status: 502 }
      )
    }
    return NextResponse.json(parsed.data, { status: backendResponse.status })
  } catch (error) {
    console.error('[chapters] PUT error:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}

export async function DELETE() {
  return NextResponse.json({ error: 'Chapter deletion not supported' }, { status: 501 })
}