import { useAuth } from '@clerk/nextjs'

export function useAuthToken() {
  const { getToken, isLoaded, isSignedIn } = useAuth()
  
  const getAuthHeaders = async (): Promise<Record<string, string>> => {
    console.log('getAuthHeaders called - isLoaded:', isLoaded, 'isSignedIn:', isSignedIn)
    
    if (!isLoaded || !isSignedIn) {
      console.log('Not loaded or not signed in, returning empty headers')
      return {}
    }
    
    try {
      console.log('Calling getToken()...')
      const token = await getToken()
      console.log('Token received:', token ? `${token.substring(0, 20)}...` : 'null')
      console.log('Token type:', typeof token)
      console.log('Token length:', token ? token.length : 0)
      
      if (token) {
        // Check if it looks like a JWT (should have 3 parts separated by dots)
        const parts = token.split('.')
        console.log('Token parts count:', parts.length)
        if (parts.length !== 3) {
          console.error('Invalid JWT format - should have 3 parts separated by dots, got:', parts.length)
        }
      }
      
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