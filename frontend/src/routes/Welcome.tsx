import { useState } from 'react'
import { Navigate, useSearchParams } from 'react-router'
import { useAuth } from '../auth/context'
import { rememberReturnTo, saveWithGoogle, signInWithGoogle } from '../auth/google'
import { Logo } from '../components/AppShell'
import { LandingComposer } from '../components/LandingComposer'
import { SHOWCASE_BASE, Showcase } from '../components/Showcase'
import { useSeriesList } from '../lib/queries'
import { PUBLIC_PLAN_INFO } from '../lib/pricing'
import { PlanCards } from '../components/PlanCards'
import { TOPICS, topicHref } from '../lib/topics'
import { HOUSE_STYLES, sampleOf } from '../lib/houseStyles'
import { usePageTitle } from '../lib/seo'

const ERRORS: Record<string, string> = {
  cancelled: 'No se completó el inicio de sesión.',
  failed: 'No pudimos iniciar sesión con Google. Inténtalo de nuevo.',
}

function ReturningVisitor() {
  const { data: series } = useSeriesList()
  return series?.length ? <Navigate to={`/app/tomos/${series[0].id}`} replace /> : null
}

export function Welcome() {
  usePageTitle('Jelyx Docs: libros educativos ilustrados para imprimir, hechos con IA')
  const { session, loading } = useAuth()
  const [params, setParams] = useSearchParams()
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

  /** A style card: a free style fills the request box's picker; a plan style goes to the plans. */
  function pickStyle(key: string) {
    if (!HOUSE_STYLES.find((s) => s.key === key)?.free) {
      document.getElementById('planes')?.scrollIntoView({ behavior: 'smooth' })
      return
    }
    setParams((p) => { p.set('estilo', key); return p }, { replace: true, preventScrollReset: true })
    const box = document.querySelector<HTMLTextAreaElement>('#crear textarea')
    box?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    box?.focus({ preventScroll: true })
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
    <header className="welcome-top">
      <a href="/laminas" className="welcome-top-link">Láminas gratis</a>
      <a href="#planes" className="welcome-top-link">Planes</a>
      <button className="welcome-login" onClick={start} disabled={starting || loading}>{starting ? 'Abriendo…' : 'Entrar'}</button>
    </header>
    <main className="welcome">
      <div className="orb" aria-hidden="true" />
      {session?.user.is_anonymous && !previewing && <ReturningVisitor />}
      <span className="brand"><Logo /><span>Jelyx Docs</span></span>
      <h1 className="display">Libros educativos ilustrados, <span className="jelly">listos en minutos</span>.</h1>
      <p className="lede">
        Escribe un tema y recibe un tomo completo: portada ilustrada, páginas con dibujos, actividades y solucionario.
        Calidad de editorial, para tu aula o para vender.
      </p>
      <LandingComposer onStart={setPreviewing} />
      <ul className="trust" aria-label="Incluye">
        <li><Check />Ves tu tomo real antes de pagar</li>
        <li><Check />PDF listo para imprimir</li>
        <li><Check />Word editable</li>
      </ul>
      {error && <p className="error" role="alert">{error}</p>}
    </main>
    <Showcase />
    <div className="landing">
      <section>
        <p className="eyebrow">Estilos de ilustración</p>
        <h2 className="l-h">El mismo tema, el estilo que tu clase merece.</h2>
        <p className="l-lede">Ilustraciones con el acabado de los libros de las mejores editoriales, no de una imagen genérica. Así se ve el mismo tema en seis estilos.</p>
        <ul className="l-styles">
          {HOUSE_STYLES.map((s) => (
            <li key={s.key}>
              <button type="button" onClick={() => pickStyle(s.key)}>
                <img src={sampleOf(s.key)} alt={`El sistema solar en estilo ${s.name}`} loading="lazy" width={717} height={960} />
                <strong>{s.name}</strong><span>{s.desc}</span>
                <span className="l-style-use">{s.free ? 'Probar gratis en este estilo →' : 'Con un plan →'}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="l-intro">
        <p className="eyebrow">Por qué Jelyx</p>
        <h2 className="l-h">Deja de pasar el fin de semana armando material.</h2>
        <p className="l-lede">Buscar imágenes, maquetar, corregir y volver a imprimir. Ahora describes lo que quieres y recibes un libro terminado, hecho para tu tema y tu grupo.</p>
        <div className="l-values">
          {VALUES.map(([t, d], i) => (
            <article key={t} className="l-value"><span className="l-n">{String(i + 1).padStart(2, '0')}</span><h3>{t}</h3><p>{d}</p></article>
          ))}
        </div>
      </section>

      <section>
        <p className="eyebrow">Qué trae cada tomo</p>
        <h2 className="l-h">Todo lo que haría una editorial, en un solo clic.</h2>
        <ul className="l-features">
          {FEATURES.map(([t, d]) => <li key={t}><Check /><div><strong>{t}</strong><span>{d}</span></div></li>)}
        </ul>
      </section>

      <section>
        <p className="eyebrow">Formatos</p>
        <h2 className="l-h">Un formato para cada clase.</h2>
        <ul className="l-formats">
          {FORMAT_CARDS.map(([t, d]) => <li key={t}><strong>{t}</strong><span>{d}</span></li>)}
        </ul>
      </section>

      <section>
        <p className="eyebrow">Para quién</p>
        <h2 className="l-h">Hecho para quien enseña, y para quien vende lo que enseña.</h2>
        <div className="l-who">
          {WHO.map(([t, d, plan]) => (
            <article key={t}><span className="pill info">{plan}</span><h3>{t}</h3><p>{d}</p></article>
          ))}
        </div>
      </section>

      <section>
        <p className="eyebrow">Cómo funciona</p>
        <h2 className="l-h">De la idea al libro impreso en tres pasos.</h2>
        <ol className="landing-steps">
          <li><strong>Cuéntanos qué necesitas</strong><span>«Libro ilustrado del sistema solar para primero», «cuadernillo de sumas hasta el 20». Tú eliges el nivel y el formato.</span></li>
          <li><strong>Mira tu tomo, gratis</strong><span>En un par de minutos ves tu portada y tus páginas ilustradas. Sin registrarte y sin tarjeta.</span></li>
          <li><strong>Hazlo tuyo y descárgalo</strong><span>Ajusta secciones y textos sin gastar créditos, y descarga en PDF a color, blanco y negro o para imprenta.</span></li>
        </ol>
      </section>

      <section>
        <p className="eyebrow">Ideas</p>
        <h2 className="l-h">¿Por dónde empezar? Elige un tema.</h2>
        <ul className="l-topics">
          {TOPICS.map((t) => (
            <li key={t.slug}>
              <a href={topicHref(t)}>
                <img src={`${SHOWCASE_BASE}/${t.cover}.webp`} alt="" loading="lazy" decoding="async" width={120} height={170} />
                <span className="eyebrow">{t.name}</span>
                <strong>{t.title}</strong>
              </a>
            </li>
          ))}
        </ul>
      </section>

      <section id="planes">
        <p className="eyebrow">Planes</p>
        <h2 className="l-h">Empieza hoy. Cancela cuando quieras.</h2>
        <p className="l-lede">Tu vista previa es gratis. Con un plan generas tomos completos, los editas y los descargas. 1 crédito ≈ 1 página, y si una generación falla te devolvemos los créditos.</p>
        <PlanCards plans={PUBLIC_PLAN_INFO} action={(p) => (
          <button className={`${p.key === 'creador' ? 'primary' : 'ghost'} block`} onClick={() => void subscribe(p.key)} disabled={!!joining}>
            {joining === p.key ? 'Abriendo…' : 'Suscribirme'}
          </button>
        )} />
      </section>

      <section className="l-faq">
        <p className="eyebrow">Preguntas frecuentes</p>
        <h2 className="l-h">Lo que suelen preguntarnos.</h2>
        {FAQ.map(([q, a]) => <details key={q}><summary>{q}</summary><p>{a}</p></details>)}
      </section>

      <section className="l-cta">
        <h2>Tu próximo libro está a un párrafo de distancia.</h2>
        <p>Escribe el tema y míralo terminado antes de pagar.</p>
        <a className="l-cta-btn" href="#crear" onClick={focusComposer}>Crear mi vista previa gratis</a>
      </section>

      <footer className="landing-foot muted small">
        <a href="/material-educativo">Material educativo por tema</a> · <a href="#planes">Planes</a> ·{' '}
        <button className="link-button" onClick={start} disabled={starting || loading}>{starting ? 'Abriendo Google…' : 'Entrar con Google'}</button>
      </footer>
    </div>
    </>
  )
}

/** The closing call to action brings the visitor back to the request box, ready to type. */
function focusComposer(e: React.MouseEvent) {
  e.preventDefault()
  const box = document.querySelector<HTMLTextAreaElement>('#crear textarea')
  box?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  box?.focus({ preventScroll: true })
}

function Check() {
  return <svg className="ck" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
}

const VALUES: [string, string][] = [
  ['Minutos, no fines de semana', 'Del tema al libro terminado en una sola sesión. Tú decides; Jelyx investiga, escribe, ilustra y maqueta.'],
  ['Se ve como libro de editorial', 'Portada pintada para tu tema, ilustraciones en cada página, tipografía y colores cuidados. Nada de plantillas genéricas.'],
  ['Tuyo para usar o vender', 'Imprímelo para tu grupo o, desde el plan Creador, véndelo en Amazon KDP, Teachers Pay Teachers o tu tienda, sin marca de agua.'],
]

const FEATURES: [string, string][] = [
  ['Portada ilustrada única', 'Pintada para tu tema, con el título en la tipografía de tu tomo.'],
  ['Ilustraciones en cada página', 'Láminas a página completa, dibujos para colorear y material para contar.'],
  ['Actividades con solucionario', 'Ejercicios de lo fácil a lo difícil, y las respuestas al final para ti.'],
  ['Contenido revisado', 'Datos verificados en fuentes y un editor que corrige cada sección.'],
  ['Edita sin gastar créditos', 'Cambia textos, secciones y páginas antes de descargar.'],
  ['Imprime como quieras', 'A color, en blanco y negro para ahorrar tinta, o listo para imprenta y KDP.'],
]

const FORMAT_CARDS: [string, string][] = [
  ['Libro ilustrado', 'Preguntas y respuestas con láminas a página completa, como los libros de divulgación infantil.'],
  ['Cuento ilustrado', 'Una historia con su protagonista, para leer en voz alta, y al final datos reales del tema.'],
  ['Libro para colorear', 'Dibujos de línea limpia para manos pequeñas, con el nombre de cada figura.'],
  ['Cuadernillo de fichas', 'Práctica lista para fotocopiar: trazos, operaciones, sopas de letras y más.'],
  ['Método paso a paso', 'Una habilidad de principio a fin: piano, caligrafía, dibujo, un idioma.'],
  ['Secuencia didáctica', 'Clases completas con objetivos, actividades y evaluación.'],
]

const WHO: [string, string, string][] = [
  ['Docentes', 'Material a la medida de tu grupo cada semana, sin pasar las tardes en el procesador de textos.', 'Docente'],
  ['Creadores de contenido', 'Una colección de libros con tu marca, tu logo y licencia comercial para venderlos.', 'Creador'],
  ['Escuelas y editoriales', 'Series por niveles, varias identidades editoriales y tu equipo trabajando a la vez.', 'Editorial'],
]

const FAQ: [string, string][] = [
  ['¿Puedo probar antes de pagar?', 'Sí. Escribe tu tema y ves tu tomo real, con portada y páginas ilustradas, sin registrarte ni dar tarjeta.'],
  ['¿Puedo vender lo que creo?', 'Desde el plan Creador tienes licencia comercial, sin marca de agua, Word editable y edición para imprenta. El plan Docente es para usarlo en tu aula.'],
  ['¿Puedo cambiar el contenido?', 'Sí. Antes de descargar ajustas las secciones y el texto, y editar no gasta créditos.'],
  ['¿Qué es un crédito?', 'Aproximadamente una página terminada. Si una generación falla, te devolvemos los créditos.'],
  ['¿Puedo cancelar?', 'Cuando quieras, desde tu cuenta. Tus tomos se quedan guardados.'],
]
