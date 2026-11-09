import { AbsoluteFill, Sequence } from 'remotion'
import { ComposeScene, CoverScene, CtaScene, EditorCoverScene, EditorFactsScene, EditorMoveScene, EditorOpenScene, EditorRepaintScene,
  EditorSaveScene, ListScene, NumberScene, PagesScene, PdfScene, PlanScene, TitleScene, VersusScene } from './scenes'
import { FONT, LOOKS, timeline, type Look, type Scene, type StoryboardProps, type VideoTome } from './spec'

/** Any video the director wrote: its scenes one after another, each the real app animated with the tome. */
export function StoryboardVideo({ board, tome }: StoryboardProps) {
  return (
    <AbsoluteFill style={{ background: '#ffffff', fontFamily: FONT, color: '#0c0a09' }}>
      {timeline(board).map(({ scene, from, frames, step }, i) => (
        <Sequence key={i} from={from} durationInFrames={frames}><SceneView scene={scene} dur={frames} step={step} tome={tome} look={board.look ?? 'claro'} /></Sequence>
      ))}
    </AbsoluteFill>
  )
}

function SceneView({ scene, dur, step, tome, look }: { scene: Scene; dur: number; step?: number; tome: VideoTome; look: Look }) {
  const p = { dur, caption: scene.caption, step, tome, text: scene.text, look: LOOKS[look] }
  switch (scene.type) {
    case 'title': return <TitleScene {...p} />
    case 'list': return <ListScene {...p} />
    case 'versus': return <VersusScene {...p} />
    case 'number': return <NumberScene {...p} />
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
