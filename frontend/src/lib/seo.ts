import { useEffect } from 'react'

/** The tab's title for a public page, kept when moving between routes inside the app (the build writes it too). */
export function usePageTitle(title: string | undefined) {
  useEffect(() => {
    if (title) document.title = title
  }, [title])
}
