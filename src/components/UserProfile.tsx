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

interface UserProfileData {
  name: string
  email: string
  bio?: string
  genre_preference?: string
  writing_experience?: string
  timezone?: string
  preferred_word_count?: number
  quality_strictness?: 'lenient' | 'standard' | 'strict'
  auto_backup_enabled?: boolean
  email_notifications?: boolean
}

export default function UserProfile() {
  const { user, isLoaded } = useUser()
  const { getToken } = useAuth()
  const [profile, setProfile] = useState<UserProfileData>({
    name: '',
    email: '',
    bio: '',
    genre_preference: 'Fiction',
    writing_experience: 'beginner',
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    preferred_word_count: 2000,
    quality_strictness: 'standard',
    auto_backup_enabled: true,
    email_notifications: true
  })
  const [isLoading, setIsLoading] = useState(false)
  const [isEditing, setIsEditing] = useState(false)

  useEffect(() => {
    if (isLoaded && user) {
      setProfile(prev => ({
        ...prev,
        name: user.fullName || '',
        email: user.primaryEmailAddress?.emailAddress || ''
      }))
      loadUserProfile()
    }
  }, [isLoaded, user])

  const loadUserProfile = async () => {
    if (!getToken) return
    
    try {
      const response = await fetch('/api/user/profile', {
        headers: {
          'Authorization': `Bearer ${await getToken()}`
        }
      })
      
      if (response.ok) {
        const data = await response.json()
        setProfile(prev => ({ ...prev, ...data }))
      }
    } catch (error) {
      console.error('Failed to load user profile:', error)
    }
  }

  const saveProfile = async () => {
    if (!user || !getToken) return
    
    setIsLoading(true)
    try {
      const response = await fetch('/api/user/profile', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${await getToken()}`
        },
        body: JSON.stringify(profile)
      })

      if (response.ok) {
        toast({
          title: "Profile Updated",
          description: "Your profile has been saved successfully."
        })
        setIsEditing(false)
      } else {
        throw new Error('Failed to save profile')
      }
    } catch (error) {
      console.error('Failed to save profile:', error)
      toast({
        title: "Error",
        description: "Failed to save profile. Please try again.",
        variant: "destructive"
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleInputChange = (field: keyof UserProfileData, value: any) => {
    setProfile(prev => ({ ...prev, [field]: value }))
  }

  if (!isLoaded) {
    return <div className="animate-pulse">Loading profile...</div>
  }

  return (
    <Card className="max-w-2xl mx-auto">
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          User Profile
          <Button
            variant={isEditing ? "secondary" : "outline"}
            onClick={() => setIsEditing(!isEditing)}
          >
            {isEditing ? 'Cancel' : 'Edit'}
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Basic Information */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="name">Full Name</Label>
            <Input
              id="name"
              value={profile.name}
              onChange={(e) => handleInputChange('name', e.target.value)}
              disabled={!isEditing}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              value={profile.email}
              disabled={true}
              className="bg-gray-50"
            />
          </div>
        </div>

        {/* Bio */}
        <div className="space-y-2">
          <Label htmlFor="bio">Bio</Label>
          <Textarea
            id="bio"
            placeholder="Tell us about yourself and your writing..."
            value={profile.bio || ''}
            onChange={(e) => handleInputChange('bio', e.target.value)}
            disabled={!isEditing}
            rows={3}
          />
        </div>

        {/* Writing Preferences */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="genre">Preferred Genre</Label>
            <select
              value={profile.genre_preference}
              onChange={(e) => handleInputChange('genre_preference', e.target.value)}
              disabled={!isEditing}
              className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
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
            </select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="experience">Writing Experience</Label>
            <select
              value={profile.writing_experience}
              onChange={(e) => handleInputChange('writing_experience', e.target.value)}
              disabled={!isEditing}
              className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <option value="beginner">Beginner</option>
              <option value="intermediate">Intermediate</option>
              <option value="advanced">Advanced</option>
              <option value="professional">Professional</option>
            </select>
          </div>
        </div>

        {/* System Preferences */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="word-count">Preferred Word Count per Chapter</Label>
            <Input
              id="word-count"
              type="number"
              min="500"
              max="5000"
              step="100"
              value={profile.preferred_word_count}
              onChange={(e) => handleInputChange('preferred_word_count', parseInt(e.target.value))}
              disabled={!isEditing}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="quality">Quality Strictness</Label>
            <select
              value={profile.quality_strictness}
              onChange={(e) => handleInputChange('quality_strictness', e.target.value as 'lenient' | 'standard' | 'strict')}
              disabled={!isEditing}
              className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <option value="lenient">Lenient</option>
              <option value="standard">Standard</option>
              <option value="strict">Strict</option>
            </select>
          </div>
        </div>

        {/* Notifications */}
        <div className="space-y-4">
          <h3 className="text-lg font-semibold">Preferences</h3>
          <div className="space-y-3">
            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="auto-backup"
                checked={profile.auto_backup_enabled}
                onChange={(e) => handleInputChange('auto_backup_enabled', e.target.checked)}
                disabled={!isEditing}
                className="rounded"
              />
              <Label htmlFor="auto-backup">Enable auto-backup</Label>
            </div>
            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="email-notifications"
                checked={profile.email_notifications}
                onChange={(e) => handleInputChange('email_notifications', e.target.checked)}
                disabled={!isEditing}
                className="rounded"
              />
              <Label htmlFor="email-notifications">Email notifications</Label>
            </div>
          </div>
        </div>

        {/* Save Button */}
        {isEditing && (
          <div className="flex justify-end space-x-2">
            <Button variant="outline" onClick={() => setIsEditing(false)}>
              Cancel
            </Button>
            <Button onClick={saveProfile} disabled={isLoading}>
              {isLoading ? 'Saving...' : 'Save Profile'}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
} 