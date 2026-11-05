// Comparison pages: one static page each at /comparar/<slug> (written by scripts/seo.ts at build time) and the
// /comparar hub. Plain data only: Node runs this file directly, without a bundler.
// Say about the other app only what its public site shows, with the date it was checked, and say where it wins:
// a fair page is the one teachers trust and search engines keep.

export type Row = [feature: string, jelyx: string, them: string, winner: 'jelyx' | 'them' | 'tie']

export type Comparison = {
  slug: string
  rival: string           // the other app's name as people search it
  site: string            // its public site, the source of every claim in `rows`
  checked: string         // when its site was read, e.g. 'noviembre de 2026'
  title: string           // <title> and <h1>
  description: string     // meta description, ≤ 160 characters
  intro: string
  verdict: string         // the short answer, under the h1
  rows: Row[]
  pickJelyx: string[]     // when Jelyx is the better choice
  pickThem: string[]      // when the other one is
  faq: [string, string][]
  request: string         // the studio's first request, ready to generate
  audience: string
}

export const COMPARISONS: Comparison[] = [
  {
    slug: 'jelyx-vs-kiddoworksheets', rival: 'KiddoWorksheets', site: 'https://www.kiddoworksheets.com/', checked: 'noviembre de 2026',
    title: 'Jelyx Docs vs KiddoWorksheets: la alternativa en español',
    description: 'Comparamos Jelyx Docs y KiddoWorksheets: idioma, niveles, sopas de letras, laberintos, solucionario, marca propia y precio. Cuál conviene a cada docente.',
    intro: 'KiddoWorksheets es un catálogo gratuito de hojas imprimibles en inglés, de preescolar a 5.º grado, con un generador de fichas. Jelyx Docs crea en español un cuadernillo o libro completo sobre el tema que escribas, con portada, ilustraciones, fichas y solucionario. Aquí van las diferencias, punto por punto.',
    verdict: 'Si buscas una hoja suelta en inglés y gratis, KiddoWorksheets cumple. Si necesitas material en español, de tu tema exacto, armado como cuadernillo y con solucionario, Jelyx Docs hace en minutos lo que allá tendrías que juntar hoja por hoja.',
    rows: [
      ['Idioma', 'Pensado en español, con método de lectoescritura en español', 'En inglés', 'jelyx'],
      ['Qué obtienes', 'Un cuadernillo o libro completo: portada, índice, secciones y solucionario', 'Hojas sueltas, una por descarga', 'jelyx'],
      ['Temas', 'Cualquier tema que escribas, al nivel de tu grupo', 'Las categorías y plantillas del catálogo', 'jelyx'],
      ['Niveles', 'De preescolar a secundaria, y también adultos', 'De preescolar a 5.º grado', 'jelyx'],
      ['Ilustraciones', 'Dibujos nuevos para tu tema, con los mismos personajes en todo el libro', 'Dibujos del catálogo', 'jelyx'],
      ['Sopas de letras', 'Con los dibujos del tema como pista; diagonales e invertidas para los mayores', 'Generador de sopas de letras y crucigramas', 'tie'],
      ['Laberintos', 'Generados para tu tema (quién busca y qué busca), del tamaño adecuado a la edad', 'Hojas de laberintos en el catálogo', 'jelyx'],
      ['Solucionario', 'Automático, con la sopa marcada y el camino del laberinto dibujado', 'Su sitio no lo menciona', 'jelyx'],
      ['Tu marca', 'Tu nombre, tu escuela y tu logo; sello y mascota propios desde el plan Creador', 'No', 'jelyx'],
      ['Editar', 'Editas cada texto antes de descargar, sin gastar créditos; Word editable desde el plan Creador', 'Ajustes del generador', 'jelyx'],
      ['Para vender', 'Licencia comercial sin marca de agua desde el plan Creador (Amazon KDP, Teachers Pay Teachers)', 'Su sitio no ofrece una licencia comercial', 'jelyx'],
      ['Versión digital', 'PDF para imprimir', 'Además de imprimir, hojas para resolver en línea y botón para Google Classroom', 'them'],
      ['Precio', 'Vista previa gratis sin registro; planes desde 9 USD al mes', 'Gratis', 'them'],
    ],
    pickJelyx: [
      'Das clase en español y no quieres traducir ni adaptar hojas en inglés.',
      'Necesitas un cuadernillo entero de un tema (una unidad, un mes, una letra) y no veinte hojas sueltas.',
      'Tu grupo está en secundaria o tu tema no aparece en ningún catálogo.',
      'Quieres el solucionario hecho y el material con tu nombre o tu logo.',
      'Vendes tu material y necesitas licencia comercial.',
    ],
    pickThem: [
      'Solo necesitas una hoja rápida en inglés para hoy.',
      'Quieres que los niños resuelvan la hoja en línea.',
      'No puedes pagar nada: su catálogo es gratuito.',
    ],
    faq: [
      ['¿Jelyx Docs es gratis como KiddoWorksheets?', 'Puedes ver tu tomo real gratis y sin registrarte: portada, índice y una muestra de páginas. Para generarlo completo y descargarlo eliges un plan desde 9 USD al mes.'],
      ['¿Jelyx hace sopas de letras y laberintos?', 'Sí. Los arma el código, con los dibujos de tu tema, del tamaño adecuado a la edad, y el solucionario trae la sopa marcada y el camino del laberinto dibujado.'],
      ['¿Puedo usar Jelyx para material en español de preescolar?', 'Sí. Hay fichas de lectoescritura en español (sílabas, trazos, dictados, completar frases) y la letra que se usa es una tipografía hecha para aprender a leer.'],
      ['¿Puedo vender lo que hago con Jelyx?', 'Sí, desde el plan Creador: licencia comercial, sin marca de agua y con edición para imprenta.'],
      ['¿De dónde sale la información sobre KiddoWorksheets?', 'De su sitio público, revisado en noviembre de 2026. Si algo cambió, escríbenos y actualizamos la tabla.'],
    ],
    request: 'Cuadernillo de actividades de los animales de la granja: sopa de letras, laberinto, contar y colorear',
    audience: 'Primaria baja (6–8)',
  },
]

export const comparisonHref = (c: Comparison) => `/comparar/${c.slug}`
