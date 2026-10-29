import { useEffect, useState } from 'react'
import { Navigate, useSearchParams } from 'react-router'
import { useAuth } from '../auth/context'
import { redeemClaim, takeReturnTo } from '../auth/google'

export function AuthCallback() {
  const { session, loading } = useAuth()
  const [params] = useSearchParams()
  const [claimed, setClaimed] = useState(false)
  const ready = !loading && !!session && !session.user.is_anonymous

  useEffect(() => {  // a landing visitor's free preview moves to the account they just signed in with
    if (ready) void redeemClaim().finally(() => setClaimed(true))
  }, [ready])

  // Google/Supabase put the reason in the query string; access_denied means the user pressed "Cancel".
  const error = params.get('error')
  if (error) return <Navigate to={`/?error=${error === 'access_denied' ? 'cancelled' : 'failed'}`} replace />

  if (loading || (ready && !claimed)) return <p className="center muted">Iniciando sesión…</p>
  if (!session) return <Navigate to="/?error=failed" replace />
  return <Navigate to={takeReturnTo()} replace />
}
