import { AbsoluteFill, Img, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion'
import { ACCENT, Caption, INK, LINE, OK, SOFT, ease, fadeOut, parts, typed, useUnit, type Base, type Palette } from './scenes'
import { LOOKS, SITE, type VideoTome } from './spec'

/* The scenes of a startup's launch video: the app in an iPhone, a laptop and a phone together, a magnifying zoom on a
 * page, kinetic type, a bento of features, the AI chat that makes the book and the logo reveal. 2D transforms,
 * opacity, gradients and plain boxes only, which the in-browser renderer paints exactly as the preview. */

export const isDark = (look: Palette) => look.bg !== '#ffffff'

/** A deep (or light) field with two soft glows drifting, as the launch videos of the AI apps. */
export function Glow({ look, children, style }: { look: Palette; children?: React.ReactNode; style?: React.CSSProperties }) {
  const frame = useCurrentFrame()
  const a = 28 + Math.sin(frame / 40) * 8
  const b = 72 + Math.cos(frame / 50) * 8
  const bg = isDark(look)
    ? `radial-gradient(circle at ${a}% 22%, ${look.accent}66, transparent 46%), radial-gradient(circle at ${b}% 82%, #ff7a5966, transparent 42%), ${look.bg}`
    : `radial-gradient(circle at ${a}% 18%, #e2dcff, transparent 50%), radial-gradient(circle at ${b}% 86%, #ffe2d1, transparent 46%), #f8f7f5`
  return <AbsoluteFill style={{ background: bg, overflow: 'hidden', ...style }}>{children}</AbsoluteFill>
}

/** An iPhone drawn around a screen: the titanium rim, the black bezel, the Dynamic Island, the side buttons and the
 * status bar. `w` × `h` is the whole phone; `edge` the rim and bezel around the screen. */
export function IPhone({ w, h, edge, children, shadow = true, statusBar = true }: { w: number; h: number; edge: number; children: React.ReactNode; shadow?: boolean
  statusBar?: boolean }) {
  const r = w * 0.16
  const rim = Math.max(2, edge * 0.32)
  const sw = w - edge * 2
  const button = (side: 'left' | 'right', top: number, len: number): React.ReactNode => (
    <div style={{ position: 'absolute', [side]: -rim * 0.9, top: h * top, width: rim * 1.4, height: h * len, borderRadius: rim,
      background: 'linear-gradient(90deg, #2b2b2e, #6b6b70, #2b2b2e)' }} />
  )
  return (
    <div style={{ position: 'relative', width: w, height: h }}>
      {button('left', 0.16, 0.045)}{button('left', 0.24, 0.075)}{button('left', 0.33, 0.075)}{button('right', 0.26, 0.11)}
      <div style={{ position: 'absolute', inset: 0, borderRadius: r, background: 'linear-gradient(145deg, #77777c, #2a2a2d 30%, #4a4a4f 62%, #1b1b1d)',
        boxShadow: shadow ? `0 ${w * 0.09}px ${w * 0.22}px rgba(12,10,9,.38)` : undefined }}>
        <div style={{ position: 'absolute', inset: rim, borderRadius: r - rim, background: '#050505' }}>
          <div style={{ position: 'absolute', inset: edge - rim, borderRadius: r - edge, overflow: 'hidden', background: '#fff' }}>
            {children}
            {statusBar && <div style={{ position: 'absolute', left: 0, right: 0, top: 0, height: sw * 0.13, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: `0 ${sw * 0.09}px`, fontSize: sw * 0.042, fontWeight: 700, color: INK, zIndex: 9 }}>
              <span>9:41</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: sw * 0.012 }}>
                {[0.4, 0.6, 0.8, 1].map((x, i) => <span key={i} style={{ width: sw * 0.009, height: sw * 0.03 * x, borderRadius: 2, background: INK }} />)}
                <span style={{ marginLeft: sw * 0.02, width: sw * 0.06, height: sw * 0.03, borderRadius: sw * 0.009, border: `${Math.max(1, sw * 0.003)}px solid ${INK}`,
                  padding: sw * 0.003, display: 'flex' }}><span style={{ flex: 1, borderRadius: sw * 0.005, background: INK }} /></span>
              </span>
            </div>}
            <div style={{ position: 'absolute', left: '50%', top: sw * 0.03, width: sw * 0.3, height: sw * 0.085, marginLeft: -sw * 0.15, borderRadius: 999,
              background: '#000', zIndex: 10 }} />
          </div>
        </div>
      </div>
    </div>
  )
}

