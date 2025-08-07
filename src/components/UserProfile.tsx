'use client'

import { useState, useEffect } from 'react'
import { useAuth, useUser } from '@clerk/nextjs'
import { useSearchParams } from 'next/navigation'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { CreditBalance, useCreditsCheck } from '@/components/CreditBalance'
import { useCreditsApi, type CreditTransaction } from '@/lib/api-client'
import { 
  UserIcon, 
  PencilIcon, 
  CreditCardIcon,
  ChartBarIcon,
  BookOpenIcon,
  StarIcon,
  GlobeAltIcon,
  AcademicCapIcon,
  BriefcaseIcon,
  HeartIcon,
  Zap,
  ArrowUpIcon,
  ArrowDownIcon,
  ClockIcon
} from '@heroicons/react/24/outline'

interface UserProfileData {
  purpose: 'personal' | 'commercial' | 'educational'
  involvement_level: 'hands_off' | 'balanced' | 'hands_on'
  writing_experience: 'beginner' | 'intermediate' | 'advanced' | 'professional'
  genre_preference: string
  bio?: string
  writing_goals?: string
  completed: boolean
  completed_at?: string
}

interface UsageData {
  monthly_cost: number
  chapters_generated: number
  api_calls: number
  words_generated: number
  projects_created: number
}

