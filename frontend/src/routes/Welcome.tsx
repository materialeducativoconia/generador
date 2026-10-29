import { useState } from 'react'
import { Navigate, useSearchParams } from 'react-router'
import { useAuth } from '../auth/context'
import { signInWithGoogle } from '../auth/google'
import { Logo } from '../components/AppShell'
import { LandingComposer } from '../components/LandingComposer'
import { PUBLIC_PLANS } from '../lib/pricing'
import { TOPICS, topicHref } from '../lib/topics'

const ERRORS: Record<string, string> = {
  cancelled: 'No se completó el inicio de sesión.',
  failed: 'No pudimos iniciar sesión con Google. Inténtalo de nuevo.',
}

export function Welcome() {
  const { session, loading } = useAuth()
  const [params] = useSearchParams()
  const [starting, setStarting] = useState(false)
  const [previewing, setPreviewing] = useState(false)  // the visitor's anonymous session must not bounce them to /app
  const [error, setError] = useState<string | null>(() => ERRORS[params.get('error') ?? ''] ?? null)

  if (!loading && session && !previewing) return <Navigate to="/app" replace />

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
      <p className="lede">Describe lo que necesitas y mira gratis tu portada ilustrada, el índice y una muestra de la primera sección. Sin registrarte.</p>
      <LandingComposer onStart={setPreviewing} />
      <p className="fine-print muted">
        ¿Ya tienes cuenta?{' '}
        <button className="link-button" onClick={start} disabled={starting || loading}>{starting ? 'Abriendo Google…' : 'Entrar con Google'}</button>
      </p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
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
          <li><strong>Describe y mira la vista previa</strong><span>El tema, el nivel y el formato: «cuadernillo de sumas para primero», «libro para colorear de dinosaurios».</span></li>
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
        <p className="muted">La vista previa es gratis y sin tarjeta. Con un plan generas el tomo completo y lo descargas. 1 crédito ≈ 1 página; si algo falla, te devolvemos los créditos.</p>
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