/** A laptop around a screen: the lid with its camera, the screen and the base. */
function Laptop({ w, children }: { w: number; children: React.ReactNode }) {
  const lid = w * 0.64
  const e = w * 0.018
  return (
    <div style={{ position: 'relative', width: w, height: lid + w * 0.04 }}>
      <div style={{ position: 'absolute', left: w * 0.06, right: w * 0.06, top: 0, height: lid, borderRadius: w * 0.02, background: '#111113',
        boxShadow: `0 ${w * 0.05}px ${w * 0.12}px rgba(12,10,9,.32)` }}>
        <div style={{ position: 'absolute', left: '50%', top: e * 0.35, width: e * 0.3, height: e * 0.3, marginLeft: -e * 0.15, borderRadius: 99, background: '#2c2c30' }} />
        <div style={{ position: 'absolute', inset: e, overflow: 'hidden', borderRadius: w * 0.006, background: '#fff' }}>{children}</div>
      </div>
      <div style={{ position: 'absolute', left: 0, right: 0, top: lid, height: w * 0.035, borderRadius: `0 0 ${w * 0.03}px ${w * 0.03}px`,
        background: 'linear-gradient(#e2e0dd, #a9a5a0)' }}>
        <div style={{ width: w * 0.14, height: w * 0.008, margin: '0 auto', borderRadius: `0 0 ${w * 0.01}px ${w * 0.01}px`, background: '#8f8a85' }} />
      </div>
    </div>
  )
}

const Logo = ({ size, ink = INK, paper = '#fff' }: { size: number; ink?: string; paper?: string }) => (
  <svg width={size} height={size} viewBox="0 0 64 64" style={{ flex: 'none' }}>
    <rect width="64" height="64" rx="15" fill={paper} />
    <path d="M40 15v20a11 11 0 0 1-22 0" fill="none" stroke={ink} strokeWidth="8.5" />
  </svg>
)

/** The app as it looks on the phone: the request typed, the book being made, then the finished book scrolling by.
 * `t` runs 0 → 1 over the scene. */
function PhoneApp({ sw, sh, t, tome, text }: { sw: number; sh: number; t: number; tome: VideoTome; text: string }) {
  const s = sw / 390  // iPhone points
  const making = ease(t, 0.36, 0.42)
  const done = ease(t, 0.56, 0.62)
  const wipe = ease(t, 0.4, 0.56)
  const scroll = ease(t, 0.66, 0.96)
  const pages = (tome.pages.length ? tome.pages : tome.cover ? [tome.cover] : []).slice(0, 6)
  const pressed = t > 0.33 && t < 0.37
  return (
    <div style={{ position: 'absolute', inset: 0, background: '#fafaf9', fontSize: 16 * s, color: INK }}>
      <div style={{ position: 'absolute', left: 0, right: 0, top: 54 * s, height: 50 * s, display: 'flex', alignItems: 'center', gap: 10 * s, padding: `0 ${20 * s}px`,
        borderBottom: `${s}px solid ${LINE}`, background: '#fff' }}>
        <Logo size={26 * s} paper={INK} ink="#fff" /><span style={{ fontWeight: 700, fontSize: 18 * s }}>Jelyx Docs</span>
      </div>
      {/* The composer */}
      <div style={{ position: 'absolute', left: 18 * s, right: 18 * s, top: 130 * s, opacity: 1 - making, transform: `translateY(${-making * 40 * s}px)` }}>
        <div style={{ fontSize: 26 * s, fontWeight: 700, letterSpacing: '-0.02em', lineHeight: 1.15, marginBottom: 16 * s }}>¿Qué libro necesitas hoy?</div>
        <div style={{ background: '#fff', border: `${1.5 * s}px solid ${ACCENT}`, borderRadius: 16 * s, padding: 14 * s, minHeight: 110 * s, fontSize: 17 * s, lineHeight: 1.35,
          boxShadow: `0 0 0 ${4 * s}px ${ACCENT}22` }}>
          {typed(text, t * 100, 4, 30)}<span style={{ opacity: Math.floor(t * 60) % 2 ? 1 : 0, color: ACCENT }}>|</span>
        </div>
        <div style={{ marginTop: 14 * s, background: ACCENT, color: '#fff', borderRadius: 14 * s, padding: `${14 * s}px 0`, textAlign: 'center', fontWeight: 700,
          fontSize: 17 * s, transform: `scale(${pressed ? 0.95 : 1})` }}>Crear mi libro</div>
        <div style={{ display: 'flex', gap: 8 * s, marginTop: 16 * s, flexWrap: 'wrap' }}>
          {['Libro ilustrado', 'Cuento', 'Para colorear'].map((c) => (
            <span key={c} style={{ border: `${s}px solid ${LINE}`, borderRadius: 999, padding: `${6 * s}px ${12 * s}px`, fontSize: 13 * s, background: '#fff' }}>{c}</span>))}
        </div>
      </div>
      {/* The book being made, then made */}
      <div style={{ position: 'absolute', left: 18 * s, right: 18 * s, top: 124 * s, opacity: making, transform: `translateY(${(1 - making) * 40 * s - scroll * (sh * 0.62)}px)` }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 * s, fontSize: 14 * s, fontWeight: 600, marginBottom: 12 * s }}>
          <span style={{ width: 10 * s, height: 10 * s, borderRadius: 99, background: done ? OK : '#c98a12' }} />
          {done ? 'Tu libro está listo' : 'Pintando la portada…'}
        </div>
        <div style={{ position: 'relative', width: '100%', aspectRatio: '170 / 210', borderRadius: 14 * s, overflow: 'hidden', background: SOFT,
          boxShadow: `0 ${12 * s}px ${30 * s}px rgba(12,10,9,.18)` }}>
          {tome.cover && <Img src={tome.cover} crossOrigin="anonymous" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />}
          <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: `${(1 - wipe) * 100}%`, background: SOFT }} />
        </div>
        <div style={{ fontWeight: 700, fontSize: 19 * s, margin: `${14 * s}px 0 ${4 * s}px`, lineHeight: 1.2 }}>{tome.title}</div>
        <div style={{ fontSize: 13 * s, color: '#78716c', marginBottom: 14 * s }}>{tome.kind}{tome.audience ? ` · ${tome.audience}` : ''}</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 * s }}>
          {pages.map((src, i) => (
            <div key={i} style={{ aspectRatio: '170 / 210', borderRadius: 10 * s, overflow: 'hidden', background: '#fff', boxShadow: `0 ${6 * s}px ${14 * s}px rgba(12,10,9,.14)`,
              opacity: ease(t, 0.6 + i * 0.03, 0.66 + i * 0.03) }}>
              <Img src={src} crossOrigin="anonymous" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            </div>
          ))}
        </div>
      </div>
      {/* The download bar */}
      <div style={{ position: 'absolute', left: 18 * s, right: 18 * s, bottom: 30 * s, background: INK, color: '#fff', borderRadius: 16 * s, padding: `${14 * s}px ${16 * s}px`,
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontWeight: 700, fontSize: 15 * s, opacity: done, transform: `translateY(${(1 - done) * 60 * s}px)` }}>
        <span>PDF listo para imprimir</span><span style={{ background: ACCENT, borderRadius: 10 * s, padding: `${6 * s}px ${12 * s}px` }}>Descargar</span>
      </div>
    </div>
  )
}

