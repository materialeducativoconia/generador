import { AbsoluteFill, Easing, Img, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion'
import { Glow, IPhone, Rise, isDark } from './startup'
import { LOOKS, SITE, type Capture, type ShelfBook, type VideoTome } from './spec'

/** The scenes every video is made of, each the real app animated with a real tome. `dur` is the scene's length in
 * frames: timings are fractions of it, so the director can give a scene 2 s or 8 s. Drawn with transforms, opacity
 * and plain boxes only, which the in-browser renderer (@remotion/web-renderer) paints exactly as the preview. */

export const INK = '#0c0a09'
export const ACCENT = '#5b4cf0'
export const SOFT = '#f4f2ff'
export const LINE = '#e7e5e2'
export const OK = '#2f8f4e'
export type Base = { dur: number; caption?: string; step?: number }
export type Palette = (typeof LOOKS)[keyof typeof LOOKS]

export function useUnit() {
  const { width, height } = useVideoConfig()
  const u = Math.min(width, height) / 1080
  // k: text on a phone screen is read at arm's length, so the vertical cut sets it larger.
  return { u, k: width >= height ? 1 : 1.3, wide: width > height, width, height }
}

export const ease = (f: number, from: number, to: number, out: [number, number] = [0, 1]) =>
  interpolate(f, [from, Math.max(from + 1, to)], out, { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.bezier(0.22, 1, 0.36, 1) })
export const fadeOut = (frame: number, dur: number) => ease(frame, dur - 10, dur, [1, 0])
export const typed = (text: string, frame: number, from: number, to: number) =>
  text.slice(0, Math.round(interpolate(frame, [from, Math.max(from + 1, to)], [0, text.length], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })))

function Pointer({ u, style }: { u: number; style: React.CSSProperties }) {
  return (
    <svg width={56 * u} height={56 * u} viewBox="0 0 24 24" style={{ position: 'absolute', zIndex: 5, ...style }}>
      <path d="M5 3l14 8-6 1.5L10 19z" fill={INK} stroke="#fff" strokeWidth="1.4" strokeLinejoin="round" />
    </svg>
  )
}

/** The line on screen; in a tutorial it carries its step number. */
export function Caption({ text, at = 6, step }: { text?: string; at?: number; step?: number }) {
  const frame = useCurrentFrame()
  const { u, wide } = useUnit()
  if (!text) return null
  const s = ease(frame, at, at + 12)
  return (
    <div style={{ position: 'absolute', left: 0, right: 0, bottom: (wide ? 48 : 150) * u, display: 'flex', flexDirection: 'column', alignItems: 'center',
      gap: 12 * u, opacity: s, transform: `translateY(${(1 - s) * 24 * u}px)`, zIndex: 6 }}>
      {step && <div style={{ background: ACCENT, color: '#fff', fontSize: 28 * u, fontWeight: 700, letterSpacing: '.12em', padding: `${8 * u}px ${20 * u}px`,
        borderRadius: 999 }}>PASO {step}</div>}
      <div style={{ background: INK, color: '#fff', fontSize: (wide ? 50 : 56) * u, fontWeight: 700, letterSpacing: '-0.02em',
        padding: `${18 * u}px ${34 * u}px`, borderRadius: 22 * u, maxWidth: '86%', textAlign: 'center', lineHeight: 1.15 }}>{text}</div>
    </div>
  )
}

/** Big words rising out of a mask one by one over a field of light, the last in the accent colour and underlined, the
 * whole line pushing in slowly: the hook, a tutorial's title, a key idea. */
export function TitleScene({ dur, caption = '', look = LOOKS.claro }: Base & { look?: Palette }) {
  const frame = useCurrentFrame()
  const { u, wide } = useUnit()
  const words = caption.split(/\s+/).filter(Boolean)
  const lastIn = 6 + (words.length - 1) * 3
  const under = ease(frame, lastIn + 8, lastIn + 22)
  const push = interpolate(frame, [0, dur], [1, 1.05], { extrapolateRight: 'clamp' })
  return (
    <Glow look={look} style={{ alignItems: 'center', justifyContent: 'center', padding: 90 * u, opacity: fadeOut(frame, dur) }}>
      <div style={{ fontSize: (wide ? 128 : 112) * u, fontWeight: 700, lineHeight: 1.06, letterSpacing: '-0.04em', textAlign: 'center', color: look.ink,
        maxWidth: wide ? 1500 * u : '84%', transform: `scale(${push})` }}>
        {words.map((w, i) => {
          const s = ease(frame, 4 + i * 3, 18 + i * 3)
          const end = i === words.length - 1
          return (
            <span key={i} style={{ position: 'relative', display: 'inline-block' }}>
              <Rise y={(1 - s) * 110} color={end ? look.accent : look.ink}>{w}</Rise>
              {end && <span style={{ position: 'absolute', left: '0.13em', right: '0.13em', bottom: '0.02em', height: 10 * u, borderRadius: 99, background: look.accent,
                transform: `scaleX(${under})`, transformOrigin: 'left', opacity: 0.9 }} />}
            </span>
          )
        })}
      </div>
    </Glow>
  )
}

export const parts = (text: string) => text.split('|').map((t) => t.trim()).filter(Boolean)

/** Two to four points landing one after another as cards over a field of light, each with its number: reasons, what
 * a book brings, a summary. */
export function ListScene({ dur, caption, step, text = '', look = LOOKS.claro }: Base & { text?: string; look?: Palette }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const { u, k, wide } = useUnit()
  const dark = isDark(look)
  const items = parts(text).slice(0, 4)
  const gap = Math.max(6, Math.min(16, (dur - 30) / Math.max(1, items.length)))
  return (
    <Glow look={look} style={{ alignItems: 'center', justifyContent: 'center', color: look.ink, opacity: fadeOut(frame, dur) }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 22 * u, width: wide ? '58%' : '84%', marginTop: (wide ? -60 : -160) * u }}>
        {items.map((item, i) => {
          const s = spring({ frame: frame - 6 - i * gap, fps, config: { damping: 16, mass: 0.7 } })
          const t = ease(frame, 9 + i * gap, 21 + i * gap)
          return (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 28 * u, opacity: Math.min(1, s * 1.4), transform: `translateY(${(1 - s) * 50 * u}px) scale(${0.96 + s * 0.04})`,
              padding: `${22 * u}px ${30 * u}px`, borderRadius: 28 * u, background: dark ? 'rgba(255,255,255,.07)' : '#fff',
              border: `${2 * u}px solid ${dark ? 'rgba(255,255,255,.13)' : LINE}`, boxShadow: dark ? undefined : `0 ${12 * u}px ${32 * u}px rgba(12,10,9,.07)` }}>
              <span style={{ flex: 'none', width: 70 * u * k, height: 70 * u * k, borderRadius: 20 * u * k, background: look.accent, color: dark ? INK : '#fff',
                display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 38 * u * k, fontWeight: 700, transform: `scale(${s})` }}>{i + 1}</span>
              <span style={{ fontSize: 58 * u * k, fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1.1, opacity: t, transform: `translateX(${(1 - t) * 24 * u}px)` }}>{item}</span>
            </div>
          )
        })}
      </div>
      <Caption text={caption} at={Math.min(dur - 20, 14 + items.length * gap)} step={step} />
    </Glow>
  )
}

/** The screen split in two: how it was done before, struck out, and how it is done with the app. */
export function VersusScene({ dur, caption, step, text = '', look = LOOKS.claro }: Base & { text?: string; look?: Palette }) {
  const frame = useCurrentFrame()
  const { u, k, wide } = useUnit()
  const [before = 'Antes', after = 'Con Jelyx'] = parts(text)
  const split = ease(frame, 0, 16)
  const second = ease(frame, dur * 0.4, dur * 0.4 + 14)
  const strike = ease(frame, dur * 0.25, dur * 0.25 + 12)
  const half = (dark: boolean, label: string, line: string, s: number, struck = 0): React.ReactNode => (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 24 * u, padding: 60 * u,
      background: dark ? look.bg : '#f4f2f0', color: dark ? look.ink : INK, opacity: s }}>
      <span style={{ fontSize: 30 * u * k, fontWeight: 700, letterSpacing: '.16em', color: dark ? look.accent : '#8a8580' }}>{label}</span>
      <span style={{ position: 'relative', fontSize: 70 * u * k, fontWeight: 700, letterSpacing: '-0.03em', textAlign: 'center', lineHeight: 1.08,
        transform: `translateY(${(1 - s) * 40 * u}px)` }}>{line}
        {struck > 0 && <span style={{ position: 'absolute', left: 0, top: '52%', height: 8 * u, width: `${struck * 100}%`, background: '#d9480f', borderRadius: 4 * u }} />}
      </span>
    </div>
  )
  return (
    <AbsoluteFill style={{ flexDirection: wide ? 'row' : 'column', opacity: fadeOut(frame, dur) }}>
      {half(false, 'ANTES', before, split, strike)}
      {half(true, 'AHORA', after, second)}
      <Caption text={caption} at={Math.min(dur - 20, dur * 0.4 + 18)} step={step} />
    </AbsoluteFill>
  )
}

