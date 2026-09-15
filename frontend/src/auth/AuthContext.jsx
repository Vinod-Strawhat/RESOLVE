import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  getCurrentUser,
  login as apiLogin,
  logout as apiLogout,
  setUnauthorizedHandler,
  signup as apiSignup,
} from '../api.js'
import { AuthContext } from './context.js'

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()
  const sessionEpochRef = useRef(0)

  useEffect(() => {
    let cancelled = false
    const bootstrapEpoch = sessionEpochRef.current

    function handleUnauthorized() {
      if (cancelled) return
      setUser(null)
      setLoading(false)
      navigate('/login', { replace: true })
    }
    setUnauthorizedHandler(handleUnauthorized)

    getCurrentUser()
      .then((body) => {
        if (cancelled || bootstrapEpoch !== sessionEpochRef.current) return
        setUser(body.user)
      })
      .catch(() => {
        if (cancelled || bootstrapEpoch !== sessionEpochRef.current) return
        setUser(null)
      })
      .finally(() => {
        if (!cancelled && bootstrapEpoch === sessionEpochRef.current) {
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
      setUnauthorizedHandler(null)
    }
  }, [navigate])

  const login = useCallback(async (email, password) => {
    sessionEpochRef.current += 1
    const body = await apiLogin({ email, password })
    setUser(body.user)
    return body.user
  }, [])

  const signup = useCallback(async (payload) => {
    sessionEpochRef.current += 1
    const body = await apiSignup(payload)
    setUser(body.user)
    return body.user
  }, [])

  const logout = useCallback(async () => {
    sessionEpochRef.current += 1
    try {
      await apiLogout()
    } finally {
      setUser(null)
      setLoading(false)
    }
  }, [])

  const value = {
    user,
    loading,
    isAuthenticated: Boolean(user),
    login,
    signup,
    logout,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}