import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Navigate } from 'react-router'
import { AppShell } from '../components/AppShell'
import { errorText } from '../components/ErrorNote'
import { api } from '../lib/apiClient'
import { GENRE_LABEL } from '../lib/labels'
import { useMe } from '../lib/queries'

type Count = { key: string; count: number }
type Analytics = {
  days: number
  users: { total: number; new: number; onboarded: number; activated: number; creators: number; paying: number; churned: number; conversion: number }
  revenue: { mrr_usd: number; packs_usd: number; packs_sold: number; by_plan: { plan: string; label: string; count: number; mrr_usd: number }[] }
  usage: { tomes: number; exports: number; jobs: number; failed_jobs: number; credits_spent: number }
  cost: { ai_usd: number; llm_usd: number; images_usd: number; per_credit_usd: number | null }
  daily: { day: string; signups: number; tomes: number }[]
  uses: Count[]
  subjects: Count[]
  genres: Count[]
  top_users: { email: string; plan: string; spent: number; jobs: number }[]
}
const USE_LABEL: Record<string, string> = { aula: 'Doy clases', venta: 'Vende material', escuela: 'Escuela o editorial', casa: 'Educa en casa' }
const usd = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: n < 100 ? 2 : 0 })
const pct = (n: number) => `${(n * 100).toLocaleString('es-MX', { maximumFractionDigits: 1 })} %`
const day = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString('es-MX', { day: 'numeric', month: 'short' })

