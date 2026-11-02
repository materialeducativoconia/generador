import { useMutation, useQuery } from '@tanstack/react-query'
import { useDeferredValue, useState } from 'react'
import { Link, Navigate } from 'react-router'
import { AppShell, StatusPill } from '../components/AppShell'
import { BookCover } from '../components/BookCover'
import { errorText } from '../components/ErrorNote'
import { api } from '../lib/apiClient'
import { FORMATS, GENRE_LABEL } from '../lib/labels'
import { useMe } from '../lib/queries'
import type { Genre } from '../lib/types'
import { AdminTabs } from './AdminUsers'

type AdminTome = {
  id: string; title: string; untitled: boolean; genre: Genre | null; status: string; preview: boolean; created_at: string
  page_target: number | null; cover_url: string | null; palette: [string, string, string] | null; email: string | null
  display_name: string | null; sections: number; score: number | null
  export: { id: string; status: string; format: string; pages: number | null } | null
}
const date = (iso: string) => new Date(iso).toLocaleDateString('es-MX', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

/** Every tome users made, to review what the agents produce: open one read-only or download its last file. */
export function AdminTomes() {
  const { data: me } = useMe()
  const staff = me?.platform_role === 'admin' || me?.platform_role === 'staff'
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [genre, setGenre] = useState('')
  const [kind, setKind] = useState('')
  const [pages, setPages] = useState(1)
  const query = useDeferredValue(q)
  const { data, error, isFetching } = useQuery({
    queryKey: ['admin-series', query, status, genre, kind, pages], enabled: staff, placeholderData: (p) => p,
    queryFn: () => api.get<{ series: AdminTome[]; more: boolean }>(
      `/api/admin/series?${new URLSearchParams({ q: query, status, genre, preview: kind, limit: String(48 * pages) })}`),
  })
  const download = useMutation({
    mutationFn: (exportId: string) => api.get<{ url: string }>(`/api/exports/${exportId}/file`),
    onSuccess: ({ url }) => window.location.assign(url),
  })
  if (me && !staff) return <Navigate to="/app" replace />

  return (
    <AppShell>
      <section className="styles-head">
        <div>
          <p className="eyebrow">Administración</p>
          <h1 className="display sm">Tomos</h1>
          <p className="muted">Todo lo que generan los usuarios. Ábrelo para verlo página por página (solo lectura) o descarga su último archivo.</p>
        </div>
      </section>
      <AdminTabs />
      <div className="admin-filters">
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar por título, pedido o correo…" aria-label="Buscar tomos" />
        <label className="select-pill"><span className="sr-only">Estado</span>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">Todos los estados</option>
            <option value="ready">Listos</option>
            <option value="generating">Generando</option>
            <option value="needs_attention">Requieren atención</option>
            <option value="outline_ready">Esquema listo</option>
            <option value="outline_failed">Error en el esquema</option>
          </select>
        </label>
        <label className="select-pill"><span className="sr-only">Formato</span>
          <select value={genre} onChange={(e) => setGenre(e.target.value)}>
            <option value="">Todos los formatos</option>
            {FORMATS.filter((f) => f.value !== 'auto').map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
          </select>
        </label>
        <label className="select-pill"><span className="sr-only">Tipo</span>
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">Vistas previas y de pago</option>
            <option value="no">Solo de usuarios con plan</option>
            <option value="yes">Solo vistas previas</option>
          </select>
        </label>
        {isFetching && <span className="spinner" />}
      </div>
      {error && <p className="error">{errorText(error, 'No pudimos cargar los tomos.')}</p>}
      {download.error && <p className="error">{errorText(download.error, 'No se pudo descargar.')}</p>}
      <ul className="admin-tomes">
        {data?.series.map((t) => (
          <li key={t.id}>
            <Link to={`/app/tomos/${t.id}`} className="admin-tome-cover" aria-label={`Abrir ${t.title}`}>
              <BookCover title={t.untitled ? 'Sin título aún' : t.title} genre={t.genre} cover_url={t.cover_url}
                         cover_status={null} cover_palette={t.palette} />
            </Link>
            <div className="admin-tome-b">
              <strong title={t.title}>{t.title}</strong>
              <span className="muted small">{t.email ?? 'Visitante sin cuenta'} · {date(t.created_at)}</span>
              <span className="admin-tome-tags">
                <StatusPill status={t.status} />
                {t.preview && <span className="pill idle">Vista previa</span>}
                {t.genre && <span className="pill idle">{GENRE_LABEL[t.genre]}</span>}
              </span>
              <span className="muted small">
                {t.sections} {t.sections === 1 ? 'sección' : 'secciones'}{t.page_target ? ` · ${t.page_target} págs.` : ''}
                {t.score !== null ? ` · Editor ${String(t.score).replace('.', ',')}/5` : ''}
              </span>
              <span className="admin-tome-actions">
                <Link className="ghost small" to={`/app/tomos/${t.id}`}>Ver</Link>
                {t.cover_url && <Link className="ghost small" to={`/admin/estilos?tomo=${t.id}`}>Probar estilos</Link>}
                {t.export?.status === 'succeeded' && (
                  <button className="ghost small" onClick={() => download.mutate(t.export!.id)} disabled={download.isPending}>
                    {t.export.format === 'docx' ? 'Word' : `PDF${t.export.pages ? ` · ${t.export.pages} págs.` : ''}`}
                  </button>
                )}
              </span>
            </div>
          </li>
        ))}
      </ul>
      {data?.series.length === 0 && <p className="muted">Ningún tomo coincide.</p>}
      {data?.more && <button className="ghost" onClick={() => setPages(pages + 1)} disabled={isFetching}>Ver más</button>}
    </AppShell>
  )
}
