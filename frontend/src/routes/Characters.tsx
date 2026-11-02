import { useState } from 'react'
import { AppShell } from '../components/AppShell'
import { errorText } from '../components/ErrorNote'
import { useCharacters } from '../lib/queries'
import type { Character } from '../lib/types'

/** The character library: guides every picture book can borrow. It grows with every tome a plan pays for. */
export function Characters() {
  const { data, isPending, error } = useCharacters()
  const [open, setOpen] = useState<Character | null>(null)
  const list = data?.characters ?? []
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
      {isPending && <div className="skeleton tall" />}
      {error && <p className="error">{errorText(error, 'No pudimos cargar los personajes.')}</p>}
      {!isPending && !list.length && <p className="muted">La biblioteca se está preparando: los primeros personajes aparecen en unos minutos.</p>}
      <ul className="characters">
        {list.map((c, i) => (
          <li key={c.id} style={{ '--i': i } as React.CSSProperties}>
            <button className="character" onClick={() => setOpen(c)}>
              {c.sheet_url && <img src={c.sheet_url} alt="" loading="lazy" decoding="async" />}
              <span className="character-b">
                <strong>{c.name}</strong>
                <span className="muted small">{c.archetype}</span>
                <span className="swatches">{c.palette.map((p) => <i key={p} style={{ background: p }} />)}</span>
                <span className="muted small">{c.use_count ? `En ${c.use_count} ${c.use_count === 1 ? 'tomo' : 'tomos'}` : 'Nuevo'}{c.mine ? ' · tuyo' : ''}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
      {open && (
        <div className="cover-viewer" role="dialog" aria-modal="true" aria-label={open.name} onClick={() => setOpen(null)}>
          <figure className="character-sheet">
            {open.sheet_url && <img src={open.sheet_url} alt={`Hoja de modelo de ${open.name}`} />}
            <figcaption><strong>{open.name}</strong> · {open.archetype}<br /><span>{open.personality}</span></figcaption>
          </figure>
          <button className="cover-viewer-x" onClick={() => setOpen(null)} aria-label="Cerrar">×</button>
        </div>
      )}
    </AppShell>
  )
}
