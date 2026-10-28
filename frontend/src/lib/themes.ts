import { useEffect } from 'react'
import type { Design } from './types'

/** Mirrors backend/app/themes.py so the web preview matches the PDF. */
type Theme = { head: string; headWeight: number; body: string; opener: string; radius: number; fonts: string }

export const THEMES: Record<Design['theme'], Theme> = {
  juego: { head: 'Fredoka', headWeight: 600, body: 'Andika', opener: 'blob', radius: 22, fonts: 'Fredoka:wght@400..700' },
  cuaderno: { head: 'Patrick Hand', headWeight: 400, body: 'Andika', opener: 'tape', radius: 6, fonts: 'Patrick+Hand' },
  editorial: { head: 'Fraunces', headWeight: 700, body: 'Nunito', opener: 'numeral', radius: 6, fonts: 'Fraunces:opsz,wght@9..144,300..800&family=Nunito:wght@400..900' },
  metodo: { head: 'Baloo 2', headWeight: 800, body: 'Nunito', opener: 'badge', radius: 14, fonts: 'Baloo+2:wght@400..800&family=Nunito:wght@400..900' },
  ciencia: { head: 'Lexend', headWeight: 700, body: 'Lexend', opener: 'bar', radius: 10, fonts: 'Lexend:wght@300..800' },
  clasico: { head: 'Nunito', headWeight: 900, body: 'Andika', opener: 'plain', radius: 14, fonts: 'Nunito:wght@400..900' },
}

export const ORNAMENTS: Record<Design['ornament'], string> = {
  estrellas: '<path d="M12 2l2.9 6.1 6.6.8-4.9 4.6 1.3 6.5L12 16.8 6.1 20l1.3-6.5L2.5 8.9l6.6-.8z"/>',
  notas: '<path d="M9 18a3 3 0 1 1-2-2.8V5l12-2v11a3 3 0 1 1-2-2.8V6.3L9 7.6z"/>',
  hojas: '<path d="M5 19c0-8 5-14 15-15-1 10-7 15-15 15z"/><path fill="none" stroke="#fff" stroke-width="1.4" stroke-linecap="round" d="M7 17l8-8"/>',
  puntos: '<circle cx="5" cy="12" r="2.6"/><circle cx="12" cy="12" r="2.6"/><circle cx="19" cy="12" r="2.6"/>',
  formas: '<circle cx="6" cy="7" r="4"/><rect x="13" y="3" width="8" height="8" rx="1.5"/><path d="M3 21l5-8 5 8z"/><path d="M17 13l4 4-4 4-4-4z"/>',
  ninguno: '',
}

/** Heading fonts a library style may use: family and its Google Fonts query, as bundled for the PDF. */
const HEAD_FONTS: Record<NonNullable<Design['head_font']>, [number, string]> = {
  Fredoka: [600, 'Fredoka:wght@400..700'], 'Patrick Hand': [400, 'Patrick+Hand'], Fraunces: [700, 'Fraunces:wght@300..800'],
  'Baloo 2': [800, 'Baloo+2:wght@400..800'], Lexend: [700, 'Lexend:wght@300..800'], Nunito: [900, 'Nunito:wght@400..900'],
  Pacifico: [400, 'Pacifico'], Sniglet: [800, 'Sniglet:wght@800'],
}
export const FRAMES: Record<NonNullable<Design['frame']>, string> = {
  none: 'none', line: '1.5px solid', rounded: '2px solid', dashed: '2px dashed', double: '4px double',
}

function themeOf(d: Design): Theme {
  const t = THEMES[d.theme]
  if (!d.head_font) return t
  const [headWeight, font] = HEAD_FONTS[d.head_font]
  return { ...t, head: d.head_font, headWeight, fonts: `${t.fonts}&family=${font}` }
}

const DEFAULT: Design = { theme: 'clasico', palette: ['#F5F3FF', '#1C1917', '#4F46E5'], ornament: 'ninguno' }

function mix(a: string, b: string, t: number) {
  const ch = (h: string, i: number) => parseInt(h.slice(1 + i * 2, 3 + i * 2), 16)
  return '#' + [0, 1, 2].map((i) => Math.round(ch(a, i) + (ch(b, i) - ch(a, i)) * t).toString(16).padStart(2, '0')).join('')
}

/** CSS variables for a themed sheet, computed like the PDF's tints. */
export function themeVars(design: Design | null | undefined) {
  const d = design ?? DEFAULT
  const t = themeOf(d)
  const [bg, ink, accent] = d.palette
  return {
    theme: t,
    ornament: ORNAMENTS[d.ornament],
    style: {
      '--t-head': `'${t.head}', 'Geist', sans-serif`, '--t-body': `'${t.body}', 'Andika', sans-serif`, '--t-head-w': t.headWeight,
      '--t-ink': ink, '--t-accent': accent, '--t-tint': mix(bg, accent, 0.28), '--t-soft': mix('#ffffff', accent, 0.09),
      '--t-radius': `${t.radius}px`,
      '--t-frame': d.frame && d.frame !== 'none' ? `${FRAMES[d.frame]} ${ink}` : 'none',
    } as React.CSSProperties,
  }
}

const loaded = new Set<string>()

/** Theme fonts load on demand from Google Fonts, the same OFL families the PDF bundles. */
export function useThemeFonts(design: Design | null | undefined) {
  const fonts = themeOf(design ?? DEFAULT).fonts
  useEffect(() => {
    if (loaded.has(fonts)) return
    loaded.add(fonts)
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = `https://fonts.googleapis.com/css2?family=${fonts}&display=swap`
    document.head.appendChild(link)
  }, [fonts])
}
