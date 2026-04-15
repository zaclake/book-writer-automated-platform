import { NextRequest, NextResponse } from 'next/server'

const SESSION_COOKIE = 'user_session'
const USER_ID_COOKIE = 'user_id'
const USER_EMAIL_COOKIE = 'user_email'
const USER_NAME_COOKIE = 'user_name'

export async function POST(request: NextRequest) {
  try {
    const backendBaseUrl =
      process.env.NEXT_PUBLIC_BACKEND_URL?.trim() || process.env.BACKEND_URL?.trim()
    const sessionToken = request.cookies.get(SESSION_COOKIE)?.value

    if (backendBaseUrl && sessionToken) {
      try {
        await fetch(`${backendBaseUrl}/v2/auth/logout`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${sessionToken}`,
          },
        })
      } catch (error) {
        console.warn('[auth/logout] Failed to revoke session:', error)
      }
    }

    const res = NextResponse.json({ success: true })
    res.cookies.set(SESSION_COOKIE, '', { maxAge: 0, path: '/' })
    res.cookies.set(USER_ID_COOKIE, '', { maxAge: 0, path: '/' })
    res.cookies.set(USER_EMAIL_COOKIE, '', { maxAge: 0, path: '/' })
    res.cookies.set(USER_NAME_COOKIE, '', { maxAge: 0, path: '/' })
    return res
  } catch (error) {
    console.error('[auth/logout] Error:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
