import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion'
import { Caption, ease, fadeOut, type Base, type Palette } from './scenes'
import { LOOKS, type Motion, type MotionIcon } from './spec'
import { Glow, Rise, isDark } from './startup'

/* Motion graphics: shapes, icons and lines that explain an idea without the app. The director (DeepSeek) describes
 * each one from the team's request (its style, its items with an icon and a label, its colours) and these draw it.
 * Transforms, opacity, gradients and plain boxes only, which the in-browser renderer paints exactly as the preview. */

export const MOTION_ICONS: Record<MotionIcon, string> = {
  sparkle: 'M12 3l2.4 5.6L20 11l-5.6 2.4L12 19l-2.4-5.6L4 11l5.6-2.4z',
  book: 'M4 5a2 2 0 0 1 2-2h12v16H6a2 2 0 0 0-2 2zM4 19V5M8 7h6',
  pencil: 'M4 20l4-1 11-11-3-3L5 16zM14 6l3 3',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2',
  star: 'M12 3l2.8 5.8 6.2.9-4.5 4.4 1 6.2L12 17.4 6.5 20.3l1-6.2L3 9.7l6.2-.9z',
  heart: 'M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z',
  check: 'M5 12l5 5 9-10',
  palette: 'M12 3a9 9 0 1 0 0 18c1 0 1.5-.8 1.5-1.6 0-1.2-1-1.4-1-2.4 0-.8.7-1.5 1.5-1.5H16a5 5 0 0 0 5-5c0-4-4-7.5-9-7.5zM7.5 11h.01M10 7h.01M15 7.5h.01',
  download: 'M12 4v11m0 0l-4-4m4 4l4-4M5 20h14',
  people: 'M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm8 0a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM2 20c0-3.3 2.7-6 6-6s6 2.7 6 6M14 14.3c.6-.2 1.3-.3 2-.3 3.3 0 6 2.7 6 6',
  idea: 'M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z',
  rocket: 'M5 15c-1 1-1.5 4-1.5 4.5S6.5 19 9 18M9 15l-3-3c1.5-5 6-9 13-9 0 7-4 11.5-9 13zM14.5 9.5h.01',
  puzzle: 'M4 8h4a2 2 0 1 1 4 0h4v4a2 2 0 1 1 0 4v4H4z',
  globe: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3 12h18M12 3c2.5 2.5 3.5 5.5 3.5 9s-1 6.5-3.5 9c-2.5-2.5-3.5-5.5-3.5-9s1-6.5 3.5-9z',
  apple: 'M12 7c-1.5-1-5-1.5-6.5 1.5S5 17 8 20c1.5 1.3 2.5.5 4 .5s2.5.8 4-.5c3-3 4-8.5 2.5-11.5S13.5 6 12 7zM12 7c0-2 1-3.5 3-4',
  music: 'M9 18V5l11-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM20 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z',
  leaf: 'M5 19c0-9 6-14 15-14 0 9-5 15-14 15M5 19l7-7',
  calculator: 'M6 3h12v18H6zM9 7h6M9 12h.01M12 12h.01M15 12h.01M9 16h.01M12 16h.01M15 16h.01',
  school: 'M3 9l9-5 9 5-9 5zM7 11v5c3 2 7 2 10 0v-5',
  printer: 'M7 9V3h10v6M7 17H4v-8h16v8h-3M7 14h10v7H7z',
}
export const MOTION_STYLES = { burst: 'Estallido', flow: 'Proceso', orbit: 'Órbita', stats: 'Datos', grid: 'Tarjetas' } as const

type Props = Base & { text?: string; look?: Palette; motion?: Motion }

/** The colours a graphic is drawn with: the director's, filled out with the look's accent and two warm ones. */
const swatch = (motion: Motion | undefined, look: Palette) => {
  const own = motion?.colors ?? []
  return [...own, look.accent, '#ff7a59', '#ffb703', '#2f8f4e'].slice(0, Math.max(3, own.length))
}

