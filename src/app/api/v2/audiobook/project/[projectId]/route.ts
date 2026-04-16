import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function POST(
  request: NextRequest,
  { params }: { params: { projectId: string } }
) {
  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      return NextResponse.json({ error: 'Backend URL not configured' }, { status: 500 })
    }

    const targetUrl = `${backendBaseUrl}/v2/audiobook/project/${params.projectId}`
    const body = await request.json()

    const authHeader = request.headers.get('Authorization')
    const sessionToken = request.cookies.get('user_session')?.value
    const resolvedAuthHeader = authHeader || (sessionToken ? `Bearer ${sessionToken}` : null)
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (resolvedAuthHeader) {
      headers.Authorization = resolvedAuthHeader
    }

    let response: Response | null = null
    let attempt = 0
    const maxAttempts = 3
    while (attempt < maxAttempts) {
      attempt++
      try {
        response = await fetch(targetUrl, {
          method: 'POST',
          headers,
          body: JSON.stringify(body),
          cache: 'no-store',
        })
        break
      } catch (err) {
        if (attempt >= maxAttempts) throw err
        await new Promise(r => setTimeout(r, 300 * attempt))
      }
    }

    if (!response!.ok) {
      const errorText = await response!.text()
      return NextResponse.json(
        { error: 'Backend request failed', details: errorText },
        { status: response!.status }
      )
    }

    return NextResponse.json(await response!.json())
  } catch (error) {
    return NextResponse.json(
      { error: 'Audiobook generation request failed', details: error instanceof Error ? error.message : String(error) },
      { status: 500 }
    )
  }
}