/** A floating badge beside the device, landing with a spring. */
function Badge({ at, frame, u, label, style }: { at: number; frame: number; u: number; label: string; style: React.CSSProperties }) {
  const { fps } = useVideoConfig()
  const s = spring({ frame: frame - at, fps, config: { damping: 12, mass: 0.6 } })
  return (
    <div style={{ position: 'absolute', zIndex: 4, background: '#fff', color: INK, borderRadius: 999, padding: `${16 * u}px ${28 * u}px`, fontSize: 34 * u, fontWeight: 700,
      display: 'flex', alignItems: 'center', gap: 14 * u, boxShadow: `0 ${18 * u}px ${44 * u}px rgba(12,10,9,.22)`, opacity: Math.min(1, s * 1.4),
      transform: `scale(${0.6 + s * 0.4})`, whiteSpace: 'nowrap', ...style }}>
      <span style={{ width: 34 * u, height: 34 * u, borderRadius: 99, background: OK, color: '#fff', fontSize: 22 * u, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>✓</span>
      {label}
    </div>
  )
}

const PHONE_RATIO = 2.06

/** The app in an iPhone: it rises into the frame, floats while the request is typed and the book is made, the
 * camera drifts in, and badges land beside it. */
export function PhoneScene({ dur, caption, step, tome, text = '', look = LOOKS.claro }: Base & { tome: VideoTome; text?: string; look?: Palette }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const { u, wide, width: W, height: H } = useUnit()
  const tall = H > W
  const w = Math.min(tall ? W * 0.56 : W * 0.42, (H * (tall ? 0.66 : 0.8)) / PHONE_RATIO)
  const h = w * PHONE_RATIO
  const land = spring({ frame, fps, config: { damping: 15, mass: 0.9 } })
  const float = Math.sin(frame / 18) * 10 * u
  const zoom = interpolate(frame, [0, dur], [1, 1.08])
  const cy = H * (tall ? 0.42 : 0.47)
  const pageCount = Math.max(tome.pages.length, tome.sections.length * 2)
  return (
    <Glow look={look} style={{ opacity: fadeOut(frame, dur) }}>
      <div style={{ position: 'absolute', inset: 0, transform: `scale(${zoom})`, transformOrigin: `50% ${(cy / H) * 100}%` }}>
        <div style={{ position: 'absolute', left: (W - w) / 2, top: cy - h / 2,
          transform: `translateY(${(1 - land) * H * 0.6 + float}px) rotate(${(1 - land) * 10 - 2}deg)` }}>
          <IPhone w={w} h={h} edge={w * 0.045}>
            <PhoneApp sw={w * 0.91} sh={h - w * 0.09} t={frame / dur} tome={tome} text={text} />
          </IPhone>
        </div>
        <Badge at={dur * 0.58} frame={frame} u={u} label="Portada" style={{ left: W / 2 - w / 2 - (wide ? 230 : 110) * u, top: cy - h * 0.28 }} />
        <Badge at={dur * 0.68} frame={frame} u={u} label={`${pageCount} páginas`} style={{ left: W / 2 + w / 2 - (wide ? -40 : 250) * u, top: cy - h * 0.02 }} />
        <Badge at={dur * 0.78} frame={frame} u={u} label="PDF listo" style={{ left: W / 2 - w / 2 - (wide ? 200 : 80) * u, top: cy + h * 0.24 }} />
      </div>
      <Caption text={caption} at={Math.min(dur - 20, dur * 0.3)} step={step} />
    </Glow>
  )
}

/** The book in a laptop and in an iPhone at once: made on one, open on the other. */
export function DevicesScene({ dur, caption, step, tome, look = LOOKS.claro }: Base & { tome: VideoTome; look?: Palette }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const { u, wide, width: W, height: H } = useUnit()
  const tall = H > W
  const lw = wide ? W * 0.56 : W * (tall ? 0.9 : 0.74)
  const lh = lw * 0.68
  const pw = wide ? H * 0.26 : W * (tall ? 0.34 : 0.25)
  const ph = pw * PHONE_RATIO
  const ltop = tall ? H * 0.17 : wide ? H * 0.18 : H * 0.14
  const lleft = wide ? W * 0.14 : (W - lw) / 2
  const pleft = wide ? lleft + lw - pw * 0.35 : W - pw - W * (tall ? 0.06 : 0.08)
  const ptop = tall ? ltop + lh * 0.55 : ltop + lh - ph * 0.82
  const a = spring({ frame, fps, config: { damping: 16 } })
  const b = spring({ frame: frame - dur * 0.22, fps, config: { damping: 14, mass: 0.8 } })
  const zoom = interpolate(frame, [0, dur], [1, 1.06])
  const pages = (tome.pages.length ? tome.pages : tome.cover ? [tome.cover] : []).slice(0, 8)
  const s = lw / 1200
  return (
    <Glow look={look} style={{ opacity: fadeOut(frame, dur) }}>
      <div style={{ position: 'absolute', inset: 0, transform: `scale(${zoom})` }}>
        <div style={{ position: 'absolute', left: lleft, top: ltop, opacity: a, transform: `translateY(${(1 - a) * 120 * u}px) scale(${0.92 + a * 0.08})` }}>
          <Laptop w={lw}>
            <div style={{ position: 'absolute', inset: 0, background: '#fafaf9', display: 'flex', flexDirection: 'column' }}>
              <div style={{ height: 46 * s, display: 'flex', alignItems: 'center', gap: 10 * s, padding: `0 ${18 * s}px`, borderBottom: `${s}px solid ${LINE}`, background: '#fff' }}>
                {['#ff5f57', '#febc2e', '#28c840'].map((c) => <span key={c} style={{ width: 12 * s, height: 12 * s, borderRadius: 99, background: c }} />)}
                <span style={{ marginLeft: 20 * s, flex: 1, maxWidth: 420 * s, height: 26 * s, borderRadius: 8 * s, background: '#f1f0ee', fontSize: 14 * s, color: '#78716c',
                  display: 'flex', alignItems: 'center', paddingLeft: 12 * s }}>{SITE}</span>
              </div>
              <div style={{ flex: 1, display: 'flex', gap: 24 * s, padding: 26 * s }}>
                <div style={{ width: 230 * s, flex: 'none', borderRadius: 12 * s, overflow: 'hidden', aspectRatio: '170 / 210', alignSelf: 'flex-start',
                  boxShadow: `0 ${10 * s}px ${26 * s}px rgba(12,10,9,.18)`, background: SOFT }}>
                  {tome.cover && <Img src={tome.cover} crossOrigin="anonymous" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 30 * s, fontWeight: 700, letterSpacing: '-0.02em', lineHeight: 1.15, color: INK }}>{tome.title}</div>
                  <div style={{ fontSize: 16 * s, color: '#78716c', margin: `${6 * s}px 0 ${18 * s}px` }}>{tome.kind}{tome.audience ? ` · ${tome.audience}` : ''}</div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 * s }}>
                    {pages.map((src, i) => (
                      <div key={i} style={{ aspectRatio: '170 / 210', borderRadius: 8 * s, overflow: 'hidden', background: '#fff', boxShadow: `0 ${4 * s}px ${12 * s}px rgba(12,10,9,.14)`,
                        opacity: ease(frame, 10 + i * 3, 20 + i * 3) }}>
                        <Img src={src} crossOrigin="anonymous" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </Laptop>
        </div>
        <div style={{ position: 'absolute', left: pleft, top: ptop, opacity: Math.min(1, b * 1.5), transform: `translateX(${(1 - b) * 260 * u}px) rotate(${(1 - b) * 12 + 3}deg)` }}>
          <IPhone w={pw} h={ph} edge={pw * 0.045}>
            <div style={{ position: 'absolute', inset: 0, background: INK }}>
              {tome.cover && <Img src={tome.cover} crossOrigin="anonymous" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />}
              <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: pw * 0.08, paddingTop: pw * 0.3, color: '#fff', fontWeight: 700,
                fontSize: pw * 0.065, lineHeight: 1.2, background: 'linear-gradient(transparent, rgba(12,10,9,.85))' }}>{tome.title}</div>
            </div>
          </IPhone>
        </div>
      </div>
      <Caption text={caption} at={Math.min(dur - 20, dur * 0.35)} step={step} />
    </Glow>
  )
}

