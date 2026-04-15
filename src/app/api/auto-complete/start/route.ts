import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function POST(request: NextRequest) {
  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      console.error('[auto-complete/start] Backend URL not configured')
      return NextResponse.json(
        { error: 'Backend URL not configured (NEXT_PUBLIC_BACKEND_URL missing)' },
        { status: 500 }
      )
    }

    const body = await request.text()
    const targetUrl = `${backendBaseUrl}/auto-complete/start`
    const sessionToken = request.cookies.get('user_session')?.value
    const authHeader = request.headers.get('authorization') || undefined
    const backendResponse = await fetch(targetUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(authHeader ? { Authorization: authHeader } : {}),
        ...(!authHeader && sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {})
      },
      body,
      cache: 'no-store',
    })

    const contentType = backendResponse.headers.get('content-type') || ''
    if (!backendResponse.ok) {
      if (contentType.includes('application/json')) {
        const data = await backendResponse.json()
        return NextResponse.json(data, { status: backendResponse.status })
      }
      const text = await backendResponse.text()
      return NextResponse.json({ error: text }, { status: backendResponse.status })
    }

    const data = await backendResponse.json()
    return NextResponse.json(data, { status: 200 })
  } catch (error) {
    console.error('[auto-complete/start] Error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}
