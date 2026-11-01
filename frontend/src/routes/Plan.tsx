import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { Link, useSearchParams } from 'react-router'
import { AppShell } from '../components/AppShell'
import { errorText } from '../components/ErrorNote'
import { api } from '../lib/apiClient'
import { useBilling, useMe } from '../lib/queries'
import { PlanCards } from '../components/PlanCards'
import { saveWithGoogle } from '../auth/google'

const date = (iso: string) => new Date(iso).toLocaleDateString('es-MX', { day: 'numeric', month: 'long' })

/** Plan and credits: one credit is about one generated page; the plan refills them every month. */
export function Plan() {
  const { data: b, isLoading } = useBilling()
  const { data: me } = useMe()
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const paid = params.get('pago') === 'ok'
  const tome = useWaitingTome(params.get('tomo'))
  useEffect(() => {  // Stripe's webhook may land a moment after the redirect
    if (!paid) return
    const t = setInterval(() => { void qc.invalidateQueries({ queryKey: ['billing'] }); void qc.invalidateQueries({ queryKey: ['me'] }) }, 2500)
    const stop = setTimeout(() => { clearInterval(t); setParams({}, { replace: true }) }, 15000)
    return () => { clearInterval(t); clearTimeout(stop) }
  }, [paid, qc, setParams])
  const go = useMutation({
    mutationFn: ({ path, body }: { path: string; body?: object }) => api.post<{ url: string }>(path, body),
    onSuccess: ({ url }) => window.location.assign(url),
  })
  const choose = (plan: string) => go.mutate({ path: '/api/billing/checkout', body: { plan } })
  // The landing's "Suscribirme" signs in with Google and lands here with ?plan=: straight on to Stripe.
  const wanted = params.get('plan')
  const started = useRef(false)
  useEffect(() => {
    if (started.current || !wanted || !b?.enabled || !me || me.anonymous || b.plan === wanted || !b.plans.some((p) => p.key === wanted)) return
    started.current = true
    go.mutate({ path: '/api/billing/checkout', body: { plan: wanted } })
  }, [wanted, b, me, go])
  // Arriving from the landing's button: a calm hand-off screen instead of the plan page flashing by.
  const handingOff = !!wanted && !go.isError && (!b || !me || (b.enabled && !me.anonymous && b.plan !== wanted && b.plans.some((p) => p.key === wanted)))
  if (handingOff) return (
    <main className="handoff" role="status">
      <span className="spinner" aria-hidden="true" />
      <p>Abriendo el pago seguro…</p>
      <small className="muted">Te llevamos a Stripe para suscribirte.</small>
    </main>
  )
  if (isLoading || !b) return <AppShell><div className="skeleton" /></AppShell>
  const current = b.plans.find((p) => p.key === b.plan)
  return (
    <AppShell>
      <section className="styles-head">
        <div>
          <p className="eyebrow">Plan y créditos</p>
          <h1 className="display">{current ? `Plan ${current.label}` : 'Elige tu plan'}</h1>
          <p className="muted">
            1 crédito ≈ 1 página generada. Un tomo usa 1 crédito por el esquema, 4 por la portada y 1 por página.
            Editar texto es gratis; si algo falla, te devolvemos los créditos.
          </p>
        </div>
        <div className="panel wallet">
          <span className="wallet-n">{b.credits.total}</span>
          <span className="muted small">créditos disponibles</span>
          {b.credits.by_source.plan ? <span className="small">{b.credits.by_source.plan} del plan{b.credits.plan_expires_at && ` · se renuevan el ${date(b.credits.plan_expires_at)}`}</span> : null}
          {b.credits.by_source.pack ? <span className="small">{b.credits.by_source.pack} de paquetes (12 meses)</span> : null}
          {b.credits.by_source.trial ? <span className="small">{b.credits.by_source.trial} de la prueba</span> : null}
          {b.can_manage && <button className="ghost small" onClick={() => go.mutate({ path: '/api/billing/portal' })} disabled={go.isPending}>Facturas y método de pago</button>}
        </div>
      </section>
      {me?.anonymous && (
        <p className="notice">Para suscribirte, entra con Google; tu vista previa se guarda en tu cuenta.{' '}
          <button className="link-button" onClick={() => void saveWithGoogle('/app/plan')}>Continuar con Google</button></p>
      )}
      {tome && !paid && b.plan === 'prueba' && <p className="notice">Elige tu plan para generar tu tomo completo, editarlo y descargarlo.</p>}
      {paid && <p className="notice" role="status">¡Gracias! Estamos acreditando tu pago…</p>}
      {tome && b.plan !== 'prueba' && <p className="notice"><Link to={`/app/tomos/${tome}`} className="primary">Volver a tu tomo</Link></p>}
      {!b.enabled && <p className="notice">Los pagos se activan muy pronto.</p>}
      {go.error && <p className="error" role="alert">{errorText(go.error, 'No pudimos abrir el pago.')}</p>}

      <PlanCards plans={b.plans} current={b.plan} action={(p) => p.key === b.plan ? <button className="ghost block" disabled>Tu plan actual</button> : (
        <button className={`${p.key === 'creador' ? 'primary' : 'ghost'} block`} disabled={!b.enabled || go.isPending || me?.anonymous}
          onClick={() => choose(p.key)}>
          {go.isPending && go.variables?.body && (go.variables.body as { plan?: string }).plan === p.key ? 'Abriendo pago…' : current ? 'Cambiar a este plan' : 'Suscribirme'}
        </button>
      )} />

      <section className="packs">
        <h2 className="section-h">¿Te faltan créditos?</h2>
        <p className="muted small">Paquetes de una sola vez; duran 12 meses y se usan después de los del plan.</p>
        <div className="pack-row">
          {b.packs.map((k) => (
            <button key={k.key} className="panel pack" disabled={!b.enabled || go.isPending}
              onClick={() => go.mutate({ path: '/api/billing/packs', body: { pack: k.key } })}>
              <strong>{k.credits} créditos</strong><span>${k.price_usd} USD</span>
            </button>
          ))}
        </div>
      </section>

      {b.history.length > 0 && (
        <section className="ledger">
          <h2 className="section-h">Movimientos</h2>
          <ul>
            {b.history.map((h, i) => (
              <li key={i}><span>{h.reason}</span><span className="muted small">{date(h.created_at)}</span>
                <span className={h.delta > 0 ? 'plus' : 'minus'}>{h.delta > 0 ? '+' : ''}{h.delta}</span></li>
            ))}
          </ul>
        </section>
      )}
    </AppShell>
  )
}

const TOME_KEY = 'plan:tomo'

/** The tome that sent the user here to pick a plan; remembered across Stripe's checkout, which returns without it. */
function useWaitingTome(fromUrl: string | null) {
  try {
    if (fromUrl) localStorage.setItem(TOME_KEY, fromUrl)
    return fromUrl ?? localStorage.getItem(TOME_KEY)
  } catch {
    return fromUrl
  }
}
