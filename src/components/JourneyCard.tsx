'use client'

import React from 'react'
import { useRouter } from 'next/navigation'
import { PencilIcon } from '@heroicons/react/24/outline'

interface Project {
  id: string
  title: string
  genre?: string
  status: 'active' | 'completed' | 'archived' | 'paused'
  created_at: string
  settings?: {
    target_chapters?: number
    word_count_per_chapter?: number
  }
  metadata?: {
    title?: string
    genre?: string
    status?: string
  }
}

interface Chapter {
  id: string
  chapter_number: number
  stage: 'draft' | 'revision' | 'complete'
  word_count: number
  target_word_count: number
}

interface JourneyCardProps {
  project: Project
  chapters?: Chapter[]
  onEdit?: (projectId: string) => void
  onDelete?: (projectId: string) => void
}

// Enhanced progress ring component with better styling
const ProgressRing = ({ progress, size = 56 }: { progress: number, size?: number }) => {
  const radius = (size - 8) / 2
  const circumference = radius * 2 * Math.PI
  const strokeDasharray = `${circumference} ${circumference}`
  const strokeDashoffset = circumference - (progress / 100) * circumference

  // Dynamic colors based on progress
  const getProgressColor = (progress: number) => {
    if (progress === 0) return 'text-gray-300'
    if (progress < 25) return 'text-blue-400'
    if (progress < 50) return 'text-purple-400'
    if (progress < 75) return 'text-brand-lavender'
    return 'text-emerald-400'
  }

  const getBadgeStyle = (progress: number) => {
    if (progress === 0) return 'bg-gray-100 text-gray-600 border-gray-200'
    if (progress < 25) return 'bg-blue-50 text-blue-700 border-blue-200'
    if (progress < 50) return 'bg-purple-50 text-purple-700 border-purple-200'
    if (progress < 75) return 'bg-brand-lavender/10 text-brand-lavender border-brand-lavender/20'
    return 'bg-emerald-50 text-emerald-700 border-emerald-200'
  }

  return (
    <div className="relative inline-flex items-center justify-center">
      <svg
        className="transform -rotate-90"
        width={size}
        height={size}
      >
        {/* Background circle */}
        <circle
          stroke="currentColor"
          className="text-gray-200"
          strokeWidth="3"
          fill="transparent"
          r={radius}
          cx={size / 2}
          cy={size / 2}
        />
        {/* Progress circle */}
        <circle
          stroke="currentColor"
          className={`${getProgressColor(progress)} transition-all duration-700 ease-out`}
          strokeWidth="3"
          strokeLinecap="round"
          fill="transparent"
          r={radius}
          cx={size / 2}
          cy={size / 2}
          style={{
            strokeDasharray,
            strokeDashoffset,
          }}
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className={`px-2 py-0.5 rounded-full text-xs font-bold border ${getBadgeStyle(progress)}`}>
          {Math.round(progress)}%
        </span>
      </div>
    </div>
  )
}

// Generate book thumbnail colors based on title
const getBookColor = (title: string) => {
  const colors = [
    'from-purple-400 to-purple-600',
    'from-blue-400 to-blue-600', 
    'from-green-400 to-green-600',
    'from-orange-400 to-orange-600',
    'from-pink-400 to-pink-600',
    'from-indigo-400 to-indigo-600',
    'from-teal-400 to-teal-600',
    'from-red-400 to-red-600'
  ]
  
  const hash = title.split('').reduce((a, b) => {
    a = ((a << 5) - a) + b.charCodeAt(0)
    return a & a
  }, 0)
  
  return colors[Math.abs(hash) % colors.length]
}

