import { useState } from 'react'

/** Example covers painted once by the worker (backend/app/showcase.py): what a tome can look like, drifting left
 *  to right. Until the worker has painted enough of them the row stays out of sight. */
const BASE = `${import.meta.env.VITE_SUPABASE_URL}/storage/v1/object/public/covers/showcase`
const ENOUGH = 4
const COVERS: [string, string][] = [
  ['colorear-dinosaurios', 'Dinosaurios para colorear'],
  ['escritura-letras', 'Mis primeras letras'],
  ['matematicas-sumas', 'Sumo y cuento hasta 20'],
  ['ciencias-espacio', 'Viaje al sistema solar'],
  ['colorear-oceano', 'Animales del océano'],
  ['lectura-cuentos', 'Leo y comprendo'],
  ['musica-ritmo', 'Mi primer piano'],
  ['granja-vocales', 'Las vocales de la granja'],
]

export function Showcase() {
  const [loaded, setLoaded] = useState(0)
  return (
    <section className={`showcase${loaded >= ENOUGH * 2 ? ' ready' : ''}`} aria-label="Portadas de ejemplo">
      <div className="showcase-track">
        {[0, 1].map((copy) => COVERS.map(([slug, title]) => (
          <img key={`${copy}-${slug}`} src={`${BASE}/${slug}.webp`} alt={copy ? '' : `Portada de ejemplo: ${title}`}
               aria-hidden={copy ? true : undefined} width={240} height={340} decoding="async"
               onLoad={() => setLoaded((n) => n + 1)} onError={(e) => { e.currentTarget.hidden = true }} />
        )))}
      </div>
    </section>
  )
}
