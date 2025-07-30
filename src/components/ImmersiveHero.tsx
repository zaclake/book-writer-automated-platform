'use client'

import { useState, useEffect } from 'react'
import { useAuth } from '@clerk/nextjs'

interface ImmersiveHeroProps {
  projectCount: number
  mostActiveProject?: {
    title: string
    id: string
  }
  onCreateProject: () => void
}

const FloatingMotif = ({ 
  path, 
  delay = 0, 
  size = 24, 
  className = '' 
}: { 
  path: string
  delay?: number
  size?: number
  className?: string
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    className={`absolute text-white/10 reduce-motion:animate-none animate-float ${className}`}
    style={{ animationDelay: `${delay}s` }}
    fill="currentColor"
  >
    <path d={path} />
  </svg>
)

// Animated particles for floating ideas effect
const FloatingParticle = ({ delay = 0, size = 4, className = '' }: { delay?: number, size?: number, className?: string }) => (
  <div
    className={`absolute bg-white/20 rounded-full reduce-motion:animate-none animate-float ${className}`}
    style={{ 
      animationDelay: `${delay}s`,
      width: `${size}px`,
      height: `${size}px`,
      animationDuration: `${8 + Math.random() * 4}s`
    }}
  />
)

// SVG paths for floating motifs - extremely faint background elements
const MOTIFS = {
  book: "M18,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V4A2,2 0 0,0 18,2M18,20H6V4H18V20Z",
  quill: "M23,10C23,8.89 22.1,8 21,8H14.68L15.64,7.04C16.78,5.9 16.78,4.1 15.64,2.96C14.5,1.82 12.7,1.82 11.56,2.96L7.5,7H2V9H7.5L11.56,13.04C12.7,14.18 14.5,14.18 15.64,13.04L16.6,12.08L21,16.5L22.41,15.09L18,10.68H21C22.1,10.68 23,9.78 23,8.68V10Z",
  sparkle: "M19,3H17V5H19V3M13,3H11V5H13V3M19,9H17V11H19V9M13,9H11V11H13V9M7,3H5V5H7V3M7,9H5V11H7V9M19,15H17V17H19V15M13,15H11V17H13V15M7,15H5V17H7V15M19,21H17V23H19V21M13,21H11V23H13V21M7,21H5V23H7V21M3,3H1V5H3V3M3,9H1V11H3V9M3,15H1V17H3V15M3,21H1V23H3V21"
}

// Rotating subtitles for emotional engagement
const subtitles = [
  "Your next chapter starts here…",
  "Let's bring your stories to life.",
  "We missed your words.",
  "Ready to craft something beautiful?",
  "Every word matters."
]

export default function ImmersiveHero({ projectCount, mostActiveProject, onCreateProject }: ImmersiveHeroProps) {
  const { user } = useAuth()
  const [isVisible, setIsVisible] = useState(false)
  const [scrollY, setScrollY] = useState(0)
  const [currentSubtitle, setCurrentSubtitle] = useState(0)

  useEffect(() => {
    setIsVisible(true)

    const handleScroll = () => setScrollY(window.scrollY)
    window.addEventListener('scroll', handleScroll)

    // Rotate subtitles every 4 seconds
    const subtitleInterval = setInterval(() => {
      setCurrentSubtitle((prev) => (prev + 1) % subtitles.length)
    }, 4000)

    return () => {
      window.removeEventListener('scroll', handleScroll)
      clearInterval(subtitleInterval)
    }
  }, [])

  const getCurrentSubtitle = () => {
    return subtitles[currentSubtitle]
  }

  return (
    <div className="relative w-full overflow-hidden">
      {/* Enhanced gradient background with subtle radial overlay */}
      <div className="absolute inset-0 bg-gradient-to-br from-brand-lavender via-brand-ink-blue to-brand-blush-orange">
        {/* Subtle radial overlay for focus */}
        <div className="absolute inset-0 bg-gradient-radial from-transparent via-black/5 to-black/10" />
        {/* Animated shimmer overlay */}
        <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/5 to-transparent animate-shimmer" />
      </div>

      {/* Floating particles for ideas/pages effect */}
      <div className="absolute inset-0">
        <FloatingParticle delay={0} size={3} className="top-[20%] left-[15%]" />
        <FloatingParticle delay={2} size={2} className="top-[40%] right-[20%]" />
        <FloatingParticle delay={4} size={4} className="bottom-[30%] left-[25%]" />
        <FloatingParticle delay={1} size={2} className="top-[60%] right-[35%]" />
        <FloatingParticle delay={3} size={3} className="bottom-[50%] right-[15%]" />
        <FloatingParticle delay={5} size={2} className="top-[80%] left-[40%]" />
      </div>

      {/* Floating background motifs - extremely faint */}
      <div 
        className="absolute inset-0 reduce-motion:transform-none"
        style={{
          transform: `translateY(${scrollY * 0.3}px)`,
        }}
      >
        <FloatingMotif 
          path={MOTIFS.book} 
          delay={0} 
          size={32}
          className="top-[15%] left-[10%] md:top-[20%] md:left-[15%]" 
        />
        <FloatingMotif 
          path={MOTIFS.quill} 
          delay={1.5} 
          size={28}
          className="top-[25%] right-[15%] md:top-[30%] md:right-[20%]" 
        />
        <FloatingMotif 
          path={MOTIFS.sparkle} 
          delay={3} 
          size={24}
          className="bottom-[25%] left-[20%] md:bottom-[30%] md:left-[25%]" 
        />
        <FloatingMotif 
          path={MOTIFS.book} 
          delay={2} 
          size={20}
          className="top-[45%] right-[25%] md:top-[50%] md:right-[30%]" 
        />
        <FloatingMotif 
          path={MOTIFS.sparkle} 
          delay={4} 
          size={18}
          className="bottom-[35%] right-[10%] md:bottom-[40%] md:right-[15%]" 
        />
      </div>

      {/* Content - reduced height */}
      <div 
        className={`relative z-10 flex items-center justify-center min-h-[45vh] px-6 py-12 transition-all duration-1000 reduce-motion:transition-none ${
          isVisible ? 'animate-fade-in-up reduce-motion:animate-none reduce-motion:opacity-100' : 'opacity-0'
        }`}
      >
        <div className="max-w-4xl mx-auto text-center text-white">
          {/* Enhanced typography with soft glow and styled "Writer" */}
          <h1 className="text-3xl md:text-4xl lg:text-5xl font-bold mb-4 leading-tight drop-shadow-lg">
            <span className="block bg-gradient-to-r from-white via-white/95 to-white/90 bg-clip-text text-transparent">
              {user?.firstName ? `Welcome back, ` : 'Welcome back, '}
              <span className="font-serif italic text-white/95 drop-shadow-xl">
                {user?.firstName || 'Writer'}
              </span>
            </span>
          </h1>
          
          {/* Animated rotating subheading */}
          <p 
            key={currentSubtitle}
            className="text-lg md:text-xl lg:text-2xl font-medium text-white/85 mb-8 leading-relaxed max-w-3xl mx-auto animate-fade-in-up"
          >
            {getCurrentSubtitle()}
          </p>
          
          {/* Unified CTA layout block - centered */}
          <div className="flex flex-col items-center space-y-4">
            {/* Enhanced journey progress pill - no icons, better contrast */}
            {projectCount > 0 && (
              <div className="inline-flex items-center bg-white/20 backdrop-blur-md rounded-2xl px-6 py-3 border border-white/30 shadow-2xl">
                <div className="text-white">
                  <span className="text-xl font-bold">{projectCount}</span>
                  <span className="text-base font-medium ml-2">
                    {projectCount === 1 ? 'journey' : 'journeys'} in progress
                  </span>
                </div>
              </div>
            )}


          </div>
        </div>
      </div>
    </div>
  )
} 