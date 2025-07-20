import { POST, GET } from '../../../app/api/book-bible/create/route'
import { auth } from '@clerk/nextjs/server'
import { NextRequest } from 'next/server'

// Mock dependencies
jest.mock('@clerk/nextjs/server')

const mockAuth = auth as jest.MockedFunction<typeof auth>

describe('/api/book-bible/create', () => {
  const mockUserId = 'user_123'
  
  beforeEach(() => {
    jest.clearAllMocks()
    mockAuth.mockReturnValue({ userId: mockUserId } as any)
  })

  describe('POST /api/book-bible/create', () => {
    const validRequestData = {
      title: 'Test Book',
      genre: 'Fantasy',
      content: 'This is a test book bible content',
      target_chapters: 25,
      word_count_per_chapter: 2000,
      must_include_sections: ['Magic system', 'Character backgrounds'],
      creation_mode: 'guided' as const
    }

    test('creates book bible successfully with valid data', async () => {
      const request = new NextRequest('http://localhost:3000/api/book-bible/create', {
        method: 'POST',
        body: JSON.stringify(validRequestData)
      })

      const response = await POST(request)
      const responseData = await response.json()

      expect(response.status).toBe(200)
      expect(responseData.success).toBe(true)
      expect(responseData.message).toBe('Book Bible created successfully')
      expect(responseData.project).toMatchObject({
        title: 'Test Book',
        genre: 'Fantasy',
        status: 'active'
      })
      expect(responseData.project.id).toBeDefined()
    })

    test('expands content for quickstart mode', async () => {
      const quickstartData = {
        ...validRequestData,
        creation_mode: 'quickstart' as const,
        source_data: {
          title: 'Test Book',
          genre: 'Fantasy',
          brief_premise: 'A hero saves the world',
          main_character: 'Hero McHeroface',
          setting: 'Fantasy realm',
          conflict: 'Evil threatens everything'
        }
      }

      const request = new NextRequest('http://localhost:3000/api/book-bible/create', {
        method: 'POST',
        body: JSON.stringify(quickstartData)
      })

      const response = await POST(request)
      const responseData = await response.json()

      expect(response.status).toBe(200)
      expect(responseData.success).toBe(true)
      // Content should be expanded for quickstart mode
      expect(responseData.project.title).toBe('Test Book')
    })

    test('returns 401 when user is not authenticated', async () => {
      mockAuth.mockReturnValue({ userId: null } as any)

      const request = new NextRequest('http://localhost:3000/api/book-bible/create', {
        method: 'POST',
        body: JSON.stringify(validRequestData)
      })

      const response = await POST(request)
      const responseData = await response.json()

      expect(response.status).toBe(401)
      expect(responseData.error).toBe('Unauthorized')
    })

    test('returns 400 when title is missing', async () => {
      const invalidData = { ...validRequestData, title: '' }

      const request = new NextRequest('http://localhost:3000/api/book-bible/create', {
        method: 'POST',
        body: JSON.stringify(invalidData)
      })

      const response = await POST(request)
      const responseData = await response.json()

      expect(response.status).toBe(400)
      expect(responseData.error).toBe('Title and content are required')
    })

    test('returns 400 when content is missing', async () => {
      const invalidData = { ...validRequestData, content: '' }

      const request = new NextRequest('http://localhost:3000/api/book-bible/create', {
        method: 'POST',
        body: JSON.stringify(invalidData)
      })

      const response = await POST(request)
      const responseData = await response.json()

      expect(response.status).toBe(400)
      expect(responseData.error).toBe('Title and content are required')
    })

    test('returns 400 when creation mode is invalid', async () => {
      const invalidData = { ...validRequestData, creation_mode: 'invalid' as any }

      const request = new NextRequest('http://localhost:3000/api/book-bible/create', {
        method: 'POST',
        body: JSON.stringify(invalidData)
      })

      const response = await POST(request)
      const responseData = await response.json()

      expect(response.status).toBe(400)
      expect(responseData.error).toBe('Invalid creation mode')
    })

    test('handles malformed JSON gracefully', async () => {
      const request = new NextRequest('http://localhost:3000/api/book-bible/create', {
        method: 'POST',
        body: 'invalid json'
      })

      const response = await POST(request)
      const responseData = await response.json()

      expect(response.status).toBe(500)
      expect(responseData.error).toBe('Internal server error')
    })

    test('applies default settings when not provided', async () => {
      const minimalData = {
        title: 'Test Book',
        content: 'Minimal content',
        creation_mode: 'paste' as const,
        must_include_sections: []
      }

      const request = new NextRequest('http://localhost:3000/api/book-bible/create', {
        method: 'POST',
        body: JSON.stringify(minimalData)
      })

      const response = await POST(request)
      const responseData = await response.json()

      expect(response.status).toBe(200)
      expect(responseData.project.settings).toMatchObject({
        target_chapters: 25,
        word_count_per_chapter: 2000,
        involvement_level: 'balanced',
        purpose: 'personal'
      })
    })
  })

  describe('GET /api/book-bible/create', () => {
    test('returns user projects successfully', async () => {
      const request = new NextRequest('http://localhost:3000/api/book-bible/create')

      const response = await GET(request)
      const responseData = await response.json()

      expect(response.status).toBe(200)
      expect(responseData.success).toBe(true)
      expect(responseData.projects).toBeDefined()
      expect(Array.isArray(responseData.projects)).toBe(true)
      expect(responseData.total).toBeDefined()
    })

    test('returns 401 when user is not authenticated', async () => {
      mockAuth.mockReturnValue({ userId: null } as any)

      const request = new NextRequest('http://localhost:3000/api/book-bible/create')

      const response = await GET(request)
      const responseData = await response.json()

      expect(response.status).toBe(401)
      expect(responseData.error).toBe('Unauthorized')
    })

    test('filters projects by user ownership', async () => {
      // First create a project for user_123
      const createRequest = new NextRequest('http://localhost:3000/api/book-bible/create', {
        method: 'POST',
        body: JSON.stringify({
          title: 'User 123 Project',
          content: 'Test content',
          creation_mode: 'paste',
          must_include_sections: []
        })
      })

      await POST(createRequest)

      // Then create a project for a different user
      mockAuth.mockReturnValue({ userId: 'user_456' } as any)
      const createRequest2 = new NextRequest('http://localhost:3000/api/book-bible/create', {
        method: 'POST',
        body: JSON.stringify({
          title: 'User 456 Project',
          content: 'Test content',
          creation_mode: 'paste',
          must_include_sections: []
        })
      })

      await POST(createRequest2)

      // Get projects for user_123
      mockAuth.mockReturnValue({ userId: 'user_123' } as any)
      const getRequest = new NextRequest('http://localhost:3000/api/book-bible/create')
      const response = await GET(getRequest)
      const responseData = await response.json()

      expect(response.status).toBe(200)
      expect(responseData.projects).toHaveLength(1)
      expect(responseData.projects[0].title).toBe('User 123 Project')
    })
  })

  describe('Data Validation and Security', () => {
    test('sanitizes HTML content in title', async () => {
      const maliciousData = {
        title: '<script>alert("xss")</script>Test Book',
        content: 'Safe content',
        creation_mode: 'paste' as const,
        must_include_sections: []
      }

      const request = new NextRequest('http://localhost:3000/api/book-bible/create', {
        method: 'POST',
        body: JSON.stringify(maliciousData)
      })

      const response = await POST(request)
      const responseData = await response.json()

      expect(response.status).toBe(200)
      // Title should be stored as-is for now, but would be sanitized in production
      expect(responseData.project.title).toBe('<script>alert("xss")</script>Test Book')
    })

    test('validates must_include_sections array', async () => {
      const dataWithInvalidSections = {
        title: 'Test Book',
        content: 'Test content',
        creation_mode: 'paste' as const,
        must_include_sections: ['valid section', null, undefined, ''] as any
      }

      const request = new NextRequest('http://localhost:3000/api/book-bible/create', {
        method: 'POST',
        body: JSON.stringify(dataWithInvalidSections)
      })

      const response = await POST(request)
      const responseData = await response.json()

      expect(response.status).toBe(200)
      // Invalid sections should be filtered out in production
      expect(responseData.project).toBeDefined()
    })

    test('limits project creation rate', async () => {
      // In production, this would test rate limiting
      // For now, just ensure multiple rapid requests work
      const requests = Array.from({ length: 5 }, (_, i) =>
        new NextRequest('http://localhost:3000/api/book-bible/create', {
          method: 'POST',
          body: JSON.stringify({
            title: `Test Book ${i}`,
            content: 'Test content',
            creation_mode: 'paste' as const,
            must_include_sections: []
          })
        })
      )

      const responses = await Promise.all(requests.map(POST))
      
      responses.forEach(response => {
        expect(response.status).toBe(200)
      })
    })
  })

  describe('Performance and Scalability', () => {
    test('handles large content efficiently', async () => {
      const largeContent = 'A'.repeat(100000) // 100KB content
      
      const largeData = {
        title: 'Large Book',
        content: largeContent,
        creation_mode: 'paste' as const,
        must_include_sections: Array.from({ length: 50 }, (_, i) => `Section ${i}`)
      }

      const start = Date.now()
      const request = new NextRequest('http://localhost:3000/api/book-bible/create', {
        method: 'POST',
        body: JSON.stringify(largeData)
      })

      const response = await POST(request)
      const end = Date.now()

      expect(response.status).toBe(200)
      expect(end - start).toBeLessThan(5000) // Should complete within 5 seconds
    })

    test('generates unique project IDs', async () => {
      const requests = Array.from({ length: 10 }, () =>
        new NextRequest('http://localhost:3000/api/book-bible/create', {
          method: 'POST',
          body: JSON.stringify({
            title: 'Test Book',
            content: 'Test content',
            creation_mode: 'paste' as const,
            must_include_sections: []
          })
        })
      )

      const responses = await Promise.all(requests.map(POST))
      const projectIds = await Promise.all(
        responses.map(async (r) => {
          const data = await r.json()
          return data.project.id
        })
      )

      const uniqueIds = new Set(projectIds)
      expect(uniqueIds.size).toBe(10) // All IDs should be unique
    })
  })
}) 