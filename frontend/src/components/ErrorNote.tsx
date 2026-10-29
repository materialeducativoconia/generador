import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { saveWithGoogle } from '../auth/google'
import { ApiError } from '../lib/api'

const UPGRADE = new Set(['insufficient_credits', 'plan_required', 'too_many_running'])

/** An API error as text; when the plan or the credits are the problem, with the way out next to it. */
export function errorText(e: unknown, fallback: string): ReactNode {
  if (!(e instanceof ApiError)) return fallback
  if (e.code === 'account_required') {
    return <>{e.message} <button type="button" className="link-button upgrade-link" onClick={() => void saveWithGoogle(window.location.pathname)}>Entrar con Google</button></>
  }
  if (!UPGRADE.has(e.code)) return e.message
  return <>{e.message} <Link to="/app/plan" className="upgrade-link">{e.code === 'insufficient_credits' ? 'Comprar créditos' : 'Ver planes'}</Link></>
}
