import { NextRequest, NextResponse } from 'next/server'

const SESSION_COOKIE = 'user_session'
const USER_ID_COOKIE = 'user_id'
const USER_EMAIL_COOKIE = 'user_email'
const USER_NAME_COOKIE = 'user_name'

export async function POST(request: NextRequest) {
  try {
    const backendBaseUrl =
      process.env.NEXT_PUBLIC_BACKEND_URL?.trim() || process.env.BACKEND_URL?.trim()
    if (!backendBaseUrl) {
      return NextResponse.json({ error: 'Backend URL not configured' }, { status: 500 })
    }

    const payload = await request.json()

    const response = await fetch(`${backendBaseUrl}/v2/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })

    const data = await response.json()

    if (!response.ok) {
      return NextResponse.json(data, { status: response.status })
    }

    const res = NextResponse.json(data)
    const maxAge = 60 * 60 * 24 * 30

    res.cookies.set(SESSION_COOKIE, data.session_token, {
      maxAge,
      path: '/',
      sameSite: 'lax',
      httpOnly: false,
    })
    res.cookies.set(USER_ID_COOKIE, data.user?.id || '', {
      maxAge,
      path: '/',
      sameSite: 'lax',
      httpOnly: false,
    })
    res.cookies.set(USER_EMAIL_COOKIE, data.user?.email || '', {
      maxAge,
      path: '/',
      sameSite: 'lax',
      httpOnly: false,
    })
    res.cookies.set(USER_NAME_COOKIE, data.user?.name || '', {
      maxAge,
      path: '/',
      sameSite: 'lax',
      httpOnly: false,
    })

    return res
  } catch (error) {
    console.error('[auth/register] Error:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
