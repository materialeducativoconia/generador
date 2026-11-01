import { useState } from 'react'
import { Navigate, useSearchParams } from 'react-router'
import { useAuth } from '../auth/context'
import { rememberReturnTo, saveWithGoogle, signInWithGoogle } from '../auth/google'
import { Logo } from '../components/AppShell'
import { LandingComposer } from '../components/LandingComposer'
import { Showcase } from '../components/Showcase'
import { useSeriesList } from '../lib/queries'
import { PUBLIC_PLAN_INFO } from '../lib/pricing'
import { PlanCards } from '../components/PlanCards'
import { TOPICS, topicHref } from '../lib/topics'

const ERRORS: Record<string, string> = {
  cancelled: 'No se completó el inicio de sesión.',
  failed: 'No pudimos iniciar sesión con Google. Inténtalo de nuevo.',
}

function ReturningVisitor() {
  const { data: series } = useSeriesList()
  return series?.length ? <Navigate to={`/app/tomos/${series[0].id}`} replace /> : null
}

export function Welcome() {
  const { session, loading } = useAuth()
  const [params] = useSearchParams()
  const [starting, setStarting] = useState(false)
  const [previewing, setPreviewing] = useState(false)  // the visitor's anonymous session must not bounce them to /app
  const [error, setError] = useState<string | null>(() => ERRORS[params.get('error') ?? ''] ?? null)
  const [joining, setJoining] = useState<string | null>(null)  // the plan whose button is signing in

  // A signed-in user goes to the studio; a visitor who already has a preview goes back to it (VisitorHome).
  if (!loading && session && !previewing && !session.user.is_anonymous) return <Navigate to="/app" replace />

  /** A plan's button: sign in with Google (a visitor's preview comes along), then the plan page opens Stripe. */
  async function subscribe(plan: string) {
    setJoining(plan)
    setError(null)
    const next = `/app/plan?plan=${plan}`
    try {
      if (session?.user.is_anonymous) {
        setPreviewing(true)
        await saveWithGoogle(next)
      } else {
        rememberReturnTo(next)
        const { error } = await signInWithGoogle()
        if (error) throw error
      }
    } catch {
      setError(ERRORS.failed)
      setJoining(null)
    }
  }

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
      {session?.user.is_anonymous && !previewing && <ReturningVisitor />}
      <span className="brand"><Logo /><span>Jelyx Docs</span></span>
      <h1 className="display">Material educativo de <span className="jelly">cualquier tema</span>, listo para imprimir.</h1>
      <p className="lede">Describe lo que necesitas y mira gratis tu portada ilustrada y el índice de tu tomo. Sin registrarte.</p>
      <LandingComposer onStart={setPreviewing} />
      <Showcase />
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
        <PlanCards plans={PUBLIC_PLAN_INFO} action={(p) => (
          <button className={`${p.key === 'creador' ? 'primary' : 'ghost'} block`} onClick={() => void subscribe(p.key)} disabled={!!joining}>
            {joining === p.key ? 'Abriendo…' : 'Suscribirme'}
          </button>
        )} />
      </section>
      <footer className="landing-foot muted small">
        <a href="/material-educativo">Material educativo por tema</a> · <a href="#planes">Planes</a>
      </footer>
    </div>
    </>
  )
}
