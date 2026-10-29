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
  email: string | null
  anonymous: boolean
  display_name: string | null
  avatar_url: string | null
  quota: { daily_lessons: number; used_today: number; remaining_today: number }
  platform_role: 'user' | 'staff' | 'admin'
  author_name: string | null
  school: string | null
  onboarded: boolean
  onboarding: { use: 'aula' | 'venta' | 'escuela' | 'casa' | null; levels: string[]; subjects: string[] } | null
  organization: { name: string; role: 'owner' | 'editor' | 'viewer'; logo_url: string | null }
  plan: {
    key: 'prueba' | 'docente' | 'creador' | 'editorial'
    label: string
    status: string | null
    word: boolean
    logo: boolean
    print_edition: boolean
    styles: number
    identities: number
    max_pages: number
    watermark: boolean
    commercial: boolean
  }
  credits: number
}
