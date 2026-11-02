import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { useAuth } from '../auth/context'
import { rememberReturnTo, saveWithGoogle, signInWithGoogle } from '../auth/google'
import { Logo } from '../components/AppShell'
import { errorText } from '../components/ErrorNote'
import { api } from '../lib/apiClient'
import { HOUSE_STYLES } from '../lib/houseStyles'

export type Plate = { id: string; slug: string; title: string; answer: string; topic: string; audience: string; style: string; style_name: string; image_url: string; downloads: number }

function LibraryShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="library">
      <header className="library-top">
        <Link to="/" className="brand"><Logo /><span>Jelyx Docs</span></Link>
        <nav><Link to="/laminas">Láminas gratis</Link><Link to="/#planes">Planes</Link><Link to="/#crear" className="welcome-login">Crear un libro</Link></nav>
      </header>
      {children}
    </div>
  )
}

/** The free plate library: browse by topic and style, open a plate to download it. */
export function Library() {
  const [params, setParams] = useSearchParams()
  const topic = params.get('tema') ?? ''
  const style = params.get('estilo') ?? ''
  const { data, error } = useQuery({
    queryKey: ['library', topic, style], placeholderData: (p) => p,
    queryFn: () => api.get<{ plates: Plate[]; topics: { topic: string; n: number }[] }>(
      `/api/library?${new URLSearchParams({ topic, style })}`),
  })
  const set = (k: string, v: string) => setParams((p) => { if (v) p.set(k, v); else p.delete(k); return p }, { replace: true })
  return (
    <LibraryShell>
      <section className="library-head">
        <p className="eyebrow">Biblioteca gratuita</p>
        <h1 className="display sm">Láminas para imprimir, gratis.</h1>
        <p className="lede">Ilustraciones con su pregunta y su respuesta, listas para tu clase. Descárgalas en PDF y, si te gustan, crea el libro completo del tema.</p>
      </section>
      <div className="library-filters">
        <button className={topic === '' ? 'on' : undefined} onClick={() => set('tema', '')}>Todos los temas</button>
        {data?.topics.map((t) => <button key={t.topic} className={topic === t.topic ? 'on' : undefined} onClick={() => set('tema', t.topic)}>{t.topic}</button>)}
        <span className="library-sep" />
        <button className={style === '' ? 'on' : undefined} onClick={() => set('estilo', '')}>Todos los estilos</button>
        {HOUSE_STYLES.map((s) => <button key={s.key} className={style === s.key ? 'on' : undefined} onClick={() => set('estilo', s.key)}>{s.name}</button>)}
      </div>
      {error && <p className="error">{errorText(error, 'No pudimos cargar la biblioteca.')}</p>}
      <ul className="library-grid">
        {data?.plates.map((p) => (
          <li key={p.id}>
            <Link to={`/laminas/${p.slug}`}>
              <img src={p.image_url} alt={p.title} loading="lazy" width={717} height={960} />
              <span className="muted small">{p.topic} · {p.style_name}</span>
              <strong>{p.title}</strong>
            </Link>
          </li>
        ))}
      </ul>
      {data?.plates.length === 0 && <p className="muted">Pronto habrá láminas aquí.</p>}
    </LibraryShell>
  )
}

/** One plate: the picture, its answer, a free PDF for signed-in users and the way to the whole book. */
export function LibraryPlate() {
  const { slug = '' } = useParams()
  const [params] = useSearchParams()
  const { session, loading } = useAuth()
  const signedIn = !!session && !session.user.is_anonymous
  const [signing, setSigning] = useState(false)
  const { data, error } = useQuery({
    queryKey: ['library-plate', slug],
    queryFn: () => api.get<{ plate: Plate; related: Plate[] }>(`/api/library/${slug}`),
  })
  const download = useMutation({
    mutationFn: () => api.post<{ url: string }>(`/api/library/${slug}/download`),
    onSuccess: ({ url }) => window.location.assign(url),
  })
  const wantsIt = params.get('descargar') === '1'
  const { mutate, isIdle } = download
  useEffect(() => {  // back from Google with the download asked for: start it
    if (wantsIt && signedIn && isIdle) mutate()
  }, [wantsIt, signedIn, isIdle, mutate])

  async function get() {
    if (signedIn) return download.mutate()
    setSigning(true)
    const back = `/laminas/${slug}?descargar=1`
    try {
      if (session?.user.is_anonymous) await saveWithGoogle(back)
      else { rememberReturnTo(back); await signInWithGoogle() }
    } catch {
      setSigning(false)
    }
  }

  const plate = data?.plate
  const style = HOUSE_STYLES.find((s) => s.key === plate?.style)
  const book = plate ? `/?${new URLSearchParams({ pedido: `Libro ilustrado de ${plate.topic}`, ...(style?.free ? { estilo: style.key } : {}) })}#crear` : '/'
  return (
    <LibraryShell>
      {error && <p className="error">{errorText(error, 'No encontramos esa lámina.')}</p>}
      {plate && (
        <article className="plate-page">
          <img src={plate.image_url} alt={plate.title} width={717} height={960} />
          <div className="plate-side">
            <Link to={`/laminas?tema=${encodeURIComponent(plate.topic)}`} className="eyebrow">{plate.topic}</Link>
            <h1 className="display sm">{plate.title}</h1>
            {plate.answer && <p className="lede">{plate.answer}</p>}
            <p className="muted small">Estilo {plate.style_name}{plate.audience ? ` · ${plate.audience}` : ''} · PDF tamaño carta</p>
            <button className="primary" onClick={get} disabled={loading || signing || download.isPending}>
              {download.isPending ? 'Preparando PDF…' : signedIn ? 'Descargar PDF gratis' : 'Entrar con Google y descargar gratis'}
            </button>
            {download.error && <p className="error small">{errorText(download.error, 'No se pudo descargar.')}</p>}
            <div className="plate-cta">
              <strong>¿Te gustó? Crea el libro completo de {plate.topic}.</strong>
              <span className="muted small">Portada, láminas como esta en cada página, actividades y solucionario. La vista previa es gratis.</span>
              <a className="ghost" href={book}>Crear mi libro de {plate.topic}</a>
            </div>
          </div>
        </article>
      )}
      {!!data?.related.length && (
        <section>
          <h2 className="l-h sm">Más láminas</h2>
          <ul className="library-grid">
            {data.related.map((p) => (
              <li key={p.id}><Link to={`/laminas/${p.slug}`}><img src={p.image_url} alt={p.title} loading="lazy" width={717} height={960} /><span className="muted small">{p.topic} · {p.style_name}</span><strong>{p.title}</strong></Link></li>
            ))}
          </ul>
        </section>
      )}
    </LibraryShell>
  )
}
