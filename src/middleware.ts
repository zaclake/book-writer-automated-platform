import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'
import { NextResponse } from 'next/server'

const isProtectedRoute = createRouteMatcher([
  '/dashboard(.*)',
  '/api/auto-complete(.*)',
  '/api/book-bible(.*)',
  '/api/chapters(.*)',
  '/api/quality(.*)',
  '/api/test-protected(.*)',
])

const isDebugRoute = createRouteMatcher([
  '/api/debug(.*)',
  '/api/auth-debug(.*)',
  '/api/config-check(.*)',
  '/api/auth-test(.*)',
  '/api/client-auth-test(.*)',
])

export default clerkMiddleware(async (auth, req) => {
  // Allow debug routes to bypass authentication
  if (isDebugRoute(req)) {
    return NextResponse.next()
  }

  // Protect the specified routes
  if (isProtectedRoute(req)) {
    try {
      const { userId } = await auth()
      if (!userId) {
        // For API routes, return 401. For pages, redirect to sign-in
        if (req.nextUrl.pathname.startsWith('/api/')) {
          return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
        } else {
          // For pages, let Clerk handle the redirect
          await auth.protect()
        }
      }
    } catch (error) {
      console.error('Auth middleware error:', error)
      if (req.nextUrl.pathname.startsWith('/api/')) {
        return NextResponse.json({ error: 'Authentication failed' }, { status: 401 })
      } else {
        await auth.protect()
      }
    }
  }

  return NextResponse.next()
})

export const config = {
  matcher: [
    // Skip Next.js internals and all static files, unless found in search params
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    // Always run for API routes
    '/(api|trpc)(.*)',
  ],
} 