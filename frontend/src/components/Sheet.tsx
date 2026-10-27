import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { themeVars, useThemeFonts } from '../lib/themes'
import type { Block, Design } from '../lib/types'
import { AssetsContext } from '../lib/assets'
import { Blocks } from './BlockView'

type Props = {
  design: Design | null | undefined
  position: number
  title: string
  blocks?: Block[]
  assets?: Record<string, string>
  credits?: Record<string, string>
  painting?: boolean
  children?: ReactNode
  className?: string
}

/** A printed page in the tome's theme: same opener, fonts and palette as the PDF. */
export function Sheet({ design, position, title, blocks, assets = {}, credits = {}, painting = false, children, className = '' }: Props) {
  useThemeFonts(design)
  const { theme, ornament, style } = themeVars(design)
  const label = theme.opener === 'blob' ? String(position) : theme.opener === 'numeral' ? String(position).padStart(2, '0') : `Sección ${position}`
  return (
    <article className={`sheet opener-${theme.opener} ${className}`} style={style}>
      <header className="op">
        {/* Static markup from lib/themes, never model output. */}
        {ornament && <svg className="orn" viewBox="0 0 24 24" aria-hidden="true" dangerouslySetInnerHTML={{ __html: ornament }} />}
        <span className="num">{label}</span>
        <h1 className="sheet-title">{title}</h1>
      </header>
      <AssetsContext.Provider value={{ urls: assets, credits, painting }}>{blocks ? <Blocks blocks={blocks} /> : children}</AssetsContext.Provider>
    </article>
  )
}

const PAGE_WIDTH = 794 // A4 at 96 dpi: the thumbnail is the real page, scaled down

/** A section as a miniature page; scales with its grid cell. */
export function PageThumb(props: Omit<Props, 'className'>) {
  const box = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(0.25)
  useLayoutEffect(() => {
    const el = box.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => setScale(entry.contentRect.width / PAGE_WIDTH))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return (
    <div className="thumb" ref={box} aria-hidden="true">
      <div className="thumb-page" style={{ width: PAGE_WIDTH, transform: `scale(${scale})` }}>
        <Sheet {...props} blocks={props.blocks?.slice(0, 14)} className="paper" />
      </div>
    </div>
  )
}
