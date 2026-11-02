import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Navigate, useSearchParams } from 'react-router'
import { AppShell } from '../components/AppShell'
import { errorText } from '../components/ErrorNote'
import { api } from '../lib/apiClient'
import { useMe } from '../lib/queries'
import { AdminTabs } from './AdminUsers'

type Sample = { id: string; style: string; status: 'painting' | 'done' | 'failed'; error: string | null; cost_usd: number | null; chosen: boolean; url: string | null; raw_url: string | null }
type Run = { run: string; subject: string; created_at: string; samples: Sample[] }
type Lab = { styles: { key: string; name: string; inspired_by: string }[]; runs: Run[] }

/** The style lab: one subject painted in every house style, to keep the samples that look made by an illustrator. */
export function AdminStyles() {
  const { data: me } = useMe()
  const admin = me?.platform_role === 'admin'
  const staff = admin || me?.platform_role === 'staff'
  const [params] = useSearchParams()
  const [subject, setSubject] = useState('')
  const [seriesId, setSeriesId] = useState(params.get('tomo') ?? '')
  const [raw, setRaw] = useState<string | null>(null)
  const qc = useQueryClient()
  const { data, error } = useQuery({
    queryKey: ['style-lab'], enabled: staff,
    queryFn: () => api.get<Lab>('/api/admin/style-lab'),
    refetchInterval: (q) => q.state.data?.runs.some((r) => r.samples.some((s) => s.status === 'painting')) ? 4000 : false,
  })
  const paint = useMutation({
    mutationFn: () => api.post('/api/admin/style-lab', { subject: subject.trim() || null, series_id: seriesId.trim() || null }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['style-lab'] }),
  })
  const retry = useMutation({
    mutationFn: (run: string) => api.post(`/api/admin/style-lab/${run}/retry`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['style-lab'] }),
  })
  const choose = useMutation({
    mutationFn: (s: Sample) => api.patch(`/api/admin/style-lab/${s.id}`, { chosen: !s.chosen }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['style-lab'] }),
  })
  if (me && !staff) return <Navigate to="/app" replace />
  const name = (key: string) => data?.styles.find((s) => s.key === key)

  return (
    <AppShell>
      <section className="styles-head">
        <div>
          <p className="eyebrow">Administración</p>
          <h1 className="display sm">Estilos</h1>
          <p className="muted">La misma lámina pintada en cada estilo editorial. Las que marques como referencia guiarán ese estilo en los tomos.</p>
        </div>
      </section>
      <AdminTabs />
      {admin && (
        <form className="lab-form" onSubmit={(e) => { e.preventDefault(); paint.mutate() }}>
          <textarea value={subject} onChange={(e) => setSubject(e.target.value)} rows={3} maxLength={700}
                    placeholder="Qué pintar (si lo dejas vacío se usa la primera lámina del tomo)…" />
          <input value={seriesId} onChange={(e) => setSeriesId(e.target.value)} placeholder="ID del tomo (usa su lámina y sus personajes)" />
          <button className="primary" disabled={paint.isPending || (!subject.trim() && !seriesId.trim())}>
            {paint.isPending ? 'Enviando…' : `Pintar en ${data?.styles.length ?? 6} estilos`}
          </button>
          {paint.error && <p className="error">{errorText(paint.error, 'No se pudo pintar.')}</p>}
        </form>
      )}
      {error && <p className="error">{errorText(error, 'No pudimos cargar el laboratorio.')}</p>}
      {retry.error && <p className="error">{errorText(retry.error, 'No se pudo repintar.')}</p>}
      {data?.runs.map((run) => (
        <section key={run.run} className="lab-run">
          <p className="lab-subject">{run.subject}</p>
          {admin && run.samples.some((s) => s.status === 'failed') && (
            <button type="button" className="ghost small" onClick={() => retry.mutate(run.run)} disabled={retry.isPending}>
              Repintar las fallidas
            </button>
          )}
          <ul className="lab-grid">
            {run.samples.map((s) => (
              <li key={s.id} className={s.chosen ? 'chosen' : undefined}>
                <div className="lab-img">
                  {s.status === 'done' && s.url && <img src={raw === s.id ? s.raw_url! : s.url} alt={name(s.style)?.name ?? s.style} loading="lazy" />}
                  {s.status === 'painting' && <span className="spinner" />}
                  {s.status === 'failed' && <span className="error small">{s.error ?? 'Falló'}</span>}
                </div>
                <div className="lab-b">
                  <strong>{name(s.style)?.name ?? s.style}</strong>
                  <span className="muted small">Inspirado en {name(s.style)?.inspired_by ?? '—'}{s.cost_usd != null ? ` · $${s.cost_usd.toFixed(3)}` : ''}</span>
                  {s.status === 'done' && (
                    <span className="admin-tome-actions">
                      <button type="button" className="ghost small" onClick={() => setRaw(raw === s.id ? null : s.id)}>
                        {raw === s.id ? 'Ver terminado' : 'Ver original'}
                      </button>
                      {admin && (
                        <button type="button" className={s.chosen ? 'primary small' : 'ghost small'} onClick={() => choose.mutate(s)} disabled={choose.isPending}>
                          {s.chosen ? '✓ Referencia' : 'Usar como referencia'}
                        </button>
                      )}
                      <a className="ghost small" href={s.url!} target="_blank" rel="noreferrer">Abrir</a>
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}
      {data?.runs.length === 0 && <p className="muted">Aún no hay muestras.</p>}
    </AppShell>
  )
}
