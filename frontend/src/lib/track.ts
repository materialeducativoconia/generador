// What people do in the app, for the team to learn from (/admin/actividad): pages opened and the key actions.
// Events wait in a queue and go in batches; a signed-out visitor sends nothing.
import { useEffect } from 'react'
import { useLocation } from 'react-router'
import { api } from './apiClient'
import { supabase } from './supabase'

type Tracked = { event: string; path: string; props: Record<string, unknown> }
const queue: Tracked[] = []
let timer: ReturnType<typeof setTimeout> | null = null

export function track(event: string, props: Record<string, unknown> = {}) {
  queue.push({ event, path: location.pathname.slice(0, 200), props })
  if (queue.length >= 20) void flush()
  else timer ??= setTimeout(() => void flush(), 8000)
}

async function flush() {
  if (timer) clearTimeout(timer)
  timer = null
  if (!queue.length || !(await supabase.auth.getSession()).data.session) return
  const events = queue.splice(0, 30)
  await api.post('/api/activity', { events }).catch(() => {})  // learning data: never in the user's way
}

if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') void flush() })
}

/** One page_view per route the user opens (ids in the path stay: they say which tome). */
export function usePageViews() {
  const { pathname } = useLocation()
  useEffect(() => { track('page_view') }, [pathname])
}
