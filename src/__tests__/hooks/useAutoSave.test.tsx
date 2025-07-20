import { renderHook, act } from '@testing-library/react'
import { useUser } from '@clerk/nextjs'
import { useAutoSave } from '../../hooks/useAutoSave'
import { toast } from '../../components/ui/use-toast'

// Mock dependencies
jest.mock('@clerk/nextjs')
jest.mock('../../components/ui/use-toast')

// Mock localStorage
const localStorageMock = {
  getItem: jest.fn(),
  setItem: jest.fn(),
  removeItem: jest.fn(),
  clear: jest.fn(),
}
Object.defineProperty(window, 'localStorage', {
  value: localStorageMock
})

const mockUseUser = useUser as jest.MockedFunction<typeof useUser>
const mockToast = toast as jest.MockedFunction<typeof toast>

// Mock timers
jest.useFakeTimers()

describe('useAutoSave Hook', () => {
  const mockUser = {
    id: 'user_123',
    getToken: jest.fn().mockResolvedValue('mock-token')
  }

  const mockSaveFunction = jest.fn().mockResolvedValue(undefined)
  const testData = { content: 'test content', title: 'test title' }
  const saveOptions = {
    key: 'test-document',
    interval: 5000,
    debounceDelay: 1000
  }

  beforeEach(() => {
    jest.clearAllMocks()
    jest.clearAllTimers()
    mockUseUser.mockReturnValue({
      user: mockUser,
      isLoaded: true
    } as any)
  })

  afterEach(() => {
    jest.runOnlyPendingTimers()
  })

  describe('Basic Functionality', () => {
    test('initializes with correct default state', () => {
      const { result } = renderHook(() =>
        useAutoSave(testData, mockSaveFunction, saveOptions)
      )

      expect(result.current.isSaving).toBe(false)
      expect(result.current.lastSaved).toBeNull()
      expect(result.current.hasUnsavedChanges).toBe(false)
      expect(result.current.error).toBeNull()
    })

    test('detects unsaved changes when data changes', async () => {
      const { result, rerender } = renderHook(
        ({ data }) => useAutoSave(data, mockSaveFunction, saveOptions),
        { initialProps: { data: testData } }
      )

      const newData = { ...testData, content: 'modified content' }
      
      await act(async () => {
        rerender({ data: newData })
      })

      expect(result.current.hasUnsavedChanges).toBe(true)
    })
  })

  describe('Auto-save Behavior', () => {
    test('triggers debounced save after data change', async () => {
      const { result, rerender } = renderHook(
        ({ data }) => useAutoSave(data, mockSaveFunction, saveOptions),
        { initialProps: { data: testData } }
      )

      const newData = { ...testData, content: 'modified content' }
      
      await act(async () => {
        rerender({ data: newData })
        
        // Fast-forward past debounce delay
        jest.advanceTimersByTime(1000)
      })

      await act(async () => {
        // Allow promises to resolve
        await Promise.resolve()
      })

      expect(mockSaveFunction).toHaveBeenCalledWith(newData)
    })

    test('cancels previous debounced save when data changes again', async () => {
      const { result, rerender } = renderHook(
        ({ data }) => useAutoSave(data, mockSaveFunction, saveOptions),
        { initialProps: { data: testData } }
      )

      // First change
      await act(async () => {
        rerender({ data: { ...testData, content: 'first change' } })
        jest.advanceTimersByTime(500) // Half of debounce delay
      })

      // Second change before first save
      await act(async () => {
        rerender({ data: { ...testData, content: 'second change' } })
        jest.advanceTimersByTime(1000)
      })

      await act(async () => {
        await Promise.resolve()
      })

      // Should only save once with the latest data
      expect(mockSaveFunction).toHaveBeenCalledTimes(1)
      expect(mockSaveFunction).toHaveBeenCalledWith({
        ...testData,
        content: 'second change'
      })
    })

    test('triggers interval-based save', async () => {
      const { result, rerender } = renderHook(
        ({ data }) => useAutoSave(data, mockSaveFunction, saveOptions),
        { initialProps: { data: testData } }
      )

      const newData = { ...testData, content: 'modified content' }
      
      await act(async () => {
        rerender({ data: newData })
        
        // Skip debounce and go to interval
        jest.advanceTimersByTime(6000)
      })

      await act(async () => {
        await Promise.resolve()
      })

      expect(mockSaveFunction).toHaveBeenCalled()
    })
  })

  describe('Manual Save', () => {
    test('performs manual save immediately', async () => {
      const { result } = renderHook(() =>
        useAutoSave(testData, mockSaveFunction, saveOptions)
      )

      await act(async () => {
        await result.current.manualSave()
      })

      expect(mockSaveFunction).toHaveBeenCalledWith(testData)
      expect(mockToast).toHaveBeenCalledWith({
        title: 'Saved',
        description: 'Your changes have been saved successfully.',
        duration: 2000
      })
    })

    test('cancels debounced save when manual save is triggered', async () => {
      const { result, rerender } = renderHook(
        ({ data }) => useAutoSave(data, mockSaveFunction, saveOptions),
        { initialProps: { data: testData } }
      )

      const newData = { ...testData, content: 'modified content' }
      
      await act(async () => {
        rerender({ data: newData })
        jest.advanceTimersByTime(500) // Partial debounce
        
        // Manual save should cancel debounce
        await result.current.manualSave()
      })

      expect(mockSaveFunction).toHaveBeenCalledTimes(1)
    })
  })

  describe('Local Storage Integration', () => {
    test('saves to localStorage on change', async () => {
      const { result, rerender } = renderHook(
        ({ data }) => useAutoSave(data, mockSaveFunction, saveOptions),
        { initialProps: { data: testData } }
      )

      const newData = { ...testData, content: 'modified content' }
      
      await act(async () => {
        rerender({ data: newData })
        jest.advanceTimersByTime(1000)
      })

      expect(localStorageMock.setItem).toHaveBeenCalledWith(
        'autosave_test-document_user_123',
        expect.stringContaining('"content":"modified content"')
      )
    })

    test('loads from localStorage', () => {
      const savedData = {
        data: testData,
        timestamp: new Date().toISOString(),
        userId: 'user_123',
        version: '1.0'
      }
      
      localStorageMock.getItem.mockReturnValue(JSON.stringify(savedData))

      const { result } = renderHook(() =>
        useAutoSave(testData, mockSaveFunction, saveOptions)
      )

      const loaded = result.current.loadFromLocalStorage()
      expect(loaded).toEqual(testData)
    })

    test('handles localStorage errors gracefully', () => {
      localStorageMock.setItem.mockImplementation(() => {
        throw new Error('Storage quota exceeded')
      })

      const { result, rerender } = renderHook(
        ({ data }) => useAutoSave(data, mockSaveFunction, saveOptions),
        { initialProps: { data: testData } }
      )

      expect(() => {
        rerender({ data: { ...testData, content: 'new content' } })
      }).not.toThrow()
    })
  })

  describe('Error Handling', () => {
    test('handles save function errors', async () => {
      const errorSaveFunction = jest.fn().mockRejectedValue(new Error('Save failed'))
      
      const { result } = renderHook(() =>
        useAutoSave(testData, errorSaveFunction, saveOptions)
      )

      await act(async () => {
        await result.current.manualSave()
      })

      expect(result.current.error).toBe('Save failed')
      expect(mockToast).toHaveBeenCalledWith({
        title: 'Save Failed',
        description: 'Failed to save changes. They are stored locally and will sync when connection is restored.',
        variant: 'destructive'
      })
    })

    test('continues saving to localStorage even when server save fails', async () => {
      const errorSaveFunction = jest.fn().mockRejectedValue(new Error('Network error'))
      
      const { result, rerender } = renderHook(
        ({ data }) => useAutoSave(data, errorSaveFunction, saveOptions),
        { initialProps: { data: testData } }
      )

      const newData = { ...testData, content: 'modified content' }
      
      await act(async () => {
        rerender({ data: newData })
        jest.advanceTimersByTime(1000)
        await Promise.resolve()
      })

      expect(localStorageMock.setItem).toHaveBeenCalled()
      expect(result.current.error).toBe('Network error')
    })
  })

  describe('Configuration Options', () => {
    test('respects disabled localStorage option', async () => {
      const options = { ...saveOptions, enableLocalStorage: false }
      
      const { result, rerender } = renderHook(
        ({ data }) => useAutoSave(data, mockSaveFunction, options),
        { initialProps: { data: testData } }
      )

      await act(async () => {
        rerender({ data: { ...testData, content: 'modified' } })
        jest.advanceTimersByTime(1000)
      })

      expect(localStorageMock.setItem).not.toHaveBeenCalled()
    })

    test('respects disabled Firestore option', async () => {
      const options = { ...saveOptions, enableFirestore: false }
      
      const { result, rerender } = renderHook(
        ({ data }) => useAutoSave(data, mockSaveFunction, options),
        { initialProps: { data: testData } }
      )

      await act(async () => {
        rerender({ data: { ...testData, content: 'modified' } })
        jest.advanceTimersByTime(1000)
        await Promise.resolve()
      })

      expect(mockSaveFunction).not.toHaveBeenCalled()
    })

    test('uses custom intervals', async () => {
      const customOptions = { ...saveOptions, interval: 2000, debounceDelay: 500 }
      
      const { result, rerender } = renderHook(
        ({ data }) => useAutoSave(data, mockSaveFunction, customOptions),
        { initialProps: { data: testData } }
      )

      await act(async () => {
        rerender({ data: { ...testData, content: 'modified' } })
        
        // Should trigger after custom debounce delay
        jest.advanceTimersByTime(500)
        await Promise.resolve()
      })

      expect(mockSaveFunction).toHaveBeenCalled()
    })
  })

  describe('Cleanup', () => {
    test('clears timeouts on unmount', () => {
      const { result, unmount, rerender } = renderHook(
        ({ data }) => useAutoSave(data, mockSaveFunction, saveOptions),
        { initialProps: { data: testData } }
      )

      act(() => {
        rerender({ data: { ...testData, content: 'modified' } })
      })

      unmount()

      // Advance timers to ensure no save is triggered after unmount
      act(() => {
        jest.advanceTimersByTime(10000)
      })

      expect(mockSaveFunction).not.toHaveBeenCalled()
    })
  })
}) 