import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { AppShell, StatusPill } from '../components/AppShell'
import { BookCover } from '../components/BookCover'
import { errorText } from '../components/ErrorNote'
import { PageThumb } from '../components/Sheet'
import { ART_LABEL, COVER_LABEL, FRAME_LABEL, GENRE_LABEL, THEME_LABEL } from '../lib/labels'
import { api } from '../lib/apiClient'
import { useExport, useIdentities, useMe, usePreview, useProgress, useQuality, useSeries, useStyles } from '../lib/queries'
import type { Block, Design, Export, LessonSummary, Level, Preflight, Progress, Series } from '../lib/types'


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
      <Link to="/app" className="back">← Tu biblioteca</Link>
      <header className="tome-h with-cover">
        <div className="tome-h-text">
          <p className="eyebrow">{s.genre ? GENRE_LABEL[s.genre] : 'Nuevo tomo'} · {s.audience.label}</p>
          <h1 className="display sm">{s.title ?? s.topic}</h1>
          <StatusPill status={status} />
          <DeleteTome id={s.id} title={s.title ?? s.topic} />
        </div>
        {s.title && <CoverPanel series={s} />}
      </header>

      <Pipeline status={status} progress={progress.data} />
      {s.preview && <BlurredPages series={s} />}

      {status === 'outlining' && <Planning />}
      {status === 'outline_failed' && <OutlineFailed series={s} />}
      {s.research?.levels?.length ? <LevelsPanel series={s} levels={s.research.levels} /> : null}
      {s.research?.program && <ProgramPanel program={s.research.program} />}
      {status === 'outline_ready' && <OutlineEditor key={s.version} series={s} />}
      {['generating', 'needs_attention', 'ready'].includes(status) && progress.data && (
        <>
          <Sections series={s} progress={progress.data} />
          {s.research?.sources.length ? <Sources research={s.research} /> : null}
          {status === 'ready' && <QualityCard seriesId={s.id} progress={progress.data} />}
          {status === 'ready' && <ExportPanel key={progress.data.images.done} seriesId={s.id} latest={progress.data.latest_export} images={progress.data.images} />}
        </>
      )}
    </AppShell>
  )
}

/** The free preview shows only the cover; the pages the visitor chose stay blurred until the tome is bought. */
function BlurredPages({ series: s }: { series: Series }) {
  const pages = s.page_target ?? s.lessons.reduce((n, l) => n + (l.pages ?? 1), 0)
  const titles = s.lessons.flatMap((l) => Array.from({ length: l.pages ?? 1 }, () => l.title))
  if (!s.design || pages < 1) return null
  return (
    <section className="blurred-pages" aria-label="Páginas del tomo">
      {titles.slice(0, pages).map((title, i) => (
        <PageThumb key={i} design={s.design!} position={i + 1} title={title} blocks={FILLER} />
      ))}
    </section>
  )
}

const FILLER: Block[] = Array.from({ length: 6 }, (_, i) => ({ id: `f${i}`, type: 'paragraph' as const,
  text: 'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore.' }))

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

const VERDICT = {
  lista: { label: 'Lista para vender', pill: 'ok' },
  revisar: { label: 'Revisar antes de vender', pill: 'bad' },
  pendiente: { label: 'Falta generar el PDF', pill: 'idle' },
} as const

const usd = (n: number) => `$${n.toFixed(n < 0.1 ? 3 : 2)}`

