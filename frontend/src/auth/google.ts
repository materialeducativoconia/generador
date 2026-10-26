import { supabase } from '../lib/supabase'

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
