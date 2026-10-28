import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { AppShell, StatusPill } from '../components/AppShell'
import { BookCover } from '../components/BookCover'
import { PageThumb } from '../components/Sheet'
import { GENRE_LABEL } from '../lib/labels'
import { ApiError } from '../lib/api'
import { api } from '../lib/apiClient'
import { useExport, useProgress, useSeries } from '../lib/queries'
import type { Export, LessonSummary, Preflight, Progress, Series } from '../lib/types'

const errorText = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback)

export function TomePage() {
  const { id = '' } = useParams()
  const series = useSeries(id)
  const progress = useProgress(id)

  if (series.isPending) return <AppShell><div className="skeleton tall" /></AppShell>
  if (series.error) return <AppShell><p className="error">{errorText(series.error, 'No pudimos cargar el tomo.')}</p></AppShell>

  const s = series.data
  const status = progress.data?.status ?? s.status
  return (
    <AppShell>
      <Link to="/app" className="back">← Tus tomos</Link>
      <header className="tome-h with-cover">
        <div className="tome-h-text">
          <p className="eyebrow">{s.genre ? GENRE_LABEL[s.genre] : 'Nuevo tomo'} · {s.audience.label}</p>
          <h1 className="display sm">{s.title ?? s.topic}</h1>
          <StatusPill status={status} />
        </div>
        {s.title && <CoverPanel series={s} />}
      </header>

      <Pipeline status={status} progress={progress.data} />

      {status === 'outlining' && <Planning />}
      {status === 'outline_failed' && <OutlineFailed series={s} />}
      {status === 'outline_ready' && <OutlineEditor key={s.version} series={s} />}
      {['generating', 'needs_attention', 'ready'].includes(status) && progress.data && (
        <>
          <Sections series={s} progress={progress.data} />
          {s.research?.sources.length ? <Sources research={s.research} /> : null}
          {status === 'ready' && <ExportPanel key={progress.data.images.done} seriesId={s.id} latest={progress.data.latest_export} images={progress.data.images} />}
        </>
      )}
    </AppShell>
  )
}

function CoverPanel({ series: s }: { series: Series }) {
  const qc = useQueryClient()
  const repaint = useMutation({
    mutationFn: () => api.post(`/api/series/${s.id}/cover`),
    onSettled: () => Promise.all([qc.invalidateQueries({ queryKey: ['series', s.id] }), qc.invalidateQueries({ queryKey: ['series'], exact: true })]),
  })
  const busy = s.cover_status === 'queued' || s.cover_status === 'running' || repaint.isPending
  return (
    <div className="cover-panel">
      <BookCover size="hero" title={s.title ?? s.topic} genre={s.genre} audience={s.audience.label} cover_url={s.cover_url} cover_status={s.cover_status} cover_palette={s.cover_palette ?? s.design?.palette ?? null} />
      <button className="ghost small" onClick={() => repaint.mutate()} disabled={busy}>
        {busy ? 'Pintando…' : s.cover_url ? 'Otra portada' : s.cover_status === 'failed' ? 'Reintentar portada' : 'Crear portada'}
      </button>
      {repaint.error && <p className="error small">{errorText(repaint.error, 'No se pudo pedir otra portada.')}</p>}
    </div>
  )
}

const STEPS = [
  { key: 'architect', label: 'Arquitecto', hint: 'Planifica el tomo' },
  { key: 'review', label: 'Tu revisión', hint: 'Apruebas el esquema' },
  { key: 'writer', label: 'Redactor', hint: 'Escribe cada sección' },
  { key: 'layout', label: 'Maquetador', hint: 'Arma el PDF' },
]

function Pipeline({ status, progress }: { status: string; progress?: Progress }) {
  const active = { outlining: 0, outline_failed: 0, outline_ready: 1, generating: 2, needs_attention: 2, ready: 3 }[status] ?? 0
  const done = progress ? progress.counts.generated + progress.counts.edited + progress.counts.approved : 0
  return (
    <ol className="pipeline">
      {STEPS.map((step, i) => (
        <li key={step.key} className={i < active ? 'done' : i === active ? 'active' : ''}>
          <span className="pl-dot" />
          <span className="pl-l">{step.label}</span>
          <span className="pl-h">
            {step.key === 'writer' && i === active && progress ? `${done} de ${progress.counts.total}` : step.hint}
          </span>
        </li>
      ))}
    </ol>
  )
}

