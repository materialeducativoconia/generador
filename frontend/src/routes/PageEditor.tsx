import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { AppShell } from '../components/AppShell'
import { errorText } from '../components/ErrorNote'
import { api } from '../lib/apiClient'
import { tomeName } from '../lib/labels'
import { useSeries } from '../lib/queries'
import type { Block } from '../lib/types'

type Plate = Extract<Block, { type: 'image' }>
type Page = { lessonId: string; position: number; section: string; block: Plate }

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
      .map((block) => ({ lessonId: l.id, position: l.position, section: l.title, block }))), [s])
  const current = pages.find((p) => p.block.id === params.get('p') && p.lessonId === params.get('s')) ?? pages[0]
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
          <PageView key={`${current.lessonId}:${current.block.id}`} seriesId={id} page={current}
            paper={s.genre === 'story_book' || s.genre === 'picture_book' ? '17x21' : 'A4'} story={s.genre === 'story_book'} />
        </div>
      )}
    </AppShell>
  )
}

function PageView({ seriesId, page, paper, story }: { seriesId: string; page: Page; paper: string; story: boolean }) {
  const qc = useQueryClient()
  const b = page.block
  const [narration, setNarration] = useState(b.narration ?? '')
  const [question, setQuestion] = useState(b.question ?? '')
  const [answer, setAnswer] = useState(b.answer ?? '')
  const [notes, setNotes] = useState<string[]>(() => [...(b.notes ?? []), '', '', '', ''].slice(0, 4))
  const [find, setFind] = useState(b.find ?? '')
  const [layout, setLayout] = useState(b.layout ?? 'bleed')
  const [ask, setAsk] = useState('')
  const base = `/api/lessons/${page.lessonId}/pages/${b.id}`
  // The picture of the page as printed; it follows the saved page (its asset and words), not the form.
  const stamp = `${b.asset_id ?? 'none'}:${b.layout ?? ''}:${b.narration ?? ''}:${b.question ?? ''}:${b.answer ?? ''}:${(b.notes ?? []).join('|')}:${b.find ?? ''}`
  const preview = useQuery({
    queryKey: ['page-preview', page.lessonId, b.id, stamp, paper],
    queryFn: () => api.get<{ image: string }>(`${base}/preview?paper=${paper}`),
    staleTime: Infinity,
  })
  const refresh = () => qc.invalidateQueries({ queryKey: ['series', seriesId] })
  const save = useMutation({
    mutationFn: () => api.patch(base, {
      ...(b.narration != null || story ? { narration } : {}),
      ...(b.question != null ? { question } : {}),
      ...(b.answer != null ? { answer } : {}),
      ...(b.notes?.length ? { notes: notes.filter((n) => n.trim()) } : {}),
      ...(b.find != null ? { find } : {}),
      layout,
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
  const dirty = narration !== (b.narration ?? '') || question !== (b.question ?? '') || answer !== (b.answer ?? '') ||
    find !== (b.find ?? '') || layout !== (b.layout ?? 'bleed') ||
    notes.filter((n) => n.trim()).join('|') !== (b.notes ?? []).join('|')
  const layouts = LAYOUTS.filter((l) => !story || l.key !== 'vignette')

  return (
    <>
      <figure className="page-preview">
        {preview.data ? <img src={preview.data.image} alt={`Página: ${b.narration ?? b.question ?? b.subject}`} />
          : <div className="page-preview-wait">{preview.isError ? 'No se pudo mostrar la página.' : 'Preparando la página…'}</div>}
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
        {b.answer != null && (
          <label className="field"><span>Respuesta</span>
            <textarea value={answer} onChange={(e) => setAnswer(e.target.value)} rows={3} maxLength={500} /></label>
        )}
        {b.notes?.length ? (
          <fieldset className="field"><legend>Datos</legend>
            {notes.map((n, i) => (
              <input key={i} value={n} onChange={(e) => setNotes(notes.map((x, j) => (j === i ? e.target.value : x)))}
                maxLength={140} aria-label={`Dato ${i + 1}`} />
            ))}
          </fieldset>
        ) : null}
        {b.find != null && (
          <label className="field"><span>Observa y encuentra</span>
            <input value={find} onChange={(e) => setFind(e.target.value)} maxLength={300} /></label>
        )}
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