const JourneyCard: React.FC<JourneyCardProps> = ({
  project,
  chapters = [],
  onEdit,
  onDelete
}) => {
  const router = useRouter()

  // Calculate progress - better handling for projects without chapters
  const targetChapters = project.settings?.target_chapters || 25 // Default to 25 chapters
  const totalChapters = Math.max(targetChapters, chapters.length) || 1
  const completedChapters = chapters.filter(c => c.stage === 'complete').length
  const chaptersWritten = chapters.length
  
  // Progress based on chapters written vs target, not just completed
  const writtenProgressPercentage = Math.round((chaptersWritten / targetChapters) * 100) || 0
  const completedProgressPercentage = Math.round((completedChapters / targetChapters) * 100) || 0
  
  // Use written progress as the main indicator
  const progressPercentage = Math.min(100, writtenProgressPercentage)
  
  // Helper function for progress display
  const getDisplayProgress = (progress: number) => {
    // Always show at least 1% if there are any chapters
    if (progress === 0 && chapters.length > 0) return 1
    return progress
  }

  // Get creative progress message
  const getProgressMessage = (progress: number) => {
    if (progress === 0) return "Ready to begin your story"
    if (progress < 25) return "The opening pages are flowing"
    if (progress < 50) return "Building momentum beautifully"
    if (progress < 75) return "The story is taking shape"
    if (progress === 100) return "Your masterpiece awaits"
    return "Approaching the climax"
  }

  // Get warm CTA text based on progress
  const getCTAText = (progress: number) => {
    if (progress === 0) return "Let's write"
    if (progress === 100) return "Admire your work"
    return "Pick up where you left off"
  }

  const handleContinue = () => {
    router.push(`/project/${project.id}/overview`)
  }

  const formatDate = (dateString: string) => {
    try {
      const date = new Date(dateString)
      if (isNaN(date.getTime())) {
        return null
      }
      
      const now = new Date()
      const diffTime = Math.abs(now.getTime() - date.getTime())
      const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24))
      
      if (diffDays === 1) return "Yesterday"
      if (diffDays < 7) return `${diffDays} days ago`
      if (diffDays < 30) return `${Math.ceil(diffDays / 7)} weeks ago`
      
      return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined
      })
    } catch {
      return null
    }
  }

  const statusColors = {
    active: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    completed: 'bg-purple-50 text-purple-800 border-purple-200',
    paused: 'bg-amber-50 text-amber-800 border-amber-200',
    archived: 'bg-slate-50 text-slate-600 border-slate-200'
  }

  const statusLabels = {
    active: 'In Progress',
    completed: 'Complete',
    paused: 'Paused',
    archived: 'Archived'
  }

  const totalWords = chapters.reduce((sum, c) => sum + c.word_count, 0)
  const bookColor = getBookColor(project.metadata?.title || project.title || project.id)
  const formattedDate = formatDate(project.created_at)

  return (
    <div className="group relative antialiased">
      {/* Main card with enhanced styling */}
      <div className="bg-gradient-to-br from-white via-brand-off-white to-brand-beige/40 rounded-2xl border border-brand-lavender/20 p-5 shadow-xl hover:shadow-2xl transition-all duration-500 hover:-translate-y-3 hover:scale-[1.02] backdrop-blur-sm overflow-hidden transform-gpu will-change-transform">
        
        {/* Subtle paper texture overlay */}
        <div className="absolute inset-0 opacity-20 bg-gradient-to-br from-transparent via-white/30 to-transparent" />
        
        {/* Edit button - top right */}
        {onEdit && (
          <button
            onClick={() => onEdit(project.id)}
            className="absolute top-4 right-4 z-10 p-2 rounded-full bg-white/80 backdrop-blur-sm border border-brand-lavender/20 text-brand-forest/60 hover:text-brand-lavender hover:bg-white hover:shadow-md transition-all duration-200 opacity-0 group-hover:opacity-100"
          >
            <PencilIcon className="w-4 h-4" />
          </button>
        )}

        {/* Header with book thumbnail - tighter spacing */}
        <div className="relative flex items-start space-x-3 mb-4">
          {/* Book spine thumbnail */}
          <div className={`flex-shrink-0 w-11 h-14 bg-gradient-to-b ${bookColor} rounded-md shadow-lg relative overflow-hidden group-hover:shadow-xl transition-all duration-300`}>
            <div className="absolute inset-0 bg-gradient-to-r from-white/25 to-transparent" />
            <div className="absolute bottom-1 left-1 right-1">
              <div className="h-0.5 bg-white/40 mb-0.5" />
              <div className="h-0.5 bg-white/25" />
            </div>
          </div>
          
          {/* Title and metadata - tighter spacing */}
          <div className="flex-1 min-w-0 pr-8">
            <h3 className="text-lg font-bold text-brand-forest leading-tight mb-1 group-hover:text-brand-lavender transition-colors duration-300 select-none">
              {project.metadata?.title || project.title || `Journey ${project.id}`}
            </h3>
            
            <div className="flex items-center gap-2 mb-1">
              {project.metadata?.genre && (
                <span className="text-xs text-brand-forest/70 font-semibold">
                  {project.metadata.genre}
                </span>
              )}
              
              <span className={`px-2 py-0.5 rounded-full text-xs font-bold border ${statusColors[project.status]}`}>
                {statusLabels[project.status]}
              </span>
            </div>
            
            {/* Date started - only show if valid */}
            {formattedDate && (
              <p className="text-xs text-brand-forest/50 font-medium">
                Started {formattedDate}
              </p>
            )}
          </div>
          
          {/* Progress ring */}
          <div className="flex-shrink-0">
            <ProgressRing progress={getDisplayProgress(progressPercentage)} size={52} />
          </div>
        </div>

        {/* Progress message - tighter spacing */}
        <div className="mb-4">
          <p className="text-sm font-semibold text-brand-forest/80 italic leading-relaxed">
            {getProgressMessage(progressPercentage)}
          </p>
        </div>

        {/* Stats with tighter spacing */}
        <div className="grid grid-cols-2 gap-3 mb-5">
          <div className="text-center p-3 bg-gradient-to-br from-brand-beige/60 to-white/60 rounded-xl border border-brand-lavender/15">
            <div className="text-lg font-black text-brand-forest">{chapters.length}</div>
            <div className="text-xs text-brand-forest/60 font-bold uppercase tracking-wide">
              {chapters.length === 1 ? 'Chapter' : 'Chapters'}
            </div>
          </div>
          <div className="text-center p-3 bg-gradient-to-br from-brand-beige/60 to-white/60 rounded-xl border border-brand-lavender/15">
            <div className="text-lg font-black text-brand-forest">
              {totalWords === 0 ? '0' : 
               totalWords > 1000 ? `${Math.round(totalWords / 1000)}k` : 
               totalWords.toLocaleString()}
            </div>
            <div className="text-xs text-brand-forest/60 font-bold uppercase tracking-wide">Words</div>
            {totalWords === 0 && (
              <div className="text-xs text-brand-forest/40 mt-1">Start writing!</div>
            )}
          </div>
        </div>

        {/* Enhanced CTA button */}
        <div className="flex justify-center">
          <button
            onClick={handleContinue}
            className="group/btn bg-gradient-to-r from-brand-forest to-brand-lavender text-white px-7 py-3 rounded-xl text-sm font-bold hover:shadow-xl hover:shadow-brand-lavender/25 hover:scale-105 transition-all duration-300 flex items-center space-x-2 relative overflow-hidden"
          >
            <span className="relative z-10">{getCTAText(progressPercentage)}</span>
            <svg className="w-4 h-4 relative z-10 transition-transform group-hover/btn:translate-x-1 duration-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            {/* Hover glow effect */}
            <div className="absolute inset-0 bg-gradient-to-r from-white/20 to-white/10 opacity-0 group-hover/btn:opacity-100 transition-opacity duration-300" />
          </button>
        </div>
      </div>
    </div>
  )
}

export default JourneyCard 