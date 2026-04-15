import { NextRequest, NextResponse } from 'next/server'
import { getBackendUrl, getSessionAuthHeader } from '@/lib/api-utils'

export async function GET(
  request: NextRequest,
  { params }: { params: { chapterId: string } }
) {
  try {
    const authHeader = await getSessionAuthHeader(request)
    if (!authHeader) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const backendUrl = getBackendUrl()
    const url = `${backendUrl}/v2/chapters/${encodeURIComponent(params.chapterId)}/versions`

    const response = await fetch(url, {
      method: 'GET',
      headers: {
        Authorization: authHeader,
      },
      cache: 'no-store',
    })

    const text = await response.text()
    return new NextResponse(text, {
      status: response.status,
      headers: {
        'Content-Type': response.headers.get('content-type') || 'application/json',
      },
    })
  } catch (error) {
    return NextResponse.json(
      { error: 'Failed to fetch chapter versions' },
      { status: 500 }
    )
  }
}

export async function POST(
  request: NextRequest,
  { params }: { params: { chapterId: string } }
) {
  try {
    const authHeader = await getSessionAuthHeader(request)
    if (!authHeader) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const body = await request.json().catch(() => ({}))
    const backendUrl = getBackendUrl()
    const url = `${backendUrl}/v2/chapters/${encodeURIComponent(params.chapterId)}/versions`

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        Authorization: authHeader,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    })

    const text = await response.text()
    return new NextResponse(text, {
      status: response.status,
      headers: {
        'Content-Type': response.headers.get('content-type') || 'application/json',
      },
    })
  } catch (error) {
    return NextResponse.json(
      { error: 'Failed to add chapter version' },
      { status: 500 }
    )
  }
}

