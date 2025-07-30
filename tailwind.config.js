/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  safelist: [
    // Protect dynamic brand color classes from purging
    {
      pattern: /(hover:)?(bg|text|border)-brand-(soft-purple|leaf|sand|forest|lavender|orange|beige|off-white|ink-blue|blush-orange)(\/\d+)?/,
    },
    // Protect opacity variants
    'bg-brand-soft-purple/10',
    'bg-brand-soft-purple/20',
    'bg-brand-leaf/10',
    'bg-brand-leaf/20',
    'bg-brand-leaf/30',
    'bg-brand-sand/20',
    'bg-brand-sand/30',
    // Auto-Complete specific colors
    'bg-brand-forest',
    'bg-brand-forest/90',
    'bg-brand-lavender',
    'hover:bg-brand-forest/90',
    'hover:bg-brand-lavender',
    // Scale and shadow variants
    'hover:scale-105',
    'shadow-lg',
    'hover:shadow-xl',
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          800: '#1e40af',
          900: '#1e3a8a',
          950: '#172554',
        },
        brand: {
          'soft-purple': '#9BA4FF',
          'leaf': '#9ED2C6',
          'sand': '#F8F4EC',
          // WriterBloom specific palette
          'lavender': '#B18EFF',
          'forest': '#1F4737',
          'beige': '#FAF8F3',
          'orange': '#FF8A47',
          'off-white': '#FEFDFB',
          // New immersive hero colors
          'ink-blue': '#363B6C',
          'blush-orange': '#FF9A6B',
        },
      },
      fontSize: {
        'display-lg': ['3.5rem', { lineHeight: '1.1', fontWeight: '700' }],
        'display-md': ['2.5rem', { lineHeight: '1.2', fontWeight: '600' }], 
        'display-sm': ['2rem', { lineHeight: '1.25', fontWeight: '600' }],
      },
      animation: {
        'fade-in': 'fadeIn 0.5s ease-in-out',
        'fade-in-up': 'fadeInUp 0.6s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'shimmer': 'shimmer 8s linear infinite',
        'float': 'float 6s ease-in-out infinite',
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
      },
      keyframes: {
        fadeInUp: {
          '0%': { opacity: '0', transform: 'translateY(30px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        shimmer: {
          '0%': { transform: 'translateX(-100%)' },
          '50%': { transform: 'translateX(100%)' },
          '100%': { transform: 'translateX(300%)' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-10px)' },
        },
      },
      screens: {
        'reduce-motion': { 'raw': '(prefers-reduced-motion: reduce)' },
      },
    },
  },
  plugins: [],
} 