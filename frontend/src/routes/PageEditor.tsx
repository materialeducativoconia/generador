import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { AppShell } from '../components/AppShell'
import { PlateStage } from '../components/PlateStage'
import { errorText } from '../components/ErrorNote'
import { api } from '../lib/apiClient'
import { tomeName } from '../lib/labels'
import { useSeries } from '../lib/queries'
import type { Block, Design, PlatePlace } from '../lib/types'

type Plate = Extract<Block, { type: 'image' }>
type Page = { lessonId: string; position: number; section: string; block: Plate; first: boolean }

const LAYOUTS: { key: NonNullable<Plate['layout']>; label: string }[] = [
  { key: 'bleed', label: 'Ilustración a toda página' },
  { key: 'band', label: 'Ilustración arriba, texto abajo' },
  { key: 'vignette', label: 'Recortada sobre blanco' },
]

/** Editor de páginas: each page of an illustrated book as the PDF prints it, its words and composition edited by
 * hand (free) and its picture painted again from an instruction (one credit). */
export function PageEditor() {
  const { id = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const series = useSeries(id)
  const s = series.data
  const pages = useMemo<Page[]>(() => (s?.lessons ?? []).flatMap((l) =>
    (l.content_json?.blocks ?? []).filter((b): b is Plate => b.type === 'image' && b.size === 'plate')
      .map((block, i) => ({ lessonId: l.id, position: l.position, section: l.title, block, first: i === 0 }))), [s])
  const current = pages.find((p) => p.block.id === params.get('p') && p.lessonId === params.get('s')) ?? pages[0]
  const next = current && pages[pages.indexOf(current) + 1]
  const paper = s?.genre === 'story_book' || s?.genre === 'picture_book' ? '17x21' : 'A4'
  const painting = pages.some((p) => !p.block.asset_id)
  const { refetch } = series

  useEffect(() => {  // a picture being painted again: look for it every few seconds
    if (!painting) return
    const t = setInterval(() => void refetch(), 6000)
    return () => clearInterval(t)
  }, [painting, refetch])

  if (series.isPending) return <AppShell><div className="skeleton tall" /></AppShell>
  if (!s) return <AppShell><p className="error">{errorText(series.error, 'No pudimos cargar el tomo.')}</p></AppShell>
  return (
    <AppShell>
      <Link to={`/app/tomos/${id}`} className="back">← Volver al tomo</Link>
      <header className="page-editor-head">
        <p className="eyebrow">Editor de páginas</p>
        <h1 className="display sm">{tomeName(s)}</h1>
      </header>
      {!current ? (
        <p className="muted">Este tomo no tiene páginas ilustradas para editar.</p>
      ) : (
        <div className="page-editor">
          <ol className="page-strip" aria-label="Páginas">
            {pages.map((p, i) => {
              const url = p.block.asset_id ? s.assets[p.block.asset_id] : undefined
              const on = p === current
              return (
                <li key={`${p.lessonId}:${p.block.id}`}>
                  <button type="button" className={on ? 'on' : undefined} aria-current={on ? 'page' : undefined}
                    onClick={() => setParams({ s: p.lessonId, p: p.block.id }, { replace: true })}>
                    {url ? <img src={url} alt="" /> : <span className="page-strip-wait" aria-hidden="true" />}
                    <span className="page-strip-n">{i + 1}</span>
                  </button>
                </li>
              )
            })}
          </ol>
          <PageView key={`${current.lessonId}:${current.block.id}`} seriesId={id} page={current} paper={paper}
            picture={current.block.asset_id ? s.assets[current.block.asset_id] : undefined} story={s.genre === 'story_book'} design={s.design} />
          {next && <Prefetch page={next} paper={paper} />}
        </div>
      )}
    </AppShell>
  )
}

// The picture of the page as printed; it follows the saved page (its asset and words), not the form.
function previewQuery(page: Page, paper: string) {
  const b = page.block
  const stamp = `${b.asset_id ?? 'none'}:${b.layout ?? ''}:${b.narration ?? ''}:${b.question ?? ''}:${b.answer ?? ''}:${(b.notes ?? []).join('|')}:${b.find ?? ''}:${JSON.stringify(b.place ?? {})}`
  return {
    queryKey: ['page-preview', page.lessonId, b.id, stamp, paper],
    queryFn: () => api.get<{ image: string; spots?: (string | null)[]; low?: boolean; looks?: Record<string, string> }>(`/api/lessons/${page.lessonId}/pages/${b.id}/preview?paper=${paper}`),
    staleTime: Infinity,
  }
}

/** The next page, rendered while the user looks at this one, so moving forward opens it at once. */
function Prefetch({ page, paper }: { page: Page; paper: string }) {
  const qc = useQueryClient()
  const options = previewQuery(page, paper)
  useEffect(() => { void qc.prefetchQuery(options) }, [qc, options.queryKey.join('/')])  // eslint-disable-line react-hooks/exhaustive-deps
  return null
}

function PageView({ seriesId, page, paper, picture, story, design }: { seriesId: string; page: Page; paper: string; picture?: string; story: boolean; design?: Design | null }) {
  const qc = useQueryClient()
  const b = page.block
  const [narration, setNarration] = useState(b.narration ?? '')
  const [question, setQuestion] = useState(b.question ?? '')
  // null: the page has no such text (removed, or never written); the PDF then leaves its place out.
  const [answer, setAnswer] = useState<string | null>(b.answer ?? null)
  const [notes, setNotes] = useState<string[]>(() => b.notes ?? [])
  const [find, setFind] = useState<string | null>(b.find ?? null)
  const [layout, setLayout] = useState(b.layout ?? 'bleed')
  const [place, setPlace] = useState<PlatePlace>(b.place ?? {})
  const [view, setView] = useState<'move' | 'print'>('move')
  const [ask, setAsk] = useState('')
  const base = `/api/lessons/${page.lessonId}/pages/${b.id}`
  const preview = useQuery(previewQuery(page, paper))
  const refresh = () => Promise.all([qc.invalidateQueries({ queryKey: ['series', seriesId] }), qc.invalidateQueries({ queryKey: ['progress', seriesId] })])
  const save = useMutation({
    mutationFn: () => api.patch(base, {
      ...(b.narration != null || story ? { narration } : {}),
      ...(b.question != null ? { question } : {}),
      ...(!story ? { answer: answer ?? '', notes: notes.filter((n) => n.trim()), find: find ?? '' } : {}),
      layout,
      ...(placed ? { place } : {}),
    }),
    onSuccess: refresh,
  })
  const repaint = useMutation({
    mutationFn: () => api.post(`${base}/repaint`, { instructions: ask.trim() }),
    onSuccess: async () => {
      setAsk('')
      await Promise.all([refresh(), qc.invalidateQueries({ queryKey: ['me'] })])
    },
  })
  const placed = JSON.stringify(place) !== JSON.stringify(b.place ?? {})
  const dirty = narration !== (b.narration ?? '') || question !== (b.question ?? '') || (answer ?? '') !== (b.answer ?? '') ||
    (find ?? '') !== (b.find ?? '') || layout !== (b.layout ?? 'bleed') ||
    notes.filter((n) => n.trim()).join('|') !== (b.notes ?? []).join('|') || placed
  // Texts lie over the picture only on a bleed page; an inset diagram keeps its own place at the foot.
  const movable = layout === 'bleed' && !!picture && !!b.asset_id
  const layouts = LAYOUTS.filter((l) => !story || l.key !== 'vignette')
  // A fact removed: the ones after it move up a place, and so does where the user had dragged them.
  const dropNote = (i: number) => {
    setNotes(notes.filter((_, j) => j !== i))
    const moved: PlatePlace = { ...place }
    for (let j = i; j < 4; j++) {
      const key = `n${j}` as keyof PlatePlace, after = place[`n${j + 1}` as keyof PlatePlace]
      if (after) moved[key] = after
      else delete moved[key]
    }
    setPlace(moved)
  }

  return (
    <>
      <figure className="page-preview">
        {movable && (
          <div className="page-view-switch">
            <div className="segmented-inline" role="radiogroup" aria-label="Vista">
              <button type="button" role="radio" aria-checked={view === 'move'} className={view === 'move' ? 'chip on' : 'chip'} onClick={() => setView('move')}>Mover textos</button>
              <button type="button" role="radio" aria-checked={view === 'print'} className={view === 'print' ? 'chip on' : 'chip'} onClick={() => setView('print')}>Vista de impresión</button>
            </div>
            {view === 'move' && Object.keys(place).length > 0 && <button type="button" className="ghost small" onClick={() => setPlace({})}>Volver al acomodo automático</button>}
          </div>
        )}
        {movable && view === 'move' ? (
          <PlateStage picture={picture!} design={design} kicker={page.first ? `${page.position} · ${page.section}` : undefined}
            narration={b.narration != null || story ? narration : undefined} question={question} answer={answer ?? undefined}
            notes={notes} find={find ?? undefined} spots={preview.data?.spots} low={preview.data?.low} place={place} onPlace={setPlace}
            looks={dirty ? undefined : preview.data?.looks} inset={!!b.inset} />
        ) : preview.data ? <img src={preview.data.image} alt={`Página: ${b.narration ?? b.question ?? b.subject}`} />
          : picture && !preview.isError ? (  // the painting itself, at once, while the printed page is laid out
            <div className="page-preview-draft"><img src={picture} alt="" /><span className="notice small">Preparando la página…</span></div>
          ) : <div className="page-preview-wait">{preview.isError ? 'No se pudo mostrar la página.' : 'Preparando la página…'}</div>}
        {movable && view === 'move' && <figcaption className="muted small">Arrastra la pregunta, los datos o el reto con el dedo o el cursor; lo que escribes a la derecha se ve aquí al momento. Guarda para llevarlo al PDF.</figcaption>}
        {movable && view === 'print' && placed && <figcaption className="muted small">La vista de impresión muestra la página guardada: guarda los cambios para verlos aquí.</figcaption>}
        {!b.asset_id && <figcaption className="notice small">Pintando la ilustración de nuevo… aparecerá aquí en uno o dos minutos.</figcaption>}
      </figure>
      <aside className="page-form">
        <p className="muted small">{page.position} · {page.section}</p>
        {(b.narration != null || story) && (
          <label className="field"><span>Texto de la página</span>
            <textarea value={narration} onChange={(e) => setNarration(e.target.value)} rows={5} maxLength={700} /></label>
        )}
        {b.question != null && (
          <label className="field"><span>Pregunta</span>
            <input value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={300} /></label>
        )}
        {!story && (answer != null ? (
          <div className="field">
            <span className="field-head"><label htmlFor="pe-answer">Respuesta</label>
              <button type="button" className="ghost small" onClick={() => setAnswer(null)}>Quitar</button></span>
            <textarea id="pe-answer" value={answer} onChange={(e) => setAnswer(e.target.value)} rows={3} maxLength={500} />
          </div>
        ) : <button type="button" className="ghost small add-text" onClick={() => setAnswer('')}>+ Añadir respuesta</button>)}
        {!story && (
          <fieldset className="field"><legend>Datos</legend>
            {notes.map((n, i) => (
              <span key={i} className="removable">
                <input value={n} onChange={(e) => setNotes(notes.map((x, j) => (j === i ? e.target.value : x)))}
                  maxLength={140} aria-label={`Dato ${i + 1}`} />
                <button type="button" className="ghost small" aria-label={`Quitar el dato ${i + 1}`} onClick={() => dropNote(i)}>✕</button>
              </span>
            ))}
            {notes.length < 4 && <button type="button" className="ghost small add-text" onClick={() => setNotes([...notes, ''])}>+ Añadir dato</button>}
          </fieldset>
        )}
        {!story && (find != null ? (
          <div className="field">
            <span className="field-head"><label htmlFor="pe-find">Observa y encuentra</label>
              <button type="button" className="ghost small" onClick={() => setFind(null)}>Quitar</button></span>
            <input id="pe-find" value={find} onChange={(e) => setFind(e.target.value)} maxLength={300} />
          </div>
        ) : <button type="button" className="ghost small add-text" onClick={() => setFind('')}>+ Añadir reto «Observa y encuentra»</button>)}
        {b.layout !== 'spread' && (
          <fieldset className="field"><legend>Composición</legend>
            <div className="segmented" role="radiogroup" aria-label="Composición">
              {layouts.map((l) => (
                <button key={l.key} type="button" role="radio" aria-checked={layout === l.key}
                  className={layout === l.key ? 'on' : undefined} onClick={() => setLayout(l.key)}>{l.label}</button>
              ))}
            </div>
            {layout !== (b.layout ?? 'bleed') && <span className="muted small">La ilustración se recorta al nuevo formato; si no encaja, repíntala abajo.</span>}
          </fieldset>
        )}
        <button className="primary" onClick={() => save.mutate()} disabled={!dirty || save.isPending}>
          {save.isPending ? 'Guardando…' : 'Guardar cambios'}
        </button>
        {save.error && <p className="error small" role="alert">{errorText(save.error, 'No se pudo guardar la página.')}</p>}
        {save.isSuccess && !dirty && <p className="muted small" role="status">Guardado. El próximo PDF ya lo incluye.</p>}

        <hr />
        <label className="field"><span>Repintar esta ilustración</span>
          <textarea value={ask} onChange={(e) => setAsk(e.target.value)} rows={3} maxLength={400}
            placeholder="Ej.: que Karla mire hacia el nido; más luz de mañana; el águila más cerca" /></label>
        <button className="ghost" onClick={() => repaint.mutate()} disabled={ask.trim().length < 3 || repaint.isPending || !b.asset_id}>
          {repaint.isPending ? 'Enviando…' : 'Repintar (1 crédito)'}
        </button>
        {repaint.error && <p className="error small" role="alert">{errorText(repaint.error, 'No se pudo repintar.')}</p>}
      </aside>
    </>
  )
}
