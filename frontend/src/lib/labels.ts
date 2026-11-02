import type { Design } from './types'

export const AUDIENCES = ['Preescolar (3–5 años)', 'Primaria baja (6–8)', 'Primaria alta (9–12)', 'Secundaria', 'Adultos principiantes']

export const GENRE_LABEL: Record<string, string> = {
  picture_book: 'Libro ilustrado',
  story_book: 'Cuento ilustrado',
  coloring_book: 'Libro para colorear',
  worksheets: 'Cuadernillo de fichas',
  tutorial: 'Método paso a paso',
  lesson_series: 'Secuencia didáctica',
}

/** The composer's format choice; "auto" lets the Architect decide from the request (a picture book by default). */
export const FORMATS: { value: string; label: string }[] = [
  { value: 'auto', label: 'Formato automático' },
  { value: 'picture_book', label: 'Libro ilustrado' },
  { value: 'story_book', label: 'Cuento ilustrado' },
  { value: 'coloring_book', label: 'Libro para colorear' },
  { value: 'worksheets', label: 'Cuadernillo de fichas' },
  { value: 'tutorial', label: 'Método paso a paso' },
  { value: 'lesson_series', label: 'Secuencia didáctica' },
]

export const THEME_LABEL: Record<Design['theme'], string> = {
  juego: 'Juego', cuaderno: 'Cuaderno', editorial: 'Editorial', metodo: 'Método', ciencia: 'Ciencia', clasico: 'Clásico',
}
export const FRAME_LABEL: Record<NonNullable<Design['frame']>, string> = {
  none: 'sin marco', line: 'marco fino', rounded: 'marco redondeado', dashed: 'marco punteado', double: 'marco doble',
}

export const ART_LABEL: Record<NonNullable<Design['illustration']>, string> = {
  acuarela: 'acuarela', crayon: 'crayón y lápiz de color', recorte: 'papel recortado', gouache: 'gouache',
  vector: 'vectorial plano', riso: 'impresión risográfica', tinta: 'tinta y aguada', plastilina: 'plastilina 3D',
  grabado: 'grabado clásico', infografia: 'infografía limpia',
}
export const COVER_LABEL: Record<NonNullable<Design['cover_layout']>, string> = {
  plate: 'portada con tarjeta', band: 'portada con franja', framed: 'portada enmarcada',
}

/** A tome's name for headings: its title once the Architect gave it one, else the request cut to its first
 *  phrase (a pasted brief can run for paragraphs). */
export function tomeName(s: { title: string | null; topic: string }, max = 60): string {
  if (s.title) return s.title
  const first = s.topic.trim().split(/(?<=[.:;!?])\s|\n/)[0] ?? s.topic
  return first.length > max ? `${first.slice(0, max).replace(/\s+\S*$/, '')}…` : first
}
