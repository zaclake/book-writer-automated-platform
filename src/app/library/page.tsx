'use client'

import React from 'react'
import { UI_STRINGS } from '@/lib/strings'

export default function LibraryPage() {
  return (
    <div className="min-h-screen bg-brand-sand py-12">
      <div className="max-w-4xl mx-auto px-6 text-center">
        {/* Coming Soon Illustration */}
        <div className="mb-8">
          <div className="w-32 h-32 mx-auto bg-gradient-to-br from-brand-soft-purple/20 to-brand-leaf/20 rounded-full flex items-center justify-center mb-6">
            <span className="text-6xl">📚</span>
          </div>
          <div className="relative">
            <div className="absolute -top-4 -left-8 w-8 h-8 bg-brand-leaf/30 rounded-full flex items-center justify-center float-gentle">
              <span className="text-lg">✨</span>
            </div>
            <div className="absolute -top-2 -right-6 w-6 h-6 bg-brand-soft-purple/30 rounded-full flex items-center justify-center float-gentle" style={{animationDelay: '1s'}}>
              <span className="text-sm">📖</span>
            </div>
          </div>
        </div>

        {/* Content */}
        <h1 className="text-4xl font-bold text-gray-900 mb-4">
          {UI_STRINGS.navigation.library} Coming Soon
        </h1>
        
        <p className="text-xl text-gray-600 mb-8 leading-relaxed">
          We're crafting a beautiful space where you can publish your finished journeys 
          and discover inspiring stories from fellow writers in our community.
        </p>

        {/* Features Preview */}
        <div className="grid md:grid-cols-2 gap-6 max-w-2xl mx-auto mb-8">
          <div className="bg-white p-6 rounded-xl border border-gray-200">
            <div className="text-3xl mb-3">📖</div>
            <h3 className="font-semibold text-gray-900 mb-2">Kindle-Style Reader</h3>
            <p className="text-sm text-gray-600">Read your published works and community stories with our built-in reader.</p>
          </div>
          
          <div className="bg-white p-6 rounded-xl border border-gray-200">
            <div className="text-3xl mb-3">🌟</div>
            <h3 className="font-semibold text-gray-900 mb-2">Publishing Platform</h3>
            <p className="text-sm text-gray-600">Share your completed journeys with readers who love great stories.</p>
          </div>
        </div>

        {/* Call to Action */}
        <div className="bg-white rounded-xl p-8 border border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900 mb-3">
            Want to be notified when it's ready?
          </h3>
          <p className="text-gray-600 mb-4">
            Keep writing your current journeys, and we'll let you know when the Library blooms!
          </p>
          <button
            onClick={() => window.location.href = '/dashboard'}
            className="bg-brand-soft-purple text-white px-6 py-3 rounded-lg font-medium hover:bg-opacity-90 transition-all"
          >
            Continue Your Journey
          </button>
        </div>
      </div>
    </div>
  )
} 