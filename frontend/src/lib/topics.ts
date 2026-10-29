// Landing topics: one static page each at /material-educativo/<slug> (written by scripts/seo.ts at build time)
// and a link from the home page. Plain data only: Node runs this file directly, without a bundler.

export type Topic = {
  slug: string
  name: string            // the subject as teachers search it
  title: string           // <title> and <h1>
  description: string     // meta description, ≤ 160 characters
  intro: string
  audience: string        // one of AUDIENCES: what the studio opens with
  request: string         // the studio's first request, ready to generate
  outline: string[]       // a sample table of contents
  includes: string[]      // what the material brings
  faq: [string, string][]
}

export const TOPICS: Topic[] = [
  {
    slug: 'lectoescritura', name: 'Lectoescritura', title: 'Material de lectoescritura para imprimir',
    description: 'Crea cuadernillos de lectoescritura con vocales, sílabas, trazos y dictados, listos para imprimir en PDF o editar en Word.',
    intro: 'Cuadernillos para aprender a leer y escribir paso a paso: trazos, vocales, sílabas, palabras y primeras frases, con dibujos para colorear y ejercicios que van de lo fácil a lo difícil.',
    audience: 'Preescolar (3–5 años)', request: 'Cuadernillo de lectoescritura de la vocal A: repasar, colorear, sílabas y dictado',
    outline: ['Trazos de preescritura', 'La vocal A: forma y sonido', 'Palabras que empiezan con A', 'Sílabas ma, me, mi, mo, mu', 'Une la palabra con su dibujo', 'Mi primer dictado'],
    includes: ['Trazos punteados para repasar', 'Ilustraciones para colorear', 'Sopas de letras y relacionar', 'Solucionario para el docente'],
    faq: [['¿Sirve para el método silábico?', 'Sí. Pide el método que usas (silábico, fonético, global) y el cuadernillo se arma con esa progresión.'], ['¿Puedo cambiar las palabras?', 'Sí, todo el texto se edita antes de descargar y editarlo no cuesta créditos.']],
  },
  {
    slug: 'matematicas-primaria', name: 'Matemáticas', title: 'Fichas de matemáticas para primaria',
    description: 'Genera fichas de matemáticas para primaria: sumas, restas, multiplicaciones, fracciones y problemas, con solucionario y listas para imprimir.',
    intro: 'Cuadernillos de práctica con operaciones, problemas razonados y material para contar, ordenados por dificultad y con solucionario al final.',
    audience: 'Primaria baja (6–8)', request: 'Cuadernillo de sumas hasta el 10 con dibujos para contar y problemas cortos',
    outline: ['Contamos objetos hasta el 10', 'Sumas con dibujos', 'Sumas en la recta numérica', 'Problemas de la tiendita', 'Restas para quitar', 'Repaso y evaluación'],
    includes: ['Arreglos y dibujos para contar', 'Problemas con contexto cotidiano', 'Evaluación final', 'Solucionario'],
    faq: [['¿Llega a fracciones y multiplicaciones?', 'Sí. Indica el tema y el grado; el contenido se ajusta al nivel que elijas.'], ['¿Las respuestas son correctas?', 'Los ejercicios se revisan antes de maquetarse y el solucionario sale de las mismas respuestas.']],
  },
  {
    slug: 'libros-para-colorear', name: 'Libros para colorear', title: 'Libros para colorear personalizados',
    description: 'Crea libros para colorear de cualquier tema con dibujos de línea limpia, nombres de cada figura y portada propia. Descarga en PDF listo para imprimir.',
    intro: 'Libros para colorear con ilustraciones de línea clara pensadas para manos pequeñas, el nombre de cada dibujo y una portada a color.',
    audience: 'Preescolar (3–5 años)', request: 'Libro para colorear de animales de la granja, con el nombre de cada animal',
    outline: ['La vaca', 'El caballo', 'La gallina y sus pollitos', 'El cerdito', 'La oveja', 'El granero'],
    includes: ['Dibujos de línea limpia', 'Nombre de cada figura', 'Portada ilustrada', 'Edición para imprenta (KDP)'],
    faq: [['¿Puedo venderlos?', 'Desde el plan Creador tienes licencia comercial y la edición para imprenta con lomo y sangrado.'], ['¿Los dibujos son originales?', 'Sí, se generan para tu libro; no se copian de otros.']],
  },
  {
    slug: 'ciencias-naturales', name: 'Ciencias naturales', title: 'Secuencias didácticas de ciencias naturales',
    description: 'Arma secuencias didácticas de ciencias: ciclo del agua, seres vivos, cuerpo humano y más, con experimentos caseros y actividades.',
    intro: 'Lecciones de ciencias con explicación clara, experimento casero, preguntas de comprensión y actividades para cada clase.',
    audience: 'Secundaria', request: 'Secuencia de lecciones sobre el ciclo del agua con un experimento casero por lección',
    outline: ['¿Dónde está el agua del planeta?', 'Evaporación: el experimento del vaso', 'Condensación y nubes', 'Precipitación', 'El agua subterránea', 'Cuidemos el agua'],
    includes: ['Experimento por lección', 'Esquemas y diagramas', 'Preguntas de comprensión', 'Fuentes consultadas'],
    faq: [['¿De dónde sale la información?', 'Un agente investigador consulta fuentes y las lista al final del material.'], ['¿Sigue el programa oficial?', 'Puedes indicar el programa o los aprendizajes esperados y la secuencia se ordena con ellos.']],
  },
  {
    slug: 'ingles-para-ninos', name: 'Inglés', title: 'Material de inglés para niños',
    description: 'Crea material de inglés para niños: vocabulario con imágenes, tarjetas, frases y juegos, listo para imprimir en el aula o en casa.',
    intro: 'Vocabulario en inglés con dibujos, tarjetas recortables, frases cortas y actividades para relacionar, colorear y repasar.',
    audience: 'Primaria baja (6–8)', request: 'Vocabulario en inglés de los animales: tarjetas, colorear y relacionar con su nombre',
    outline: ['Farm animals', 'Wild animals', 'Sea animals', 'What can it do?', 'Match the word', 'Review game'],
    includes: ['Tarjetas de vocabulario', 'Actividades de relacionar', 'Frases modelo', 'Solucionario'],
    faq: [['¿Viene todo en inglés?', 'Elige el idioma de las instrucciones; el vocabulario va en inglés.'], ['¿Sirve para varios niveles?', 'Sí, desde preescolar hasta secundaria.']],
  },
  {
    slug: 'historia', name: 'Historia', title: 'Material de historia para primaria y secundaria',
    description: 'Genera lecciones de historia con líneas del tiempo, lecturas, mapas y actividades: culturas mesoamericanas, independencia y más.',
    intro: 'Lecciones de historia con lecturas breves, líneas del tiempo, personajes, mapas y preguntas para pensar.',
    audience: 'Primaria alta (9–12)', request: 'Lecciones sobre las culturas mesoamericanas con línea del tiempo y actividades',
    outline: ['¿Qué es Mesoamérica?', 'Los olmecas', 'Los mayas', 'Teotihuacan', 'Los mexicas', 'Línea del tiempo'],
    includes: ['Líneas del tiempo', 'Lecturas breves', 'Preguntas de reflexión', 'Fuentes consultadas'],
    faq: [['¿Incluye fuentes?', 'Sí, las fuentes consultadas aparecen al final.'], ['¿Puedo enfocarlo en mi país?', 'Sí, describe el tema y el enfoque que necesitas.']],
  },
  {
    slug: 'geografia', name: 'Geografía', title: 'Fichas de geografía con mapas para colorear',
    description: 'Crea fichas de geografía con mapas para colorear y ubicar: continentes, océanos, relieve y climas, listas para imprimir.',
    intro: 'Cuadernillos de geografía con mapas, rosa de los vientos, actividades de ubicar y colorear, y datos clave de cada región.',
    audience: 'Primaria alta (9–12)', request: 'Cuadernillo de los continentes y océanos con mapas para colorear y ubicar',
    outline: ['El planeta Tierra', 'Los continentes', 'Los océanos', 'Puntos cardinales', 'Climas del mundo', 'Repaso'],
    includes: ['Mapas para colorear', 'Actividades de ubicar', 'Datos clave', 'Evaluación'],
    faq: [['¿Los mapas son exactos?', 'Los mapas son esquemáticos y educativos, pensados para colorear y ubicar.'], ['¿Puedo pedir mi país o estado?', 'Sí, el tema puede ser tan local como necesites.']],
  },
  {
    slug: 'piano-para-principiantes', name: 'Música', title: 'Método de piano para principiantes',
    description: 'Crea un método de piano paso a paso con teclado ilustrado, pentagramas y melodías sencillas para niños y adultos principiantes.',
    intro: 'Métodos de música con teclado ilustrado, notas resaltadas, pentagramas dibujados y melodías que suben de nivel en cada lección.',
    audience: 'Adultos principiantes', request: 'Método de piano para principiantes: postura, Do central, primeras melodías con la mano derecha',
    outline: ['Postura y manos', 'El Do central', 'Do, Re, Mi', 'Mi primera melodía', 'La mano izquierda', 'Pieza final'],
    includes: ['Teclados con notas resaltadas', 'Pentagramas dibujados', 'Ejercicios progresivos', 'Repaso por lección'],
    faq: [['¿Incluye partituras?', 'Sí, los pentagramas se dibujan con las notas de cada ejercicio.'], ['¿Sirve para otros instrumentos?', 'Sí: guitarra, flauta o teoría musical, describe lo que necesitas.']],
  },
  {
    slug: 'educacion-socioemocional', name: 'Valores y emociones', title: 'Material de educación socioemocional',
    description: 'Genera cuadernillos de emociones y valores: reconocer, nombrar y manejar emociones, con actividades y dibujos para niños.',
    intro: 'Actividades para reconocer y nombrar emociones, cuentos breves, preguntas para conversar y dibujos para expresarse.',
    audience: 'Primaria baja (6–8)', request: 'Cuadernillo de emociones: reconocerlas, nombrarlas y qué hacer con cada una',
    outline: ['¿Qué son las emociones?', 'La alegría', 'La tristeza', 'El enojo', 'El miedo', 'Mi termómetro de emociones'],
    includes: ['Cuentos breves', 'Preguntas para conversar', 'Dibujos para expresarse', 'Guía para el adulto'],
    faq: [['¿Sirve para tutoría?', 'Sí, para tutoría, orientación o en casa.'], ['¿Puedo adaptar la edad?', 'Sí, elige el nivel al crearlo.']],
  },
  {
    slug: 'cuadernillos-de-repaso', name: 'Cuadernillos de repaso', title: 'Cuadernillos de repaso para vacaciones',
    description: 'Crea cuadernillos de repaso para vacaciones o fin de ciclo con español, matemáticas y ciencias, por grado y listos para imprimir.',
    intro: 'Repasos por grado que mezclan lectura, operaciones y ciencias en fichas cortas, ideales para vacaciones o para empezar el ciclo.',
    audience: 'Primaria alta (9–12)', request: 'Cuadernillo de repaso de vacaciones para cuarto de primaria: lectura, operaciones y ciencias',
    outline: ['Lectura de comprensión', 'Operaciones básicas', 'Fracciones', 'Ciencias: el cuerpo humano', 'Problemas razonados', 'Autoevaluación'],
    includes: ['Fichas cortas por día', 'Varias materias', 'Autoevaluación', 'Solucionario'],
    faq: [['¿Puedo hacer uno por grado?', 'Sí. Agrúpalos en una colección y cada grado queda como un nivel con la misma identidad.'], ['¿Cuánto cuesta uno?', 'Aproximadamente 1 crédito por página, más 5 del esquema y la portada.']],
  },
]

export const topicHref = (t: Topic) => `/material-educativo/${t.slug}`
