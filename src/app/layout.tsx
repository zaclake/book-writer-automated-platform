import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import AppLayout from '@/components/layout/AppLayout'
import './globals.css'
import GlobalLoadingOverlay from '@/components/ui/GlobalLoadingOverlay'
import ActiveJobsBanner from '@/components/ActiveJobsBanner'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'WriterBloom - Your Creative Writing Journey',
  description: 'Transform your stories into published books with AI-powered guidance, gentle encouragement, and professional tools.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const backendUrl =
    process.env.BACKEND_URL?.trim() || process.env.NEXT_PUBLIC_BACKEND_URL?.trim()

  return (
    <html lang="en">
      <body className={inter.className}>
        {backendUrl ? (
          <script
            dangerouslySetInnerHTML={{
              __html: `window.__BACKEND_URL=${JSON.stringify(backendUrl)};`,
            }}
          />
        ) : null}
        <AppLayout>
          {children}
        </AppLayout>
        <GlobalLoadingOverlay />
        <ActiveJobsBanner />
      </body>
    </html>
  )
}
