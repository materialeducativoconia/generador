// After `vite build`: static, crawlable pages for each landing topic, the topic hub, sitemap.xml and robots.txt,
// plus the home page's meta tags. Vercel serves these files before the SPA fallback (cleanUrls in vercel.json).
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { PUBLIC_PLANS, TRIAL_CREDITS } from '../src/lib/pricing.ts'
import { TOPICS, topicHref, type Topic } from '../src/lib/topics.ts'

const SITE = (process.env.SITE_URL
  ?? (process.env.VERCEL_PROJECT_PRODUCTION_URL ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}` : 'http://localhost:5173'))
  .replace(/\/$/, '')
const NAME = 'Material Educativo IA'
const DIST = new URL('../dist/', import.meta.url)

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)
const studio = (t: Topic) => `/app?${new URLSearchParams({ pedido: t.request, publico: t.audience })}`
const json = (data: object) => `<script type="application/ld+json">${JSON.stringify(data).replace(/</g, '\\u003c')}</script>`

function head(title: string, description: string, path: string, extra = '') {
  const url = SITE + path
  return `<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)}</title>
<meta name="description" content="${esc(description)}">
<link rel="canonical" href="${url}">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<meta property="og:type" content="website">
<meta property="og:site_name" content="${NAME}">
<meta property="og:locale" content="es_MX">
<meta property="og:title" content="${esc(title)}">
<meta property="og:description" content="${esc(description)}">
<meta property="og:url" content="${url}">
<meta name="twitter:card" content="summary">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>${CSS}</style>
${extra}`
}

const LOGO = `<svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="13" height="18" rx="2.5" fill="currentColor" opacity=".18"/><rect x="8" y="3" width="13" height="18" rx="2.5" fill="currentColor"/><path d="M11.5 8.5h6M11.5 12h6M11.5 15.5h3.5" stroke="var(--bg)" stroke-width="1.6" stroke-linecap="round"/></svg>`
const HEADER = `<header class="top"><a class="brand" href="/">${LOGO}<span>${NAME}</span></a>
<nav><a href="/material-educativo">Temas</a><a href="/#planes">Planes</a><a class="btn small" href="/app">Entrar</a></nav></header>`
const FOOTER = `<footer><p><a href="/">${NAME}</a> · <a href="/material-educativo">Material educativo por tema</a> · <a href="/#planes">Planes</a></p>
<p class="muted">Empieza gratis con ${TRIAL_CREDITS} créditos. Sin tarjeta.</p></footer>`

const plans = () => `<section id="planes"><h2>Planes</h2><div class="grid3">${PUBLIC_PLANS.map((p) => `
<article class="card"><h3>${p.label}</h3><p class="muted">${p.for}</p><p class="price">$${p.price} <span class="muted">USD/mes</span></p>
<ul>${p.features.map((f) => `<li>${esc(f)}</li>`).join('')}</ul></article>`).join('')}</div>
<p class="muted center">1 crédito ≈ 1 página. Si una generación falla, te devolvemos los créditos.</p></section>`

function topicPage(t: Topic) {
  const related = TOPICS.filter((o) => o.slug !== t.slug).slice(0, 6)
  const ld = [
    { '@context': 'https://schema.org', '@type': 'FAQPage', mainEntity: t.faq.map(([q, a]) => ({ '@type': 'Question', name: q, acceptedAnswer: { '@type': 'Answer', text: a } })) },
    { '@context': 'https://schema.org', '@type': 'BreadcrumbList', itemListElement: [
      { '@type': 'ListItem', position: 1, name: NAME, item: `${SITE}/` },
      { '@type': 'ListItem', position: 2, name: 'Material educativo', item: `${SITE}/material-educativo` },
      { '@type': 'ListItem', position: 3, name: t.name, item: SITE + topicHref(t) }] },
  ]
  return `<!doctype html><html lang="es"><head>${head(`${t.title} | ${NAME}`, t.description, topicHref(t), ld.map(json).join('\n'))}</head><body>
