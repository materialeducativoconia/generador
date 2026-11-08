import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { saveWithGoogle } from '../auth/google'
import { AppShell, StatusPill } from '../components/AppShell'
import { BookCover, CoverViewer } from '../components/BookCover'
import { errorText } from '../components/ErrorNote'
import { PageThumb } from '../components/Sheet'
import { StylePicker } from '../components/StylePicker'
import { ART_LABEL, COVER_LABEL, FRAME_LABEL, GENRE_LABEL, THEME_LABEL, tomeName } from '../lib/labels'
import { api } from '../lib/apiClient'
import { useExport, useIdentities, useMe, usePreview, useProgress, useQuality, useSeries, useStyles } from '../lib/queries'
import { HOUSE_STYLES, sampleOf } from '../lib/houseStyles'
import type { Block, Design, Export, LessonSummary, Level, Preflight, Progress, Series, TomeVariant } from '../lib/types'


export function TomePage() {
  const { id = '' } = useParams()
  const series = useSeries(id)
  const progress = useProgress(id)

  if (series.isPending) return <AppShell><div className="skeleton tall" /></AppShell>
  if (series.error) return <AppShell><p className="error">{errorText(series.error, 'No pudimos cargar el tomo.')}</p></AppShell>

  const s = series.data
  const status = progress.data?.status ?? s.status
  const img = progress.data?.images
  // Text done but plates still being painted: not "Listo" yet.
  const pill = status === 'ready' && img && img.total > 0 && (img.active > 0 || img.done + img.failed < img.total) ? 'generating' : status
  return (
    <AppShell>
      {s.owner ? (
        <>
          <Link to="/admin/tomos" className="back">← Tomos de usuarios</Link>
          <p className="notice small review-note">Vista del equipo: tomo de <strong>{s.owner.display_name || s.owner.email || 'un visitante'}</strong>{s.owner.email && s.owner.display_name ? ` (${s.owner.email})` : ''}. Puedes revisarlo y descargarlo; los cambios solo los hace su dueño.</p>
        </>
      ) : <Link to="/app" className="back">← Tu biblioteca</Link>}
      <header className="tome-h with-cover">
        <div className="tome-h-text">
          <p className="eyebrow">{s.genre ? GENRE_LABEL[s.genre] : 'Nuevo tomo'} · {s.audience.label}</p>
          {s.title && !s.owner && !s.preview && status !== 'outline_ready' ? <TomeTitle series={s} /> : <h1 className="display sm">{s.title ?? 'Tu nuevo tomo'}</h1>}
          {!s.title && <p className="tome-request" title={s.topic}>{s.topic}</p>}
          <StatusPill status={pill} />
          {s.cast?.length ? (
            <ul className="cast-row" aria-label="Personajes del tomo">
              {s.cast.map((c) => (
                <li key={c.name}>{c.sheet_url && <img src={c.sheet_url} alt="" />}<span><strong>{c.name}</strong>{c.archetype}</span></li>
              ))}
            </ul>
          ) : null}
          {s.versions?.length ? <VersionLinks series={s} /> : null}
          {!s.owner && <DeleteTome id={s.id} title={tomeName(s)} />}
        </div>
        {s.title && <CoverPanel series={s} />}
      </header>

      <TomeProgress series={s} status={status} progress={progress.data} preview={s.preview} />
      {s.preview && status === 'outline_ready' && <PreviewPages series={s} progress={progress.data} />}
      {s.preview && !s.owner && ['outline_ready', 'needs_attention', 'ready'].includes(status) && <MakeFullBook series={s} />}

      {status === 'outline_failed' && <OutlineFailed series={s} />}
      {!s.owner && !s.preview && ['outline_ready', 'needs_attention', 'ready'].includes(status) && <NewVersion series={s} />}
      {s.research?.levels?.length ? <LevelsPanel series={s} levels={s.research.levels} /> : null}
      {s.research?.program && <ProgramPanel program={s.research.program} />}
      {status === 'outline_ready' && <OutlineEditor key={s.version} series={s} />}
      {['generating', 'needs_attention', 'ready'].includes(status) && progress.data && (
        <>
          {!s.owner && status === 'ready' && (
            <Link to={`/app/tomos/${s.id}/paginas`} className="panel edit-pages">
              <span className="section-h">Editor de páginas</span>
              <span className="muted small">{s.genre === 'picture_book' || s.genre === 'story_book'
                ? 'Ve cada página como sale en el PDF, corrige su texto, cambia su composición o repinta una ilustración; también la portada'
                : 'Edita la portada como sale en el PDF: qué lleva además del título, o píntala de nuevo'}</span>
            </Link>
          )}
          <Sections series={s} progress={progress.data} />
          {s.research?.sources.length ? <Sources research={s.research} /> : null}
          {status === 'ready' && <QualityCard seriesId={s.id} progress={progress.data} />}
          {status === 'ready' && <ExportPanel key={`${progress.data.images.done}:${progress.data.latest_export?.id}:${progress.data.latest_export?.stale}`} seriesId={s.id} genre={s.genre} latest={progress.data.latest_export} images={progress.data.images} />}
        </>
      )}
    </AppShell>
  )
}

