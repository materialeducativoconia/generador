import { useState } from 'react'
import { Navigate, useSearchParams } from 'react-router'
import { useAuth } from '../auth/context'
import { signInWithGoogle } from '../auth/google'
import { Logo } from '../components/AppShell'
import { PUBLIC_PLANS, TRIAL_CREDITS } from '../lib/pricing'
import { TOPICS, topicHref } from '../lib/topics'

const ERRORS: Record<string, string> = {
  cancelled: 'No se completó el inicio de sesión.',
  failed: 'No pudimos iniciar sesión con Google. Inténtalo de nuevo.',
}

export function Welcome() {
  const { session, loading } = useAuth()
  const [params] = useSearchParams()
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(() => ERRORS[params.get('error') ?? ''] ?? null)

  if (!loading && session) return <Navigate to="/app" replace />

  async function start() {
    setStarting(true)
    setError(null)
    const { error } = await signInWithGoogle()
    // On success the browser is already leaving for Google; only failures come back here.
    if (error) {
      setError(ERRORS.failed)
      setStarting(false)
    }
  }

  return (
    <>
    <main className="welcome">
      <div className="orb" aria-hidden="true" />
      <span className="brand"><Logo /><span>Material Educativo IA</span></span>
      <h1 className="display">Material educativo de cualquier tema, listo para imprimir.</h1>
      <p className="lede">Libros para colorear, cuadernillos de fichas, métodos paso a paso y secuencias didácticas. Tú describes, un equipo de agentes lo planifica, escribe y maqueta.</p>
      <button className="google-button" onClick={start} disabled={starting || loading}>
        <GoogleLogo />
        {starting ? 'Abriendo Google…' : 'Continuar con Google'}
      </button>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <p className="fine-print muted">Sirve tu cuenta de Gmail o la de tu centro educativo.</p>
      <ul className="welcome-genres" aria-label="Qué puedes crear">
        <li>Libro para colorear</li>
        <li>Cuadernillo de fichas</li>
        <li>Método paso a paso</li>
        <li>Secuencia didáctica</li>
      </ul>
    </main>
    <div className="landing">
      <section>
        <h2>Cómo funciona</h2>
        <ol className="landing-steps">
          <li><strong>Describe</strong><span>El tema, el nivel y el formato: «cuadernillo de sumas para primero», «libro para colorear de dinosaurios».</span></li>
          <li><strong>Revisa el esquema</strong><span>Un equipo de agentes propone las secciones; las ajustas antes de generar.</span></li>
          <li><strong>Descarga</strong><span>PDF listo para imprimir o Word editable, con portada ilustrada, tu firma y tu identidad editorial.</span></li>
        </ol>
      </section>
      <section>
        <h2>Ideas para empezar</h2>
        <ul className="landing-topics">
          {TOPICS.map((t) => <li key={t.slug}><a href={topicHref(t)}>{t.title}</a></li>)}
        </ul>
      </section>
      <section id="planes">
        <h2>Planes</h2>
        <p className="muted">Empieza gratis con {TRIAL_CREDITS} créditos, sin tarjeta. 1 crédito ≈ 1 página; si algo falla, te devolvemos los créditos.</p>
        <div className="landing-plans">
          {PUBLIC_PLANS.map((p) => (
            <article key={p.key} className={`panel${p.key === 'creador' ? ' featured' : ''}`}>
              <h3>{p.label}</h3>
              <p className="muted small">{p.for}</p>
              <p className="landing-price">${p.price} <span className="muted small">USD/mes</span></p>
              <ul>{p.features.map((f) => <li key={f}>{f}</li>)}</ul>
            </article>
          ))}
        </div>
      </section>
      <footer className="landing-foot muted small">
        <a href="/material-educativo">Material educativo por tema</a> · <a href="#planes">Planes</a>
      </footer>
    </div>
    </>
  )
}

function GoogleLogo() {
  return (
    <svg viewBox="0 0 48 48" width="18" height="18" aria-hidden="true">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  )
}
