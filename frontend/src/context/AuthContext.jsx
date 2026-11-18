import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, refreshSession, tokenStore } from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [status, setStatus] = useState('loading') // loading | authenticated | anonymous

  const loadMe = useCallback(async () => {
    const { data } = await api.get('/auth/me')
    setUser(data)
    setStatus('authenticated')
    return data
  }, [])

  useEffect(() => {
    tokenStore.onSessionEnd(() => {
      setUser(null)
      setStatus('anonymous')
    })
    if (!tokenStore.refresh) {
      setStatus('anonymous')
      return
    }
    refreshSession()
      .then(loadMe)
      .catch(() => {
        tokenStore.clear()
        setStatus('anonymous')
      })
  }, [loadMe])

  const login = useCallback(async (email, password) => {
    const { data } = await api.post('/auth/login', { email, password })
    tokenStore.set(data.access_token, data.refresh_token)
    setUser(data.user)
    setStatus('authenticated')
    return data.user
  }, [])

  const applyTokens = useCallback((data) => {
    tokenStore.set(data.access_token, data.refresh_token)
    if (data.user) setUser(data.user)
  }, [])

  const logout = useCallback(async () => {
    const rt = tokenStore.refresh
    try { if (rt) await api.post('/auth/logout', { refresh_token: rt }) } catch { /* ignore */ }
    tokenStore.clear()
    setUser(null)
    setStatus('anonymous')
  }, [])

  const value = useMemo(() => {
    const perms = new Set(user?.permissions || [])
    return {
      user,
      status,
      login,
      logout,
      reload: loadMe,
      applyTokens,
      role: user?.role?.code,
      employee: user?.employee,
      can: (...codes) => codes.every((c) => perms.has(c)),
      canAny: (...codes) => codes.some((c) => perms.has(c)),
    }
  }, [user, status, login, logout, loadMe, applyTokens])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
