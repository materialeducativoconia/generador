import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { useAuth } from '../auth/context'
import { rememberReturnTo, saveWithGoogle, signInWithGoogle } from '../auth/google'
import { errorText } from '../components/ErrorNote'
import { api } from '../lib/apiClient'
import { type FreeBook, useFreeBooks } from '../lib/queries'
import { usePageTitle } from '../lib/seo'
import { LibraryShell } from './Library'


/** A book as a shelf card: its cover, with its first inner pages as miniatures beneath. */
export function BookCard({ book }: { book: FreeBook }) {
  const [cover, ...inside] = book.pages
  return (
    <Link to={`/libros/${book.slug}`} className="book-card">
      {cover && <img src={cover} alt={`Portada de ${book.title}`} loading="lazy" width={480} height={593} />}
      {inside.length > 0 && <span className="book-minis" aria-hidden="true">
        {inside.slice(0, 3).map((p) => <img key={p} src={p} alt="" loading="lazy" />)}
      </span>}
      <span className="muted small">{book.genre_label} · {book.page_count} págs.{book.audience ? ` · ${book.audience}` : ''}</span>
      <strong>{book.title}</strong>
    </Link>
  )
}

/** The free book library: whole books to browse page by page and download after signing in. */
export function Books() {
  usePageTitle('Libros gratis para imprimir | Jelyx Docs')
  const { data, error } = useFreeBooks()
  return (
    <LibraryShell>
      <section className="library-head">
        <p className="eyebrow">Biblioteca gratuita</p>
        <h1 className="display sm">Libros completos para imprimir, gratis.</h1>
        <p className="lede">Libros ilustrados y cuadernillos hechos con Jelyx Docs. Hojéalos aquí, descárgalos en PDF y, si te gustan, crea el tuyo sobre tu tema.</p>
      </section>
      {error && <p className="error">{errorText(error, 'No pudimos cargar la biblioteca.')}</p>}
      <ul className="library-grid books">
        {data?.books.map((b) => <li key={b.id}><BookCard book={b} /></li>)}
      </ul>
      {data?.books.length === 0 && <p className="muted">Pronto habrá libros aquí.</p>}
    </LibraryShell>
  )
}

/** One book: its pages as miniatures, the free PDF for signed-in users and the way to make one's own. */
export function Book() {
  const { slug = '' } = useParams()
  const [params] = useSearchParams()
  const { session, loading } = useAuth()
  const signedIn = !!session && !session.user.is_anonymous
  const [signing, setSigning] = useState(false)
  const [open, setOpen] = useState(0)
  const { data, error } = useQuery({
    queryKey: ['free-book', slug],
    queryFn: () => api.get<{ book: FreeBook; related: FreeBook[] }>(`/api/books/${slug}`),
  })
  const download = useMutation({
    mutationFn: () => api.post<{ url: string }>(`/api/books/${slug}/download`),
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
    const back = `/libros/${slug}?descargar=1`
    try {
      if (session?.user.is_anonymous) await saveWithGoogle(back)
      else { rememberReturnTo(back); await signInWithGoogle() }
    } catch {
      setSigning(false)
    }
  }

  const book = data?.book
  usePageTitle(book && `${book.title} — libro gratis para imprimir | Jelyx Docs`)
  const make = book ? `/?${new URLSearchParams({ pedido: `${book.genre_label} sobre ${book.topic}` })}#crear` : '/'
  return (
    <LibraryShell>
      {error && <p className="error">{errorText(error, 'No encontramos ese libro.')}</p>}
      {book && (
        <article className="plate-page">
          <div className="book-viewer">
            {book.pages[open] && <img src={book.pages[open]} alt={`${book.title}, página ${open + 1}`} width={480} height={593} />}
            <ol className="book-thumbs" aria-label="Páginas">
              {book.pages.map((p, i) => (
                <li key={p}><button type="button" className={i === open ? 'on' : undefined} aria-current={i === open ? 'page' : undefined}
                  onClick={() => setOpen(i)}><img src={p} alt={i === 0 ? 'Portada' : `Página ${i + 1}`} loading="lazy" /></button></li>
              ))}
            </ol>
          </div>
          <div className="plate-side">
            <span className="eyebrow">{book.genre_label} · {book.topic}</span>
            <h1 className="display sm">{book.title}</h1>
            <p className="muted small">{book.page_count} páginas{book.audience ? ` · ${book.audience}` : ''} · PDF para imprimir</p>
            <button className="primary" onClick={get} disabled={loading || signing || download.isPending}>
              {download.isPending ? 'Preparando PDF…' : signedIn ? 'Descargar PDF gratis' : 'Regístrate con Google y descárgalo gratis'}
            </button>
            {!signedIn && <span className="muted small">Gratis: solo te pedimos una cuenta para descargar.</span>}
            {download.error && <p className="error small">{errorText(download.error, 'No se pudo descargar.')}</p>}
            <div className="plate-cta">
              <strong>¿Te gustó? Crea uno igual sobre tu tema.</strong>
              <span className="muted small">Escribe el tema y la edad de tu grupo: portada, ilustraciones, actividades y solucionario. La vista previa es gratis.</span>
              <a className="ghost" href={make}>Crear mi libro</a>
            </div>
          </div>
        </article>
      )}
      {!!data?.related.length && (
        <section>
          <h2 className="l-h sm">Más libros gratis</h2>
          <ul className="library-grid books">{data.related.map((b) => <li key={b.id}><BookCard book={b} /></li>)}</ul>
        </section>
      )}
    </LibraryShell>
  )
}
