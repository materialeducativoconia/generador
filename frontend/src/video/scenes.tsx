import { AbsoluteFill, Easing, Img, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion'
import { SITE, type VideoTome } from './spec'

/** The scenes every video is made of, each the real app animated with a real tome. `dur` is the scene's length in
 * frames: timings are fractions of it, so the director can give a scene 2 s or 8 s. Drawn with transforms, opacity
 * and plain boxes only, which the in-browser renderer (@remotion/web-renderer) paints exactly as the preview. */

const INK = '#0c0a09'
const ACCENT = '#5b4cf0'
const SOFT = '#f4f2ff'
const LINE = '#e7e5e2'
const OK = '#2f8f4e'
type Base = { dur: number; caption?: string; step?: number }

function useUnit() {
  const { width, height } = useVideoConfig()
  const u = Math.min(width, height) / 1080
  // k: text on a phone screen is read at arm's length, so the vertical cut sets it larger.
  return { u, k: width >= height ? 1 : 1.3, wide: width > height, width, height }
}

const ease = (f: number, from: number, to: number, out: [number, number] = [0, 1]) =>
  interpolate(f, [from, Math.max(from + 1, to)], out, { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.bezier(0.22, 1, 0.36, 1) })
const fadeOut = (frame: number, dur: number) => ease(frame, dur - 10, dur, [1, 0])
const typed = (text: string, frame: number, from: number, to: number) =>
  text.slice(0, Math.round(interpolate(frame, [from, Math.max(from + 1, to)], [0, text.length], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })))

function Pointer({ u, style }: { u: number; style: React.CSSProperties }) {
  return (
    <svg width={56 * u} height={56 * u} viewBox="0 0 24 24" style={{ position: 'absolute', zIndex: 5, ...style }}>
      <path d="M5 3l14 8-6 1.5L10 19z" fill={INK} stroke="#fff" strokeWidth="1.4" strokeLinejoin="round" />
    </svg>
  )
}

/** The line on screen; in a tutorial it carries its step number. */
function Caption({ text, at = 6, step }: { text?: string; at?: number; step?: number }) {
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

/** Big words landing one by one, the last in the accent colour: the hook, a tutorial's title, a key idea. */
export function TitleScene({ dur, caption = '' }: Base) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const { u, wide } = useUnit()
  const words = caption.split(/\s+/).filter(Boolean)
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', padding: 90 * u, opacity: fadeOut(frame, dur) }}>
      <div style={{ fontSize: (wide ? 104 : 112) * u, fontWeight: 700, lineHeight: 1.08, letterSpacing: '-0.035em', textAlign: 'center', maxWidth: wide ? 1500 * u : undefined }}>
        {words.map((w, i) => {
          const s = spring({ frame: frame - 4 - i * 4, fps, config: { damping: 14, mass: 0.6 } })
          return <span key={i} style={{ display: 'inline-block', marginRight: '0.26em', opacity: s, transform: `translateY(${(1 - s) * 40 * u}px)`,
            color: i === words.length - 1 ? ACCENT : INK }}>{w}</span>
        })}
      </div>
    </AbsoluteFill>
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
export function CtaScene({ caption = '' }: Base) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const { u } = useUnit()
  const s = spring({ frame, fps, config: { damping: 14 } })
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', background: INK, color: '#fff', gap: 40 * u }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 24 * u, opacity: s, transform: `scale(${0.8 + s * 0.2})` }}>
        <svg width={110 * u} height={110 * u} viewBox="0 0 64 64">
          <rect width="64" height="64" rx="15" fill="#fff" />
          <path d="M40 15v20a11 11 0 0 1-22 0" fill="none" stroke={INK} strokeWidth="8.5" />
        </svg>
        <span style={{ fontSize: 76 * u, fontWeight: 700, letterSpacing: '-0.03em' }}>Jelyx Docs</span>
      </div>
      <div style={{ fontSize: 60 * u, fontWeight: 700, textAlign: 'center', maxWidth: '84%', lineHeight: 1.12, letterSpacing: '-0.02em',
        opacity: ease(frame, 10, 22) }}>{caption}</div>
      <div style={{ background: ACCENT, borderRadius: 999, padding: `${18 * u}px ${40 * u}px`, fontSize: 40 * u, fontWeight: 700,
        opacity: ease(frame, 20, 32) }}>{SITE}</div>
    </AbsoluteFill>
  )
}

/* ——— The page editor, as the app draws it: the strip of pages, the plate with its texts, the form beside it. ——— */

type Box = { left: number; top: number; width: number; height: number }

