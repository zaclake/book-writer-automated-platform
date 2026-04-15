'use client'

import React, { useEffect, useRef } from 'react'
import { usePathname } from 'next/navigation'
import TopNav from './TopNav'
import { SyncStatusIndicator } from '@/lib/firestore-offline'
import { ensureFirebaseInitialized } from '@/lib/firestore-client'
import { BuyCreditsModal, useGlobalBuyCreditsModal } from '@/components/BuyCreditsModal'
import { GlobalLoader } from '@/stores/useGlobalLoaderStore'
import { Toaster } from 'sonner'
import { muteConsoleInProduction } from '@/lib/console-mute'

interface AppLayoutProps {
  children: React.ReactNode
}

const AppLayout: React.FC<AppLayoutProps> = ({ children }) => {
  const { modalProps } = useGlobalBuyCreditsModal()
  const pathname = usePathname()
  const prevPathnameRef = useRef(pathname)

  const useNewLayout = process.env.NEXT_PUBLIC_USE_NEW_LAYOUT !== 'false'

  useEffect(() => {
    ensureFirebaseInitialized()
  }, [])

  useEffect(() => {
    muteConsoleInProduction()
  }, [])

  useEffect(() => {
    if (prevPathnameRef.current !== pathname) {
      prevPathnameRef.current = pathname
      GlobalLoader.forceHide()
    }
  }, [pathname])

  if (!useNewLayout) {
    return (
      <div className="min-h-screen bg-gray-50">
        <div className="bg-white border-b border-gray-200 p-4">
          <div className="max-w-7xl mx-auto">
            <h1 className="text-xl font-semibold">WriterBloom (Legacy Mode)</h1>
            <p className="text-sm text-gray-600">New layout disabled via feature flag</p>
          </div>
        </div>
        <main className="max-w-7xl mx-auto p-4">
          {children}
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      <TopNav />

      <main className="flex-1">
        <div className="w-full">
          <div className="px-4 sm:px-6 lg:px-8 py-2">
            <SyncStatusIndicator showDetails />
          </div>

          <div>
            {children}
          </div>
        </div>
      </main>

      <BuyCreditsModal {...modalProps} />
      <Toaster position="bottom-right" richColors />
    </div>
  )
}

export default AppLayout
