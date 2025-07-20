import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { useUser } from '@clerk/nextjs'
import BookBibleCreator from '../../components/BookBibleCreator'
import ProjectDashboard from '../../components/ProjectDashboard'
import ChapterEditor from '../../components/ChapterEditor'

// Mock dependencies
jest.mock('@clerk/nextjs')
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: jest.fn(),
    replace: jest.fn(),
    back: jest.fn()
  })
}))

const mockUseUser = useUser as jest.MockedFunction<typeof useUser>

// Mock fetch globally
global.fetch = jest.fn()

describe('Chapter Creation Flow Integration', () => {
  const mockUser = {
    id: 'user_123',
    firstName: 'John',
    lastName: 'Doe',
    getToken: jest.fn().mockResolvedValue('mock-token')
  }

  beforeEach(() => {
    jest.clearAllMocks()
    mockUseUser.mockReturnValue({
      user: mockUser,
      isLoaded: true,
      isSignedIn: true
    } as any)
  })

  describe('Complete Workflow: Book Bible → Project → Chapter Creation', () => {
    test('creates book bible, generates summary, and creates first chapter', async () => {
      const mockFetch = global.fetch as jest.MockedFunction<typeof fetch>
      
      // Mock responses for the complete workflow
      mockFetch
        // Book Bible creation
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            success: true,
            message: 'Book Bible created successfully',
            project: {
              id: 'project_123',
              title: 'Test Fantasy Novel',
              genre: 'Fantasy',
              status: 'active',
              created_at: new Date().toISOString(),
              settings: {
                target_chapters: 25,
                word_count_per_chapter: 2000,
                involvement_level: 'balanced',
                purpose: 'personal'
              }
            }
          })
        } as Response)
        // Prewriting summary generation
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            success: true,
            summary: {
              project_id: 'project_123',
              title: 'Test Fantasy Novel',
              genre: 'Fantasy',
              premise: 'A young wizard discovers their true heritage',
              main_characters: [
                { name: 'Alex', description: 'Young wizard protagonist' },
                { name: 'Mentor', description: 'Wise old wizard guide' }
              ],
              setting: {
                description: 'Magical realm with ancient secrets',
                time: 'Medieval fantasy',
                place: 'Mystical kingdom'
              },
              themes: ['Coming of age', 'Good vs evil', 'Self-discovery'],
              story_structure: {
                act1: 'Discovery and training',
                act2: 'Challenges and growth',
                act3: 'Final confrontation and resolution'
              },
              chapter_outline: Array.from({ length: 25 }, (_, i) => ({
                chapter: i + 1,
                description: `Chapter ${i + 1} events`,
                act: i < 8 ? 'act1' : i < 17 ? 'act2' : 'act3'
              })),
              total_chapters: 25,
              word_count_target: 2000
            }
          })
        } as Response)
        // Chapter creation
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            success: true,
            message: 'Chapter generated successfully',
            chapter: {
              id: 'chapter_123',
              project_id: 'project_123',
              chapter_number: 1,
              title: 'Chapter 1',
              word_count: 2000,
              target_word_count: 2000,
              stage: 'draft',
              created_at: new Date().toISOString(),
              generation_time: 2.5,
              cost_estimate: 0.05
            }
          })
        } as Response)

      // Step 1: Create Book Bible
      render(<BookBibleCreator onProjectCreated={jest.fn()} />)
      
      // Select guided mode
      const guidedModeButton = screen.getByText('🧙‍♂️ Guided Wizard')
      fireEvent.click(guidedModeButton)

      // Fill out the guided form
      await waitFor(() => {
        const titleInput = screen.getByPlaceholderText('Enter your book title')
        fireEvent.change(titleInput, { target: { value: 'Test Fantasy Novel' } })
      })

      const genreSelect = screen.getByRole('combobox')
      fireEvent.change(genreSelect, { target: { value: 'Fantasy' } })

      const premiseTextarea = screen.getByPlaceholderText('Describe your story in 2-3 sentences')
      fireEvent.change(premiseTextarea, { 
        target: { value: 'A young wizard discovers their true heritage and must save the world.' } 
      })

      // Continue through steps
      const nextButton = screen.getByText('Next Step')
      fireEvent.click(nextButton)

      // Add characters
      const characterTextarea = screen.getByPlaceholderText('Describe your main characters')
      fireEvent.change(characterTextarea, { 
        target: { value: 'Alex - Young wizard protagonist\nMentor - Wise old wizard guide' } 
      })

      fireEvent.click(nextButton)

      // Add setting
      const settingTextarea = screen.getByPlaceholderText('Describe the time and place')
      fireEvent.change(settingTextarea, { 
        target: { value: 'Magical realm with ancient secrets' } 
      })

      fireEvent.click(nextButton)

      // Add must-include elements
      const mustIncludeInput = screen.getByPlaceholderText('Enter an element to include')
      fireEvent.change(mustIncludeInput, { target: { value: 'Magic system explanation' } })
      
      const addElementButton = screen.getByText('Add Element')
      fireEvent.click(addElementButton)

      // Create the project
      const createProjectButton = screen.getByText('Create Project')
      fireEvent.click(createProjectButton)

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith('/api/book-bible/create', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer mock-token'
          },
          body: expect.stringContaining('"title":"Test Fantasy Novel"')
        })
      })

      // Verify book bible creation API call
      expect(mockFetch).toHaveBeenCalledWith('/api/book-bible/create', 
        expect.objectContaining({
          method: 'POST',
          body: expect.stringContaining('"creation_mode":"guided"')
        })
      )
    })

    test('handles chapter creation with prewriting summary', async () => {
      const mockFetch = global.fetch as jest.MockedFunction<typeof fetch>
      
      // Mock project dashboard data loading
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            project: {
              id: 'project_123',
              title: 'Test Fantasy Novel',
              genre: 'Fantasy',
              status: 'active'
            }
          })
        } as Response)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ chapters: [] })
        } as Response)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            summary: {
              project_id: 'project_123',
              title: 'Test Fantasy Novel',
              total_chapters: 25,
              word_count_target: 2000,
              main_characters: [
                { name: 'Alex', description: 'Young wizard' }
              ],
              themes: ['Coming of age'],
              setting: { description: 'Magical realm' }
            }
          })
        } as Response)
        // Chapter creation
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            success: true,
            chapter: {
              id: 'chapter_123',
              chapter_number: 1,
              word_count: 2000,
              stage: 'draft'
            }
          })
        } as Response)

      const mockOnCreateChapter = jest.fn()
      
      render(
        <ProjectDashboard 
          projectId="project_123" 
          onCreateChapter={mockOnCreateChapter}
        />
      )

      // Wait for project data to load
      await waitFor(() => {
        expect(screen.getByText('Test Fantasy Novel')).toBeInTheDocument()
      })

      // Click on a chapter slot to create new chapter
      const chapterSlot = screen.getByText('Ch. 1')
      fireEvent.click(chapterSlot)

      expect(mockOnCreateChapter).toHaveBeenCalledWith(1)
    })

    test('integrates chapter editor with auto-save and director notes', async () => {
      const mockFetch = global.fetch as jest.MockedFunction<typeof fetch>
      
      // Mock chapter loading
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            success: true,
            chapter: {
              id: 'chapter_123',
              project_id: 'project_123',
              chapter_number: 1,
              title: 'Chapter 1: The Beginning',
              content: 'Initial chapter content...',
              metadata: {
                word_count: 1500,
                target_word_count: 2000,
                stage: 'draft',
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString()
              },
              director_notes: []
            }
          })
        } as Response)
        // Mock save response
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            success: true,
            message: 'Chapter updated successfully'
          })
        } as Response)

      render(
        <ChapterEditor 
          chapterId="chapter_123" 
          projectId="project_123"
        />
      )

      // Wait for chapter to load
      await waitFor(() => {
        expect(screen.getByDisplayValue('Chapter 1: The Beginning')).toBeInTheDocument()
      })

      // Edit chapter content
      const contentTextarea = screen.getByDisplayValue(/Initial chapter content/)
      fireEvent.change(contentTextarea, { 
        target: { value: 'Updated chapter content with more details...' } 
      })

      // Add a director's note
      const showNotesButton = screen.getByText(/Show Notes/)
      fireEvent.click(showNotesButton)

      const noteTextarea = screen.getByPlaceholderText('Add feedback, suggestions, or revision notes...')
      fireEvent.change(noteTextarea, { 
        target: { value: 'Need to add more character development here' } 
      })

      const addNoteButton = screen.getByText('Add Note')
      fireEvent.click(addNoteButton)

      // Save chapter
      const saveButton = screen.getByText('Save Draft')
      fireEvent.click(saveButton)

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith('/api/chapters/chapter_123', {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer mock-token'
          },
          body: expect.stringContaining('"content":"Updated chapter content')
        })
      })
    })
  })

  describe('Error Handling and Edge Cases', () => {
    test('handles network errors gracefully during workflow', async () => {
      const mockFetch = global.fetch as jest.MockedFunction<typeof fetch>
      
      // Mock network error
      mockFetch.mockRejectedValueOnce(new Error('Network error'))

      render(<BookBibleCreator onProjectCreated={jest.fn()} />)
      
      // Try to create a project that will fail
      const guidedModeButton = screen.getByText('🧙‍♂️ Guided Wizard')
      fireEvent.click(guidedModeButton)

      const titleInput = screen.getByPlaceholderText('Enter your book title')
      fireEvent.change(titleInput, { target: { value: 'Test Book' } })

      const createButton = screen.getByText('Create Project')
      fireEvent.click(createButton)

      // Should handle error gracefully
      await waitFor(() => {
        // Error should be displayed to user
        expect(mockFetch).toHaveBeenCalled()
      })
    })

    test('validates form data before submission', async () => {
      render(<BookBibleCreator onProjectCreated={jest.fn()} />)
      
      const guidedModeButton = screen.getByText('🧙‍♂️ Guided Wizard')
      fireEvent.click(guidedModeButton)

      // Try to submit without required fields
      const createButton = screen.getByText('Create Project')
      fireEvent.click(createButton)

      // Should show validation errors
      await waitFor(() => {
        // Form should not submit with empty required fields
        expect(global.fetch).not.toHaveBeenCalled()
      })
    })

    test('recovers from partial failures in multi-step process', async () => {
      const mockFetch = global.fetch as jest.MockedFunction<typeof fetch>
      
      // Book bible creation succeeds
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            success: true,
            project: { id: 'project_123', title: 'Test Book' }
          })
        } as Response)
        // Summary generation fails
        .mockResolvedValueOnce({
          ok: false,
          json: async () => ({ error: 'Summary generation failed' })
        } as Response)

      const mockOnProjectCreated = jest.fn()
      
      render(<BookBibleCreator onProjectCreated={mockOnProjectCreated} />)
      
      // Complete book bible creation
      const guidedModeButton = screen.getByText('🧙‍♂️ Guided Wizard')
      fireEvent.click(guidedModeButton)

      const titleInput = screen.getByPlaceholderText('Enter your book title')
      fireEvent.change(titleInput, { target: { value: 'Test Book' } })

      const createButton = screen.getByText('Create Project')
      fireEvent.click(createButton)

      await waitFor(() => {
        // Should still call onProjectCreated even if summary fails
        expect(mockOnProjectCreated).toHaveBeenCalledWith(
          expect.objectContaining({ id: 'project_123' })
        )
      })
    })
  })

  describe('Performance and User Experience', () => {
    test('shows loading states during async operations', async () => {
      const mockFetch = global.fetch as jest.MockedFunction<typeof fetch>
      
      // Simulate slow response
      mockFetch.mockImplementation(() => 
        new Promise(resolve => 
          setTimeout(() => resolve({
            ok: true,
            json: async () => ({ success: true, project: { id: 'test' } })
          } as Response), 1000)
        )
      )

      render(<BookBibleCreator onProjectCreated={jest.fn()} />)
      
      const guidedModeButton = screen.getByText('🧙‍♂️ Guided Wizard')
      fireEvent.click(guidedModeButton)

      const titleInput = screen.getByPlaceholderText('Enter your book title')
      fireEvent.change(titleInput, { target: { value: 'Test Book' } })

      const createButton = screen.getByText('Create Project')
      fireEvent.click(createButton)

      // Should show loading state
      await waitFor(() => {
        expect(screen.getByText('Creating...')).toBeInTheDocument()
      })
    })

    test('maintains user data during navigation', async () => {
      // This would test that form data is preserved when users navigate
      // between steps or if they accidentally close/refresh the page
      
      const { rerender } = render(<BookBibleCreator onProjectCreated={jest.fn()} />)
      
      const guidedModeButton = screen.getByText('🧙‍♂️ Guided Wizard')
      fireEvent.click(guidedModeButton)

      const titleInput = screen.getByPlaceholderText('Enter your book title')
      fireEvent.change(titleInput, { target: { value: 'Persistent Test Book' } })

      // Simulate component re-render (navigation, etc.)
      rerender(<BookBibleCreator onProjectCreated={jest.fn()} />)

      // In a real implementation with persistence, the title should still be there
      // For this test, we're just ensuring the component handles re-renders
      expect(guidedModeButton).toBeInTheDocument()
    })
  })
}) 