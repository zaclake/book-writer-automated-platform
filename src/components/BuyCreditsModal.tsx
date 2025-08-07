'use client'

import { useState } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { CreditCard, Zap, Star, Gift, X } from 'lucide-react'
import { useCreditsApi } from '@/lib/api-client'
import { toast } from 'sonner'

export interface BuyCreditsModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  requiredCredits?: number
  availableCredits?: number
  message?: string
}

interface CreditPackage {
  id: string
  name: string
  credits: number
  price: number
  popular?: boolean
  description: string
  value: string
}

const creditPackages: CreditPackage[] = [
  {
    id: 'starter',
    name: 'Starter Pack',
    credits: 1000,
    price: 10,
    description: '2-5 chapters or multiple reference generations',
    value: 'Perfect for trying the platform'
  },
  {
    id: 'creator',
    name: 'Creator Pack',
    credits: 5000,
    price: 45,
    popular: true,
    description: '10-15 chapters plus cover art',
    value: 'Most popular - Save $5'
  },
  {
    id: 'author',
    name: 'Author Pack',
    credits: 10000,
    price: 85,
    description: 'Full novel (20-25 chapters) + extras',
    value: 'Best value - Save $15'
  }
]

export function BuyCreditsModal({
  open,
  onOpenChange,
  requiredCredits,
  availableCredits,
  message
}: BuyCreditsModalProps) {
  const [selectedPackage, setSelectedPackage] = useState<string>('creator')
  const [isInitializingBeta, setIsInitializingBeta] = useState(false)
  const creditsApi = useCreditsApi()

  const handleInitializeBetaCredits = async () => {
    setIsInitializingBeta(true)
    
    try {
      const response = await creditsApi.initializeBetaCredits()
      
      if (response.ok && response.data?.success) {
        toast.success('Beta Credits Granted!', {
          description: `You've received ${response.data.credits_granted} free credits to get started.`
        })
        onOpenChange(false)
        // Refresh the page to update balance
        window.location.reload()
      } else if (response.data?.already_initialized) {
        toast.info('Credits Already Initialized', {
          description: `You already have ${response.data.current_balance} credits in your account.`
        })
        onOpenChange(false)
      } else {
        toast.error('Failed to Initialize Credits', {
          description: response.error?.message || 'Please try again or contact support.'
        })
      }
    } catch (error) {
      console.error('Beta credits initialization error:', error)
      toast.error('Network Error', {
        description: 'Please check your connection and try again.'
      })
    } finally {
      setIsInitializingBeta(false)
    }
  }

  const handlePurchase = async (packageId: string) => {
    // This is a stub - will be implemented with Stripe integration
    toast.info('Coming Soon', {
      description: 'Credit purchasing will be available soon. Contact support for early access.',
      duration: 6000
    })
  }

  const selectedPkg = creditPackages.find(pkg => pkg.id === selectedPackage)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-yellow-500" />
            Get Credits to Continue
          </DialogTitle>
          <DialogDescription>
            {requiredCredits && availableCredits !== undefined ? (
              <span>
                You need <strong>{requiredCredits} credits</strong> but only have <strong>{availableCredits}</strong>.
                {message && ` ${message}`}
              </span>
            ) : (
              'Choose a credit package to continue using AI features.'
            )}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          {/* Beta Credits Option */}
          <div className="bg-gradient-to-r from-blue-50 to-purple-50 border border-blue-200 rounded-lg p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Gift className="h-5 w-5 text-blue-600" />
                <div>
                  <h3 className="font-semibold text-blue-900">Beta Program</h3>
                  <p className="text-sm text-blue-700">
                    Get 2,000 free credits to try our platform ($20 value)
                  </p>
                </div>
              </div>
              <Button 
                onClick={handleInitializeBetaCredits}
                disabled={isInitializingBeta}
                variant="outline"
                className="border-blue-300 text-blue-700 hover:bg-blue-50"
              >
                {isInitializingBeta ? 'Initializing...' : 'Claim Free Credits'}
              </Button>
            </div>
          </div>

          {/* Credit Packages */}
          <div>
            <h3 className="font-semibold mb-4">Credit Packages</h3>
            <div className="grid gap-3">
              {creditPackages.map((pkg) => (
                <div
                  key={pkg.id}
                  className={`border rounded-lg p-4 cursor-pointer transition-all ${
                    selectedPackage === pkg.id
                      ? 'border-blue-500 bg-blue-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                  onClick={() => setSelectedPackage(pkg.id)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className={`w-4 h-4 rounded-full border-2 ${
                        selectedPackage === pkg.id
                          ? 'border-blue-500 bg-blue-500'
                          : 'border-gray-300'
                      }`}>
                        {selectedPackage === pkg.id && (
                          <div className="w-full h-full rounded-full bg-white scale-50" />
                        )}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h4 className="font-medium">{pkg.name}</h4>
                          {pkg.popular && (
                            <Badge variant="secondary" className="bg-yellow-100 text-yellow-800">
                              <Star className="h-3 w-3 mr-1" />
                              Popular
                            </Badge>
                          )}
                        </div>
                        <p className="text-sm text-gray-600">{pkg.description}</p>
                        <p className="text-xs text-blue-600">{pkg.value}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-lg font-semibold">${pkg.price}</div>
                      <div className="text-sm text-gray-500">{pkg.credits.toLocaleString()} credits</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Usage Examples */}
          <div className="bg-gray-50 rounded-lg p-4">
            <h4 className="font-medium mb-2">What can you do with credits?</h4>
            <div className="text-sm text-gray-600 space-y-1">
              <div>• Generate a novel chapter (3,000 words): ~100-200 credits</div>
              <div>• Create reference files (characters, outline): ~50-100 credits</div>
              <div>• Generate cover art: ~200 credits</div>
              <div>• Complete novel (25 chapters): ~3,000-5,000 credits</div>
            </div>
          </div>
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button 
            onClick={() => handlePurchase(selectedPackage)}
            disabled={!selectedPkg}
            className="flex items-center gap-2"
          >
            <CreditCard className="h-4 w-4" />
            Purchase {selectedPkg?.credits.toLocaleString()} Credits
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// Global state for the modal
let globalModalOpen = false
let globalModalProps: Partial<BuyCreditsModalProps> = {}
let globalModalSetter: ((props: Partial<BuyCreditsModalProps>) => void) | null = null

export function showBuyCreditsModal(props: Partial<BuyCreditsModalProps> = {}) {
  if (globalModalSetter) {
    globalModalSetter({ ...props, open: true })
  } else {
    // Store props for when the modal component mounts
    globalModalProps = { ...props, open: true }
    globalModalOpen = true
  }
}

export function hideBuyCreditsModal() {
  if (globalModalSetter) {
    globalModalSetter({ open: false })
  } else {
    globalModalOpen = false
  }
}

// Hook for managing global modal state
export function useGlobalBuyCreditsModal() {
  const [modalState, setModalState] = useState<Partial<BuyCreditsModalProps>>(() => ({
    open: globalModalOpen,
    ...globalModalProps
  }))

  // Register the setter for global access
  if (!globalModalSetter) {
    globalModalSetter = setModalState
  }

  const handleOpenChange = (open: boolean) => {
    setModalState(prev => ({ ...prev, open }))
    globalModalOpen = open
  }

  return {
    modalProps: {
      ...modalState,
      onOpenChange: handleOpenChange
    },
    showModal: (props: Partial<BuyCreditsModalProps> = {}) => {
      setModalState({ ...props, open: true })
    },
    hideModal: () => {
      setModalState(prev => ({ ...prev, open: false }))
    }
  }
}