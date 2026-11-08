// The promotional videos' data, sizes and font (backend app/marketing.py writes the script).
import { loadFont } from '@remotion/google-fonts/Geist'

export type VideoScript = { hook: string; request: string; plan: string; cover: string; pages: string; pdf: string; cta: string; post?: string; voiceover?: string }
export type VideoTome = { title: string; kind: string; audience: string; cover: string | null; pages: string[]; sections: string[] }
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
