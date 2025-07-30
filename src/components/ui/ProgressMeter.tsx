'use client'

import React from 'react'

interface ProgressMeterProps {
  progress: number // 0-100
  size?: 'sm' | 'md' | 'lg'
  showPercentage?: boolean
  animated?: boolean
  label?: string
}

const ProgressMeter: React.FC<ProgressMeterProps> = ({
  progress,
  size = 'md',
  showPercentage = true,
  animated = true,
  label
}) => {
  const clampedProgress = Math.min(Math.max(progress, 0), 100)
  
  const sizeClasses = {
    sm: 'h-2',
    md: 'h-3',
    lg: 'h-4'
  }

  const progressColor = 
    clampedProgress === 100 ? 'bg-brand-leaf' :
    clampedProgress >= 75 ? 'bg-brand-soft-purple' :
    clampedProgress >= 50 ? 'bg-gradient-to-r from-brand-soft-purple to-brand-leaf' :
    clampedProgress >= 25 ? 'bg-brand-soft-purple' :
    'bg-gray-300'

  return (
    <div className="w-full">
      {label && (
        <div className="flex justify-between items-center mb-2">
          <span className="text-sm font-medium text-gray-700">{label}</span>
          {showPercentage && (
            <span className="text-sm text-gray-500">{Math.round(clampedProgress)}%</span>
          )}
        </div>
      )}
      
      <div className={`w-full bg-gray-200 rounded-full overflow-hidden ${sizeClasses[size]}`}>
        <div
          className={`${progressColor} ${sizeClasses[size]} rounded-full transition-all duration-500 ease-out ${
            animated ? 'transform-gpu' : ''
          }`}
          style={{ width: `${clampedProgress}%` }}
        >
          {animated && clampedProgress > 0 && (
            <div className="h-full w-full bg-gradient-to-r from-transparent via-white/20 to-transparent animate-pulse" />
          )}
        </div>
      </div>
    </div>
  )
}

export default ProgressMeter 