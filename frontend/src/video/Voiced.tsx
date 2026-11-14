import { Audio } from '@remotion/media'
import { AbsoluteFill, Sequence, useVideoConfig } from 'remotion'
import { timeline, type Storyboard } from './spec'

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

/** The video with its voiceover: each line starts with its scene, or right after the line before if that one runs
 * long, and is never cut by the next; only the end of the video cuts it. */
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
  return (
    <AbsoluteFill>
      <Video {...props} />
      {placed.map(({ c, from, frames }) => frames > 0 && (
        <Sequence key={c.url} from={from} durationInFrames={frames} layout="none">
          <Audio src={c.url} />
        </Sequence>
      ))}
    </AbsoluteFill>
  )
}
