import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useDeferredValue, useState } from 'react'
import { Navigate, NavLink } from 'react-router'
import { AppShell } from '../components/AppShell'
import { errorText } from '../components/ErrorNote'
import { api } from '../lib/apiClient'
import { GENRE_LABEL } from '../lib/labels'
import { useMe } from '../lib/queries'

type AdminUser = {
  id: string; email: string; name: string | null; avatar_url: string | null; role: 'user' | 'staff' | 'admin'
  created_at: string; last_sign_in_at: string | null; plan: string; plan_status: string | null; period_end: string | null
  stripe: boolean; credits: number; tomes: number
}
type Detail = AdminUser & {
  ledger: { delta: number; kind: string; reason: string; created_at: string }[]
  series: { id: string; title: string; genre: string | null; status: string; preview: boolean; created_at: string }[]
}
const PLAN_LABEL: Record<string, string> = { prueba: 'Prueba', docente: 'Docente', creador: 'Creador', editorial: 'Editorial' }
const ROLE_LABEL: Record<string, string> = { user: 'Usuario', staff: 'Equipo (solo ver)', admin: 'Administrador' }
const date = (iso: string | null) => iso ? new Date(iso).toLocaleDateString('es-MX', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'

/** The admin panel's sections, above each of its pages. */
export function AdminTabs() {
  return (
    <nav className="admin-tabs" aria-label="Administración">
      <NavLink to="/admin" end>Usuarios</NavLink>
      <NavLink to="/admin/tomos">Tomos</NavLink>
      <NavLink to="/admin/estilos">Estilos</NavLink>
      <NavLink to="/admin/analytics">Analítica</NavLink>
      <NavLink to="/admin/marketing">Marketing</NavLink>
      <NavLink to="/admin/licencias">Licencias</NavLink>
      <NavLink to="/admin/opiniones">Opiniones</NavLink>
      <NavLink to="/admin/actividad">Actividad</NavLink>
    </nav>
  )
}

/** Users and their plans: find anyone, give or take back a plan by hand, add credits, name staff and admins. */
export function AdminUsers() {
  const { data: me } = useMe()
  const staff = me?.platform_role === 'admin' || me?.platform_role === 'staff'
  const [q, setQ] = useState('')
  const [plan, setPlan] = useState('')
  const [open, setOpen] = useState<string | null>(null)
  const query = useDeferredValue(q)
  const { data, error, isFetching } = useQuery({
    queryKey: ['admin-users', query, plan], enabled: staff, placeholderData: (p) => p,
    queryFn: () => api.get<{ users: AdminUser[]; more: boolean }>(`/api/admin/users?q=${encodeURIComponent(query)}&plan=${plan}`),
  })
  if (me && !staff) return <Navigate to="/app" replace />

  return (
    <AppShell>
      <section className="styles-head">
        <div>
          <p className="eyebrow">Administración</p>
          <h1 className="display sm">Usuarios</h1>
        </div>
      </section>
      <AdminTabs />
      <div className="admin-filters">
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar por correo o nombre…" aria-label="Buscar usuarios" />
        <label className="select-pill"><span className="sr-only">Plan</span>
          <select value={plan} onChange={(e) => setPlan(e.target.value)}>
            <option value="">Todos los planes</option>
            {Object.entries(PLAN_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </label>
        {isFetching && <span className="spinner" aria-label="Cargando" />}
      </div>
      {error && <p className="error" role="alert">{errorText(error, 'No se pudieron cargar los usuarios.')}</p>}
      {!data ? <div className="skeleton tall" /> : (
        <div className="admin-table" role="table" aria-label="Usuarios">
          <div className="admin-row head" role="row">
            <span role="columnheader">Usuario</span><span role="columnheader">Plan</span><span role="columnheader">Créditos</span>
            <span role="columnheader">Tomos</span><span role="columnheader">Alta</span><span role="columnheader">Último acceso</span>
          </div>
          {data.users.map((u) => (
            <button key={u.id} className="admin-row" role="row" onClick={() => setOpen(u.id)}>
              <span role="cell" className="who">
                {u.avatar_url ? <img src={u.avatar_url} alt="" width={28} height={28} className="avatar" referrerPolicy="no-referrer" />
                  : <span className="avatar initial">{(u.name ?? u.email)[0]?.toUpperCase()}</span>}
                <span><strong>{u.name ?? u.email}</strong><small className="muted">{u.email}</small></span>
                {u.role !== 'user' && <span className="pill info">{u.role === 'admin' ? 'Admin' : 'Equipo'}</span>}
              </span>
              <span role="cell"><span className={`plan-tag ${u.plan}`}>{PLAN_LABEL[u.plan]}</span>{u.stripe && <small className="muted"> · Stripe</small>}</span>
              <span role="cell" className="num">{u.credits.toLocaleString('es-MX')}</span>
              <span role="cell" className="num">{u.tomes}</span>
              <span role="cell" className="muted">{date(u.created_at)}</span>
              <span role="cell" className="muted">{date(u.last_sign_in_at)}</span>
            </button>
          ))}
          {!data.users.length && <p className="muted admin-empty">Nadie coincide con la búsqueda.</p>}
        </div>
      )}
      {open && <UserPanel id={open} admin={me?.platform_role === 'admin'} self={me?.id === open} onClose={() => setOpen(null)} />}
    </AppShell>
  )
}

function UserPanel({ id, admin, self, onClose }: { id: string; admin: boolean; self: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const { data: u } = useQuery({ queryKey: ['admin-user', id], queryFn: () => api.get<Detail>(`/api/admin/users/${id}`) })
  const [plan, setPlan] = useState('docente')
  const [months, setMonths] = useState(1)
  const [amount, setAmount] = useState(50)
  const [reason, setReason] = useState('Créditos de cortesía')
  const act = useMutation({
    mutationFn: ({ path, body }: { path: string; body: object }) => api.post<AdminUser>(`/api/admin/users/${id}/${path}`, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['admin-user', id] })
      void qc.invalidateQueries({ queryKey: ['admin-users'] })
    },
  })

  return (
    <div className="admin-sheet-wrap" onClick={onClose}>
      <aside className="admin-sheet" role="dialog" aria-modal="true" aria-label="Usuario" onClick={(e) => e.stopPropagation()}>
        <button className="icon close" onClick={onClose} aria-label="Cerrar">✕</button>
        {!u ? <div className="skeleton tall" /> : (
          <>
            <header>
              <h2>{u.name ?? u.email}</h2>
              <p className="muted small">{u.email} · alta {date(u.created_at)} · último acceso {date(u.last_sign_in_at)}</p>
            </header>
            <div className="admin-facts">
              <div><small className="muted">Plan</small><strong>{PLAN_LABEL[u.plan]}</strong>
                {u.plan !== 'prueba' && <small className="muted">{u.stripe ? 'Pagado con Stripe' : 'Asignado a mano'} · hasta {date(u.period_end)}</small>}</div>
              <div><small className="muted">Créditos</small><strong>{u.credits.toLocaleString('es-MX')}</strong></div>
              <div><small className="muted">Tomos</small><strong>{u.tomes}</strong></div>
            </div>
            {act.error && <p className="error" role="alert">{errorText(act.error, 'No se pudo guardar.')}</p>}

            {admin && (
              <section className="admin-actions">
                <h3>Plan</h3>
                {u.stripe && u.plan !== 'prueba' ? (
                  <p className="muted small">Este plan se paga con Stripe: cámbialo o cancélalo desde el panel de Stripe.</p>
                ) : (
                  <div className="admin-inline">
                    <select value={plan} onChange={(e) => setPlan(e.target.value)} aria-label="Plan">
                      <option value="docente">Docente</option><option value="creador">Creador</option><option value="editorial">Editorial</option>
                    </select>
                    <select value={months} onChange={(e) => setMonths(Number(e.target.value))} aria-label="Duración">
                      {[1, 3, 6, 12].map((m) => <option key={m} value={m}>{m} {m === 1 ? 'mes' : 'meses'}</option>)}
                    </select>
                    <button className="primary" disabled={act.isPending} onClick={() => act.mutate({ path: 'plan', body: { plan, months } })}>Asignar plan</button>
                    {u.plan !== 'prueba' && <button className="ghost" disabled={act.isPending} onClick={() => act.mutate({ path: 'plan', body: { plan: null } })}>Quitar plan</button>}
                  </div>
                )}
                <p className="muted small">Asignar un plan le da sus créditos de todos los meses elegidos; al terminar el periodo vuelve a Prueba.</p>

                <h3>Créditos de cortesía</h3>
                <div className="admin-inline">
                  <input type="number" min={1} max={100000} value={amount} onChange={(e) => setAmount(Math.max(1, Number(e.target.value) || 1))} aria-label="Créditos" />
                  <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={200} aria-label="Motivo" />
                  <button className="ghost" disabled={act.isPending || reason.trim().length < 3} onClick={() => act.mutate({ path: 'credits', body: { amount, reason: reason.trim() } })}>Dar créditos</button>
                </div>
                <p className="muted small">Duran 12 meses y se usan después de los del plan.</p>

                <h3>Acceso al panel</h3>
                <div className="admin-inline">
                  <select value={u.role} disabled={self || act.isPending} onChange={(e) => act.mutate({ path: 'role', body: { role: e.target.value } })} aria-label="Rol">
                    {Object.entries(ROLE_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                  </select>
                  {self && <small className="muted">Es tu cuenta: no puedes quitarte el acceso.</small>}
                </div>
              </section>
            )}

            <section>
              <h3>Tomos recientes</h3>
              {u.series.length ? (
                <ul className="admin-list">{u.series.map((s) => (
                  <li key={s.id}><span>{s.title}</span><small className="muted">{s.genre ? GENRE_LABEL[s.genre] : '—'}{s.preview ? ' · vista previa' : ''} · {date(s.created_at)}</small></li>
                ))}</ul>
              ) : <p className="muted small">Todavía no crea tomos.</p>}
            </section>
            <section>
              <h3>Movimientos de créditos</h3>
              {u.ledger.length ? (
                <ul className="admin-list">{u.ledger.map((l, i) => (
                  <li key={i}><span>{l.reason}</span><small className={l.delta > 0 ? 'plus' : 'muted'}>{l.delta > 0 ? '+' : ''}{l.delta} · {date(l.created_at)}</small></li>
                ))}</ul>
              ) : <p className="muted small">Sin movimientos.</p>}
            </section>
          </>
        )}
      </aside>
    </div>
  )
}
