import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { Link, Navigate, useSearchParams } from 'react-router'
import { AppShell } from '../components/AppShell'
import { errorText } from '../components/ErrorNote'
import { api } from '../lib/apiClient'
import { useMe } from '../lib/queries'
import { AdminTabs } from './AdminUsers'

type Adopter = { user_id: string; email: string | null; display_name: string | null; redeemed_at: string; tomes: number
  last_seen: string | null; feedback: number }
type Lic = { id: string; code: string; plan: string; months: number; max_uses: number; uses: number; note: string
  expires_at: string | null; revoked_at: string | null; created_at: string; state: string; users: Adopter[] }
type Feedback = { id: string; user_id: string | null; email: string | null; display_name: string | null; kind: string; area: string
  summary: string; detail: string; severity: 'baja' | 'media' | 'alta'; path: string | null; status: string; created_at: string
  transcript: { role: 'user' | 'assistant'; content: string }[] }
type Activity = { events: { id: number; user_id: string; email: string | null; display_name: string | null; event: string
  path: string | null; props: Record<string, unknown>; created_at: string; adopter: boolean }[]
  top: { event: string; n: number; users: number }[]; daily: { day: string; users: number; events: number }[] }

const PLAN = { docente: 'Docente', creador: 'Creador', editorial: 'Editorial' } as Record<string, string>
const STATE_TONE: Record<string, string> = { activo: 'ok', agotado: 'idle', vencido: 'idle', revocado: 'bad' }
const when = (iso: string | null) => iso ? new Date(iso).toLocaleString('es-MX', { dateStyle: 'medium', timeStyle: 'short' }) : '—'
const day = (iso: string | null) => iso ? new Date(iso).toLocaleDateString('es-MX', { day: 'numeric', month: 'short' }) : '—'

function Staff({ title, children }: { title: string; children: ReactNode }) {
  const { data: me } = useMe()
  if (me && me.platform_role !== 'admin' && me.platform_role !== 'staff') return <Navigate to="/app" replace />
  return (
    <AppShell>
      <section className="styles-head"><div><p className="eyebrow">Administración</p><h1 className="display sm">{title}</h1></div></section>
      <AdminTabs />
      {children}
    </AppShell>
  )
}

