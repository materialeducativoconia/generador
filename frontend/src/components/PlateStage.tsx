import { useRef } from 'react'
import { themeVars, useThemeFonts } from '../lib/themes'
import type { Design, PlatePlace } from '../lib/types'

type Key = keyof PlatePlace
type Spot = string | null

const SPOTS: Record<string, React.CSSProperties> = {  // backend tome.html.j2: .plate .pn.n1 … n4
  n1: { left: 'calc(var(--mm) * 5)', top: '27%' },
  n2: { right: 'calc(var(--mm) * 5)', top: '27%' },
  n3: { left: 'calc(var(--mm) * 5)', top: '50%' },
  n4: { right: 'calc(var(--mm) * 5)', top: '50%' },
}
const plain = (t: string) => t.replace(/\*\*?([^*]+)\*\*?/g, '$1')

/** A bleed plate laid out as the PDF prints it (same millimetres, fonts and colours), its texts dragged with a finger
 * or the cursor. The words follow the form as the user types; positions are % of the page, as the PDF reads them. */
export function PlateStage({ picture, design, kicker, narration, question, answer, notes, find, spots, low, place, onPlace }: {
  picture: string; design: Design | null | undefined; kicker?: string; narration?: string; question?: string; answer?: string
  notes: string[]; find?: string; spots?: Spot[]; low?: boolean; place: PlatePlace; onPlace: (p: PlatePlace) => void
}) {
  useThemeFonts(design)
  const stage = useRef<HTMLDivElement>(null)
  const drag = useRef<{ key: Key; dx: number; dy: number; wide: boolean } | null>(null)

  const start = (key: Key, wide: boolean) => (e: React.PointerEvent<HTMLElement>) => {
    if (e.button !== 0) return
    e.stopPropagation()
    const el = e.currentTarget.getBoundingClientRect()
    drag.current = { key, dx: e.clientX - el.left, dy: e.clientY - el.top, wide }
    stage.current?.setPointerCapture(e.pointerId)
  }
  const move = (e: React.PointerEvent<HTMLDivElement>) => {
    const d = drag.current
    const box = stage.current?.getBoundingClientRect()
    if (!d || !box) return
    const el = stage.current!.querySelector<HTMLElement>(`[data-k="${d.key}"]`)?.getBoundingClientRect()
    const w = el?.width ?? 0, h = el?.height ?? 0
    const x = Math.min(Math.max(e.clientX - box.left - d.dx, 0), box.width - w)
    const y = Math.min(Math.max(e.clientY - box.top - d.dy, 0), box.height - h)
    const pct = (v: number, of: number) => Math.round((v / of) * 1000) / 10
    onPlace({ ...place, [d.key]: { x: d.wide ? 0 : pct(x, box.width), y: pct(y, box.height) } })
  }
  const end = () => { drag.current = null }

  const story = narration != null
  const floating = notes.map((n, i) => ({ n, i, key: `n${i}` as Key }))
    .filter(({ n, i, key }) => n.trim() && (place[key] || spots?.[i]))
  const carded = notes.map((n, i) => ({ n, i, key: `n${i}` as Key }))
    .filter(({ n, i, key }) => n.trim() && !place[key] && !spots?.[i])
  const at = (key: Key): React.CSSProperties | undefined => place[key] && { left: `${place[key]!.x}%`, top: `${place[key]!.y}%`, right: 'auto' }

  return (
    <div ref={stage} className="plate-stage" style={themeVars(design).style}
      onPointerMove={move} onPointerUp={end} onPointerCancel={end}>
      <img src={picture} alt="" draggable={false} />
      <div data-k="q" className="ps-q movable" onPointerDown={start('q', true)}
        style={place.q ? { top: `${place.q.y}%` } : low ? { top: 'auto', bottom: `calc(var(--mm) * ${find ? 27 : 9})` } : undefined}>
        {kicker && <div className="ps-k">{kicker}</div>}
        {story ? <p className="ps-nar">{plain(narration)}</p> : <>
          <h3>{plain(question || '')}</h3>
          {answer && <p>{plain(answer)}</p>}
        </>}
        {carded.length > 0 && <ul>{carded.map(({ n, key }) => (
          <li key={key} data-k={key} className="movable" onPointerDown={start(key, false)}>{plain(n)}</li>))}</ul>}
      </div>
      {floating.map(({ n, i, key }) => (
        <div key={key} data-k={key} className="ps-n movable" onPointerDown={start(key, false)}
          style={at(key) ?? SPOTS[spots?.[i] ?? ''] ?? SPOTS.n1}>{plain(n)}</div>
      ))}
      {find?.trim() && (
        <div data-k="f" className="ps-f movable" onPointerDown={start('f', true)}
          style={place.f ? { top: `${place.f.y}%`, bottom: 'auto' } : undefined}>
          <b>Observa y encuentra:</b> {plain(find.replace(/^\s*observa y encuentra:?\s*/i, ''))}
        </div>
      )}
    </div>
  )
}
