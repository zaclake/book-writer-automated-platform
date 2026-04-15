'use client'

import React, { useMemo, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import Image from 'next/image'
import Link from 'next/link'
import { UI_STRINGS } from '@/lib/strings'
import { CreditBalance } from '@/components/CreditBalance'
import { useUserJobs } from '@/hooks/useFirestore'
import { useAuthToken } from '@/lib/auth'

const TopNav: React.FC = () => {
  const { user, isLoaded, isSignedIn } = useAuthToken()
  const pathname = usePathname()
  const router = useRouter()
  const isProjectView = pathname.startsWith('/project/')
  const projectIdFromPath = isProjectView ? pathname.split('/')[2] : null
  const creditsEnabled = process.env.NEXT_PUBLIC_CREDITS_ENABLED === 'true'
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const { jobs } = useUserJobs(10, { enabled: isLoaded && isSignedIn })

  const activeAutoCompleteJob = useMemo(() => {
    const list = (jobs || []) as any[]
    if (!list.length) return null

    const isTerminal = (s: any) => ['completed', 'failed', 'cancelled'].includes(String(s || '').toLowerCase())
    const isActive = (s: any) => !isTerminal(s)

    const jobTime = (j: any) => {
      const parsed = Date.parse(String(j?.started_at || j?.created_at || 0))
      return Number.isFinite(parsed) ? parsed : 0
    }

    const pickLatestForProject = (projectId: string | null) => {
      if (!projectId) return null
      const filtered = list
        .filter((j: any) =>
          String(j?.project_id || '') === String(projectId) &&
          String(j?.job_type || '') === 'auto_complete_book' &&
          isActive(j?.status)
        )
        .sort((a: any, b: any) => jobTime(b) - jobTime(a))
      return filtered[0] || null
    }

    // Prefer the currently viewed project; otherwise show any active auto-complete job.
    return (
      pickLatestForProject(projectIdFromPath) ||
      list
        .filter((j: any) => String(j?.job_type || '') === 'auto_complete_book' && isActive(j?.status))
        .sort((a: any, b: any) => jobTime(b) - jobTime(a))[0] ||
      null
    )
  }, [jobs, projectIdFromPath])

  const activeAutoCompleteProjectTitle = useMemo(() => {
    if (!activeAutoCompleteJob) return null
    const pid = String((activeAutoCompleteJob as any)?.project_id || '')
    return `Auto-Complete`
  }, [activeAutoCompleteJob])

  const activeAutoCompletePct = useMemo(() => {
    if (!activeAutoCompleteJob) return 0
    const pct = (activeAutoCompleteJob as any)?.progress?.percentage ?? (activeAutoCompleteJob as any)?.progress?.progress_percentage ?? 0
    const n = Number(pct)
    if (!Number.isFinite(n)) return 0
    return Math.max(0, Math.min(100, n))
  }, [activeAutoCompleteJob])

  const activeAutoCompleteStatusLabel = useMemo(() => {
    const s = String((activeAutoCompleteJob as any)?.status || '').toLowerCase()
    if (s === 'paused') return 'Paused'
    return 'Running'
  }, [activeAutoCompleteJob])

  const activeAutoCompleteProjectId = useMemo(() => {
    if (!activeAutoCompleteJob) return ''
    return String((activeAutoCompleteJob as any)?.project_id || '').trim()
  }, [activeAutoCompleteJob])


  const navigationItems = [
    {
      label: UI_STRINGS.navigation.dashboard,
      href: '/dashboard',
      active: pathname === '/dashboard'
    },
    {
      label: 'Profile',
      href: '/profile',
      active: pathname.startsWith('/profile')
    },
    {
      label: UI_STRINGS.navigation.library,
      href: '/library',
      active: pathname.startsWith('/library'),
      disabled: false
    },
    {
      label: UI_STRINGS.navigation.community,
      href: '/community',
      active: pathname.startsWith('/community'),
      disabled: true, // Placeholder for Contact/FAQ/Blog
      tooltip: 'Coming soon'
    },
    {
      label: UI_STRINGS.navigation.forum,
      href: '/forum',
      active: pathname.startsWith('/forum'),
      disabled: true, // Coming soon
      tooltip: 'Coming soon'
    }
  ]

  const navigate = (href: string) => {
    router.push(href)
  }

  const toggleMobileMenu = () => {
    setIsMobileMenuOpen(!isMobileMenuOpen)
  }

  const userInitial =
    user?.firstName?.charAt(0) ||
    user?.emailAddresses?.[0]?.emailAddress?.charAt(0) ||
    'U'

  const handleSignOut = async () => {
    try {
      await fetch('/api/auth/logout', { method: 'POST' })
    } catch {
      // Clear cookies client-side as fallback
      document.cookie.split(';').forEach(c => {
        const name = c.split('=')[0].trim()
        if (['user_session', 'user_id', 'user_email', 'user_name'].includes(name)) {
          document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`
        }
      })
    }
    navigate('/sign-in')
  }

  return (
    <>
      <header
        className="bg-white border-b border-gray-200 sticky top-0 z-40 overflow-x-clip"
        style={{ paddingTop: 'env(safe-area-inset-top)' }}
      >
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Logo and Project Info */}
            <div className="flex items-center space-x-3 sm:space-x-6">
              {/* Brand Logo */}
              <div
                className="flex items-center space-x-3"
              >
                <Link
                  href="/dashboard"
                  className="flex items-center space-x-3 cursor-pointer"
                  aria-label="Go to dashboard"
                >
                  <Image
                    src="/logo.png"
                    alt="WriterBloom"
                    width={40}
                    height={40}
                    className="w-8 h-8 sm:w-10 sm:h-10 object-contain"
                    priority
                  />
                  <span className="hidden sm:inline font-semibold text-gray-900 text-base sm:text-lg">WriterBloom</span>
                </Link>
              </div>

            </div>

            {/* Auto-complete running indicator (project-wide) */}
            {activeAutoCompleteJob && (
              <div className="hidden md:flex items-center gap-3 min-w-0">
                {activeAutoCompleteProjectId ? (
                <Link
                  href={`/project/${encodeURIComponent(activeAutoCompleteProjectId)}/auto-complete`}
                  className="flex items-center gap-3 rounded-xl border border-brand-lavender/30 bg-brand-off-white px-3 py-2 hover:bg-white transition-colors max-w-[28rem]"
                  aria-label="View auto-complete progress"
                  title="View auto-complete progress"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-sm" aria-hidden="true">⚡</span>
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-gray-900 truncate">
                        {activeAutoCompleteProjectTitle || 'Auto-Complete'}
                      </div>
                      <div className="text-[11px] text-gray-600">
                        {activeAutoCompleteStatusLabel} • {Math.round(activeAutoCompletePct)}%
                      </div>
                    </div>
                  </div>
                  <div className="w-28">
                    <div className="h-2 w-full bg-white border border-gray-200 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-brand-lavender via-brand-leaf to-brand-blush-orange transition-all duration-700"
                        style={{ width: `${activeAutoCompletePct}%` }}
                      />
                    </div>
                  </div>
                  <div className="text-xs font-semibold text-brand-soft-purple whitespace-nowrap">
                    View
                  </div>
                </Link>
                ) : null}
              </div>
            )}

            {/* Desktop Navigation Links */}
            <nav className="hidden md:flex items-center space-x-8">
              {navigationItems.map((item) => (
                <div key={item.label} className="relative group">
                  {item.disabled ? (
                    <button
                      disabled
                      className="relative px-3 py-2 text-sm font-medium transition-all duration-200 text-gray-400 cursor-not-allowed"
                      aria-label={`${item.label} - ${item.tooltip || 'Disabled'}`}
                    >
                      {item.label}
                    </button>
                  ) : (
                    <Link
                      href={item.href}
                      className={`relative px-3 py-2 text-sm font-medium transition-all duration-200 ${
                        item.active ? 'text-brand-soft-purple' : 'text-gray-600 hover:text-brand-soft-purple'
                      }`}
                      aria-label={item.label}
                    >
                      {item.label}

                      {item.active && (
                        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-brand-soft-purple rounded-full" />
                      )}

                      {!item.active && (
                        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-brand-soft-purple rounded-full opacity-0 group-hover:opacity-50 transition-opacity duration-200" />
                      )}
                    </Link>
                  )}

                  {/* Tooltip for disabled items */}
                  {item.disabled && item.tooltip && (
                    <div className="absolute top-full mt-2 left-1/2 transform -translate-x-1/2 bg-gray-900 text-white text-xs py-1 px-2 rounded opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none whitespace-nowrap">
                      {item.tooltip}
                    </div>
                  )}
                </div>
              ))}
            </nav>

            {/* Right side - Profile & Mobile Menu */}
            <div className="flex items-center space-x-2 sm:space-x-4">
              {/* Auto-complete running indicator (mobile) */}
              {activeAutoCompleteJob && (
                activeAutoCompleteProjectId ? (
                <Link
                  href={`/project/${encodeURIComponent(activeAutoCompleteProjectId)}/auto-complete`}
                  className="md:hidden inline-flex items-center gap-2 rounded-full border border-brand-lavender/30 bg-brand-off-white px-3 py-1.5 text-xs font-semibold text-gray-800 hover:bg-white transition-colors max-w-[55vw]"
                  aria-label="View auto-complete progress"
                  title="View auto-complete progress"
                >
                  <span aria-hidden="true">⚡</span>
                  <span className="truncate">{Math.round(activeAutoCompletePct)}%</span>
                </Link>
                ) : null
              )}
              {/* Mobile menu button */}
              <button
                onClick={toggleMobileMenu}
                className="md:hidden p-2 rounded-lg text-gray-600 hover:text-brand-soft-purple hover:bg-gray-100 transition-colors"
                aria-label="Toggle navigation menu"
                aria-expanded={isMobileMenuOpen}
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  {isMobileMenuOpen ? (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  ) : (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                  )}
                </svg>
              </button>

              {creditsEnabled && isLoaded && isSignedIn && (
                <CreditBalance variant="compact" className="hidden sm:flex" />
              )}

              {isLoaded && !isSignedIn ? (
                <div className="hidden sm:flex items-center space-x-3">
                  <a
                    href="/sign-in"
                    className="inline-flex items-center text-xs font-medium text-gray-600 hover:text-brand-soft-purple transition-colors"
                  >
                    Sign in
                  </a>
                  <a
                    href="/sign-up"
                    className="inline-flex items-center text-xs font-medium text-white bg-brand-soft-purple px-3 py-1.5 rounded-full hover:bg-opacity-90 transition-colors"
                  >
                    Create account
                  </a>
                </div>
              ) : isLoaded ? (
                <button
                  onClick={handleSignOut}
                  className="hidden sm:inline-flex items-center text-xs font-medium text-gray-600 hover:text-brand-soft-purple transition-colors"
                >
                  Sign out
                </button>
              ) : null}
              <div className="w-7 h-7 sm:w-8 sm:h-8 rounded-full bg-brand-soft-purple flex items-center justify-center text-white text-xs sm:text-sm font-medium">
                {userInitial}
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Mobile Navigation Drawer */}
      {isMobileMenuOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-black bg-opacity-50 z-40 md:hidden"
            onClick={() => setIsMobileMenuOpen(false)}
            aria-hidden="true"
          />

          {/* Drawer */}
          <div
            className="fixed left-0 right-0 bg-white border-b border-gray-200 shadow-lg z-50 md:hidden overflow-y-auto"
            style={{
              top: 'calc(4rem + env(safe-area-inset-top))',
              maxHeight: 'calc(100vh - (4rem + env(safe-area-inset-top)))',
            }}
            role="navigation"
            aria-label="Mobile navigation"
          >
            <div className="px-4 py-6 space-y-4">
              {/* Credits on mobile */}
              {creditsEnabled && isLoaded && isSignedIn && (
                <div className="pb-4 border-b border-gray-200">
                  <CreditBalance variant="full" />
                </div>
              )}

              {/* Navigation items */}
              {navigationItems.map((item) => (
                item.disabled ? (
                  <button
                    key={item.label}
                    disabled
                    className="w-full text-left px-4 py-3 rounded-lg transition-colors text-gray-400 cursor-not-allowed"
                    aria-label={`${item.label} - ${item.tooltip || 'Disabled'}`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{item.label}</span>
                      {item.tooltip && (
                        <span className="text-xs text-gray-400">{item.tooltip}</span>
                      )}
                    </div>
                  </button>
                ) : (
                  <Link
                    key={item.label}
                    href={item.href}
                    className={`block w-full text-left px-4 py-3 rounded-lg transition-colors ${
                      item.active ? 'bg-brand-soft-purple text-white' : 'text-gray-700 hover:bg-brand-sand hover:text-brand-soft-purple'
                    }`}
                    aria-label={item.label}
                    onClick={() => setIsMobileMenuOpen(false)}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{item.label}</span>
                    </div>
                  </Link>
                )
              ))}

              {/* Auth buttons on mobile */}
              {isLoaded && !isSignedIn ? (
                <div className="pt-2 space-y-2">
                  <a
                    href="/sign-in"
                    className="block w-full text-left px-4 py-3 rounded-lg text-gray-700 hover:bg-brand-sand hover:text-brand-soft-purple transition-colors"
                  >
                    Sign in
                  </a>
                  <a
                    href="/sign-up"
                    className="block w-full text-left px-4 py-3 rounded-lg bg-brand-soft-purple text-white hover:bg-opacity-90 transition-colors"
                  >
                    Create account
                  </a>
                </div>
              ) : isLoaded ? (
                <button
                  onClick={() => {
                    setIsMobileMenuOpen(false)
                    handleSignOut()
                  }}
                  className="w-full text-left px-4 py-3 rounded-lg text-gray-700 hover:bg-brand-sand hover:text-brand-soft-purple transition-colors"
                >
                  Sign out
                </button>
              ) : null}
            </div>
          </div>
        </>
      )}
    </>
  )
}

export default TopNav
