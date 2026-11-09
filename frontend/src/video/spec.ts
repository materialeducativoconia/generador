// The promotional videos' data, sizes and font (backend app/marketing.py writes the script).
import { loadFont } from '@remotion/google-fonts/Geist'

export type VideoScript = { hook: string; request: string; plan: string; cover: string; pages: string; pdf: string; cta: string; post?: string; voiceover?: string }
export type VideoTome = {
  title: string; kind: string; audience: string; cover: string | null; pages: string[]; sections: string[]
  plate?: { image: string; question: string; answer?: string; notes: string[]; find?: string }  // one real page, for the editor scenes
}
export type TopicToBookProps = { script: VideoScript; tome: VideoTome }

export const FPS = 30
export const DURATION = 30 * FPS
export const SIZES = { '9:16': [1080, 1920], '1:1': [1080, 1080], '16:9': [1920, 1080] } as const
export const SITE = 'docs.jelyx.app'

// The in-browser renderer does not wait for a font requested at import time: await fontsReady() before each render,
// or its first frame is drawn in the fallback font.
const geist = loadFont('normal', { weights: ['500', '600', '700'], subsets: ['latin', 'latin-ext'] })
export const FONT = `${geist.fontFamily}, system-ui, sans-serif`
export const fontsReady = geist.waitUntilDone

// The director's storyboard (backend app/marketing.py Storyboard): any video, scene by scene.
export type SceneType = 'title' | 'compose' | 'plan' | 'cover' | 'pages' | 'pdf' | 'editor_open' | 'editor_move' | 'editor_facts'
  | 'editor_repaint' | 'editor_cover' | 'editor_save' | 'list' | 'versus' | 'number' | 'cta'
export type Scene = { type: SceneType; seconds: number; caption: string; voice: string; text: string }
export type VideoKind = 'marketing' | 'explainer' | 'tutorial'
export type Look = 'claro' | 'oscuro' | 'color'
export type Storyboard = { kind: VideoKind; duration: 15 | 30 | 45 | 60; title: string; scenes: Scene[]; post: string; structure?: string; look?: Look }
/** The text scenes' colours: background, ink and the accent of the key word. */
export const LOOKS: Record<Look, { label: string; bg: string; ink: string; accent: string }> = {
  claro: { label: 'Claro', bg: '#ffffff', ink: '#0c0a09', accent: '#5b4cf0' },
  oscuro: { label: 'Oscuro', bg: '#0c0a09', ink: '#ffffff', accent: '#a99cff' },
  color: { label: 'Color', bg: '#5b4cf0', ink: '#ffffff', accent: '#ffd166' },
}
export type StoryboardProps = { board: Storyboard; tome: VideoTome }

export const SCENES: Record<SceneType, { label: string; types?: string }> = {
  title: { label: 'Texto grande' }, compose: { label: 'Escribir el pedido', types: 'Pedido que se escribe' },
  plan: { label: 'El plan del libro' }, cover: { label: 'La portada se pinta' }, pages: { label: 'Las páginas pasan' },
  pdf: { label: 'El PDF listo' }, editor_open: { label: 'Editor: abrir una página' }, editor_move: { label: 'Editor: mover textos' },
  editor_facts: { label: 'Editor: quitar y añadir datos', types: 'Dato nuevo' },
  editor_repaint: { label: 'Editor: repintar la ilustración', types: 'Qué cambiar' },
  editor_cover: { label: 'Editor: la portada' }, editor_save: { label: 'Editor: guardar' },
  list: { label: 'Lista animada', types: 'Puntos separados por |' }, versus: { label: 'Antes y después', types: 'Antes | después' },
  number: { label: 'Número grande', types: 'El número, p. ej. 5 min' }, cta: { label: 'Cierre' },
}

/** Each scene's first frame and length; tutorial steps numbered (every scene but the title and the close). */
export function timeline(board: Storyboard) {
  let from = 0
  let n = 0
  return board.scenes.map((scene) => {
    const frames = Math.max(15, Math.round(scene.seconds * FPS))
    const step = board.kind === 'tutorial' && scene.type !== 'title' && scene.type !== 'cta' ? ++n : undefined
    const out = { scene, from, frames, step }
    from += frames
    return out
  })
}
export const boardFrames = (board: Storyboard) => timeline(board).reduce((sum, t) => sum + t.frames, 0)
