import { useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'

export interface InsufficientCreditsError {
  error: 'INSUFFICIENT_CREDITS'
  required: number
  available?: number
  message: string
}

export interface CreditError {
  status: number
  data: InsufficientCreditsError | { error: string; message: string }
}

/**
 * Hook for handling credits-related errors globally
 */
export function useCreditsErrorHandler() {
  const router = useRouter()

  const handleCreditsError = useCallback((error: any) => {
    // Check if this is a 402 Payment Required error
    if (error?.status === 402 || error?.response?.status === 402) {
      const errorData = error?.data || error?.response?.data
      
      if (errorData?.error === 'INSUFFICIENT_CREDITS') {
        const { required, available = 0, message } = errorData
        
        // Show detailed insufficient credits toast
        toast.error('Insufficient Credits', {
          description: `Need ${required} credits, have ${available}. ${message}`,
          action: {
            label: 'Buy Credits',
            onClick: () => {
              // Navigate to credits page
              router.push('/profile?tab=credits')
            }
          },
          duration: 8000
        })
        
        return true // Handled
      } else {
        // Generic 402 error
        toast.error('Payment Required', {
          description: 'This operation requires credits to complete.',
          action: {
            label: 'Buy Credits',
            onClick: () => {
              router.push('/profile?tab=credits')
            }
          },
          duration: 6000
        })
        
        return true // Handled
      }
    }
    
    // Not a credits error
    return false
  }, [router])

  const handleApiError = useCallback((error: any) => {
    // Try to handle as credits error first
    if (handleCreditsError(error)) {
      return true
    }
    
    // Handle other common API errors
    const status = error?.status || error?.response?.status
    const message = error?.message || error?.response?.data?.message || 'An error occurred'
    
    switch (status) {
      case 401:
        toast.error('Authentication Required', {
          description: 'Please sign in to continue.',
          action: {
            label: 'Sign In',
            onClick: () => router.push('/sign-in')
          }
        })
        return true
        
      case 403:
        toast.error('Access Denied', {
          description: 'You do not have permission to perform this action.'
        })
        return true
        
      case 404:
        toast.error('Not Found', {
          description: 'The requested resource was not found.'
        })
        return true
        
      case 429:
        toast.error('Rate Limited', {
          description: 'Too many requests. Please try again later.'
        })
        return true
        
      case 500:
      case 503:
        toast.error('Server Error', {
          description: 'The server encountered an error. Please try again.'
        })
        return true
        
      default:
        if (status >= 400) {
          toast.error('Error', {
            description: message
          })
          return true
        }
    }
    
    return false
  }, [handleCreditsError, router])

  return {
    handleCreditsError,
    handleApiError
  }
}