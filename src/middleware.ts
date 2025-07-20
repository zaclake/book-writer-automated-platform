import { clerkMiddleware } from '@clerk/nextjs/server'

export default clerkMiddleware(async (auth, req) => {
  const { pathname } = req.nextUrl
  
  // Public API routes that don't need authentication
  const publicApiRoutes = [
    '/api/debug/',
    '/api/config-check',
    '/api/status',
    '/api/cron/',
    '/api/health'
  ]
  
  // Skip auth for public API routes
  if (pathname.startsWith('/api/') && 
      publicApiRoutes.some(route => pathname.startsWith(route))) {
    return
  }
  
  // Allow public access to auth pages and home
  const publicPaths = ['/sign-in', '/sign-up', '/']
  const isPublicPath = publicPaths.some(path => 
    pathname.startsWith(path)
  )
  
  // For non-API routes, protect only specific paths
  const protectedPaths = ['/dashboard', '/profile', '/settings', '/create', '/project']
  const isProtectedPath = protectedPaths.some(path => 
    pathname.startsWith(path)
  )
  
  // Protect API routes that need authentication (most of them)
  const isProtectedApi = pathname.startsWith('/api/') && 
    !publicApiRoutes.some(route => pathname.startsWith(route))
  
  if ((isProtectedPath && !isPublicPath) || isProtectedApi) {
    await auth.protect()
  }
})

export const config = {
  matcher: [
    // Skip Next.js internals and all static files, unless found in search params
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    // Include all routes including API routes
    '/(api|trpc)(.*)',
  ],
} 