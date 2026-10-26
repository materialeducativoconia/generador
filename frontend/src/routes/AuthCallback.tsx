import { Navigate, useSearchParams } from 'react-router'
import { useAuth } from '../auth/context'
import { takeReturnTo } from '../auth/google'

export function AuthCallback() {
  const { session, loading } = useAuth()
  const [params] = useSearchParams()

  // Google/Supabase put the reason in the query string; access_denied means the user pressed "Cancel".
  const error = params.get('error')
  if (error) return <Navigate to={`/?error=${error === 'access_denied' ? 'cancelled' : 'failed'}`} replace />

  if (loading) return <p className="center muted">Iniciando sesión…</p>
  if (!session) return <Navigate to="/?error=failed" replace />
  return <Navigate to={takeReturnTo()} replace />
}