function Planning() {
  return (
    <div className="panel planning">
      <div className="shimmer-lines" aria-hidden="true"><span /><span /><span /><span /></div>
      <p className="muted">
        El investigador busca fuentes si el tema lo necesita y el arquitecto diseña el tomo: género, secciones y objetivos.
        Suele tardar entre 15 y 60 segundos.
      </p>
    </div>
  )
}

function Sources({ research }: { research: NonNullable<Series['research']> }) {
  return (
    <details className="panel sources">
      <summary>
        <span className="section-h">Fuentes</span>
        <span className="muted small">{research.facts} datos verificados en {research.sources.length} artículos</span>
      </summary>
      <ol>
        {research.sources.map((src) => (
          <li key={src.url}>
            <a href={src.url} target="_blank" rel="noreferrer noopener">{src.title}</a>
          </li>
        ))}
      </ol>
    </details>
  )
}

function OutlineFailed({ series }: { series: Series }) {
  const qc = useQueryClient()
  const retry = useMutation({
    mutationFn: () => api.post(`/api/series/${series.id}/outline/regenerate`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['progress', series.id] }),
  })
  return (
    <div className="panel">
      <p className="error">{series.outline_error?.message ?? 'No pudimos generar el esquema.'}</p>
      <button className="primary" onClick={() => retry.mutate()} disabled={retry.isPending}>Reintentar</button>
    </div>
  )
}

type Draft = { id?: string; title: string; objectives: string; key_points: string }

function OutlineEditor({ series }: { series: Series }) {
  const qc = useQueryClient()
  const [title, setTitle] = useState(series.title ?? '')
  const [draft, setDraft] = useState<Draft[]>(() =>
    series.lessons.map((l) => ({ id: l.id, title: l.title, objectives: l.objectives.join('\n'), key_points: l.key_points.join(', ') })),
  )
  const [dirty, setDirty] = useState(false)
  const [redo, setRedo] = useState('')

  const update = (i: number, patch: Partial<Draft>) => {
    setDraft((d) => d.map((x, j) => (j === i ? { ...x, ...patch } : x)))
    setDirty(true)
  }
  const move = (i: number, by: number) => {
    setDraft((d) => {
      const next = [...d]
      const [item] = next.splice(i, 1)
      next.splice(i + by, 0, item)
      return next
    })
    setDirty(true)
  }

  const refresh = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: ['series', series.id] }),
      qc.invalidateQueries({ queryKey: ['progress', series.id] }),
      qc.invalidateQueries({ queryKey: ['me'] }),
    ])

  const approve = useMutation({
    mutationFn: async () => {
      if (dirty) {
        await api.patch(`/api/series/${series.id}/outline`, {
          version: series.version,
          title: title.trim() || null,
          lessons: draft.map((d) => ({
            id: d.id,
            title: d.title.trim() || 'Sin título',
            objectives: d.objectives.split('\n').map((x) => x.trim()).filter(Boolean),
            key_points: d.key_points.split(',').map((x) => x.trim()).filter(Boolean),
          })),
        })
      }
      return api.post(`/api/series/${series.id}/lessons/generate`, {})
    },
    onSuccess: refresh,
  })
  const regenerate = useMutation({
    mutationFn: () => api.post(`/api/series/${series.id}/outline/regenerate`, { instructions: redo.trim() || null }),
    onSuccess: refresh,
  })

  return (
    <section className="outline">
      <div className="panel">
        <label className="field">
          <span>Título del tomo</span>
          <input value={title} onChange={(e) => { setTitle(e.target.value); setDirty(true) }} maxLength={300} />
        </label>
      </div>

      <ol className="outline-list">
        {draft.map((d, i) => (
          <li key={d.id ?? `new-${i}`} className="outline-item" style={{ '--i': i } as React.CSSProperties}>
            <span className="num">{i + 1}</span>
            <div className="outline-body">
              <input className="outline-title" value={d.title} onChange={(e) => update(i, { title: e.target.value })} aria-label={`Título de la sección ${i + 1}`} />
              <textarea value={d.objectives} onChange={(e) => update(i, { objectives: e.target.value })} rows={2} placeholder="Objetivos (uno por línea)" aria-label="Objetivos" />
              <input className="small" value={d.key_points} onChange={(e) => update(i, { key_points: e.target.value })} placeholder="Puntos clave, separados por comas" aria-label="Puntos clave" />
            </div>
            <div className="outline-tools">
              <button className="icon" onClick={() => move(i, -1)} disabled={i === 0} aria-label="Subir">↑</button>
              <button className="icon" onClick={() => move(i, 1)} disabled={i === draft.length - 1} aria-label="Bajar">↓</button>
              <button className="icon" onClick={() => { setDraft((x) => x.filter((_, j) => j !== i)); setDirty(true) }} disabled={draft.length === 1} aria-label="Eliminar">✕</button>
            </div>
          </li>
        ))}
      </ol>
      {draft.length < 20 && (
        <button className="ghost" onClick={() => { setDraft((d) => [...d, { title: 'Nueva sección', objectives: '', key_points: '' }]); setDirty(true) }}>
          + Añadir sección
        </button>
      )}

      <div className="action-bar">
        <div className="redo">
          <input value={redo} onChange={(e) => setRedo(e.target.value)} placeholder="¿Rehacer? Ej.: menos teoría, más ejercicios" maxLength={2000} />
          <button className="ghost" onClick={() => regenerate.mutate()} disabled={regenerate.isPending}>Rehacer esquema</button>
        </div>
        <button className="primary" onClick={() => approve.mutate()} disabled={approve.isPending}>
          {approve.isPending ? 'Aprobando…' : `Aprobar y escribir ${draft.length} ${draft.length === 1 ? 'sección' : 'secciones'}`}
        </button>
      </div>
      {(approve.error || regenerate.error) && <p className="error" role="alert">{errorText(approve.error ?? regenerate.error, 'Algo salió mal.')}</p>}
    </section>
  )
}

