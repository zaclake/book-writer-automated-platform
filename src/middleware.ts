import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'
import { NextResponse } from 'next/server'

const isProtectedRoute = createRouteMatcher([
  '/dashboard(.*)',
  '/api/auto-complete(.*)',
  '/api/book-bible(.*)',
  '/api/chapters(.*)',
  '/api/quality(.*)',
])

export default clerkMiddleware(async (auth, req) => {
  // Protect the specified routes
  if (isProtectedRoute(req)) {
    // Prefer Clerk's built-in protection helper for pages
    if (!req.nextUrl.pathname.startsWith('/api/')) {
      // Will redirect unauthenticated users to /sign-in
      await auth.protect()
    } else {
      // For API routes, return 401 instead of Clerk's default 404
      const { userId } = await auth()
      if (!userId) {
        return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
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