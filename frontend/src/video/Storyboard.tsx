import { AbsoluteFill, Easing, interpolate, Sequence, useCurrentFrame } from 'remotion'
import { ComposeScene, CoverScene, CtaScene, EditorCoverScene, EditorFactsScene, EditorMoveScene, EditorOpenScene, EditorRepaintScene,
  EditorSaveScene, ListScene, NumberScene, PagesScene, PdfScene, PlanScene, ScreenScene, FormatsScene, CharactersScene, TitleScene, VersusScene } from './scenes'
import { FONT, LOOKS, timeline, type Capture, type Look, type Scene, type ShelfBook, type StoryboardProps, type Transition, type VideoTome } from './spec'

/** Any video the director wrote: its scenes one after another, each the real app animated with the tome. */
export function StoryboardVideo({ board, tome, captures = {}, shelf = [] }: StoryboardProps) {
  const look = board.look ?? 'claro'
  const steps = timeline(board)
  return (
    <AbsoluteFill style={{ background: LOOKS[look].bg, fontFamily: FONT, color: '#0c0a09' }}>
      {steps.map(({ scene, from, frames, step }, i) => {
        // Each scene runs on under the next one's entrance, so the length of the video does not change.
        const kind = transitionOf(board.transition ?? 'mixta', i + 1)
        const over = i < steps.length - 1 && kind !== 'corte' ? Math.min(OVER, Math.floor(steps[i + 1].frames / 3)) : 0
        const enter = i > 0 ? transitionOf(board.transition ?? 'mixta', i) : 'corte'
        return (
          <Sequence key={i} from={from} durationInFrames={frames + over}>
            <Move bg={scene.type === 'plan' || scene.type === 'pages' ? '#ffffff' : undefined} enter={enter} exit={over ? kind : 'corte'} frames={frames} over={over}
              enterOver={i > 0 ? Math.min(OVER, Math.floor(frames / 3)) : 0}>
              <SceneView scene={scene} dur={over ? frames + over + 10 : frames} step={step} tome={tome} look={look}
                capture={scene.capture ? captures[scene.capture] : undefined} shelf={shelf} />
            </Move>
          </Sequence>
        )
      })}
    </AbsoluteFill>
  )
}

const OVER = 14  // frames two scenes share while one gives way to the next
const MIXED: Transition[] = ['deslizar', 'zoom', 'barrido']
const transitionOf = (t: Transition, i: number): Transition => t === 'mixta' ? MIXED[i % MIXED.length] : t

/** A scene's entrance (over its first frames) and exit (under the next scene's entrance). */
function Move({ bg, enter, exit, frames, over, enterOver, children }: { bg?: string; enter: Transition; exit: Transition; frames: number; over: number
  enterOver: number; children: React.ReactNode }) {
  const frame = useCurrentFrame()
  const ease = (a: number, b: number) => interpolate(frame, [a, Math.max(a + 1, b)], [0, 1],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.bezier(0.65, 0, 0.35, 1) })
  const e = enterOver && enter !== 'corte' ? ease(0, enterOver) : 1
  const x = over ? ease(frames, frames + over) : 0
  const style: React.CSSProperties = { overflow: 'hidden', background: bg }  // plan and pages draw on the page white
  const transform: string[] = []
  if (e < 1) {
    if (enter === 'deslizar') transform.push(`translateX(${(1 - e) * 100}%)`)
    if (enter === 'zoom') { transform.push(`scale(${1.18 - 0.18 * e})`); style.opacity = e }
    if (enter === 'barrido') style.clipPath = `inset(0 0 0 ${(1 - e) * 100}%)`
  }
  if (x > 0) {
    if (exit === 'deslizar') transform.push(`translateX(${-x * 35}%)`)
    if (exit === 'zoom') transform.push(`scale(${1 + 0.08 * x})`)
    if (exit === 'barrido') style.filter = `brightness(${1 - x * 0.35})`
  }
  if (transform.length) style.transform = transform.join(' ')
  return <AbsoluteFill style={style}>{children}</AbsoluteFill>
}

function SceneView({ scene, dur, step, tome, look, capture, shelf }: { scene: Scene; dur: number; step?: number; tome: VideoTome; look: Look; capture?: Capture; shelf: ShelfBook[] }) {
  const p = { dur, caption: scene.caption, step, tome, text: scene.text, look: LOOKS[look] }
  switch (scene.type) {
    case 'title': return <TitleScene {...p} />
    case 'list': return <ListScene {...p} />
    case 'versus': return <VersusScene {...p} />
    case 'number': return <NumberScene {...p} />
    case 'formats': return <FormatsScene {...p} shelf={shelf} />
    case 'characters': return <CharactersScene {...p} />
    case 'screen': return <ScreenScene {...p} capture={capture} focus={scene.focus ?? 0} />
    case 'compose': return <ComposeScene {...p} />
    case 'plan': return <PlanScene {...p} />
    case 'cover': return <CoverScene {...p} />
    case 'pages': return <PagesScene {...p} />
    case 'pdf': return <PdfScene {...p} />
    case 'editor_open': return <EditorOpenScene {...p} />
    case 'editor_move': return <EditorMoveScene {...p} />
    case 'editor_facts': return <EditorFactsScene {...p} />
    case 'editor_repaint': return <EditorRepaintScene {...p} />
    case 'editor_cover': return <EditorCoverScene {...p} />
    case 'editor_save': return <EditorSaveScene {...p} />
    case 'cta': return <CtaScene {...p} />
  }
}