${HEADER}<main>
<nav class="crumbs" aria-label="Ruta"><a href="/material-educativo">Material educativo</a> › ${esc(t.name)}</nav>
<section class="hero"><p class="eyebrow">${esc(t.name)} · ${esc(t.audience)}</p><h1>${esc(t.title)}</h1><p class="lede">${esc(t.intro)}</p>
<a class="btn" href="${esc(studio(t))}">Crear este material gratis</a><p class="muted small">${TRIAL_CREDITS} créditos de prueba: alcanzan para un cuadernillo completo.</p></section>
<section class="two"><div class="card"><h2>Ejemplo de índice</h2><p class="muted small">«${esc(t.request)}»</p><ol>${t.outline.map((o) => `<li>${esc(o)}</li>`).join('')}</ol></div>
<div class="card"><h2>Qué incluye</h2><ul>${t.includes.map((i) => `<li>${esc(i)}</li>`).join('')}</ul>
<p class="muted small">Tú describes el tema y el nivel; un equipo de agentes planifica, investiga, escribe, ilustra y maqueta. Revisas y editas el texto gratis antes de descargar en PDF${' '}o Word.</p></div></section>
<section><h2>Cómo funciona</h2><ol class="steps"><li><strong>Describe</strong> el tema, el nivel y el formato.</li><li><strong>Revisa el esquema</strong> y ajusta las secciones.</li><li><strong>Descarga</strong> en PDF listo para imprimir o en Word editable.</li></ol></section>
<section><h2>Preguntas frecuentes</h2>${t.faq.map(([q, a]) => `<details><summary>${esc(q)}</summary><p>${esc(a)}</p></details>`).join('')}</section>
${plans()}
<section><h2>Más temas</h2><ul class="topics">${related.map((o) => `<li><a href="${topicHref(o)}">${esc(o.title)}</a></li>`).join('')}</ul></section>
</main>${FOOTER}</body></html>`
}

function hubPage() {
  const title = `Material educativo para imprimir por tema | ${NAME}`
  const description = 'Crea material educativo para imprimir de cualquier tema: lectoescritura, matemáticas, ciencias, inglés, libros para colorear y más.'
  const ld = { '@context': 'https://schema.org', '@type': 'CollectionPage', name: title, url: `${SITE}/material-educativo`,
    hasPart: TOPICS.map((t) => ({ '@type': 'WebPage', name: t.title, url: SITE + topicHref(t) })) }
  return `<!doctype html><html lang="es"><head>${head(title, description, '/material-educativo', json(ld))}</head><body>
${HEADER}<main><section class="hero"><p class="eyebrow">Material educativo</p><h1>Material educativo para imprimir, de cualquier tema</h1>
<p class="lede">${esc(description)} Elige un tema para ver un ejemplo y crearlo en minutos.</p></section>
<div class="grid3">${TOPICS.map((t) => `<a class="card topic" href="${topicHref(t)}"><span class="eyebrow">${esc(t.name)}</span><strong>${esc(t.title)}</strong><span class="muted small">${esc(t.description)}</span></a>`).join('')}</div>
${plans()}</main>${FOOTER}</body></html>`
}

function homeHead() {
  const description = 'Crea material educativo de cualquier tema listo para imprimir: libros para colorear, cuadernillos de fichas, métodos y secuencias didácticas.'
  const ld = { '@context': 'https://schema.org', '@type': 'SoftwareApplication', name: NAME, url: `${SITE}/`,
    applicationCategory: 'EducationalApplication', operatingSystem: 'Web', inLanguage: 'es', description,
    offers: PUBLIC_PLANS.map((p) => ({ '@type': 'Offer', name: p.label, price: p.price, priceCurrency: 'USD' })) }
  return `<meta name="description" content="${esc(description)}">
    <link rel="canonical" href="${SITE}/">
    <meta property="og:type" content="website"><meta property="og:site_name" content="${NAME}"><meta property="og:locale" content="es_MX">
    <meta property="og:title" content="${NAME}: material educativo listo para imprimir"><meta property="og:description" content="${esc(description)}">
    <meta property="og:url" content="${SITE}/"><meta name="twitter:card" content="summary">
    ${json(ld)}
  </head>`
}

const CSS = `:root{--bg:#fff;--text:#0c0a09;--muted:#6b6864;--surface:#f7f7f6;--border:#e7e5e2;--accent:#5b4cf0;--accent-soft:#eeecfe}
@media (prefers-color-scheme:dark){:root{--bg:#0b0b0a;--text:#f4f3f1;--muted:#a19e99;--surface:#151514;--border:#272725;--accent:#8b80ff;--accent-soft:#221f3d}}
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
footer{border-top:1px solid var(--border);padding:24px 16px;text-align:center;font-size:14px}`

const pages: string[] = ['/', '/material-educativo']
mkdirSync(new URL('material-educativo/', DIST), { recursive: true })
writeFileSync(new URL('material-educativo/index.html', DIST), hubPage())
for (const t of TOPICS) {
  writeFileSync(new URL(`material-educativo/${t.slug}.html`, DIST), topicPage(t))
  pages.push(topicHref(t))
}
const today = new Date().toISOString().slice(0, 10)
writeFileSync(new URL('sitemap.xml', DIST), `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${pages.map((p) => `  <url><loc>${SITE}${p === '/' ? '/' : p}</loc><lastmod>${today}</lastmod></url>`).join('\n')}
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
const index = new URL('index.html', DIST)
writeFileSync(index, readFileSync(index, 'utf8').replace('</head>', homeHead()))
console.log(`seo: ${pages.length} pages for ${SITE}`)
