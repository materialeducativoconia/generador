import { AbsoluteFill, Easing, Img, Sequence, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion'
import { FONT, SITE, type TopicToBookProps, type VideoTome } from './spec'

/** «De un tema a un libro en 30 s»: the app's own flow, animated with a real tome. Drawn with transforms, opacity
 * and plain boxes only, which the in-browser renderer (@remotion/web-renderer) paints exactly as the preview. */


const INK = '#0c0a09'
const ACCENT = '#5b4cf0'
const SOFT = '#f4f2ff'
// Where each scene starts (frames): hook, composer, plan, cover, pages, pdf, cta.
const AT = { hook: 0, typing: 90, plan: 240, cover: 360, pages: 510, pdf: 690, cta: 810 }

function useUnit() {
  const { width, height } = useVideoConfig()
  const u = Math.min(width, height) / 1080
  // k: text on a phone screen is read at arm's length, so the vertical cut sets it larger.
  return { u, k: width >= height ? 1 : 1.3, wide: width > height, width, height }
}

const ease = (f: number, from: number, to: number, out: [number, number] = [0, 1]) =>
  interpolate(f, [from, to], out, { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.bezier(0.22, 1, 0.36, 1) })

export function TopicToBook({ script, tome }: TopicToBookProps) {
  return (
    <AbsoluteFill style={{ background: '#ffffff', fontFamily: FONT, color: INK }}>
      <Sequence from={AT.hook} durationInFrames={AT.typing - AT.hook}><Hook text={script.hook} /></Sequence>
      <Sequence from={AT.typing} durationInFrames={AT.plan - AT.typing}><Composer request={script.request} /></Sequence>
      <Sequence from={AT.plan} durationInFrames={AT.cover - AT.plan}><Plan tome={tome} caption={script.plan} /></Sequence>
      <Sequence from={AT.cover} durationInFrames={AT.pages - AT.cover}><Cover tome={tome} caption={script.cover} /></Sequence>
      <Sequence from={AT.pages} durationInFrames={AT.pdf - AT.pages}><Pages tome={tome} caption={script.pages} /></Sequence>
      <Sequence from={AT.pdf} durationInFrames={AT.cta - AT.pdf}><Pdf tome={tome} caption={script.pdf} /></Sequence>
      <Sequence from={AT.cta}><Cta text={script.cta} /></Sequence>
    </AbsoluteFill>
  )
}

/** The scroll-stopper: the words land one by one, the last one in the accent colour. */
function Hook({ text }: { text: string }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const { u, wide } = useUnit()
  const words = text.split(/\s+/).filter(Boolean)
  const out = ease(frame, 78, 90, [1, 0])
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', padding: 90 * u, opacity: out }}>
      <div style={{ fontSize: (wide ? 104 : 112) * u, fontWeight: 700, lineHeight: 1.08, letterSpacing: '-0.035em', textAlign: 'center', maxWidth: wide ? 1500 * u : undefined }}>
        {words.map((w, i) => {
          const s = spring({ frame: frame - 4 - i * 4, fps, config: { damping: 14, mass: 0.6 } })
          return (
            <span key={i} style={{ display: 'inline-block', marginRight: '0.26em', opacity: s, transform: `translateY(${(1 - s) * 40 * u}px)`,
              color: i === words.length - 1 ? ACCENT : INK }}>{w}</span>
          )
        })}
      </div>
    </AbsoluteFill>
  )
}

/** The app's composer: the request typed letter by letter, then «Crear mi libro» pressed. */
function Composer({ request }: { request: string }) {
  const frame = useCurrentFrame()
  const { u, k, wide } = useUnit()
  const shown = Math.round(interpolate(frame, [12, 105], [0, request.length], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }))
  const enter = ease(frame, 0, 14)
  const press = frame > 118 && frame < 128 ? 0.94 : 1
  const pointer = ease(frame, 100, 118)
  const out = ease(frame, 138, 150, [1, 0])
  const w = (wide ? 1100 : 960) * u
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', background: SOFT, opacity: out }}>
      <div style={{ width: w, transform: `translateY(${(1 - enter) * 60 * u}px)`, opacity: enter }}>
        <div style={{ fontSize: 46 * u * k, fontWeight: 700, letterSpacing: '-0.02em', marginBottom: 28 * u }}>¿Qué libro quieres crear?</div>
        <div style={{ background: '#fff', borderRadius: 32 * u, padding: 40 * u, boxShadow: `0 ${24 * u}px ${60 * u}px rgba(12,10,9,.12)`,
          border: `${2 * u}px solid #e7e5e2`, minHeight: 300 * u, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div style={{ fontSize: 40 * u * k, lineHeight: 1.4, fontWeight: 500 }}>
            {request.slice(0, shown)}
            <span style={{ display: 'inline-block', width: 4 * u, height: 46 * u * k, background: ACCENT, marginLeft: 4 * u, verticalAlign: 'middle',
              opacity: Math.floor(frame / 8) % 2 === 0 || shown < request.length ? 1 : 0 }} />
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 36 * u, position: 'relative' }}>
            <div style={{ background: INK, color: '#fff', fontSize: 34 * u * k, fontWeight: 600, padding: `${22 * u}px ${40 * u}px`, borderRadius: 999,
              transform: `scale(${press})` }}>Crear mi libro</div>
            <Pointer u={u} style={{ position: 'absolute', right: 70 * u, top: 50 * u, opacity: pointer,
              transform: `translate(${(1 - pointer) * 260 * u}px, ${(1 - pointer) * 180 * u}px) scale(${press})` }} />
          </div>
        </div>
      </div>
    </AbsoluteFill>
  )
}