/** A real page and a magnifying glass gliding over it to a detail; then the camera pushes in on the detail and a
 * label names it (text). */
export function ZoomScene({ dur, caption, step, tome, text = '', look = LOOKS.claro }: Base & { tome: VideoTome; text?: string; look?: Palette }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const { u, wide, width: W, height: H } = useUnit()
  const src = tome.plate?.image ?? tome.pages[0] ?? tome.cover
  const ch = H * (wide ? 0.78 : 0.6)
  const cw = Math.min(ch * (170 / 210), W * 0.86)
  const cl = (W - cw) / 2
  const ct = (H - ch) / 2 - (wide ? 20 : 120) * u
  const tx = cl + cw * 0.5
  const ty = ct + ch * 0.42  // the detail: the middle of the picture, where the figures stand
  const land = spring({ frame, fps, config: { damping: 15 } })
  const g = ease(frame, dur * 0.15, dur * 0.45)
  const lx = cl + cw * 0.85 + (tx - cl - cw * 0.85) * g
  const ly = ct + ch * 0.85 + (ty - ct - ch * 0.85) * g
  const D = cw * 0.42
  const M = 2.3
  const lens = ease(frame, dur * 0.1, dur * 0.18) * (1 - ease(frame, dur * 0.52, dur * 0.6))
  const push = ease(frame, dur * 0.5, dur * 0.72)
  const Z = 1 + push * 1.3
  const cx = W / 2
  const cy = H * (wide ? 0.45 : 0.4)
  const camX = tx + push * (cx - tx) - tx * Z
  const camY = ty + push * (cy - ty) - ty * Z
  const label = ease(frame, dur * 0.7, dur * 0.78)
  if (!src) return <Glow look={look} />
  return (
    <Glow look={look} style={{ opacity: fadeOut(frame, dur) }}>
      <div style={{ position: 'absolute', inset: 0, transformOrigin: '0 0', transform: `translate(${camX}px, ${camY}px) scale(${Z})` }}>
        <div style={{ position: 'absolute', left: cl, top: ct, width: cw, height: ch, borderRadius: 16 * u, overflow: 'hidden', background: '#fff',
          boxShadow: `0 ${30 * u}px ${80 * u}px rgba(12,10,9,.3)`, opacity: land, transform: `translateY(${(1 - land) * 100 * u}px)` }}>
          <Img src={src} crossOrigin="anonymous" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        </div>
        {lens > 0 && (
          <div style={{ position: 'absolute', left: lx - D / 2, top: ly - D / 2, width: D, height: D, borderRadius: 999, overflow: 'hidden', opacity: lens,
            boxSizing: 'border-box', border: `${8 * u}px solid #fff`, boxShadow: `0 ${20 * u}px ${50 * u}px rgba(12,10,9,.35)`, transform: `scale(${0.7 + lens * 0.3})`, background: '#fff' }}>
            <Img src={src} crossOrigin="anonymous" style={{ position: 'absolute', width: cw * M, height: ch * M, objectFit: 'cover',
              left: -(lx - cl) * M + D / 2 - 8 * u, top: -(ly - ct) * M + D / 2 - 8 * u }} />
          </div>
        )}
      </div>
      {text && (
        <div style={{ position: 'absolute', left: 0, right: 0, top: cy - (wide ? 300 : 420) * u, display: 'flex', justifyContent: 'center', opacity: label,
          transform: `translateY(${(1 - label) * 30 * u}px)` }}>
          <span style={{ background: ACCENT, color: '#fff', borderRadius: 999, padding: `${16 * u}px ${34 * u}px`, fontSize: 44 * u, fontWeight: 700,
            boxShadow: `0 ${16 * u}px ${40 * u}px ${ACCENT}66` }}>{text}</span>
        </div>
      )}
      <Caption text={caption} at={Math.min(dur - 20, dur * 0.25)} step={step} />
    </Glow>
  )
}

