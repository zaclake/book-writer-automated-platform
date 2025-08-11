import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(request: NextRequest, { params }: { params: { projectId: string } }) {
  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      return NextResponse.json({ error: 'Backend URL not configured' }, { status: 500 })
    }

    const targetUrl = `${backendBaseUrl}/v2/library/book/${encodeURIComponent(params.projectId)}/reader`

    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    const { getToken } = await auth()
    const token = await getToken()
    if (!token) return NextResponse.json({ error: 'Authentication required' }, { status: 401 })
    headers['Authorization'] = `Bearer ${token}`

    const res = await fetch(targetUrl, { headers })
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch (err) {
    return NextResponse.json({ error: 'Reader payload request failed', details: err instanceof Error ? err.message : String(err) }, { status: 500 })
  }
}


