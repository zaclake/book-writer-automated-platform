'use client'

import { useState, useEffect } from 'react'
import { useAuth, useUser } from '@clerk/nextjs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
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
  HeartIcon
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
  const [profileData, setProfileData] = useState<UserProfileData | null>(null)
  const [usageData, setUsageData] = useState<UsageData | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [isEditing, setIsEditing] = useState(false)

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
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
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

          {/* Account & Billing */}
          <div className="space-y-6">
            {/* Credits & Usage */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center">
                  <CreditCardIcon className="w-5 h-5 mr-2 text-brand-soft-purple" />
                  Credits & Usage
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {/* Credits Display - Placeholder for future feature */}
                  <div className="flex items-center justify-between p-4 bg-gradient-to-r from-brand-lavender/10 to-brand-soft-purple/10 rounded-lg border border-brand-lavender/20">
                    <div>
                      <div className="font-medium text-gray-900">Available Credits</div>
                      <div className="text-2xl font-bold text-brand-soft-purple">∞</div>
                      <div className="text-xs text-gray-500">Unlimited during beta</div>
                    </div>
                    <Button variant="outline" disabled className="opacity-50">
                      Add Credits
                      <span className="ml-2 text-xs">(Coming Soon)</span>
                    </Button>
                  </div>

                  {/* Usage Stats - Placeholder */}
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
                </div>
              </CardContent>
            </Card>

            {/* Account Settings */}
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
        </div>

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