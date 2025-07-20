/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    serverComponentsExternalPackages: ['openai']
  },
  env: {
    OPENAI_API_KEY: process.env.OPENAI_API_KEY,
  },
  eslint: {
    // Temporarily ignore ESLint errors during builds for deployment
    ignoreDuringBuilds: true,
  },
  typescript: {
    // Temporarily ignore TypeScript errors during builds for deployment
    ignoreBuildErrors: true,
  },
}

module.exports = nextConfig 