function QualityCard({ seriesId, progress }: { seriesId: string; progress: Progress }) {
  const e = progress.latest_export
  const stamp = `${progress.counts.generated}:${progress.images.done}:${progress.images.failed}:${e?.id ?? ''}:${e?.status ?? ''}`
  const q = useQuality(seriesId, stamp).data
  if (!q) return null
  const v = VERDICT[q.verdict]
  const t = q.text
  const rows: [string, string][] = [
    ['Texto', t.score === null ? 'Sin revisión del Editor' : `Editor ${String(t.score).replace('.', ',')}/5 · ${t.fixed} correcciones aplicadas`],
    ['Datos', q.facts?.needed ? `${q.facts.facts} datos verificados en ${q.facts.sources} fuentes` : 'No requiere fuentes'],
    ['Ilustraciones', q.art.total ? `${q.art.done} de ${q.art.total}${q.art.failed ? ` · ${q.art.failed} fallidas` : ''}` : 'Sin ilustraciones'],
    ...(q.pages.target ? [['Páginas', q.pages.actual ? `${q.pages.actual} de ${q.pages.target} pedidas` : `${q.pages.target} pedidas · genera el PDF para contarlas`] as [string, string]] : []),
    ['Costo IA', `${usd(q.cost.total_usd)} · texto ${usd(q.cost.text_usd)}${q.cost.search_usd ? `, búsqueda ${usd(q.cost.search_usd)}` : ''}, portada ${usd(q.cost.cover_usd)}, ilustraciones ${usd(q.cost.images_usd + q.cost.review_usd)}`],
    ...(q.cost.minutes === null ? [] : [['Tiempo', `${String(q.cost.minutes).replace('.', ',')} min de escritura e ilustración`] as [string, string]]),
    ['Impresión', q.print ? `${{ lista: 'Lista', aceptable: 'Aceptable', baja: 'Baja resolución' }[q.print.rating]}${q.print.layout?.fixed.length ? ` · maqueta ajustada en ${q.print.layout.fixed.length} imágenes` : ''}` : 'Genera el PDF para revisarla'],
  ]
  return (
    <details className="panel quality">
      <summary>
        <span className="section-h">Calidad</span>
        <span className={`pill ${v.pill}`}>{v.label}</span>
      </summary>
      <dl>
        {rows.map(([k, val]) => (
          <div key={k}><dt>{k}</dt><dd>{val}</dd></div>
        ))}
      </dl>
      {q.reasons.length > 0 && <ul className="reasons">{q.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
      {t.issues.length > 0 && (
        <ul className="issues muted small">
          {t.issues.map((i, n) => <li key={n}><strong>Sección {i.section}:</strong> {i.issue}</li>)}
        </ul>
      )}
    </details>
  )
}

function DeleteTome({ id, title }: { id: string; title: string }) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const remove = useMutation({
    mutationFn: () => api.delete(`/api/series/${id}`),
    onSuccess: async () => {
      await Promise.all([qc.invalidateQueries({ queryKey: ['series'] }), qc.invalidateQueries({ queryKey: ['collections'] })])
      navigate('/app')
    },
  })
  return (
    <button className="ghost small delete-tome" disabled={remove.isPending}
      onClick={() => { if (window.confirm(`¿Eliminar «${title}»? Se borran sus secciones y sus PDF. No se puede deshacer.`)) remove.mutate() }}>
      Eliminar tomo
    </button>
  )
}

/** A series by levels: the tomes before and after this one on the same topic, as the programs found by the
 * Researcher lay it out by grade. Each one opens the studio with its request ready to send. */
function LevelsPanel({ series: s, levels }: { series: Series; levels: Level[] }) {
  const navigate = useNavigate()
  const sources = s.research?.program?.sources ?? []
  // A level joins this tome's collection; a tome without one starts it, named after itself.
  const open = useMutation({
    mutationFn: async (lv: Level) => {
      const collection = s.collection_id ?? (await api.post<{ collection: { id: string } }>(
        '/api/collections', { name: s.title ?? s.topic, series_ids: [s.id] })).collection.id
      return { lv, collection }
    },
    onSuccess: ({ lv, collection }) => navigate(`/app?${new URLSearchParams({
      pedido: lv.request, publico: lv.audience, coleccion: collection, lugar: lv.relation === 'anterior' ? 'start' : 'end' })}`),
  })
  const card = (lv: Level) => (
    <li key={lv.request} className={`level ${lv.relation}`}>
      <span className="eyebrow">{lv.relation === 'anterior' ? 'Nivel anterior' : 'Nivel siguiente'} · {lv.audience}</span>
      <p className="small">{lv.focus}</p>
      {lv.grade && (
        <p className="muted small">
          {lv.source && sources[lv.source - 1]
            ? <a href={sources[lv.source - 1].url} target="_blank" rel="noreferrer noopener">{lv.grade}</a>
            : lv.grade}
        </p>
      )}
      <button className="ghost small" onClick={() => open.mutate(lv)} disabled={open.isPending}>
        Crear este nivel
      </button>
    </li>
  )
  const before = levels.filter((lv) => lv.relation === 'anterior')
  const after = levels.filter((lv) => lv.relation === 'siguiente')
  return (
    <section className="panel levels">
      <h2 className="section-h">Niveles sugeridos para la serie</h2>
      <p className="muted small">Según los programas de estudio encontrados, este tema se trabaja así antes y después de este tomo.</p>
      <ol className="level-list">
        {before.map(card)}
        <li className="level current">
          <span className="eyebrow">Este tomo · {s.audience.label}</span>
          <p className="small">{s.title ?? s.topic}</p>
        </li>
        {after.map(card)}
      </ol>
    </section>
  )
}

/** Where the syllabus came from: the official programs and methods the searcher found, and the reviewer's check.
 * A testing aid for now; it will be hidden from end users later. */
function ProgramPanel({ program: p }: { program: NonNullable<NonNullable<Series['research']>['program']> }) {
  const sources = p.sources ?? []
  return (
    <details className="panel sources program">
      <summary>
        <span className="section-h">Programa de referencia</span>
        <span className="muted small">{p.program || 'Sin programa claro'} · {sources.length} fuentes{p.review ? ` · revisión ${p.review.score}/5` : ''}</span>
      </summary>
      {p.method && <p className="small"><strong>Método:</strong> {p.method}</p>}
      {(p.points ?? []).length > 0 && (
        <ol className="small">{(p.points ?? []).map((x, i) => <li key={i}>{x.text} <span className="muted">[{x.source}]</span></li>)}</ol>
      )}
      {p.review && (
        <div className="small">
          <strong>Revisión del esquema contra el programa: {p.review.score}/5</strong>
          {p.review.missing.length > 0 && <p>Falta: {p.review.missing.join('; ')}</p>}
          {p.review.issues.length > 0 && <ul>{p.review.issues.map((x) => <li key={x}>{x}</li>)}</ul>}
        </div>
      )}
      <p className="small"><strong>Fuentes</strong></p>
      <ol className="small">
        {sources.map((s) => <li key={s.url}><a href={s.url} target="_blank" rel="noreferrer noopener">{s.title}</a></li>)}
      </ol>
      {(p.queries ?? []).length > 0 && <p className="small muted">Búsquedas: {(p.queries ?? []).join(' · ')}</p>}
      {(p.findings ?? []).length > 0 && (
        <details className="small"><summary>Lo que encontró el buscador</summary>
          {(p.findings ?? []).map((f) => <div key={f.query}><p><strong>{f.query}</strong></p><p className="pre">{f.text}</p></div>)}
        </details>
      )}
    </details>
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

type Draft = { id?: string; title: string; objectives: string; key_points: string; pages?: number | null }

/** The look the Designer chose with the outline, on a sample page; the user may swap it before writing. */
function DesignPreview({ series }: { series: Series }) {
  const qc = useQueryClient()
  const d = series.design
  const preview = usePreview(series.id, JSON.stringify(d)).data
  const styles = (useStyles().data?.styles ?? []).filter((s) => s.status === 'ready')
  const identities = (useIdentities().data?.identities ?? []).filter((i) => i.design?.brand)
  const change = useMutation({
    mutationFn: (value: string) =>
      api.patch(`/api/series/${series.id}/design`, { [{ i: 'identity_id', s: 'style_id', t: 'theme' }[value[0]]!]: value.slice(2) }),
    onSettled: () => Promise.all([qc.invalidateQueries({ queryKey: ['series', series.id] }), qc.invalidateQueries({ queryKey: ['preview', series.id] })]),
  })
  if (!d) return <div className="panel design-preview"><p className="muted">El diseño se elige con la portada…</p></div>
  const style = styles.find((s) => s.id === d.style_id)
  const seal = identities.find((i) => i.id === d.identity_id)?.design?.mark_svg  // drawn by our server
  const value = d.identity_id ? `i:${d.identity_id}` : d.style_id ? `s:${d.style_id}` : `t:${d.theme}`
  return (
    <section className="panel design-preview">
      <div className="design-sample">
        {preview && <PageThumb design={d} position={1} title={preview.title} blocks={preview.blocks} diagrams={preview.diagrams} />}
      </div>
      <div className="design-info">
        <p className="eyebrow">Diseño propuesto</p>
        <h2>{d.brand ? <span className="brand-line">{seal && <span className="seal" dangerouslySetInnerHTML={{ __html: seal }} />}{d.brand.name}</span> : style ? style.name : `Tema ${THEME_LABEL[d.theme]}`}</h2>
        {d.rationale && <p className="muted small">{d.rationale}</p>}
        <div className="swatches">
          {d.palette.map((c) => <span key={c} style={{ background: c }} title={c} />)}
        </div>
        <p className="small">
          Títulos en {d.head_font ?? 'la letra del tema'} · {FRAME_LABEL[d.frame ?? 'none']}
          {d.illustration ? ` · ilustración: ${ART_LABEL[d.illustration]}` : d.art_style ? ` · ilustración: ${d.art_style}` : ''}
          {` · ${COVER_LABEL[d.cover_layout ?? 'plate']}`}
        </p>
        <label className="field">
          <span>Cambiar diseño</span>
          <select value={value} onChange={(e) => change.mutate(e.target.value)} disabled={change.isPending}>
            {identities.length > 0 && (
              <optgroup label="Mis identidades">
                {identities.map((i) => <option key={i.id} value={`i:${i.id}`}>{i.design!.brand!.name}</option>)}
              </optgroup>
            )}
            {styles.length > 0 && (
              <optgroup label="Tus estilos">
                {styles.map((s) => <option key={s.id} value={`s:${s.id}`}>{s.name}</option>)}
              </optgroup>
            )}
            <optgroup label="Temas base">
              {(Object.keys(THEME_LABEL) as Design['theme'][]).map((t) => <option key={t} value={`t:${t}`}>{THEME_LABEL[t]}</option>)}
            </optgroup>
          </select>
        </label>
        {change.error && <p className="error small" role="alert">{errorText(change.error, 'No se pudo cambiar el diseño.')}</p>}
      </div>
    </section>
  )
}

function OutlineEditor({ series }: { series: Series }) {
  const qc = useQueryClient()
  const [title, setTitle] = useState(series.title ?? '')
  const [draft, setDraft] = useState<Draft[]>(() =>
    series.lessons.map((l) => ({ id: l.id, title: l.title, objectives: l.objectives.join('\n'), key_points: l.key_points.join(', '), pages: l.pages })),
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
            pages: d.pages ?? null,
          })),
        })
      }
      return api.post(`/api/series/${series.id}/lessons/generate`, {})
    },
    onSuccess: refresh,
  })
  const pages = draft.some((d) => d.pages) ? draft.reduce((n, d) => n + (d.pages ?? 0), 1) : null  // + cover
  const regenerate = useMutation({
    mutationFn: () => api.post(`/api/series/${series.id}/outline/regenerate`, { instructions: redo.trim() || null }),
    onSuccess: refresh,
  })

  return (
    <section className="outline">
      <DesignPreview series={series} />
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
              {d.pages != null && (
                <label className="pages small">
                  <input type="number" min={1} max={60} value={d.pages} onChange={(e) => update(i, { pages: Math.max(1, Math.min(60, Number(e.target.value) || 1)) })} aria-label="Páginas de la sección" />
                  páginas
                </label>
              )}
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
          {approve.isPending ? 'Aprobando…' : `Generar así · ${draft.length} ${draft.length === 1 ? 'sección' : 'secciones'}${pages ? ` · ~${pages} páginas` : ''}`}
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

/** Marks an option the user's plan does not include; choosing it explains which plan does. */
function Lock() {
  return <span className="lock" title="Desde el plan Creador"> · Creador</span>
}

type Edition = 'digital' | 'print'
type Paper = 'A4' | 'Letter' | '8x10' | '6x9'
const PAPERS: Record<Edition, { value: Paper; label: string }[]> = {
  digital: [{ value: 'A4', label: 'A4' }, { value: 'Letter', label: 'Carta' }],
  print: [{ value: 'Letter', label: '8.5×11' }, { value: '8x10', label: '8×10' }, { value: '6x9', label: '6×9' }, { value: 'A4', label: 'A4' }],
}
const RATING: Record<Preflight['rating'], string> = { lista: 'Lista para imprenta', aceptable: 'Aceptable', baja: 'Baja resolución' }

function ExportPanel({ seriesId, latest, images }: { seriesId: string; latest: Progress['latest_export']; images: Progress['images'] }) {
  const plan = useMe().data?.plan
  const [format, setFormat] = useState<'pdf' | 'docx'>('pdf')
  const [edition, setEdition] = useState<Edition>('digital')
  const [paper, setPaper] = useState<Paper>('A4')
  const [answers, setAnswers] = useState(true)
  // A PDF made before the last pictures arrived would miss them: start a fresh one instead.
  const [exportId, setExportId] = useState<string | null>(latest && latest.status !== 'failed' && !latest.stale ? latest.id : null)
  const illustrating = images.active > 0
  const current = useExport(exportId)
  const create = useMutation({
    mutationFn: () => api.post<{ export: Export }>(`/api/series/${seriesId}/exports`, { paper, include_answer_key: answers, edition, format }),
    onSuccess: (data) => setExportId(data.export.id),
  })
  const download = useMutation({
    mutationFn: (path: string) => api.get<{ url: string }>(path),
    onSuccess: ({ url }) => window.location.assign(url),
  })
  const status = current.data?.status
  const qc = useQueryClient()
  useEffect(() => {
    if (status === 'succeeded') qc.invalidateQueries({ queryKey: ['quality', seriesId] })
  }, [status, qc, seriesId])
  const busy = create.isPending || status === 'queued' || status === 'running'
  // Any new option means a different PDF: offer to generate it rather than download the old one.
  const change = (fn: () => void) => () => { fn(); setExportId(null) }
  const preflight = status === 'succeeded' ? current.data?.preflight : null

  return (
    <section className="panel export">
      <div>
        <h2 className="section-h">Exportar</h2>
        <p className="muted small">
          {illustrating
            ? `Ilustrando ${images.done} de ${images.total} imágenes… el archivo estará listo al terminar.`
            : format === 'docx'
              ? 'Documento de Word editable: textos y ejercicios para cambiar a tu gusto; fichas y dibujos como imágenes.'
              : edition === 'print'
              ? 'Interior y portada con lomo por separado, a medida de KDP y otras imprentas.'
              : `Portada, índice, secciones${images.total ? ', ilustraciones' : ''}${answers ? ' y solucionario' : ''}, listo para imprimir.`}
        </p>
      </div>
      <div className="export-opts">
        <div className="segmented" role="radiogroup" aria-label="Formato">
          {(['pdf', 'docx'] as const).map((f) => (
            <button key={f} role="radio" aria-checked={format === f} className={format === f ? 'on' : ''}
              onClick={change(() => { setFormat(f); if (f === 'docx') { setEdition('digital'); setPaper(PAPERS.digital[0].value) } })}>
              {f === 'pdf' ? 'PDF' : <>Word{plan && !plan.word && <Lock />}</>}
            </button>
          ))}
        </div>
        {format === 'pdf' && <div className="segmented" role="radiogroup" aria-label="Edición">
          {(['digital', 'print'] as const).map((e) => (
            <button key={e} role="radio" aria-checked={edition === e} className={edition === e ? 'on' : ''}
              onClick={change(() => { setEdition(e); setPaper(PAPERS[e][0].value) })}>
              {e === 'digital' ? 'Digital' : <>Imprenta{plan && !plan.print_edition && <Lock />}</>}
            </button>
          ))}
        </div>}
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
              {format === 'docx' ? 'Descargar Word'
                : `Descargar ${current.data.cover_download_url ? 'interior' : 'PDF'} · ${current.data.page_count} págs.`}
            </button>
          </>
        ) : (
          <button className="primary" onClick={() => create.mutate()} disabled={busy || illustrating}>
            {busy ? <><span className="spinner" /> Maquetando…</> : illustrating ? <><span className="spinner" /> Ilustrando…</> : format === 'docx' ? 'Generar Word' : 'Generar PDF'}
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
      {(status === 'failed' || create.error) && <p className="error">{errorText(create.error, 'No pudimos generar el archivo. Inténtalo de nuevo.')}</p>}
    </section>
  )
}
