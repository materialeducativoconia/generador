import { QueryClient, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { api, type Me } from './apiClient'
import { supabase } from './supabase'
import type { CoverFields, Export, Lesson, Progress, Series, SeriesSummary } from './types'

export const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 10_000, retry: 1, refetchOnWindowFocus: false } },
})

export const useMe = () => useQuery({ queryKey: ['me'], queryFn: () => api.get<Me>('/api/me') })

/** A cover takes ~20–60 s to paint; poll only while one is on its way. */
export const coverPending = (s: CoverFields & { status: string }) =>
  s.status === 'outlining' || s.cover_status === 'queued' || s.cover_status === 'running'

export const useSeriesList = () =>
  useQuery({
    queryKey: ['series'],
    queryFn: async () => (await api.get<{ series: SeriesSummary[] }>('/api/series')).series,
    refetchInterval: (q) => (q.state.data?.some(coverPending) ? 5000 : false),
  })

export const useSeries = (id: string) =>
  useQuery({
    queryKey: ['series', id],
    queryFn: () => api.get<Series>(`/api/series/${id}`),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data && coverPending(q.state.data) ? 5000 : false),
  })

export const useLesson = (id: string) => useQuery({ queryKey: ['lesson', id], queryFn: () => api.get<Lesson>(`/api/lessons/${id}`) })

export function useExport(id: string | null) {
  return useQuery({
    queryKey: ['export', id],
    queryFn: () => api.get<Export>(`/api/exports/${id}`),
    enabled: !!id,
    // Exports are short (5–30 s): a light poll is simpler than another Realtime channel.
    refetchInterval: (q) => (q.state.data && ['succeeded', 'failed'].includes(q.state.data.status) ? false : 2000),
  })
}

/**
 * Progress of a tome. Realtime events on generation_jobs only *signal* a change; the data always
 * comes from /progress, so a dropped websocket just means a refetch on reconnect (ARCHITECTURE.md §3.2).
 */
export function useProgress(id: string) {
  const qc = useQueryClient()
  const query = useQuery({
    queryKey: ['progress', id],
    queryFn: () => api.get<Progress>(`/api/series/${id}/progress`),
    refetchInterval: (q) => q.state.data?.poll_after_ms ?? false, // safety net, only while jobs are active
  })
  const lastState = useRef<string | null>(null)

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined
    const refetch = () => {
      clearTimeout(timer)
      // Debounced: ten sections finishing together must not fire ten requests.
      timer = setTimeout(() => void qc.invalidateQueries({ queryKey: ['progress', id] }), 500)
    }
    const channel = supabase
      .channel(`series:${id}`)
      .on('postgres_changes', { event: '*', schema: 'public', table: 'generation_jobs', filter: `series_id=eq.${id}` }, refetch)
      .subscribe((status) => {
        if (status === 'SUBSCRIBED') refetch()
      })
    return () => {
      clearTimeout(timer)
      void supabase.removeChannel(channel)
    }
  }, [id, qc])

  // When the tome's state moves on (outline ready, sections done), the detail view is stale too.
  useEffect(() => {
    const v = query.data ? `${query.data.status}:${query.data.version}:${query.data.counts.generated}:${query.data.counts.failed}:${query.data.images.done}` : null
    if (v && lastState.current !== null && lastState.current !== v) {
      void qc.invalidateQueries({ queryKey: ['series', id] })
      void qc.invalidateQueries({ queryKey: ['series'], exact: true })
    }
    lastState.current = v
  }, [query.data, id, qc])

  return query
}