/** One big number counting up to its value (5 min, 24 páginas) over a field of light, its unit set smaller beside it, a
 * bar sweeping under it, and what it means below. */
export function NumberScene({ dur, caption, step, text = '', look = LOOKS.claro }: Base & { text?: string; look?: Palette }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const { u, k } = useUnit()
  const m = text.match(/^(\D*)(\d+(?:[.,]\d+)?)(.*)$/)
  const target = m ? Number(m[2].replace(',', '.')) : 0
  const count = interpolate(frame, [4, Math.max(5, dur * 0.45)], [0, target], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic) })
  const num = m ? `${m[1]}${Number.isInteger(target) ? Math.round(count) : count.toFixed(1)}` : text
  const unit = m ? m[3].trim() : ''
  const pop = spring({ frame, fps, config: { damping: 15, mass: 0.6 } })
  const bar = ease(frame, dur * 0.45 - 6, dur * 0.45 + 10)
  const push = interpolate(frame, [0, dur], [1, 1.04], { extrapolateRight: 'clamp' })
  return (
    <Glow look={look} style={{ alignItems: 'center', justifyContent: 'center', opacity: fadeOut(frame, dur) }}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', marginTop: -120 * u, transform: `scale(${(0.82 + pop * 0.18) * push})`, opacity: Math.min(1, pop * 1.5) }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 34 * u, whiteSpace: 'nowrap' }}>
          <span style={{ fontSize: 250 * u * k, fontWeight: 700, letterSpacing: '-0.045em', paddingRight: '0.04em', lineHeight: 1, color: look.accent, fontVariantNumeric: 'tabular-nums' }}>{num}</span>
          {unit && <span style={{ fontSize: 96 * u * k, fontWeight: 700, letterSpacing: '-0.03em', color: look.ink, opacity: ease(frame, 8, 20) }}>{unit}</span>}
        </div>
        <div style={{ width: '100%', height: 12 * u, borderRadius: 99, marginTop: 18 * u, background: look.accent, transform: `scaleX(${bar})`, transformOrigin: 'left', opacity: 0.85 }} />
      </div>
      <Caption text={caption} at={Math.min(dur - 20, dur * 0.45)} step={step} />
    </Glow>
  )
}

/** The app's composer: the request typed letter by letter, then «Crear mi libro» pressed. */
export function ComposeScene({ dur, caption, step, text }: Base & { text: string }) {
  const frame = useCurrentFrame()
  const { u, k, wide } = useUnit()
  const shown = typed(text, frame, 12, dur * 0.66)
  const pointer = ease(frame, dur * 0.66, dur * 0.78)
  const press = frame > dur * 0.79 && frame < dur * 0.85 ? 0.94 : 1
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', background: SOFT, opacity: fadeOut(frame, dur) }}>
      <div style={{ width: (wide ? 1100 : 960) * u, transform: `translateY(${(1 - ease(frame, 0, 14)) * 60 * u}px)`, opacity: ease(frame, 0, 14),
        marginTop: caption && !wide ? -200 * u : 0 }}>
        <div style={{ fontSize: 46 * u * k, fontWeight: 700, letterSpacing: '-0.02em', marginBottom: 28 * u }}>¿Qué libro quieres crear?</div>
        <div style={{ background: '#fff', borderRadius: 32 * u, padding: 40 * u, boxShadow: `0 ${24 * u}px ${60 * u}px rgba(12,10,9,.12)`,
          border: `${2 * u}px solid ${LINE}`, minHeight: 300 * u, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div style={{ fontSize: 40 * u * k, lineHeight: 1.4, fontWeight: 500 }}>
            {shown}
            <span style={{ display: 'inline-block', width: 4 * u, height: 46 * u * k, background: ACCENT, marginLeft: 4 * u, verticalAlign: 'middle',
              opacity: Math.floor(frame / 8) % 2 === 0 || shown.length < text.length ? 1 : 0 }} />
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 36 * u, position: 'relative' }}>
            <div style={{ background: INK, color: '#fff', fontSize: 34 * u * k, fontWeight: 600, padding: `${22 * u}px ${40 * u}px`, borderRadius: 999,
              transform: `scale(${press})` }}>Crear mi libro</div>
            <Pointer u={u} style={{ right: 70 * u, top: 50 * u, opacity: pointer,
              transform: `translate(${(1 - pointer) * 260 * u}px, ${(1 - pointer) * 180 * u}px) scale(${press})` }} />
          </div>
        </div>
      </div>
      <Caption text={caption} step={step} at={10} />
    </AbsoluteFill>
  )
}

/** The Architect's plan: the book's sections arrive one after another. */
export function PlanScene({ dur, caption, step, tome }: Base & { tome: VideoTome }) {
  const frame = useCurrentFrame()
  const { u, k, wide } = useUnit()
  const sections = tome.sections.slice(0, wide ? 5 : 6)
  const gap = Math.min(9, (dur * 0.5) / Math.max(1, sections.length))
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: wide ? 'center' : 'flex-start', paddingTop: wide ? 0 : 300 * u, opacity: fadeOut(frame, dur) }}>
      <div style={{ width: (wide ? 1100 : 960) * u }}>
        <div style={{ fontSize: 28 * u * k, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', color: ACCENT, opacity: ease(frame, 0, 10) }}>
          {tome.kind}{tome.audience ? ` · ${tome.audience}` : ''}</div>
        <div style={{ fontSize: 60 * u * k, fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1.08, margin: `${14 * u}px 0 ${36 * u}px`,
          opacity: ease(frame, 2, 14) }}>{tome.title}</div>
        {sections.map((t, i) => {
          const s = ease(frame, 14 + i * gap, 28 + i * gap)
          return (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 24 * u, padding: `${20 * u}px ${26 * u}px`, marginBottom: 16 * u,
              background: '#fff', border: `${2 * u}px solid ${LINE}`, borderRadius: 22 * u, opacity: s, transform: `translateX(${(1 - s) * 80 * u}px)` }}>
              <span style={{ width: 56 * u, height: 56 * u, borderRadius: 16 * u, background: SOFT, color: ACCENT, fontWeight: 700, fontSize: 30 * u,
                display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 'none' }}>{i + 1}</span>
              <span style={{ fontSize: 36 * u * k, fontWeight: 600, lineHeight: 1.2 }}>{t}</span>
            </div>
          )
        })}
      </div>
      <Caption text={caption} step={step} at={20} />
    </AbsoluteFill>
  )
}

/** The cover being painted: a paper card wipes away from the art, then the book settles. */
export function CoverScene({ dur, caption, step, tome }: Base & { tome: VideoTome }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const { u, height, wide } = useUnit()
  const h = height * (wide ? 0.64 : 0.56)
  const pop = spring({ frame, fps, config: { damping: 16 } })
  const wipe = ease(frame, 18, dur * 0.55)
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', background: SOFT, opacity: fadeOut(frame, dur) }}>
      <div style={{ position: 'relative', width: h * (170 / 210), height: h, borderRadius: 18 * u, overflow: 'hidden', marginTop: wide ? -40 * u : -160 * u,
        transform: `scale(${0.85 + pop * 0.15}) rotate(${(1 - pop) * -4}deg)`, boxShadow: `0 ${30 * u}px ${70 * u}px rgba(12,10,9,.25)` }}>
        {tome.cover ? <Img src={tome.cover} crossOrigin="anonymous" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          : <div style={{ width: '100%', height: '100%', background: ACCENT }} />}
        <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: `${(1 - wipe) * 100}%`, background: '#fff' }} />
        <div style={{ position: 'absolute', left: 0, right: 0, bottom: `${(1 - wipe) * 100}%`, height: 10 * u, background: ACCENT, opacity: wipe < 1 ? 1 : 0 }} />
      </div>
      <Status u={u} wide={wide} busy={wipe < 1} label={wipe < 1 ? 'Pintando la portada…' : 'Portada lista'} />
      <Caption text={caption} step={step} at={24} />
    </AbsoluteFill>
  )
}

