'use client'

import React, { useEffect, useRef, useCallback, useState } from 'react'
import { useUser } from '@clerk/nextjs'
import { toast } from '@/components/ui/use-toast'

interface AutoSaveOptions {
  interval?: number // Auto-save interval in milliseconds (default: 30 seconds)
  debounceDelay?: number // Debounce delay in milliseconds (default: 2 seconds)
  key: string // Unique key for the data being saved
  enableLocalStorage?: boolean // Enable localStorage backup (default: true)
  enableFirestore?: boolean // Enable Firestore sync (default: true)
}

interface AutoSaveState {
  isSaving: boolean
  lastSaved: Date | null
  hasUnsavedChanges: boolean
  error: string | null
  retryCount: number
  isRecovering: boolean
}

export function useAutoSave<T>(
  data: T,
  saveFunction: (data: T) => Promise<void>,
  options: AutoSaveOptions
) {
  const { user, isLoaded } = useUser()
  const [state, setState] = useState<AutoSaveState>({
    isSaving: false,
    lastSaved: null,
    hasUnsavedChanges: false,
    error: null,
    retryCount: 0,
    isRecovering: false
  })

  const {
    interval = 30000, // 30 seconds
    debounceDelay = 2000, // 2 seconds
    key,
    enableLocalStorage = true,
    enableFirestore = true
  } = options

  // Refs to store mutable values
  const timeoutRef = useRef<NodeJS.Timeout>()
  const intervalRef = useRef<NodeJS.Timeout>()
  const lastDataRef = useRef<string>('')
  const saveInProgressRef = useRef(false)

  // Local storage key
  const storageKey = `autosave_${key}_${user?.id || 'anonymous'}`

  // Save to localStorage
  const saveToLocalStorage = useCallback((data: T) => {
    if (!enableLocalStorage || typeof window === 'undefined') return

    try {
      const saveData = {
        data,
        timestamp: new Date().toISOString(),
        userId: user?.id,
        version: '1.0'
      }
      localStorage.setItem(storageKey, JSON.stringify(saveData))
    } catch (error) {
      console.error('Failed to save to localStorage:', error)
    }
  }, [storageKey, enableLocalStorage, user?.id])

  // Load from localStorage
  const loadFromLocalStorage = useCallback((): T | null => {
    if (!enableLocalStorage || typeof window === 'undefined') return null

    try {
      const saved = localStorage.getItem(storageKey)
      if (!saved) return null

      const saveData = JSON.parse(saved)
      
      // Validate the saved data
      if (saveData.userId !== user?.id) return null
      
      return saveData.data
    } catch (error) {
      console.error('Failed to load from localStorage:', error)
      return null
    }
  }, [storageKey, enableLocalStorage, user?.id])

  // Clear localStorage
  const clearLocalStorage = useCallback(() => {
    if (!enableLocalStorage || typeof window === 'undefined') return
    
    try {
      localStorage.removeItem(storageKey)
    } catch (error) {
      console.error('Failed to clear localStorage:', error)
    }
  }, [storageKey, enableLocalStorage])

  // Retry mechanism with exponential backoff
  const retryWithBackoff = useCallback(async (data: T, retryCount: number) => {
    const maxRetries = 3
    const baseDelay = 1000 // 1 second
    
    if (retryCount >= maxRetries) {
      throw new Error('Max retries exceeded')
    }
    
    const delay = baseDelay * Math.pow(2, retryCount)
    await new Promise(resolve => setTimeout(resolve, delay))
    
    return performSaveAttempt(data, false, retryCount + 1)
  }, [])

  // Conflict resolution helper
  const handleConflict = useCallback(async (data: T, conflictError: any) => {
    setState(prev => ({ ...prev, isRecovering: true }))
    
    try {
      // Try to load the latest version from server
      const savedData = loadFromLocalStorage()
      
      if (savedData) {
        // Show conflict resolution UI (simplified for now)
        const useLocal = confirm(
          'There was a conflict saving your changes. Would you like to use your local version? ' +
          'Click OK to use local version, Cancel to discard changes.'
        )
        
        if (useLocal) {
          // Force save with conflict resolution
          await saveFunction(data)
          setState(prev => ({ ...prev, isRecovering: false }))
          return true
        }
      }
      
      setState(prev => ({ ...prev, isRecovering: false }))
      return false
      
    } catch (error) {
      console.error('Conflict resolution failed:', error)
      setState(prev => ({ ...prev, isRecovering: false }))
      return false
    }
  }, [loadFromLocalStorage, saveFunction])

  // Perform the actual save operation with retry logic
  const performSaveAttempt = useCallback(async (data: T, isManual = false, retryCount = 0) => {
    if (saveInProgressRef.current && !isManual) return
    
    try {
      saveInProgressRef.current = true
      setState(prev => ({ 
        ...prev, 
        isSaving: true, 
        error: null, 
        retryCount: retryCount 
      }))

      // Save to localStorage first (faster and always succeeds)
      saveToLocalStorage(data)

      // Save to server/Firestore if enabled
      if (enableFirestore && isLoaded && user) {
        await saveFunction(data)
      }

      setState(prev => ({
        ...prev,
        isSaving: false,
        lastSaved: new Date(),
        hasUnsavedChanges: false,
        error: null,
        retryCount: 0
      }))

      if (isManual) {
        toast({
          title: "Saved",
          description: "Your changes have been saved successfully.",
          duration: 2000
        })
      }

    } catch (error) {
      console.error(`Auto-save failed (attempt ${retryCount + 1}):`, error)
      
      const errorMessage = error instanceof Error ? error.message : 'Save failed'
      const isNetworkError = errorMessage.includes('network') || errorMessage.includes('fetch')
      const isConflictError = errorMessage.includes('conflict') || errorMessage.includes('409')
      
      // Handle different types of errors
      if (isConflictError) {
        const resolved = await handleConflict(data, error)
        if (resolved) return // Successfully resolved conflict
      } else if (isNetworkError && retryCount < 3) {
        // Retry network errors
        try {
          await retryWithBackoff(data, retryCount)
          return // Retry succeeded
        } catch (retryError) {
          // All retries failed, continue to error handling
        }
      }

      setState(prev => ({
        ...prev,
        isSaving: false,
        error: errorMessage,
        retryCount: retryCount
      }))

      if (isManual) {
        toast({
          title: "Save Failed",
          description: "Failed to save changes. They are stored locally and will sync when connection is restored.",
          variant: "destructive"
        })
      }
    } finally {
      saveInProgressRef.current = false
    }
  }, [saveFunction, saveToLocalStorage, enableFirestore, isLoaded, user, retryWithBackoff, handleConflict])

  // Alias for backward compatibility
  const performSave = performSaveAttempt

  // Debounced save function
  const debouncedSave = useCallback((data: T) => {
    // Clear existing timeout
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
    }

    // Set new timeout
    timeoutRef.current = setTimeout(() => {
      performSave(data)
    }, debounceDelay)
  }, [performSave, debounceDelay])

  // Manual save function
  const manualSave = useCallback(async () => {
    // Clear debounced save timeout
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
    }
    
    await performSave(data, true)
  }, [performSave, data])

  // Set up auto-save effect
  useEffect(() => {
    if (!data || !isLoaded) return

    const currentDataString = JSON.stringify(data)
    
    // Check if data has actually changed
    if (currentDataString === lastDataRef.current) return
    
    lastDataRef.current = currentDataString
    setState(prev => ({ ...prev, hasUnsavedChanges: true }))

    // Trigger debounced save
    debouncedSave(data)

    // Set up interval-based save
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
    }

    intervalRef.current = setInterval(() => {
      if (state.hasUnsavedChanges && !saveInProgressRef.current) {
        performSave(data)
      }
    }, interval)

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
    }
  }, [data, debouncedSave, performSave, interval, isLoaded, state.hasUnsavedChanges])

  // Set up beforeunload listener to warn about unsaved changes
  useEffect(() => {
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      if (state.hasUnsavedChanges) {
        event.preventDefault()
        event.returnValue = 'You have unsaved changes. Are you sure you want to leave?'
        return event.returnValue
      }
    }

    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [state.hasUnsavedChanges])

  // Set up visibility change listener to save when tab becomes hidden
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden && state.hasUnsavedChanges && !saveInProgressRef.current) {
        performSave(data)
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
  }, [performSave, data, state.hasUnsavedChanges])

  // Cleanup timeouts on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
      }
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
    }
  }, [])

  return {
    ...state,
    manualSave,
    loadFromLocalStorage,
    clearLocalStorage,
    storageKey
  }
}