/** Where the editor's parts sit: wide, strip | plate | form; tall, strip on top, plate, form below. */
function useEditorLayout() {
  const { u, k, wide, width, height } = useUnit()
  if (wide) {
    const plateH = height * 0.6  // the caption and its step badge keep the bottom fifth
    const plate: Box = { left: 230 * u, top: 140 * u, width: plateH * (170 / 210), height: plateH }
    return { u, k, wide, width, height, strip: { left: 70 * u, top: 140 * u, width: 120 * u, height: plateH },
      plate, form: { left: plate.left + plate.width + 60 * u, top: 140 * u, width: width - plate.left - plate.width - 130 * u, height: plateH } }
  }
  const plateH = height * 0.42
  const plateW = plateH * (170 / 210)
  const plate: Box = { left: (width - plateW) / 2, top: 360 * u, width: plateW, height: plateH }
  return { u, k, wide, width, height, strip: { left: 60 * u, top: 200 * u, width: width - 120 * u, height: 130 * u },
    plate, form: { left: 60 * u, top: plate.top + plateH + 40 * u, width: width - 120 * u, height: 320 * u } }
}

const at = (b: Box): React.CSSProperties => ({ position: 'absolute', left: b.left, top: b.top, width: b.width, height: b.height })

function EditorShell({ children, dur, caption, step }: Base & { children: React.ReactNode }) {
  const frame = useCurrentFrame()
  const { u, wide } = useUnit()
  return (
    <AbsoluteFill style={{ background: '#fafaf9', opacity: fadeOut(frame, dur) }}>
      <div style={{ position: 'absolute', left: 0, right: 0, top: 0, height: (wide ? 100 : 150) * u, display: 'flex', alignItems: 'flex-end',
        padding: `0 ${(wide ? 70 : 60) * u}px ${22 * u}px`, borderBottom: `${2 * u}px solid ${LINE}`, background: '#fff', gap: 20 * u }}>
        <span style={{ fontSize: 26 * u, fontWeight: 700, letterSpacing: '.14em', color: ACCENT }}>EDITOR DE PÁGINAS</span>
      </div>
      {children}
      <Caption text={caption} step={step} at={8} />
    </AbsoluteFill>
  )
}

/** The thumbnails of the book's pages, the cover first; `on` is the one open. */
function Strip({ tome, on, appear = 1 }: { tome: VideoTome; on: number; appear?: number }) {
  const { u, wide, strip } = useEditorLayout()
  const size = wide ? strip.width : (strip.width - 5 * 16 * u) / 6
  const fit = wide ? Math.floor((strip.height + 16 * u) / (size * (210 / 170) + 16 * u)) : 6  // as many as the column holds
  const thumbs = [tome.cover, ...tome.pages].filter(Boolean).slice(0, fit) as string[]
  return (
    <div style={{ ...at(strip), display: 'flex', flexDirection: wide ? 'column' : 'row', gap: 16 * u }}>
      {thumbs.map((src, i) => (
        <div key={i} style={{ width: size, height: size * (210 / 170), flex: 'none', borderRadius: 8 * u, overflow: 'hidden',
          outline: `${(i === on ? 5 : 0) * u}px solid ${ACCENT}`, outlineOffset: 3 * u, opacity: ease(appear * 30, i * 3, i * 3 + 10),
          boxShadow: `0 ${4 * u}px ${12 * u}px rgba(12,10,9,.15)` }}>
          <Img src={src} crossOrigin="anonymous" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        </div>
      ))}
    </div>
  )
}

