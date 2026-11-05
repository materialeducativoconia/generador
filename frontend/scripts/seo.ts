// After `vite build`: static, crawlable pages for each landing topic, the topic hub, sitemap.xml and robots.txt,
// the comparison pages (/comparar/<slug>) and the home page's meta tags. vercel.json rewrites /material-educativo/<slug> to these files before the SPA fallback.
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { PUBLIC_PLANS } from '../src/lib/pricing.ts'
import { showcaseFrom } from '../src/lib/showcase.ts'
import { COMPARISONS, comparisonHref, type Comparison } from '../src/lib/comparisons.ts'
import { TOPICS, topicHref, type Topic } from '../src/lib/topics.ts'

const SITE = (process.env.SITE_URL
  ?? (process.env.VERCEL_PROJECT_PRODUCTION_URL ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}` : 'http://localhost:5173'))
  .replace(/\/$/, '')
const NAME = 'Jelyx Docs'
const COVERS = `${(process.env.VITE_SUPABASE_URL ?? 'https://uryxcesvtrkwrtjmszcc.supabase.co').replace(/\/$/, '')}/storage/v1/object/public/covers/showcase`
const DIST = new URL('../dist/', import.meta.url)
const API = (process.env.SEO_API_URL ?? 'https://generador-oktm.onrender.com').replace(/\/$/, '')
const OG = `${SITE}/og.jpg`

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)
const studio = (t: Topic) => `/?${new URLSearchParams({ pedido: t.request, publico: t.audience })}#crear`
const json = (data: object) => `<script type="application/ld+json">${JSON.stringify(data).replace(/</g, '\\u003c')}</script>`

/** Description, canonical, Open Graph and Twitter tags: what search results and shared links show. */
function meta(title: string, description: string, path: string, image = OG) {
  const url = SITE + path
  return `<meta name="description" content="${esc(description)}">
<link rel="canonical" href="${url}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="${NAME}">
<meta property="og:locale" content="es_MX">
<meta property="og:title" content="${esc(title)}">
<meta property="og:description" content="${esc(description)}">
<meta property="og:url" content="${url}">
<meta property="og:image" content="${esc(image)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="${esc(title)}">
<meta name="twitter:description" content="${esc(description)}">
<meta name="twitter:image" content="${esc(image)}">`
}

function head(title: string, description: string, path: string, extra = '', image = OG) {
  return `<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)}</title>
${meta(title, description, path, image)}
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>${CSS}</style>
${extra}`
}

const LOGO = `<svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="13" height="18" rx="2.5" fill="currentColor" opacity=".18"/><rect x="8" y="3" width="13" height="18" rx="2.5" fill="currentColor"/><path d="M11.5 8.5h6M11.5 12h6M11.5 15.5h3.5" stroke="var(--bg)" stroke-width="1.6" stroke-linecap="round"/></svg>`
const HEADER = `<header class="top"><a class="brand" href="/">${LOGO}<span>${NAME}</span></a>
<nav><a href="/material-educativo">Temas</a><a class="wide" href="/comparar">Comparar</a><a class="wide" href="/laminas">Láminas gratis</a><a href="/#planes">Planes</a><a class="btn small" href="/app">Entrar</a></nav></header>`
const FOOTER = `<footer><p><a href="/">${NAME}</a> · <a href="/material-educativo">Material educativo por tema</a> · <a href="/laminas">Láminas gratis</a> · <a href="/comparar">Comparar apps</a> · <a href="/#planes">Planes</a></p>
<p class="muted">Vista previa sin registro ni tarjeta.</p></footer>`

/** The example covers drifting by, as on the home page: pure CSS, two copies of the row. */
const carousel = (first?: string) => {
  const row = showcaseFrom(first)
  const imgs = (hidden: boolean) => row.map(([slug, title]) =>
    `<img src="${COVERS}/${slug}.webp" alt="${hidden ? '' : esc(`Portada de ejemplo: ${title}`)}"${hidden ? ' aria-hidden="true"' : ''} width="200" height="283" loading="lazy" decoding="async">`).join('')
  return `<section class="showcase" aria-label="Portadas de ejemplo"><div class="track">${imgs(false)}${imgs(true)}</div></section>`
}

const VALUES = `<section><p class="eyebrow">Por qué Jelyx</p><h2>Material de editorial, sin pasar el fin de semana armándolo.</h2><div class="values">
<article><h3>Minutos, no fines de semana</h3><p>Del tema al libro terminado en una sola sesión: Jelyx investiga, escribe, ilustra y maqueta; tú decides.</p></article>
<article><h3>Se ve como libro de editorial</h3><p>Portada pintada para tu tema, ilustraciones en cada página y una tipografía cuidada. Nada de plantillas genéricas.</p></article>
<article><h3>Tuyo para usar o vender</h3><p>Imprímelo para tu grupo o, desde el plan Creador, véndelo en Amazon KDP o Teachers Pay Teachers sin marca de agua.</p></article></div></section>`

const STEPS = `<section><p class="eyebrow">Cómo funciona</p><h2>De la idea al libro impreso en tres pasos.</h2><ol class="steps">
<li><strong>Cuéntanos qué necesitas</strong><span>El tema, el nivel y el formato que prefieras.</span></li>
<li><strong>Mira tu tomo, gratis</strong><span>Tu portada y tus páginas ilustradas en un par de minutos, sin registrarte.</span></li>
<li><strong>Hazlo tuyo y descárgalo</strong><span>Ajusta el texto sin gastar créditos y descarga en PDF o Word.</span></li></ol></section>`

const CTA = (href: string) => `<section class="cta"><h2>Tu próximo libro está a un párrafo de distancia.</h2><p>Escribe el tema y míralo terminado antes de pagar.</p>
<a class="btn light" href="${esc(href)}">Crear mi vista previa gratis</a></section>`

const plans = () => `<section id="planes"><p class="eyebrow">Planes</p><h2>Empieza hoy. Cancela cuando quieras.</h2><div class="grid3">${PUBLIC_PLANS.map((p) => `
<article class="card"><h3>${p.label}</h3><p class="muted">${p.for}</p><p class="price">$${p.price} <span class="muted">USD/mes</span></p>
<ul>${p.features.map((f) => `<li>${esc(f)}</li>`).join('')}</ul></article>`).join('')}</div>
<p class="muted center">1 crédito ≈ 1 página. Si una generación falla, te devolvemos los créditos.</p></section>`

function topicPage(t: Topic) {
  const related = TOPICS.filter((o) => o.slug !== t.slug).slice(0, 5)
  const ld = [
    { '@context': 'https://schema.org', '@type': 'FAQPage', mainEntity: t.faq.map(([q, a]) => ({ '@type': 'Question', name: q, acceptedAnswer: { '@type': 'Answer', text: a } })) },
    { '@context': 'https://schema.org', '@type': 'BreadcrumbList', itemListElement: [
      { '@type': 'ListItem', position: 1, name: NAME, item: `${SITE}/` },
      { '@type': 'ListItem', position: 2, name: 'Material educativo', item: `${SITE}/material-educativo` },
      { '@type': 'ListItem', position: 3, name: t.name, item: SITE + topicHref(t) }] },
  ]
  return `<!doctype html><html lang="es"><head>${head(`${t.title} | ${NAME}`, t.description, topicHref(t), ld.map(json).join('\n'), `${COVERS}/${t.cover}.webp`)}</head><body>
${HEADER}<main>
<nav class="crumbs" aria-label="Ruta"><a href="/material-educativo">Material educativo</a> › ${esc(t.name)}</nav>
<section class="hero"><p class="eyebrow">${esc(t.name)} · ${esc(t.audience)}</p><h1>${esc(t.title)}</h1><p class="lede">${esc(t.intro)}</p>
<a class="btn" href="${esc(studio(t))}">Crear el mío gratis</a><p class="muted small trust">✓ Ves tu tomo real antes de pagar · ✓ Sin tarjeta · ✓ PDF y Word</p></section>
${carousel(t.cover)}
<section class="two"><div class="card"><p class="eyebrow">Ejemplo de índice</p><h2>Así se arma tu tomo</h2><p class="muted small">«${esc(t.request)}»</p><ol>${t.outline.map((o) => `<li>${esc(o)}</li>`).join('')}</ol></div>
<div class="card"><p class="eyebrow">Qué incluye</p><h2>Listo para imprimir, de verdad</h2><ul class="checks">${t.includes.map((i) => `<li>${esc(i)}</li>`).join('')}<li>Portada ilustrada única para tu tema</li><li>A color, en blanco y negro o para imprenta</li></ul>
<a class="btn small" href="${esc(studio(t))}">Ver mi vista previa</a></div></section>
${VALUES}
${STEPS}
<section><p class="eyebrow">Preguntas frecuentes</p><h2>Lo que suelen preguntarnos.</h2>${t.faq.map(([q, a]) => `<details><summary>${esc(q)}</summary><p>${esc(a)}</p></details>`).join('')}</section>
${plans()}
<section><p class="eyebrow">Más ideas</p><h2>Otros temas para crear hoy</h2>${topicGrid(related)}</section>
${CTA(studio(t))}
</main>${FOOTER}</body></html>`
}

const topicGrid = (list: Topic[]) => `<ul class="covers">${list.map((t) => `<li><a href="${topicHref(t)}"><img src="${COVERS}/${t.cover}.webp" alt="" width="180" height="240" loading="lazy" decoding="async"><span class="eyebrow">${esc(t.name)}</span><strong>${esc(t.title)}</strong></a></li>`).join('')}</ul>`

function hubPage() {
  const title = `Material educativo para imprimir por tema | ${NAME}`
  const description = 'Crea material educativo para imprimir de cualquier tema: libros ilustrados, cuentos, lectoescritura, matemáticas, ciencias, inglés, libros para colorear y más.'
  const ld = { '@context': 'https://schema.org', '@type': 'CollectionPage', name: title, url: `${SITE}/material-educativo`,
    hasPart: TOPICS.map((t) => ({ '@type': 'WebPage', name: t.title, url: SITE + topicHref(t) })) }
  return `<!doctype html><html lang="es"><head>${head(title, description, '/material-educativo', json(ld))}</head><body>
${HEADER}<main><section class="hero"><p class="eyebrow">Material educativo</p><h1>Material educativo para imprimir, de cualquier tema</h1>
<p class="lede">Libros ilustrados, cuadernillos y libros para colorear con calidad de editorial, hechos para tu tema y tu grupo en minutos. Elige un tema y mira el tuyo gratis.</p>
<a class="btn" href="/#crear">Crear mi vista previa gratis</a></section>
${carousel()}
<section><p class="eyebrow">Temas</p><h2>¿Por dónde empezar?</h2>${topicGrid(TOPICS)}</section>
${VALUES}
${plans()}
${CTA('/#crear')}</main>${FOOTER}</body></html>`
}

const MARK = { jelyx: '✓', them: '–', tie: '✓' } as const
const RIVAL_MARK = { jelyx: '–', them: '✓', tie: '✓' } as const

/** Feature by feature, the winner's cell marked; on a phone each row stacks as a card (no sideways scroll). */
const vsTable = (c: Comparison) => `<table class="vs"><caption class="muted small">Datos de ${esc(c.rival)} tomados de su sitio público (${esc(c.checked)}).</caption>
<thead><tr><th scope="col">Qué comparas</th><th scope="col">${NAME}</th><th scope="col">${esc(c.rival)}</th></tr></thead><tbody>${c.rows.map(([f, j, t, w]) => `
<tr><th scope="row">${esc(f)}</th><td class="${w === 'them' ? '' : 'win'}" data-app="${NAME}"><b aria-hidden="true">${MARK[w]}</b> ${esc(j)}</td><td class="${w === 'jelyx' ? '' : 'win'}" data-app="${esc(c.rival)}"><b aria-hidden="true">${RIVAL_MARK[w]}</b> ${esc(t)}</td></tr>`).join('')}</tbody></table>`

function comparisonPage(c: Comparison) {
  const start = `/?${new URLSearchParams({ pedido: c.request, publico: c.audience })}#crear`
  const wins = c.rows.filter((r) => r[3] === 'jelyx').length
  const ld = [
    { '@context': 'https://schema.org', '@type': 'FAQPage', mainEntity: c.faq.map(([q, a]) => ({ '@type': 'Question', name: q, acceptedAnswer: { '@type': 'Answer', text: a } })) },
    { '@context': 'https://schema.org', '@type': 'BreadcrumbList', itemListElement: [
      { '@type': 'ListItem', position: 1, name: NAME, item: `${SITE}/` },
      { '@type': 'ListItem', position: 2, name: 'Comparar', item: `${SITE}/comparar` },
      { '@type': 'ListItem', position: 3, name: `${NAME} vs ${c.rival}`, item: SITE + comparisonHref(c) }] },
  ]
  return `<!doctype html><html lang="es"><head>${head(`${c.title} | ${NAME}`, c.description, comparisonHref(c), ld.map(json).join('\n'))}</head><body>
${HEADER}<main>
<nav class="crumbs" aria-label="Ruta"><a href="/comparar">Comparar</a> › ${NAME} vs ${esc(c.rival)}</nav>
<section class="hero"><p class="eyebrow">Comparación · revisada en ${esc(c.checked)}</p><h1>${esc(c.title)}</h1><p class="lede">${esc(c.intro)}</p>
<a class="btn" href="${esc(start)}">Probar ${NAME} gratis</a><p class="muted small trust">✓ Ves tu tomo real antes de pagar · ✓ Sin tarjeta · ✓ En español</p></section>
<section class="card verdict"><p class="eyebrow">La respuesta corta</p><p>${esc(c.verdict)}</p><p class="muted small">${NAME} gana en ${wins} de ${c.rows.length} puntos; ${esc(c.rival)}, en ${c.rows.filter((r) => r[3] === 'them').length}.</p></section>
<section><p class="eyebrow">Punto por punto</p><h2>${NAME} y ${esc(c.rival)}, lado a lado.</h2>${vsTable(c)}</section>
<section class="two"><div class="card"><p class="eyebrow">Elige ${NAME} si…</p><ul class="checks">${c.pickJelyx.map((p) => `<li>${esc(p)}</li>`).join('')}</ul><a class="btn small" href="${esc(start)}">Crear mi vista previa</a></div>
<div class="card"><p class="eyebrow">Elige ${esc(c.rival)} si…</p><ul>${c.pickThem.map((p) => `<li>${esc(p)}</li>`).join('')}</ul></div></section>
${VALUES}
${STEPS}
<section><p class="eyebrow">Preguntas frecuentes</p><h2>Lo que suelen preguntarnos.</h2>${c.faq.map(([q, a]) => `<details><summary>${esc(q)}</summary><p>${esc(a)}</p></details>`).join('')}</section>
${plans()}
<section><p class="eyebrow">Ideas para empezar</p><h2>Material que puedes crear hoy</h2>${topicGrid(TOPICS.slice(0, 5))}</section>
${CTA(start)}
</main>${FOOTER}</body></html>`
}

function comparisonsHub() {
  const title = `Comparar ${NAME} con otras apps de material educativo`
  const description = `${NAME} frente a otras apps y sitios de fichas para imprimir: idioma, niveles, solucionario, marca propia y precio, punto por punto.`
  const ld = { '@context': 'https://schema.org', '@type': 'CollectionPage', name: title, url: `${SITE}/comparar`,
    hasPart: COMPARISONS.map((c) => ({ '@type': 'WebPage', name: c.title, url: SITE + comparisonHref(c) })) }
  return `<!doctype html><html lang="es"><head>${head(title, description, '/comparar', json(ld))}</head><body>
${HEADER}<main><section class="hero"><p class="eyebrow">Comparar</p><h1>${NAME} frente a otras apps de material educativo</h1>
<p class="lede">Comparaciones honestas, con los datos de cada sitio y la fecha en que los revisamos. También te decimos cuándo te conviene la otra opción.</p></section>
<section class="grid3">${COMPARISONS.map((c) => `<a class="card topic" href="${comparisonHref(c)}"><span class="eyebrow">${NAME} vs ${esc(c.rival)}</span><strong>${esc(c.title)}</strong><span class="muted small">${esc(c.description)}</span></a>`).join('')}</section>
${VALUES}
${CTA('/#crear')}</main>${FOOTER}</body></html>`
}

const HOME_TITLE = `${NAME}: libros educativos ilustrados para imprimir, hechos con IA`
const HOME_DESCRIPTION = 'Escribe el tema y la edad y recibe un libro ilustrado listo para imprimir: láminas a página completa, cuentos, cuadernillos y libros para colorear. Vista previa gratis.'

/** The built SPA page with this route's head and a crawlable copy of its content inside #root, which React
 * replaces when it starts: search engines and link previews read the page without running the app. */
function shell(base: string, path: string, title: string, description: string, body: string, ld: object[], image = OG) {
  return base
    .replace(/<title>[^<]*<\/title>/, `<title>${esc(title)}</title>\n    ${meta(title, description, path, image)}\n    ${ld.map(json).join('\n    ')}`)
    .replace('<div id="root"></div>', `<div id="root"><div class="prerender">${body}</div></div>`)
}

const ORG = { '@context': 'https://schema.org', '@type': 'Organization', name: NAME, url: `${SITE}/`, logo: `${SITE}/apple-touch-icon.png` }

function homeShell(base: string) {
  const ld = [ORG,
    { '@context': 'https://schema.org', '@type': 'WebSite', name: NAME, url: `${SITE}/`, inLanguage: 'es' },
    { '@context': 'https://schema.org', '@type': 'SoftwareApplication', name: NAME, url: `${SITE}/`,
      applicationCategory: 'EducationalApplication', operatingSystem: 'Web', inLanguage: 'es', description: HOME_DESCRIPTION,
      image: OG, offers: PUBLIC_PLANS.map((p) => ({ '@type': 'Offer', name: p.label, price: p.price, priceCurrency: 'USD' })) }]
  const body = `<h1>Libros educativos ilustrados, listos en minutos.</h1><p>${esc(HOME_DESCRIPTION)}</p>
<h2>Material educativo por tema</h2><ul>${TOPICS.map((t) => `<li><a href="${topicHref(t)}">${esc(t.title)}</a></li>`).join('')}</ul>
<p><a href="/laminas">Láminas gratis para imprimir</a> · <a href="/material-educativo">Todos los temas</a> · <a href="/comparar">Comparar apps</a> · <a href="/#planes">Planes</a></p>`
  return shell(base, '/', HOME_TITLE, HOME_DESCRIPTION, body, ld)
}

type Plate = { slug: string; title: string; answer: string; topic: string; audience: string; style_name: string; image_url: string; created_at: string }

/** The published free plates, from the API; the build goes on without them when it cannot answer (a cold start). */
async function plates(): Promise<Plate[]> {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const res = await fetch(`${API}/api/library`, { signal: AbortSignal.timeout(30_000) })
      if (res.ok) return ((await res.json()) as { plates: Plate[] }).plates
    } catch { /* asleep: try again */ }
  }
  console.warn('seo: the library did not answer; no plate pages this build')
  return []
}