function Bubble({ icon, color, size, s = 1 }: { icon: MotionIcon; color: string; size: number; s?: number }) {
  return (
    <div style={{ width: size, height: size, borderRadius: '50%', background: color, display: 'flex', alignItems: 'center', justifyContent: 'center',
      transform: `scale(${s})`, opacity: Math.min(1, s * 1.4), boxShadow: `0 ${size * 0.12}px ${size * 0.3}px ${color}55`, flex: 'none' }}>
      <svg width={size * 0.52} height={size * 0.52} viewBox="0 0 24 24">
        <path d={MOTION_ICONS[icon] ?? MOTION_ICONS.sparkle} fill="none" stroke="#fff" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  )
}

/** The scene's line in big type, word by word out of a mask, the last word in the accent. */
function Headline({ text, at, size, ink, accent }: { text: string; at: number; size: number; ink: string; accent: string }) {
  const frame = useCurrentFrame()
  const words = text.split(/\s+/).filter(Boolean)
  return (
    <div style={{ fontSize: size, fontWeight: 700, letterSpacing: '-0.04em', lineHeight: 1.05, color: ink, textAlign: 'center' }}>
      {words.map((w, i) => <Rise key={i} y={(1 - ease(frame, at + i * 3, at + 12 + i * 3)) * 110} color={i === words.length - 1 && words.length > 1 ? accent : ink}>{w}</Rise>)}
    </div>
  )
}

/** A motion graphic as the director described it. */
export function MotionScene({ dur, caption, step, text = '', look = LOOKS.claro, motion }: Props) {
  const frame = useCurrentFrame()
  const items = (motion?.items ?? []).slice(0, 6)
  const p = { dur, text, look, items, colors: swatch(motion, look) }
  const style = motion?.style ?? 'burst'
  return (
    <Glow look={look} style={{ opacity: fadeOut(frame, dur) }}>
      {style === 'flow' ? <Flow {...p} /> : style === 'orbit' ? <Orbit {...p} /> : style === 'stats' ? <Stats {...p} />
        : style === 'grid' ? <Grid {...p} /> : <Burst {...p} />}
      <Caption text={caption} at={Math.min(dur - 20, 24)} step={step} />
    </Glow>
  )
}

type Inner = { dur: number; text: string; look: Palette; items: Motion['items']; colors: string[] }

function useMotionUnit() {
  const { width: W, height: H } = useVideoConfig()
  const u = Math.min(W, H) / 1080
  return { u, W, H, wide: W > H, tall: H > W * 1.2 }
}

