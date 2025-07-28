import { headers } from 'next/headers'

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  // Force dynamic rendering by accessing headers
  headers()
  
  return children
} 