function Status({ u, wide, busy, label }: { u: number; wide: boolean; busy: boolean; label: string }) {
  return (
    <div style={{ position: 'absolute', top: (wide ? 50 : 150) * u, background: '#fff', borderRadius: 999, padding: `${14 * u}px ${28 * u}px`,
      fontSize: 30 * u, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 14 * u }}>
      <span style={{ width: 18 * u, height: 18 * u, borderRadius: 99, background: busy ? '#c98a12' : OK }} />{label}
    </div>
  )
}

/** The pages go by like a hand flipping the book: each slides in over the last, with its number. */
export function PagesScene({ dur, caption, step, tome }: Base & { tome: VideoTome }) {
  const frame = useCurrentFrame()
  const { u, height, wide } = useUnit()
  const pages = tome.pages.length ? tome.pages.slice(0, 6) : tome.cover ? [tome.cover] : []
  const each = Math.max(8, Math.floor((dur - 30) / Math.max(1, pages.length)))
  const h = height * (wide ? 0.64 : 0.54)
  const w = h * (170 / 210)
  const shown = Math.min(pages.length, Math.floor(frame / each) + 1)
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', opacity: fadeOut(frame, dur) }}>
      <div style={{ position: 'relative', width: w, height: h, marginTop: wide ? -40 * u : -160 * u }}>
        {pages.map((src, i) => {
          const s = ease(frame, i * each, i * each + 14)
          const tilt = ((i % 3) - 1) * 2.5
          return (
            <div key={i} style={{ position: 'absolute', inset: 0, borderRadius: 14 * u, overflow: 'hidden', background: '#fff',
              boxShadow: `0 ${20 * u}px ${50 * u}px rgba(12,10,9,.22)`, opacity: s,
              transform: `translateX(${(1 - s) * w * 1.1}px) rotate(${tilt * s + (1 - s) * 10}deg)` }}>
              <Img src={src} crossOrigin="anonymous" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            </div>
          )
        })}
      </div>
      <div style={{ position: 'absolute', top: (wide ? 50 : 150) * u, fontSize: 32 * u, fontWeight: 700, color: ACCENT, letterSpacing: '.08em' }}>
        PÁGINA {shown} DE {Math.max(pages.length, tome.sections.length * 2)}</div>
      <Caption text={caption} step={step} at={10} />
    </AbsoluteFill>
  )
}

/** The finished PDF: the book with its badges, ready to print. */
export function PdfScene({ dur, caption, step, tome }: Base & { tome: VideoTome }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const { u, height, wide } = useUnit()
  const h = height * (wide ? 0.6 : 0.42)
  const pop = spring({ frame, fps, config: { damping: 13 } })
  const chips = ['Solucionario', 'Tu nombre y tu logo', 'Listo para imprimir']
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', background: SOFT, opacity: fadeOut(frame, dur) }}>
      <div style={{ display: 'flex', flexDirection: wide ? 'row' : 'column', alignItems: 'center', gap: 56 * u, marginTop: wide ? -40 * u : -160 * u }}>
        <div style={{ position: 'relative', width: h * (170 / 210), height: h, transform: `scale(${0.7 + pop * 0.3})` }}>
          <div style={{ position: 'absolute', inset: 0, transform: `translate(${18 * u}px, ${14 * u}px)`, background: '#ddd8f6', borderRadius: 14 * u }} />
          <div style={{ position: 'absolute', inset: 0, borderRadius: 14 * u, overflow: 'hidden', boxShadow: `0 ${24 * u}px ${60 * u}px rgba(12,10,9,.25)` }}>
            {tome.cover && <Img src={tome.cover} crossOrigin="anonymous" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />}
          </div>
          <div style={{ position: 'absolute', right: -26 * u, top: -26 * u, background: OK, color: '#fff', borderRadius: 999,
            padding: `${14 * u}px ${24 * u}px`, fontSize: 30 * u, fontWeight: 700, transform: `scale(${spring({ frame: frame - 14, fps })})` }}>PDF ✓</div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 * u, alignItems: wide ? 'flex-start' : 'center' }}>
          {chips.map((c, i) => {
            const s = ease(frame, 20 + i * 8, 34 + i * 8)
            return <div key={c} style={{ background: '#fff', border: `${2 * u}px solid ${LINE}`, borderRadius: 999, padding: `${14 * u}px ${28 * u}px`,
              fontSize: 32 * u, fontWeight: 600, opacity: s, transform: `translateY(${(1 - s) * 20 * u}px)` }}>✓ {c}</div>
          })}
        </div>
      </div>
      <Caption text={caption} step={step} at={30} />
    </AbsoluteFill>
  )
}

/** The close: the brand, the call to action and the address. */
export function CtaScene({ dur, caption = '', look = LOOKS.noche }: Base & { look?: Palette }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const { u: u0, wide, k } = useUnit()
  const u = u0 * (wide ? 1 : k * 0.95)  // the close is read on a phone: larger on the vertical cut
  const field = isDark(look) ? look : LOOKS.noche  // the close is always the brand's dark field
  const s = spring({ frame, fps, config: { damping: 14 } })
  const words = caption.split(/\s+/).filter(Boolean)
  const pill = spring({ frame: frame - 18, fps, config: { damping: 12, mass: 0.6 } })
  const shine = interpolate(frame, [30, 52], [-60, 160], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
  const ring = ease(frame, 26, 56)
  const press = frame > dur * 0.62 && frame < dur * 0.62 + 5 ? 0.95 : 1
  const pointer = ease(frame, dur * 0.4, dur * 0.6)
  return (
    <Glow look={field} style={{ alignItems: 'center', justifyContent: 'center', color: '#fff', gap: 44 * u }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 24 * u, opacity: s, transform: `scale(${0.8 + s * 0.2})` }}>
        <svg width={110 * u} height={110 * u} viewBox="0 0 64 64">
          <rect width="64" height="64" rx="15" fill="#fff" />
          <path d="M40 15v20a11 11 0 0 1-22 0" fill="none" stroke={INK} strokeWidth="8.5" />
        </svg>
        <span style={{ fontSize: 76 * u, fontWeight: 700, letterSpacing: '-0.03em' }}>Jelyx Docs</span>
      </div>
      <div style={{ fontSize: (wide ? 72 : 66) * u, fontWeight: 700, textAlign: 'center', maxWidth: '84%', lineHeight: 1.1, letterSpacing: '-0.035em' }}>
        {words.map((w, i) => <Rise key={i} y={(1 - ease(frame, 8 + i * 2, 20 + i * 2)) * 110}>{w}</Rise>)}
      </div>
      <div style={{ position: 'relative', transform: `scale(${pill * press})`, opacity: Math.min(1, pill * 1.5) }}>
        <div style={{ position: 'absolute', inset: -16 * u * ring - 2, borderRadius: 999, border: `${3 * u}px solid ${field.accent}`, opacity: (1 - ring) * 0.9 }} />
        <div style={{ position: 'relative', overflow: 'hidden', background: '#fff', color: INK, borderRadius: 999, padding: `${20 * u}px ${46 * u}px`, fontSize: 42 * u,
          fontWeight: 700, letterSpacing: '-0.01em', boxShadow: `0 ${18 * u}px ${50 * u}px ${field.accent}88` }}>
          {SITE}
          <span style={{ position: 'absolute', top: 0, bottom: 0, left: `${shine}%`, width: '30%', transform: 'skewX(-20deg)',
            background: `linear-gradient(90deg, transparent, ${field.accent}33, transparent)` }} />
        </div>
        <Pointer u={u} style={{ left: '62%', top: '55%', opacity: pointer, transform: `translate(${(1 - pointer) * 160 * u}px, ${(1 - pointer) * 120 * u}px) scale(${press})` }} />
      </div>
    </Glow>
  )
}