/** The items in a row (a column on a phone) joined by a line drawn from one to the next: a process. */
function Flow({ dur, text, look, items, colors }: Inner) {
  const frame = useCurrentFrame()
  const { u, W, H, wide, tall } = useMotionUnit()
  const ink = look.ink
  const n = Math.max(1, items.length)
  const span = Math.max(20, dur * 0.6)
  const reach = interpolate(frame, [10, 10 + span], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
  const size = (tall ? 150 : 170) * u
  const horizontal = !tall
  const len = horizontal ? W * 0.78 : H * 0.52
  const x0 = horizontal ? (W - len) / 2 : W * 0.2
  const y0 = horizontal ? H * (wide ? 0.56 : 0.54) : H * 0.3
  const at = (i: number) => n === 1 ? 0.5 : i / (n - 1)
  return (
    <AbsoluteFill>
      <div style={{ position: 'absolute', top: H * (tall ? 0.12 : 0.16), left: '6%', right: '6%' }}>
        <Headline text={text} at={2} size={(tall ? 96 : 90) * u} ink={ink} accent={look.accent} />
      </div>
      <div style={{ position: 'absolute', left: horizontal ? x0 : x0 + size / 2 - 4 * u, top: horizontal ? y0 + size / 2 - 4 * u : y0,
        width: horizontal ? len * reach : 8 * u, height: horizontal ? 8 * u : len * reach, borderRadius: 8 * u,
        background: `linear-gradient(${horizontal ? 90 : 180}deg, ${colors.join(', ')})` }} />
      {items.map((it, i) => {
        const s = spring({ frame: frame - 10 - at(i) * span, fps: 30, config: { damping: 11, mass: 0.6 } })
        const cx = horizontal ? x0 + at(i) * len - size / 2 : x0
        const cy = horizontal ? y0 : y0 + at(i) * len - size / 2
        return (
          <div key={i} style={{ position: 'absolute', left: horizontal ? cx : cx, top: cy, display: 'flex', flexDirection: horizontal ? 'column' : 'row',
            alignItems: 'center', gap: 22 * u, width: horizontal ? size : W * 0.7 }}>
            <Bubble icon={it.icon} color={colors[i % colors.length]} size={size} s={s} />
            <span style={{ fontSize: (tall ? 50 : 38) * u, fontWeight: 700, color: ink, textAlign: horizontal ? 'center' : 'left', lineHeight: 1.1,
              width: horizontal ? len / n + 40 * u : undefined, opacity: s, transform: `translateY(${(1 - s) * 20 * u}px)` }}>{it.label}</span>
          </div>
        )
      })}
    </AbsoluteFill>
  )
}

/** The line in a circle at the centre and the items in bubbles turning around it: what something brings together. */
function Orbit({ text, look, items, colors }: Inner) {
  const frame = useCurrentFrame()
  const { u, W, H, tall } = useMotionUnit()
  const core = spring({ frame, fps: 30, config: { damping: 13 } })
  const R = Math.min(W, H) * (tall ? 0.36 : 0.33)
  const cx = W / 2
  const cy = H * (tall ? 0.45 : 0.5)
  const turn = frame * 0.5
  const size = 130 * u
  return (
    <AbsoluteFill>
      <div style={{ position: 'absolute', left: cx - R, top: cy - R, width: R * 2, height: R * 2, borderRadius: '50%',
        border: `${3 * u}px dashed ${look.accent}55`, transform: `rotate(${turn}deg) scale(${core})` }} />
      <div style={{ position: 'absolute', left: cx - R * 0.58, top: cy - R * 0.58, width: R * 1.16, height: R * 1.16, borderRadius: '50%',
        background: `radial-gradient(circle at 35% 30%, ${colors[0]}, ${colors[1] ?? colors[0]})`, transform: `scale(${core})`,
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 30 * u, boxSizing: 'border-box' }}>
        <Headline text={text} at={6} size={Math.min(78 * u, (R * 1.0) / Math.max(4, ...text.split(/\s+/).map((w) => w.length)) / 0.55)} ink="#fff" accent="#fff" />
      </div>
      {items.map((it, i) => {
        const s = spring({ frame: frame - 12 - i * 6, fps: 30, config: { damping: 12, mass: 0.6 } })
        const a = ((turn + (360 / items.length) * i - 90) * Math.PI) / 180
        const x = cx + Math.cos(a) * R
        const y = cy + Math.sin(a) * R
        return (
          <div key={i} style={{ position: 'absolute', left: x - size / 2, top: y - size / 2, width: size, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 * u }}>
            <Bubble icon={it.icon} color={colors[(i + 1) % colors.length]} size={size} s={s} />
            <span style={{ whiteSpace: 'nowrap', fontSize: (tall ? 40 : 32) * u, fontWeight: 700, color: isDark(look) ? '#fff' : look.ink,
              background: isDark(look) ? 'rgba(0,0,0,.35)' : 'rgba(255,255,255,.85)', padding: `${6 * u}px ${14 * u}px`, borderRadius: 999, opacity: s }}>{it.label}</span>
          </div>
        )
      })}
    </AbsoluteFill>
  )
}

const SHAPES = ['50%', '22%', '50% 50% 50% 0']  // circle, rounded square, leaf

/** Coloured shapes burst out of the centre and settle around the line; the items as chips: an impact, an idea. */
function Burst({ text, look, items, colors }: Inner) {
  const frame = useCurrentFrame()
  const { u, W, H, tall } = useMotionUnit()
  const cx = W / 2
  const cy = H * (tall ? 0.42 : 0.46)
  const out = spring({ frame, fps: 30, config: { damping: 9, mass: 0.8 } })
  return (
    <AbsoluteFill>
      {Array.from({ length: 14 }, (_, i) => {
        const a = (i / 14) * Math.PI * 2 + 0.3
        const r = Math.min(W, H) * (0.3 + (i % 3) * 0.09) * out
        const size = (40 + (i % 4) * 22) * u
        return <div key={i} style={{ position: 'absolute', left: cx + Math.cos(a) * r - size / 2, top: cy + Math.sin(a) * r * (tall ? 1.3 : 0.9) - size / 2,
          width: size, height: size, borderRadius: SHAPES[i % SHAPES.length], background: colors[i % colors.length], opacity: 0.85 * out,
          transform: `rotate(${frame * (i % 2 ? 2 : -1.5) + i * 30}deg) scale(${out})` }} />
      })}
      <div style={{ position: 'absolute', left: '8%', right: '8%', top: cy - 110 * u, display: 'flex', justifyContent: 'center' }}>
        <div style={{ background: isDark(look) ? 'rgba(8,7,26,.72)' : 'rgba(255,255,255,.9)', borderRadius: 40 * u, padding: `${28 * u}px ${40 * u}px`,
          transform: `scale(${0.8 + out * 0.2})`, opacity: Math.min(1, out * 1.5) }}>
          <Headline text={text} at={8} size={(tall ? 104 : 96) * u} ink={look.ink === '#ffffff' && !isDark(look) ? '#0c0a09' : look.ink} accent={look.accent} />
        </div>
      </div>
      <div style={{ position: 'absolute', left: '6%', right: '6%', top: cy + (tall ? 200 : 140) * u, display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: 18 * u }}>
        {items.map((it, i) => {
          const s = spring({ frame: frame - 18 - i * 5, fps: 30, config: { damping: 12 } })
          return (
            <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 12 * u, background: colors[i % colors.length], color: '#fff', borderRadius: 999,
              padding: `${10 * u}px ${24 * u}px ${10 * u}px ${12 * u}px`, fontSize: (tall ? 40 : 34) * u, fontWeight: 700, transform: `scale(${s})`, opacity: s }}>
              <Bubble icon={it.icon} color="rgba(255,255,255,.22)" size={56 * u} />{it.label}
            </span>
          )
        })}
      </div>
    </AbsoluteFill>
  )
}

