import { Fragment, useContext, type ReactNode } from 'react'
import { AssetsContext } from '../lib/assets'
import type { Block, DiagramType } from '../lib/types'

/** **bold** and *italic* only, as React nodes: model output never becomes HTML. */
export function Inline({ text }: { text: string }) {
  const parts: ReactNode[] = []
  const re = /\*\*(.+?)\*\*|\*(?!\s)(.+?)(?<!\s)\*/g
  let last = 0
  for (const m of text.matchAll(re)) {
    if (m.index > last) parts.push(text.slice(last, m.index))
    parts.push(m[1] ? <strong key={m.index}>{m[1]}</strong> : <em key={m.index}>{m[2]}</em>)
    last = m.index + m[0].length
  }
  parts.push(text.slice(last))
  return <>{parts}</>
}

function ImageBlock({ block }: { block: Extract<Block, { type: 'image' }> }) {
  const { urls, credits, painting } = useContext(AssetsContext)
  const url = block.asset_id ? urls[block.asset_id] : undefined
  if (url) {
    return (
      <figure className={`fig ${block.size} ${block.kind}`}>
        <img src={url} alt={block.subject} loading="lazy" />
        {block.caption && <figcaption>{block.caption}</figcaption>}
        {credits[block.asset_id!] && <small className="credit">{credits[block.asset_id!]}</small>}
      </figure>
    )
  }
  return (
    <figure className={`img-ph ${block.size}${painting ? ' painting' : ''}`}>
      <span className="img-k">{block.kind === 'line_art' ? 'Dibujo para colorear' : 'Ilustración'}</span>
      <span>{block.subject}</span>
      <small>{painting ? 'Ilustrando…' : 'Sin ilustración'}</small>
    </figure>
  )
}

const WHITE = ['C', 'D', 'E', 'F', 'G', 'A', 'B']
const ES: Record<string, string> = { C: 'Do', D: 'Re', E: 'Mi', F: 'Fa', G: 'Sol', A: 'La', B: 'Si' }

function Keyboard({ block }: { block: Extract<Block, { type: 'keyboard' }> }) {
  const octave = Number(block.start.at(-1))
  const start = WHITE.indexOf(block.start[0])
  const whites = Array.from({ length: 7 * block.octaves }, (_, i) => `${WHITE[(start + i) % 7]}${octave + Math.floor((start + i) / 7)}`)
  const lit = new Set(block.highlight)
  const w = 34
  return (
    <figure className="kb">
      <svg viewBox={`-1 -1 ${whites.length * w + 2} 152`} role="img" aria-label={`Teclado: ${block.highlight.join(', ')}`}>
        {whites.map((n, i) => (
          <g key={n}>
            <rect x={i * w} width={w} height={150} rx={3} className={lit.has(n) ? 'w on' : 'w'} />
            {block.show_labels && (
              <text x={i * w + w / 2} y={138}>
                {ES[n[0]]}
              </text>
            )}
          </g>
        ))}
        {whites.slice(0, -1).map((n, i) =>
          'CDFGA'.includes(n[0]) ? (
            <rect key={`${n}#`} x={(i + 1) * w - 10} width={20} height={92} rx={2} className={lit.has(`${n[0]}#${n.slice(1)}`) ? 'b on' : 'b'} />
          ) : null,
        )}
      </svg>
      {block.caption && <figcaption>{block.caption}</figcaption>}
    </figure>
  )
}

function seededGrid(block: Extract<Block, { type: 'letter_grid' }>) {
  // Visual stand-in for the PDF's grid (which shuffles server-side); same mix of targets.
  let seed = [...block.id].reduce((a, c) => a + c.charCodeAt(0), 7)
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647)
  const total = block.rows * block.cols
  const nTargets = Math.max(block.targets.length, Math.round(total * 0.35))
  const cells = Array.from({ length: total }, (_, i) =>
    i < nTargets ? block.targets[i % block.targets.length] : block.distractors[Math.floor(rnd() * block.distractors.length)],
  )
  return cells.sort(() => rnd() - 0.5)
}

