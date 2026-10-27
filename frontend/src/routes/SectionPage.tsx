import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { AppShell, StatusPill } from '../components/AppShell'
import { Blocks } from '../components/BlockView'
import { ApiError } from '../lib/api'
import { api } from '../lib/apiClient'
import { useLesson } from '../lib/queries'

export function SectionPage() {
  const { id = '' } = useParams()
  const { data: lesson, isPending, error } = useLesson(id)
  const [instructions, setInstructions] = useState('')
  const qc = useQueryClient()
  const navigate = useNavigate()
  const regenerate = useMutation({
    mutationFn: () => api.post(`/api/lessons/${id}/regenerate`, { instructions: instructions.trim() || null }),
    onSuccess: async () => {
      await Promise.all([qc.invalidateQueries({ queryKey: ['progress', lesson!.series_id] }), qc.invalidateQueries({ queryKey: ['me'] })])
      navigate(`/app/tomos/${lesson!.series_id}`)
    },
  })

  if (isPending) return <AppShell><div className="skeleton tall" /></AppShell>
  if (error || !lesson) return <AppShell><p className="error">{error instanceof ApiError ? error.message : 'No pudimos cargar la sección.'}</p></AppShell>

  return (
    <AppShell>
      <Link to={`/app/tomos/${lesson.series_id}`} className="back">← Volver al tomo</Link>
      <div className="section-layout">
        <article className="sheet">
          <p className="eyebrow">Sección {lesson.position}</p>
          <h1 className="sheet-title">{lesson.title}</h1>
          {lesson.content_json ? <Blocks blocks={lesson.content_json.blocks} /> : <p className="muted">Esta sección aún no tiene contenido.</p>}
        </article>
        <aside className="side">
          <StatusPill status={lesson.status} />
          {lesson.objectives.length > 0 && (
            <div>
              <h2 className="side-h">Objetivos</h2>
              <ul className="side-list">{lesson.objectives.map((o, i) => <li key={i}>{o}</li>)}</ul>
            </div>
          )}
          <div>
            <h2 className="side-h">Regenerar</h2>
            <textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} rows={3} placeholder="Ej.: más ejercicios y frases más cortas" maxLength={2000} />
            <button className="primary block" onClick={() => regenerate.mutate()} disabled={regenerate.isPending}>
              {regenerate.isPending ? 'Enviando…' : 'Regenerar sección'}
            </button>
            {regenerate.error && <p className="error small">{regenerate.error instanceof ApiError ? regenerate.error.message : 'No se pudo regenerar.'}</p>}
          </div>
        </aside>
      </div>
    </AppShell>
  )
}
