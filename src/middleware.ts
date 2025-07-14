import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'

// Create matcher for protected routes (only protect the main pages, not API routes)
const isProtectedRoute = createRouteMatcher([
  '/((?!api).*)', // Protect all routes except API routes
])

export default clerkMiddleware((auth, req) => {
  // Let API routes handle their own authentication
  if (req.nextUrl.pathname.startsWith('/api/')) {
    return
  }
  
  // For non-API routes, apply Clerk auth logic
  if (isProtectedRoute(req)) {
    // Let Clerk handle authentication for pages
    // The main page will handle showing sign-in UI when needed
  }
})

export const config = {
  matcher: [
    // Skip Next.js internals and all static files, unless found in search params
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    // Always run for API routes
    '/(api|trpc)(.*)',
  ],
} 