const SWATCH = ['#5b4cf0', '#e8590c', '#2f8f4e', '#c2255c', '#1971c2', '#c98a12']

/** The kinds of book the app makes, each a real cover landing on the table; the one this video shows is lifted last. */
export function FormatsScene({ dur, caption, step, tome, shelf = [] }: Base & { tome: VideoTome; shelf?: ShelfBook[] }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const { u, k, wide } = useUnit()
  const books = shelf.slice(0, 6)
  const cols = wide ? Math.min(6, books.length) : Math.min(3, books.length)
  const cardW = wide ? Math.min(270, 1720 / Math.max(1, cols) - 30) * u : 300 * u
  const gap = Math.max(4, Math.min(9, (dur * 0.5) / Math.max(1, books.length)))
  const lift = ease(frame, dur * 0.62, dur * 0.62 + 14)
  const mine = books.findIndex((b) => b.label === tome.kind)
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', background: SOFT, opacity: fadeOut(frame, dur) }}>
      <div style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, ${cardW}px)`, gap: `${(wide ? 34 : 30) * u}px ${30 * u}px`,
        marginTop: (wide ? -80 : -170) * u }}>
        {books.map((b, i) => {
          const s = spring({ frame: frame - 4 - i * gap, fps, config: { damping: 13, mass: 0.7 } })
          const on = i === mine ? lift : 0
          const tilt = (i % 2 ? 1 : -1) * (1 - s) * 10
          return (
            <div key={b.genre} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 * u, opacity: s * (mine >= 0 && i !== mine ? 1 - lift * 0.55 : 1),
              transform: `translateY(${(1 - s) * 120 * u - on * 24 * u}px) rotate(${tilt}deg) scale(${1 + on * 0.1})`, zIndex: i === mine ? 2 : 1 }}>
              <div style={{ width: cardW, aspectRatio: '3 / 4', borderRadius: 12 * u, overflow: 'hidden', background: SWATCH[i % SWATCH.length],
                boxShadow: `0 ${18 * u}px ${40 * u}px rgba(12,10,9,${0.18 + on * 0.12})`, outline: on ? `${6 * u * on}px solid ${ACCENT}` : 'none' }}>
                {b.cover && <Img src={b.cover} crossOrigin="anonymous" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />}
              </div>
              <span style={{ fontSize: (wide ? 26 : 30) * u * (wide ? 1 : k * 0.85), fontWeight: 700, color: INK, textAlign: 'center', lineHeight: 1.1 }}>{b.label}</span>
            </div>
          )
        })}
      </div>
      <Caption text={caption} at={Math.min(dur - 20, dur * 0.4)} step={step} />
    </AbsoluteFill>
  )
}

/** The book's recurring characters: their model sheets land with their names, then the same faces walk through its pages. */
export function CharactersScene({ dur, caption, step, tome }: Base & { tome: VideoTome }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const { u, k, wide } = useUnit()
  const cast = (tome.cast ?? []).slice(0, 3)
  const pages = tome.pages.slice(0, 3)
  const half = cast.length && pages.length ? dur * 0.48 : cast.length ? dur : 0
  const swap = ease(frame, half, half + 14)  // the sheets become a row of portraits; the pages come in
  const sheetW = (wide ? 420 : 320) * u * (cast.length < 3 ? 1.25 : 1)
  const pageW = (wide ? 440 : 500) * u
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', background: SOFT, opacity: fadeOut(frame, dur) }}>
      {cast.length > 0 && (
        <div style={{ position: 'absolute', top: (wide ? 60 : 180) * u + (1 - swap) * (wide ? 120 : 300) * u, display: 'flex', gap: (30 - swap * 14) * u }}>
          {cast.map((c, i) => {
            const s = spring({ frame: frame - 4 - i * 7, fps, config: { damping: 14, mass: 0.7 } })
            const w = sheetW + ((wide ? 110 : 150) * u - sheetW) * swap
            return (
              <div key={c.name} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 * u, opacity: s, transform: `translateY(${(1 - s) * 80 * u}px)` }}>
                <div style={{ width: w, height: w, borderRadius: 18 * u + swap * 60 * u, overflow: 'hidden', background: '#fff',
                  boxShadow: `0 ${14 * u}px ${36 * u}px rgba(12,10,9,.16)`, border: `${4 * u}px solid #fff` }}>
                  <Img src={c.sheet} crossOrigin="anonymous" style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: swap > 0.5 ? '20% 15%' : 'center' }} />
                </div>
                <span style={{ background: INK, color: '#fff', borderRadius: 999, padding: `${8 * u}px ${20 * u}px`, fontSize: (34 - swap * 10) * u * k, fontWeight: 700 }}>{c.name}</span>
              </div>
            )
          })}
        </div>
      )}
      {pages.length > 0 && (
        <div style={{ position: 'absolute', top: wide ? 330 * u : (cast.length ? 470 : 360) * u, display: 'flex', flexDirection: wide ? 'row' : 'column',
          alignItems: 'center', gap: (wide ? 30 : 0) * u }}>
          {pages.map((src, i) => {
            const s = cast.length ? ease(frame, half + 6 + i * 6, half + 20 + i * 6) : spring({ frame: frame - 4 - i * 8, fps, config: { damping: 14 } })
            const tilt = [-4, 3, -2][i]
            return (
              <div key={i} style={{ width: pageW, aspectRatio: '4 / 3', borderRadius: 12 * u, overflow: 'hidden', background: '#fff', border: `${6 * u}px solid #fff`,
                boxShadow: `0 ${16 * u}px ${40 * u}px rgba(12,10,9,.2)`, opacity: s, marginTop: wide || i === 0 ? 0 : -50 * u,
                transform: `translateY(${(1 - s) * 90 * u}px) rotate(${tilt}deg)`, zIndex: i }}>
                <Img src={src} crossOrigin="anonymous" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              </div>
            )
          })}
        </div>
      )}
      <Caption text={caption} at={Math.min(dur - 20, Math.max(12, half))} step={step} />
    </AbsoluteFill>
  )
}

/** A real screenshot of the app in a phone (tall) or a laptop (wide), as Screen Studio films it: the device lands, the
 * camera glides in to the marked point, the cursor comes and clicks, and the camera holds there. */
