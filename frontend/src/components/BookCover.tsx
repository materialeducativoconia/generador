import { useEffect, useState } from 'react'
import { GENRE_LABEL } from '../lib/labels'
import { themeVars, useThemeFonts } from '../lib/themes'
import type { CoverFields, Design, Genre } from '../lib/types'

type Props = CoverFields & {
  title: string
  genre: Genre | null
  audience?: string
  size?: 'card' | 'hero' | 'full'
  design?: Design | null  // the tome's own cover layout and heading font, as in the PDF
  marked?: boolean        // a free preview: watermarked
}

/** The tome as a printed book: the agent's illustration with our type set on top, like the PDF cover. */
export function BookCover({ title, genre, audience, cover_url, cover_status, cover_palette, cover_lettered, size = 'card', design, marked = false }: Props) {
  const [loaded, setLoaded] = useState(false)
  useThemeFonts(design)
  const [bg, ink, accent] = cover_palette ?? ['#EEF2FF', '#1C1917', '#4F46E5']
  const painting = cover_status === 'queued' || cover_status === 'running'
  const layout = genre === 'picture_book' || genre === 'story_book' ? 'poster' : design?.cover_layout ?? 'plate'  // as the PDF sets it
  const head = design ? (themeVars(design).style as Record<string, string>)['--t-head'] : undefined
  return (
    <div
      className={`book ${size} l-${layout}`}
      style={{ '--book-bg': bg, '--book-ink': ink, '--book-accent': accent, '--book-head': head } as React.CSSProperties}
    >
      {cover_url ? (
        <img src={cover_url} alt="" className={loaded ? 'book-art loaded' : 'book-art'} onLoad={() => setLoaded(true)} draggable={false} />
      ) : (
        <div className={painting ? 'book-art placeholder painting' : 'book-art placeholder'} aria-hidden="true" />
      )}
      {cover_lettered && cover_url ? <span className="sr-only">{title}</span> : <div className="book-plate">
        <span className="book-k">{genre ? GENRE_LABEL[genre] : 'Nuevo tomo'}</span>
        <span className="book-t">{layout === 'poster' ? title.split(':')[0] : title}</span>
        {layout === 'poster' && title.includes(':') && size !== 'card' && <span className="book-sub">{title.split(':').slice(1).join(':').trim()}</span>}
        {audience && size !== 'card' && layout !== 'poster' && <span className="book-a">{audience}</span>}
      </div>}
      {layout === 'poster' && audience && size !== 'card' && <span className="book-age">{audience.match(/\(([^)]+)\)/)?.[1] ?? audience}</span>}
      {marked && <span className="watermark" aria-hidden="true" />}
      {painting && <span className="book-badge">Pintando portada…</span>}
    </div>
  )
}

/** The cover at full size over the page; Esc or a click closes it. */
export function CoverViewer({ onClose, ...props }: Props & { onClose: () => void }) {
  useEffect(() => {
    const key = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [onClose])
  return (
    <div className="cover-viewer" role="dialog" aria-modal="true" aria-label="Portada" onClick={onClose} onContextMenu={(e) => e.preventDefault()}>
      <BookCover {...props} size="full" />
      <button className="cover-viewer-x" onClick={onClose} aria-label="Cerrar">×</button>
    </div>
  )
}