/** Free license links for first adopters: make one, copy it, see who used it and how they are doing. */
export function AdminLicenses() {
  const qc = useQueryClient()
  const admin = useMe().data?.platform_role === 'admin'
  const [form, setForm] = useState({ plan: 'docente', months: 3, max_uses: 1, expires_days: 30, note: '' })
  const [copied, setCopied] = useState<string | null>(null)
  const list = useQuery({ queryKey: ['admin-licenses'], queryFn: () => api.get<{ licenses: Lic[] }>('/api/admin/licenses') })
  const make = useMutation({
    mutationFn: () => api.post<{ license: Lic }>('/api/admin/licenses', form),
    onSuccess: async ({ license }) => { await qc.invalidateQueries({ queryKey: ['admin-licenses'] }); void copy(license.code) },
  })
  const revoke = useMutation({
    mutationFn: (id: string) => api.post(`/api/admin/licenses/${id}/revoke`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-licenses'] }),
  })
  const link = (code: string) => `${location.origin}/licencia/${code}`
  async function copy(code: string) {
    await navigator.clipboard.writeText(link(code)).catch(() => {})
    setCopied(code)
    setTimeout(() => setCopied(null), 2000)
  }
  const set = (k: keyof typeof form, v: string | number) => setForm({ ...form, [k]: v })

  return (
    <Staff title="Licencias gratis">
      {admin && (
        <section className="panel adopt-form">
          <h2 className="section-h">Nuevo enlace</h2>
          <p className="muted small">Quien lo abra y entre con Google recibe el plan gratis (una licencia por persona; nunca baja un plan mejor). Con él aparece la burbuja de opinión.</p>
          <div className="adopt-grid">
            <label className="field"><span>Plan</span>
              <select value={form.plan} onChange={(e) => set('plan', e.target.value)}>
                {Object.entries(PLAN).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select></label>
            <label className="field"><span>Meses gratis</span>
              <input type="number" min={1} max={24} value={form.months} onChange={(e) => set('months', Number(e.target.value))} /></label>
            <label className="field"><span>Personas que pueden usarlo</span>
              <input type="number" min={1} max={1000} value={form.max_uses} onChange={(e) => set('max_uses', Number(e.target.value))} /></label>
            <label className="field"><span>El enlace abre durante (días)</span>
              <input type="number" min={1} max={365} value={form.expires_days} onChange={(e) => set('expires_days', Number(e.target.value))} /></label>
            <label className="field wide"><span>Para quién (nota interna)</span>
              <input value={form.note} maxLength={200} placeholder="Ej.: maestras del grupo de Facebook de preescolar" onChange={(e) => set('note', e.target.value)} /></label>
          </div>
          {make.error ? <p className="error small" role="alert">{errorText(make.error, 'No se pudo crear el enlace.')}</p> : null}
          <button className="primary" onClick={() => make.mutate()} disabled={make.isPending}>{make.isPending ? 'Creando…' : 'Crear y copiar enlace'}</button>
        </section>
      )}
      {list.error ? <p className="error">{errorText(list.error, 'No se pudieron cargar las licencias.')}</p> : null}
      {!list.data ? <div className="skeleton tall" /> : !list.data.licenses.length ? <p className="muted">Aún no hay enlaces.</p> : (
        <div className="adopt-list">
          {list.data.licenses.map((l) => (
            <article key={l.id} className="panel adopt-card">
              <header>
                <span className={`pill ${STATE_TONE[l.state] ?? 'idle'}`}>{l.state}</span>
                <strong>Plan {PLAN[l.plan]} · {l.months} {l.months === 1 ? 'mes' : 'meses'}</strong>
                <span className="muted small">{l.uses}/{l.max_uses} usos · abre hasta {day(l.expires_at)}</span>
              </header>
              {l.note && <p className="small">{l.note}</p>}
              <div className="adopt-link">
                <code>{link(l.code)}</code>
                <button className="ghost small" onClick={() => void copy(l.code)}>{copied === l.code ? 'Copiado ✓' : 'Copiar'}</button>
                {admin && l.state === 'activo' && <button className="ghost small" onClick={() => revoke.mutate(l.id)} disabled={revoke.isPending}>Revocar</button>}
              </div>
              {l.users.length > 0 && (
                <ul className="adopt-users">
                  {l.users.map((u) => (
                    <li key={u.user_id}>
                      <span><strong>{u.display_name ?? u.email}</strong> <small className="muted">{u.email}</small></span>
                      <small className="muted">desde {day(u.redeemed_at)} · {u.tomes} tomos · {u.feedback} opiniones · visto {day(u.last_seen)}</small>
                      <Link className="small" to={`/admin/actividad?user=${u.user_id}`}>Actividad</Link>
                    </li>
                  ))}
                </ul>
              )}
            </article>
          ))}
        </div>
      )}
    </Staff>
  )
}

const KIND_TONE: Record<string, string> = { problema: 'bad', mejora: 'info', idea: 'info', elogio: 'ok' }
const STATUSES = ['nuevo', 'visto', 'resuelto', 'descartado']

/** What the first adopters told the feedback bubble, written down with DeepSeek: newest and unread first. */
export function AdminFeedback() {
  const qc = useQueryClient()
  const [status, setStatus] = useState('')
  const [open, setOpen] = useState<string | null>(null)
  const list = useQuery({ queryKey: ['admin-feedback', status], placeholderData: (p) => p,
    queryFn: () => api.get<{ feedback: Feedback[]; counts: Record<string, number> }>(`/api/admin/feedback?status=${status}`) })
  const mark = useMutation({
    mutationFn: ({ id, to }: { id: string; to: string }) => api.patch(`/api/admin/feedback/${id}`, { status: to }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-feedback'] }),
  })
  const counts = list.data?.counts ?? {}
  return (
    <Staff title="Opiniones">
      <div className="admin-filters">
        <button className={status === '' ? 'chip on' : 'chip'} onClick={() => setStatus('')}>Todas</button>
        {STATUSES.map((s) => <button key={s} className={status === s ? 'chip on' : 'chip'} onClick={() => setStatus(s)}>{s} · {counts[s] ?? 0}</button>)}
      </div>
      {list.error ? <p className="error">{errorText(list.error, 'No se pudieron cargar las opiniones.')}</p> : null}
      {!list.data ? <div className="skeleton tall" /> : !list.data.feedback.length ? <p className="muted">Nada por aquí todavía.</p> : (
        <div className="adopt-list">
          {list.data.feedback.map((f) => (
            <article key={f.id} className={`panel fb-card${f.status === 'nuevo' ? ' unread' : ''}`}>
              <header>
                <span className={`pill ${KIND_TONE[f.kind] ?? 'idle'}`}>{f.kind}</span>
                <span className={`sev ${f.severity}`}>{f.severity}</span>
                {f.area && <span className="muted small">{f.area}</span>}
                <span className="muted small grow">{when(f.created_at)}</span>
                <select value={f.status} aria-label="Estado" onChange={(e) => mark.mutate({ id: f.id, to: e.target.value })}>
                  {STATUSES.map((s) => <option key={s}>{s}</option>)}
                </select>
              </header>
              <h3>{f.summary}</h3>
              {f.detail && <p className="small">{f.detail}</p>}
              <p className="muted small">
                {f.user_id ? <Link to={`/admin/actividad?user=${f.user_id}`}>{f.display_name ?? f.email}</Link> : 'Usuario borrado'}
                {f.path && <> · en <code>{f.path}</code></>}
              </p>
              <button className="ghost small" onClick={() => setOpen(open === f.id ? null : f.id)}>{open === f.id ? 'Ocultar conversación' : 'Ver conversación'}</button>
              {open === f.id && (
                <div className="fb-lines static">
                  {f.transcript.map((l, i) => <p key={i} className={`fb-line ${l.role}`}>{l.content}</p>)}
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </Staff>
  )
}

/** What people do in the app: people per day, the most done actions and the latest events (of one user, or all). */
export function AdminActivity() {
  const [params, setParams] = useSearchParams()
  const user = params.get('user') ?? ''
  const event = params.get('evento') ?? ''
  const [days, setDays] = useState(7)
  const data = useQuery({ queryKey: ['admin-activity', user, event, days], placeholderData: (p) => p,
    queryFn: () => api.get<Activity>(`/api/admin/activity?days=${days}&event=${encodeURIComponent(event)}${user ? `&user=${user}` : ''}`) })
  const pick = (k: string, v: string) => { const next = new URLSearchParams(params); if (v) next.set(k, v); else next.delete(k); setParams(next) }
  const a = data.data
  const peak = Math.max(1, ...(a?.daily.map((d) => d.users) ?? [1]))
  const who = user && a?.events[0] ? (a.events[0].display_name ?? a.events[0].email) : null
  return (
    <Staff title="Actividad">
      <div className="admin-filters">
        <label className="select-pill"><span className="sr-only">Periodo</span>
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {[1, 7, 30, 90].map((d) => <option key={d} value={d}>{d === 1 ? 'Hoy y ayer' : `Últimos ${d} días`}</option>)}
          </select></label>
        {user && <button className="chip on" onClick={() => pick('user', '')}>{who ?? 'Un usuario'} ✕</button>}
        {event && <button className="chip on" onClick={() => pick('evento', '')}>{event} ✕</button>}
        {data.isFetching && <span className="spinner" aria-label="Cargando" />}
      </div>
      {data.error ? <p className="error">{errorText(data.error, 'No se pudo cargar la actividad.')}</p> : null}
      {!a ? <div className="skeleton tall" /> : (
        <>
          <section className="panel">
            <h2 className="section-h">Personas por día</h2>
            <div className="act-days">
              {a.daily.map((d) => (
                <div key={d.day} title={`${d.users} personas · ${d.events} eventos`}>
                  <span style={{ height: `${(d.users / peak) * 100}%` }} /><small>{day(d.day + 'T12:00:00')}</small><b>{d.users}</b>
                </div>
              ))}
              {!a.daily.length && <p className="muted small">Sin actividad en este periodo.</p>}
            </div>
          </section>
          <section className="panel">
            <h2 className="section-h">Lo que más se hace</h2>
            <div className="act-top">
              {a.top.map((t) => (
                <button key={t.event} className="act-top-row" onClick={() => pick('evento', t.event)}>
                  <code>{t.event}</code><span className="num">{t.n}</span><span className="muted small">{t.users} personas</span>
                </button>
              ))}
            </div>
          </section>
          <section className="panel">
            <h2 className="section-h">Últimos eventos</h2>
            <div className="act-events">
              {a.events.map((e) => (
                <div key={e.id} className="act-event">
                  <small className="muted">{when(e.created_at)}</small>
                  <button className="link-btn" onClick={() => pick('user', e.user_id)}>{e.display_name ?? e.email ?? 'visitante'}{e.adopter && <span className="pill info">licencia</span>}</button>
                  <code>{e.event}</code>
                  <small className="muted">{e.path}{Object.keys(e.props).length ? ` · ${JSON.stringify(e.props).slice(0, 160)}` : ''}</small>
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </Staff>
  )
}
