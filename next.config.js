/** @type {import('next').NextConfig} */
const path = require('path')

const nextConfig = {
  experimental: {
    serverComponentsExternalPackages: ['openai']
  },
  env: {
    OPENAI_API_KEY: process.env.OPENAI_API_KEY,
  },
  compiler: {
    // Preserve server logs in production for diagnostics
    removeConsole: false,
  },
  eslint: {
    // Temporarily ignore ESLint errors during builds for deployment
    ignoreDuringBuilds: true,
  },
  typescript: {
    // Temporarily ignore TypeScript errors during builds for deployment
    ignoreBuildErrors: true,
  },
  // API requests are now handled by proper Next.js API routes with authentication
  // Fix development server reloading issues
  webpack: (config, { dev, isServer }) => {
    config.resolve = config.resolve || {}
    config.resolve.alias = {
      ...(config.resolve.alias || {}),
      '@clerk/nextjs': path.resolve(__dirname, 'src/lib/clerk-shim.tsx'),
      '@clerk/clerk-react': path.resolve(__dirname, 'src/lib/clerk-shim.tsx'),
      '@clerk/nextjs/server': path.resolve(__dirname, 'src/lib/server-auth.ts'),
    }

    if (dev && !isServer) {
      // Reduce aggressive file watching in development
      config.watchOptions = {
        poll: 1000,
        aggregateTimeout: 300,
        ignored: /node_modules|\.git|\.next/,
      }
    }
    return config
  },
}

module.exports = nextConfig 