interface ErrorContext {
  userId?: string
  url?: string
  userAgent?: string
  timestamp?: string
  apiEndpoint?: string
  httpStatus?: number
  requestId?: string
  projectId?: string
}

interface ErrorEvent {
  message: string
  stack?: string
  context: ErrorContext
  level: 'error' | 'warning' | 'info'
}

class ErrorMonitoring {
  private isEnabled: boolean
  private userId: string | null = null
  private context: Partial<ErrorContext> = {}

  constructor() {
    this.isEnabled = typeof window !== 'undefined'
    
    if (this.isEnabled) {
      this.setupGlobalErrorHandlers()
    }
  }

  setUserId(userId: string) {
    this.userId = userId
    this.context.userId = userId
  }

  setContext(context: Partial<ErrorContext>) {
    this.context = { ...this.context, ...context }
  }

  private setupGlobalErrorHandlers() {
    // Catch unhandled errors
    window.addEventListener('error', (event) => {
      this.captureError(event.error || new Error(event.message), {
        url: event.filename,
        stack: event.error?.stack
      })
    })

    // Catch unhandled promise rejections
    window.addEventListener('unhandledrejection', (event) => {
      this.captureError(new Error(event.reason || 'Unhandled promise rejection'), {
        level: 'error'
      })
    })
  }

  captureError(error: Error | string, context: Partial<ErrorContext> & { level?: 'error' | 'warning' | 'info' } = {}) {
    const errorMessage = typeof error === 'string' ? error : error.message
    const errorStack = typeof error === 'string' ? undefined : error.stack

    const errorEvent: ErrorEvent = {
      message: errorMessage,
      stack: errorStack,
      level: context.level || 'error',
      context: {
        ...this.context,
        ...context,
        timestamp: new Date().toISOString(),
        url: window.location.href,
        userAgent: navigator.userAgent
      }
    }

    this.sendError(errorEvent)
  }

  captureApiError(endpoint: string, status: number, error: any, context: Partial<ErrorContext> = {}) {
    const errorMessage = `API Error: ${endpoint} returned ${status}`
    
    this.captureError(error instanceof Error ? error : new Error(errorMessage), {
      ...context,
      apiEndpoint: endpoint,
      httpStatus: status,
      level: status >= 500 ? 'error' : 'warning'
    })
  }

  captureException(error: Error, context: Partial<ErrorContext> = {}) {
    this.captureError(error, { ...context, level: 'error' })
  }

  captureMessage(message: string, level: 'error' | 'warning' | 'info' = 'info', context: Partial<ErrorContext> = {}) {
    this.captureError(message, { ...context, level })
  }

  private sendError(errorEvent: ErrorEvent) {
    if (process.env.NODE_ENV === 'development') {
      console.error('🚨 Error Monitor (dev):', errorEvent)
      return
    }

    try {
      // In production, send to error monitoring service
      // For now, log to console and localStorage for debugging
      console.error('🚨 Error Monitor:', errorEvent)
      
      // Store recent errors in localStorage for debugging
      const recentErrors = JSON.parse(localStorage.getItem('recent_errors') || '[]')
      recentErrors.unshift(errorEvent)
      
      // Keep only last 10 errors
      const trimmedErrors = recentErrors.slice(0, 10)
      localStorage.setItem('recent_errors', JSON.stringify(trimmedErrors))

      // Example integration with Sentry (commented out)
      // if (window.Sentry) {
      //   window.Sentry.captureException(new Error(errorEvent.message), {
      //     contexts: { custom: errorEvent.context },
      //     level: errorEvent.level
      //   })
      // }

      // Example integration with LogRocket (commented out)
      // if (window.LogRocket) {
      //   window.LogRocket.captureException(new Error(errorEvent.message))
      // }

      // Send to custom endpoint
      // fetch('/api/errors', {
      //   method: 'POST',
      //   headers: { 'Content-Type': 'application/json' },
      //   body: JSON.stringify(errorEvent)
      // }).catch(() => {
      //   // Silently fail if error reporting fails
      // })

    } catch (reportingError) {
      console.error('Failed to report error:', reportingError)
    }
  }

  // Dashboard specific error tracking
  trackProjectsLoadError(error: any) {
    this.captureApiError('/api/projects', 0, error, {
      projectId: 'N/A'
    })
  }

  trackChaptersLoadError(projectId: string, error: any) {
    this.captureApiError('/api/chapters', 0, error, {
      projectId
    })
  }

  trackProjectCreationError(method: 'upload' | 'blank', error: any) {
    this.captureError(error, {
      level: 'error',
      projectId: 'creation-failed'
    })
  }

  trackProjectDeletionError(projectId: string, error: any) {
    this.captureApiError(`/api/projects/${projectId}`, 0, error, {
      projectId
    })
  }

  trackAuthError(error: any) {
    this.captureError(error, {
      level: 'warning'
    })
  }
}

// Lazy initialization to prevent server-side allocation
let errorMonitoringInstance: ErrorMonitoring | null = null

function getErrorMonitoring(): ErrorMonitoring {
  if (typeof window === 'undefined') {
    // Return a no-op instance on server
    return {
      setUserId: () => {},
      setContext: () => {},
      captureError: () => {},
      captureApiError: () => {},
      captureException: () => {},
      captureMessage: () => {},
      trackProjectsLoadError: () => {},
      trackChaptersLoadError: () => {},
      trackProjectCreationError: () => {},
      trackProjectDeletionError: () => {},
      trackAuthError: () => {}
    } as ErrorMonitoring
  }

  if (!errorMonitoringInstance) {
    errorMonitoringInstance = new ErrorMonitoring()
  }
  return errorMonitoringInstance
}

export const errorMonitoring = getErrorMonitoring()

// Hook for using error monitoring in React components
export function useErrorMonitoring() {
  return getErrorMonitoring()
} 