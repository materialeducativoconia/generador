import { useEffect, useState } from 'react'
import { ApiError } from '../lib/api'
import { api, type Me } from '../lib/apiClient'
import { supabase } from '../lib/supabase'

export function Home() {
  const [me, setMe] = useState<Me | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .get<Me>('/api/me')
      .then(setMe)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'No pudimos cargar tu perfil.'))
  }, [])

  return (
    <main className="home">
      <header className="topbar">
        <span className="brand">Generador</span>
        <button className="link-button" onClick={() => void supabase.auth.signOut()}>
          Cerrar sesión
        </button>
      </header>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!me && !error && <p className="muted">Cargando…</p>}
      {me && (
        <section className="profile">
          {me.avatar_url && <img src={me.avatar_url} alt="" width={56} height={56} referrerPolicy="no-referrer" />}
          <div>
            <h1>Hola, {me.display_name ?? me.email}</h1>
            <p className="muted">
              Hoy puedes generar {me.quota.remaining_today} de {me.quota.daily_lessons} lecciones.
            </p>
          </div>
        </section>
      )}
    </main>
  )
}
