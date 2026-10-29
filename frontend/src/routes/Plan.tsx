import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useSearchParams } from 'react-router'
import { AppShell } from '../components/AppShell'
import { errorText } from '../components/ErrorNote'
import { api } from '../lib/apiClient'
import { useBilling, useMe, type Billing } from '../lib/queries'
import { saveWithGoogle } from '../auth/google'

const PITCH: Record<string, string> = {
  docente: 'Para tu grupo: material listo para imprimir y usar en clase.',
  creador: 'Para vender tu material con tu propia marca.',
  editorial: 'Para varias marcas o clientes, con equipo y los mejores modelos.',
}
const date = (iso: string) => new Date(iso).toLocaleDateString('es-MX', { day: 'numeric', month: 'long' })

/** Plan and credits: one credit is about one generated page; the plan refills them every month. */
export function Plan() {
  const { data: b, isLoading } = useBilling()
  const { data: me } = useMe()
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const paid = params.get('pago') === 'ok'
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
      {paid && <p className="notice" role="status">¡Gracias! Estamos acreditando tu pago…</p>}
      {!b.enabled && <p className="notice">Los pagos se activan muy pronto.</p>}
      {go.error && <p className="error" role="alert">{errorText(go.error, 'No pudimos abrir el pago.')}</p>}

      <div className="plan-grid">
        {b.plans.map((p) => (
          <article key={p.key} className={`panel plan-card${p.key === b.plan ? ' current' : ''}${p.key === 'creador' ? ' featured' : ''}`}>
            {p.key === 'creador' && <span className="pill info">Más elegido</span>}
            <h2>{p.label}</h2>
            <p className="price"><strong>${p.price_usd}</strong> USD/mes</p>
            <p className="small muted">{PITCH[p.key]}</p>
            <p className="credits-line"><strong>{p.credits}</strong> créditos al mes <span className="muted small">(~{Math.round(p.credits / 29)} tomos de 24 páginas)</span></p>
            <Features plan={p} />
            {p.key === b.plan ? <button className="ghost" disabled>Tu plan</button> : (
              <button className={p.key === 'creador' ? 'primary' : 'ghost'} disabled={!b.enabled || go.isPending}
                onClick={() => go.mutate({ path: '/api/billing/checkout', body: { plan: p.key } })}>
                {current ? 'Cambiar a este plan' : 'Suscribirme'}
              </button>
            )}
          </article>
        ))}
      </div>

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

function Features({ plan: p }: { plan: Billing['plans'][number] }) {
  const rows: [boolean, string][] = [
    [true, `Tomos de hasta ${p.max_pages} páginas`],
    [true, 'Editar texto, colecciones y niveles'],
    [!p.watermark, p.watermark ? 'PDF con marca «Hecho con…» · uso en el aula' : 'Sin marca de agua · licencia para vender'],
    [p.word, 'Descargar en Word editable'],
    [p.print_edition, 'Edición para imprenta (KDP)'],
    [p.styles > 0, p.styles ? `${p.styles} estilos de referencia` : 'Biblioteca de estilos'],
    [p.identities > 0, p.identities > 1 ? `${p.identities} identidades de marca` : 'Tu identidad de marca'],
    [p.premium, 'Modelos de IA premium'],
    [true, `${p.concurrent} ${p.concurrent === 1 ? 'tomo' : 'tomos'} generándose a la vez`],
    [p.seats > 1, p.seats > 1 ? `Equipo de ${p.seats} personas` : 'Equipo'],
  ]
  return (
    <ul className="features">
      {rows.map(([on, label]) => <li key={label} className={on ? '' : 'off'}>{on ? '✓' : '—'} {label}</li>)}
    </ul>
  )
}
