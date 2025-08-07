'use client'

import { useState, useEffect } from 'react'
import { useUser } from '@clerk/nextjs'
import { Zap, Plus, AlertCircle, Loader2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { useAuthToken } from '@/lib/auth'
import { showBuyCreditsModal } from '@/components/BuyCreditsModal'
import { toast } from 'sonner'
import apiClient from '@/lib/apiClient'

export interface CreditBalance {
  balance: number
  pending_debits: number
  available_balance: number
  last_updated: string
}

export interface CreditBalanceProps {
  variant?: 'compact' | 'full'
  showActions?: boolean
  className?: string
}

export function CreditBalance({ 
  variant = 'compact', 
  showActions = true, 
  className = '' 
}: CreditBalanceProps) {
  const { user } = useUser()
  const { getAuthHeaders, isLoaded, isSignedIn } = useAuthToken()
  const [balance, setBalance] = useState<CreditBalance | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [authFailed, setAuthFailed] = useState(false)

  useEffect(() => {
    if (!user) {
      setLoading(false)
      setAuthFailed(false) // Reset auth failure state when user changes
      return
    }

    setAuthFailed(false) // Reset auth failure state for new user
    loadBalance()
    
    // Set up periodic refresh every 30 seconds, but stop if auth fails
    const interval = setInterval(() => {
      if (!authFailed) {
        loadBalance()
      }
    }, 30000)
    
    // Listen for manual refresh events
    const handleRefresh = () => {
      if (!authFailed) {
        loadBalance()
      }
    }
    window.addEventListener('refreshCreditBalance', handleRefresh)
    
    return () => {
      clearInterval(interval)
      window.removeEventListener('refreshCreditBalance', handleRefresh)
    }
  }, [user, authFailed])

  const loadBalance = async () => {
    // Don't attempt to load balance if user is not available or not signed in
    if (!user || !isSignedIn) {
      setLoading(false)
      return
    }

    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetch('/api/v2/credits/balance', { headers: authHeaders })
      
      if (response.ok) {
        const data = await response.json()
        setBalance(data)
        setError(null)
      } else if (response.status === 501) {
        // Credits system not enabled
        setBalance(null)
        setError(null)
      } else if (response.status === 401) {
        // User not authenticated - stop polling to prevent spam
        setBalance(null)
        setError(null)
        setAuthFailed(true)
        setLoading(false)
        console.log('Credits: Authentication failed, stopping balance polling')
        return
      } else {
        const errorData = await response.json().catch(() => ({} as any))
        setError((errorData as any).error || 'Failed to load balance')
        console.error('Credits balance error:', response.status, (errorData as any).error)
      }
    } catch (error) {
      console.error('Credits balance error:', error)
      setError('Failed to load balance')
    } finally {
      setLoading(false)
    }
  }

  const handleBuyCredits = () => {
    showBuyCreditsModal({
      availableCredits: balance?.available_balance
    })
  }

  const handleInitializeBeta = async () => {
    if (!isSignedIn) return

    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetch('/api/v2/credits/initialize-beta', {
        method: 'POST',
        headers: authHeaders
      })
      
      if (response.ok) {
        const data = await response.json()
        if (data.success) {
          toast.success('Beta Credits Granted!', {
            description: `You've received ${data.credits_granted} free credits.`
          })
          loadBalance() // Refresh balance
        } else if (data.already_initialized) {
          toast.info('Credits Already Initialized', {
            description: `You already have ${data.current_balance} credits.`
          })
        }
      } else {
        const errorData = await response.json()
        toast.error('Failed to Initialize Credits', {
          description: errorData.message || 'Please try again.'
        })
      }
    } catch (error) {
      console.error('Beta credits error:', error)
      toast.error('Network Error', {
        description: 'Please check your connection and try again.'
      })
    }
  }

  // Don't render if user not loaded or credits system not available
  if (!user || (!loading && !balance && !error) || authFailed) {
    return null
  }

  if (loading) {
    return (
      <div className={`flex items-center gap-2 ${className}`}>
        <Loader2 className="h-4 w-4 animate-spin text-gray-400" />
        <span className="text-sm text-gray-500">Loading credits...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className={`flex items-center gap-2 ${className}`}>
        <AlertCircle className="h-4 w-4 text-orange-500" />
        <span className="text-sm text-orange-600">Credits unavailable</span>
      </div>
    )
  }

  if (!balance) {
    // Show beta initialization option
    return (
      <div className={`${className}`}>
        {variant === 'full' ? (
          <div className="bg-gradient-to-r from-blue-50 to-purple-50 border border-blue-200 rounded-lg p-4">
            <div className="flex items-center gap-3 mb-2">
              <Zap className="h-5 w-5 text-blue-600" />
              <h3 className="font-medium text-blue-900">Get Started with Credits</h3>
            </div>
            <p className="text-sm text-blue-700 mb-3">
              Get 2,000 free credits to try our AI features ($20 value)
            </p>
            {showActions && (
              <Button 
                onClick={handleInitializeBeta}
                size="sm"
                variant="outline"
                className="border-blue-300 text-blue-700 hover:bg-blue-50"
              >
                Claim Free Credits
              </Button>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <Zap className="h-4 w-4 text-blue-600" />
            <span className="text-sm text-blue-700">Get free credits</span>
            {showActions && (
              <Button 
                onClick={handleInitializeBeta}
                size="sm"
                variant="ghost"
                className="h-6 px-2 text-xs text-blue-700 hover:bg-blue-50"
              >
                Claim
              </Button>
            )}
          </div>
        )}
      </div>
    )
  }

  const { balance: totalBalance, pending_debits, available_balance } = balance
  const isLow = available_balance < 100
  const isCritical = available_balance < 50

  if (variant === 'compact') {
    return (
      <TooltipProvider>
        <div className={`flex items-center gap-2 ${className}`}>
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="flex items-center gap-2 cursor-pointer">
                <Zap className={`h-4 w-4 ${isCritical ? 'text-red-500' : isLow ? 'text-orange-500' : 'text-yellow-500'}`} />
                <Badge 
                  variant={isCritical ? 'destructive' : isLow ? 'secondary' : 'outline'}
                  className="text-xs"
                >
                  {available_balance.toLocaleString()}
                </Badge>
              </div>
            </TooltipTrigger>
            <TooltipContent>
              <div className="text-xs">
                <div>Available: {available_balance.toLocaleString()} credits</div>
                <div>Total: {totalBalance.toLocaleString()} credits</div>
                {pending_debits > 0 && (
                  <div>Pending: {pending_debits.toLocaleString()} credits</div>
                )}
              </div>
            </TooltipContent>
          </Tooltip>
          
          {showActions && (
            <Button 
              onClick={handleBuyCredits}
              size="sm"
              variant="ghost"
              className="h-6 w-6 p-0"
            >
              <Plus className="h-3 w-3" />
            </Button>
          )}
        </div>
      </TooltipProvider>
    )
  }

  return (
    <div className={`${className}`}>
      <div className="bg-white border rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Zap className={`h-5 w-5 ${isCritical ? 'text-red-500' : isLow ? 'text-orange-500' : 'text-yellow-500'}`} />
            <h3 className="font-medium">Credits</h3>
          </div>
          {showActions && (
            <Button 
              onClick={handleBuyCredits}
              size="sm"
              variant="outline"
              className="flex items-center gap-1"
            >
              <Plus className="h-3 w-3" />
              Buy
            </Button>
          )}
        </div>
        
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="text-sm text-gray-600">Available</span>
            <Badge 
              variant={isCritical ? 'destructive' : isLow ? 'secondary' : 'outline'}
              className="text-sm"
            >
              {available_balance.toLocaleString()}
            </Badge>
          </div>
          
          <div className="flex justify-between items-center text-xs text-gray-500">
            <span>Total</span>
            <span>{totalBalance.toLocaleString()}</span>
          </div>
          
          {pending_debits > 0 && (
            <div className="flex justify-between items-center text-xs text-gray-500">
              <span>Pending</span>
              <span>{pending_debits.toLocaleString()}</span>
            </div>
          )}
        </div>

        {(isLow || isCritical) && (
          <div className={`mt-3 p-2 rounded text-xs ${
            isCritical 
              ? 'bg-red-50 text-red-700 border border-red-200' 
              : 'bg-orange-50 text-orange-700 border border-orange-200'
          }`}>
            {isCritical 
              ? 'Critical: Very low credits remaining'
              : 'Warning: Credits running low'
            }
          </div>
        )}
      </div>
    </div>
  )
}

// Hook for checking if user has sufficient credits for an operation
export function useCreditsCheck() {
  const { getAuthHeaders, isSignedIn } = useAuthToken()
  const [balance, setBalance] = useState<CreditBalance | null>(null)

  useEffect(() => {
    if (isSignedIn) {
      loadBalance()
    }
  }, [isSignedIn])

  const loadBalance = async () => {
    if (!isSignedIn) return
    
    try {
      const authHeaders = await getAuthHeaders()
      const response = await fetch('/api/v2/credits/balance', { headers: authHeaders })
      
      if (response.ok) {
        const data = await response.json()
        setBalance(data)
      }
    } catch (error) {
      console.error('Credits check error:', error)
    }
  }

  const checkSufficient = (requiredCredits: number): boolean => {
    if (!balance) return true // Allow if credits system not available
    return balance.available_balance >= requiredCredits
  }

  const getAvailableCredits = (): number => {
    return balance?.available_balance || 0
  }

  const refreshBalance = () => {
    loadBalance()
  }

  return {
    balance,
    checkSufficient,
    getAvailableCredits,
    refreshBalance,
    isLoaded: balance !== null
  }
}