const plateLd = (p: Plate) => ({ '@context': 'https://schema.org', '@type': 'LearningResource', name: p.title,
  description: p.answer || p.title, url: `${SITE}/laminas/${p.slug}`, image: p.image_url, inLanguage: 'es',
  learningResourceType: 'Lámina ilustrada', educationalLevel: p.audience || undefined, about: p.topic,
  isAccessibleForFree: true, publisher: { '@type': 'Organization', name: NAME } })

function libraryShell(base: string, list: Plate[]) {
  const title = `Láminas gratis para imprimir | ${NAME}`
  const description = 'Láminas educativas ilustradas gratis: una ilustración con su pregunta y su respuesta, lista para imprimir en PDF tamaño carta.'
  const ld = [{ '@context': 'https://schema.org', '@type': 'CollectionPage', name: title, url: `${SITE}/laminas`, description,
    hasPart: list.map((p) => ({ '@type': 'LearningResource', name: p.title, url: `${SITE}/laminas/${p.slug}` })) }]
  const body = `<h1>Láminas para imprimir, gratis.</h1><p>${esc(description)}</p>
<ul>${list.map((p) => `<li><a href="/laminas/${p.slug}">${esc(p.title)}</a> · ${esc(p.topic)}</li>`).join('')}</ul>`
  return shell(base, '/laminas', title, description, body, ld, list[0]?.image_url)
}