/** Platform analytics for our staff: growth, activation, revenue against AI cost. */
export function Analytics() {
  const { data: me } = useMe()
  const [days, setDays] = useState(30)
  const staff = me?.platform_role === 'admin' || me?.platform_role === 'staff'
  const { data: a, error } = useQuery({
    queryKey: ['admin-analytics', days], enabled: staff, placeholderData: (p) => p,
    queryFn: () => api.get<Analytics>(`/api/admin/analytics?days=${days}`),
  })
  if (me && !staff) return <Navigate to="/app" replace />

  return (
    <AppShell>
      <section className="styles-head">
        <div>
          <p className="eyebrow">Administración</p>
          <h1 className="display sm">Analítica</h1>
        </div>
        <div className="segmented" role="radiogroup" aria-label="Periodo">
          {[7, 30, 90].map((d) => (
            <button key={d} role="radio" aria-checked={days === d} className={days === d ? 'on' : ''} onClick={() => setDays(d)}>{d} días</button>
          ))}
        </div>
      </section>
      {error && <p className="error" role="alert">{errorText(error, 'No se pudo cargar la analítica.')}</p>}
      {!a ? <div className="skeleton" /> : (
        <div className="analytics">
          <div className="tiles">
            <Tile label="Usuarios" value={a.users.total.toLocaleString('es-MX')} note={`+${a.users.new} en ${a.days} días`} />
            <Tile label="Suscriptores" value={String(a.users.paying)} note={`${pct(a.users.conversion)} del total · ${a.users.churned} cancelados`} />
            <Tile label="Ingreso mensual (MRR)" value={usd(a.revenue.mrr_usd)} note={`+ ${usd(a.revenue.packs_usd)} en ${a.revenue.packs_sold} paquetes`} />
            <Tile label="Costo de IA" value={usd(a.cost.ai_usd)} note={a.cost.per_credit_usd != null ? `${usd(a.cost.per_credit_usd)} por crédito` : 'sin consumo'} />
            <Tile label="Créditos gastados" value={a.usage.credits_spent.toLocaleString('es-MX')} note={`${a.usage.tomes} tomos · ${a.usage.exports} descargas`} />
            <Tile label="Trabajos fallidos" value={a.usage.jobs ? pct(a.usage.failed_jobs / a.usage.jobs) : '—'} note={`${a.usage.failed_jobs} de ${a.usage.jobs}`} />
          </div>

          <div className="chart-row">
            <DailyBars title="Registros por día" data={a.daily} field="signups" />
            <DailyBars title="Tomos creados por día" data={a.daily} field="tomes" />
          </div>

          <div className="chart-row">
            <section className="panel">
              <h2 className="h3">Activación ({a.days} días)</h2>
              <HBars total={a.users.new} rows={[
                { key: 'Se registraron', count: a.users.new },
                { key: 'Completaron la bienvenida', count: a.users.onboarded },
                { key: 'Crearon un tomo', count: a.users.activated },
              ]} />
            </section>
            <section className="panel">
              <h2 className="h3">Suscripciones activas</h2>
              <HBars rows={a.revenue.by_plan.map((p) => ({ key: p.label, count: p.count }))}
                     note={(r) => usd(a.revenue.by_plan.find((p) => p.label === r.key)?.mrr_usd ?? 0)} />
            </section>
            <section className="panel">
              <h2 className="h3">Para qué la usan</h2>
              <HBars rows={a.uses.map((u) => ({ key: USE_LABEL[u.key] ?? u.key, count: u.count }))} />
            </section>
            <section className="panel">
              <h2 className="h3">Materias</h2>
              <HBars rows={a.subjects} />
            </section>
            <section className="panel">
              <h2 className="h3">Tipo de material ({a.days} días)</h2>
              <HBars rows={a.genres.map((g) => ({ key: GENRE_LABEL[g.key] ?? g.key, count: g.count }))} />
            </section>
            <section className="panel">
              <h2 className="h3">Costo de IA</h2>
              <HBars rows={[{ key: 'Texto (LLM)', count: a.cost.llm_usd }, { key: 'Imágenes y portadas', count: a.cost.images_usd }]}
                     note={(r) => usd(r.count)} />
            </section>
          </div>

          <section className="panel">
            <h2 className="h3">Quién más consume ({a.days} días)</h2>
            {a.top_users.length === 0 ? <p className="muted">Sin consumo en este periodo.</p> : (
              <div className="table-wrap">
                <table className="data">
                  <thead><tr><th>Usuario</th><th>Plan</th><th className="num">Créditos</th><th className="num">Trabajos</th></tr></thead>
                  <tbody>{a.top_users.map((u) => (
                    <tr key={u.email}><td>{u.email}</td><td>{u.plan}</td><td className="num">{u.spent}</td><td className="num">{u.jobs}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}
    </AppShell>
  )
}

function Tile({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="panel tile">
      <span className="muted small">{label}</span>
      <strong className="tile-v">{value}</strong>
      <span className="muted small">{note}</span>
    </div>
  )
}

/** One series per chart: daily counts as thin bars, a tooltip on hover or focus. */
function DailyBars({ title, data, field }: { title: string; data: Analytics['daily']; field: 'signups' | 'tomes' }) {
  const [hover, setHover] = useState<number | null>(null)
  const max = Math.max(1, ...data.map((d) => d[field]))
  const total = data.reduce((n, d) => n + d[field], 0)
  const w = 600, h = 140, step = w / data.length, bar = Math.max(2, step - 2)
  return (
    <section className="panel chart">
      <div className="chart-h">
        <h2 className="h3">{title}</h2>
        <span className="muted small">
          {hover != null ? `${day(data[hover].day)}: ${data[hover][field]}` : `${total} en total · máx. ${max}`}
        </span>
      </div>
      <svg viewBox={`0 0 ${w} ${h + 18}`} role="img" aria-label={`${title}: ${total} en ${data.length} días`} onMouseLeave={() => setHover(null)}>
        <line x1="0" x2={w} y1={h} y2={h} className="axis" />
        {data.map((d, i) => {
          const bh = d[field] ? Math.max(3, (d[field] / max) * (h - 8)) : 0
          return (
            <g key={d.day} onMouseEnter={() => setHover(i)}>
              <rect x={i * step} y="0" width={step} height={h} fill="transparent" />
              {bh > 0 && <path className={`bar${hover === i ? ' on' : ''}`} d={topRounded(i * step + 1, h, bar, bh)} />}
            </g>
          )
        })}
        <text x="0" y={h + 14} className="tick">{day(data[0].day)}</text>
        <text x={w} y={h + 14} textAnchor="end" className="tick">{day(data[data.length - 1].day)}</text>
      </svg>
    </section>
  )
}

/** A bar standing on the baseline with its top corners rounded (4px, less when the bar is small). */
function topRounded(x: number, base: number, width: number, height: number) {
  const r = Math.min(4, width / 2, height)
  return `M${x},${base} v${-(height - r)} q0,${-r} ${r},${-r} h${width - 2 * r} q${r},0 ${r},${r} v${height - r} z`
}

function HBars({ rows, total, note }: { rows: Count[]; total?: number; note?: (r: Count) => string }) {
  if (!rows.length || rows.every((r) => !r.count)) return <p className="muted small">Sin datos todavía.</p>
  const max = total ?? Math.max(...rows.map((r) => r.count))
  return (
    <ul className="hbars">
      {rows.map((r) => (
        <li key={r.key}>
          <span className="hb-k">{r.key}</span>
          <span className="hb-v">{note ? note(r) : r.count.toLocaleString('es-MX')}</span>
          <span className="hb-track"><span style={{ width: `${max ? Math.max(r.count ? 2 : 0, (r.count / max) * 100) : 0}%` }} /></span>
        </li>
      ))}
    </ul>
  )
}