function Pointer({ u, style }: { u: number; style: React.CSSProperties }) {
  return (
    <svg width={56 * u} height={56 * u} viewBox="0 0 24 24" style={style}>
      <path d="M5 3l14 8-6 1.5L10 19z" fill={INK} stroke="#fff" strokeWidth="1.4" strokeLinejoin="round" />
    </svg>
  )
}

function Caption({ text, at = 6 }: { text: string; at?: number }) {
  const frame = useCurrentFrame()
  const { u, wide } = useUnit()
  const s = ease(frame, at, at + 12)
  return (
    <div style={{ position: 'absolute', left: 0, right: 0, bottom: (wide ? 48 : 170) * u, display: 'flex', justifyContent: 'center',
      opacity: s, transform: `translateY(${(1 - s) * 24 * u}px)` }}>
      <div style={{ background: INK, color: '#fff', fontSize: (wide ? 50 : 56) * u, fontWeight: 700, letterSpacing: '-0.02em',
        padding: `${18 * u}px ${34 * u}px`, borderRadius: 22 * u, maxWidth: '86%', textAlign: 'center', lineHeight: 1.15 }}>{text}</div>
    </div>
  )
}

/** The Architect's plan: the book's sections arrive one after another. */
function Plan({ tome, caption }: { tome: VideoTome; caption: string }) {
  const frame = useCurrentFrame()
  const { u, k, wide } = useUnit()
  const sections = tome.sections.slice(0, wide ? 5 : 6)
  const out = ease(frame, 108, 120, [1, 0])
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: wide ? 'center' : 'flex-start', paddingTop: wide ? 0 : 300 * u, opacity: out }}>
      <div style={{ width: (wide ? 1100 : 960) * u }}>
        <div style={{ fontSize: 28 * u * k, fontWeight: 700, letterSpacing: '.14em', textTransform: 'uppercase', color: ACCENT, opacity: ease(frame, 0, 10) }}>
          {tome.kind}{tome.audience ? ` · ${tome.audience}` : ''}</div>
        <div style={{ fontSize: 60 * u * k, fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1.08, margin: `${14 * u}px 0 ${36 * u}px`,
          opacity: ease(frame, 2, 14) }}>{tome.title}</div>
        {sections.map((t, i) => {
          const s = ease(frame, 14 + i * 9, 28 + i * 9)
          return (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 24 * u, padding: `${20 * u}px ${26 * u}px`, marginBottom: 16 * u,
              background: '#fff', border: `${2 * u}px solid #e7e5e2`, borderRadius: 22 * u, opacity: s, transform: `translateX(${(1 - s) * 80 * u}px)` }}>
              <span style={{ width: 56 * u, height: 56 * u, borderRadius: 16 * u, background: SOFT, color: ACCENT, fontWeight: 700, fontSize: 30 * u,
                display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 'none' }}>{i + 1}</span>
              <span style={{ fontSize: 36 * u * k, fontWeight: 600, lineHeight: 1.2 }}>{t}</span>
            </div>
          )
        })}
      </div>
      <Caption text={caption} at={20} />
    </AbsoluteFill>
  )
}