export function ScreenScene({ dur, caption, step, capture, focus = 0, look = LOOKS.claro }: Base & { capture?: Capture; focus?: number; look?: Palette }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const { u, wide, width: W, height: H } = useUnit()
  const dark = look.bg !== '#ffffff'
  const backdrop = dark ? `radial-gradient(circle at 30% 20%, ${look.accent}55, transparent 60%), ${look.bg}`
    : 'radial-gradient(circle at 30% 15%, #e4e0ff, transparent 55%), radial-gradient(circle at 80% 90%, #ffe7d6, transparent 50%), #f7f6f4'
  if (!capture?.url) {
    return <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', background: backdrop, color: dark ? '#fff' : INK, fontSize: 48 * u }}>
      Elige una captura para esta escena</AbsoluteFill>
  }
  const laptop = capture.width > capture.height
  const ratio = capture.width / capture.height
  // The device fits the frame above the caption.
  const maxW = W * (laptop ? (wide ? 0.72 : 0.9) : (wide ? 0.4 : 0.74))
  const maxH = H * (wide ? 0.72 : 0.68)
  const bezel = laptop ? 14 * u : maxW * 0.042  // a phone's titanium rim and black bezel
  let sw = maxW - bezel * 2
  let sh = sw / ratio
  const base = laptop ? 34 * u : 0
  if (sh + bezel * 2 + base > maxH) { sh = maxH - bezel * 2 - base; sw = sh * ratio }
  const dw = sw + bezel * 2
  const dh = sh + bezel * 2
  const left = (W - dw) / 2
  const top = (H - dh - base) / 2 - (wide ? 30 : 90) * u
  const point = capture.focus[Math.min(focus, capture.focus.length - 1)] ?? { x: 0.5, y: 0.5, label: '' }
  const px = left + bezel + point.x * sw
  const py = top + bezel + point.y * sh
  // The camera: in from 15 % to 45 % of the scene, to a zoom that still shows some context around the point.
  const land = spring({ frame, fps, config: { damping: 16, mass: 0.8 } })
  const e = ease(frame, dur * 0.15, dur * 0.45)
  // A laptop's screen is zoomed until about half of it fills the frame; a phone less, so its frame still shows.
  const Z = laptop ? Math.min(2, Math.max(1.4, (0.95 * W) / (sw * 0.6))) : (wide ? 1.7 : 1.45)
  const z = 1 + (Z - 1) * e
  const cx = W / 2
  const cy = H * (wide ? 0.42 : 0.4)
  const tx = px + e * (cx - px) - px * z
  const ty = py + e * (cy - py) - py * z
  // The cursor glides to the point and clicks.
  const glide = ease(frame, dur * 0.35, dur * 0.6)
  const click = frame - dur * 0.62
  const press = click > 0 && click < 8 ? 0.85 : 1
  const ring = click > 0 ? ease(click, 0, 16) : 0
  const startX = left + dw * 0.92
  const startY = top + dh * 0.95
  const curX = startX + (px - startX) * glide
  const curY = startY + (py - startY) * glide
  const cs = 64 * u / Math.sqrt(z)
  return (
    <AbsoluteFill style={{ background: backdrop, overflow: 'hidden' }}>
      <div style={{ position: 'absolute', inset: 0, transformOrigin: '0 0', transform: `translate(${tx}px, ${ty}px) scale(${z})` }}>
        {laptop ? (
          <div style={{ position: 'absolute', left, top, width: dw, height: dh, borderRadius: 18 * u, background: '#141414',
            boxShadow: `0 ${40 * u}px ${100 * u}px rgba(12,10,9,.28)`, opacity: land, transform: `translateY(${(1 - land) * 80 * u}px) scale(${0.94 + land * 0.06})` }}>
            <div style={{ position: 'absolute', left: bezel, top: bezel, width: sw, height: sh, borderRadius: 6 * u, overflow: 'hidden', background: '#fff' }}>
              <Img src={capture.url} crossOrigin="anonymous" style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
            </div>
            <div style={{ position: 'absolute', left: -dw * 0.08, right: -dw * 0.08, top: dh, height: base, borderRadius: `0 0 ${24 * u}px ${24 * u}px`,
              background: 'linear-gradient(#d6d3d1, #a8a29e)' }}>
              <div style={{ width: dw * 0.16, height: 10 * u, margin: '0 auto', borderRadius: `0 0 ${10 * u}px ${10 * u}px`, background: '#8a8580' }} />
            </div>
          </div>
        ) : (
          <div style={{ position: 'absolute', left, top, opacity: land, transform: `translateY(${(1 - land) * 80 * u}px) scale(${0.94 + land * 0.06})` }}>
            <IPhone w={dw} h={dh} edge={bezel} statusBar={false}>
              <Img src={capture.url} crossOrigin="anonymous" style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
            </IPhone>
          </div>
        )}
        {ring > 0 && ring < 1 && <div style={{ position: 'absolute', left: px - 50 * u * ring / Math.sqrt(z), top: py - 50 * u * ring / Math.sqrt(z),
          width: 100 * u * ring / Math.sqrt(z), height: 100 * u * ring / Math.sqrt(z), borderRadius: 999, border: `${4 * u / Math.sqrt(z)}px solid ${ACCENT}`, opacity: 1 - ring }} />}
        <svg width={cs} height={cs} viewBox="0 0 24 24" style={{ position: 'absolute', left: curX - cs * 0.2, top: curY - cs * 0.12, opacity: ease(frame, dur * 0.3, dur * 0.36),
          transform: `scale(${press})`, transformOrigin: '20% 12%', filter: 'drop-shadow(0 2px 3px rgba(0,0,0,.3))' }}>
          <path d="M5 3l14 8-6 1.5L10 19z" fill={INK} stroke="#fff" strokeWidth="1.4" strokeLinejoin="round" />
        </svg>
      </div>
      <Caption text={caption} at={Math.min(dur - 20, dur * 0.45)} step={step} />
    </AbsoluteFill>
  )
}

/* ——— The page editor, as the app draws it today: a window of the app floating on the launch backdrop, with the strip
 * of pages, the page or the printed cover, and the form beside it (below it on a phone's vertical cut). ——— */

type Box = { left: number; top: number; width: number; height: number }

/** Where the editor's parts sit, in the frame: the window, the strip, the plate and the form. Wide: strip | plate |
 * form; square: the same, narrower; tall: strip on top, plate, form below. Every box stays above the caption. */
function useEditorLayout() {
  const { u, k, wide, width, height } = useUnit()
  const tall = height > width
  const chrome = 56 * u
  const head = 58 * u
  if (!tall) {
    const win: Box = wide ? { left: 60 * u, top: 50 * u, width: width - 120 * u, height: 860 * u } : { left: 40 * u, top: 40 * u, width: width - 80 * u, height: 850 * u }
    const top = win.top + chrome + head + 10 * u
    const plateH = wide ? 700 * u : 610 * u
    const thumb = wide ? 110 * u : 84 * u
    const strip: Box = { left: win.left + (wide ? 40 : 28) * u, top, width: thumb, height: plateH }
    const plate: Box = { left: strip.left + thumb + (wide ? 40 : 26) * u, top, width: plateH * (170 / 210), height: plateH }
    const formLeft = plate.left + plate.width + (wide ? 50 : 26) * u
    const form: Box = { left: formLeft, top, width: Math.min(760 * u, win.left + win.width - formLeft - (wide ? 40 : 26) * u), height: plateH }
    return { u, k, wide, tall, width, height, win, chrome, head, strip, plate, form, thumb, row: false }
  }
  const win: Box = { left: 40 * u, top: 90 * u, width: width - 80 * u, height: 1500 * u }
  const strip: Box = { left: win.left + 40 * u, top: win.top + chrome + head + 14 * u, width: win.width - 80 * u, height: 0 }
  const thumb = (strip.width - 5 * 16 * u) / 6
  strip.height = thumb * (210 / 170) + 34 * u
  const plateH = 600 * u
  const plateW = plateH * (170 / 210)
  const plate: Box = { left: (width - plateW) / 2, top: strip.top + strip.height + 22 * u, width: plateW, height: plateH }
  const form: Box = { left: strip.left, top: plate.top + plateH + 26 * u, width: strip.width, height: win.top + win.height - (plate.top + plateH + 26 * u) - 30 * u }
  return { u, k, wide, tall, width, height, win, chrome, head, strip, plate, form, thumb, row: true }
}

const at = (b: Box): React.CSSProperties => ({ position: 'absolute', left: b.left, top: b.top, width: b.width, height: b.height })

/** The centre of the strip's thumbnail `i` (0 is the cover), as fractions of the frame. */
function thumbAt(L: ReturnType<typeof useEditorLayout>, i: number): [number, number] {
  const h = L.thumb * (210 / 170)
  const gap = 16 * L.u
  const x = L.row ? L.strip.left + i * (L.thumb + gap) + L.thumb / 2 : L.strip.left + L.thumb / 2
  const y = L.row ? L.strip.top + h / 2 : L.strip.top + i * (h + 30 * L.u + gap) + h / 2
  return [x / L.width, y / L.height]
}

/** The app's window: its address bar, «← Volver al tomo» and the editor's heading with the book's name; the
 * camera drifting in slowly, as in the launch scenes. */
