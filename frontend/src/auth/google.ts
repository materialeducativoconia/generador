import { supabase } from '../lib/supabase'
import { api } from '../lib/apiClient'

const RETURN_TO_KEY = 'auth:returnTo'

export function rememberReturnTo(path: string) {
  try {
    sessionStorage.setItem(RETURN_TO_KEY, path)
  } catch {
    // Storage can be unavailable (private mode); we just land on the home page instead.
  }
}

export function takeReturnTo(): string {
  try {
    const path = sessionStorage.getItem(RETURN_TO_KEY)
    sessionStorage.removeItem(RETURN_TO_KEY)
    // Only same-app paths: never let a stored value redirect off-site.
    if (path?.startsWith('/') && !path.startsWith('//')) return path
  } catch {
    // fall through
  }
  return '/app'
}

export function signInWithGoogle() {
  return supabase.auth.signInWithOAuth({
    provider: 'google',
    options: { redirectTo: `${window.location.origin}/auth/callback` },
  })
}

const CLAIM_KEY = 'auth:claim'

/** A landing visitor starts as an anonymous Supabase user: their free preview needs no account yet. */
export async function ensureVisitorSession(captchaToken?: string) {
  if ((await supabase.auth.getSession()).data.session) return
  const { error } = await supabase.auth.signInAnonymously({ options: captchaToken ? { captchaToken } : undefined })
  if (error) throw new Error('No pudimos empezar tu vista previa. Recarga la página e inténtalo de nuevo.')
}

/** The visitor signs in with Google; a claim code carries their preview to that account (new or existing). */
export async function saveWithGoogle(returnTo: string) {
  const { code } = await api.post<{ code: string }>('/api/claims')
  try {
    localStorage.setItem(CLAIM_KEY, code)
  } catch {
    // without storage the preview stays with the anonymous visitor; signing in still works
  }
  rememberReturnTo(returnTo)
  return signInWithGoogle()
}

/** After Google: move the anonymous visitor's tomes here. Safe to call when there is nothing to claim. */
export async function redeemClaim() {
  let code: string | null = null
  try {
    code = localStorage.getItem(CLAIM_KEY)
    localStorage.removeItem(CLAIM_KEY)
  } catch {
    return
  }
  if (code) await api.post(`/api/claims/${encodeURIComponent(code)}`).catch(() => undefined)
}
