import { NextRequest, NextResponse } from 'next/server'

const SESSION_COOKIE = 'user_session'

export async function GET(request: NextRequest) {
  try {
    const backendBaseUrl =
      process.env.NEXT_PUBLIC_BACKEND_URL?.trim() || process.env.BACKEND_URL?.trim()
    const sessionToken = request.cookies.get(SESSION_COOKIE)?.value

    if (!backendBaseUrl || !sessionToken) {
      return NextResponse.json({ user: null }, { status: 200 })
    }

    const response = await fetch(`${backendBaseUrl}/v2/auth/me`, {
      headers: {
        Authorization: `Bearer ${sessionToken}`,
        'Content-Type': 'application/json',
      },
    })

    const data = await response.json()
    if (!response.ok) {
      return NextResponse.json({ user: null }, { status: 200 })
    }

    return NextResponse.json(data)
  } catch (error) {
    console.error('[auth/me] Error:', error)
    return NextResponse.json({ user: null }, { status: 200 })
  }
}
