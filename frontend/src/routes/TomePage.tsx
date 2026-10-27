import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { AppShell, StatusPill } from '../components/AppShell'
import { GENRE_LABEL } from '../lib/labels'
import { ApiError } from '../lib/api'
import { api } from '../lib/apiClient'
import { useExport, useProgress, useSeries } from '../lib/queries'
import type { Export, LessonSummary, Progress, Series } from '../lib/types'

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
      <header className="tome-h">
        <p className="eyebrow">{s.genre ? GENRE_LABEL[s.genre] : 'Nuevo tomo'} · {s.audience.label}</p>
        <h1 className="display sm">{s.title ?? s.topic}</h1>
        <StatusPill status={status} />
      </header>

      <Pipeline status={status} progress={progress.data} />

      {status === 'outlining' && <Planning />}
      {status === 'outline_failed' && <OutlineFailed series={s} />}
      {status === 'outline_ready' && <OutlineEditor key={s.version} series={s} />}
      {['generating', 'needs_attention', 'ready'].includes(status) && progress.data && (
        <>
          <Sections series={s} progress={progress.data} />
          {status === 'ready' && <ExportPanel seriesId={s.id} latest={progress.data.latest_export} />}
        </>
      )}
    </AppShell>
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
      <p className="muted">El arquitecto está diseñando el tomo: género, secciones y objetivos. Suele tardar entre 10 y 40 segundos.</p>
    </div>
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
      <ul className="sections">
        {progress.lessons.map((l) => {
          const ready = ['generated', 'edited', 'approved'].includes(l.status)
          const row = (
            <>
              <span className="num">{l.position}</span>
              <span className="sec-t">
                {l.title}
                {l.status === 'failed' && <small className="error">{l.error?.message}</small>}
                {!ready && l.status !== 'failed' && byId.get(l.id)?.objectives[0] && <small className="muted">{byId.get(l.id)?.objectives[0]}</small>}
              </span>
              <StatusPill status={l.status} />
            </>
          )
          return (
            <li key={l.id} className={`sec ${l.status}`}>
              {ready ? <Link to={`/app/secciones/${l.id}`} className="sec-row">{row}<span className="chev">→</span></Link> : <div className="sec-row">{row}</div>}
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

function ExportPanel({ seriesId, latest }: { seriesId: string; latest: Progress['latest_export'] }) {
  const [paper, setPaper] = useState<'A4' | 'Letter'>('A4')
  const [answers, setAnswers] = useState(true)
  const [exportId, setExportId] = useState<string | null>(latest?.status === 'failed' ? null : (latest?.id ?? null))
  const current = useExport(exportId)
  const create = useMutation({
    mutationFn: () => api.post<{ export: Export }>(`/api/series/${seriesId}/exports`, { paper, include_answer_key: answers }),
    onSuccess: (data) => setExportId(data.export.id),
  })
  const download = useMutation({
    mutationFn: (path: string) => api.get<{ url: string }>(path),
    onSuccess: ({ url }) => window.location.assign(url),
  })
  const status = current.data?.status
  const busy = create.isPending || status === 'queued' || status === 'running'

  return (
    <section className="panel export">
      <div>
        <h2 className="section-h">Exportar PDF</h2>
        <p className="muted small">Portada, índice, secciones{answers ? ' y solucionario' : ''}, listo para imprimir.</p>
      </div>
      <div className="export-opts">
        <div className="segmented" role="radiogroup" aria-label="Tamaño de papel">
          {(['A4', 'Letter'] as const).map((p) => (
            <button key={p} role="radio" aria-checked={paper === p} className={paper === p ? 'on' : ''} onClick={() => setPaper(p)}>
              {p === 'A4' ? 'A4' : 'Carta'}
            </button>
          ))}
        </div>
        <label className="check">
          <input type="checkbox" checked={answers} onChange={(e) => setAnswers(e.target.checked)} /> Solucionario
        </label>
        {status === 'succeeded' && current.data?.download_url ? (
          <button className="primary" onClick={() => download.mutate(current.data!.download_url!)} disabled={download.isPending}>
            Descargar PDF · {current.data.page_count} págs.
          </button>
        ) : (
          <button className="primary" onClick={() => create.mutate()} disabled={busy}>
            {busy ? <><span className="spinner" /> Maquetando…</> : 'Generar PDF'}
          </button>
        )}
      </div>
      {(status === 'failed' || create.error) && <p className="error">{errorText(create.error, 'No pudimos generar el PDF. Inténtalo de nuevo.')}</p>}
    </section>
  )
}