function Sections({ series, progress }: { series: Series; progress: Progress }) {
  const qc = useQueryClient()
  const failed = progress.lessons.filter((l) => l.status === 'failed')
  const done = progress.counts.generated + progress.counts.edited + progress.counts.approved
  const retry = useMutation({
    mutationFn: (ids: string[]) => api.post(`/api/series/${series.id}/lessons/generate`, { lesson_ids: ids }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['progress', series.id] }),
  })
  const byId = new Map<string, LessonSummary>(series.lessons.map((l) => [l.id, l]))

  return (
    <section>
      <div className="progress" role="progressbar" aria-valuenow={done} aria-valuemax={progress.counts.total}>
        <span style={{ transform: `scaleX(${progress.counts.total ? done / progress.counts.total : 0})` }} />
      </div>
      <ul className="thumbs">
        {progress.lessons.map((l, i) => {
          const ready = ['generated', 'edited', 'approved'].includes(l.status)
          const blocks = byId.get(l.id)?.content_json?.blocks
          const caption = (
            <span className="thumb-cap">
              <span className="thumb-t"><span className="thumb-n">{l.position}</span>{l.title}</span>
              {l.status === 'failed' ? <small className="error">{l.error?.message}</small> : !ready && <StatusPill status={l.status} />}
            </span>
          )
          return (
            <li key={l.id} className={`thumb-item ${l.status}`} style={{ '--i': i } as React.CSSProperties}>
              {ready && blocks ? (
                <Link to={`/app/secciones/${l.id}`} className="thumb-link" aria-label={`Abrir sección ${l.position}: ${l.title}`}>
                  <PageThumb design={series.design} position={l.position} title={l.title} blocks={blocks} assets={series.assets} credits={series.credits} diagrams={byId.get(l.id)?.diagrams} painting={progress.images.active > 0} />
                  {caption}
                </Link>
              ) : (
                <div className="thumb-link idle">
                  <div className={`thumb placeholder ${l.status}`} aria-hidden="true"><span /><span /><span /><span /></div>
                  {caption}
                </div>
              )}
            </li>
          )
        })}
      </ul>
      {failed.length > 0 && (
        <button className="primary" onClick={() => retry.mutate(failed.map((l) => l.id))} disabled={retry.isPending}>
          Reintentar {failed.length} {failed.length === 1 ? 'sección' : 'secciones'}
        </button>
      )}
      {retry.error && <p className="error">{errorText(retry.error, 'No se pudo reintentar.')}</p>}
    </section>
  )
}

type Edition = 'digital' | 'print'
type Paper = 'A4' | 'Letter' | '8x10' | '6x9'
const PAPERS: Record<Edition, { value: Paper; label: string }[]> = {
  digital: [{ value: 'A4', label: 'A4' }, { value: 'Letter', label: 'Carta' }],
  print: [{ value: 'Letter', label: '8.5×11' }, { value: '8x10', label: '8×10' }, { value: '6x9', label: '6×9' }, { value: 'A4', label: 'A4' }],
}
const RATING: Record<Preflight['rating'], string> = { lista: 'Lista para imprenta', aceptable: 'Aceptable', baja: 'Baja resolución' }

