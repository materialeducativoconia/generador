import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { AppShell } from '../components/AppShell'
import { ApiError } from '../lib/api'
import { api } from '../lib/apiClient'
import { ART_LABEL, COVER_LABEL } from '../lib/labels'
import { useCollections, useIdentities, useStyles } from '../lib/queries'
import { themeVars, useThemeFonts } from '../lib/themes'
import type { Design, Identity } from '../lib/types'

const AUDIENCES = ['Preescolar y primaria baja', 'Primaria', 'Secundaria', 'Adultos', 'Variado']
const errorText = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback)

/** Mis identidades: the user as a publisher with their own line. Agents propose three, the user keeps one and
 * gives it to a collection, so every level of the collection looks, sounds and signs the same. */
export function Identities() {
  const { data, isLoading } = useIdentities()
  const styles = (useStyles().data?.styles ?? []).filter((s) => s.status === 'ready')
  const qc = useQueryClient()
  const [about, setAbout] = useState('')
  const [audience, setAudience] = useState(AUDIENCES[0])
  const [personality, setPersonality] = useState('')
  const [style, setStyle] = useState('')
  const create = useMutation({
    mutationFn: () => api.post('/api/identities', { about: about.trim(), audience, personality: personality.trim() || null, style_id: style || null }),
    onSuccess: () => { setAbout(''); setPersonality('') },
    onSettled: () => qc.invalidateQueries({ queryKey: ['identities'] }),
  })
  function submit(e: FormEvent) {
    e.preventDefault()
    if (about.trim().length >= 3 && !create.isPending) create.mutate()
  }
  const identities = data?.identities ?? []
  return (
    <AppShell>
      <section className="styles-head">
        <div>
          <p className="eyebrow">Tu línea editorial</p>
          <h1 className="display">Mis identidades</h1>
          <p className="muted">
            Como una editorial con sello propio: nombre, sello, colores, letra, estilo de ilustración, portada, voz y
            mascota. Asigna una identidad a una colección y todos sus niveles se verán, sonarán y firmarán igual.
          </p>
        </div>
      </section>
      <form className="panel identity-form" onSubmit={submit}>
        <label className="field">
          <span>¿Qué publicas?</span>
          <textarea value={about} onChange={(e) => setAbout(e.target.value)} rows={2} maxLength={600}
                    placeholder="Ej.: Cuadernillos de matemáticas y lectoescritura para primaria, muy prácticos" />
        </label>
        <div className="identity-form-row">
          <label className="field">
            <span>Para quién</span>
            <select value={audience} onChange={(e) => setAudience(e.target.value)}>{AUDIENCES.map((a) => <option key={a}>{a}</option>)}</select>
          </label>
          <label className="field">
            <span>Personalidad (opcional)</span>
            <input type="text" value={personality} onChange={(e) => setPersonality(e.target.value)} maxLength={200} placeholder="cálida, divertida, ordenada" />
          </label>
          {styles.length > 0 && (
            <label className="field">
              <span>Inspirada en</span>
              <select value={style} onChange={(e) => setStyle(e.target.value)}>
                <option value="">Ningún estilo</option>
                {styles.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </label>
          )}
        </div>
        <button className="primary" type="submit" disabled={about.trim().length < 3 || create.isPending}>
          {create.isPending ? 'Enviando…' : 'Proponer 3 identidades'}
        </button>
        {create.error && <p className="error small" role="alert">{errorText(create.error, 'No se pudo crear.')}</p>}
      </form>
      {isLoading ? <p className="muted">Cargando…</p> : identities.length === 0 ? (
        <p className="muted">Aún no tienes identidades. Describe lo que publicas y te proponemos tres líneas distintas.</p>
      ) : identities.map((i) => <IdentityRow key={i.id} identity={i} />)}
    </AppShell>
  )
}

function IdentityRow({ identity: i }: { identity: Identity }) {
  const qc = useQueryClient()
  const collections = useCollections().data ?? []
  const refresh = () => qc.invalidateQueries({ queryKey: ['identities'] })
  const choose = useMutation({
    mutationFn: (index: number) => api.post(`/api/identities/${i.id}/choose`, { index }),
    onSettled: () => Promise.all([refresh(), qc.invalidateQueries({ queryKey: ['series'] })]),
  })
  const propose = useMutation({ mutationFn: () => api.post(`/api/identities/${i.id}/propose`), onSettled: refresh })
  const edit = useMutation({ mutationFn: (body: object) => api.patch(`/api/identities/${i.id}`, body), onSettled: refresh })
  const remove = useMutation({ mutationFn: () => api.delete(`/api/identities/${i.id}`), onSettled: () => Promise.all([refresh(), qc.invalidateQueries({ queryKey: ['collections'] })]) })
  const used = collections.filter((c) => i.collection_ids.includes(c.id)).map((c) => c.name)
  const name = i.design?.brand?.name
  return (
    <section className="identity-row">
      <div className="identity-row-head">
        <h2 className="section-h">{name ?? i.brief.about}</h2>
        {used.length > 0 && <span className="muted small">Colecciones: {used.join(', ')}</span>}
        <span className="spacer" />
        {i.design && <button className="ghost small" onClick={() => { const n = window.prompt('Nombre del sello', name); if (n?.trim()) edit.mutate({ name: n.trim() }) }}>Renombrar</button>}
        {i.design && <button className="ghost small" onClick={() => { const t = window.prompt('Lema', i.design?.brand?.tagline); if (t != null) edit.mutate({ tagline: t.trim() }) }}>Lema</button>}
        {i.status !== 'generating' && <button className="ghost small" onClick={() => propose.mutate()} disabled={propose.isPending}>Otras propuestas</button>}
        <button className="ghost small" disabled={remove.isPending}
          onClick={() => { if (window.confirm(`¿Borrar la identidad${name ? ` «${name}»` : ''}? Sus tomos conservan su diseño.`)) remove.mutate() }}>Borrar</button>
      </div>
      {i.status === 'generating' && <p className="muted"><span className="spinner" /> La estratega de marca y la diseñadora están proponiendo tres líneas…</p>}
      {i.status === 'failed' && <p className="error small">{i.error}</p>}
      {i.status === 'ready' && i.design && <div className="identity-grid one"><IdentityCard design={i.design} chosen /></div>}
      {i.candidates.length > 0 && i.status !== 'generating' && (i.status === 'choosing' || !i.design) && (
        <>
          <p className="muted small">Elige la que te represente; podrás pedir otras propuestas.</p>
          <div className="identity-grid">
            {i.candidates.map((c, n) => (
              <IdentityCard key={n} design={c}
                action={<button className="primary small" onClick={() => choose.mutate(n)} disabled={choose.isPending}>Elegir esta</button>} />
            ))}
          </div>
        </>
      )}
      {i.status === 'ready' && i.candidates.length > 0 && i.design && <ChooseAgain identity={i} onPick={(n) => choose.mutate(n)} />}
      {(choose.error || edit.error) && <p className="error small" role="alert">{errorText(choose.error ?? edit.error, 'No se pudo guardar.')}</p>}
    </section>
  )
}

/** After picking, the other proposals stay one click away. */
function ChooseAgain({ identity: i, onPick }: { identity: Identity; onPick: (n: number) => void }) {
  const [open, setOpen] = useState(false)
  if (!open) return <button className="ghost small" onClick={() => setOpen(true)}>Ver las otras propuestas</button>
  return (
    <div className="identity-grid">
      {i.candidates.map((c, n) => c.brand?.name === i.design?.brand?.name ? null : (
        <IdentityCard key={n} design={c} action={<button className="ghost small" onClick={() => onPick(n)}>Cambiar a esta</button>} />
      ))}
    </div>
  )
}

/** A mock cover of the line plus its system: how a tome of this identity would look on the shelf. */
function IdentityCard({ design: d, chosen, action }: { design: Design; chosen?: boolean; action?: React.ReactNode }) {
  useThemeFonts(d)
  const { style, theme } = themeVars(d)
  const b = d.brand
  const head = d.head_font ?? theme.head
  return (
    <article className={`panel identity-card${chosen ? ' chosen' : ''}`}>
      <div className={`identity-cover ${d.cover_layout ?? 'plate'}`} style={style}>
        <span className="kicker">Colección · Nivel 1</span>
        <span className="title" style={{ fontFamily: `'${head}', sans-serif` }}>Tu próximo tomo</span>
        {b?.mascot && <span className="mascot">con {b.mascot.name}</span>}
        <span className="imprint">
          {d.mark_svg && <span className="seal" dangerouslySetInnerHTML={{ __html: d.mark_svg }} />}
          {b?.name}
        </span>
      </div>
      <div className="identity-body">
        <h3 style={{ fontFamily: `'${head}', sans-serif` }}>{b?.name}</h3>
        {b?.tagline && <p className="small muted">{b.tagline}</p>}
        <div className="swatches">{d.palette.map((c) => <span key={c} style={{ background: c }} title={c} />)}</div>
        {b?.personality.length ? <p className="chips">{b.personality.map((p) => <span key={p} className="chip">{p}</span>)}</p> : null}
        <p className="small">
          Letra {head} · {d.illustration ? ART_LABEL[d.illustration] : 'ilustración propia'} · {COVER_LABEL[d.cover_layout ?? 'plate']}
        </p>
        {b?.voice && <p className="small voice">«{b.voice}»</p>}
        {b?.mascot && <p className="small muted">Mascota: {b.mascot.name}</p>}
        {action}
      </div>
    </article>
  )
}