// Session recovery hook
export function useSessionRecovery<T>(
  key: string,
  defaultValue: T,
  onRecover?: (data: T) => void
) {
  const { user, isLoaded } = useUser()
  const [hasRecoverableData, setHasRecoverableData] = useState(false)
  const [recoveredData, setRecoveredData] = useState<T | null>(null)

  const storageKey = `autosave_${key}_${user?.id || 'anonymous'}`

  useEffect(() => {
    if (!isLoaded || typeof window === 'undefined') return

    try {
      const saved = localStorage.getItem(storageKey)
      if (!saved) return

      const saveData = JSON.parse(saved)
      
      // Validate the saved data
      if (saveData.userId !== user?.id) return
      
      // Check if the saved data is recent (within last 24 hours)
      const savedTime = new Date(saveData.timestamp)
      const now = new Date()
      const hoursDiff = (now.getTime() - savedTime.getTime()) / (1000 * 60 * 60)
      
      if (hoursDiff > 24) return

      setRecoveredData(saveData.data)
      setHasRecoverableData(true)

    } catch (error) {
      console.error('Failed to check for recoverable data:', error)
    }
  }, [isLoaded, user?.id, storageKey])

  const acceptRecovery = useCallback(() => {
    if (recoveredData && onRecover) {
      onRecover(recoveredData)
      toast({
        title: "Session Recovered",
        description: "Your previous work has been restored.",
      })
    }
    setHasRecoverableData(false)
    setRecoveredData(null)
  }, [recoveredData, onRecover])

  const rejectRecovery = useCallback(() => {
    setHasRecoverableData(false)
    setRecoveredData(null)
    // Clear the localStorage data
    try {
      if (typeof window !== 'undefined') {
        localStorage.removeItem(storageKey)
      }
    } catch (error) {
      console.error('Failed to clear localStorage:', error)
    }
  }, [storageKey])

  return {
    hasRecoverableData,
    recoveredData,
    acceptRecovery,
    rejectRecovery
  }
}

