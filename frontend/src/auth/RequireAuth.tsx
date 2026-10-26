import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'
import { useAuth } from './context'
import { rememberReturnTo } from './google'

export function RequireAuth({ children }: { children: ReactNode }) {
  const { session, loading } = useAuth()
  const location = useLocation()

  if (loading) return <p className="center muted">Cargando…</p>
  if (!session) {
    rememberReturnTo(location.pathname + location.search)
    return <Navigate to="/" replace />
  }
  return children
}
