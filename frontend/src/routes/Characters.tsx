import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { AppShell } from '../components/AppShell'
import { errorText } from '../components/ErrorNote'
import { StylePicker } from '../components/StylePicker'
import { api } from '../lib/apiClient'
import { HOUSE_STYLES } from '../lib/houseStyles'
import { useCharacters, useMe } from '../lib/queries'
import type { Character } from '../lib/types'

/** The character maker (plans that sell): a description, an optional base character and a house style. */
function CharacterMaker({ base, onBase }: { base: Character | null; onBase: (c: Character | null) => void }) {
  const qc = useQueryClient()
  const [description, setDescription] = useState('')
  const [style, setStyle] = useState<string | null>(null)
  const make = useMutation({
    mutationFn: () => api.post('/api/characters', { description: description.trim(), based_on: base?.id ?? null, style }),
    onSuccess: () => {
      setDescription('')
      onBase(null)
      void qc.invalidateQueries({ queryKey: ['characters'] })
      void qc.invalidateQueries({ queryKey: ['me'] })
    },
  })
  function submit(e: FormEvent) {
    e.preventDefault()
    if (description.trim().length >= 5 && !make.isPending) make.mutate()
  }
  return (
    <form className="composer character-maker" onSubmit={submit} id="crear-personaje">
      {base && <p className="collection-chip">Basado en <strong>{base.name}</strong> (misma cara y cuerpo) <button type="button" className="ghost small" onClick={() => onBase(null)}>Quitar</button></p>}
      <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} maxLength={600}
                placeholder={base ? `Qué cambia: «${base.name} con traje de astronauta»…` : 'Ej.: Una tortuga marina curiosa con una careta de buceo roja, guía de un libro del océano…'}
                aria-label="Describe tu personaje" />
      <StylePicker value={style} onChange={setStyle} paid />
      <div className="composer-bar">
        <span className="muted small">Se diseña y se pinta su hoja de modelo en un par de minutos · 3 créditos · solo para tus tomos</span>
        <button className="primary" disabled={description.trim().length < 5 || make.isPending}>{make.isPending ? 'Enviando…' : 'Crear personaje'}</button>
      </div>
      {make.error && <p className="error small">{errorText(make.error, 'No se pudo crear el personaje.')}</p>}
    </form>
  )
}

/** The character library: guides every picture book can borrow. It grows with every tome a plan pays for. */
export function Characters() {
  const { data, isPending, error } = useCharacters()
  const { data: me } = useMe()
  const qc = useQueryClient()
  const [open, setOpen] = useState<Character | null>(null)
  const [base, setBase] = useState<Character | null>(null)
  const list = data?.characters ?? []
  const maker = !!me?.plan.commercial
  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`/api/characters/${id}`),
    onSuccess: () => { setOpen(null); void qc.invalidateQueries({ queryKey: ['characters'] }) },
  })
  function derive(c: Character) {
    setOpen(null)
    setBase(c)
    document.getElementById('crear-personaje')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
  return (
    <AppShell>
      <header className="characters-h">
        <p className="eyebrow">Biblioteca</p>
        <h1 className="display">Personajes</h1>
        <p className="muted">
          Los guías de tus libros ilustrados. Cada uno tiene su hoja de modelo, así se ve igual en la portada y en
          cada lámina. Al crear un tomo, el agente de casting elige uno que encaje, lo adapta al tema o diseña uno
          nuevo, que se suma a la biblioteca.
        </p>
      </header>
      {maker ? <CharacterMaker base={base} onBase={setBase} /> : (
        <p className="plan-note">¿Quieres la mascota de tu colección? Crea tus propios personajes con el plan Creador. <Link to="/app/plan">Ver planes</Link></p>
      )}
      {isPending && <div className="skeleton tall" />}
      {error && <p className="error">{errorText(error, 'No pudimos cargar los personajes.')}</p>}
      {!isPending && !list.length && <p className="muted">La biblioteca se está preparando: los primeros personajes aparecen en unos minutos.</p>}
      <ul className="characters">
        {list.map((c, i) => (
          <li key={c.id} style={{ '--i': i } as React.CSSProperties}>
            <button className="character" onClick={() => c.status === 'ready' && setOpen(c)} disabled={c.status !== 'ready'}>
              {c.sheet_url ? <img src={c.sheet_url} alt="" loading="lazy" decoding="async" />
                : <span className="character-wait">{c.status === 'painting' ? <><span className="spinner" />Pintando su hoja…</> : <span className="error small">{c.error ?? 'No se pudo pintar'}</span>}</span>}
              <span className="character-b">
                <strong>{c.name}</strong>
                <span className="muted small">{c.archetype}</span>
                <span className="swatches">{c.palette.map((p) => <i key={p} style={{ background: p }} />)}</span>
                <span className="muted small">{c.use_count ? `En ${c.use_count} ${c.use_count === 1 ? 'tomo' : 'tomos'}` : 'Nuevo'}{c.mine ? ' · tuyo' : ''}</span>
                {c.styles.length > 0 && <span className="muted small">{c.styles.map((k) => HOUSE_STYLES.find((h) => h.key === k)?.name ?? k).join(' · ')}</span>}
              </span>
            </button>
          </li>
        ))}
      </ul>
      {open && (
        <div className="cover-viewer" role="dialog" aria-modal="true" aria-label={open.name} onClick={() => setOpen(null)}>
          <figure className="character-sheet">
            {open.sheet_url && <img src={open.sheet_url} alt={`Hoja de modelo de ${open.name}`} />}
            <figcaption><strong>{open.name}</strong> · {open.archetype}<br /><span>{open.personality}</span>
              <span className="character-actions" onClick={(e) => e.stopPropagation()}>
                {maker && <button className="ghost small" onClick={() => derive(open)}>Crear uno basado en {open.name}</button>}
                {open.mine && <button className="ghost small danger" onClick={() => remove.mutate(open.id)} disabled={remove.isPending}>Borrar</button>}
              </span>
            </figcaption>
          </figure>
          <button className="cover-viewer-x" onClick={() => setOpen(null)} aria-label="Cerrar">×</button>
        </div>
      )}
    </AppShell>
  )
}