// Component for session recovery prompt
export interface SessionRecoveryPromptProps {
  isOpen: boolean
  onAccept: () => void
  onReject: () => void
  dataPreview?: string
}

export const SessionRecoveryPrompt: React.FC<SessionRecoveryPromptProps> = ({
  isOpen,
  onAccept,
  onReject,
  dataPreview
}) => {
  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white p-6 rounded-lg max-w-md w-full mx-4">
        <h3 className="text-lg font-semibold mb-4">Recover Previous Session?</h3>
        <p className="text-gray-600 mb-4">
          We found unsaved work from your previous session. Would you like to recover it?
        </p>
        {dataPreview && (
          <div className="bg-gray-100 p-3 rounded mb-4 text-sm">
            <strong>Preview:</strong> {dataPreview}
          </div>
        )}
        <div className="flex space-x-3">
          <button
            onClick={onAccept}
            className="flex-1 bg-blue-600 text-white py-2 px-4 rounded hover:bg-blue-700 transition-colors"
          >
            Recover
          </button>
          <button
            onClick={onReject}
            className="flex-1 bg-gray-300 text-gray-700 py-2 px-4 rounded hover:bg-gray-400 transition-colors"
          >
            Start Fresh
          </button>
        </div>
      </div>
    </div>
  )
} 