const FULL_SIZES = [8, 12, 16, 24, 32, 48]

/** Convertir en libro completo: the Architect adds the sections the preview still needs, after its written pages,
 *  and the outline opens for review; without a plan the button leads to the plans. */
function MakeFullBook({ series: s }: { series: Series }) {
  const qc = useQueryClient()
  const { data: me } = useMe()
  const navigate = useNavigate()
  const have = s.lessons.reduce((n, l) => n + (l.pages ?? 1), 0)
  const sizes = FULL_SIZES.filter((n) => n > have && (!me || n <= me.plan.max_pages))
  const [pages, setPages] = useState(sizes[1] ?? sizes[0] ?? 0)
  const needsPlan = !!me && (me.anonymous || me.plan.key === 'prueba')
  const expand = useMutation({
    mutationFn: () => api.post(`/api/series/${s.id}/expand`, { pages }),
    onSuccess: () => Promise.all([qc.invalidateQueries({ queryKey: ['series', s.id] }), qc.invalidateQueries({ queryKey: ['me'] })]),
  })
  if (!needsPlan && !sizes.length) return null
  return (
    <section className="panel full-book">
      <div>
        <strong>Convertir en libro completo</strong>
        <p className="muted small">Tus {have} {have === 1 ? 'página' : 'páginas'} se quedan como están. El arquitecto añade las secciones que faltan para completar el libro y tú revisas el esquema antes de generarlo.</p>
      </div>
      {needsPlan ? (
        <button className="primary" onClick={() => (me?.anonymous ? saveWithGoogle(`/app/plan?tomo=${s.id}`) : navigate(`/app/plan?tomo=${s.id}`))}>Elegir un plan</button>
      ) : (
        <div className="full-book-go">
          <label className="select-pill"><span className="sr-only">Páginas del libro completo</span>
            <select value={pages} onChange={(e) => setPages(Number(e.target.value))}>
              {sizes.map((n) => <option key={n} value={n}>{n} páginas</option>)}
            </select>
          </label>
          <button className="primary" onClick={() => expand.mutate()} disabled={expand.isPending || !pages}>{expand.isPending ? 'Preparando…' : 'Convertir en libro completo'}</button>
        </div>
      )}
      {expand.error && <p className="error small" role="alert">{errorText(expand.error, 'No se pudo ampliar el tomo.')}</p>}
    </section>
  )
}

/** The free preview is the visitor's real tome, page by page, as small locked thumbnails: no opening, zooming,
 *  copying or printing until a plan is chosen. */