/** Kinetic type: short phrases (text, separated by |) cut one after another, as in a launch film: each word rises out
 * of a mask, the phrase pushes in slowly and leaves upwards on the cut, and the field flips to the accent every other
 * phrase. The last word of each phrase on the plain field takes the accent. */
export function KineticScene({ dur, text = '', caption = '', look = LOOKS.claro }: Base & { text?: string; look?: Palette }) {
  const frame = useCurrentFrame()
  const { u, wide, width: W } = useUnit()
  const phrases = (parts(text).length ? parts(text) : [caption]).filter(Boolean).slice(0, 5)
  if (!phrases.length) return <Glow look={look} />
  const each = dur / phrases.length
  const i = Math.min(phrases.length - 1, Math.floor(frame / each))
  const local = frame - i * each
  const last = i === phrases.length - 1
  const flip = i % 2 === 1
  const ink = flip ? (isDark(look) ? INK : '#fff') : look.ink
  const words = phrases[i].split(/\s+/).filter(Boolean)
  const longest = Math.max(4, ...words.map((w) => w.length))
  const size = Math.min((wide ? 200 : 176) * u, (W * 0.84) / (longest * 0.6))
  const push = interpolate(local, [0, each], [1, 1.07], { extrapolateRight: 'clamp' })
  const leave = last ? 0 : ease(local, each - 6, each)
  const body = (
    <div style={{ fontSize: size, fontWeight: 700, letterSpacing: '-0.05em', lineHeight: 1.02, color: ink, textAlign: 'center', maxWidth: '88%',
      transform: `scale(${push})`, marginTop: wide ? 0 : -90 * u }}>
      {words.map((w, j) => {
        const s = ease(local, 1 + j * 3, 13 + j * 3)
        return <Rise key={`${i}-${j}`} y={(1 - s) * 110 - leave * 110} color={!flip && j === words.length - 1 && words.length > 1 ? look.accent : ink}>{w}</Rise>
      })}
    </div>
  )
  const style: React.CSSProperties = { alignItems: 'center', justifyContent: 'center', opacity: last ? fadeOut(frame, dur) : 1 }
  return flip
    ? <AbsoluteFill style={{ ...style, background: `radial-gradient(circle at 50% 30%, rgba(255,255,255,.22), transparent 62%), ${look.accent}` }}>{body}</AbsoluteFill>
    : <Glow look={look} style={style}>{body}</Glow>
}