function plateShell(base: string, p: Plate) {
  const title = `${p.title} — lámina gratis de ${p.topic} | ${NAME}`
  const description = (p.answer || `Lámina ilustrada de ${p.topic} para imprimir gratis en PDF.`).slice(0, 158)
  const crumbs = { '@context': 'https://schema.org', '@type': 'BreadcrumbList', itemListElement: [
    { '@type': 'ListItem', position: 1, name: NAME, item: `${SITE}/` },
    { '@type': 'ListItem', position: 2, name: 'Láminas gratis', item: `${SITE}/laminas` },
    { '@type': 'ListItem', position: 3, name: p.title, item: `${SITE}/laminas/${p.slug}` }] }
  const body = `<p><a href="/laminas">Láminas gratis</a> › ${esc(p.topic)}</p><h1>${esc(p.title)}</h1>
<img src="${esc(p.image_url)}" alt="${esc(p.title)}" width="717" height="960"><p>${esc(p.answer)}</p>
<p>Estilo ${esc(p.style_name)} · PDF tamaño carta gratis.</p>`
  return shell(base, `/laminas/${p.slug}`, title, description, body, [plateLd(p), crumbs], p.image_url)
}

const CSS = `:root{--bg:#fff;--text:#0c0a09;--muted:#6b6864;--surface:#f7f7f6;--border:#e7e5e2;--accent:#5b4cf0;--accent-soft:#eeecfe}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.6 Geist,system-ui,sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit}main{max-width:980px;margin:0 auto;padding:0 16px 64px}
.top{display:flex;justify-content:space-between;align-items:center;gap:12px;max-width:980px;margin:0 auto;padding:16px}
.top nav{display:flex;align-items:center;gap:16px;font-size:14px}.top nav a{text-decoration:none}
.brand{display:inline-flex;align-items:center;gap:8px;font-weight:600;text-decoration:none;letter-spacing:-.02em}
.hero{padding:56px 0 32px;max-width:44rem}h1{font-size:clamp(32px,5vw,48px);line-height:1.06;letter-spacing:-.035em;margin:0 0 16px;font-weight:600;text-wrap:balance}
h2{font-size:22px;letter-spacing:-.02em;margin:0 0 12px}h3{margin:0}section{margin:40px 0}
.lede{font-size:18px;color:var(--muted);margin:0 0 24px;text-wrap:pretty}.eyebrow{display:block;margin:0 0 10px;font-size:12px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.muted{color:var(--muted)}.small{font-size:13px}.center{text-align:center}
.btn{display:inline-block;padding:12px 22px;border-radius:999px;background:var(--text);color:var(--bg);text-decoration:none;font-weight:500}.btn.small{padding:6px 14px}
.card{display:block;background:var(--bg);border:1px solid var(--border);border-radius:16px;padding:20px;text-decoration:none}
.card ul,.card ol{padding-left:20px;margin:8px 0 0}.card li{margin:4px 0}
.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}
.grid3{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}
.topic{display:grid;gap:6px}a.card:hover{border-color:var(--accent)}
.price{font-size:28px;font-weight:600;margin:8px 0}.price span{font-size:14px;font-weight:400}
.steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;padding:0;list-style:none;counter-reset:s}
.steps li{background:var(--surface);border-radius:14px;padding:16px}
details{border-bottom:1px solid var(--border);padding:12px 0}summary{cursor:pointer;font-weight:500}details p{margin:8px 0 0;color:var(--muted)}
.topics{columns:2 260px;padding-left:20px}.topics li{margin:6px 0}.crumbs{font-size:13px;color:var(--muted);padding-top:16px}
h2{font-size:clamp(24px,3.6vw,34px);line-height:1.1;letter-spacing:-.03em;font-weight:600;text-wrap:balance}.card h2{font-size:20px}
.trust{margin-top:12px}.btn.light{background:#fff;color:#0c0a09;font-weight:600}.btn{transition:transform .16s cubic-bezier(.23,1,.32,1)}.btn:active{transform:scale(.97)}
.showcase{width:100vw;margin:8px calc(50% - 50vw) 0;overflow:hidden;-webkit-mask-image:linear-gradient(90deg,transparent,#000 8%,#000 92%,transparent);mask-image:linear-gradient(90deg,transparent,#000 8%,#000 92%,transparent)}
.showcase .track{display:flex;gap:20px;width:max-content;padding:12px 0 24px;animation:drift 60s linear infinite}.showcase:hover .track{animation-play-state:paused}
.showcase img{width:180px;height:auto;aspect-ratio:210/297;object-fit:cover;border-radius:5px 11px 11px 5px;background:var(--surface);box-shadow:inset 6px 0 8px -6px rgb(0 0 0/.25),0 1px 2px rgb(12 10 9/.08),0 16px 30px -16px rgb(12 10 9/.45)}
@keyframes drift{from{transform:translateX(calc(-50% - 10px))}to{transform:translateX(0)}}
@media (prefers-reduced-motion:reduce){.showcase{overflow-x:auto}.showcase .track{animation:none}}
@media (max-width:640px){.showcase img{width:130px}.showcase .track{gap:14px}}
.values{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:1px;background:var(--border);border:1px solid var(--border);border-radius:20px;overflow:hidden}
.values article{background:var(--bg);padding:24px}.values h3{font-size:17px;letter-spacing:-.02em}.values p{margin:6px 0 0;color:var(--muted);font-size:15px}
.steps li{display:grid;gap:4px}.steps span{color:var(--muted);font-size:14px}
.checks{list-style:none;padding:0!important}.checks li{padding-left:24px;position:relative}.checks li::before{content:'✓';position:absolute;left:0;color:#0f7b4f;font-weight:700}
.card .btn{margin-top:16px}
.covers{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:20px 16px}
.covers a{display:grid;gap:4px;text-decoration:none}.covers img{width:100%;height:auto;aspect-ratio:3/4;object-fit:cover;border-radius:4px 10px 10px 4px;margin-bottom:6px;background:var(--surface);box-shadow:0 1px 2px rgb(12 10 9/.08),0 14px 26px -16px rgb(12 10 9/.4);transition:transform .22s cubic-bezier(.23,1,.32,1)}
@media (hover:hover){.covers a:hover img{transform:translateY(-4px) rotate(-.5deg)}}.covers strong{font-size:14px;line-height:1.3}.covers .eyebrow{margin:0;font-size:11px}
@media (max-width:640px){.covers{grid-template-columns:repeat(2,1fr)}}
.cta{position:relative;overflow:hidden;isolation:isolate;text-align:center;padding:64px 24px;border-radius:28px;background:#0c0a09;color:#fff}
.cta::before{content:'';position:absolute;inset:auto -10% -60% -10%;height:120%;z-index:-1;background:linear-gradient(120deg,#7c6cff,#ff8a6b 52%,#3dd6b5);filter:blur(80px);opacity:.55}
.verdict{background:var(--accent-soft);border-color:transparent}.verdict p:not(.eyebrow){margin:0 0 8px;font-size:17px}
.vs{width:100%;border-collapse:collapse;font-size:15px}.vs caption{caption-side:bottom;text-align:left;padding-top:10px}
.vs th,.vs td{text-align:left;vertical-align:top;padding:12px;border-bottom:1px solid var(--border)}.vs thead th{font-size:13px;color:var(--muted);font-weight:600}
.vs tbody th{font-weight:600;width:22%}.vs td{width:39%;color:var(--muted)}.vs td.win{color:var(--text)}.vs td b{display:inline-block;width:1.1em}.vs td.win b{color:#0f7b4f}
@media (max-width:640px){.vs thead{display:none}.vs tr{display:block;border:1px solid var(--border);border-radius:14px;padding:4px 14px;margin-bottom:12px}
.vs th,.vs td,.vs tbody th{display:block;width:auto;border:0;padding:8px 0}.vs tbody th{padding-top:12px}.vs td::before{content:attr(data-app);display:block;font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}}
@media (max-width:640px){.top nav .wide{display:none}}  /* the footer links them */
.cta h2{max-width:22ch;margin:0 auto 10px}.cta p{color:rgb(255 255 255/.72);margin:0 0 24px}
footer{border-top:1px solid var(--border);padding:24px 16px;text-align:center;font-size:14px}`