function EditorShell({ children, dur, caption, step, tome, look = LOOKS.claro }: Base & { children: React.ReactNode; tome: VideoTome; look?: Palette }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const L = useEditorLayout()
  const { u, win, chrome, head } = L
  const land = spring({ frame, fps, config: { damping: 18 } })
  const drift = interpolate(frame, [0, dur], [1, 1.035])
  return (
    <Glow look={look} style={{ opacity: fadeOut(frame, dur) }}>
      <div style={{ position: 'absolute', inset: 0, transform: `scale(${drift * (0.96 + land * 0.04)})`, opacity: Math.min(1, land * 1.6) }}>
        <div style={{ ...at(win), borderRadius: 26 * u, background: '#fafaf9', overflow: 'hidden', boxShadow: `0 ${40 * u}px ${110 * u}px rgba(12,10,9,.3)`,
          border: `${2 * u}px solid rgba(255,255,255,.6)` }}>
          <div style={{ height: chrome, display: 'flex', alignItems: 'center', gap: 12 * u, padding: `0 ${22 * u}px`, background: '#fff', borderBottom: `${2 * u}px solid ${LINE}` }}>
            {['#ff5f57', '#febc2e', '#28c840'].map((c) => <span key={c} style={{ width: 16 * u, height: 16 * u, borderRadius: 99, background: c, flex: 'none' }} />)}
            <span style={{ marginLeft: 14 * u, flex: 1, maxWidth: 560 * u, height: 34 * u, borderRadius: 10 * u, background: '#f1f0ee', color: '#78716c', fontSize: 20 * u,
              display: 'flex', alignItems: 'center', padding: `0 ${14 * u}px`, whiteSpace: 'nowrap', overflow: 'hidden' }}>{SITE}/app/tomos/editor</span>
          </div>
          <div style={{ height: head, display: 'flex', alignItems: 'center', gap: 22 * u, padding: `0 ${(L.tall ? 40 : 30) * u}px`, whiteSpace: 'nowrap', overflow: 'hidden' }}>
            <span style={{ fontSize: 20 * u, color: '#78716c', fontWeight: 600 }}>← Volver al tomo</span>
            <span style={{ fontSize: 18 * u, fontWeight: 700, letterSpacing: '.14em', color: ACCENT }}>EDITOR DE PÁGINAS</span>
            <span style={{ fontSize: 26 * u, fontWeight: 700, letterSpacing: '-0.02em', color: INK, overflow: 'hidden', textOverflow: 'ellipsis' }}>{tome.title}</span>
          </div>
        </div>
        {children}
      </div>
      <Caption text={caption} step={step} at={8} />
    </Glow>
  )
}

/** The strip of pages, the printed cover first, each with its number under it; `on` is the one open. */
function Strip({ tome, on, appear = 1 }: { tome: VideoTome; on: number; appear?: number }) {
  const L = useEditorLayout()
  const { u, k, strip, thumb, row } = L
  const fit = row ? 6 : Math.max(1, Math.floor((strip.height + 16 * u) / (thumb * (210 / 170) + 30 * u + 16 * u)))
  const thumbs = [tome.cover, ...tome.pages].filter(Boolean).slice(0, fit) as string[]
  return (
    <div style={{ ...at(strip), display: 'flex', flexDirection: row ? 'row' : 'column', gap: 16 * u }}>
      {thumbs.map((src, i) => (
        <div key={i} style={{ width: thumb, flex: 'none', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 * u, opacity: ease(appear * 30, i * 3, i * 3 + 10) }}>
          <div style={{ width: thumb, height: thumb * (210 / 170), borderRadius: 8 * u, overflow: 'hidden', background: SOFT,
            outline: `${(i === on ? 5 : 0) * u}px solid ${ACCENT}`, outlineOffset: 3 * u, boxShadow: `0 ${4 * u}px ${12 * u}px rgba(12,10,9,.15)` }}>
            <Img src={src} crossOrigin="anonymous" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          </div>
          <span style={{ fontSize: 16 * u * Math.min(k, 1.15), fontWeight: 600, color: i === on ? ACCENT : '#78716c', lineHeight: 1.2 }}>{i === 0 ? 'Portada' : i}</span>
        </div>
      ))}
    </div>
  )
}

/** A plate with its words over the picture: the question card, the facts and the find strip. The cover is the real
 * printed one, its name line and age badge fading out as they are switched off. */
function Plate({ tome, qTop = 4, notes, hidden = [], fresh, freshIn = 0, image, dragging = false, cover = false, nameLine = 1, age = 1 }: {
  tome: VideoTome; qTop?: number; notes?: string[]; hidden?: number[]; fresh?: string; freshIn?: number; image?: string; dragging?: boolean
  cover?: boolean; nameLine?: number; age?: number
}) {
  const { u, k, plate } = useEditorLayout()
  const p = tome.plate
  const src = image ?? (cover ? tome.cover : p?.image ?? tome.pages[0] ?? tome.cover) ?? undefined
  const facts = notes ?? p?.notes ?? []
  const f = 0.42 * k
  const fill: React.CSSProperties = { position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }
  return (
    <div style={{ ...at(plate), borderRadius: 10 * u, overflow: 'hidden', background: SOFT, boxShadow: `0 ${16 * u}px ${44 * u}px rgba(12,10,9,.2)` }}>
      {cover && tome.covers ? (
        <>
          <Img src={tome.covers.full} crossOrigin="anonymous" style={fill} />
          <Img src={tome.covers.noName} crossOrigin="anonymous" style={{ ...fill, opacity: 1 - nameLine }} />
          <Img src={tome.covers.bare} crossOrigin="anonymous" style={{ ...fill, opacity: 1 - age }} />
        </>
      ) : src && <Img src={src} crossOrigin="anonymous" style={fill} />}
      {cover ? !tome.covers && (
        <>
          <div style={{ position: 'absolute', left: '8%', bottom: '14%', width: '46%', borderBottom: `${3 * u}px solid #fff`, paddingBottom: 26 * u * f,
            color: '#fff', fontSize: 30 * u * f, fontWeight: 700, letterSpacing: '.06em', opacity: nameLine }}>NOMBRE:</div>
          <div style={{ position: 'absolute', right: '6%', bottom: '6%', width: 120 * u * f * 1.6, height: 120 * u * f * 1.6, borderRadius: 999, background: '#e8590c',
            color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 30 * u * f * 1.4, fontWeight: 800, opacity: age,
            transform: `scale(${0.6 + age * 0.4}) rotate(8deg)` }}>{(tome.audience || '4–7 años').replace(' años', '')}<br />años</div>
        </>
      ) : (
        <>
          <div style={{ position: 'absolute', left: '5%', right: '5%', top: `${qTop}%`, background: '#fff', borderRadius: 18 * u * f, padding: `${22 * u * f}px ${28 * u * f}px`,
            boxShadow: `0 ${6 * u}px ${16 * u}px rgba(0,0,0,.18)`, outline: dragging ? `${3 * u}px dashed ${ACCENT}` : 'none', outlineOffset: 4 * u }}>
            <div style={{ fontSize: 46 * u * f, fontWeight: 700, lineHeight: 1.1, color: INK }}>{p?.question ?? tome.title}</div>
            {p?.answer && <div style={{ fontSize: 28 * u * f, lineHeight: 1.35, marginTop: 10 * u * f, color: '#44403c' }}>{p.answer.slice(0, 140)}</div>}
          </div>
          {[...facts.slice(0, 3), ...(fresh ? [fresh] : [])].map((n, i) => {
            const isFresh = fresh !== undefined && i === Math.min(3, facts.length)
            const gone = hidden.includes(i) ? 0 : 1
            const show = isFresh ? freshIn : gone
            return (
              <div key={i} style={{ position: 'absolute', [i % 2 ? 'right' : 'left']: '3%', top: `${44 + Math.floor(i / 2) * 18}%`, maxWidth: '34%',
                background: '#fff', borderLeft: `${6 * u * f}px solid ${ACCENT}`, borderRadius: 10 * u * f, padding: `${12 * u * f}px ${16 * u * f}px`,
                fontSize: 26 * u * f, fontWeight: 600, lineHeight: 1.25, color: INK, opacity: show, transform: `scale(${0.8 + show * 0.2})`,
                boxShadow: `0 ${4 * u}px ${10 * u}px rgba(0,0,0,.15)` }}>{n}</div>
            )
          })}
          {p?.find && <div style={{ position: 'absolute', left: '5%', right: '5%', bottom: '3%', background: '#fff', borderRadius: 999,
            padding: `${12 * u * f}px ${24 * u * f}px`, fontSize: 26 * u * f, fontWeight: 600, color: INK }}>
            <b style={{ color: ACCENT }}>Observa y encuentra: </b>{p.find.slice(0, 70)}</div>}
        </>
      )}
    </div>
  )
}

// The form's sizes, fixed so the pointer lands on what it presses in every cut.
const PAD = 30
const GAP = 16
function useForm() {
  const L = useEditorLayout()
  const s = L.u * Math.min(L.k, 1.2)
  return { ...L, s, label: 30 * s, input: 58 * s, check: 44 * s, button: 60 * s }
}

