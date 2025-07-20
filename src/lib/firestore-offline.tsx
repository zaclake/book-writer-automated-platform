import { 
  enableNetwork, 
  disableNetwork, 
  doc, 
  collection, 
  setDoc, 
  updateDoc, 
  deleteDoc 
} from 'firebase/firestore'
import { db } from './firestore-client'
import React from 'react'

interface QueuedOperation {
  id: string
  type: 'create' | 'update' | 'delete'
  collection: string
  documentId: string
  data?: any
  timestamp: number
  retry_count: number
  max_retries: number
}

interface SyncStatus {
  isOnline: boolean
  isSyncing: boolean
  queuedOperations: number
  lastSyncAttempt: Date | null
  lastSuccessfulSync: Date | null
}

class FirestoreOfflineManager {
  private operationQueue: QueuedOperation[] = []
  private syncStatus: SyncStatus = {
    isOnline: typeof navigator !== 'undefined' ? navigator.onLine : true,
    isSyncing: false,
    queuedOperations: 0,
    lastSyncAttempt: null,
    lastSuccessfulSync: null
  }
  private listeners: ((status: SyncStatus) => void)[] = []
  private syncInterval: NodeJS.Timeout | null = null

  constructor() {
    // Only initialize in browser environment
    if (typeof window !== 'undefined') {
      this.loadQueueFromStorage()
      this.setupNetworkListeners()
      this.startPeriodicSync()
    }
  }

  // Load queued operations from localStorage
  private loadQueueFromStorage() {
    if (typeof localStorage === 'undefined') return
    
    try {
      const stored = localStorage.getItem('firestore_offline_queue')
      if (stored) {
        this.operationQueue = JSON.parse(stored)
        this.updateSyncStatus({ queuedOperations: this.operationQueue.length })
      }
    } catch (error) {
      console.error('Failed to load offline queue:', error)
    }
  }

  // Save queued operations to localStorage
  private saveQueueToStorage() {
    if (typeof localStorage === 'undefined') return
    
    try {
      localStorage.setItem('firestore_offline_queue', JSON.stringify(this.operationQueue))
    } catch (error) {
      console.error('Failed to save offline queue:', error)
    }
  }

  // Setup network event listeners
  private setupNetworkListeners() {
    if (typeof window === 'undefined') return
    
    window.addEventListener('online', this.handleOnline)
    window.addEventListener('offline', this.handleOffline)
  }

  // Start periodic sync attempts
  private startPeriodicSync() {
    if (this.syncInterval) {
      clearInterval(this.syncInterval)
    }

    this.syncInterval = setInterval(() => {
      if (this.syncStatus.isOnline && this.operationQueue.length > 0) {
        this.processSyncQueue()
      }
    }, 30000) // Try every 30 seconds
  }

  // Update sync status and notify listeners
  private updateSyncStatus(updates: Partial<SyncStatus>) {
    this.syncStatus = { ...this.syncStatus, ...updates }
    this.listeners.forEach(listener => listener(this.syncStatus))
  }

  // Add a listener for sync status changes
  public onSyncStatusChange(listener: (status: SyncStatus) => void) {
    this.listeners.push(listener)
    
    // Return unsubscribe function
    return () => {
      const index = this.listeners.indexOf(listener)
      if (index > -1) {
        this.listeners.splice(index, 1)
      }
    }
  }

  // Cleanup method to prevent memory leaks
  public destroy() {
    // Clear the sync interval
    if (this.syncInterval) {
      clearInterval(this.syncInterval)
      this.syncInterval = null
    }
    
    // Clear all listeners
    this.listeners = []
    
    // Remove network event listeners
    window.removeEventListener('online', this.handleOnline)
    window.removeEventListener('offline', this.handleOffline)
    
    // Clear the operation queue
    this.operationQueue = []
    this.saveQueueToStorage()
    
    console.log('FirestoreOfflineManager destroyed and cleaned up')
  }

  // Bound event handlers for proper cleanup
  private handleOnline = () => {
    this.updateSyncStatus({ isOnline: true })
    this.processSyncQueue()
  }

  private handleOffline = () => {
    this.updateSyncStatus({ isOnline: false })
  }

