import { useEffect, useState } from 'react'

const SESSION_COOKIE = 'user_session'
const USER_ID_COOKIE = 'user_id'
const USER_EMAIL_COOKIE = 'user_email'
const USER_NAME_COOKIE = 'user_name'

function getClientCookie(name: string): string | null {
  if (typeof document === 'undefined') {
    return null
  }
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

export function getClientSessionToken(): string | null {
  return getClientCookie(SESSION_COOKIE)
}

export function getClientUser() {
  const session = getClientSessionToken()
  const id = getClientCookie(USER_ID_COOKIE)
  const email = getClientCookie(USER_EMAIL_COOKIE)
  const fullName = getClientCookie(USER_NAME_COOKIE) || ''
  const [firstName, ...rest] = fullName.split(' ')
  const lastName = rest.join(' ')

  if (!session || !id) {
    return null
  }

  return {
    id,
    firstName: firstName || null,
    lastName: lastName || null,
    fullName: fullName || null,
    emailAddresses: email ? [{ emailAddress: email }] : [],
    primaryEmailAddress: email ? { emailAddress: email } : null,
    imageUrl: null,
    createdAt: null,
  }
}

export function useAuthToken() {
  const [token, setToken] = useState<string | null>(null)
  const [user, setUser] = useState<any>(ANONYMOUS_USER)
  const [isLoaded, setIsLoaded] = useState(false)

  const refreshFromCookies = () => {
    const nextToken = getClientSessionToken()
    const nextUser = getClientUser()
    setToken(nextToken)
    setUser(nextUser || ANONYMOUS_USER)
    setIsLoaded(true)
  }

  useEffect(() => {
    refreshFromCookies()

    const onFocus = () => refreshFromCookies()
    const onVisibility = () => {
      if (document.visibilityState === 'visible') refreshFromCookies()
    }

    window.addEventListener('focus', onFocus)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      window.removeEventListener('focus', onFocus)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [])

  const getAuthHeaders = async (): Promise<Record<string, string>> => {
    const currentToken = getClientSessionToken()
    if (currentToken && currentToken !== token) {
      setToken(currentToken)
    }
    if (!currentToken) {
      return {}
    }
    return { Authorization: `Bearer ${currentToken}` }
  }

  return {
    getAuthHeaders,
    isLoaded,
    isSignedIn: Boolean(token),
    user: user || ANONYMOUS_USER,
  }
}

export const ANONYMOUS_USER = {
  id: 'anonymous-user',
  firstName: null,
  lastName: null,
  fullName: null,
  emailAddresses: [],
  primaryEmailAddress: null,
  imageUrl: null,
  createdAt: null,
}
