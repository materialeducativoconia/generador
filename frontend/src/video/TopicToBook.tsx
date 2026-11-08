import { AbsoluteFill, Sequence } from 'remotion'
import { ComposeScene, CoverScene, CtaScene, PagesScene, PdfScene, PlanScene, TitleScene } from './scenes'
import { FONT, type TopicToBookProps } from './spec'

/** «De un tema a un libro en 30 s», the first fixed video: the app's own flow, animated with a real tome. */

// Where each scene starts (frames): hook, composer, plan, cover, pages, pdf, cta.
const AT = { hook: 0, typing: 90, plan: 240, cover: 360, pages: 510, pdf: 690, cta: 810, end: 900 }

export function TopicToBook({ script, tome }: TopicToBookProps) {
  return (
    <AbsoluteFill style={{ background: '#ffffff', fontFamily: FONT, color: '#0c0a09' }}>
      <Sequence from={AT.hook} durationInFrames={AT.typing - AT.hook}><TitleScene dur={AT.typing - AT.hook} caption={script.hook} /></Sequence>
      <Sequence from={AT.typing} durationInFrames={AT.plan - AT.typing}><ComposeScene dur={AT.plan - AT.typing} text={script.request} /></Sequence>
      <Sequence from={AT.plan} durationInFrames={AT.cover - AT.plan}><PlanScene dur={AT.cover - AT.plan} tome={tome} caption={script.plan} /></Sequence>
      <Sequence from={AT.cover} durationInFrames={AT.pages - AT.cover}><CoverScene dur={AT.pages - AT.cover} tome={tome} caption={script.cover} /></Sequence>
      <Sequence from={AT.pages} durationInFrames={AT.pdf - AT.pages}><PagesScene dur={AT.pdf - AT.pages} tome={tome} caption={script.pages} /></Sequence>
      <Sequence from={AT.pdf} durationInFrames={AT.cta - AT.pdf}><PdfScene dur={AT.cta - AT.pdf} tome={tome} caption={script.pdf} /></Sequence>
      <Sequence from={AT.cta}><CtaScene dur={AT.end - AT.cta} caption={script.cta} /></Sequence>
    </AbsoluteFill>
  )
}