  // Queue an operation for offline sync
  public queueOperation(
    type: QueuedOperation['type'],
    collection: string,
    documentId: string,
    data?: any
  ) {
    const operation: QueuedOperation = {
      id: `${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      type,
      collection,
      documentId,
      data,
      timestamp: Date.now(),
      retry_count: 0,
      max_retries: 3
    }

    this.operationQueue.push(operation)
    this.saveQueueToStorage()
    this.updateSyncStatus({ queuedOperations: this.operationQueue.length })

    // Try to sync immediately if online
    if (this.syncStatus.isOnline) {
      this.processSyncQueue()
    }

    return operation.id
  }

  // Process the sync queue
  public async processSyncQueue() {
    if (this.syncStatus.isSyncing || this.operationQueue.length === 0) {
      return
    }

    this.updateSyncStatus({ 
      isSyncing: true, 
      lastSyncAttempt: new Date() 
    })

    let successfulSyncs = 0
    const failedOperations: QueuedOperation[] = []

    for (const operation of this.operationQueue) {
      try {
        await this.executeOperation(operation)
        successfulSyncs++
      } catch (error) {
        console.error('Failed to sync operation:', operation, error)
        
        // Increment retry count
        operation.retry_count++
        
        // Keep in queue if under max retries, otherwise drop
        if (operation.retry_count < operation.max_retries) {
          failedOperations.push(operation)
        }
      }
    }

    // Update queue with failed operations only
    this.operationQueue = failedOperations
    this.saveQueueToStorage()

    this.updateSyncStatus({
      isSyncing: false,
      queuedOperations: this.operationQueue.length,
      lastSuccessfulSync: successfulSyncs > 0 ? new Date() : this.syncStatus.lastSuccessfulSync
    })
  }

  // Execute a single operation using Firestore SDK
  private async executeOperation(operation: QueuedOperation) {
    const { type, collection: collectionName, documentId, data } = operation

    const docRef = doc(db, collectionName, documentId)
    
    switch (type) {
      case 'create':
        // Use setDoc for create operations
        await setDoc(docRef, data)
        break

      case 'update':
        // Use updateDoc for partial updates
        await updateDoc(docRef, data)
        break

      case 'delete':
        // Use deleteDoc for deletions
        await deleteDoc(docRef)
        break

      default:
        throw new Error(`Unknown operation type: ${type}`)
    }
  }

  // Get current sync status
  public getSyncStatus(): SyncStatus {
    return { ...this.syncStatus }
  }

  // Enable Firestore network access
  public async enableFirestoreNetwork() {
    try {
      await enableNetwork(db)
      this.updateSyncStatus({ isOnline: true })
    } catch (error) {
      console.error('Failed to enable Firestore network:', error)
    }
  }

  // Disable Firestore network access
  public async disableFirestoreNetwork() {
    try {
      await disableNetwork(db)
      this.updateSyncStatus({ isOnline: false })
    } catch (error) {
      console.error('Failed to disable Firestore network:', error)
    }
  }

  // Clear all queued operations
  public clearQueue() {
    this.operationQueue = []
    this.saveQueueToStorage()
    this.updateSyncStatus({ queuedOperations: 0 })
  }

  // Force sync now
  public async forceSync() {
    if (this.syncStatus.isOnline) {
      await this.processSyncQueue()
    }
  }

  // Convenience methods for common operations
  public async saveDocument(collectionName: string, documentId: string, data: any) {
    try {
      if (this.syncStatus.isOnline) {
        // Try direct save first when online
        const docRef = doc(db, collectionName, documentId)
        await setDoc(docRef, data)
      } else {
        // Queue for offline sync
        this.queueOperation('create', collectionName, documentId, data)
      }
    } catch (error) {
      // If direct save fails, queue it
      console.warn('Direct save failed, queuing for offline sync:', error)
      this.queueOperation('create', collectionName, documentId, data)
    }
  }

  public async updateDocument(collectionName: string, documentId: string, data: any) {
    try {
      if (this.syncStatus.isOnline) {
        // Try direct update first when online
        const docRef = doc(db, collectionName, documentId)
        await updateDoc(docRef, data)
      } else {
        // Queue for offline sync
        this.queueOperation('update', collectionName, documentId, data)
      }
    } catch (error) {
      // If direct update fails, queue it
      console.warn('Direct update failed, queuing for offline sync:', error)
      this.queueOperation('update', collectionName, documentId, data)
    }
  }

  public async deleteDocument(collectionName: string, documentId: string) {
    try {
      if (this.syncStatus.isOnline) {
        // Try direct delete first when online
        const docRef = doc(db, collectionName, documentId)
        await deleteDoc(docRef)
      } else {
        // Queue for offline sync
        this.queueOperation('delete', collectionName, documentId)
      }
    } catch (error) {
      // If direct delete fails, queue it
      console.warn('Direct delete failed, queuing for offline sync:', error)
      this.queueOperation('delete', collectionName, documentId)
    }
  }

  // Destroy the manager and clean up
  public destroy() {
    if (this.syncInterval) {
      clearInterval(this.syncInterval)
    }
    
    window.removeEventListener('online', this.processSyncQueue)
    window.removeEventListener('offline', () => {})
    
    this.listeners = []
  }
}

// Create singleton instance (lazy initialization)
let _offlineManager: FirestoreOfflineManager | null = null

export const getOfflineManager = (): FirestoreOfflineManager => {
  if (!_offlineManager) {
    _offlineManager = new FirestoreOfflineManager()
  }
  return _offlineManager
}

// Utility functions for common operations
export function saveOffline<T>(
  collection: string,
  documentId: string,
  data: T,
  isUpdate = false
) {
  return getOfflineManager().queueOperation(
    isUpdate ? 'update' : 'create',
    collection,
    documentId,
    data
  )
}

export function deleteOffline(collection: string, documentId: string) {
  return getOfflineManager().queueOperation('delete', collection, documentId)
}

// React hook for sync status
export function useSyncStatus() {
  const [status, setStatus] = React.useState(() => {
    // Only get initial status in browser
    if (typeof window !== 'undefined') {
      return getOfflineManager().getSyncStatus()
    }
    return {
      isOnline: true,
      isSyncing: false,
      queuedOperations: 0,
      lastSyncAttempt: null,
      lastSuccessfulSync: null
    }
  })

  React.useEffect(() => {
    if (typeof window === 'undefined') return
    
    const manager = getOfflineManager()
    const unsubscribe = manager.onSyncStatusChange(setStatus)
    return unsubscribe
  }, [])

  return {
    ...status,
    forceSync: () => {
      if (typeof window !== 'undefined') {
        getOfflineManager().forceSync()
      }
    },
    clearQueue: () => {
      if (typeof window !== 'undefined') {
        getOfflineManager().clearQueue()
      }
    },
    destroy: () => {
      if (typeof window !== 'undefined') {
        getOfflineManager().destroy()
      }
    }
  }
}

// Component for sync status indicator
export interface SyncStatusIndicatorProps {
  className?: string
  showDetails?: boolean
}

export const SyncStatusIndicator: React.FC<SyncStatusIndicatorProps> = ({
  className = '',
  showDetails = false
}) => {
  const status = useSyncStatus()

  const getStatusColor = () => {
    if (!status.isOnline) return 'text-red-500'
    if (status.isSyncing) return 'text-yellow-500'
    if (status.queuedOperations > 0) return 'text-orange-500'
    return 'text-green-500'
  }

  const getStatusText = () => {
    if (!status.isOnline) return 'Offline'
    if (status.isSyncing) return 'Syncing...'
    if (status.queuedOperations > 0) return `${status.queuedOperations} pending`
    return 'Synced'
  }

  return (
    <div className={`flex items-center space-x-2 ${className}`}>
      <div className={`w-2 h-2 rounded-full ${getStatusColor().replace('text-', 'bg-')}`} />
      <span className={`text-sm ${getStatusColor()}`}>
        {getStatusText()}
      </span>
      {showDetails && status.lastSuccessfulSync && (
        <span className="text-xs text-gray-500">
          Last sync: {status.lastSuccessfulSync.toLocaleTimeString()}
        </span>
      )}
    </div>
  )
} 