export function BlockView({ block, index }: { block: Block; index: number }) {
  switch (block.type) {
    case 'heading':
      return block.level === 2 ? <h2><Inline text={block.text} /></h2> : <h3><Inline text={block.text} /></h3>
    case 'paragraph':
      return <p><Inline text={block.text} /></p>
    case 'list': {
      const items = block.items.map((it, i) => <li key={i}><Inline text={it} /></li>)
      return block.style === 'number' ? <ol>{items}</ol> : <ul className={block.style}>{items}</ul>
    }
    case 'callout':
      return (
        <aside className={`callout ${block.variant}`}>
          {block.title && <strong className="callout-t">{block.title}</strong>}
          <Inline text={block.text} />
        </aside>
      )
    case 'table':
      return (
        <div className="table-wrap">
          <table>
            {block.caption && <caption>{block.caption}</caption>}
            <thead><tr>{block.headers.map((h, i) => <th key={i}><Inline text={h} /></th>)}</tr></thead>
            <tbody>{block.rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}><Inline text={c} /></td>)}</tr>)}</tbody>
          </table>
        </div>
      )
    case 'example':
      return (
        <div className="example">
          {block.title && <strong>{block.title}</strong>}
          <p><Inline text={block.text} /></p>
        </div>
      )
    case 'activity':
      return (
        <div className="activity">
          <div className="activity-h">
            <strong>{block.title}</strong>
            {block.duration_minutes && <span>{block.duration_minutes} min</span>}
          </div>
          {block.materials.length > 0 && <p className="muted small">Materiales: {block.materials.join(', ')}</p>}
          <ol>{block.steps.map((s, i) => <li key={i}><Inline text={s} /></li>)}</ol>
        </div>
      )
    case 'exercise':
      return (
        <div className="exercise">
          <p className="q"><span className="n">{index}.</span><Inline text={block.prompt} /></p>
          {block.kind === 'multiple_choice' && <ul className="opts">{block.options.map((o, i) => <li key={i}><Inline text={o} /></li>)}</ul>}
          {block.kind === 'true_false' && <ul className="opts"><li>Verdadero</li><li>Falso</li></ul>}
          {block.answer && (
            <details className="answer">
              <summary>Ver respuesta</summary>
              <Inline text={block.answer} />
              {block.explanation && <> — <Inline text={block.explanation} /></>}
            </details>
          )}
        </div>
      )
    case 'keyboard':
      return <Keyboard block={block} />
    case 'tracing':
      return (
        <div className="tracing">
          {block.instruction && <p><strong>{block.instruction}</strong></p>}
          {Array.from({ length: block.repeat }, (_, i) => (
            <div key={i} className={i === 0 ? 'trace-row model' : 'trace-row'}>{block.text}</div>
          ))}
        </div>
      )
    case 'letter_grid':
      return (
        <div>
          {block.instruction && <p><strong>{block.instruction}</strong></p>}
          <div className="lgrid" style={{ gridTemplateColumns: `repeat(${block.cols}, minmax(0, 56px))` }}>
            {seededGrid(block).map((c, i) => <span key={i}>{c}</span>)}
          </div>
        </div>
      )
    case 'image':
      return <ImageBlock block={block} />
    case 'writing_lines':
      return (
        <div className="lines">
          {block.label && <strong>{block.label}</strong>}
          {Array.from({ length: block.lines }, (_, i) => <div key={i} className="line" />)}
        </div>
      )
    case 'page_break':
      return <hr className="page-break" />
    default:
      return <Diagram block={block} />
  }
}

function Diagram({ block }: { block: Extract<Block, { type: DiagramType }> }) {
  const { diagrams } = useContext(AssetsContext)
  const svg = diagrams[block.id]
  if (!svg) return null
  return (
    <figure className="diagram">
      {/* Drawn by our backend from validated data, every model string escaped; never raw model output. */}
      <div dangerouslySetInnerHTML={{ __html: svg }} />
      {block.caption && <figcaption className="figcap">{block.caption}</figcaption>}
    </figure>
  )
}

export function Blocks({ blocks }: { blocks: Block[] }) {
  let n = 0
  return (
    <>
      {blocks.map((b) => (
        <Fragment key={b.id}>
          <BlockView block={b} index={b.type === 'exercise' ? ++n : 0} />
        </Fragment>
      ))}
    </>
  )
}
