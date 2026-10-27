import { useState } from 'react'
import { GENRE_LABEL } from '../lib/labels'
import type { CoverFields, Genre } from '../lib/types'

type Props = CoverFields & {
  title: string
  genre: Genre | null
  audience?: string
  size?: 'card' | 'hero'
}

/** The tome as a printed book: the agent's illustration with our type set on top, like the PDF cover. */
export function BookCover({ title, genre, audience, cover_url, cover_status, cover_palette, size = 'card' }: Props) {
  const [loaded, setLoaded] = useState(false)
  const [bg, ink, accent] = cover_palette ?? ['#EEF2FF', '#1C1917', '#4F46E5']
  const painting = cover_status === 'queued' || cover_status === 'running'
  return (
    <div
      className={`book ${size}`}
      style={{ '--book-bg': bg, '--book-ink': ink, '--book-accent': accent } as React.CSSProperties}
    >
      {cover_url ? (
        <img src={cover_url} alt="" className={loaded ? 'book-art loaded' : 'book-art'} onLoad={() => setLoaded(true)} draggable={false} />
      ) : (
        <div className={painting ? 'book-art placeholder painting' : 'book-art placeholder'} aria-hidden="true" />
      )}
      <div className="book-plate">
        <span className="book-k">{genre ? GENRE_LABEL[genre] : 'Nuevo tomo'}</span>
        <span className="book-t">{title}</span>
        {audience && size === 'hero' && <span className="book-a">{audience}</span>}
      </div>
      {painting && <span className="book-badge">Pintando portada…</span>}
    </div>
  )
}