function PreviewPages({ series: s, progress }: { series: Series; progress?: Progress }) {
  const status = new Map(progress?.lessons.map((l) => [l.id, l.status]))
  const painting = (progress?.images.active ?? 0) > 0
  if (!s.design) return null
  type Page = { key: string; lesson: LessonSummary; blocks: Block[] | null; first: boolean }
  const pages = s.lessons.flatMap((l): Page[] => {
    const blocks = l.content_json?.blocks
    const st = status.get(l.id) ?? l.status
    if (st === 'pending' || st === 'failed') return []  // not part of the free preview (a redone outline, a new section)
    if (!blocks || !['generated', 'edited', 'approved'].includes(st)) {
      return Array.from({ length: l.pages ?? 1 }, (_, i) => ({ key: `${l.id}:${i}`, lesson: l, blocks: null, first: i === 0 }))
    }
    return splitPages(blocks).map((page, i) => ({ key: `${l.id}:${i}`, lesson: l, blocks: page, first: i === 0 }))
  })
  if (!pages.length) return null
  const writing = pages.some((p) => !p.blocks)
  return (
    <section className="preview-pages" aria-label="Vista previa de tu tomo" onContextMenu={(e) => e.preventDefault()} onDragStart={(e) => e.preventDefault()}>
      <header>
        <h2 className="section-h">{writing ? 'Escribiendo e ilustrando tu tomo…' : 'Así quedó tu tomo'}</h2>
        <p className="muted small">Vista previa protegida. Con un plan lo ves en grande, lo editas, lo descargas e imprimes.</p>
      </header>
      <ul>
        {pages.map((p) => (
          <li key={p.key} className="preview-page">
            {p.blocks ? (
              <PageThumb design={s.design} position={p.lesson.position} title={p.lesson.title} blocks={p.blocks} bare={!p.first}
                         assets={s.assets} credits={s.credits} diagrams={p.lesson.diagrams} painting={painting} />
            ) : (
              <div className="thumb placeholder generating" aria-hidden="true"><span /><span /><span /><span /></div>
            )}
            <span className="watermark" aria-hidden="true" />
            <span className="preview-mark" aria-hidden="true">Vista previa</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** A section's blocks page by page: a page break starts a new page, and a picture book's plate is a page of its own. */
function splitPages(blocks: Block[]): Block[][] {
  const pages: Block[][] = [[]]
  for (const b of blocks) {
    const plate = b.type === 'image' && b.size === 'plate'
    if (b.type === 'page_break' || (plate && pages.at(-1)!.length)) pages.push([])
    if (b.type !== 'page_break') pages.at(-1)!.push(b)
    if (plate) pages.push([])
  }
  return pages.filter((p) => p.length)
}

function CoverPanel({ series: s }: { series: Series }) {
  const qc = useQueryClient()
  const repaint = useMutation({
    mutationFn: () => api.post(`/api/series/${s.id}/cover`),
    onSettled: () => Promise.all([qc.invalidateQueries({ queryKey: ['series', s.id] }), qc.invalidateQueries({ queryKey: ['series'], exact: true })]),
  })
  const busy = s.cover_status === 'queued' || s.cover_status === 'running' || repaint.isPending
  const [big, setBig] = useState(false)
  const cover = { title: tomeName(s), genre: s.genre, audience: s.audience.label, cover_url: s.cover_url, cover_status: s.cover_status, cover_lettered: s.cover_lettered,
                  cover_palette: s.cover_palette ?? s.design?.palette ?? null, design: s.design, marked: s.preview }
  return (
    <div className="cover-panel">
      <button className="cover-open" onClick={() => setBig(true)} disabled={!s.cover_url} aria-label="Ver la portada en grande">
        <BookCover size="hero" {...cover} />
      </button>
      {big && <CoverViewer {...cover} onClose={() => setBig(false)} />}
      {!s.owner && <button className="ghost small" onClick={() => repaint.mutate()} disabled={busy}>
        {busy ? 'Pintando…' : s.cover_url ? 'Otra portada' : s.cover_status === 'failed' ? 'Reintentar portada' : 'Crear portada'}
      </button>}
      {repaint.error && <p className="error small">{errorText(repaint.error, 'No se pudo pedir otra portada.')}</p>}
    </div>
  )
}

// The editorial flow, as a publisher runs it: plan, art direction, text, illustration, then the finished book.
const STAGES = ['Plan editorial', 'Dirección de arte', 'Texto', 'Ilustración', 'Libro listo']
const THINKING = ['Leyendo tu idea…', 'Buscando fuentes confiables…', 'Organizando las secciones…', 'Eligiendo el estilo visual…', 'Preparando tu portada…']

/** One line that changes every few seconds while the agents work, so the wait reads as progress. */
function useTicker(lines: string[], on: boolean, ms = 2800) {
  const [i, setI] = useState(0)
  useEffect(() => {
    if (!on || lines.length < 2) return
    const t = window.setInterval(() => setI((n) => (n + 1) % lines.length), ms)
    return () => window.clearInterval(t)
  }, [on, lines.length, ms])
  return lines[i % Math.max(1, lines.length)] ?? ''
}

/** The tome's progress as one card: which step of the book it is on, what is happening now, how much is done and,
 * while it is being illustrated, each plate as soon as it is painted. */
function TomeProgress({ series, status, progress, preview }: { series: Series; status: string; progress?: Progress; preview: boolean }) {
  const c = progress?.counts
  const img = progress?.images
  const sections = c ? c.generated + c.edited + c.approved : 0
  const textDone = !!c && c.total > 0 && sections + c.failed >= c.total
  // Pictures still coming: the book is not ready while a plate is being painted, whatever the text says.
  const painting = !!img && img.total > 0 && (img.active > 0 || img.done + img.failed < img.total)
  const stage = status === 'outlining' || status === 'outline_failed' ? 0
    : status === 'outline_ready' ? 1
    : (status === 'generating' && !textDone) ? 2
    : painting || status === 'generating' ? 3 : 4
  const writing = progress?.lessons.find((l) => l.status === 'generating')
  const working = stage === 0 ? status === 'outlining' : stage === 2 || stage === 3
  const live = useTicker(status === 'outlining' ? THINKING
    : stage === 2 ? [writing ? `Escribiendo «${writing.title}»` : 'Escribiendo tus páginas…', 'Revisando cada página…']
    : ['Pintando las láminas…', 'Revisando que cada lámina diga lo que dice el texto…', 'Cuidando cada detalle…'], working)
  const [title, sub] = stage === 0 ? (status === 'outline_failed'
      ? ['No pudimos diseñar el tomo', 'Prueba de nuevo o cambia un poco la idea.'] : ['Planeando tu libro', live])
    : stage === 1 ? (preview ? ['Tu vista previa', 'Mira tus páginas y, con un plan, genera el tomo completo.']
                             : ['El plan está listo: falta tu visto bueno', 'Nada se escribe ni se ilustra hasta que pulses «Generar así».'])
    : stage === 2 ? ['Escribiendo tu libro', live]
    : stage === 3 ? [`Ilustrando · ${img?.done ?? 0} de ${img?.total ?? 0} láminas`, live]
    : status === 'needs_attention' ? ['Algunas secciones necesitan otro intento', 'Reinténtalas abajo; no se cobran dos veces.']
    : ['Tu libro está listo', 'Descárgalo en PDF o Word cuando quieras.']
  const share = stage === 2 ? (c?.total ? sections / c.total : 0) : stage === 3 ? (img?.total ? img.done / img.total : 0) : 0
  const fill = (i: number) => (i < stage ? 1 : i === stage && stage === 4 ? 1 : i === stage ? share : 0)
  return (
    <section className={`run ${stage === 4 ? 'ready' : status}`} aria-live="polite">
      <div className="run-top">
        <div className="run-text">
          <p className="run-k">Paso {stage + 1} de {STAGES.length} · {STAGES[stage]}</p>
          <h2 className="run-t">{title}</h2>
          <p className="run-s" key={sub}>{sub}</p>
        </div>
        <div className="run-fig" aria-hidden={!working}>
          {stage === 4 ? <span className="run-done"><svg viewBox="0 0 16 16" width="22" height="22"><path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg></span>
            : (stage === 2 || stage === 3) ? <span className="run-pct">{Math.round(share * 100)}<small>%</small></span>
            : working ? <span className="run-orb" /> : null}
        </div>
      </div>
      <ol className="run-track">
        {STAGES.map((label, i) => (
          <li key={label} className={i < stage || stage === 4 ? 'done' : i === stage ? 'active' : ''}>
            <span className={`run-bar${i === stage && working && stage === 0 ? ' busy' : ''}`}><i style={{ transform: `scaleX(${fill(i)})` }} /></span>
            <span className="run-l">{label}</span>
          </li>
        ))}
      </ol>
      {stage === 1 && !preview && !series.owner && <NextStep series={series} />}
      {(stage === 2 || stage === 3) && c && (
        <dl className="run-stats">
          <div><dt>Secciones</dt><dd>{sections}<span>/{c.total}</span></dd></div>
          {img && img.total > 0 && <div><dt>Láminas</dt><dd>{img.done}<span>/{img.total}</span></dd></div>}
          {c.failed > 0 && <div className="bad"><dt>Por reintentar</dt><dd>{c.failed}</dd></div>}
        </dl>
      )}
      {stage === 3 && <PaintedPlates series={series} total={img?.total ?? 0} />}
    </section>
  )
}

/** After the plan: what is done, what is still being painted, and the one button that moves the tome on. */
function NextStep({ series: s }: { series: Series }) {
  const painting = s.cover_status === 'queued' || s.cover_status === 'running'
  return (
    <div className="next-step">
      <ol>
        <li className="done">Plan del libro: listo</li>
        <li className={painting ? 'busy' : s.cover_url ? 'done' : ''}>
          {painting ? 'Portada: pintándose (1 a 3 minutos). No hace falta esperarla.' : s.cover_url ? 'Portada: lista' : 'Portada: pendiente'}
        </li>
        <li className="now">Siguiente: revisa las secciones abajo y pulsa <strong>«Generar así»</strong></li>
      </ol>
      <button className="primary" onClick={() => document.getElementById('generar')?.scrollIntoView({ behavior: 'smooth', block: 'center' })}>
        Revisar y generar ↓
      </button>
    </div>
  )
}

/** The plates painted so far, newest last, and a soft slot for each one still on the easel. */
function PaintedPlates({ series, total }: { series: Series; total: number }) {
  const painted = series.lessons.flatMap((l) => (l.content_json?.blocks ?? [])
    .filter((b): b is Extract<Block, { type: 'image' }> => b.type === 'image' && b.kind === 'illustration' && !!b.asset_id && !!series.assets[b.asset_id])
    .map((b) => ({ key: `${l.id}:${b.id}`, url: series.assets[b.asset_id!], alt: b.subject })))
  const waiting = Math.max(0, Math.min(total, 12) - painted.length)
  return (
    <ul className="run-plates" aria-label="Láminas pintadas">
      {painted.map((p) => <li key={p.key}><img src={p.url} alt={p.alt} loading="lazy" /></li>)}
      {Array.from({ length: waiting }, (_, i) => <li key={`w${i}`} className="waiting" aria-hidden="true" />)}
    </ul>
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
  const role = useMe().data?.platform_role
  const staff = role === 'admin' || role === 'staff'  // what a tome cost us is ours to see, not the customer's
  if (!q) return null
  const v = VERDICT[q.verdict]
  const t = q.text
  const rows: [string, string][] = [
    ['Texto', t.score === null ? 'Sin revisión del Editor' : `Editor ${String(t.score).replace('.', ',')}/5 · ${t.fixed} correcciones aplicadas`],
    ['Datos', q.facts?.needed ? `${q.facts.facts} datos verificados en ${q.facts.sources} fuentes` : 'No requiere fuentes'],
    ['Ilustraciones', q.art.total ? `${q.art.done} de ${q.art.total}${q.art.failed ? ` · ${q.art.failed} fallidas` : ''}` : 'Sin ilustraciones'],
    ...(q.pages.target ? [['Páginas', q.pages.actual ? `${q.pages.actual} de ${q.pages.target} pedidas` : `${q.pages.target} pedidas · genera el PDF para contarlas`] as [string, string]] : []),
    ...(!staff ? [] : [['Costo IA', `${usd(q.cost.total_usd)} · texto ${usd(q.cost.text_usd)}${q.cost.search_usd ? `, búsqueda ${usd(q.cost.search_usd)}` : ''}, portada ${usd(q.cost.cover_usd)}, ilustraciones ${usd(q.cost.images_usd + q.cost.review_usd)}`] as [string, string]]),
    ...(q.cost.minutes === null || !staff ? [] : [['Tiempo', `${String(q.cost.minutes).replace('.', ',')} min de escritura e ilustración`] as [string, string]]),
    ['Impresión', q.print ? `${{ lista: 'Lista', aceptable: 'Aceptable', baja: 'Baja resolución' }[q.print.rating]}${q.print.layout?.fixed.length ? ` · maqueta ajustada en ${q.print.layout.fixed.length} imágenes` : ''}` : 'Genera el PDF para revisarla'],
  ]
  return (
    <details className="panel quality">
      <summary>
        <span className="section-h">Calidad</span>
        <span className={`pill ${v.pill}`}>{v.label}</span>
        {staff && <span className="pill idle" title="Lo que costó el tomo en IA (solo lo ve el equipo)">Costó {usd(q.cost.total_usd)} USD</span>}
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

const VARIANT_LABEL: Record<TomeVariant, string> = { style: 'Otro estilo', text: 'Texto reescrito', story: 'Otra historia', next: 'Siguiente tomo' }

/** The tome's other versions, to go back and forth between them. */
function VersionLinks({ series: s }: { series: Series }) {
  return (
    <nav className="version-links" aria-label="Otras versiones">
      <span className="muted small">{s.variant ? `${VARIANT_LABEL[s.variant]} de otro tomo ·` : 'Versiones:'}</span>
      {s.versions!.map((v) => (
        <Link key={v.id} to={`/app/tomos/${v.id}`} className="chip">
          {v.id === s.source_id ? 'Original' : v.variant ? VARIANT_LABEL[v.variant] : 'Versión'}
          <span className="muted"> · {v.title ?? v.topic}</span>
        </Link>
      ))}
    </nav>
  )
}

const MODES: { key: TomeVariant; title: string; text: string }[] = [
  { key: 'style', title: 'Otro estilo', text: 'El mismo texto y personajes, pintado de nuevo en otro estilo de ilustración.' },
  { key: 'text', title: 'Reescribir el texto', text: 'Las mismas ilustraciones y portada; solo cambia la redacción. No se pinta nada.' },
  { key: 'story', title: 'Cambiar la historia o el contenido', text: 'Un tomo nuevo a partir de tu pedido ajustado, con el mismo diseño.' },
  { key: 'next', title: 'Siguiente tomo de la serie', text: 'Continúa este tomo con los mismos personajes y estilo, sin repetir temas.' },
]

/** Hacer otra versión: the same book in another style, its story or content changed, or the next one of its series.
 * The original stays as it is; the new tome opens when it is created. */
function NewVersion({ series: s }: { series: Series }) {
  const { data: me } = useMe()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const paid = !!me && !me.anonymous && me.plan.key !== 'prueba'
  const ready = s.status === 'ready'
  const [mode, setMode] = useState<TomeVariant>(ready ? 'style' : 'story')
  const [house, setHouse] = useState<string | null>(null)
  const [request, setRequest] = useState(s.topic)
  const [changes, setChanges] = useState('')
  const [keepCast, setKeepCast] = useState(true)
  const plates = s.lessons.reduce((n, l) => n + (l.content_json?.blocks ?? []).filter((b) => b.type === 'image' && b.kind === 'illustration').length, 0)
  const pages = s.lessons.reduce((n, l) => n + (l.pages ?? 0), 0) || s.lessons.length
  const illustrated = s.genre === 'picture_book' || s.genre === 'story_book'
  const cost = mode === 'style' ? 4 + Math.ceil(plates / 2) : mode === 'text' ? Math.max(Math.ceil(plates / 4), 1) : 5 + pages
  // A story written before the Narrator has no narration: another style keeps that text, a new story rewrites it.
  const oldStory = s.genre === 'story_book' && !s.lessons.some((l) => (l.content_json?.blocks ?? []).some((b) => b.type === 'image' && !!b.narration))
  const create = useMutation({
    mutationFn: () => api.post<{ series: { id: string } }>(`/api/series/${s.id}/versions`, {
      mode, house_style: house, keep_cast: keepCast,
      ...(mode === 'style' ? {} : mode === 'text' ? { changes: changes.trim() } : { request: request.trim() === s.topic.trim() ? null : request.trim(), changes: changes.trim() || null }) }),
    onSuccess: ({ series }) => {
      void qc.invalidateQueries({ queryKey: ['series'] })
      navigate(`/app/tomos/${series.id}`)
    },
  })
  const missing = mode === 'style' ? !house || house === s.house_style : mode === 'text' ? changes.trim().length < 3 : mode === 'story' && !changes.trim() && request.trim() === s.topic.trim()
  return (
    <details className="panel sources new-version">
      <summary>
        <span className="section-h">Hacer otra versión</span>
        <span className="muted small">Otro estilo, otra historia o el siguiente tomo; este se queda como está</span>
      </summary>
      {!paid ? (
        <p className="small">Hacer otras versiones de un tomo está incluido en los planes de pago. <Link to={`/app/plan?tomo=${s.id}`}>Elegir un plan</Link></p>
      ) : (
        <>
          <div className="version-modes" role="radiogroup" aria-label="Qué versión hacer">
            {MODES.filter((m) => m.key !== 'text' || illustrated).map((m) => {
              const off = (m.key === 'style' || m.key === 'text') && !ready
              return (
                <button key={m.key} type="button" role="radio" aria-checked={mode === m.key} disabled={off}
                  className={mode === m.key ? 'on' : undefined} onClick={() => setMode(m.key)}>
                  <strong>{m.title}</strong>
                  <span className="muted small">{off ? 'Cuando el tomo esté terminado.' : m.text}</span>
                </button>
              )
            })}
          </div>
          {mode === 'text' && (
            <label className="field">
              <span>¿Qué quieres cambiar del texto?</span>
              <textarea value={changes} onChange={(e) => setChanges(e.target.value)} rows={3} maxLength={2000}
                placeholder="Ej.: que suene más a cuento, frases más cortas para 4 años, que Karla hable más" />
            </label>
          )}
          {(mode === 'story' || mode === 'next') && (
            <>
              <label className="field">
                <span>Pedido</span>
                <textarea value={request} onChange={(e) => setRequest(e.target.value)} rows={3} maxLength={2000} />
              </label>
              <label className="field">
                <span>{mode === 'next' ? '¿Qué debe tratar el siguiente tomo? (opcional)' : '¿Qué quieres cambiar?'}</span>
                <textarea value={changes} onChange={(e) => setChanges(e.target.value)} rows={3} maxLength={2000}
                  placeholder={mode === 'next' ? 'Ej.: ahora visitan el mar y conocen a las ballenas' : 'Ej.: que la protagonista sea una niña pirata y que el final ocurra en la playa'} />
              </label>
              {mode === 'story' && s.cast?.length ? (
                <label className="check small"><input type="checkbox" checked={keepCast} onChange={(e) => setKeepCast(e.target.checked)} /> Conservar los personajes ({s.cast.map((c) => c.name).join(', ')})</label>
              ) : null}
            </>
          )}
          {mode === 'style' && oldStory && (
            <p className="notice small">Este cuento se escribió antes del Narrador y «Otro estilo» conserva su texto. Para que se reescriba como cuento sin pintar de nuevo, elige «Reescribir el texto».</p>
          )}
          {mode !== 'text' && <StylePicker value={house} onChange={setHouse} paid />}
          <p className="muted small">
            {mode === 'style' ? (house === s.house_style || !house ? 'Elige un estilo distinto al actual.' : `Unos ${cost} créditos: portada nueva y ${plates} láminas pintadas otra vez.`)
              : mode === 'text' ? `${cost} ${cost === 1 ? 'crédito' : 'créditos'}: se conservan las ${plates} ilustraciones y la portada. Sirve para mejorar la redacción; para cambiar de qué trata la historia, elige «Cambiar la historia».`
              : `Unos ${cost} créditos, como un tomo nuevo. ${house ? '' : 'Mantiene el estilo de ilustración de este tomo. '}Primero revisas su plan.`}
          </p>
          <button className="primary" onClick={() => create.mutate()} disabled={missing || create.isPending}>
            {create.isPending ? 'Creando…' : mode === 'style' ? 'Pintar en este estilo' : mode === 'text' ? 'Reescribir el texto' : mode === 'next' ? 'Crear el siguiente tomo' : 'Crear la nueva versión'}
          </button>
          {create.error && <p className="error small" role="alert">{errorText(create.error, 'No se pudo crear la versión.')}</p>}
        </>
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
  const { data: me } = useMe()
  // Building a series by levels is for paid plans: a visitor sees what it would add, locked.
  const locked = !me || me.anonymous || me.plan.key === 'prueba'
  const sources = s.research?.program?.sources ?? []
  // A level joins this tome's collection; a tome without one starts it, named after itself.
  const open = useMutation({
    mutationFn: async (lv: Level) => {
      const collection = s.collection_id ?? (await api.post<{ collection: { id: string } }>(
        '/api/collections', { name: tomeName(s), series_ids: [s.id] })).collection.id
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
      {locked
        ? <Link className="ghost small" to={`/app/plan?tomo=${s.id}`}>Con un plan</Link>
        : <button className="ghost small" onClick={() => open.mutate(lv)} disabled={open.isPending}>Crear este nivel</button>}
    </li>
  )
  const before = levels.filter((lv) => lv.relation === 'anterior')
  const after = levels.filter((lv) => lv.relation === 'siguiente')
  return (
    <details className="panel sources levels">
      <summary>
        <span className="section-h">Niveles sugeridos</span>
        <span className="muted small">{before.length + after.length} niveles para hacer una serie</span>
      </summary>
      <p className="muted small">Según los programas de estudio encontrados, este tema se trabaja así antes y después de este tomo.
        {locked && ' Crear la serie completa por niveles está incluido en los planes de pago.'}</p>
      <ol className="level-list">
        {before.map(card)}
        <li className="level current">
          <span className="eyebrow">Este tomo · {s.audience.label}</span>
          <p className="small">{tomeName(s)}</p>
        </li>
        {after.map(card)}
      </ol>
    </details>
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
  const house = HOUSE_STYLES.find((h) => h.key === d.house_style)
  const plates = series.genre === 'picture_book' || series.genre === 'story_book'
  const seal = identities.find((i) => i.id === d.identity_id)?.design?.mark_svg  // drawn by our server
  const value = d.identity_id ? `i:${d.identity_id}` : d.style_id ? `s:${d.style_id}` : `t:${d.theme}`
  return (
    <section className="panel design-preview">
      <div className="design-sample">
        {plates ? <PlateSample series={series} />
          : preview && <PageThumb design={d} position={1} title={preview.title} blocks={preview.blocks} diagrams={preview.diagrams} />}
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
          {house ? ` · ilustración: ${house.name}` : d.illustration ? ` · ilustración: ${ART_LABEL[d.illustration]}` : ''}
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

/** A picture book's look is its plates: a sample page in the tome's illustration style (or its painted cover) with
 * the first page's text over it, the way the book will print. */
function PlateSample({ series: s }: { series: Series }) {
  const house = s.design?.house_style
  const image = house ? sampleOf(house) : s.cover_url
  const first = s.lessons[0]
  const story = s.genre === 'story_book'
  return (
    <div className="plate-sample" aria-label="Lámina de muestra">
      {image ? <img src={image} alt="" /> : <span className="plate-sample-ph">La ilustración llega con la portada…</span>}
      <div className="plate-sample-card">
        <span className="eyebrow">{story ? 'Página 1' : `1 · ${first?.title ?? ''}`}</span>
        <strong>{story ? (first?.title ?? s.title ?? '') : (first?.key_points[0] ?? first?.title ?? '')}</strong>
      </div>
      <span className="plate-sample-tag">Muestra</span>
    </div>
  )
}

/** An illustrated book's section shows its first painted plate: a miniature of the page in HTML can't match the
 * printed composition. Undefined for other books and while nothing is painted. */
function plateOf(blocks: Block[], series: Series): string | undefined {
  if (series.genre !== 'picture_book' && series.genre !== 'story_book') return undefined
  const plate = blocks.find((b) => b.type === 'image' && b.size === 'plate' && b.asset_id && series.assets?.[b.asset_id])
  return plate && plate.type === 'image' && plate.asset_id ? series.assets[plate.asset_id] : undefined
}

/** The title, editable once the tome has its plan: the cover prints it as text, so nothing is repainted. */
function TomeTitle({ series: s }: { series: Series }) {
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(s.title ?? '')
  // The title is painted into the cover: a new title paints a new cover.
  const repaint = !!s.cover_lettered && title.trim().replace(/\s+/g, ' ') !== s.title
  const rename = useMutation({
    mutationFn: () => api.patch(`/api/series/${s.id}/title`, { title: title.trim(), repaint: repaint }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['series', s.id] })
      setEditing(false)
    },
  })
  if (!editing) {
    return (
      <div className="tome-title">
        <h1 className="display sm">{s.title}</h1>
        <button type="button" className="link-button small" onClick={() => { setTitle(s.title ?? ''); setEditing(true) }}>Cambiar título</button>
      </div>
    )
  }
  return (
    <form className="tome-title editing" onSubmit={(e) => { e.preventDefault(); rename.mutate() }}>
      <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={300} autoFocus aria-label="Título del tomo" />
      <button className="primary" disabled={title.trim().length < 2 || rename.isPending}>
        {rename.isPending ? 'Guardando…' : repaint ? 'Guardar y pintar portada (4 créditos)' : 'Guardar'}
      </button>
      <button type="button" className="ghost" onClick={() => setEditing(false)}>Cancelar</button>
      {repaint && <p className="muted small">El título está pintado en la portada, así que se pinta una portada nueva con el título nuevo.</p>}
      {rename.error && <p className="error small" role="alert">{errorText(rename.error, 'No se pudo cambiar el título.')}</p>}
    </form>
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
  const { data: me } = useMe()
  const navigate = useNavigate()
  const choosePlan = `/app/plan?tomo=${series.id}`
  // The free preview stops at the outline and cover: the full tome comes with a plan (Google first for a visitor).
  const needsPlan = series.preview && !!me && (me.anonymous || me.plan.key === 'prueba')

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
      if (needsPlan) {
        if (me.anonymous) await saveWithGoogle(choosePlan)
        else navigate(choosePlan)
        return
      }
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
              <textarea value={d.objectives} onChange={(e) => update(i, { objectives: e.target.value })} rows={4} placeholder="Objetivos (uno por línea)" aria-label="Objetivos" />
              <textarea rows={3} value={d.key_points} onChange={(e) => update(i, { key_points: e.target.value })} placeholder="Puntos clave, separados por comas" aria-label="Puntos clave" />
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

      {series.preview && <p className="muted small">Las páginas de tu vista previa ya están hechas y no gastan créditos: solo se cobran las secciones nuevas o las que cambies de páginas o contenido.</p>}
      <div className="action-bar" id="generar">
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
                <Link to={plateOf(blocks, series) ? `/app/tomos/${series.id}/paginas?s=${l.id}&p=${blocks.find((b) => b.type === 'image' && b.size === 'plate')?.id ?? ''}` : `/app/secciones/${l.id}`} className="thumb-link" aria-label={`Abrir sección ${l.position}: ${l.title}`}>
                  {plateOf(blocks, series) ? (
                    <div className="thumb"><img className="thumb-img" src={plateOf(blocks, series)} alt="" /></div>
                  ) : <PageThumb design={series.design} position={l.position} title={l.title} blocks={blocks} assets={series.assets} credits={series.credits} diagrams={byId.get(l.id)?.diagrams} painting={progress.images.active > 0} />}
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
type Paper = 'A4' | 'Letter' | '8x10' | '6x9' | '17x21'
const PAPERS: Record<Edition, { value: Paper; label: string }[]> = {
  digital: [{ value: 'A4', label: 'A4' }, { value: 'Letter', label: 'Carta' }, { value: '17x21', label: '17×21' }],
  print: [{ value: 'Letter', label: '8.5×11' }, { value: '8x10', label: '8×10' }, { value: '6x9', label: '6×9' }, { value: '17x21', label: '17×21' }, { value: 'A4', label: 'A4' }],
}
const RATING: Record<Preflight['rating'], string> = { lista: 'Lista para imprenta', aceptable: 'Aceptable', baja: 'Baja resolución' }

function ExportPanel({ seriesId, genre, latest, images }: { seriesId: string; genre: Series['genre']; latest: Progress['latest_export']; images: Progress['images'] }) {
  const plan = useMe().data?.plan
  const [format, setFormat] = useState<'pdf' | 'docx'>('pdf')
  const [edition, setEdition] = useState<Edition>('digital')
  // A picture book or a story is printed at its own trim, 17×21, like the books it sits next to.
  const book = genre === 'picture_book' || genre === 'story_book'
  const firstPaper = (e: Edition): Paper => (book ? '17x21' : PAPERS[e][0].value)
  const [paper, setPaper] = useState<Paper>(firstPaper('digital'))
  const [answers, setAnswers] = useState(true)
  const [ink, setInk] = useState<'color' | 'saver'>('color')
  // A PDF made before the last pictures arrived would miss them: start a fresh one instead.
  const [exportId, setExportId] = useState<string | null>(latest && latest.status !== 'failed' && !latest.stale ? latest.id : null)
  const illustrating = images.active > 0
  const current = useExport(exportId)
  const create = useMutation({
    mutationFn: () => api.post<{ export: Export }>(`/api/series/${seriesId}/exports`, { paper, include_answer_key: answers, edition, format, ink }),
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
              : ink === 'saver'
              ? 'Blanco y negro para imprimir en casa o en la escuela: ilustraciones en grises claros y sin fondos de color, gasta mucha menos tinta.'
              : edition === 'print'
              ? 'Interior y portada con lomo por separado, a medida de KDP y otras imprentas.'
              : `Portada, índice, secciones${images.total ? ', ilustraciones' : ''}${answers ? ' y solucionario' : ''}, listo para imprimir.`}
        </p>
      </div>
      <div className="export-opts">
        <div className="segmented" role="radiogroup" aria-label="Formato">
          {(['pdf', 'docx'] as const).map((f) => (
            <button key={f} role="radio" aria-checked={format === f} className={format === f ? 'on' : ''}
              onClick={change(() => { setFormat(f); if (f === 'docx') { setEdition('digital'); setPaper(firstPaper('digital')) } })}>
              {f === 'pdf' ? 'PDF' : <>Word{plan && !plan.word && <Lock />}</>}
            </button>
          ))}
        </div>
        {format === 'pdf' && <div className="segmented" role="radiogroup" aria-label="Edición">
          {(['digital', 'print'] as const).map((e) => (
            <button key={e} role="radio" aria-checked={edition === e} className={edition === e ? 'on' : ''}
              onClick={change(() => { setEdition(e); setPaper(firstPaper(e)) })}>
              {e === 'digital' ? 'Digital' : <>Imprenta{plan && !plan.print_edition && <Lock />}</>}
            </button>
          ))}
        </div>}
        <div className="segmented" role="radiogroup" aria-label="Tinta">
          {(['color', 'saver'] as const).map((k) => (
            <button key={k} role="radio" aria-checked={ink === k} className={ink === k ? 'on' : ''} onClick={change(() => setInk(k))}>
              {k === 'color' ? 'Color' : 'Blanco y negro'}
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
            <button className="ghost" onClick={() => create.mutate()} disabled={busy || illustrating}
              title="Maqueta el libro otra vez con los últimos cambios de texto, posiciones e ilustraciones">
              {create.isPending ? <><span className="spinner" /> Maquetando…</> : 'Volver a maquetar'}
            </button>
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
      {!exportId && latest?.stale && latest.status === 'succeeded' && (
        <p className="notice small">Cambiaste páginas después del último PDF: genéralo de nuevo para que las incluya.</p>
      )}
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
