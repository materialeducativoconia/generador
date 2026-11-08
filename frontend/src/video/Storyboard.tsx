import { AbsoluteFill, Sequence } from 'remotion'
import { ComposeScene, CoverScene, CtaScene, EditorCoverScene, EditorFactsScene, EditorMoveScene, EditorOpenScene, EditorRepaintScene,
  EditorSaveScene, PagesScene, PdfScene, PlanScene, TitleScene } from './scenes'
import { FONT, timeline, type Scene, type StoryboardProps, type VideoTome } from './spec'

/** Any video the director wrote: its scenes one after another, each the real app animated with the tome. */
export function StoryboardVideo({ board, tome }: StoryboardProps) {
  return (
    <AbsoluteFill style={{ background: '#ffffff', fontFamily: FONT, color: '#0c0a09' }}>
      {timeline(board).map(({ scene, from, frames, step }, i) => (
        <Sequence key={i} from={from} durationInFrames={frames}><SceneView scene={scene} dur={frames} step={step} tome={tome} /></Sequence>
      ))}
    </AbsoluteFill>
  )
}

function SceneView({ scene, dur, step, tome }: { scene: Scene; dur: number; step?: number; tome: VideoTome }) {
  const p = { dur, caption: scene.caption, step, tome, text: scene.text }
  switch (scene.type) {
    case 'title': return <TitleScene {...p} />
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
