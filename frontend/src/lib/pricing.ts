// The plans as the public pages show them. The source of truth is backend/app/plans.py; keep the two in step.
export const PUBLIC_PLANS = [
  { key: 'docente', label: 'Docente', price: 9, credits: 150, for: 'Para tu grupo',
    flags: { watermark: true, commercial: false, word: false, print_edition: false, styles: 0, identities: 0, logo: false, premium: false, max_pages: 24, concurrent: 1, seats: 1 },
    features: ['150 créditos al mes (≈ 5 cuadernillos)', 'PDF listo para imprimir', 'Uso en el aula', 'Tomos de hasta 24 páginas'] },
  { key: 'creador', label: 'Creador', price: 24, credits: 500, for: 'Para vender tu material',
    flags: { watermark: false, commercial: true, word: true, print_edition: true, styles: 5, identities: 1, logo: true, premium: false, max_pages: 100, concurrent: 3, seats: 1 },
    features: ['500 créditos al mes', 'Licencia comercial, sin marca de agua', 'Word editable y edición para imprenta', 'Tu identidad editorial, estilos y logo'] },
  { key: 'editorial', label: 'Editorial', price: 69, credits: 1500, for: 'Para escuelas y editoriales',
    flags: { watermark: false, commercial: true, word: true, print_edition: true, styles: 30, identities: 20, logo: true, premium: true, max_pages: 200, concurrent: 10, seats: 3 },
    features: ['1,500 créditos al mes', 'Hasta 20 identidades y 30 estilos', 'Tomos de hasta 200 páginas', '10 tomos generándose a la vez'] },
] as const
export const FREE_PREVIEW_PAGES = 4  // app.plans.FREE_PREVIEW_PAGES: a visitor's preview, pages and sections
export const TRIAL_CREDITS = 0  // no free credits: the free preview (cover, index and sample) is the trial

/** The public plans in the shape /api/billing returns, so the landing and the plan page share one card. */
export const PUBLIC_PLAN_INFO = PUBLIC_PLANS.map((p) => ({ key: p.key, label: p.label, price_usd: p.price, credits: p.credits, ...p.flags }))
