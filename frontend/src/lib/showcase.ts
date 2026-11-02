// The example covers the worker painted once (backend/app/showcase.py), stored at covers/showcase/<slug>.webp.
// Plain data: the landing's carousel and the static topic pages (scripts/seo.ts) both read it.

export const SHOWCASE: [string, string][] = [
  ['colorear-dinosaurios', 'Dinosaurios para colorear'],
  ['escritura-letras', 'Mis primeras letras'],
  ['matematicas-sumas', 'Sumo y cuento hasta 20'],
  ['ciencias-espacio', 'Viaje al sistema solar'],
  ['colorear-oceano', 'Animales del océano'],
  ['lectura-cuentos', 'Leo y comprendo'],
  ['musica-ritmo', 'Mi primer piano'],
  ['granja-vocales', 'Las vocales de la granja'],
]

/** The covers with the given one first, so a topic page opens on its own kind of book. */
export function showcaseFrom(first?: string): [string, string][] {
  const i = Math.max(0, SHOWCASE.findIndex(([slug]) => slug === first))
  return [...SHOWCASE.slice(i), ...SHOWCASE.slice(0, i)]
}