/** A panel of the editor's form, beside or under the plate, with the page's place in the book on top. */
function Form({ children, where }: { children: React.ReactNode; where?: string }) {
  const { u, s, form } = useForm()
  return (
    <div style={{ ...at(form), background: '#fff', border: `${2 * u}px solid ${LINE}`, borderRadius: 22 * u, padding: PAD * u,
      display: 'flex', flexDirection: 'column', gap: GAP * u, overflow: 'hidden' }}>
      {where && <div style={{ height: 30 * s, fontSize: 20 * s, color: '#a8a29e', fontWeight: 500, flex: 'none' }}>{where}</div>}
      {children}
    </div>
  )
}

function Label({ children }: { children: React.ReactNode }) {
  const { s, label } = useForm()
  return <div style={{ height: label, flex: 'none', fontSize: 22 * s, fontWeight: 600, color: '#57534e', display: 'flex', alignItems: 'center' }}>{children}</div>
}

function Input({ children, focus = false, tall = 1 }: { children: React.ReactNode; focus?: boolean; tall?: number }) {
  const { u, s, input } = useForm()
  return (
    <div style={{ minHeight: input, height: tall > 1 ? input * tall : undefined, flex: 'none', border: `${2 * u}px solid ${focus ? ACCENT : LINE}`, borderRadius: 12 * u, padding: `${12 * s}px ${16 * s}px`,
      fontSize: 22 * s, lineHeight: 1.4, color: INK, boxShadow: focus ? `0 0 0 ${4 * u}px ${ACCENT}22` : undefined, overflow: 'hidden', boxSizing: 'border-box' }}>{children}</div>
  )
}

function Caret() {
  const { u, s } = useForm()
  return <span style={{ display: 'inline-block', width: 3 * u, height: 26 * s, background: ACCENT, marginLeft: 3 * u, verticalAlign: 'middle' }} />
}

function Button({ children, primary = false, pressed = false }: { children: React.ReactNode; primary?: boolean; pressed?: boolean }) {
  const { u, s, button } = useForm()
  return (
    <div style={{ alignSelf: 'flex-start', height: button, flex: 'none', display: 'flex', alignItems: 'center', background: primary ? ACCENT : '#fff', color: primary ? '#fff' : INK,
      border: `${2 * u}px solid ${primary ? ACCENT : LINE}`, borderRadius: 14 * u, padding: `0 ${26 * s}px`, fontSize: 22 * s, fontWeight: 700,
      transform: `scale(${pressed ? 0.94 : 1})`, boxSizing: 'border-box' }}>{children}</div>
  )
}

/** A pointer that glides from one spot of the frame to another (fractions of the width and height). */
function Glide({ frame, from, to, a, b, press }: { frame: number; from: [number, number]; to: [number, number]; a: number; b: number; press?: boolean }) {
  const { u, width, height } = useUnit()
  const t = ease(frame, a, b)
  return <Pointer u={u} style={{ left: (from[0] + (to[0] - from[0]) * t) * width, top: (from[1] + (to[1] - from[1]) * t) * height,
    transform: `scale(${press ? 0.85 : 1})` }} />
}

/** A point of the form: `y` pixels down from the form's top, `x` from its left. */
const inForm = (F: ReturnType<typeof useForm>, x: number, y: number): [number, number] =>
  [(F.form.left + x) / F.width, (F.form.top + PAD * F.u + y) / F.height]

const where = (tome: VideoTome) => `Página 2 · ${tome.sections[0] ?? tome.kind}`

/** The page editor opens: the strip of pages arrives and a page is chosen. */
export function EditorOpenScene({ dur, caption, step, tome, look }: Base & { tome: VideoTome; look?: Palette }) {
  const frame = useCurrentFrame()
  const L = useEditorLayout()
  const pick = frame > dur * 0.5 ? 2 : -1
  const open = ease(frame, dur * 0.52, dur * 0.66)
  return (
    <EditorShell dur={dur} caption={caption} step={step} tome={tome} look={look}>
      <Strip tome={tome} on={pick} appear={Math.min(1, frame / 30)} />
      <div style={{ position: 'absolute', inset: 0, opacity: open, transform: `translateY(${(1 - open) * 30}px)` }}>
        <Plate tome={tome} />
        <Form where={where(tome)}>
          <Label>Pregunta</Label>
          <Input>{tome.plate?.question ?? tome.title}</Input>
          <Label>Datos</Label>
          {(tome.plate?.notes ?? []).slice(0, 2).map((n, i) => <Input key={i}>{n}</Input>)}
        </Form>
      </div>
      {open < 0.01 && <div style={{ ...at(L.plate), borderRadius: 10 * L.u, border: `${3 * L.u}px dashed ${LINE}` }} />}
      <Glide frame={frame} from={[0.75, 0.82]} to={thumbAt(L, 2)} a={dur * 0.15} b={dur * 0.45} press={frame > dur * 0.46 && frame < dur * 0.52} />
    </EditorShell>
  )
}

/** «Mover textos»: the question card is dragged down the page, its outline dashed while it moves. */
export function EditorMoveScene({ dur, caption, step, tome, look }: Base & { tome: VideoTome; look?: Palette }) {
  const frame = useCurrentFrame()
  const F = useForm()
  const { u, s, plate, width, height } = F
  const move = ease(frame, dur * 0.3, dur * 0.7)
  const dragging = frame > dur * 0.25 && frame < dur * 0.72
  const qTop = 4 + move * 52
  const grab: [number, number] = [(plate.left + plate.width * 0.5) / width, (plate.top + plate.height * (qTop / 100 + 0.04)) / height]
  const chip = (on: boolean, label: string) => (
    <div style={{ background: on ? SOFT : '#fff', color: on ? ACCENT : INK, border: `${2 * u}px solid ${on ? ACCENT : LINE}`, borderRadius: 999,
      padding: `${10 * s}px ${20 * s}px`, fontSize: 20 * s, fontWeight: on ? 700 : 500, whiteSpace: 'nowrap' }}>{label}</div>
  )
  return (
    <EditorShell dur={dur} caption={caption} step={step} tome={tome} look={look}>
      <Strip tome={tome} on={2} />
      <Plate tome={tome} qTop={qTop} dragging={dragging} />
      <Form where={where(tome)}>
        <Label>Vista</Label>
        <div style={{ display: 'flex', gap: 10 * u, flexWrap: 'wrap' }}>{chip(true, 'Mover textos')}{chip(false, 'Vista de impresión')}</div>
        <div style={{ fontSize: 20 * s, color: '#78716c', lineHeight: 1.45 }}>Arrastra la pregunta, los datos o el reto con el dedo o el cursor; lo que escribes aquí se ve al momento.</div>
        {move > 0.98 && <div style={{ fontSize: 20 * s, color: ACCENT, fontWeight: 600 }}>Volver al acomodo automático</div>}
      </Form>
      {frame < dur * 0.3
        ? <Glide frame={frame} from={[0.85, 0.8]} to={grab} a={0} b={dur * 0.25} />
        : <Pointer u={u} style={{ left: grab[0] * width, top: grab[1] * height, transform: `scale(${dragging ? 0.85 : 1})` }} />}
    </EditorShell>
  )
}

