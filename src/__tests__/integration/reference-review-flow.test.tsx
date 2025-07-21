/**
 * Integration tests for Reference Review Flow
 * Tests the complete reference review interface and interactions
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { jest } from '@jest/globals'
import ReferenceReviewPage from '@/app/project/[projectId]/references/page'

// Mock next/navigation
const mockPush = jest.fn()
const mockParams = { projectId: 'test-project-123' }

jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: jest.fn(),
    back: jest.fn(),
  }),
  useParams: () => mockParams,
}))

// Mock authentication
jest.mock('@/lib/auth', () => ({
  useAuthToken: () => ({
    getAuthHeaders: jest.fn().mockResolvedValue({
      'Authorization': 'Bearer mock-token'
    }),
    isSignedIn: true,
    isLoaded: true,
  }),
}))

// Mock fetch for API calls
global.fetch = jest.fn()

const mockReferenceFiles = {
  'characters.md': {
    name: 'characters.md',
    content: '# Characters\n\n## Protagonist\n**Alex Stone** - A 16-year-old student with hidden magical abilities.\n\n## Antagonist\n**Dark Lord Malachar** - Ancient evil seeking to return to power.',
    lastModified: '2024-01-15T10:30:00Z'
  },
  'outline.md': {
    name: 'outline.md', 
    content: '# Plot Outline\n\n## Act I: Discovery\nChapters 1-8: Alex discovers magical powers and enters academy.\n\n## Act II: Training\nChapters 9-17: Training, friendships, and growing threat.\n\n## Act III: Confrontation\nChapters 18-25: Final battle with Malachar.',
    lastModified: '2024-01-15T10:30:00Z'
  },
  'world-building.md': {
    name: 'world-building.md',
    content: '# World Building\n\n## Setting\nModern-day magical academy hidden from regular world.\n\n## Magic System\nElemental magic based on natural forces.\n\n## Key Locations\n- Arcanum Academy\n- The Hidden Forest\n- Crystal Caves',
    lastModified: '2024-01-15T10:30:00Z'
  },
  'style-guide.md': {
    name: 'style-guide.md',
    content: '# Style Guide\n\n## Narrative Voice\nThird person limited, focusing on Alex\'s perspective.\n\n## Tone\nAdventurous with moments of humor and wonder.\n\n## Pacing\nSteady build with action sequences in key moments.',
    lastModified: '2024-01-15T10:30:00Z'
  },
  'plot-timeline.md': {
    name: 'plot-timeline.md',
    content: '# Plot Timeline\n\n## Must-Include Elements\n- Magic discovery scene\n- First spell casting\n- Meeting mentor character\n- Academy entrance exam\n- First confrontation with antagonist',
    lastModified: '2024-01-15T10:30:00Z'
  }
}

describe('Reference Review Flow - Integration Tests', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockPush.mockClear()
    
    // Mock API responses for loading reference files
    ;(global.fetch as jest.Mock).mockImplementation((url: string) => {
      if (url.includes('/api/references/')) {
        const filename = url.split('/').pop()?.split('?')[0]
        if (filename && mockReferenceFiles[filename as keyof typeof mockReferenceFiles]) {
          return Promise.resolve({
            ok: true,
            json: async () => mockReferenceFiles[filename as keyof typeof mockReferenceFiles]
          })
        }
      }
      return Promise.resolve({
        ok: false,
        status: 404
      })
    })
  })

  describe('Initial Load and Tab Navigation', () => {
    it('should load and display all reference tabs', async () => {
      render(<ReferenceReviewPage />)

      await waitFor(() => {
        expect(screen.getByText('📘 Story Reference Review')).toBeInTheDocument()
      })

      // Check all tabs are present
      expect(screen.getByText('Characters')).toBeInTheDocument()
      expect(screen.getByText('Plot Outline')).toBeInTheDocument()
      expect(screen.getByText('World/Glossary')).toBeInTheDocument()
      expect(screen.getByText('Style & Tone')).toBeInTheDocument()
      expect(screen.getByText('Must-Includes')).toBeInTheDocument()

      // Characters should be active by default
      const charactersTab = screen.getByText('Characters').closest('button')
      expect(charactersTab).toHaveClass('border-blue-500', 'text-blue-600')
    })

    it('should switch tabs and load different content', async () => {
      render(<ReferenceReviewPage />)

      await waitFor(() => {
        expect(screen.getByText('Characters')).toBeInTheDocument()
      })

      // Wait for characters content to load
      await waitFor(() => {
        expect(screen.getByText(/Alex Stone/)).toBeInTheDocument()
      })

      // Click on Plot Outline tab
      const outlineTab = screen.getByText('Plot Outline')
      fireEvent.click(outlineTab)

      // Should show outline content
      await waitFor(() => {
        expect(screen.getByText(/Act I: Discovery/)).toBeInTheDocument()
      })

      // Tab should be active
      const outlineButton = outlineTab.closest('button')
      expect(outlineButton).toHaveClass('border-blue-500', 'text-blue-600')
    })

    it('should show sticky finish review CTA at bottom', async () => {
      render(<ReferenceReviewPage />)

      await waitFor(() => {
        expect(screen.getByText('Finish Review & Start Writing')).toBeInTheDocument()
      })

      const ctaButton = screen.getByText('Finish Review & Start Writing')
      expect(ctaButton.closest('div')).toHaveClass('fixed', 'bottom-0')
    })
  })

  describe('Edit and Approve Functionality', () => {
    it('should allow editing reference content', async () => {
      render(<ReferenceReviewPage />)

      await waitFor(() => {
        expect(screen.getByText(/Alex Stone/)).toBeInTheDocument()
      })

      // Click Edit button
      const editButton = screen.getByText('Edit')
      fireEvent.click(editButton)

      // Should show textarea with content
      const textarea = screen.getByDisplayValue(/Alex Stone/)
      expect(textarea).toBeInTheDocument()
      expect(textarea.tagName).toBe('TEXTAREA')

      // Should show Save and Cancel buttons
      expect(screen.getByText('Save Changes')).toBeInTheDocument()
      expect(screen.getByText('Cancel')).toBeInTheDocument()
    })

    it('should save edited content', async () => {
      // Mock successful save
      ;(global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true })
      })

      render(<ReferenceReviewPage />)

      await waitFor(() => {
        expect(screen.getByText(/Alex Stone/)).toBeInTheDocument()
      })

      // Enter edit mode
      const editButton = screen.getByText('Edit')
      fireEvent.click(editButton)

      // Modify content
      const textarea = screen.getByDisplayValue(/Alex Stone/)
      fireEvent.change(textarea, { 
        target: { value: '# Characters\n\n## Protagonist\n**Alex Stone** - A 16-year-old student with newly discovered magical abilities.' }
      })

      // Save changes
      const saveButton = screen.getByText('Save Changes')
      fireEvent.click(saveButton)

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/references/characters.md'),
          expect.objectContaining({
            method: 'PUT',
            headers: expect.objectContaining({
              'Content-Type': 'application/json'
            })
          })
        )
      })

      // Should exit edit mode
      expect(screen.getByText('Edit')).toBeInTheDocument()
      expect(screen.queryByText('Save Changes')).not.toBeInTheDocument()
    })

    it('should approve reference files', async () => {
      render(<ReferenceReviewPage />)

      await waitFor(() => {
        expect(screen.getByText(/Alex Stone/)).toBeInTheDocument()
      })

      // Click Approve button
      const approveButton = screen.getByText('Approve')
      fireEvent.click(approveButton)

      // Button should change to "Approved"
      await waitFor(() => {
        expect(screen.getByText('Approved')).toBeInTheDocument()
      })

      // Should show check icon in tab
      const charactersTab = screen.getByText('Characters').closest('button')
      expect(charactersTab?.querySelector('svg')).toBeInTheDocument()
    })

    it('should track approval progress', async () => {
      render(<ReferenceReviewPage />)

      await waitFor(() => {
        expect(screen.getByText('0 of 5 references approved')).toBeInTheDocument()
      })

      // Approve one reference
      const approveButton = screen.getByText('Approve')
      fireEvent.click(approveButton)

      await waitFor(() => {
        expect(screen.getByText('1 of 5 references approved')).toBeInTheDocument()
      })
    })
  })

  describe('Generate References Functionality', () => {
    it('should show generate button when no references exist', async () => {
      // Mock empty/missing references
      ;(global.fetch as jest.Mock).mockImplementation(() => 
        Promise.resolve({
          ok: false,
          status: 404
        })
      )

      render(<ReferenceReviewPage />)

      await waitFor(() => {
        expect(screen.getByText('Generate References')).toBeInTheDocument()
      })

      expect(screen.getByText(/This reference file has not been generated yet/)).toBeInTheDocument()
    })

    it('should call generate references API', async () => {
      // Mock empty reference first, then successful generation
      ;(global.fetch as jest.Mock)
        .mockResolvedValueOnce({ ok: false, status: 404 })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            success: true,
            files: [
              { type: 'characters', filename: 'characters.md', size: 1500 },
              { type: 'outline', filename: 'outline.md', size: 2000 }
            ]
          })
        })

      render(<ReferenceReviewPage />)

      await waitFor(() => {
        expect(screen.getByText('Generate References')).toBeInTheDocument()
      })

      const generateButton = screen.getByText('Generate References')
      fireEvent.click(generateButton)

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/v2/projects/test-project-123/references/generate'),
          expect.objectContaining({
            method: 'POST'
          })
        )
      })
    })
  })

  describe('Finish Review Flow', () => {
    it('should redirect to chapters page when finish review is clicked', async () => {
      render(<ReferenceReviewPage />)

      await waitFor(() => {
        expect(screen.getByText('Finish Review & Start Writing')).toBeInTheDocument()
      })

      const finishButton = screen.getByText('Finish Review & Start Writing')
      fireEvent.click(finishButton)

      expect(mockPush).toHaveBeenCalledWith('/project/test-project-123/chapters')
    })

    it('should show completion status when all references approved', async () => {
      render(<ReferenceReviewPage />)

      await waitFor(() => {
        expect(screen.getByText(/Alex Stone/)).toBeInTheDocument()
      })

      // Approve all references by clicking through tabs
      const tabs = ['Characters', 'Plot Outline', 'World/Glossary', 'Style & Tone', 'Must-Includes']
      
      for (const tabName of tabs) {
        const tab = screen.getByText(tabName)
        fireEvent.click(tab)
        
        await waitFor(() => {
          const approveButton = screen.getByText('Approve')
          fireEvent.click(approveButton)
        })
      }

      // Should show completion message
      await waitFor(() => {
        expect(screen.getByText('✅ All references approved - ready to start writing!')).toBeInTheDocument()
      })
    })
  })

  describe('Error Handling', () => {
    it('should handle API errors gracefully', async () => {
      ;(global.fetch as jest.Mock).mockRejectedValue(new Error('Network error'))

      render(<ReferenceReviewPage />)

      await waitFor(() => {
        expect(screen.getByText(/Error loading this reference file/)).toBeInTheDocument()
      })
    })

    it('should handle save errors', async () => {
      ;(global.fetch as jest.Mock)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => mockReferenceFiles['characters.md']
        })
        .mockResolvedValueOnce({
          ok: false,
          status: 500
        })

      render(<ReferenceReviewPage />)

      await waitFor(() => {
        expect(screen.getByText(/Alex Stone/)).toBeInTheDocument()
      })

      // Enter edit mode and try to save
      const editButton = screen.getByText('Edit')
      fireEvent.click(editButton)

      const saveButton = screen.getByText('Save Changes')
      fireEvent.click(saveButton)

      await waitFor(() => {
        expect(screen.getByText('❌ Failed to save file')).toBeInTheDocument()
      })
    })
  })
}) 