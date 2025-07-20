/**
 * Integration tests for Book Bible Creation Flow
 * Tests the complete end-to-end flow from wizard data to project creation
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { jest } from '@jest/globals'
import BookBibleCreator from '@/components/BookBibleCreator'
import { BookBibleData } from '@/lib/types'

// Mock next/navigation
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: jest.fn(),
    replace: jest.fn(),
    back: jest.fn(),
  }),
}))

// Mock Clerk authentication
jest.mock('@clerk/nextjs', () => ({
  useAuth: () => ({
    getToken: jest.fn().mockResolvedValue('mock-auth-token'),
    userId: 'test-user-123',
    isSignedIn: true,
  }),
  useUser: () => ({
    user: {
      id: 'test-user-123',
      emailAddresses: [{ emailAddress: 'test@example.com' }],
    },
  }),
}))

// Mock the toast hook
jest.mock('@/hooks/use-toast', () => ({
  toast: jest.fn(),
}))

// Mock fetch for API calls
global.fetch = jest.fn()

describe('Book Bible Creation Flow - Integration Tests', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    // Reset fetch mock
    ;(global.fetch as jest.Mock).mockClear()
  })

  describe('QuickStart Mode Flow', () => {
    const mockQuickStartData = {
      title: 'The Digital Frontier',
      genre: 'Science Fiction',
      brief_premise: 'A hacker discovers a conspiracy in virtual reality',
      main_character: 'Alex Chen, brilliant but reckless hacker',
      setting: 'Neo-Tokyo, 2087',
      conflict: 'Corporate AI threatens human consciousness',
    }

    test('should complete QuickStart flow and create project successfully', async () => {
      // Mock successful API response
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          project: {
            id: 'project-123',
            title: 'The Digital Frontier',
            genre: 'Science Fiction',
            status: 'active',
          },
        }),
      })

      render(<BookBibleCreator onBookBibleGenerated={jest.fn()} />)

      // Select QuickStart mode
      const quickStartButton = screen.getByText('QuickStart')
      fireEvent.click(quickStartButton)

      // Fill in QuickStart form
      fireEvent.change(screen.getByLabelText(/title/i), {
        target: { value: mockQuickStartData.title },
      })

      fireEvent.change(screen.getByLabelText(/genre/i), {
        target: { value: mockQuickStartData.genre },
      })

      fireEvent.change(screen.getByLabelText(/brief premise/i), {
        target: { value: mockQuickStartData.brief_premise },
      })

      fireEvent.change(screen.getByLabelText(/main character/i), {
        target: { value: mockQuickStartData.main_character },
      })

      fireEvent.change(screen.getByLabelText(/setting/i), {
        target: { value: mockQuickStartData.setting },
      })

      fireEvent.change(screen.getByLabelText(/conflict/i), {
        target: { value: mockQuickStartData.conflict },
      })

      // Select book length
      const bookLengthSelect = screen.getByLabelText(/book length/i)
      fireEvent.change(bookLengthSelect, { target: { value: 'standard_novel' } })

      // Submit form
      const submitButton = screen.getByText(/create book bible/i)
      fireEvent.click(submitButton)

      // Wait for API call
      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith('/api/book-bible/create', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: 'Bearer mock-auth-token',
          },
          body: expect.stringContaining(mockQuickStartData.title),
        })
      })

      // Verify the API call contains all expected data
      const apiCall = (global.fetch as jest.Mock).mock.calls[0]
      const requestBody = JSON.parse(apiCall[1].body)

      expect(requestBody).toEqual(
        expect.objectContaining({
          title: mockQuickStartData.title,
          genre: mockQuickStartData.genre,
          creation_mode: 'quickstart',
          source_data: expect.objectContaining(mockQuickStartData),
          book_length_tier: 'standard_novel',
          content: expect.stringContaining(mockQuickStartData.title),
        })
      )
    })

    test('should handle validation errors in QuickStart mode', async () => {
      const { toast } = require('@/hooks/use-toast')

      render(<BookBibleCreator onBookBibleGenerated={jest.fn()} />)

      // Select QuickStart mode
      fireEvent.click(screen.getByText('QuickStart'))

      // Try to submit without filling required fields
      const submitButton = screen.getByText(/create book bible/i)
      fireEvent.click(submitButton)

      // Should show validation error
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Title Required',
          variant: 'destructive',
        })
      )

      // Should not make API call
      expect(global.fetch).not.toHaveBeenCalled()
    })
  })

  describe('Guided Mode Flow', () => {
    const mockGuidedData = {
      title: 'The Last Library',
      genre: 'Fantasy',
      premise: 'In a world where books are forbidden, a librarian guards the last collection',
      main_characters: 'Mira the Librarian, Kael the Rebel, Elder Thorne',
      setting_time: 'Post-apocalyptic future',
      setting_place: 'The Wastes of former civilization',
      central_conflict: 'Knowledge vs. ignorance, freedom vs. control',
      themes: 'Power of knowledge, preservation of culture, resistance',
      target_audience: 'Young Adult',
      tone: 'Epic and hopeful despite dark setting',
      key_plot_points: 'Discovery, betrayal, revelation, final confrontation',
    }

    test('should complete Guided flow with comprehensive data', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          project: { id: 'guided-project-456' },
        }),
      })

      render(<BookBibleCreator onBookBibleGenerated={jest.fn()} />)

      // Select Guided mode
      fireEvent.click(screen.getByText('Guided'))

      // Fill comprehensive guided form
      Object.entries(mockGuidedData).forEach(([key, value]) => {
        const input = screen.getByLabelText(new RegExp(key.replace('_', ' '), 'i'))
        fireEvent.change(input, { target: { value } })
      })

      // Submit
      fireEvent.click(screen.getByText(/create book bible/i))

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalled()
      })

      const requestBody = JSON.parse((global.fetch as jest.Mock).mock.calls[0][1].body)
      expect(requestBody.creation_mode).toBe('guided')
      expect(requestBody.source_data).toEqual(expect.objectContaining(mockGuidedData))
    })
  })

  describe('Paste-In Mode Flow', () => {
    const mockPastedContent = `
# The Quantum Detective

## Genre
Science Fiction Mystery

## Premise
Detective Sarah Kim can observe quantum superpositions of crime scenes, seeing all possible outcomes simultaneously. When a murder case defies quantum logic, she must solve it before reality itself unravels.

## Main Characters
- Sarah Kim: Quantum-sensitive detective
- Dr. Marcus Webb: Quantum physicist
- The Paradox Killer: Reality-bending murderer

## Plot Structure
Act I: Introduction to quantum crime scene
Act II: Investigation deepens, reality breaks down
Act III: Confrontation in quantum space
`

    test('should handle paste-in content correctly', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          project: { id: 'paste-project-789' },
        }),
      })

      render(<BookBibleCreator onBookBibleGenerated={jest.fn()} />)

      // Select Paste-In mode
      fireEvent.click(screen.getByText('Paste-In'))

      // Fill in title and content
      fireEvent.change(screen.getByLabelText(/title/i), {
        target: { value: 'The Quantum Detective' },
      })

      fireEvent.change(screen.getByLabelText(/content/i), {
        target: { value: mockPastedContent },
      })

      // Submit
      fireEvent.click(screen.getByText(/create book bible/i))

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalled()
      })

      const requestBody = JSON.parse((global.fetch as jest.Mock).mock.calls[0][1].body)
      expect(requestBody.creation_mode).toBe('paste')
      expect(requestBody.content).toBe(mockPastedContent)
    })
  })

  describe('API Error Handling', () => {
    test('should handle backend API errors gracefully', async () => {
      const { toast } = require('@/hooks/use-toast')

      // Mock API error
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({ error: 'Internal server error' }),
      })

      render(<BookBibleCreator onBookBibleGenerated={jest.fn()} />)

      // Fill and submit quickstart
      fireEvent.click(screen.getByText('QuickStart'))
      fireEvent.change(screen.getByLabelText(/title/i), {
        target: { value: 'Test Book' },
      })
      fireEvent.change(screen.getByLabelText(/brief premise/i), {
        target: { value: 'Test premise' },
      })

      fireEvent.click(screen.getByText(/create book bible/i))

      await waitFor(() => {
        expect(toast).toHaveBeenCalledWith(
          expect.objectContaining({
            title: 'Error',
            description: expect.stringContaining('Failed to create'),
            variant: 'destructive',
          })
        )
      })
    })

    test('should handle network errors', async () => {
      const { toast } = require('@/hooks/use-toast')

      // Mock network error
      ;(global.fetch as jest.Mock).mockRejectedValueOnce(new Error('Network error'))

      render(<BookBibleCreator onBookBibleGenerated={jest.fn()} />)

      // Fill and submit
      fireEvent.click(screen.getByText('QuickStart'))
      fireEvent.change(screen.getByLabelText(/title/i), {
        target: { value: 'Test Book' },
      })
      fireEvent.change(screen.getByLabelText(/brief premise/i), {
        target: { value: 'Test premise' },
      })

      fireEvent.click(screen.getByText(/create book bible/i))

      await waitFor(() => {
        expect(toast).toHaveBeenCalledWith(
          expect.objectContaining({
            title: 'Error',
            description: expect.stringContaining('network'),
            variant: 'destructive',
          })
        )
      })
    })
  })

  describe('Book Length Calculations', () => {
    test('should calculate correct chapter counts for different book lengths', async () => {
      render(<BookBibleCreator onBookBibleGenerated={jest.fn()} />)

      fireEvent.click(screen.getByText('QuickStart'))

      // Test different book lengths
      const bookLengthTests = [
        { tier: 'novella', expectedChapters: 15 },
        { tier: 'standard_novel', expectedChapters: 25 },
        { tier: 'epic_novel', expectedChapters: 40 },
      ]

      for (const { tier, expectedChapters } of bookLengthTests) {
        const bookLengthSelect = screen.getByLabelText(/book length/i)
        fireEvent.change(bookLengthSelect, { target: { value: tier } })

        // Verify chapter count is updated (would need to check component state or UI)
        // This would require exposing chapter count in the UI or component state
      }
    })
  })

  describe('Loading States', () => {
    test('should show loading state during submission', async () => {
      // Mock delayed API response
      ;(global.fetch as jest.Mock).mockImplementationOnce(
        () =>
          new Promise((resolve) =>
            setTimeout(
              () =>
                resolve({
                  ok: true,
                  json: async () => ({ success: true, project: { id: 'test' } }),
                }),
              1000
            )
          )
      )

      render(<BookBibleCreator onBookBibleGenerated={jest.fn()} />)

      fireEvent.click(screen.getByText('QuickStart'))
      fireEvent.change(screen.getByLabelText(/title/i), {
        target: { value: 'Test Book' },
      })
      fireEvent.change(screen.getByLabelText(/brief premise/i), {
        target: { value: 'Test premise' },
      })

      fireEvent.click(screen.getByText(/create book bible/i))

      // Should show loading state
      expect(screen.getByText(/creating/i)).toBeInTheDocument()
    })
  })

  describe('Data Transformation', () => {
    test('should correctly transform wizard data for API', async () => {
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true, project: { id: 'test' } }),
      })

      render(<BookBibleCreator onBookBibleGenerated={jest.fn()} />)

      fireEvent.click(screen.getByText('QuickStart'))

      // Fill form with specific data
      fireEvent.change(screen.getByLabelText(/title/i), {
        target: { value: 'Transform Test' },
      })
      fireEvent.change(screen.getByLabelText(/genre/i), {
        target: { value: 'Horror' },
      })

      fireEvent.click(screen.getByText(/create book bible/i))

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalled()
      })

      const requestBody = JSON.parse((global.fetch as jest.Mock).mock.calls[0][1].body)

      // Verify data transformation
      expect(requestBody).toEqual(
        expect.objectContaining({
          title: 'Transform Test',
          genre: 'Horror',
          creation_mode: 'quickstart',
          must_include_sections: expect.any(Array),
          book_length_tier: expect.any(String),
          estimated_chapters: expect.any(Number),
          target_word_count: expect.any(Number),
          word_count_per_chapter: expect.any(Number),
          source_data: expect.any(Object),
          content: expect.stringContaining('Transform Test'),
        })
      )
    })
  })
}) 