const amount = (v: string) => { const m = v.replace(',', '.').match(/[\d.]+/); return m ? parseFloat(m[0]) : NaN }

/** Bars growing to their value, each with its icon and label, the number counting up: data. */
function Stats({ dur, text, look, items, colors }: Inner) {
  const frame = useCurrentFrame()
  const { u, W, H, tall } = useMotionUnit()
  const values = items.map((it, i) => (Number.isFinite(amount(it.value)) ? amount(it.value) : items.length - i))
  const top = Math.max(...values, 1)
  const ink = isDark(look) ? '#fff' : look.ink
  const row = Math.min((tall ? 190 : 150) * u, (H * 0.55) / Math.max(1, items.length))
  return (
    <AbsoluteFill>
      <div style={{ position: 'absolute', top: H * (tall ? 0.12 : 0.1), left: '6%', right: '6%' }}>
        <Headline text={text} at={2} size={(tall ? 92 : 80) * u} ink={ink} accent={look.accent} />
      </div>
      <div style={{ position: 'absolute', left: W * 0.08, right: W * 0.08, top: H * (tall ? 0.32 : 0.3), display: 'grid', gap: row * 0.25 }}>
        {items.map((it, i) => {
          const g = ease(frame, 10 + i * 6, 10 + i * 6 + dur * 0.4)
          const shown = it.value ? it.value.replace(/[\d.,]+/, (n) => {
            const full = amount(n)
            return Number.isFinite(full) ? (Number.isInteger(full) ? String(Math.round(full * g)) : (full * g).toFixed(1)) : n
          }) : ''
          return (
            <div key={i} style={{ display: 'grid', gap: 10 * u, opacity: ease(frame, 6 + i * 6, 14 + i * 6) }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 14 * u, fontSize: (tall ? 42 : 34) * u, fontWeight: 700, color: ink }}>
                <Bubble icon={it.icon} color={colors[i % colors.length]} size={(tall ? 64 : 54) * u} />{it.label}
              </span>
              <div style={{ position: 'relative', height: row * 0.32, borderRadius: 999, background: isDark(look) ? 'rgba(255,255,255,.1)' : '#ece9f6' }}>
                <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${(values[i] / top) * 100 * g}%`, borderRadius: 999,
                  background: colors[i % colors.length], minWidth: row * 0.32 }} />
                {shown && <span style={{ position: 'absolute', right: 0, top: '50%', transform: `translate(0, -50%)`, paddingRight: 18 * u,
                  fontSize: row * 0.24, fontWeight: 800, color: ink }}>{shown}</span>}
              </div>
            </div>
          )
        })}
      </div>
    </AbsoluteFill>
  )
}

/** The items on cards that come in as a wave, shapes turning slowly behind: a list of benefits. */
function Grid({ text, look, items, colors }: Inner) {
  const frame = useCurrentFrame()
  const { u, W, H, tall, wide } = useMotionUnit()
  const cols = wide ? Math.min(3, items.length) : 2
  const gw = W * (wide ? 0.78 : 0.86)
  const gap = 24 * u
  const cw = (gw - gap * (cols - 1)) / cols
  const ch = (tall ? 300 : 230) * u
  const dark = isDark(look)
  return (
    <AbsoluteFill>
      {[0, 1, 2].map((i) => (
        <div key={i} style={{ position: 'absolute', width: W * (0.4 + i * 0.12), height: W * (0.4 + i * 0.12), left: `${[70, -10, 60][i]}%`, top: `${[5, 55, 80][i]}%`,
          borderRadius: SHAPES[i], border: `${4 * u}px solid ${colors[i % colors.length]}44`, transform: `translate(-50%, -50%) rotate(${frame * (i % 2 ? -0.4 : 0.5)}deg)` }} />
      ))}
      <div style={{ position: 'absolute', top: H * (tall ? 0.13 : 0.1), left: '6%', right: '6%' }}>
        <Headline text={text} at={2} size={(tall ? 92 : 80) * u} ink={dark ? '#fff' : look.ink} accent={look.accent} />
      </div>
      <div style={{ position: 'absolute', left: (W - gw) / 2, top: H * (tall ? 0.33 : 0.34), width: gw, display: 'grid', gridTemplateColumns: `repeat(${cols}, ${cw}px)`, gap }}>
        {items.map((it, i) => {
          const s = spring({ frame: frame - 8 - ((i % cols) + Math.floor(i / cols)) * 5, fps: 30, config: { damping: 13, mass: 0.7 } })
          return (
            <div key={i} style={{ height: ch, borderRadius: 32 * u, padding: 28 * u, boxSizing: 'border-box', display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
              background: dark ? 'rgba(255,255,255,.08)' : '#fff', border: `${2 * u}px solid ${dark ? 'rgba(255,255,255,.14)' : '#e7e5e2'}`,
              boxShadow: dark ? undefined : `0 ${14 * u}px ${36 * u}px rgba(12,10,9,.08)`, opacity: s, transform: `translateY(${(1 - s) * 80 * u}px) rotate(${(1 - s) * (i % 2 ? 4 : -4)}deg)` }}>
              <Bubble icon={it.icon} color={colors[i % colors.length]} size={(tall ? 96 : 80) * u} />
              <span style={{ fontSize: (tall ? 44 : 36) * u, fontWeight: 700, letterSpacing: '-0.02em', lineHeight: 1.1, color: dark ? '#fff' : look.ink }}>{it.label}</span>
            </div>
          )
        })}
      </div>
    </AbsoluteFill>
  )
}
