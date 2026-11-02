// The illustration styles a tome can be painted in (backend/app/house_styles.py); samples in public/estilos.
export type HouseStyle = { key: string; name: string; desc: string; free: boolean }

export const HOUSE_STYLES: HouseStyle[] = [
  { key: 'enciclopedia', name: 'Enciclopedia', desc: 'Acuarela naturalista sobre página blanca, como una enciclopedia infantil.', free: false },
  { key: 'didactico', name: 'Didáctico claro', desc: 'Contornos limpios y colores planos, como en los libros de texto.', free: true },
  { key: 'gouache', name: 'Gouache moderno', desc: 'Formas gráficas y pocas tintas, con textura de impresión.', free: false },
  { key: 'acuarela', name: 'Acuarela y tinta', desc: 'Trazo suelto y aguadas suaves sobre papel.', free: true },
  { key: 'collage', name: 'Collage de papel', desc: 'Papeles pintados y recortados a mano, con sus bordes y texturas.', free: false },
  { key: 'crayon', name: 'Lápiz y crayón', desc: 'Lápices de color sobre papel con grano, cálido y cercano.', free: false },
]

export const sampleOf = (key: string) => `/estilos/${key}.webp`
