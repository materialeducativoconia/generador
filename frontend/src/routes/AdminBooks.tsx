import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, Navigate } from 'react-router'
import { AppShell } from '../components/AppShell'
import { errorText } from '../components/ErrorNote'
import { api } from '../lib/apiClient'
import { type FreeBook, useMe } from '../lib/queries'
import { AdminTabs } from './AdminUsers'

/** The page a shared link opens: the book, and its download right after the visitor signs up with Google. */
export const bookLink = (slug: string) => `${window.location.origin}/libros/${slug}?descargar=1`

/** The free library, for admins only: the tomes picked in «Tomos», each with the link to share. Whoever opens it
 * sees that book and downloads it after signing up; every page of the PDF carries the copyright on its edge. */
export function AdminBooks() {
  const { data: me } = useMe()
  const admin = me?.platform_role === 'admin'
  const [copied, setCopied] = useState<string | null>(null)
  const qc = useQueryClient()
  const { data, error } = useQuery({
    queryKey: ['admin-books'], enabled: admin,
    queryFn: () => api.get<{ books: FreeBook[] }>('/api/admin/books'),
  })
  const remove = useMutation({
    mutationFn: (b: FreeBook) => api.delete(`/api/admin/books/${b.series_id}`),
    onSuccess: () => Promise.all([qc.invalidateQueries({ queryKey: ['admin-books'] }), qc.invalidateQueries({ queryKey: ['admin-series'] })]),
  })
  if (me && !admin) return <Navigate to={me.platform_role === 'staff' ? '/admin' : '/app'} replace />

  async function copy(slug: string) {
    await navigator.clipboard.writeText(bookLink(slug)).catch(() => {})
    setCopied(slug)
    setTimeout(() => setCopied(null), 2000)
  }

  return (
    <AppShell>
      <section className="styles-head">
        <div>
          <p className="eyebrow">Administración</p>
          <h1 className="display sm">Biblioteca</h1>
          <p className="muted">Los libros gratis que eliges en <Link to="/admin/tomos">Tomos</Link>. Solo tú ves esta lista: copia el enlace de un libro y compártelo; quien lo abra se registra con Google y lo descarga. Cada página del PDF lleva el copyright en el borde.</p>
        </div>
      </section>
      <AdminTabs />
      {error && <p className="error">{errorText(error, 'No pudimos cargar la biblioteca.')}</p>}
      {remove.error && <p className="error">{errorText(remove.error, 'No se pudo quitar el libro.')}</p>}
      {!data ? <div className="skeleton tall" /> : !data.books.length ? (
        <p className="muted">Aún no hay libros. En <Link to="/admin/tomos">Tomos</Link>, pulsa «Pasar a la biblioteca» en un tomo listo.</p>
      ) : (
        <ul className="admin-tomes">
          {data.books.map((b) => (
            <li key={b.id}>
              <a href={`/libros/${b.slug}`} target="_blank" rel="noreferrer" className="admin-tome-cover" aria-label={`Abrir ${b.title}`}>
                {b.pages[0] && <img src={b.pages[0]} alt="" width={96} height={119} loading="lazy" className="admin-book-cover" />}
              </a>
              <div className="admin-tome-b">
                <strong title={b.title}>{b.title}</strong>
                <span className="muted small">{b.genre_label} · {b.page_count} págs.{b.audience ? ` · ${b.audience}` : ''}</span>
                <span className="muted small">{b.downloads} {b.downloads === 1 ? 'descarga' : 'descargas'}</span>
                <code className="admin-book-link">{bookLink(b.slug)}</code>
                <span className="admin-tome-actions">
                  <button className="primary small" onClick={() => void copy(b.slug)}>{copied === b.slug ? 'Copiado ✓' : 'Copiar enlace'}</button>
                  <a className="ghost small" href={`/libros/${b.slug}`} target="_blank" rel="noreferrer">Ver</a>
                  <button className="ghost small" onClick={() => remove.mutate(b)} disabled={remove.isPending}>Quitar</button>
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </AppShell>
  )
}
