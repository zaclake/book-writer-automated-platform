import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { useUser } from '@clerk/nextjs'
import UserProfile from '../../components/UserProfile'
import { toast } from '../../components/ui/use-toast'

// Mock dependencies
jest.mock('@clerk/nextjs')
jest.mock('../../components/ui/use-toast')

const mockUseUser = useUser as jest.MockedFunction<typeof useUser>
const mockToast = toast as jest.MockedFunction<typeof toast>

// Mock fetch
global.fetch = jest.fn()

describe('UserProfile Component', () => {
  const mockUser = {
    id: 'user_123',
    firstName: 'John',
    lastName: 'Doe',
    emailAddresses: [{ emailAddress: 'john.doe@example.com' }],
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

  describe('Component Rendering', () => {
    test('renders user profile form when user is loaded', () => {
      render(<UserProfile />)
      
      expect(screen.getByText('User Profile')).toBeInTheDocument()
      expect(screen.getByDisplayValue('John Doe')).toBeInTheDocument()
      expect(screen.getByDisplayValue('john.doe@example.com')).toBeInTheDocument()
    })

    test('shows loading state when user is not loaded', () => {
      mockUseUser.mockReturnValue({
        user: null,
        isLoaded: false,
        isSignedIn: false
      } as any)

      render(<UserProfile />)
      expect(screen.getByText('Loading profile...')).toBeInTheDocument()
    })

    test('shows sign-in message when user is not signed in', () => {
      mockUseUser.mockReturnValue({
        user: null,
        isLoaded: true,
        isSignedIn: false
      } as any)

      render(<UserProfile />)
      expect(screen.getByText('Please sign in to view your profile.')).toBeInTheDocument()
    })
  })

  describe('Form Interactions', () => {
    test('allows user to edit bio field', async () => {
      render(<UserProfile />)
      
      const bioTextarea = screen.getByPlaceholderText('Tell us about yourself...')
      fireEvent.change(bioTextarea, { target: { value: 'I am a writer' } })
      
      expect(bioTextarea).toHaveValue('I am a writer')
    })

    test('allows user to select preferred genres', () => {
      render(<UserProfile />)
      
      const fantasyCheckbox = screen.getByLabelText('Fantasy')
      fireEvent.click(fantasyCheckbox)
      
      expect(fantasyCheckbox).toBeChecked()
    })

    test('updates quality preferences', () => {
      render(<UserProfile />)
      
      const proseSlider = screen.getByLabelText(/Prose Quality/i)
      fireEvent.change(proseSlider, { target: { value: '8' } })
      
      expect(proseSlider).toHaveValue('8')
    })
  })

  describe('Profile Saving', () => {
    test('saves profile successfully', async () => {
      const mockFetch = global.fetch as jest.MockedFunction<typeof fetch>
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true })
      } as Response)

      render(<UserProfile />)
      
      const saveButton = screen.getByText('Save Profile')
      fireEvent.click(saveButton)
      
      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith('/api/user/profile', {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer mock-token'
          },
          body: expect.stringContaining('"bio":""')
        })
      })

      expect(mockToast).toHaveBeenCalledWith({
        title: 'Success',
        description: 'Profile updated successfully'
      })
    })

    test('handles save errors gracefully', async () => {
      const mockFetch = global.fetch as jest.MockedFunction<typeof fetch>
      mockFetch.mockRejectedValueOnce(new Error('Network error'))

      render(<UserProfile />)
      
      const saveButton = screen.getByText('Save Profile')
      fireEvent.click(saveButton)
      
      await waitFor(() => {
        expect(mockToast).toHaveBeenCalledWith({
          title: 'Error',
          description: 'Failed to update profile. Please try again.',
          variant: 'destructive'
        })
      })
    })
  })

  describe('Accessibility', () => {
    test('has proper ARIA labels', () => {
      render(<UserProfile />)
      
      expect(screen.getByLabelText('Full Name')).toBeInTheDocument()
      expect(screen.getByLabelText('Email')).toBeInTheDocument()
      expect(screen.getByLabelText('Bio')).toBeInTheDocument()
    })

    test('supports keyboard navigation', () => {
      render(<UserProfile />)
      
      const saveButton = screen.getByText('Save Profile')
      saveButton.focus()
      
      expect(document.activeElement).toBe(saveButton)
    })
  })

  describe('Data Validation', () => {
    test('validates quality settings ranges', () => {
      render(<UserProfile />)
      
      const proseSlider = screen.getByLabelText(/Prose Quality/i)
      fireEvent.change(proseSlider, { target: { value: '15' } })
      
      // Should clamp to maximum value
      expect(proseSlider).toHaveValue('10')
    })

    test('handles empty bio gracefully', async () => {
      const mockFetch = global.fetch as jest.MockedFunction<typeof fetch>
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true })
      } as Response)

      render(<UserProfile />)
      
      const bioTextarea = screen.getByPlaceholderText('Tell us about yourself...')
      fireEvent.change(bioTextarea, { target: { value: '' } })
      
      const saveButton = screen.getByText('Save Profile')
      fireEvent.click(saveButton)
      
      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalled()
      })
    })
  })
}) 