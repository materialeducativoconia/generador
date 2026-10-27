import { createContext } from 'react'

/** Asset id -> public URL and photo credit, plus whether the Illustrator is still painting this tome. */
export const AssetsContext = createContext<{ urls: Record<string, string>; credits: Record<string, string>; painting: boolean }>({
  urls: {},
  credits: {},
  painting: false,
})
