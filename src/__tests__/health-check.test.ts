/**
 * Health check smoke test for backend connectivity
 * This test should run before frontend deployments to ensure backend is accessible
 */

import { describe, it, expect, beforeAll } from '@jest/globals'

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || process.env.BACKEND_URL || 'http://localhost:8000'
const HEALTH_TIMEOUT = 10000 // 10 seconds

describe('Backend Health Check', () => {
  beforeAll(() => {
    console.log(`Testing backend health at: ${BACKEND_URL}`)
  })

  it('should connect to backend health endpoint', async () => {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), HEALTH_TIMEOUT)

    try {
      const response = await fetch(`${BACKEND_URL}/health`, {
        method: 'GET',
        signal: controller.signal,
        headers: {
          'Accept': 'application/json'
        }
      })

      clearTimeout(timeoutId)

      expect(response.status).toBe(200)
      
      const data = await response.json()
      expect(data).toHaveProperty('status')
      expect(data.status).toBe('healthy')
      
      console.log('✅ Backend health check passed:', data)
    } catch (error) {
      clearTimeout(timeoutId)
      
      if (error instanceof Error && error.name === 'AbortError') {
        throw new Error(`Backend health check timed out after ${HEALTH_TIMEOUT}ms`)
      }
      
      throw new Error(`Backend health check failed: ${error}`)
    }
  }, HEALTH_TIMEOUT + 1000)

  it('should have credits system available', async () => {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), HEALTH_TIMEOUT)

    try {
      const response = await fetch(`${BACKEND_URL}/v2/credits/health`, {
        method: 'GET',
        signal: controller.signal,
        headers: {
          'Accept': 'application/json'
        }
      })

      clearTimeout(timeoutId)

      expect(response.status).toBe(200)
      
      const data = await response.json()
      expect(data).toHaveProperty('status')
      expect(['healthy', 'degraded']).toContain(data.status)
      expect(data).toHaveProperty('feature_enabled')
      
      console.log('✅ Credits system health check passed:', data)
    } catch (error) {
      clearTimeout(timeoutId)
      
      if (error instanceof Error && error.name === 'AbortError') {
        throw new Error(`Credits health check timed out after ${HEALTH_TIMEOUT}ms`)
      }
      
      throw new Error(`Credits health check failed: ${error}`)
    }
  }, HEALTH_TIMEOUT + 1000)

  it('should have CORS configured for frontend domain', async () => {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), HEALTH_TIMEOUT)

    try {
      const response = await fetch(`${BACKEND_URL}/debug/auth-config`, {
        method: 'GET',
        signal: controller.signal,
        headers: {
          'Accept': 'application/json',
          'Origin': 'https://writerbloom.com' // Test CORS
        }
      })

      clearTimeout(timeoutId)

      expect(response.status).toBe(200)
      
      const corsHeader = response.headers.get('access-control-allow-origin')
      expect(corsHeader).toBeTruthy()
      
      console.log('✅ CORS configuration check passed')
    } catch (error) {
      clearTimeout(timeoutId)
      
      if (error instanceof Error && error.name === 'AbortError') {
        throw new Error(`CORS check timed out after ${HEALTH_TIMEOUT}ms`)
      }
      
      throw new Error(`CORS check failed: ${error}`)
    }
  }, HEALTH_TIMEOUT + 1000)
})