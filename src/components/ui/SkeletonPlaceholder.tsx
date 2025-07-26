interface SkeletonPlaceholderProps {
  type?: 'text' | 'button' | 'card' | 'list' | 'custom'
  className?: string
  lines?: number
  width?: string
  height?: string
}

export function SkeletonPlaceholder({ 
  type = 'text', 
  className = '', 
  lines = 3,
  width = 'w-full',
  height = 'h-4'
}: SkeletonPlaceholderProps) {
  const baseClasses = 'animate-pulse bg-gray-200 rounded'

  if (type === 'text') {
    return (
      <div className={`space-y-2 ${className}`}>
        {Array.from({ length: lines }).map((_, i) => (
          <div
            key={i}
            className={`${baseClasses} ${height} ${
              i === lines - 1 ? 'w-3/4' : width
            }`}
          />
        ))}
      </div>
    )
  }

  if (type === 'button') {
    return (
      <div className={`${baseClasses} ${width} h-10 ${className}`} />
    )
  }

  if (type === 'card') {
    return (
      <div className={`p-6 border border-gray-200 rounded-lg ${className}`}>
        <div className="space-y-4">
          <div className={`${baseClasses} h-6 w-1/2`} />
          <div className="space-y-2">
            <div className={`${baseClasses} h-4 w-full`} />
            <div className={`${baseClasses} h-4 w-3/4`} />
          </div>
          <div className={`${baseClasses} h-10 w-1/3`} />
        </div>
      </div>
    )
  }

  if (type === 'list') {
    return (
      <div className={`space-y-3 ${className}`}>
        {Array.from({ length: lines }).map((_, i) => (
          <div key={i} className="flex items-center space-x-3">
            <div className={`${baseClasses} w-8 h-8 rounded-full`} />
            <div className="space-y-1 flex-1">
              <div className={`${baseClasses} h-4 w-1/2`} />
              <div className={`${baseClasses} h-3 w-1/4`} />
            </div>
          </div>
        ))}
      </div>
    )
  }

  // Custom skeleton
  return (
    <div className={`${baseClasses} ${width} ${height} ${className}`} />
  )
} 