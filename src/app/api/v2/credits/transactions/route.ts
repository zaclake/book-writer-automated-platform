import { NextRequest, NextResponse } from 'next/server'
import { auth } from '@clerk/nextjs/server'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function GET(request: NextRequest) {
  try {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      return NextResponse.json(
        { error: 'Backend URL not configured (NEXT_PUBLIC_BACKEND_URL missing)' },
        { status: 500 }
      )
    }

    const { getToken } = await auth()
    const token = await getToken()
    if (!token) {
      return NextResponse.json({ error: 'Authentication required' }, { status: 401 })
    }

    const url = new URL(request.url)
    const params = url.searchParams.toString()
    const targetUrl = `${backendBaseUrl}/v2/credits/transactions${params ? `?${params}` : ''}`

    const backendResponse = await fetch(targetUrl, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
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
    console.error('[v2/credits/transactions] Error:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}


