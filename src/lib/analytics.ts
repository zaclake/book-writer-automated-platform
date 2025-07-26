interface AnalyticsEvent {
  event: string
  properties?: Record<string, any>
  userId?: string
}

class Analytics {
  private isEnabled: boolean
  private userId: string | null = null

  constructor() {
    this.isEnabled = typeof window !== 'undefined' && process.env.NODE_ENV === 'production'
  }

  setUserId(userId: string) {
    this.userId = userId
  }

  track(event: string, properties: Record<string, any> = {}) {
    if (!this.isEnabled) {
      console.log('📊 Analytics (dev):', event, properties)
      return
    }

    const eventData: AnalyticsEvent = {
      event,
      properties: {
        ...properties,
        timestamp: new Date().toISOString(),
        url: window.location.href,
        userAgent: navigator.userAgent
      },
      userId: this.userId || undefined
    }

    // Send to analytics service (could be Mixpanel, GA, etc.)
    try {
      // For now, just log to console in production
      // In the future, integrate with actual analytics service
      console.log('📊 Analytics:', eventData)
      
      // Example integration with PostHog (commented out)
      // if (window.posthog) {
      //   window.posthog.capture(event, eventData.properties)
      // }
      
      // Example integration with Google Analytics (commented out)
      // if (window.gtag) {
      //   window.gtag('event', event, eventData.properties)
      // }
      
    } catch (error) {
      console.error('Analytics error:', error)
    }
  }

  // Dashboard specific events
  dashboardViewed() {
    this.track('Dashboard Viewed')
  }

  projectCreated(projectId: string, method: 'upload' | 'blank') {
    this.track('Project Created', {
      projectId,
      method,
      category: 'Project Management'
    })
  }

  projectDeleted(projectId: string, projectTitle?: string) {
    this.track('Project Deleted', {
      projectId,
      projectTitle,
      category: 'Project Management'
    })
  }

  projectSelected(projectId: string, projectTitle?: string) {
    this.track('Project Selected', {
      projectId,
      projectTitle,
      category: 'Navigation'
    })
  }

  navigationClicked(destination: string, projectId?: string) {
    this.track('Navigation Clicked', {
      destination,
      projectId,
      category: 'Navigation'
    })
  }

  chapterClicked(chapterNumber: number, projectId?: string) {
    this.track('Chapter Clicked', {
      chapterNumber,
      projectId,
      category: 'Content'
    })
  }

  autoCompleteStarted(projectId?: string) {
    this.track('Auto Complete Started', {
      projectId,
      category: 'AI Features'
    })
  }

  modalOpened(modalType: string) {
    this.track('Modal Opened', {
      modalType,
      category: 'UI Interaction'
    })
  }

  modalClosed(modalType: string) {
    this.track('Modal Closed', {
      modalType,
      category: 'UI Interaction'
    })
  }
}

export const analytics = new Analytics()

// Hook for using analytics in React components
export function useAnalytics() {
  return analytics
} 