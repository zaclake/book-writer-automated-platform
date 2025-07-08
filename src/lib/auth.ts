import { useAuth } from '@clerk/nextjs'

export function useAuthToken() {
  const { getToken, isLoaded, isSignedIn } = useAuth()
  
  const getAuthHeaders = async () => {
    if (!isLoaded || !isSignedIn) {
      return {}
    }
    
    try {
      const token = await getToken()
      return token ? { Authorization: `Bearer ${token}` } : {}
    } catch (error) {
      console.error('Failed to get auth token:', error)
      return {}
    }
  }
  
  return {
    getAuthHeaders,
    isLoaded,
    isSignedIn
  }
} 