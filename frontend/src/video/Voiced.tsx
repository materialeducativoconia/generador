import { Audio } from '@remotion/media'
import { AbsoluteFill, Sequence, useVideoConfig } from 'remotion'
import { audioFile, timeline, type Storyboard } from './spec'

/** A voiceover clip (backend /voice): the scene it is read over (-1: the whole video) and how long it lasts. */
export type VoiceClip = { scene: number; url: string; seconds?: number | null }

const GAP = 4  // frames of breath between two lines

/** How long a clip lasts, from its WAV's size (24 kHz, 16-bit, mono, 44-byte header) when the server did not say. */
export async function withLengths(clips: VoiceClip[]): Promise<VoiceClip[]> {
  return Promise.all(clips.map(async (c) => {
    if (c.seconds) return c
    const size = Number((await fetch(c.url, { method: 'HEAD' }).catch(() => null))?.headers.get('content-length') ?? 0)
    return { ...c, seconds: size > 44 ? (size - 44) / 48_000 : null }
  }))
}

/** The video with its voiceover, its music and its sound effects. Each line starts with its scene, or right after the
 * line before if that one runs long, and is never cut by the next; only the end of the video cuts it. The music
 * goes down while the voice speaks and fades out at the end; a whoosh marks each cut and a hit the close. */
export function Voiced<P extends object>({ Video, props, board, clips }: { Video: React.ComponentType<P>; props: P
  board: Storyboard | null; clips: VoiceClip[] }) {
  const { durationInFrames, fps } = useVideoConfig()
  const steps = board ? timeline(board) : []
  let free = 0
  const placed = clips.map((c) => {
    const from = Math.max(c.scene < 0 ? 0 : steps[c.scene]?.from ?? 0, free)
    const length = c.seconds ? Math.ceil(c.seconds * fps) : durationInFrames
    free = from + length + GAP
    return { c, from, frames: Math.min(length, durationInFrames - from) }
  })
  const spoken = placed.filter((p) => p.frames > 0).map((p) => [p.from, p.from + p.frames] as const)
  return (
    <AbsoluteFill>
      <Video {...props} />
      {board?.music && <Audio src={audioFile(`${board.music}.mp3`)} loop volume={(f) => musicVolume(f, durationInFrames, spoken)} />}
      {board?.sfx !== false && steps.map(({ scene, from }, i) => {
        const cue = scene.type === 'cta' ? 'hit' : i > 0 && board?.transition !== 'corte' ? 'whoosh' : null
        const at = cue === 'whoosh' ? Math.max(0, from - 7) : from
        return cue && (
          <Sequence key={`sfx-${i}`} from={at} durationInFrames={Math.round(fps * (cue === 'hit' ? 1.1 : 0.45))} layout="none">
            <Audio src={audioFile(`${cue}.wav`)} volume={cue === 'hit' ? 0.45 : 0.28} />
          </Sequence>
        )
      })}
      {placed.map(({ c, from, frames }) => frames > 0 && (
        <Sequence key={c.url} from={from} durationInFrames={frames} layout="none">
          <Audio src={c.url} />
        </Sequence>
      ))}
    </AbsoluteFill>
  )
}

const MUSIC_UP = 0.24  // the music alone
const MUSIC_UNDER = 0.08  // under the voice
const RAMP = 8  // frames the music takes to go down or up around a line

/** The music's volume at frame `f`: in over half a second, down under each spoken line, out over the last second and a half. */
export function musicVolume(f: number, total: number, spoken: (readonly [number, number])[]) {
  const near = spoken.reduce((d, [a, b]) => Math.min(d, f < a ? a - f : f > b ? f - b : 0), Infinity)
  const level = MUSIC_UNDER + (MUSIC_UP - MUSIC_UNDER) * Math.min(1, near / RAMP)
  return level * Math.min(1, f / 15) * Math.min(1, Math.max(0, (total - f) / 45))
}
