import React from 'react'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { SkeletonPlaceholder } from '@/components/ui/SkeletonPlaceholder'

export function ProjectPageSkeleton(props: { title?: string; lines?: number }) {
  const { title = 'Loading…', lines = 3 } = props
  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 md:px-8 py-8 space-y-6">
      <div className="space-y-2">
        <div className="text-2xl sm:text-3xl font-bold text-gray-900">{title}</div>
        <SkeletonPlaceholder type="text" lines={2} className="max-w-2xl" />
      </div>
      <SkeletonPlaceholder type="card" />
      <SkeletonPlaceholder type="text" lines={lines} />
    </div>
  )
}

export function ProjectPageError(props: {
  title?: string
  message: string
  onRetry?: () => void
  retryLabel?: string
}) {
  const { title = 'Something went wrong', message, onRetry, retryLabel = 'Retry' } = props
  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 md:px-8 py-8">
      <Alert variant="destructive">
        <AlertDescription>
          <div className="space-y-3">
            <div className="font-semibold">{title}</div>
            <div className="text-sm opacity-90">{message}</div>
            {onRetry && (
              <div>
                <Button variant="outline" onClick={onRetry}>
                  {retryLabel}
                </Button>
              </div>
            )}
          </div>
        </AlertDescription>
      </Alert>
    </div>
  )
}

