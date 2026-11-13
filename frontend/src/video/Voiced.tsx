import { Audio } from '@remotion/media'
import { AbsoluteFill, Sequence, useVideoConfig } from 'remotion'
import { timeline, type Storyboard } from './spec'

/** A voiceover clip (backend /voice): the scene it is read over, or -1 for the whole video. */
export type VoiceClip = { scene: number; url: string }

/** The video with its voiceover: each clip starts with its scene and lasts until the next clip begins. */
export function Voiced<P extends object>({ Video, props, board, clips }: { Video: React.ComponentType<P>; props: P
  board: Storyboard | null; clips: VoiceClip[] }) {
  const { durationInFrames } = useVideoConfig()
  const steps = board ? timeline(board) : []
  const starts = clips.map((c) => (c.scene < 0 ? 0 : steps[c.scene]?.from ?? 0))
  return (
    <AbsoluteFill>
      <Video {...props} />
      {clips.map((c, i) => {
        const from = starts[i]
        const until = Math.min(durationInFrames, ...starts.filter((s) => s > from))
        return until > from && (
          <Sequence key={c.url} from={from} durationInFrames={until - from} layout="none">
            <Audio src={c.url} />
          </Sequence>
        )
      })}
    </AbsoluteFill>
  )
}