/** A plate with its words over the picture: the question card, the facts and the find strip. */
function Plate({ tome, qTop = 4, notes, hidden = [], fresh, freshIn = 0, image, dragging = false, cover = false, nameLine = 1, age = 1 }: {
  tome: VideoTome; qTop?: number; notes?: string[]; hidden?: number[]; fresh?: string; freshIn?: number; image?: string; dragging?: boolean
  cover?: boolean; nameLine?: number; age?: number
}) {
  const { u, k, plate } = useEditorLayout()
  const p = tome.plate
  const src = image ?? (cover ? tome.cover : p?.image ?? tome.pages[0] ?? tome.cover) ?? undefined
  const facts = notes ?? p?.notes ?? []
  const f = 0.42 * k
  return (
    <div style={{ ...at(plate), borderRadius: 10 * u, overflow: 'hidden', background: SOFT, boxShadow: `0 ${16 * u}px ${44 * u}px rgba(12,10,9,.2)` }}>
      {src && <Img src={src} crossOrigin="anonymous" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />}
      {cover ? (
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

/** A panel of the editor's form, beside or under the plate. */
function Form({ children }: { children: React.ReactNode }) {
  const { u, form } = useEditorLayout()
  return (
    <div style={{ ...at(form), background: '#fff', border: `${2 * u}px solid ${LINE}`, borderRadius: 24 * u, padding: 32 * u,
      display: 'flex', flexDirection: 'column', gap: 18 * u, overflow: 'hidden' }}>{children}</div>
  )
}

function Label({ children }: { children: React.ReactNode }) {
  const { u, k } = useEditorLayout()
  return <div style={{ fontSize: 24 * u * k, fontWeight: 600, color: '#78716c' }}>{children}</div>
}

function Button({ children, primary = false, pressed = false }: { children: React.ReactNode; primary?: boolean; pressed?: boolean }) {
  const { u, k } = useEditorLayout()
  return (
    <div style={{ alignSelf: 'flex-start', background: primary ? INK : '#fff', color: primary ? '#fff' : INK, border: `${2 * u}px solid ${primary ? INK : LINE}`,
      borderRadius: 999, padding: `${14 * u}px ${28 * u}px`, fontSize: 26 * u * k, fontWeight: 600, transform: `scale(${pressed ? 0.94 : 1})` }}>{children}</div>
  )
}

/** A pointer that glides from one spot of the screen to another (fractions of the width and height). */
function Glide({ frame, from, to, a, b, press }: { frame: number; from: [number, number]; to: [number, number]; a: number; b: number; press?: boolean }) {
  const { u, width, height } = useUnit()
  const t = ease(frame, a, b)
  return <Pointer u={u} style={{ left: (from[0] + (to[0] - from[0]) * t) * width, top: (from[1] + (to[1] - from[1]) * t) * height,
    transform: `scale(${press ? 0.85 : 1})` }} />
}

/** The page editor opens: the strip of pages arrives and a page is chosen. */
export function EditorOpenScene({ dur, caption, step, tome }: Base & { tome: VideoTome }) {
  const frame = useCurrentFrame()
  const { wide, strip, plate, width, height } = useEditorLayout()
  const pick = frame > dur * 0.5 ? 2 : -1
  const open = ease(frame, dur * 0.52, dur * 0.66)
  const thumb: [number, number] = wide ? [(strip.left + strip.width * 0.6) / width, (strip.top + strip.width * 1.24 * 2.3) / height]
    : [(strip.left + (strip.width / 6) * 2.5) / width, (strip.top + strip.height * 0.6) / height]
  return (
    <EditorShell dur={dur} caption={caption} step={step}>
      <Strip tome={tome} on={pick} appear={Math.min(1, frame / 30)} />
      <div style={{ position: 'absolute', inset: 0, opacity: open, transform: `translateY(${(1 - open) * 30}px)` }}><Plate tome={tome} /></div>
      {open < 0.01 && <div style={{ ...at(plate), borderRadius: 10, border: `3px dashed ${LINE}` }} />}
      <Glide frame={frame} from={[0.7, 0.85]} to={thumb} a={dur * 0.15} b={dur * 0.45} press={frame > dur * 0.46 && frame < dur * 0.52} />
    </EditorShell>
  )
}

/** «Mover textos»: the question card is dragged down the page, its outline dashed while it moves. */
export function EditorMoveScene({ dur, caption, step, tome }: Base & { tome: VideoTome }) {
  const frame = useCurrentFrame()
  const { u, k, plate, width, height } = useEditorLayout()
  const move = ease(frame, dur * 0.3, dur * 0.7)
  const dragging = frame > dur * 0.25 && frame < dur * 0.72
  const qTop = 4 + move * 52
  const grab: [number, number] = [(plate.left + plate.width * 0.5) / width, (plate.top + plate.height * (qTop / 100 + 0.04)) / height]
  return (
    <EditorShell dur={dur} caption={caption} step={step}>
      <Strip tome={tome} on={2} />
      <Plate tome={tome} qTop={qTop} dragging={dragging} />
      <Form>
        <Label>Vista</Label>
        <div style={{ display: 'flex', gap: 12 * u }}>
          <div style={{ background: SOFT, color: ACCENT, borderRadius: 999, padding: `${10 * u}px ${22 * u}px`, fontSize: 24 * u * k, fontWeight: 700 }}>Mover textos</div>
          <div style={{ border: `${2 * u}px solid ${LINE}`, borderRadius: 999, padding: `${10 * u}px ${22 * u}px`, fontSize: 24 * u * k }}>Vista de impresión</div>
        </div>
        <div style={{ fontSize: 24 * u * k, color: '#78716c', lineHeight: 1.4 }}>Arrastra la pregunta, los datos o el reto con el dedo o el cursor.</div>
      </Form>
      {frame < dur * 0.3
        ? <Glide frame={frame} from={[0.85, 0.8]} to={grab} a={0} b={dur * 0.25} />
        : <Pointer u={u} style={{ left: grab[0] * width, top: grab[1] * height, transform: `scale(${dragging ? 0.85 : 1})` }} />}
    </EditorShell>
  )
}

/** A fact removed with its ✕ and a new one added with «+ Añadir dato», typed and appearing on the plate. */
export function EditorFactsScene({ dur, caption, step, tome, text }: Base & { tome: VideoTome; text: string }) {
  const frame = useCurrentFrame()
  const { u, k, form, width, height } = useEditorLayout()
  const facts = (tome.plate?.notes ?? ['La Luna refleja la luz del Sol.', 'Tarda 28 días en dar una vuelta.']).slice(0, 2)
  const removed = frame > dur * 0.3
  const gone = ease(frame, dur * 0.3, dur * 0.38)
  const adding = frame > dur * 0.5
  const typedFact = typed(text, frame, dur * 0.55, dur * 0.85)
  const row = 58 * u * k
  const xAt: [number, number] = [(form.left + form.width - 70 * u) / width, (form.top + 32 * u + 40 * u * k + row * 1.2) / height]
  const addAt: [number, number] = [(form.left + 120 * u) / width, (form.top + 32 * u + 40 * u * k + row * 2.4) / height]
  return (
    <EditorShell dur={dur} caption={caption} step={step}>
      <Strip tome={tome} on={2} />
      <Plate tome={tome} notes={facts} hidden={removed ? [1] : []} fresh={adding ? typedFact || ' ' : undefined} freshIn={ease(frame, dur * 0.85, dur * 0.92)} />
      <Form>
        <Label>Datos</Label>
        {facts.map((n, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12 * u, opacity: i === 1 ? 1 - gone : 1, height: i === 1 && removed ? row * (1 - gone) : undefined }}>
            <div style={{ flex: 1, border: `${2 * u}px solid ${LINE}`, borderRadius: 12 * u, padding: `${10 * u}px ${16 * u}px`, fontSize: 24 * u * k,
              whiteSpace: 'nowrap', overflow: 'hidden' }}>{n}</div>
            <span style={{ fontSize: 28 * u * k, fontWeight: 700, color: '#78716c' }}>✕</span>
          </div>
        ))}
        {adding ? (
          <div style={{ border: `${2 * u}px solid ${ACCENT}`, borderRadius: 12 * u, padding: `${10 * u}px ${16 * u}px`, fontSize: 24 * u * k, minHeight: 30 * u * k }}>
            {typedFact}<span style={{ display: 'inline-block', width: 3 * u, height: 28 * u * k, background: ACCENT, marginLeft: 3 * u, verticalAlign: 'middle' }} />
          </div>
        ) : <Button pressed={frame > dur * 0.46}>+ Añadir dato</Button>}
      </Form>
      {frame < dur * 0.32
        ? <Glide frame={frame} from={[0.8, 0.9]} to={xAt} a={0} b={dur * 0.26} press={frame > dur * 0.26} />
        : <Glide frame={frame} from={xAt} to={addAt} a={dur * 0.34} b={dur * 0.45} press={frame > dur * 0.45 && frame < dur * 0.5} />}
    </EditorShell>
  )
}

/** «Repintar esta ilustración»: what to change is typed, the button pressed, the picture painted again. */
export function EditorRepaintScene({ dur, caption, step, tome, text }: Base & { tome: VideoTome; text: string }) {
  const frame = useCurrentFrame()
  const { u, k, plate, form, width, height } = useEditorLayout()
  const ask = typed(text, frame, dur * 0.12, dur * 0.45)
  const pressed = frame > dur * 0.52 && frame < dur * 0.58
  const painting = ease(frame, dur * 0.58, dur * 0.66) * (1 - ease(frame, dur * 0.82, dur * 0.9))
  const swapped = frame > dur * 0.8
  const next = tome.pages.find((p) => p !== tome.plate?.image) ?? tome.cover ?? undefined
  const button: [number, number] = [(form.left + 140 * u) / width, (form.top + form.height - 90 * u) / height]
  return (
    <EditorShell dur={dur} caption={caption} step={step}>
      <Strip tome={tome} on={2} />
      <Plate tome={tome} image={swapped ? next : undefined} />
      <div style={{ ...at(plate), borderRadius: 10 * u, background: `rgba(255,255,255,${0.75 * painting})`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ opacity: painting, background: '#fff', borderRadius: 999, padding: `${14 * u}px ${26 * u}px`, fontSize: 28 * u * k, fontWeight: 600,
          display: 'flex', gap: 12 * u, alignItems: 'center' }}>
          <span style={{ width: 16 * u, height: 16 * u, borderRadius: 99, background: '#c98a12' }} />Pintando la ilustración…</div>
      </div>
      <Form>
        <Label>Repintar esta ilustración</Label>
        <div style={{ flex: 1, border: `${2 * u}px solid ${ACCENT}`, borderRadius: 14 * u, padding: 18 * u, fontSize: 26 * u * k, lineHeight: 1.4 }}>
          {ask}<span style={{ display: 'inline-block', width: 3 * u, height: 30 * u * k, background: ACCENT, marginLeft: 3 * u, verticalAlign: 'middle' }} />
        </div>
        <Button pressed={pressed}>Repintar (1 crédito)</Button>
      </Form>
      <Glide frame={frame} from={[0.9, 0.95]} to={button} a={dur * 0.4} b={dur * 0.52} press={pressed} />
    </EditorShell>
  )
}

/** The cover in the editor: the name line and the age badge switched off with a click each. */
export function EditorCoverScene({ dur, caption, step, tome }: Base & { tome: VideoTome }) {
  const frame = useCurrentFrame()
  const { u, k, form, width, height } = useEditorLayout()
  const nameOff = ease(frame, dur * 0.35, dur * 0.42)
  const ageOff = ease(frame, dur * 0.65, dur * 0.72)
  const row = (i: number): [number, number] => [(form.left + 50 * u) / width, (form.top + 32 * u + 50 * u * k + i * 64 * u * k) / height]
  const box = (on: boolean) => (
    <span style={{ width: 34 * u * k, height: 34 * u * k, borderRadius: 8 * u, flex: 'none', border: `${3 * u}px solid ${INK}`, background: on ? INK : '#fff',
      color: '#fff', fontSize: 24 * u * k, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{on ? '✓' : ''}</span>
  )
  return (
    <EditorShell dur={dur} caption={caption} step={step}>
      <Strip tome={tome} on={0} />
      <Plate tome={tome} cover nameLine={1 - nameOff} age={1 - ageOff} />
      <Form>
        <Label>Qué más lleva la portada</Label>
        {[['Línea «Nombre»', nameOff < 0.5], ['«Elaborado por»', true], ['Sello de edad', ageOff < 0.5]].map(([l, on]) => (
          <div key={String(l)} style={{ display: 'flex', alignItems: 'center', gap: 16 * u, fontSize: 26 * u * k, fontWeight: 500 }}>{box(Boolean(on))}{l}</div>
        ))}
      </Form>
      {frame < dur * 0.45
        ? <Glide frame={frame} from={[0.85, 0.9]} to={row(0)} a={dur * 0.1} b={dur * 0.33} press={frame > dur * 0.33 && frame < dur * 0.4} />
        : <Glide frame={frame} from={row(0)} to={row(2)} a={dur * 0.45} b={dur * 0.62} press={frame > dur * 0.62 && frame < dur * 0.7} />}
    </EditorShell>
  )
}

/** «Guardar cambios»: saved, and the next PDF carries every change. */
export function EditorSaveScene({ dur, caption, step, tome }: Base & { tome: VideoTome }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const { u, k, form, width, height } = useEditorLayout()
  const pressed = frame > dur * 0.35 && frame < dur * 0.42
  const saved = frame > dur * 0.42
  const pop = spring({ frame: frame - dur * 0.55, fps, config: { damping: 12 } })
  const button: [number, number] = [(form.left + 150 * u) / width, (form.top + 80 * u) / height]
  return (
    <EditorShell dur={dur} caption={caption} step={step}>
      <Strip tome={tome} on={2} />
      <Plate tome={tome} qTop={56} />
      <Form>
        <Button primary pressed={pressed}>{saved ? 'Guardado' : 'Guardar cambios'}</Button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 * u, fontSize: 26 * u * k, color: OK, fontWeight: 600, opacity: saved ? 1 : 0 }}>
          ✓ El próximo PDF ya lo incluye</div>
        <div style={{ alignSelf: 'flex-start', background: OK, color: '#fff', borderRadius: 999, padding: `${12 * u}px ${24 * u}px`, fontSize: 28 * u * k,
          fontWeight: 700, transform: `scale(${pop})` }}>PDF ✓</div>
      </Form>
      <Glide frame={frame} from={[0.85, 0.9]} to={button} a={dur * 0.1} b={dur * 0.33} press={pressed} />
    </EditorShell>
  )
}
