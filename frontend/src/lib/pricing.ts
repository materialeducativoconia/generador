// The plans as the public pages show them. The source of truth is backend/app/plans.py; keep the two in step.
export const PUBLIC_PLANS = [
  { key: 'docente', label: 'Docente', price: 9, credits: 150, for: 'Para tu grupo',
    features: ['150 créditos al mes (≈ 5 cuadernillos)', 'PDF listo para imprimir', 'Uso en el aula', 'Tomos de hasta 24 páginas'] },
  { key: 'creador', label: 'Creador', price: 24, credits: 500, for: 'Para vender tu material',
    features: ['500 créditos al mes', 'Licencia comercial, sin marca de agua', 'Word editable y edición para imprenta', 'Tu identidad editorial, estilos y logo'] },
  { key: 'editorial', label: 'Editorial', price: 69, credits: 1500, for: 'Para escuelas y editoriales',
    features: ['1,500 créditos al mes', 'Hasta 20 identidades y 30 estilos', 'Tomos de hasta 200 páginas', '10 tomos generándose a la vez'] },
] as const
export const TRIAL_CREDITS = 0  // no free credits: the free preview (cover, index and sample) is the trial
