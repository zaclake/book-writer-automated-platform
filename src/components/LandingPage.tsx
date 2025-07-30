'use client'

import React from 'react'
import { useRouter } from 'next/navigation'
import Image from 'next/image'
import { UI_STRINGS } from '@/lib/strings'

const LandingPage: React.FC = () => {
  const router = useRouter()

  const { landing } = UI_STRINGS

  return (
    <div className="min-h-screen bg-gradient-to-br from-brand-sand via-white to-brand-leaf/10">
      {/* Hero Section */}
      <section className="relative overflow-hidden">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-20 pb-24">
          <div className="text-center">
            {/* Logo */}
            <div className="flex justify-center mb-8">
              <Image
                src="/logo.png"
                alt="WriterBloom"
                width={80}
                height={80}
                className="w-20 h-20 object-contain"
                priority
              />
            </div>

            {/* Hero Text */}
            <h1 className="text-4xl md:text-6xl font-bold text-gray-900 mb-6 leading-tight">
              <span className="text-brand-soft-purple block">WriterBloom</span>
              <span className="text-3xl md:text-5xl font-light block">
                {landing.tagline}
              </span>
            </h1>
            
            <p className="text-xl text-gray-600 mb-8 max-w-3xl mx-auto leading-relaxed">
              {landing.subtitle}
            </p>

            {/* CTA Buttons */}
            <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
              <button
                onClick={() => router.push('/sign-up')}
                className="bg-brand-soft-purple text-white px-8 py-4 rounded-lg text-lg font-medium hover:bg-opacity-90 transition-all transform hover:scale-105 shadow-lg"
              >
                {UI_STRINGS.actions.getStarted}
              </button>
              <button
                onClick={() => router.push('/sign-in')}
                className="border-2 border-brand-soft-purple text-brand-soft-purple px-8 py-4 rounded-lg text-lg font-medium hover:bg-brand-soft-purple hover:text-white transition-all"
              >
                {UI_STRINGS.actions.takeTour}
              </button>
            </div>
          </div>
        </div>

        {/* Decorative Elements */}
        <div className="absolute top-1/4 left-10 text-6xl opacity-10 rotate-12" aria-hidden="true" role="presentation">🌱</div>
        <div className="absolute bottom-1/4 right-10 text-5xl opacity-10 -rotate-12" aria-hidden="true" role="presentation">📚</div>
        <div className="absolute top-1/3 right-1/4 text-4xl opacity-10 rotate-45" aria-hidden="true" role="presentation">✨</div>
      </section>

      {/* How It Works Section */}
      <section className="py-20 bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold text-gray-900 mb-4">
              {landing.howItWorks.title}
            </h2>
            <p className="text-xl text-gray-600 max-w-2xl mx-auto">
              From the spark of an idea to published masterpiece—we'll guide you every step of the way.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-12">
            {landing.howItWorks.steps.map((step, index) => (
              <div key={index} className="text-center group">
                <div className="relative mb-6">
                  <div className="w-20 h-20 bg-gradient-to-br from-brand-soft-purple to-brand-leaf rounded-full flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform duration-300">
                    <span className="text-3xl text-white font-bold">{index + 1}</span>
                  </div>
                  {index < 2 && (
                    <div className="hidden md:block absolute top-10 left-full w-full h-0.5 bg-gradient-to-r from-brand-soft-purple to-brand-leaf opacity-30"></div>
                  )}
                </div>
                <h3 className="text-xl font-semibold text-gray-900 mb-3">{step.title}</h3>
                <p className="text-gray-600 leading-relaxed">{step.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features Preview */}
      <section className="py-20 bg-brand-sand/30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold text-gray-900 mb-4">
              Everything You Need to Bloom
            </h2>
            <p className="text-xl text-gray-600 max-w-2xl mx-auto">
              Powerful tools designed to nurture your creativity and guide your writing journey.
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
            {[
              {
                icon: '🧠',
                title: 'AI Writing Assistant',
                description: 'Get intelligent suggestions and overcome writer\'s block with gentle AI guidance.'
              },
              {
                icon: '📊',
                title: 'Progress Tracking',
                description: 'Watch your story bloom with visual progress meters and milestone celebrations.'
              },
              {
                icon: '🎨',
                title: 'Cover Art Generator',
                description: 'Create stunning book covers that capture the essence of your story.'
              },
              {
                icon: '📚',
                title: 'Publishing Tools',
                description: 'Transform your manuscript into professional EPUB, PDF, and print-ready formats.'
              },
              {
                icon: '🌱',
                title: 'Gentle Guidance',
                description: 'Receive encouraging nudges and supportive feedback throughout your journey.'
              },
              {
                icon: '✨',
                title: 'Quality Enhancement',
                description: 'Polish your prose with intelligent editing suggestions and quality assessments.'
              }
            ].map((feature, index) => (
              <div key={index} className="bg-white p-6 rounded-xl shadow-sm hover:shadow-md transition-shadow border border-gray-100">
                <div className="text-4xl mb-4">{feature.icon}</div>
                <h3 className="text-lg font-semibold text-gray-900 mb-2">{feature.title}</h3>
                <p className="text-gray-600">{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section className="py-20 bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-bold text-gray-900 mb-4">
              {landing.testimonials.title}
            </h2>
          </div>

          <div className="grid md:grid-cols-2 gap-8 max-w-4xl mx-auto">
            {landing.testimonials.quotes.map((testimonial, index) => (
              <div key={index} className="bg-brand-sand/20 p-8 rounded-xl">
                <div className="text-brand-soft-purple text-4xl mb-4">"</div>
                <p className="text-lg text-gray-700 mb-4 italic leading-relaxed">
                  {testimonial.text}
                </p>
                <p className="text-brand-soft-purple font-medium">— {testimonial.author}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="py-20 bg-gradient-to-r from-brand-soft-purple to-brand-leaf">
        <div className="max-w-4xl mx-auto text-center px-4 sm:px-6 lg:px-8">
          <h2 className="text-3xl md:text-4xl font-bold text-white mb-6">
            Ready to Start Your Writing Journey?
          </h2>
          <p className="text-xl text-white/90 mb-8">
            Join thousands of writers who are already blooming with WriterBloom.
          </p>
          <button
            onClick={() => router.push('/sign-up')}
            className="bg-white text-brand-soft-purple px-8 py-4 rounded-lg text-lg font-medium hover:bg-gray-50 transition-all transform hover:scale-105 shadow-lg"
          >
            {UI_STRINGS.actions.getStarted}
          </button>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-gray-900 text-white py-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col md:flex-row justify-between items-center">
            <div className="flex items-center space-x-3 mb-4 md:mb-0">
              <Image
                src="/logo-bw.png"
                alt="WriterBloom"
                width={32}
                height={32}
                className="w-8 h-8 object-contain"
              />
              <span className="font-semibold text-lg">WriterBloom</span>
            </div>
            <div className="text-gray-400 text-center md:text-right">
              <p>&copy; 2024 WriterBloom. Nurturing creativity, one story at a time.</p>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}

export default LandingPage 