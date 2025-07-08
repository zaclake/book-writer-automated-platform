import { useAuth } from '@clerk/nextjs'

export function useAuthToken() {
  const { getToken, isLoaded, isSignedIn } = useAuth()
  
  const getAuthHeaders = async (): Promise<Record<string, string>> => {
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