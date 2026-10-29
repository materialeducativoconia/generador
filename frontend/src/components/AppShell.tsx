import { useState, type ReactNode } from 'react'
import { Link, NavLink } from 'react-router'
import { useMe } from '../lib/queries'
import { supabase } from '../lib/supabase'

const NAV: [string, string, ReactNode][] = [
  ['/app', 'Biblioteca', <path key="i" d="M4 5h4v14H4zM10 5h4v14h-4zM16.5 5.5l3.5 1-3 12.5-3.5-1z" />],
  ['/app/identidades', 'Identidades', <path key="i" d="M12 3l2.6 5.6 6 .7-4.5 4.1 1.2 6L12 16.4 6.7 19.4l1.2-6L3.4 9.3l6-.7z" />],
  ['/app/estilos', 'Estilos', <path key="i" d="M12 3a9 9 0 1 0 0 18c1 0 1.5-.7 1.5-1.5 0-1.2-1-1.5-1-2.5s.8-1.5 2-1.5h2A4.5 4.5 0 0 0 21 11c0-4.4-4-8-9-8zM7.5 12h.01M10 8h.01M15 8h.01" />],
  ['/app/plan', 'Plan y créditos', <path key="i" d="M3 7h18v12H3zM3 11h18M7 15h3" />],
  ['/app/perfil', 'Perfil', <path key="i" d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21c1.5-4 4.5-6 8-6s6.5 2 8 6" />],
]

export function AppShell({ children }: { children: ReactNode }) {
  const { data: me } = useMe()
  const [open, setOpen] = useState(false)
  const name = me?.display_name || me?.email
  return (
    <div className={`shell${open ? ' nav-open' : ''}`}>
      <header className="topbar">
        <button className="icon menu" aria-label="Abrir menú" aria-expanded={open} onClick={() => setOpen(!open)}>
          <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
        </button>
        <Link to="/app" className="brand"><Logo /><span>Material Educativo IA</span></Link>
        {me && <Link to="/app/plan" className="quota"><span className="quota-dot" />{me.credits}</Link>}
      </header>
      <aside className="sidenav" aria-label="Navegación" onClick={(e) => { if ((e.target as HTMLElement).closest('a')) setOpen(false) }}>
        <Link to="/app" className="brand"><Logo /><span>Material Educativo IA</span></Link>
        <nav>
          {NAV.map(([to, label, icon]) => (
            <NavLink key={to} to={to} end={to === '/app'} className="nav-item">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
                   strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{icon}</svg>
              {label}
            </NavLink>
          ))}
          {(me?.platform_role === 'admin' || me?.platform_role === 'staff') && (
            <NavLink to="/admin/analytics" className="nav-item">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
                   strokeLinecap="round" aria-hidden="true"><path d="M4 20V10M10 20V4M16 20v-7M21 20H3" /></svg>
              Analítica
            </NavLink>
          )}
        </nav>
        {me && (
          <div className="sidenav-foot">
            <Link to="/app/plan" className="wallet-mini">
              <span><strong>{me.credits}</strong> créditos</span>
              <span className="muted">Plan {me.plan.label}</span>
              {me.plan.key === 'prueba' && <span className="wallet-cta">Elegir plan</span>}
            </Link>
            <div className="me-row">
              <Link to="/app/perfil" className="me-link">
                {me.avatar_url ? <img className="avatar" src={me.avatar_url} alt="" width={28} height={28} referrerPolicy="no-referrer" />
                  : <span className="avatar initial">{(name ?? '?').slice(0, 1).toUpperCase()}</span>}
                <span className="me-name">{name}</span>
              </Link>
              <button className="ghost small" onClick={() => void supabase.auth.signOut()}>Salir</button>
            </div>
          </div>
        )}
      </aside>
      {open && <div className="scrim" onClick={() => setOpen(false)} />}
      <main className="page">{children}</main>
    </div>
  )
}

export function Logo() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
      <rect x="3" y="3" width="13" height="18" rx="2.5" fill="currentColor" opacity=".18" />
      <rect x="8" y="3" width="13" height="18" rx="2.5" fill="currentColor" />
      <path d="M11.5 8.5h6M11.5 12h6M11.5 15.5h3.5" stroke="var(--bg)" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  )
}

const STATUS: Record<string, [string, string]> = {
  outlining: ['Planificando', 'busy'],
  outline_ready: ['Esquema listo', 'info'],
  outline_failed: ['Error en el esquema', 'bad'],
  generating: ['Generando', 'busy'],
  needs_attention: ['Requiere atención', 'bad'],
  ready: ['Listo', 'ok'],
  pending: ['Pendiente', 'idle'],
  queued: ['En cola', 'idle'],
  generated: ['Lista', 'ok'],
  failed: ['Error', 'bad'],
  edited: ['Editada', 'ok'],
  approved: ['Revisada', 'ok'],
}

export function StatusPill({ status }: { status: string }) {
  const [label, tone] = STATUS[status] ?? [status, 'idle']
  return <span className={`pill ${tone}`}>{label}</span>
}
