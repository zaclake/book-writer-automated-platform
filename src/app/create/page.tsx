'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function CreateProjectPage() {
  const router = useRouter()

  useEffect(() => {
    router.replace('/create/paste-idea')
  }, [router])

  return null
}