/** A fact removed with its ✕ and a new one added with «+ Añadir dato», typed and appearing on the plate. */
export function EditorFactsScene({ dur, caption, step, tome, text, look }: Base & { tome: VideoTome; text: string; look?: Palette }) {
  const frame = useCurrentFrame()
  const F = useForm()
  const { u, s, form } = F
  const facts = (tome.plate?.notes ?? ['La Luna refleja la luz del Sol.', 'Tarda 28 días en dar una vuelta.']).slice(0, 2)
  const removed = frame > dur * 0.3
  const gone = ease(frame, dur * 0.3, dur * 0.38)
  const adding = frame > dur * 0.5
  const typedFact = typed(text, frame, dur * 0.55, dur * 0.85)
  const top = (30 * s + GAP * u) + (F.label + GAP * u)  // under «Página…» and «Datos»
  const xAt = inForm(F, form.width - PAD * u - 30 * s, top + (F.input + GAP * u) + F.input / 2)
  const addAt = inForm(F, 90 * s, top + (F.input + GAP * u) * 2 - (F.input + GAP * u) * gone + F.button / 2)
  return (
    <EditorShell dur={dur} caption={caption} step={step} tome={tome} look={look}>
      <Strip tome={tome} on={2} />
      <Plate tome={tome} notes={facts} hidden={removed ? [1] : []} fresh={adding ? typedFact || ' ' : undefined} freshIn={ease(frame, dur * 0.85, dur * 0.92)} />
      <Form where={where(tome)}>
        <Label>Datos</Label>
        {facts.map((n, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12 * u, flex: 'none', opacity: i === 1 ? 1 - gone : 1,
            height: i === 1 && removed ? F.input * (1 - gone) : F.input, marginBottom: i === 1 && removed ? -GAP * u * gone : 0 }}>
            <div style={{ flex: 1, minWidth: 0 }}><Input><span style={{ whiteSpace: 'nowrap' }}>{n}</span></Input></div>
            <span style={{ width: 44 * s, textAlign: 'center', fontSize: 24 * s, fontWeight: 700, color: '#78716c', flex: 'none' }}>✕</span>
          </div>
        ))}
        {adding ? <Input focus>{typedFact}<Caret /></Input> : <Button pressed={frame > dur * 0.46}>+ Añadir dato</Button>}
      </Form>
      {frame < dur * 0.32
        ? <Glide frame={frame} from={[0.8, 0.9]} to={xAt} a={0} b={dur * 0.26} press={frame > dur * 0.26} />
        : <Glide frame={frame} from={xAt} to={addAt} a={dur * 0.34} b={dur * 0.45} press={frame > dur * 0.45 && frame < dur * 0.5} />}
    </EditorShell>
  )
}

/** «Repintar esta ilustración»: what to change is typed, the button pressed, the picture painted again. */
export function EditorRepaintScene({ dur, caption, step, tome, text, look }: Base & { tome: VideoTome; text: string; look?: Palette }) {
  const frame = useCurrentFrame()
  const F = useForm()
  const { u, s, plate } = F
  const ask = typed(text, frame, dur * 0.12, dur * 0.45)
  const pressed = frame > dur * 0.52 && frame < dur * 0.58
  const painting = ease(frame, dur * 0.58, dur * 0.66) * (1 - ease(frame, dur * 0.82, dur * 0.9))
  const swapped = frame > dur * 0.8
  const next = tome.pages.find((p) => p !== tome.plate?.image) ?? tome.art ?? tome.cover ?? undefined
  const box = F.input * 2
  const button = inForm(F, 120 * s, 30 * s + GAP * u + F.label + GAP * u + box + GAP * u + F.button / 2)
  return (
    <EditorShell dur={dur} caption={caption} step={step} tome={tome} look={look}>
      <Strip tome={tome} on={2} />
      <Plate tome={tome} image={swapped ? next : undefined} />
      <div style={{ ...at(plate), borderRadius: 10 * u, background: `rgba(255,255,255,${0.75 * painting})`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ opacity: painting, background: '#fff', borderRadius: 999, padding: `${14 * s}px ${24 * s}px`, fontSize: 22 * s, fontWeight: 600,
          display: 'flex', gap: 12 * u, alignItems: 'center', boxShadow: `0 ${8 * u}px ${20 * u}px rgba(12,10,9,.15)` }}>
          <span style={{ width: 16 * u, height: 16 * u, borderRadius: 99, background: '#c98a12' }} />Pintando la ilustración de nuevo…</div>
      </div>
      <Form where={where(tome)}>
        <Label>Repintar esta ilustración</Label>
        <Input focus tall={2}>{ask || <span style={{ color: '#a8a29e' }}>Ej.: más luz de mañana</span>}<Caret /></Input>
        <Button pressed={pressed}>Repintar (1 crédito)</Button>
      </Form>
      <Glide frame={frame} from={[0.9, 0.95]} to={button} a={dur * 0.4} b={dur * 0.52} press={pressed} />
    </EditorShell>
  )
}

/** The cover in the editor, the real printed one: the name line and the age badge switched off with a click each. */
export function EditorCoverScene({ dur, caption, step, tome, look }: Base & { tome: VideoTome; look?: Palette }) {
  const frame = useCurrentFrame()
  const F = useForm()
  const { u, s } = F
  const nameOff = ease(frame, dur * 0.35, dur * 0.42)
  const ageOff = ease(frame, dur * 0.65, dur * 0.72)
  const kicker = !F.tall  // the vertical cut has room for the switches only
  const first = 30 * s + GAP * u + (kicker ? F.label + GAP * u + F.input + GAP * u : 0) + F.label + GAP * u
  const row = (i: number) => inForm(F, 22 * s, first + i * (F.check + GAP * u) + F.check / 2)
  const box = (on: boolean) => (
    <span style={{ width: 30 * s, height: 30 * s, borderRadius: 7 * u, flex: 'none', border: `${3 * u}px solid ${on ? ACCENT : '#a8a29e'}`, background: on ? ACCENT : '#fff',
      color: '#fff', fontSize: 20 * s, display: 'flex', alignItems: 'center', justifyContent: 'center', boxSizing: 'border-box' }}>{on ? '✓' : ''}</span>
  )
  const options: [string, string, boolean][] = [['Línea «Nombre»', 'para que el niño escriba su nombre', nameOff < 0.5],
    ['«Elaborado por»', 'tu firma y tu logo', true], ['Sello de edad', 'el círculo con las edades', ageOff < 0.5]]
  return (
    <EditorShell dur={dur} caption={caption} step={step} tome={tome} look={look}>
      <Strip tome={tome} on={0} />
      <Plate tome={tome} cover nameLine={1 - nameOff} age={1 - ageOff} />
      <Form where="Portada">
        {kicker && <><Label>Texto sobre el título</Label><Input>{tome.kind}</Input></>}
        <Label>Qué más lleva</Label>
        {options.map(([l, hint, on]) => (
          <div key={l} style={{ height: F.check, flex: 'none', display: 'flex', alignItems: 'center', gap: 14 * u, fontSize: 21 * s, fontWeight: 600, color: INK,
            whiteSpace: 'nowrap', overflow: 'hidden' }}>{box(on)}{l}<span style={{ color: '#a8a29e', fontWeight: 400 }}>· {hint}</span></div>
        ))}
      </Form>
      {frame < dur * 0.45
        ? <Glide frame={frame} from={[0.85, 0.9]} to={row(0)} a={dur * 0.1} b={dur * 0.33} press={frame > dur * 0.33 && frame < dur * 0.4} />
        : <Glide frame={frame} from={row(0)} to={row(2)} a={dur * 0.45} b={dur * 0.62} press={frame > dur * 0.62 && frame < dur * 0.7} />}
    </EditorShell>
  )
}

/** «Guardar cambios»: saved, and the next PDF carries every change. */
export function EditorSaveScene({ dur, caption, step, tome, look }: Base & { tome: VideoTome; look?: Palette }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const F = useForm()
  const { u, s } = F
  const pressed = frame > dur * 0.35 && frame < dur * 0.42
  const saved = frame > dur * 0.42
  const pop = spring({ frame: frame - dur * 0.55, fps, config: { damping: 12 } })
  const button = inForm(F, 110 * s, 30 * s + GAP * u + F.label + GAP * u + F.input + GAP * u + F.button / 2)
  return (
    <EditorShell dur={dur} caption={caption} step={step} tome={tome} look={look}>
      <Strip tome={tome} on={2} />
      <Plate tome={tome} qTop={56} />
      <Form where={where(tome)}>
        <Label>Pregunta</Label>
        <Input>{tome.plate?.question ?? tome.title}</Input>
        <Button primary pressed={pressed}>{saved ? 'Guardado' : 'Guardar cambios'}</Button>
        <div style={{ fontSize: 20 * s, color: OK, fontWeight: 600, opacity: saved ? 1 : 0 }}>Guardado. El próximo PDF ya lo incluye.</div>
        <div style={{ alignSelf: 'flex-start', background: OK, color: '#fff', borderRadius: 999, padding: `${10 * s}px ${22 * s}px`, fontSize: 22 * s,
          fontWeight: 700, transform: `scale(${pop})` }}>PDF ✓</div>
      </Form>
      <Glide frame={frame} from={[0.85, 0.9]} to={button} a={dur * 0.1} b={dur * 0.33} press={pressed} />
    </EditorShell>
  )
}