/** A word that rises out of a mask (y: how far below its line it still is, in % of its height). */
export function Rise({ y, color, children }: { y: number; color?: string; children: React.ReactNode }) {
  return (
    <span style={{ display: 'inline-block', overflow: 'hidden', verticalAlign: 'bottom', padding: '0.04em 0.13em 0.12em', margin: '0 0 -0.12em' }}>
      <span style={{ display: 'inline-block', transform: `translateY(${y}%)`, color }}>{children}</span>
    </span>
  )
}

const ICONS = [
  'M12 3l2.4 5.6L20 11l-5.6 2.4L12 19l-2.4-5.6L4 11l5.6-2.4z',  // sparkle: made by the AI
  'M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm8 0a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM2 20c0-3.3 2.7-6 6-6s6 2.7 6 6M14 14.3c.6-.2 1.3-.3 2-.3 3.3 0 6 2.7 6 6',  // people: same characters
  'M9 6h11M9 12h11M9 18h11M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2',  // checklist: activities, answer key
  'M12 4v11m0 0l-4-4m4 4l4-4M5 20h14',  // download: PDF and Word
]

/** A bento of features: the book's cover in the big tile and up to four features (text, separated by |) in the others. */
export function BentoScene({ dur, caption, step, tome, text = '', look = LOOKS.claro }: Base & { tome: VideoTome; text?: string; look?: Palette }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const { u, k, wide, width: W, height: H } = useUnit()
  const tall = H > W
  const dark = isDark(look)
  const features = parts(text).slice(0, 4)
  const gw = wide ? W * 0.8 : W * 0.88
  const gh = wide ? H * 0.66 : tall ? H * 0.62 : H * 0.72
  const gap = 22 * u
  const card: React.CSSProperties = { position: 'absolute', borderRadius: 30 * u, overflow: 'hidden',
    background: dark ? 'rgba(255,255,255,.07)' : '#fff', border: `${2 * u}px solid ${dark ? 'rgba(255,255,255,.14)' : LINE}`,
    boxShadow: dark ? undefined : `0 ${14 * u}px ${36 * u}px rgba(12,10,9,.08)` }
  // wide: the big tile on the left and a 2×2 of features; tall and square: the big tile on top and a 2×2 below.
  const big = wide ? { left: 0, top: 0, width: gw * 0.4 - gap / 2, height: gh } : { left: 0, top: 0, width: gw, height: gh * 0.42 - gap / 2 }
  const ox = wide ? gw * 0.4 + gap / 2 : 0
  const oy = wide ? 0 : gh * 0.42 + gap / 2
  const fw = ((wide ? gw * 0.6 - gap / 2 : gw) - gap) / 2
  const fh = ((wide ? gh : gh * 0.58 - gap / 2) - gap) / 2
  const pop = (i: number) => spring({ frame: frame - 4 - i * 5, fps, config: { damping: 14, mass: 0.7 } })
  return (
    <Glow look={look} style={{ opacity: fadeOut(frame, dur) }}>
      <div style={{ position: 'absolute', left: (W - gw) / 2, top: (H - gh) / 2 - (wide ? 30 : tall ? 110 : 60) * u, width: gw, height: gh }}>
        <div style={{ ...card, ...big, opacity: pop(0), transform: `scale(${0.9 + pop(0) * 0.1})`, background: dark ? '#1b1930' : SOFT }}>
          {tome.cover && <Img src={tome.cover} crossOrigin="anonymous" style={{ position: 'absolute', height: '86%', aspectRatio: '170 / 210', objectFit: 'cover',
            borderRadius: 14 * u, left: '50%', top: '7%', transform: `translateX(-50%) rotate(${-3 + pop(0) * 3}deg)`, boxShadow: `0 ${20 * u}px ${50 * u}px rgba(12,10,9,.3)` }} />}
        </div>
        {features.map((f, i) => {
          const s = pop(i + 1)
          return (
            <div key={i} style={{ ...card, left: ox + (i % 2) * (fw + gap), top: oy + Math.floor(i / 2) * (fh + gap), width: fw, height: fh, padding: 30 * u,
              display: 'flex', flexDirection: 'column', justifyContent: 'space-between', opacity: s, transform: `translateY(${(1 - s) * 60 * u}px)` }}>
              <span style={{ width: 76 * u, height: 76 * u, borderRadius: 22 * u, background: `${look.accent}22`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <svg width={44 * u} height={44 * u} viewBox="0 0 24 24"><path d={ICONS[i % ICONS.length]} fill="none" stroke={look.accent} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
              </span>
              <span style={{ fontSize: (wide ? 40 : 38) * u * (tall ? k * 0.9 : 1), fontWeight: 700, letterSpacing: '-0.02em', lineHeight: 1.1, color: dark ? '#fff' : INK }}>{f}</span>
            </div>
          )
        })}
      </div>
      <Caption text={caption} at={Math.min(dur - 20, 20 + features.length * 5)} step={step} />
    </Glow>
  )
}

/** The AI chat that makes the book: the request typed and sent, the assistant working through its steps, the book
 * answered as a card. */
export function ChatScene({ dur, caption, step, tome, text = '', look = LOOKS.claro }: Base & { tome: VideoTome; text?: string; look?: Palette }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const { u, k, wide, width: W, height: H } = useUnit()
  const t = frame / dur
  const tall = H > W
  const cw = wide ? 1150 * u : W * 0.88
  const f = (wide ? 1 : tall ? k * 0.9 : 0.85) * u
  const sent = ease(t, 0.3, 0.36)
  const working = ease(t, 0.36, 0.42)
  const stepsDone = [0.46, 0.53, 0.6].map((x) => t > x)
  const answer = spring({ frame: frame - dur * 0.64, fps, config: { damping: 14, mass: 0.8 } })
  const pages = Math.max(tome.pages.length, tome.sections.length * 2)
  const box: React.CSSProperties = { background: '#fff', border: `${2 * u}px solid ${LINE}`, borderRadius: 28 * u, boxShadow: `0 ${18 * u}px ${46 * u}px rgba(12,10,9,.12)` }
  return (
    <Glow look={look} style={{ opacity: fadeOut(frame, dur) }}>
      <div style={{ position: 'absolute', left: (W - cw) / 2, width: cw, top: H * (wide ? 0.1 : 0.12), display: 'flex', flexDirection: 'column', gap: 26 * u }}>
        {/* the sent request */}
        <div style={{ alignSelf: 'flex-end', maxWidth: '82%', background: ACCENT, color: '#fff', borderRadius: `${30 * u}px ${30 * u}px ${8 * u}px ${30 * u}px`,
          padding: `${22 * u}px ${30 * u}px`, fontSize: 36 * f, fontWeight: 600, lineHeight: 1.3, opacity: sent, transform: `translateY(${(1 - sent) * 80 * u}px)` }}>{text}</div>
        {/* the assistant at work */}
        <div style={{ ...box, alignSelf: 'flex-start', padding: `${24 * u}px ${30 * u}px`, opacity: working, transform: `translateY(${(1 - working) * 40 * u}px)`,
          display: 'flex', flexDirection: 'column', gap: 14 * u, minWidth: '60%' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 * u, fontSize: 32 * f, fontWeight: 700, color: INK }}>
            <Logo size={46 * u} paper={INK} ink="#fff" />
            {stepsDone[2] ? 'Listo' : 'Creando tu libro'}
            {!stepsDone[2] && <span style={{ display: 'flex', gap: 6 * u }}>{[0, 1, 2].map((d) => (
              <span key={d} style={{ width: 10 * u, height: 10 * u, borderRadius: 99, background: ACCENT, opacity: 0.35 + 0.65 * Math.abs(Math.sin((frame - d * 5) / 6)) }} />))}</span>}
          </div>
          {['El plan del libro', 'La portada', 'Las ilustraciones'].map((label, i) => (
            <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 14 * u, fontSize: 30 * f, color: stepsDone[i] ? INK : '#a8a29e', fontWeight: 600 }}>
              <span style={{ width: 36 * u, height: 36 * u, borderRadius: 99, background: stepsDone[i] ? OK : '#f1f0ee', color: '#fff', fontSize: 22 * u,
                display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{stepsDone[i] ? '✓' : ''}</span>{label}
            </div>
          ))}
        </div>
        {/* the book */}
        <div style={{ ...box, alignSelf: 'flex-start', padding: 22 * u, display: 'flex', gap: 26 * u, alignItems: 'center', width: '100%',
          opacity: Math.min(1, answer * 1.4), transform: `translateY(${(1 - answer) * 80 * u}px) scale(${0.94 + answer * 0.06})` }}>
          <div style={{ width: (wide ? 190 : tall ? 200 : 140) * u, flex: 'none', aspectRatio: '170 / 210', borderRadius: 14 * u, overflow: 'hidden', background: SOFT }}>
            {tome.cover && <Img src={tome.cover} crossOrigin="anonymous" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 * u, minWidth: 0 }}>
            <span style={{ fontSize: 38 * f, fontWeight: 700, letterSpacing: '-0.02em', lineHeight: 1.12, color: INK }}>{tome.title}</span>
            <span style={{ fontSize: 26 * f, color: '#78716c' }}>{tome.kind} · {pages} páginas</span>
            <span style={{ alignSelf: 'flex-start', background: INK, color: '#fff', borderRadius: 14 * u, padding: `${12 * u}px ${24 * u}px`, fontSize: 26 * f, fontWeight: 700 }}>Abrir libro →</span>
          </div>
        </div>
      </div>
      {/* the composer at the bottom, where the request is typed */}
      <div style={{ ...box, position: 'absolute', left: (W - cw) / 2, width: cw, bottom: (wide ? 60 : tall ? 330 : 60) * u, padding: `${22 * u}px ${26 * u}px`,
        display: 'flex', alignItems: 'center', gap: 20 * u, opacity: Math.max(0, 1 - working * 0.6 - answer * 0.4) }}>
        <span style={{ flex: 1, fontSize: 32 * f, color: sent ? '#a8a29e' : INK, lineHeight: 1.3 }}>
          {sent ? 'Describe el libro que necesitas…' : typed(text, frame, 6, dur * 0.27) || 'Describe el libro que necesitas…'}</span>
        <span style={{ width: 70 * u, height: 70 * u, borderRadius: 99, background: ACCENT, display: 'flex', alignItems: 'center', justifyContent: 'center',
          transform: `scale(${t > 0.27 && t < 0.31 ? 0.86 : 1})`, flex: 'none' }}>
          <svg width={34 * u} height={34 * u} viewBox="0 0 24 24"><path d="M12 19V5m0 0l-6 6m6-6l6 6" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </span>
      </div>
      <Caption text={caption} at={Math.min(dur - 20, dur * 0.7)} step={step} />
    </Glow>
  )
}

/** The brand reveal: the mark lands with a ring of light, the name slides out of it and the line (caption) follows. */
export function LogoScene({ dur, caption = '', look = LOOKS.oscuro }: Base & { look?: Palette }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const { u, wide } = useUnit()
  const dark = isDark(look)
  const mark = spring({ frame, fps, config: { damping: 12, mass: 0.7 } })
  const ring = ease(frame, 4, 34)
  const name = ease(frame, 12, 26)
  const line = ease(frame, 24, 38)
  const size = 170 * u
  return (
    <Glow look={look} style={{ alignItems: 'center', justifyContent: 'center', opacity: fadeOut(frame, dur) }}>
      <div style={{ position: 'absolute', width: size * 3 * ring + size, height: size * 3 * ring + size, borderRadius: 999,
        border: `${4 * u}px solid ${look.accent}`, opacity: (1 - ring) * 0.8 }} />
      <div style={{ display: 'flex', flexDirection: wide ? 'row' : 'column', alignItems: 'center', gap: 34 * u, marginTop: wide ? 0 : -120 * u }}>
        <div style={{ transform: `scale(${mark}) rotate(${(1 - mark) * -30}deg)` }}><Logo size={size} paper={dark ? '#fff' : INK} ink={dark ? INK : '#fff'} /></div>
        <span style={{ fontSize: 120 * u, fontWeight: 700, letterSpacing: '-0.04em', color: look.ink, opacity: name,
          transform: `translate${wide ? 'X' : 'Y'}(${(1 - name) * -40 * u}px)` }}>Jelyx Docs</span>
      </div>
      {caption && <div style={{ position: 'absolute', bottom: (wide ? 200 : 560) * u, left: '8%', right: '8%', textAlign: 'center', fontSize: 54 * u, fontWeight: 600,
        color: look.ink, opacity: line * 0.85, transform: `translateY(${(1 - line) * 20 * u}px)`, lineHeight: 1.2 }}>{caption}</div>}
    </Glow>
  )
}
