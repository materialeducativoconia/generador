import { useState } from 'react'
import { showcaseFrom } from '../lib/showcase'

/** Example covers painted once by the worker (backend/app/showcase.py): what a tome can look like, drifting left
 *  to right. Until the worker has painted enough of them the row stays out of sight. */
export const SHOWCASE_BASE = `${import.meta.env.VITE_SUPABASE_URL}/storage/v1/object/public/covers/showcase`
const ENOUGH = 4

export function Showcase({ first }: { first?: string }) {
  const [loaded, setLoaded] = useState(0)
  const covers = showcaseFrom(first)
  return (
    <section className={`showcase${loaded >= ENOUGH * 2 ? ' ready' : ''}`} aria-label="Portadas de ejemplo">
      <div className="showcase-track">
        {[0, 1].map((copy) => covers.map(([slug, title]) => (
          <img key={`${copy}-${slug}`} src={`${SHOWCASE_BASE}/${slug}.webp`} alt={copy ? '' : `Portada de ejemplo: ${title}`}
               aria-hidden={copy ? true : undefined} width={240} height={340} decoding="async"
               onLoad={() => setLoaded((n) => n + 1)} onError={(e) => { e.currentTarget.hidden = true }} />
        )))}
      </div>
    </section>
  )
}
