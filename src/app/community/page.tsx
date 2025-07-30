'use client'

import React from 'react'
import { UI_STRINGS } from '@/lib/strings'

export default function CommunityPage() {
  return (
    <div className="min-h-screen bg-brand-sand py-12">
      <div className="max-w-4xl mx-auto px-6 text-center">
        {/* Coming Soon Illustration */}
        <div className="mb-8">
          <div className="w-32 h-32 mx-auto bg-gradient-to-br from-brand-soft-purple/20 to-brand-leaf/20 rounded-full flex items-center justify-center mb-6">
            <span className="text-6xl">🌱</span>
          </div>
          <div className="relative">
            <div className="absolute -top-4 -left-8 w-8 h-8 bg-brand-leaf/30 rounded-full flex items-center justify-center float-gentle">
              <span className="text-lg">💬</span>
            </div>
            <div className="absolute -top-2 -right-6 w-6 h-6 bg-brand-soft-purple/30 rounded-full flex items-center justify-center float-gentle" style={{animationDelay: '1s'}}>
              <span className="text-sm">📝</span>
            </div>
          </div>
        </div>

        {/* Content */}
        <h1 className="text-4xl font-bold text-gray-900 mb-4">
          {UI_STRINGS.navigation.community} Coming Soon
        </h1>
        
        <p className="text-xl text-gray-600 mb-8 leading-relaxed">
          We're building a nurturing space for writers to connect, learn, and grow together. 
          Your supportive community of fellow creators is taking shape!
        </p>

        {/* Features Preview */}
        <div className="grid md:grid-cols-3 gap-6 max-w-3xl mx-auto mb-8">
          <div className="bg-white p-6 rounded-xl border border-gray-200">
            <div className="text-3xl mb-3">📧</div>
            <h3 className="font-semibold text-gray-900 mb-2">Contact & Support</h3>
            <p className="text-sm text-gray-600">Get help from our friendly team whenever you need it.</p>
          </div>
          
          <div className="bg-white p-6 rounded-xl border border-gray-200">
            <div className="text-3xl mb-3">❓</div>
            <h3 className="font-semibold text-gray-900 mb-2">FAQs & Guides</h3>
            <p className="text-sm text-gray-600">Find answers and learn new techniques to improve your craft.</p>
          </div>

          <div className="bg-white p-6 rounded-xl border border-gray-200">
            <div className="text-3xl mb-3">📰</div>
            <h3 className="font-semibold text-gray-900 mb-2">Writing Blog</h3>
            <p className="text-sm text-gray-600">Tips, inspiration, and stories from the writing community.</p>
          </div>
        </div>

        {/* Temporary Contact Info */}
        <div className="bg-white rounded-xl p-8 border border-gray-200">
          <h3 className="text-lg font-semibold text-gray-900 mb-3">
            Need help right now?
          </h3>
          <p className="text-gray-600 mb-4">
            While we're building the full community space, we're here to help!
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <button
              onClick={() => window.location.href = '/dashboard'}
              className="bg-brand-soft-purple text-white px-6 py-3 rounded-lg font-medium hover:bg-opacity-90 transition-all"
            >
              Continue Writing
            </button>
            <button
              onClick={() => window.location.href = 'mailto:support@writerbloom.com'}
              className="border-2 border-brand-soft-purple text-brand-soft-purple px-6 py-3 rounded-lg font-medium hover:bg-brand-soft-purple hover:text-white transition-all"
            >
              Get Support
            </button>
          </div>
        </div>
      </div>
    </div>
  )
} 