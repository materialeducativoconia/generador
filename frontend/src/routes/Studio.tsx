import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { AppShell, StatusPill } from '../components/AppShell'
import { BookCover } from '../components/BookCover'
import { ApiError } from '../lib/api'
import { api } from '../lib/apiClient'
import { useCollections, useEstimate, useIdentities, useMe, useSeriesList, useStyles } from '../lib/queries'
import type { Collection, Identity, SeriesSummary } from '../lib/types'

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
  const [params] = useSearchParams()  // "Crear este nivel" arrives with the request and audience filled in
  const [request, setRequest] = useState(params.get('pedido') ?? '')
  const [audience, setAudience] = useState(params.get('publico') ?? AUDIENCES[0])
  const audiences = AUDIENCES.includes(audience) ? AUDIENCES : [audience, ...AUDIENCES]
  const collectionId = params.get('coleccion')
  const collection = useCollections().data?.find((c) => c.id === collectionId)
  const [sections, setSections] = useState<number | null>(null)  // null: the Architect decides
  const [pages, setPages] = useState<number | null>(null)
  const [quoting, setQuoting] = useState(false)  // the cost window, shown before anything is created
  const [style, setStyle] = useState('auto')
  const ready = (useStyles().data?.styles ?? []).filter((s) => s.status === 'ready')
  const identities = usableIdentities(useIdentities().data?.identities)
  const [identity, setIdentity] = useState('')
  const lineOf = identities.find((i) => i.id === collection?.identity_id)  // a collection's line wins
  const idempotencyKey = useRef(crypto.randomUUID())
  const textarea = useRef<HTMLTextAreaElement>(null)

  const create = useMutation({
    mutationFn: () =>
      api.post<Created>(
        '/api/series',
        { request: request.trim(), audience, language: 'es',
          section_count: sections,
          page_count: pages,
          style_id: style === 'auto' ? null : style,
          identity_id: identity || null,
          collection_id: collection?.id ?? null,
          place: params.get('lugar') === 'start' ? 'start' : 'end' },
        { 'Idempotency-Key': idempotencyKey.current },
      ),
    onSuccess: (data) => {
      setQuoting(false)
      idempotencyKey.current = crypto.randomUUID()
      void qc.invalidateQueries({ queryKey: ['series'] })
      void qc.invalidateQueries({ queryKey: ['collections'] })
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

        {collection && <p className="collection-chip">Nuevo nivel de la colección <strong>{collection.name}</strong>{lineOf && <> con la identidad <strong>{lineOf.design!.brand!.name}</strong></>}</p>}
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
                {audiences.map((a) => <option key={a}>{a}</option>)}
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
            {identities.length > 0 && !lineOf && (
              <label className="select-pill">
                <span className="sr-only">Identidad</span>
                <select value={identity} onChange={(e) => setIdentity(e.target.value)}>
                  <option value="">Identidad: ninguna</option>
                  {identities.map((i) => <option key={i.id} value={i.id}>{i.design!.brand!.name}</option>)}
                </select>
              </label>
            )}
            {ready.length > 0 && !identity && !lineOf && (
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
  const collections = useCollections().data ?? []
  const qc = useQueryClient()
  const createCollection = useMutation({
    mutationFn: (name: string) => api.post('/api/collections', { name }),
    onSettled: () => qc.invalidateQueries({ queryKey: ['collections'] }),
  })
  if (isPending) return <div className="library"><div className="skeleton" /><div className="skeleton" /></div>
  if (!data?.length && !collections.length) return null
  const byId = new Map((data ?? []).map((s) => [s.id, s]))
  const loose = (data ?? []).filter((s) => !s.collection_id)
  const newCollection = () => {
    const name = window.prompt('Nombre de la colección (por ejemplo: «Multiplicación» o «Lectoescritura»)')
    if (name?.trim()) createCollection.mutate(name.trim())
  }
  return (
    <section className="library">
      <div className="library-head">
        <h2 className="section-h">Tu biblioteca</h2>
        <button className="ghost small" onClick={newCollection}>Nueva colección</button>
      </div>
      {collections.map((c) => (
        <Shelf key={c.id} collection={c} collections={collections}
          tomes={c.series_ids.map((id) => byId.get(id)).filter((s): s is SeriesSummary => !!s)} />
      ))}
      {loose.length > 0 && (
        <>
          {collections.length > 0 && <h3 className="shelf-title">Tomos sueltos</h3>}
          <ul className="cards books">
            {loose.map((s, i) => <BookItem key={s.id} tome={s} index={i} collections={collections} />)}
          </ul>
        </>
      )}
    </section>
  )
}

/** A collection: its tomes side by side in level order, like a series on a bookshop shelf. */
function Shelf({ collection: c, tomes, collections }: { collection: Collection; tomes: SeriesSummary[]; collections: Collection[] }) {
  const qc = useQueryClient()
  const refresh = () => Promise.all([qc.invalidateQueries({ queryKey: ['collections'] }), qc.invalidateQueries({ queryKey: ['series'] })])
  const rename = useMutation({ mutationFn: (name: string) => api.patch(`/api/collections/${c.id}`, { name }), onSettled: refresh })
  const remove = useMutation({ mutationFn: () => api.delete(`/api/collections/${c.id}`), onSettled: refresh })
  const identities = usableIdentities(useIdentities().data?.identities)
  const navigate = useNavigate()
  const line = useMutation({
    mutationFn: (identity_id: string | null) => api.put(`/api/collections/${c.id}/identity`, { identity_id }),
    onSettled: () => Promise.all([refresh(), qc.invalidateQueries({ queryKey: ['identities'] })]),
  })
  return (
    <div className="shelf">
      <div className="shelf-head">
        <h3 className="shelf-title">{c.name} <span className="muted small">· {tomes.length} {tomes.length === 1 ? 'nivel' : 'niveles'}</span></h3>
        <label className="select-pill small" title="Todos los niveles de la colección usan esta identidad">
          <span className="sr-only">Identidad de la colección</span>
          <select value={c.identity_id ?? ''} disabled={line.isPending}
            onChange={(e) => e.target.value === 'new' ? navigate('/app/identidades') : line.mutate(e.target.value || null)}>
            <option value="">Identidad: ninguna</option>
            {identities.map((i) => <option key={i.id} value={i.id}>{i.design!.brand!.name}</option>)}
            <option value="new">+ Crear identidad…</option>
          </select>
        </label>
        <button className="ghost small" onClick={() => { const n = window.prompt('Nuevo nombre', c.name); if (n?.trim()) rename.mutate(n.trim()) }}>Renombrar</button>
        <button className="ghost small" onClick={() => { if (window.confirm(`¿Eliminar la colección «${c.name}»? Sus tomos no se borran: quedan sueltos en tu biblioteca.`)) remove.mutate() }}>Eliminar colección</button>
      </div>
      {tomes.length ? (
        <ul className="cards books">
          {tomes.map((s, i) => <BookItem key={s.id} tome={s} index={i} level={i + 1} collections={collections} />)}
        </ul>
      ) : <p className="muted small">Vacía. Mueve aquí un tomo desde su menú ⋯ o crea un nivel desde «Niveles sugeridos».</p>}
    </div>
  )
}

function BookItem({ tome: s, index, level, collections }: { tome: SeriesSummary; index: number; level?: number; collections: Collection[] }) {
  const qc = useQueryClient()
  const [menu, setMenu] = useState(false)
  const refresh = () => Promise.all([qc.invalidateQueries({ queryKey: ['collections'] }), qc.invalidateQueries({ queryKey: ['series'] })])
  const move = useMutation({
    mutationFn: async (target: string) => {
      const id = target === 'new'
        ? (await api.post<{ collection: Collection }>('/api/collections', { name: window.prompt('Nombre de la colección', s.title ?? s.topic) || (s.title ?? s.topic) })).collection.id
        : target || null
      return api.put(`/api/series/${s.id}/collection`, { collection_id: id })
    },
    onSettled: () => { setMenu(false); return refresh() },
  })
  const remove = useMutation({ mutationFn: () => api.delete(`/api/series/${s.id}`), onSettled: refresh })
  const title = s.title ?? s.topic
  return (
    <li style={{ '--i': index } as React.CSSProperties} className="book-item">
      <Link to={`/app/tomos/${s.id}`} className="book-card" aria-label={`Abrir ${title}`}>
        <BookCover title={title} genre={s.genre} cover_url={s.cover_url} cover_status={s.cover_status} cover_palette={s.cover_palette ?? s.design?.palette ?? null} />
        <span className="card-f">
          {level && <span className="level-tag">Nivel {level}</span>}
          <StatusPill status={s.status} />
          {s.lesson_count > 0 && ['generating', 'ready', 'needs_attention'].includes(s.status) && (
            <span className="muted small">{s.done}/{s.lesson_count}</span>
          )}
        </span>
      </Link>
      <button className="book-menu-btn" aria-label={`Opciones de ${title}`} aria-expanded={menu} onClick={() => setMenu(!menu)}>⋯</button>
      {menu && (
        <div className="book-menu" role="menu">
          <label className="small">
            Colección
            <select value={s.collection_id ?? ''} onChange={(e) => move.mutate(e.target.value)} disabled={move.isPending}>
              <option value="">Sin colección</option>
              {collections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              <option value="new">+ Nueva colección…</option>
            </select>
          </label>
          <button className="danger small" disabled={remove.isPending}
            onClick={() => { if (window.confirm(`¿Eliminar «${title}»? Se borran sus secciones y sus PDF. No se puede deshacer.`)) remove.mutate() }}>
            Eliminar tomo
          </button>
        </div>
      )}
    </li>
  )
}

/** Identities the user has picked a line for (proposals still waiting for a choice can't be applied). */
const usableIdentities = (all: Identity[] | undefined) => (all ?? []).filter((i) => i.design?.brand)

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
