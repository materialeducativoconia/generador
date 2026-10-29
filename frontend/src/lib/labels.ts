import type { Design } from './types'

export const GENRE_LABEL: Record<string, string> = {
  coloring_book: 'Libro para colorear',
  worksheets: 'Cuadernillo de fichas',
  tutorial: 'Método paso a paso',
  lesson_series: 'Secuencia didáctica',
}

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
