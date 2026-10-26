import { createApiClient } from './api'
import { supabase } from './supabase'

export const api = createApiClient({
  fetchImpl: (...args) => fetch(...args),
  getAccessToken: async () => (await supabase.auth.getSession()).data.session?.access_token ?? null,
  refreshAccessToken: async () => (await supabase.auth.refreshSession()).data.session?.access_token ?? null,
  onSessionExpired: () => void supabase.auth.signOut(),
})

export type Me = {
  id: string
  email: string
  display_name: string | null
  avatar_url: string | null
  quota: { daily_lessons: number; used_today: number; remaining_today: number }
}
