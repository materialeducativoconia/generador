import { createContext } from 'react'

/** Asset id -> public URL and photo credit, block id -> diagram SVG, and whether the Illustrator is still painting. */
export const AssetsContext = createContext<{
  urls: Record<string, string>
  credits: Record<string, string>
  diagrams: Record<string, string>
  painting: boolean
}>({ urls: {}, credits: {}, diagrams: {}, painting: false })
