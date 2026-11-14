import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams, useNavigate } from 'react-router'
import { useAuth } from '../auth/context'
import { rememberReturnTo, saveWithGoogle, signInWithGoogle } from '../auth/google'
import { Logo } from '../components/AppShell'
import { errorText } from '../components/ErrorNote'
import { api } from '../lib/apiClient'
import { track } from '../lib/track'

type Info = { plan: string; plan_label: string; months: number; credits: number; valid: boolean; state: string }

/** A free license link for first adopters: what it gives, sign in with Google, and the plan is theirs. */
export function License() {
  const { code = '' } = useParams()
  const { session, loading } = useAuth()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const info = useQuery({ queryKey: ['license', code], queryFn: () => api.get<Info>(`/api/licenses/${encodeURIComponent(code)}`), retry: false })
  const signedIn = !!session && !session.user.is_anonymous
  const redeem = useMutation({
    mutationFn: () => api.post<{ plan: string; already: boolean }>(`/api/licenses/${encodeURIComponent(code)}/redeem`),
    onSuccess: async () => {
      track('license_open_app')
      await qc.invalidateQueries({ queryKey: ['me'] })
      navigate('/app?licencia=1', { replace: true })
    },
  })
  async function google() {
    const back = `/licencia/${code}`
    if (session?.user.is_anonymous) await saveWithGoogle(back)  // a landing visitor keeps their preview too
    else { rememberReturnTo(back); await signInWithGoogle() }
  }
  const i = info.data

  return (
    <main className="license-page">
      <div className="license-card">
        <span className="brand"><Logo /><span>Jelyx Docs</span></span>
        {info.isPending || loading ? <div className="skeleton" /> : info.error || !i ? (
          <>
            <h1>Este enlace no existe</h1>
            <p className="muted">Revisa que lo copiaste completo o pide uno nuevo al equipo de Jelyx Docs.</p>
          </>
        ) : !i.valid ? (
          <>
            <h1>Este enlace ya no está activo</h1>
            <p className="muted">La licencia está {i.state}. Pide uno nuevo al equipo de Jelyx Docs.</p>
          </>
        ) : (
          <>
            <p className="eyebrow">Licencia gratis para primeros usuarios</p>
            <h1>Plan {i.plan_label} gratis por {i.months} {i.months === 1 ? 'mes' : 'meses'}</h1>
            <ul className="license-perks">
              <li><strong>{i.credits * i.months}</strong> créditos: unas {i.credits * i.months} páginas de libros ilustrados</li>
              <li>Descarga en PDF lista para imprimir</li>
              <li>Sin tarjeta y sin cobros al terminar</li>
            </ul>
            <p className="muted small">A cambio, cuéntanos qué te funciona y qué no con la burbuja de opinión dentro de la app: así mejoramos Jelyx Docs para tu aula.</p>
            {redeem.error ? <p className="error small" role="alert">{errorText(redeem.error, 'No pudimos activar tu licencia.')}</p> : null}
            {signedIn ? (
              <button className="primary" onClick={() => redeem.mutate()} disabled={redeem.isPending}>
                {redeem.isPending ? 'Activando…' : 'Activar mi licencia'}
              </button>
            ) : (
              <button className="primary" onClick={() => void google()}>Entrar con Google y activar</button>
            )}
          </>
        )}
      </div>
    </main>
  )
}
