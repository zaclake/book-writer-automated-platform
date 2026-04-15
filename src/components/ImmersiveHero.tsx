'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthToken } from '@/lib/auth'

interface ImmersiveHeroProps {
  projectCount: number
  mostActiveProject?: {
    title: string
    id: string
  }
  onCreateProject: () => void
}

const subtitles = [
  'Your next chapter starts here.',
  "Let's bring your stories to life.",
  'Ready to craft something beautiful?',
  'Every word matters.',
]

export default function ImmersiveHero({ projectCount, mostActiveProject, onCreateProject }: ImmersiveHeroProps) {
  const { user, isLoaded } = useAuthToken()
  const router = useRouter()
  const [currentSubtitle, setCurrentSubtitle] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentSubtitle((prev) => (prev + 1) % subtitles.length)
    }, 5000)
    return () => clearInterval(timer)
  }, [])

  const firstName = isLoaded && user?.firstName ? user.firstName : 'Writer'

  return (
    <div className="relative w-full bg-gradient-to-br from-gray-900 via-indigo-950 to-gray-900 overflow-hidden">
      <div className="absolute top-0 right-0 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl" />
      <div className="absolute bottom-0 left-0 w-80 h-80 bg-violet-500/10 rounded-full blur-3xl" />

      <div className="relative z-10 flex items-center justify-center min-h-[32vh] px-6 py-10">
        <div className="max-w-3xl mx-auto text-center">
          <h1 className="text-3xl md:text-4xl lg:text-5xl font-bold text-white mb-3 leading-tight tracking-tight">
            Welcome back, <span className="text-indigo-300">{firstName}</span>
          </h1>

          <p
            key={currentSubtitle}
            className="text-lg md:text-xl text-white/60 mb-8 transition-opacity duration-500"
          >
            {subtitles[currentSubtitle]}
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
            {mostActiveProject && (
              <button
                onClick={() => router.push(`/project/${mostActiveProject.id}/overview`)}
                className="inline-flex items-center gap-2 px-6 py-3 bg-white text-gray-900 rounded-xl font-semibold text-sm hover:bg-gray-100 focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-2 focus-visible:ring-offset-gray-900 transition shadow-lg"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                Continue: {mostActiveProject.title.length > 30 ? mostActiveProject.title.slice(0, 30) + '...' : mostActiveProject.title}
              </button>
            )}

            <button
              onClick={onCreateProject}
              className={`inline-flex items-center gap-2 px-6 py-3 rounded-xl font-semibold text-sm transition shadow-lg ${
                mostActiveProject
                  ? 'bg-white/10 backdrop-blur-sm text-white border border-white/20 hover:bg-white/20'
                  : 'bg-indigo-500 text-white hover:bg-indigo-400 shadow-indigo-500/25'
              }`}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M12 5v14"/><path d="M5 12h14"/></svg>
              Start a New Book
            </button>

            {projectCount > 1 && (
              <div className="inline-flex items-center px-4 py-2.5 bg-white/10 backdrop-blur-sm rounded-xl border border-white/10 text-sm text-white/70">
                <span className="font-semibold text-white mr-1.5">{projectCount}</span>
                books in progress
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
