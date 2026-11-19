import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router'
import { useAuth } from '../auth/context'
import { rememberReturnTo, saveWithGoogle, signInWithGoogle } from '../auth/google'
import { errorText } from '../components/ErrorNote'
import { api } from '../lib/apiClient'
import type { FreeBook } from '../lib/queries'
import { usePageTitle } from '../lib/seo'
import { LibraryShell } from './Library'


/** One free book, reached by the link the team shares: its pages as miniatures, the PDF after signing up with
 * Google (the page starts the download on the way back) and the way to make one's own. */
export function Book() {
  const { slug = '' } = useParams()
  const [params] = useSearchParams()
  const { session, loading } = useAuth()
  const signedIn = !!session && !session.user.is_anonymous
  const [signing, setSigning] = useState(false)
  const [open, setOpen] = useState(0)
  const navigate = useNavigate()
  const { data, error } = useQuery({
    queryKey: ['free-book', slug],
    queryFn: () => api.get<{ book: FreeBook }>(`/api/books/${slug}`),
  })
  const download = useMutation({
    mutationFn: () => api.post<{ url: string }>(`/api/books/${slug}/download`),
    onSuccess: ({ url }) => {  // the PDF comes as an attachment, so the page stays and takes them to their account
      window.location.assign(url)
      setTimeout(() => navigate('/app', { replace: true }), 600)
    },
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
              {download.isPending ? 'Preparando PDF…' : 'Descarga gratis'}
            </button>
            {!signedIn && <span className="muted small">Entras con Google y el PDF se descarga.</span>}
            {download.error && <p className="error small">{errorText(download.error, 'No se pudo descargar.')}</p>}
            <div className="plate-cta">
              <strong>¿Te gustó? Crea uno igual sobre tu tema.</strong>
              <span className="muted small">Escribe el tema y la edad de tu grupo: portada, ilustraciones, actividades y solucionario. La vista previa es gratis.</span>
              <a className="ghost" href={make}>Crear mi libro</a>
            </div>
          </div>
        </article>
      )}
    </LibraryShell>
  )
}
