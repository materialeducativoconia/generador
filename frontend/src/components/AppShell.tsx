import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { useMe } from '../lib/queries'
import { supabase } from '../lib/supabase'

export function AppShell({ children }: { children: ReactNode }) {
  const { data: me } = useMe()
  return (
    <div className="shell">
      <header className="topbar">
        <Link to="/app" className="brand">
          <Logo />
          <span>Material Educativo IA</span>
        </Link>
        <div className="topbar-r">
          <Link to="/app/identidades" className="ghost small">Identidades</Link>
          <Link to="/app/estilos" className="ghost small">Estilos</Link>
          {me && (
            <Link to="/app/plan" className="quota" title={`Plan ${me.plan.label} · créditos disponibles`}>
              <span className="quota-dot" />
              {me.credits} créditos · {me.plan.label}
            </Link>
          )}
          {me?.avatar_url && <img className="avatar" src={me.avatar_url} alt="" width={28} height={28} referrerPolicy="no-referrer" />}
          <button className="ghost small" onClick={() => void supabase.auth.signOut()}>
            Salir
          </button>
        </div>
      </header>
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
