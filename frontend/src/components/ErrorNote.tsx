import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { ApiError } from '../lib/api'

const UPGRADE = new Set(['insufficient_credits', 'plan_required', 'too_many_running'])

/** An API error as text; when the plan or the credits are the problem, with the way out next to it. */
export function errorText(e: unknown, fallback: string): ReactNode {
  if (!(e instanceof ApiError)) return fallback
  if (!UPGRADE.has(e.code)) return e.message
  return <>{e.message} <Link to="/app/plan" className="upgrade-link">{e.code === 'insufficient_credits' ? 'Comprar créditos' : 'Ver planes'}</Link></>
}