export default function UserProfile() {
  const { user, isLoaded } = useUser()
  const { getToken } = useAuth()
  const searchParams = useSearchParams()
  const [profileData, setProfileData] = useState<UserProfileData | null>(null)
  const [usageData, setUsageData] = useState<UsageData | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [isEditing, setIsEditing] = useState(false)
  
  // Credits state
  const creditsApi = useCreditsApi()
  const { balance } = useCreditsCheck()
  const [transactions, setTransactions] = useState<CreditTransaction[]>([])
  const [transactionsLoading, setTransactionsLoading] = useState(false)
  const [hasMoreTransactions, setHasMoreTransactions] = useState(false)
  const [nextCursor, setNextCursor] = useState<string | undefined>()
  
  // Get active tab from URL params
  const activeTab = searchParams.get('tab') || 'profile'

  useEffect(() => {
    if (isLoaded) {
      fetchProfileData()
    }
  }, [isLoaded])

  const fetchProfileData = async () => {
    try {
      setIsLoading(true)
      const token = await getToken()
      
      const response = await fetch('/api/users/v2/onboarding', {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      })

      if (response.ok) {
        const result = await response.json()
        if (result.completed) {
          setProfileData(result.data)
        }
      } else {
        console.error('Failed to fetch profile data')
      }
    } catch (error) {
      console.error('Error fetching profile data:', error)
      setError('Failed to load profile data')
    } finally {
      setIsLoading(false)
    }
  }

  const loadTransactions = async (cursor?: string) => {
    try {
      setTransactionsLoading(true)
      const response = await creditsApi.getTransactions(25, cursor)
      
      if (response.ok && response.data) {
        if (cursor) {
          // Loading more - append to existing
          setTransactions(prev => [...prev, ...response.data.transactions])
        } else {
          // Initial load - replace
          setTransactions(response.data.transactions)
        }
        setHasMoreTransactions(response.data.has_more)
        setNextCursor(response.data.next_cursor)
      }
    } catch (error) {
      console.error('Error loading transactions:', error)
    } finally {
      setTransactionsLoading(false)
    }
  }

  // Load transactions when Credits tab is active
  useEffect(() => {
    if (activeTab === 'credits' && user) {
      loadTransactions()
    }
  }, [activeTab, user])

  const getPurposeIcon = (purpose: string) => {
    switch (purpose) {
      case 'personal': return <HeartIcon className="w-5 h-5" />
      case 'commercial': return <BriefcaseIcon className="w-5 h-5" />
      case 'educational': return <AcademicCapIcon className="w-5 h-5" />
      default: return <UserIcon className="w-5 h-5" />
    }
  }

  const getPurposeLabel = (purpose: string) => {
    switch (purpose) {
      case 'personal': return 'Personal Projects'
      case 'commercial': return 'Commercial Publishing'
      case 'educational': return 'Learning & Education'
      default: return purpose
    }
  }

  const getInvolvementLabel = (level: string) => {
    switch (level) {
      case 'hands_off': return 'Hands-Off (AI-Driven)'
      case 'balanced': return 'Balanced (Collaborative)'
      case 'hands_on': return 'Hands-On (Author-Led)'
      default: return level
    }
  }

  const getExperienceLevel = (experience: string) => {
    switch (experience) {
      case 'beginner': return 'Beginner'
      case 'intermediate': return 'Intermediate'
      case 'advanced': return 'Advanced'
      case 'professional': return 'Professional'
      default: return experience
    }
  }

  const getExperienceColor = (experience: string) => {
    switch (experience) {
      case 'beginner': return 'bg-green-100 text-green-800'
      case 'intermediate': return 'bg-blue-100 text-blue-800'
      case 'advanced': return 'bg-purple-100 text-purple-800'
      case 'professional': return 'bg-gold-100 text-gold-800'
      default: return 'bg-gray-100 text-gray-800'
    }
  }

  const formatTransactionType = (transaction: CreditTransaction) => {
    const isCredit = transaction.type === 'credit'
    return {
      icon: isCredit ? ArrowUpIcon : ArrowDownIcon,
      color: isCredit ? 'text-green-600' : 'text-red-600',
      bgColor: isCredit ? 'bg-green-100' : 'bg-red-100',
      sign: isCredit ? '+' : '-'
    }
  }

  const formatTransactionReason = (reason: string) => {
    const reasonMap: { [key: string]: string } = {
      'beta_grant': 'Beta Credits',
      'account_creation': 'Welcome Bonus',
      'purchase': 'Credit Purchase',
      'chapter_generation': 'Chapter Generation',
      'reference_generation': 'Reference Creation',
      'cover_art_generation': 'Cover Art',
      'admin_grant': 'Admin Grant',
      'refund': 'Refund',
      'auto_complete': 'Auto-Complete Feature'
    }
    return reasonMap[reason] || reason.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
  }

  if (!isLoaded || isLoading) {
    return (
      <div className="min-h-screen bg-brand-off-white py-8">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="animate-pulse space-y-6">
            <div className="h-32 bg-gray-200 rounded-xl"></div>
            <div className="grid md:grid-cols-2 gap-6">
              <div className="h-64 bg-gray-200 rounded-xl"></div>
              <div className="h-64 bg-gray-200 rounded-xl"></div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (!user) {
    return (
      <div className="min-h-screen bg-brand-off-white flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 mb-4">Please Sign In</h1>
          <p className="text-gray-600">You need to be signed in to view your profile.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-brand-off-white py-8">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Profile Header */}
        <Card className="mb-8 overflow-hidden">
          <div className="bg-gradient-to-r from-brand-soft-purple via-brand-lavender to-brand-forest px-6 py-8">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-4">
                <div className="w-20 h-20 bg-white bg-opacity-20 rounded-full flex items-center justify-center">
                  <span className="text-3xl font-bold text-white">
                    {user.firstName?.charAt(0) || user.emailAddresses[0]?.emailAddress.charAt(0) || 'U'}
                  </span>
                </div>
                <div>
                  <h1 className="text-3xl font-bold text-white">
                    {user.firstName ? `${user.firstName} ${user.lastName || ''}`.trim() : user.emailAddresses[0]?.emailAddress || 'User'}
                  </h1>
                  <p className="text-white text-opacity-90 text-lg">
                    {profileData ? getExperienceLevel(profileData.writing_experience) + ' Writer' : 'Writer'}
                  </p>
                  <p className="text-white text-opacity-80 text-sm">
                    Member since {new Date(user.createdAt || Date.now()).toLocaleDateString()}
                  </p>
                </div>
              </div>
              <Button 
                variant="outline" 
                className="bg-white bg-opacity-20 border-white border-opacity-30 text-white hover:bg-white hover:bg-opacity-30"
                onClick={() => setIsEditing(!isEditing)}
              >
                <PencilIcon className="w-4 h-4 mr-2" />
                Edit Profile
              </Button>
            </div>
          </div>
        </Card>

        {/* Tabbed Content */}
        <Tabs value={activeTab} className="space-y-6">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="profile">Profile</TabsTrigger>
            <TabsTrigger value="credits">Credits</TabsTrigger>
            <TabsTrigger value="account">Account</TabsTrigger>
          </TabsList>

          {/* Profile Tab */}
          <TabsContent value="profile">
            <div className="grid md:grid-cols-2 gap-8">
              {/* Writing Preferences */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center">
                    <BookOpenIcon className="w-5 h-5 mr-2 text-brand-soft-purple" />
                    Writing Profile
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
              {profileData ? (
                <>
                  {/* Purpose */}
                  <div className="flex items-center justify-between p-4 bg-brand-sand/30 rounded-lg">
                    <div className="flex items-center space-x-3">
                      {getPurposeIcon(profileData.purpose)}
                      <div>
                        <div className="font-medium text-gray-900">Writing Purpose</div>
                        <div className="text-sm text-gray-600">{getPurposeLabel(profileData.purpose)}</div>
                      </div>
                    </div>
                  </div>

                  {/* Experience Level */}
                  <div className="flex items-center justify-between p-4 bg-brand-sand/30 rounded-lg">
                    <div className="flex items-center space-x-3">
                      <StarIcon className="w-5 h-5 text-brand-soft-purple" />
                      <div>
                        <div className="font-medium text-gray-900">Experience Level</div>
                        <Badge className={getExperienceColor(profileData.writing_experience)}>
                          {getExperienceLevel(profileData.writing_experience)}
                        </Badge>
                      </div>
                    </div>
                  </div>

                  {/* Involvement Level */}
                  <div className="flex items-center justify-between p-4 bg-brand-sand/30 rounded-lg">
                    <div className="flex items-center space-x-3">
                      <ChartBarIcon className="w-5 h-5 text-brand-soft-purple" />
                      <div>
                        <div className="font-medium text-gray-900">AI Collaboration Style</div>
                        <div className="text-sm text-gray-600">{getInvolvementLabel(profileData.involvement_level)}</div>
                      </div>
                    </div>
                  </div>

                  {/* Favorite Genre */}
                  <div className="flex items-center justify-between p-4 bg-brand-sand/30 rounded-lg">
                    <div className="flex items-center space-x-3">
                      <GlobeAltIcon className="w-5 h-5 text-brand-soft-purple" />
                      <div>
                        <div className="font-medium text-gray-900">Favorite Genre</div>
                        <div className="text-sm text-gray-600">{profileData.genre_preference}</div>
                      </div>
                    </div>
                  </div>

                  {/* Bio */}
                  {profileData.bio && (
                    <div className="p-4 bg-brand-sand/30 rounded-lg">
                      <div className="font-medium text-gray-900 mb-2">About</div>
                      <p className="text-sm text-gray-600 leading-relaxed">{profileData.bio}</p>
                    </div>
                  )}

                  {/* Writing Goals */}
                  {profileData.writing_goals && (
                    <div className="p-4 bg-brand-sand/30 rounded-lg">
                      <div className="font-medium text-gray-900 mb-2">Writing Goals</div>
                      <p className="text-sm text-gray-600 leading-relaxed">{profileData.writing_goals}</p>
                    </div>
                  )}
                </>
              ) : (
                <div className="text-center py-8">
                  <BookOpenIcon className="w-12 h-12 text-gray-300 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-gray-900 mb-2">Complete Your Profile</h3>
                  <p className="text-gray-600 mb-4">Tell us about your writing preferences to get a personalized experience.</p>
                  <Button onClick={() => window.location.href = '/dashboard'}>
                    Complete Setup
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>

              {/* Usage Stats */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center">
                    <ChartBarIcon className="w-5 h-5 mr-2 text-brand-soft-purple" />
                    Usage Stats
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center p-3 bg-brand-sand/20 rounded-lg">
                      <div className="text-lg font-bold text-brand-forest">--</div>
                      <div className="text-xs text-gray-600">Chapters Generated</div>
                    </div>
                    <div className="text-center p-3 bg-brand-sand/20 rounded-lg">
                      <div className="text-lg font-bold text-brand-forest">--</div>
                      <div className="text-xs text-gray-600">Words Written</div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Credits Tab */}
          <TabsContent value="credits">
            <div className="space-y-6">
              {/* Credit Balance Overview */}
              <div className="grid md:grid-cols-3 gap-6">
                <div className="md:col-span-2">
                  <CreditBalance variant="full" />
                </div>
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center text-sm">
                      <Zap className="w-4 h-4 mr-2 text-yellow-500" />
                      Quick Actions
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <Button variant="outline" className="w-full" disabled>
                      Purchase Credits
                      <span className="ml-2 text-xs opacity-60">(Soon)</span>
                    </Button>
                    <Button variant="ghost" className="w-full text-xs" onClick={() => loadTransactions()}>
                      Refresh Balance
                    </Button>
                  </CardContent>
                </Card>
              </div>

              {/* Transaction History */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center">
                    <ClockIcon className="w-5 h-5 mr-2 text-brand-soft-purple" />
                    Transaction History
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {transactionsLoading && transactions.length === 0 ? (
                    <div className="text-center py-8">
                      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-soft-purple mx-auto mb-4"></div>
                      <p className="text-gray-600">Loading transactions...</p>
                    </div>
                  ) : transactions.length === 0 ? (
                    <div className="text-center py-8">
                      <Zap className="w-12 h-12 text-gray-300 mx-auto mb-4" />
                      <h3 className="text-lg font-medium text-gray-900 mb-2">No transactions yet</h3>
                      <p className="text-gray-600">Your credit transactions will appear here.</p>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {transactions.map((transaction) => {
                        const typeInfo = formatTransactionType(transaction)
                        const Icon = typeInfo.icon
                        
                        return (
                          <div key={transaction.txn_id} className="flex items-center justify-between p-4 border border-gray-200 rounded-lg hover:bg-gray-50">
                            <div className="flex items-center space-x-3">
                              <div className={`w-8 h-8 rounded-full flex items-center justify-center ${typeInfo.bgColor}`}>
                                <Icon className={`w-4 h-4 ${typeInfo.color}`} />
                              </div>
                              <div>
                                <div className="font-medium text-gray-900">
                                  {formatTransactionReason(transaction.reason)}
                                </div>
                                <div className="text-sm text-gray-500">
                                  {new Date(transaction.created_at).toLocaleDateString()} at {new Date(transaction.created_at).toLocaleTimeString()}
                                </div>
                                {transaction.meta?.operation_type && (
                                  <div className="text-xs text-gray-400">
                                    {transaction.meta.operation_type} • {transaction.meta.model || 'N/A'}
                                  </div>
                                )}
                              </div>
                            </div>
                            <div className="text-right">
                              <div className={`font-medium ${typeInfo.color}`}>
                                {typeInfo.sign}{transaction.amount.toLocaleString()} credits
                              </div>
                              {transaction.balance_after !== undefined && (
                                <div className="text-sm text-gray-500">
                                  Balance: {transaction.balance_after.toLocaleString()}
                                </div>
                              )}
                              <Badge 
                                variant={transaction.status === 'completed' ? 'outline' : 'secondary'}
                                className="text-xs mt-1"
                              >
                                {transaction.status}
                              </Badge>
                            </div>
                          </div>
                        )
                      })}
                      
                      {hasMoreTransactions && (
                        <div className="text-center pt-4">
                          <Button 
                            variant="outline" 
                            onClick={() => loadTransactions(nextCursor)}
                            disabled={transactionsLoading}
                          >
                            {transactionsLoading ? 'Loading...' : 'Load More'}
                          </Button>
                        </div>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Account Tab */}
          <TabsContent value="account">
            <div className="max-w-2xl space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center">
                    <UserIcon className="w-5 h-5 mr-2 text-brand-soft-purple" />
                    Account Settings
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-3">
                    <div className="flex items-center justify-between p-3 bg-brand-sand/20 rounded-lg">
                      <div>
                        <div className="font-medium text-gray-900">Email</div>
                        <div className="text-sm text-gray-600">{user.emailAddresses[0]?.emailAddress}</div>
                      </div>
                      <Badge variant="outline">Verified</Badge>
                    </div>
                    
                    <div className="flex items-center justify-between p-3 bg-brand-sand/20 rounded-lg">
                      <div>
                        <div className="font-medium text-gray-900">Account Type</div>
                        <div className="text-sm text-gray-600">Beta User</div>
                      </div>
                      <Badge className="bg-brand-soft-purple text-white">Free</Badge>
                    </div>

                    <div className="pt-4 border-t border-gray-200">
                      <Button variant="outline" className="w-full" disabled>
                        <span>Manage Billing</span>
                        <span className="ml-2 text-xs opacity-60">(Coming Soon)</span>
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>
        </Tabs>

        {/* Success Message */}
        {profileData && (
          <Card className="mt-8 bg-green-50 border-green-200">
            <CardContent className="p-6">
              <div className="flex items-center space-x-3">
                <div className="w-8 h-8 bg-green-100 rounded-full flex items-center justify-center">
                  <span className="text-green-600 text-xl">✓</span>
                </div>
                <div>
                  <h3 className="font-medium text-green-900">Profile Complete!</h3>
                  <p className="text-sm text-green-700">
                    Your writing preferences are set up and ready to guide your AI collaboration.
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}