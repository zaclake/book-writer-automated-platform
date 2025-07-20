'use client'

import React, { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useUser, useAuth } from '@clerk/nextjs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { toast } from '@/components/ui/use-toast'

interface OnboardingData {
  purpose: 'personal' | 'commercial' | 'educational'
  involvement_level: 'hands_off' | 'balanced' | 'hands_on'
  writing_experience: 'beginner' | 'intermediate' | 'advanced' | 'professional'
  genre_preference: string
  bio?: string
  writing_goals?: string
}

interface OnboardingFlowProps {
  onComplete: () => void
}

const OnboardingFlow: React.FC<OnboardingFlowProps> = ({ onComplete }) => {
  const { user, isLoaded } = useUser()
  const { getToken } = useAuth()
  const [currentStep, setCurrentStep] = useState(1)
  const [isLoading, setIsLoading] = useState(false)
  const [onboardingData, setOnboardingData] = useState<OnboardingData>({
    purpose: 'personal',
    involvement_level: 'balanced',
    writing_experience: 'beginner',
    genre_preference: 'Fiction',
    bio: '',
    writing_goals: ''
  })

  const totalSteps = 4

  const handleNext = () => {
    if (currentStep < totalSteps) {
      setCurrentStep(currentStep + 1)
    }
  }

  const handlePrevious = () => {
    if (currentStep > 1) {
      setCurrentStep(currentStep - 1)
    }
  }

  const handleComplete = async () => {
    if (!user || !getToken) return

    setIsLoading(true)
    try {
      const response = await fetch('/api/users/v2/onboarding', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${await getToken()}`
        },
        body: JSON.stringify(onboardingData)
      })

      if (response.ok) {
        toast({
          title: "Welcome!",
          description: "Your profile has been set up successfully."
        })
        onComplete()
      } else {
        throw new Error('Failed to complete onboarding')
      }
    } catch (error) {
      console.error('Onboarding error:', error)
      toast({
        title: "Error",
        description: "Failed to complete setup. Please try again.",
        variant: "destructive"
      })
    } finally {
      setIsLoading(false)
    }
  }

  const updateData = (field: keyof OnboardingData, value: any) => {
    setOnboardingData(prev => ({ ...prev, [field]: value }))
  }

  if (!isLoaded) {
    return <div className="animate-pulse">Loading...</div>
  }

  return (
    <div className="max-w-2xl mx-auto p-6">
      {/* Progress bar */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-2xl font-bold">Welcome to Writer Bloom</h2>
          <span className="text-sm text-gray-500">Step {currentStep} of {totalSteps}</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div 
            className="bg-blue-600 h-2 rounded-full transition-all duration-300"
            style={{ width: `${(currentStep / totalSteps) * 100}%` }}
          />
        </div>
      </div>

      <Card>
        <CardContent className="p-6">
          {/* Step 1: Purpose Selection */}
          {currentStep === 1 && (
            <div className="space-y-6">
              <div className="text-center mb-6">
                <CardTitle className="text-xl mb-2">What brings you to Writer Bloom?</CardTitle>
                <p className="text-gray-600">This helps us tailor your writing experience.</p>
              </div>
              
              <div className="space-y-4">
                {[
                  {
                    id: 'personal',
                    title: 'Personal Projects',
                    description: 'Writing for fun, creativity, or personal fulfillment'
                  },
                  {
                    id: 'commercial',
                    title: 'Commercial Publishing',
                    description: 'Planning to publish and sell your work'
                  },
                  {
                    id: 'educational',
                    title: 'Learning & Education',
                    description: 'Studying writing craft or teaching others'
                  }
                ].map((option) => (
                  <label
                    key={option.id}
                    className={`block p-4 border rounded-lg cursor-pointer transition-all ${
                      onboardingData.purpose === option.id
                        ? 'border-blue-500 bg-blue-50'
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <input
                      type="radio"
                      name="purpose"
                      value={option.id}
                      checked={onboardingData.purpose === option.id}
                      onChange={(e) => updateData('purpose', e.target.value as any)}
                      className="sr-only"
                    />
                    <div className="font-semibold">{option.title}</div>
                    <div className="text-sm text-gray-600">{option.description}</div>
                  </label>
                ))}
              </div>
            </div>
          )}

          {/* Step 2: Involvement Level */}
          {currentStep === 2 && (
            <div className="space-y-6">
              <div className="text-center mb-6">
                <CardTitle className="text-xl mb-2">How involved do you want to be?</CardTitle>
                <p className="text-gray-600">This affects how the AI assists with your writing.</p>
              </div>

              <div className="space-y-6">
                <div className="space-y-4">
                  {[
                    {
                      id: 'hands_off',
                      title: 'Hands-Off',
                      description: 'Let AI do most of the work. Minimal input required.',
                      percentage: '20%'
                    },
                    {
                      id: 'balanced',
                      title: 'Balanced',
                      description: 'Collaborative approach. You guide, AI executes.',
                      percentage: '50%'
                    },
                    {
                      id: 'hands_on',
                      title: 'Hands-On', 
                      description: 'You lead the creative process. AI provides support.',
                      percentage: '80%'
                    }
                  ].map((option) => (
                    <label
                      key={option.id}
                      className={`block p-4 border rounded-lg cursor-pointer transition-all ${
                        onboardingData.involvement_level === option.id
                          ? 'border-blue-500 bg-blue-50'
                          : 'border-gray-200 hover:border-gray-300'
                      }`}
                    >
                      <input
                        type="radio"
                        name="involvement_level"
                        value={option.id}
                        checked={onboardingData.involvement_level === option.id}
                        onChange={(e) => updateData('involvement_level', e.target.value as any)}
                        className="sr-only"
                      />
                      <div className="flex justify-between items-start">
                        <div className="flex-1">
                          <div className="font-semibold">{option.title}</div>
                          <div className="text-sm text-gray-600">{option.description}</div>
                        </div>
                        <div className="text-sm font-medium text-blue-600">{option.percentage} You</div>
                      </div>
                    </label>
                  ))}
                </div>

                {/* Visual slider representation */}
                <div className="mt-6 p-4 bg-gray-50 rounded-lg">
                  <div className="text-sm text-gray-600 mb-2">Your Writing Input Level</div>
                  <div className="w-full bg-gray-200 rounded-full h-3 relative">
                    <div 
                      className="bg-blue-600 h-3 rounded-full transition-all duration-300"
                      style={{ 
                        width: onboardingData.involvement_level === 'hands_off' ? '20%' :
                               onboardingData.involvement_level === 'balanced' ? '50%' : '80%'
                      }}
                    />
                    <div className="flex justify-between text-xs text-gray-500 mt-1">
                      <span>AI-Driven</span>
                      <span>Collaborative</span>
                      <span>Author-Led</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Step 3: Writing Experience & Preferences */}
          {currentStep === 3 && (
            <div className="space-y-6">
              <div className="text-center mb-6">
                <CardTitle className="text-xl mb-2">Tell us about your writing</CardTitle>
                <p className="text-gray-600">This helps us customize our assistance.</p>
              </div>

              <div className="grid gap-6">
                <div className="space-y-2">
                  <Label htmlFor="experience">Writing Experience</Label>
                  <select
                    id="experience"
                    value={onboardingData.writing_experience}
                    onChange={(e) => updateData('writing_experience', e.target.value as any)}
                    className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  >
                    <option value="beginner">Beginner - New to writing</option>
                    <option value="intermediate">Intermediate - Some experience</option>
                    <option value="advanced">Advanced - Experienced writer</option>
                    <option value="professional">Professional - Published author</option>
                  </select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="genre">Favorite Genre</Label>
                  <select
                    id="genre"
                    value={onboardingData.genre_preference}
                    onChange={(e) => updateData('genre_preference', e.target.value)}
                    className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  >
                    <option value="Fiction">Fiction</option>
                    <option value="Non-Fiction">Non-Fiction</option>
                    <option value="Mystery">Mystery</option>
                    <option value="Romance">Romance</option>
                    <option value="Science Fiction">Science Fiction</option>
                    <option value="Fantasy">Fantasy</option>
                    <option value="Thriller">Thriller</option>
                    <option value="Horror">Horror</option>
                    <option value="Literary">Literary</option>
                    <option value="Historical">Historical</option>
                    <option value="Young Adult">Young Adult</option>
                  </select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="bio">About You (Optional)</Label>
                  <Textarea
                    id="bio"
                    placeholder="Tell us a bit about yourself and your writing background..."
                    value={onboardingData.bio}
                    onChange={(e) => updateData('bio', e.target.value)}
                    rows={3}
                  />
                </div>
              </div>
            </div>
          )}

          {/* Step 4: Writing Goals */}
          {currentStep === 4 && (
            <div className="space-y-6">
              <div className="text-center mb-6">
                <CardTitle className="text-xl mb-2">What are your writing goals?</CardTitle>
                <p className="text-gray-600">Help us understand what you want to achieve.</p>
              </div>

              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="goals">Writing Goals (Optional)</Label>
                  <Textarea
                    id="goals"
                    placeholder="What do you hope to accomplish with your writing? (e.g., complete a novel, improve craft, publish a book series...)"
                    value={onboardingData.writing_goals}
                    onChange={(e) => updateData('writing_goals', e.target.value)}
                    rows={4}
                  />
                </div>

                <div className="p-4 bg-blue-50 rounded-lg">
                  <h4 className="font-semibold text-blue-900 mb-2">Your Setup Summary</h4>
                  <div className="text-sm text-blue-800 space-y-1">
                    <div><strong>Purpose:</strong> {onboardingData.purpose.charAt(0).toUpperCase() + onboardingData.purpose.slice(1)}</div>
                    <div><strong>Involvement:</strong> {onboardingData.involvement_level.replace('_', ' ').charAt(0).toUpperCase() + onboardingData.involvement_level.replace('_', ' ').slice(1)}</div>
                    <div><strong>Experience:</strong> {onboardingData.writing_experience.charAt(0).toUpperCase() + onboardingData.writing_experience.slice(1)}</div>
                    <div><strong>Genre:</strong> {onboardingData.genre_preference}</div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Navigation */}
          <div className="flex justify-between mt-8 pt-6 border-t">
            <Button
              variant="outline"
              onClick={handlePrevious}
              disabled={currentStep === 1}
            >
              Previous
            </Button>

            {currentStep < totalSteps ? (
              <Button onClick={handleNext}>
                Next
              </Button>
            ) : (
              <Button onClick={handleComplete} disabled={isLoading}>
                {isLoading ? 'Setting up...' : 'Complete Setup'}
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

export default OnboardingFlow 