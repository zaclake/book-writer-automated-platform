import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function POST(request: NextRequest) {
  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      return NextResponse.json({ error: 'Backend URL not configured' }, { status: 500 })
    }

    const body = await request.text()
    const authHeader = request.headers.get('authorization')
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (authHeader) headers['Authorization'] = authHeader

    const targetUrl = `${backendBaseUrl}/prewriting/refine`
    const backendResponse = await fetch(targetUrl, {
      method: 'POST',
      headers,
      body,
      cache: 'no-store'
    })

    const data = await backendResponse.json().catch(() => ({}))
    return NextResponse.json(data, { status: backendResponse.status })
  } catch (error) {
    console.error('[prewriting/refine] Error:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
