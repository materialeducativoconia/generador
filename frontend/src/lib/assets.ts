import { createContext } from 'react'

/** Asset id -> public URL, plus whether the Illustrator is still painting this tome. */
export const AssetsContext = createContext<{ urls: Record<string, string>; painting: boolean }>({ urls: {}, painting: false })
