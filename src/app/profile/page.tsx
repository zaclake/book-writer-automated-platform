'use client'

import UserProfile from '@/components/UserProfile'

export default function ProfilePage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Profile</h1>
        <p className="text-gray-600 mt-1">
          Manage your profile and writing preferences
        </p>
      </div>

      <UserProfile />
    </div>
  )
} 