const pages: { path: string; images?: string[] }[] = [{ path: '/' }, { path: '/material-educativo' }]
mkdirSync(new URL('material-educativo/', DIST), { recursive: true })
writeFileSync(new URL('material-educativo/index.html', DIST), hubPage())
for (const t of TOPICS) {
  writeFileSync(new URL(`material-educativo/${t.slug}.html`, DIST), topicPage(t))
  pages.push({ path: topicHref(t), images: [`${COVERS}/${t.cover}.webp`] })
}
mkdirSync(new URL('comparar/', DIST), { recursive: true })
writeFileSync(new URL('comparar/index.html', DIST), comparisonsHub())
pages.push({ path: '/comparar' })
for (const c of COMPARISONS) {
  writeFileSync(new URL(`comparar/${c.slug}.html`, DIST), comparisonPage(c))
  pages.push({ path: comparisonHref(c) })
}

// The SPA's public pages: each at <path>/index.html, which Vercel serves before the SPA fallback.
const index = new URL('index.html', DIST)
const base = readFileSync(index, 'utf8')
const library = await plates()
mkdirSync(new URL('laminas/', DIST), { recursive: true })
writeFileSync(new URL('laminas/index.html', DIST), libraryShell(base, library))
pages.push({ path: '/laminas' })
for (const p of library) {
  mkdirSync(new URL(`laminas/${p.slug}/`, DIST), { recursive: true })
  writeFileSync(new URL(`laminas/${p.slug}/index.html`, DIST), plateShell(base, p))
  pages.push({ path: `/laminas/${p.slug}`, images: [p.image_url] })
}
writeFileSync(index, homeShell(base))

const today = new Date().toISOString().slice(0, 10)
const image = (src: string) => `<image:image><image:loc>${esc(src)}</image:loc></image:image>`
writeFileSync(new URL('sitemap.xml', DIST), `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
${pages.map((p) => `  <url><loc>${SITE}${p.path}</loc><lastmod>${today}</lastmod>${(p.images ?? []).map(image).join('')}</url>`).join('\n')}
</urlset>
`)
writeFileSync(new URL('robots.txt', DIST), `User-agent: *
Allow: /
Disallow: /app
Disallow: /admin
Disallow: /auth
Disallow: /api

Sitemap: ${SITE}/sitemap.xml
`)
console.log(`seo: ${pages.length} pages (${library.length} plates) for ${SITE}`)
