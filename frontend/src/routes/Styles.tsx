import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { AppShell } from '../components/AppShell'
import { errorText } from '../components/ErrorNote'
import { api } from '../lib/apiClient'
import { useMe, useStyles } from '../lib/queries'
import { useThemeFonts } from '../lib/themes'
import type { Style } from '../lib/types'

const TYPES = ['application/pdf', 'image/png', 'image/jpeg', 'image/webp']
const STATUS: Record<Style['status'], [string, string]> = {
  uploading: ['Subiendo…', 'idle'], analyzing: ['Analizando…', 'busy'], ready: ['Listo', 'ok'], failed: ['Falló', 'bad'],
}

type Created = { style: { id: string }; upload_url: string }

/** Reference files in, styles out: the agents read only the style, never copy the artwork or text. */
export function Styles() {
  const { data, isLoading } = useStyles()
  const qc = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [name, setName] = useState('')
  const input = useRef<HTMLInputElement>(null)

  const upload = useMutation({
    mutationFn: async () => {
      if (!file) return
      const created = await api.post<Created>('/api/styles', { name: name.trim() || file.name, content_type: file.type, size: file.size })
      const put = await fetch(created.upload_url, { method: 'PUT', body: file, headers: { 'Content-Type': file.type } })
      if (!put.ok) throw new Error('No se pudo subir el archivo.')
      await api.post(`/api/styles/${created.style.id}/analyze`)
    },
    onSuccess: () => {
      setFile(null)
      setName('')
      if (input.current) input.current.value = ''
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['styles'] }),
  })

  function submit(e: FormEvent) {
    e.preventDefault()
    if (file && !upload.isPending) upload.mutate()
  }

  const styles = data?.styles ?? []
  const allowed = useMe().data?.plan.styles ?? 0
  return (
    <AppShell>
      <section className="styles-head">
        <div>
          <p className="eyebrow">Biblioteca de estilos</p>
          <h1 className="display">Tus estilos</h1>
          <p className="muted">
            Sube PDFs o imágenes de cuadernillos que te gusten. Elegimos sus mejores páginas y extraemos su estilo
            (colores, tipografía, marcos, ilustración) para tus tomos; nunca copiamos sus dibujos, textos ni marca.
          </p>
        </div>
        {allowed === 0 ? <Upsell what="La biblioteca de estilos" /> : <form className="uploader" onSubmit={submit}>
          <input ref={input} type="file" accept={TYPES.join(',')} aria-label="Archivo de referencia"
                 onChange={(e) => {
                   const f = e.target.files?.[0] ?? null
                   setFile(f)
                   if (f && !name) setName(f.name.replace(/\.[^.]+$/, '').slice(0, 80))
                 }} />
          <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Nombre del estilo" maxLength={80} />
          <button type="submit" disabled={!file || upload.isPending}>{upload.isPending ? 'Subiendo…' : 'Subir referencia'}</button>
        </form>}
      </section>
      {upload.error && <p className="error" role="alert">{errorText(upload.error, upload.error instanceof Error ? upload.error.message : 'No se pudo subir.')}</p>}
      {isLoading ? <p className="muted">Cargando…</p> : styles.length === 0 ? (
        <p className="muted">Aún no tienes estilos. Sube tu primera referencia (máx. 50 MB).</p>
      ) : (
        <div className="style-grid">{styles.map((s) => <StyleCard key={s.id} style={s} />)}</div>
      )}
    </AppShell>
  )
}

function Upsell({ what }: { what: string }) {
  return (
    <div className="panel upsell">
      <p><strong>{what}</strong> está disponible desde el plan <strong>Creador</strong>.</p>
      <Link to="/app/plan" className="primary">Ver planes</Link>
    </div>
  )
}

function StyleCard({ style }: { style: Style }) {
  const qc = useQueryClient()
  useThemeFonts(style.design)
  const remove = useMutation({
    mutationFn: () => api.delete(`/api/styles/${style.id}`),
    onSettled: () => qc.invalidateQueries({ queryKey: ['styles'] }),
  })
  const [label, pill] = STATUS[style.status]
  const d = style.design
  return (
    <article className="panel style-card">
      <div className="previews">
        {[0, 1, 2].map((i) => style.previews[i]
          ? <img key={i} src={style.previews[i]} alt="" loading="lazy" />
          : <div key={i} className="empty" />)}
      </div>
      <h3>{style.name}<span className={`pill ${pill}`}>{label}</span></h3>
      {style.status === 'failed' && <p className="error small">{style.error}</p>}
      {d && (
        <>
          <div className="swatches">
            {d.palette.map((c) => <span key={c} style={{ background: c }} title={c} />)}
            {d.head_font && <span className="sample" style={{ border: 0, width: 'auto', height: 'auto', fontFamily: `'${d.head_font}'`, color: d.palette[2] }}>Ficha 1</span>}
          </div>
          {style.suits && <p className="small muted">{style.suits}</p>}
          {style.traits.length > 0 && <ul className="small">{style.traits.slice(0, 5).map((t) => <li key={t}>{t}</li>)}</ul>}
        </>
      )}
      <button className="ghost small" onClick={() => remove.mutate()} disabled={remove.isPending}>Borrar</button>
    </article>
  )
}
