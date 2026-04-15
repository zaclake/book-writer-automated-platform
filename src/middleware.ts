import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

const AUTH_COOKIE_NAME = 'site_access'

// Routes that don't require password.
// Important: '/' must be checked as an exact match; every pathname starts with '/'.
const PUBLIC_EXACT_ROUTES = ['/' as const, '/sign-in' as const, '/sign-up' as const]
const PUBLIC_PREFIX_ROUTES = [
  '/_next/' as const, // Next.js internals
  '/api/' as const, // API routes (own auth handled separately)
  '/favicon' as const,
  '/logo' as const,
]

export default function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl

  // Allow public routes
  if (
    PUBLIC_EXACT_ROUTES.some((route) => pathname === route) ||
    PUBLIC_PREFIX_ROUTES.some((prefix) => pathname.startsWith(prefix))
  ) {
    return NextResponse.next()
  }

  // Allow static files
  if (pathname.match(/\.(ico|png|jpg|jpeg|svg|gif|webp|css|js|woff|woff2|ttf)$/)) {
    return NextResponse.next()
  }

  // Check for password cookie
  const authCookie = req.cookies.get(AUTH_COOKIE_NAME)
  const isAuthenticated = authCookie?.value === 'granted'

  if (!isAuthenticated) {
    // Redirect to password gate
    return NextResponse.redirect(new URL('/', req.url))
  }

  return NextResponse.next()
}

export const config = {
  matcher: [
    // Skip Next.js internals and all static files
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
  ],
}
