import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { AppShell, StatusPill } from '../components/AppShell'
import { BookCover } from '../components/BookCover'
import { ApiError } from '../lib/api'
import { api } from '../lib/apiClient'
import { useEstimate, useMe, useSeriesList, useStyles } from '../lib/queries'

const AUDIENCES = ['Preescolar (3–5 años)', 'Primaria baja (6–8)', 'Primaria alta (9–12)', 'Secundaria', 'Adultos principiantes']

const EXAMPLES = [
  { label: 'Libro de colorear', request: 'Libro para colorear de animales de la granja, con el nombre de cada animal', audience: AUDIENCES[0] },
  { label: 'Lectoescritura', request: 'Cuadernillo de lectoescritura de la vocal A: repasar, colorear, sílabas y dictado', audience: AUDIENCES[0] },
  { label: 'Piano', request: 'Método de piano para principiantes: postura, Do central, primeras melodías con la mano derecha', audience: AUDIENCES[4] },
  { label: 'Ciencias', request: 'Secuencia de lecciones sobre el ciclo del agua con un experimento casero por lección', audience: AUDIENCES[3] },
]

type Created = { series: { id: string } }

const PAGES = [3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 32, 40, 48, 64, 80, 100]

export function Studio() {
  const { data: me } = useMe()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [request, setRequest] = useState('')
  const [audience, setAudience] = useState(AUDIENCES[0])
  const [sections, setSections] = useState<number | null>(null)  // null: the Architect decides
  const [pages, setPages] = useState<number | null>(null)
  const [quoting, setQuoting] = useState(false)  // the cost window, shown before anything is created
  const [style, setStyle] = useState('auto')
  const ready = (useStyles().data?.styles ?? []).filter((s) => s.status === 'ready')
  const idempotencyKey = useRef(crypto.randomUUID())
  const textarea = useRef<HTMLTextAreaElement>(null)

  const create = useMutation({
    mutationFn: () =>
      api.post<Created>(
        '/api/series',
        { request: request.trim(), audience, language: 'es',
          section_count: sections,
          page_count: pages,
          style_id: style === 'auto' ? null : style },
        { 'Idempotency-Key': idempotencyKey.current },
      ),
    onSuccess: (data) => {
      setQuoting(false)
      idempotencyKey.current = crypto.randomUUID()
      void qc.invalidateQueries({ queryKey: ['series'] })
      navigate(`/app/tomos/${data.series.id}`)
    },
  })

  function submit(e?: FormEvent) {
    e?.preventDefault()
    if (request.trim().length >= 3 && !create.isPending) setQuoting(true)
  }

  const firstName = me?.display_name?.split(' ')[0]

  return (
    <AppShell>
      <section className="hero">
        <div className="orb" aria-hidden="true" />
        <p className="eyebrow">Estudio de material educativo</p>
        <h1 className="display">{firstName ? `¿Qué creamos hoy, ${firstName}?` : '¿Qué material creamos hoy?'}</h1>
        <p className="lede">Describe el tomo que necesitas. Un arquitecto lo planifica, tú apruebas el esquema y lo escribimos y maquetamos listo para imprimir.</p>

        <form className="composer" onSubmit={submit}>
          <textarea
            ref={textarea}
            value={request}
            onChange={(e) => setRequest(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit()
            }}
            placeholder="Ej.: Método de piano para principiantes con ejercicios para la mano derecha…"
            rows={3}
            maxLength={2000}
            aria-label="Describe el material"
          />
          <div className="composer-bar">
            <label className="select-pill">
              <span className="sr-only">Público</span>
              <select value={audience} onChange={(e) => setAudience(e.target.value)}>
                {AUDIENCES.map((a) => <option key={a}>{a}</option>)}
              </select>
            </label>
            <label className="select-pill">
              <span className="sr-only">Secciones</span>
              <select value={sections ?? ''} onChange={(e) => setSections(e.target.value ? Number(e.target.value) : null)}>
                <option value="">Secciones: auto</option>
                {Array.from({ length: 20 }, (_, i) => <option key={i + 1} value={i + 1}>{i + 1} {i ? 'secciones' : 'sección'}</option>)}
              </select>
            </label>
            <label className="select-pill">
              <span className="sr-only">Páginas</span>
              <select value={pages ?? ''} onChange={(e) => setPages(e.target.value ? Number(e.target.value) : null)}>
                <option value="">Páginas: auto</option>
                {PAGES.map((n) => <option key={n} value={n}>{n} páginas</option>)}
              </select>
            </label>
            {ready.length > 0 && (
              <label className="select-pill">
                <span className="sr-only">Estilo</span>
                <select value={style} onChange={(e) => setStyle(e.target.value)}>
                  <option value="auto">Estilo: automático</option>
                  {ready.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </label>
            )}
            <button className="send" type="submit" disabled={request.trim().length < 3 || create.isPending} aria-label="Crear tomo">
              {create.isPending ? <span className="spinner" /> : <ArrowUp />}
            </button>
          </div>
        </form>
        {quoting && (
          <CostDialog sections={sections} pages={pages} pending={create.isPending}
                      onConfirm={() => create.mutate()} onCancel={() => setQuoting(false)} />
        )}
        {create.error && <p className="error" role="alert">{create.error instanceof ApiError ? create.error.message : 'No pudimos crear el tomo.'}</p>}

        <div className="examples">
          {EXAMPLES.map((ex) => (
            <button
              key={ex.label}
              className="chip"
              type="button"
              onClick={() => {
                setRequest(ex.request)
                setAudience(ex.audience)
                textarea.current?.focus()
              }}
            >
              {ex.label}
            </button>
          ))}
        </div>
      </section>

      <Library />
    </AppShell>
  )
}

function Library() {
  const { data, isPending } = useSeriesList()
  if (isPending) return <div className="library"><div className="skeleton" /><div className="skeleton" /></div>
  if (!data?.length) return null
  return (
    <section className="library">
      <h2 className="section-h">Tus tomos</h2>
      <ul className="cards books">
        {data.map((s, i) => (
          <li key={s.id} style={{ '--i': i } as React.CSSProperties}>
            <Link to={`/app/tomos/${s.id}`} className="book-card" aria-label={`Abrir ${s.title ?? s.topic}`}>
              <BookCover title={s.title ?? s.topic} genre={s.genre} cover_url={s.cover_url} cover_status={s.cover_status} cover_palette={s.cover_palette ?? s.design?.palette ?? null} />
              <span className="card-f">
                <StatusPill status={s.status} />
                {s.lesson_count > 0 && ['generating', 'ready', 'needs_attention'].includes(s.status) && (
                  <span className="muted small">{s.done}/{s.lesson_count}</span>
                )}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

function ArrowUp() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 19V5M5 12l7-7 7 7" />
    </svg>
  )
}

const usd = (n: number) => `$${n.toFixed(2)}`

/** What the chosen tome will cost in AI calls, confirmed before anything is created. USD while testing;
 * this is where credits will be charged later. */
function CostDialog({ sections, pages, pending, onConfirm, onCancel }: {
  sections: number | null; pages: number | null; pending: boolean; onConfirm: () => void; onCancel: () => void
}) {
  const q = useEstimate(sections, pages).data
  const confirm = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    confirm.current?.focus()
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && onCancel()
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onCancel])
  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="cost-title" onClick={(e) => e.stopPropagation()}>
        <h2 id="cost-title">Costo estimado</h2>
        {!q ? <div className="skeleton" /> : (
          <>
            <p className="muted small">
              {q.sections} {q.sections === 1 ? 'sección' : 'secciones'}{q.assumed.sections ? ' (estimadas)' : ''} · {q.pages} páginas{q.assumed.pages ? ' (estimadas)' : ''}
            </p>
            <dl className="cost-rows">
              <div><dt>Texto (redacción y revisión)</dt><dd>{usd(q.text_usd)}</dd></div>
              <div><dt>Búsqueda de programas oficiales</dt><dd>{usd(q.search_usd)}</dd></div>
              <div><dt>Portada</dt><dd>{usd(q.cover_usd)}</dd></div>
              <div><dt>Ilustraciones</dt><dd>{usd(q.art_usd[0])} – {usd(q.art_usd[1])}</dd></div>
              <div className="total"><dt>Total</dt><dd>{usd(q.total_usd[0])} – {usd(q.total_usd[1])} {q.currency}</dd></div>
            </dl>
            <p className="small muted">
              Las ilustraciones dependen de lo que planifique el arquitecto; los dibujos que ya están en tu biblioteca no se vuelven a pagar.
              {q.history_usd != null && ` Con lo que costaron tus tomos anteriores, este saldría por unos ${usd(q.history_usd)}.`}
            </p>
          </>
        )}
        <div className="modal-actions">
          <button className="ghost" onClick={onCancel} disabled={pending}>Cancelar</button>
          <button ref={confirm} className="primary" onClick={onConfirm} disabled={!q || pending}>{pending ? 'Creando…' : 'Crear el esquema'}</button>
        </div>
      </div>
    </div>
  )
}