/** The cover being painted: a paper card wipes away from the art, then the book settles. */
function Cover({ tome, caption }: { tome: VideoTome; caption: string }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const { u, height, wide } = useUnit()
  const h = height * (wide ? 0.64 : 0.56)
  const w = h * (170 / 210)
  const pop = spring({ frame, fps, config: { damping: 16 } })
  const wipe = ease(frame, 18, 78)
  const out = ease(frame, 138, 150, [1, 0])
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', background: SOFT, opacity: out }}>
      <div style={{ position: 'relative', width: w, height: h, borderRadius: 18 * u, overflow: 'hidden', marginTop: wide ? -40 * u : -160 * u,
        transform: `scale(${0.85 + pop * 0.15}) rotate(${(1 - pop) * -4}deg)`, boxShadow: `0 ${30 * u}px ${70 * u}px rgba(12,10,9,.25)` }}>
        {tome.cover ? <Img src={tome.cover} crossOrigin="anonymous" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          : <div style={{ width: '100%', height: '100%', background: ACCENT }} />}
        <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: `${(1 - wipe) * 100}%`, background: '#fff' }} />
        <div style={{ position: 'absolute', left: 0, right: 0, bottom: `${(1 - wipe) * 100}%`, height: 10 * u, background: ACCENT, opacity: wipe < 1 ? 1 : 0 }} />
      </div>
      <div style={{ position: 'absolute', top: (wide ? 50 : 150) * u, background: '#fff', borderRadius: 999, padding: `${14 * u}px ${28 * u}px`,
        fontSize: 30 * u, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 14 * u, opacity: ease(frame, 4, 14) }}>
        <span style={{ width: 18 * u, height: 18 * u, borderRadius: 99, background: wipe < 1 ? '#c98a12' : '#2f8f4e' }} />
        {wipe < 1 ? 'Pintando la portada…' : 'Portada lista'}
      </div>
      <Caption text={caption} at={24} />
    </AbsoluteFill>
  )
}

/** The pages go by like a hand flipping the book: each slides in over the last, with its number. */
function Pages({ tome, caption }: { tome: VideoTome; caption: string }) {
  const frame = useCurrentFrame()
  const { u, height, wide } = useUnit()
  const pages = tome.pages.length ? tome.pages.slice(0, 6) : tome.cover ? [tome.cover] : []
  const each = Math.floor(150 / Math.max(1, pages.length))
  const h = height * (wide ? 0.64 : 0.54)
  const w = h * (170 / 210)
  const out = ease(frame, 168, 180, [1, 0])
  const shown = Math.min(pages.length, Math.floor(frame / each) + 1)
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', opacity: out }}>
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
      <Caption text={caption} at={10} />
    </AbsoluteFill>
  )
}

/** The finished PDF: the book with its badges, ready to print. */
function Pdf({ tome, caption }: { tome: VideoTome; caption: string }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const { u, height, wide } = useUnit()
  const h = height * (wide ? 0.6 : 0.42)
  const w = h * (170 / 210)
  const pop = spring({ frame, fps, config: { damping: 13 } })
  const chips = ['Solucionario', 'Tu nombre y tu logo', 'Listo para imprimir']
  const out = ease(frame, 108, 120, [1, 0])
  return (
    <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center', background: SOFT, opacity: out }}>
      <div style={{ display: 'flex', flexDirection: wide ? 'row' : 'column', alignItems: 'center', gap: 56 * u, marginTop: wide ? -40 * u : -160 * u }}>
        <div style={{ position: 'relative', width: w, height: h, transform: `scale(${0.7 + pop * 0.3})` }}>
          <div style={{ position: 'absolute', inset: 0, transform: `translate(${18 * u}px, ${14 * u}px)`, background: '#ddd8f6', borderRadius: 14 * u }} />
          <div style={{ position: 'absolute', inset: 0, borderRadius: 14 * u, overflow: 'hidden', boxShadow: `0 ${24 * u}px ${60 * u}px rgba(12,10,9,.25)` }}>
            {tome.cover && <Img src={tome.cover} crossOrigin="anonymous" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />}
          </div>
          <div style={{ position: 'absolute', right: -26 * u, top: -26 * u, background: '#2f8f4e', color: '#fff', borderRadius: 999,
            padding: `${14 * u}px ${24 * u}px`, fontSize: 30 * u, fontWeight: 700, transform: `scale(${spring({ frame: frame - 14, fps })})` }}>PDF ✓</div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 * u, alignItems: wide ? 'flex-start' : 'center' }}>
          {chips.map((c, i) => {
            const s = ease(frame, 20 + i * 8, 34 + i * 8)
            return <div key={c} style={{ background: '#fff', border: `${2 * u}px solid #e7e5e2`, borderRadius: 999, padding: `${14 * u}px ${28 * u}px`,
              fontSize: 32 * u, fontWeight: 600, opacity: s, transform: `translateY(${(1 - s) * 20 * u}px)` }}>✓ {c}</div>
          })}
        </div>
      </div>
      <Caption text={caption} at={30} />
    </AbsoluteFill>
  )
}

/** The close: the brand, the call to action and the address. */
function Cta({ text }: { text: string }) {
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
        opacity: ease(frame, 10, 22) }}>{text}</div>
      <div style={{ background: ACCENT, borderRadius: 999, padding: `${18 * u}px ${40 * u}px`, fontSize: 40 * u, fontWeight: 700,
        opacity: ease(frame, 20, 32) }}>{SITE}</div>
    </AbsoluteFill>
  )
}