function ExportPanel({ seriesId, latest, images }: { seriesId: string; latest: Progress['latest_export']; images: Progress['images'] }) {
  const [edition, setEdition] = useState<Edition>('digital')
  const [paper, setPaper] = useState<Paper>('A4')
  const [answers, setAnswers] = useState(true)
  // A PDF made before the last pictures arrived would miss them: start a fresh one instead.
  const [exportId, setExportId] = useState<string | null>(latest && latest.status !== 'failed' && !latest.stale ? latest.id : null)
  const illustrating = images.active > 0
  const current = useExport(exportId)
  const create = useMutation({
    mutationFn: () => api.post<{ export: Export }>(`/api/series/${seriesId}/exports`, { paper, include_answer_key: answers, edition }),
    onSuccess: (data) => setExportId(data.export.id),
  })
  const download = useMutation({
    mutationFn: (path: string) => api.get<{ url: string }>(path),
    onSuccess: ({ url }) => window.location.assign(url),
  })
  const status = current.data?.status
  const busy = create.isPending || status === 'queued' || status === 'running'
  // Any new option means a different PDF: offer to generate it rather than download the old one.
  const change = (fn: () => void) => () => { fn(); setExportId(null) }
  const preflight = status === 'succeeded' ? current.data?.preflight : null

  return (
    <section className="panel export">
      <div>
        <h2 className="section-h">Exportar PDF</h2>
        <p className="muted small">
          {illustrating
            ? `Ilustrando ${images.done} de ${images.total} imágenes… el PDF estará listo al terminar.`
            : edition === 'print'
              ? 'Interior y portada con lomo por separado, a medida de KDP y otras imprentas.'
              : `Portada, índice, secciones${images.total ? ', ilustraciones' : ''}${answers ? ' y solucionario' : ''}, listo para imprimir.`}
        </p>
      </div>
      <div className="export-opts">
        <div className="segmented" role="radiogroup" aria-label="Edición">
          {(['digital', 'print'] as const).map((e) => (
            <button key={e} role="radio" aria-checked={edition === e} className={edition === e ? 'on' : ''}
              onClick={change(() => { setEdition(e); setPaper(PAPERS[e][0].value) })}>
              {e === 'digital' ? 'Digital' : 'Imprenta'}
            </button>
          ))}
        </div>
        <div className="segmented" role="radiogroup" aria-label="Tamaño de papel">
          {PAPERS[edition].map((p) => (
            <button key={p.value} role="radio" aria-checked={paper === p.value} className={paper === p.value ? 'on' : ''}
              onClick={change(() => setPaper(p.value))}>
              {p.label}
            </button>
          ))}
        </div>
        <label className="check">
          <input type="checkbox" checked={answers} onChange={(e) => { setAnswers(e.target.checked); setExportId(null) }} /> Solucionario
        </label>
        {status === 'succeeded' && current.data?.download_url ? (
          <>
            {current.data.cover_download_url && (
              <button className="ghost" onClick={() => download.mutate(current.data!.cover_download_url!)} disabled={download.isPending}>
                Portada con lomo
              </button>
            )}
            <button className="primary" onClick={() => download.mutate(current.data!.download_url!)} disabled={download.isPending}>
              Descargar {current.data.cover_download_url ? 'interior' : 'PDF'} · {current.data.page_count} págs.
            </button>
          </>
        ) : (
          <button className="primary" onClick={() => create.mutate()} disabled={busy || illustrating}>
            {busy ? <><span className="spinner" /> Maquetando…</> : illustrating ? <><span className="spinner" /> Ilustrando…</> : 'Generar PDF'}
          </button>
        )}
      </div>
      {preflight && (
        <div className={`preflight ${preflight.rating}`}>
          <strong>{RATING[preflight.rating]}</strong>
          <span className="muted small">
            {preflight.min_dpi ? ` · imágenes desde ${preflight.min_dpi} dpi` : ''}
            {preflight.vector ? ` · ${preflight.vector} dibujo${preflight.vector > 1 ? 's' : ''} vectorial${preflight.vector > 1 ? 'es' : ''}` : ''}
          </span>
          {preflight.issues.length > 0 && <ul>{preflight.issues.map((i) => <li key={i}>{i}</li>)}</ul>}
        </div>
      )}
      {(status === 'failed' || create.error) && <p className="error">{errorText(create.error, 'No pudimos generar el PDF. Inténtalo de nuevo.')}</p>}
    </section>
  )
}
