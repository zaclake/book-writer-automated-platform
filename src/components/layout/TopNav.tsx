'use client'

import React, { useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { UserButton, useUser } from '@clerk/nextjs'
import Image from 'next/image'
import { UI_STRINGS } from '@/lib/strings'
import { CreditBalance } from '@/components/CreditBalance'

interface TopNavProps {
  currentProject?: {
    id: string
    title: string
    status: string
  }
}

const TopNav: React.FC<TopNavProps> = ({ currentProject }) => {
  const { user } = useUser()
  const router = useRouter()
  const pathname = usePathname()
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)

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
      disabled: true, // Coming soon
      tooltip: 'Coming soon'
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

  const handleNavClick = (href: string, disabled?: boolean) => {
    if (disabled) return
    setIsMobileMenuOpen(false) // Close mobile menu
    router.push(href)
  }

  const toggleMobileMenu = () => {
    setIsMobileMenuOpen(!isMobileMenuOpen)
  }

  return (
    <>
      <header className="bg-white border-b border-gray-200 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Logo and Project Info */}
            <div className="flex items-center space-x-6">
              {/* Brand Logo */}
              <div 
                className="flex items-center space-x-3 cursor-pointer"
                onClick={() => router.push(user ? '/dashboard' : '/')}
              >
                <Image
                  src="/logo.png"
                  alt="WriterBloom"
                  width={40}
                  height={40}
                  className="w-10 h-10 object-contain"
                  priority
                />
                <span className="font-semibold text-gray-900 text-lg">WriterBloom</span>
              </div>

              {/* Project Context (if in project) */}
              {currentProject && (
                <>
                  <div className="h-6 w-px bg-gray-300 hidden sm:block" />
                  <div className="hidden sm:flex items-center space-x-2">
                    <span className="text-sm text-gray-600">Journey:</span>
                    <span className="font-medium text-gray-900">{currentProject.title}</span>
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                      currentProject.status === 'active' ? 'bg-brand-leaf bg-opacity-20 text-green-800' :
                      currentProject.status === 'completed' ? 'bg-brand-soft-purple bg-opacity-20 text-purple-800' :
                      currentProject.status === 'paused' ? 'bg-yellow-100 text-yellow-800' :
                      'bg-gray-100 text-gray-800'
                    }`}>
                      {currentProject.status}
                    </span>
                  </div>
                </>
              )}
            </div>

            {/* Desktop Navigation Links */}
            {user && (
              <nav className="hidden md:flex items-center space-x-8">
                {navigationItems.map((item) => (
                  <div key={item.label} className="relative group">
                    <button
                      onClick={() => handleNavClick(item.href, item.disabled)}
                      disabled={item.disabled}
                      className={`relative px-3 py-2 text-sm font-medium transition-all duration-200 ${
                        item.active
                          ? 'text-brand-soft-purple'
                          : item.disabled
                          ? 'text-gray-400 cursor-not-allowed'
                          : 'text-gray-600 hover:text-brand-soft-purple'
                      }`}
                      aria-label={item.disabled ? `${item.label} - ${item.tooltip}` : item.label}
                    >
                      {item.label}
                      
                      {/* Active indicator */}
                      {item.active && (
                        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-brand-soft-purple rounded-full" />
                      )}
                      
                      {/* Hover indicator */}
                      {!item.active && !item.disabled && (
                        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-brand-soft-purple rounded-full opacity-0 group-hover:opacity-50 transition-opacity duration-200" />
                      )}
                    </button>
                    
                    {/* Tooltip for disabled items */}
                    {item.disabled && item.tooltip && (
                      <div className="absolute top-full mt-2 left-1/2 transform -translate-x-1/2 bg-gray-900 text-white text-xs py-1 px-2 rounded opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none whitespace-nowrap">
                        {item.tooltip}
                      </div>
                    )}
                  </div>
                ))}
              </nav>
            )}

            {/* Right side - Profile & Mobile Menu */}
            <div className="flex items-center space-x-4">
              {/* Mobile menu button */}
              {user && (
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
              )}

              {user && (
                <>
                  <CreditBalance variant="compact" className="hidden sm:flex" />
                  <UserButton afterSignOutUrl="/" />
                </>
              )}
              
              {!user && (
                <div className="flex items-center space-x-3">
                  <button
                    onClick={() => router.push('/sign-in')}
                    className="text-sm font-medium text-gray-600 hover:text-brand-soft-purple transition-colors"
                  >
                    Sign In
                  </button>
                  <button
                    onClick={() => router.push('/sign-up')}
                    className="bg-brand-soft-purple text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-opacity-90 transition-all"
                  >
                    {UI_STRINGS.actions.getStarted}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Mobile Navigation Drawer */}
      {isMobileMenuOpen && user && (
        <>
          {/* Backdrop */}
          <div 
            className="fixed inset-0 bg-black bg-opacity-50 z-40 md:hidden"
            onClick={() => setIsMobileMenuOpen(false)}
            aria-hidden="true"
          />
          
          {/* Drawer */}
          <div 
            className="fixed top-16 left-0 right-0 bg-white border-b border-gray-200 shadow-lg z-50 md:hidden"
            role="navigation"
            aria-label="Mobile navigation"
          >
            <div className="px-4 py-6 space-y-4">
              {/* Credits on mobile */}
              <div className="pb-4 border-b border-gray-200">
                <CreditBalance variant="full" />
              </div>

              {/* Project info on mobile */}
              {currentProject && (
                <div className="pb-4 border-b border-gray-200">
                  <div className="flex items-center space-x-2">
                    <span className="text-sm text-gray-600">Current Journey:</span>
                    <span className="font-medium text-gray-900">{currentProject.title}</span>
                  </div>
                  <span className={`inline-block mt-2 px-2 py-1 rounded-full text-xs font-medium ${
                    currentProject.status === 'active' ? 'bg-brand-leaf bg-opacity-20 text-green-800' :
                    currentProject.status === 'completed' ? 'bg-brand-soft-purple bg-opacity-20 text-purple-800' :
                    currentProject.status === 'paused' ? 'bg-yellow-100 text-yellow-800' :
                    'bg-gray-100 text-gray-800'
                  }`}>
                    {currentProject.status}
                  </span>
                </div>
              )}
              
              {/* Navigation items */}
              {navigationItems.map((item) => (
                <button
                  key={item.label}
                  onClick={() => handleNavClick(item.href, item.disabled)}
                  disabled={item.disabled}
                  className={`w-full text-left px-4 py-3 rounded-lg transition-colors ${
                    item.active
                      ? 'bg-brand-soft-purple text-white'
                      : item.disabled
                      ? 'text-gray-400 cursor-not-allowed'
                      : 'text-gray-700 hover:bg-brand-sand hover:text-brand-soft-purple'
                  }`}
                  aria-label={item.disabled ? `${item.label} - ${item.tooltip}` : item.label}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{item.label}</span>
                    {item.disabled && (
                      <span className="text-xs text-gray-400">{item.tooltip}</span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </>
  )
}

export default TopNav 