import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import { ClerkProvider } from '@clerk/nextjs'
import AppLayout from '@/components/layout/AppLayout'
import './globals.css'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'Book Writer Dashboard',
  description: 'AI-powered chapter generation and quality assessment dashboard',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <ClerkProvider>
      <html lang="en">
        <body className={inter.className}>
          <AppLayout>
            {children}
          </AppLayout>
        </body>
      </html>
    </ClerkProvider>
  )
} 