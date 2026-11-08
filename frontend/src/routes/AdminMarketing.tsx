import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Player } from '@remotion/player'
import { useMemo, useState } from 'react'
import { Navigate } from 'react-router'
import { AppShell } from '../components/AppShell'
import { errorText } from '../components/ErrorNote'
import { api } from '../lib/apiClient'
import { GENRE_LABEL } from '../lib/labels'
import { useMe, useSeries } from '../lib/queries'
import type { Genre, Series } from '../lib/types'
import { StoryboardVideo } from '../video/Storyboard'
import { TopicToBook } from '../video/TopicToBook'
import { DURATION, FPS, SCENES, SIZES, boardFrames, fontsReady, timeline, type Scene, type SceneType, type Storyboard, type VideoKind,
  type VideoScript, type VideoTome } from '../video/spec'
import { AdminTabs } from './AdminUsers'

type Format = keyof typeof SIZES
type Video = { id: string; series_id: string | null; format: Format; created_at: string; has_mp4: boolean; rendered_at: string | null }
  & ({ template: 'storyboard'; script: Storyboard } | { template: 'topic_to_book'; script: VideoScript })
type Tome = { id: string; title: string; genre: Genre | null; cover_url: string | null }

const FIELDS: [keyof VideoScript, string, number][] = [
  ['hook', 'Gancho (los primeros 3 s)', 60], ['request', 'Lo que escribe la docente', 140], ['plan', 'Subtítulo: el plan', 60],
  ['cover', 'Subtítulo: la portada', 60], ['pages', 'Subtítulo: las páginas', 60], ['pdf', 'Subtítulo: el PDF', 60],
  ['cta', 'Cierre', 60],
]
const FORMAT_LABEL: Record<Format, string> = { '9:16': 'Vertical 9:16', '1:1': 'Cuadrado 1:1', '16:9': 'Horizontal 16:9' }
const KIND_LABEL: Record<VideoKind, string> = { marketing: 'Marketing', explainer: 'Explicativo', tutorial: 'Tutorial' }
const KIND_HINT: Record<VideoKind, string> = {
  marketing: 'Ej.: anuncio para mamás que hacen homeschooling: ahorra el domingo',
  explainer: 'Ej.: cómo funciona Jelyx, de escribir el tema al PDF',
  tutorial: 'Ej.: tutorial para editar las páginas de un libro',
}
const headline = (v: Video) => v.template === 'storyboard' ? v.script.title : v.script.hook

/** The tome as the video shows it: its cover, its first pictures and its sections. */
function videoTome(s: Series): VideoTome {
  const pictures = s.lessons.flatMap((l) => (l.content_json?.blocks ?? [])
    .filter((b) => b.type === 'image' && b.asset_id).map((b) => s.assets[(b as { asset_id: string }).asset_id]))
  type Plate = { asset_id?: string; question?: string; answer?: string; notes?: string[]; find?: string; size?: string }
  const plate = s.lessons.flatMap((l) => (l.content_json?.blocks ?? []) as unknown as Plate[])
    .find((b) => b.size === 'plate' && b.asset_id && b.question && s.assets[b.asset_id])
  return {
    title: s.title ?? s.topic, kind: s.genre ? GENRE_LABEL[s.genre] : 'Libro', audience: s.audience.label,
    cover: s.cover_url, pages: pictures.filter(Boolean).slice(0, 6), sections: s.lessons.map((l) => l.title),
    plate: plate && { image: s.assets[plate.asset_id!], question: plate.question!, answer: plate.answer, notes: plate.notes ?? [], find: plate.find },
  }
}

/** Marketing: promotional videos of the app made from real tomes, reviewed here and downloaded as MP4. */
export function AdminMarketing() {
  const { data: me } = useMe()
  const staff = me?.platform_role === 'admin' || me?.platform_role === 'staff'
  const qc = useQueryClient()
  const [open, setOpen] = useState<string | null>(null)
  const [seriesId, setSeriesId] = useState('')
  const [format, setFormat] = useState<Format>('9:16')
  const [ask, setAsk] = useState('')
  const [kind, setKind] = useState<VideoKind>('tutorial')
  const [duration, setDuration] = useState<15 | 30 | 45 | 60>(30)
  const videos = useQuery({ queryKey: ['marketing-videos'], enabled: staff,
    queryFn: () => api.get<{ videos: Video[] }>('/api/admin/marketing/videos') })
  const tomes = useQuery({ queryKey: ['admin-series', 'ready-for-video'], enabled: staff,
    queryFn: () => api.get<{ series: Tome[] }>('/api/admin/series?status=ready&limit=96') })
  const create = useMutation({
    mutationFn: () => api.post<{ video: Video }>('/api/admin/marketing/videos', { series_id: seriesId, format, ask: ask.trim() || null, kind, duration }),
    onSuccess: async ({ video }) => {
      await qc.invalidateQueries({ queryKey: ['marketing-videos'] })
      setOpen(video.id)
      setAsk('')
    },
  })
  const fetchMp4 = useMutation({  // the kept MP4: a short-lived link, opened as a download
    mutationFn: (id: string) => api.get<{ url: string }>(`/api/admin/marketing/videos/${id}/mp4`),
    onSuccess: ({ url }) => window.location.assign(url),
  })
  if (me && !staff) return <Navigate to="/app" replace />
  const current = videos.data?.videos.find((v) => v.id === open)
  const titles = Object.fromEntries((tomes.data?.series ?? []).map((t) => [t.id, t.title]))

  return (
    <AppShell>
      <AdminTabs />
      <header className="page-editor-head">
        <p className="eyebrow">Marketing</p>
        <h1 className="display sm">Videos de la app</h1>
        <p className="muted">Pide el video que necesitas: un anuncio, cómo funciona la app o un tutorial. DeepSeek dirige el storyboard con escenas de la app real y un tomo tuyo; tú lo ajustas, lo revisas y descargas el MP4.</p>
      </header>

      <section className="panel marketing-new">
        <span className="section-h">Nuevo video</span>
        <label className="field"><span>Tomo que muestra</span>
          <select value={seriesId} onChange={(e) => setSeriesId(e.target.value)}>
            <option value="">Elige un tomo terminado…</option>
            {tomes.data?.series.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
          </select>
        </label>
        <fieldset className="field"><legend>Formato</legend>
          <div className="segmented-inline">
            {(Object.keys(SIZES) as Format[]).map((f) => (
              <button key={f} type="button" className={format === f ? 'chip on' : 'chip'} onClick={() => setFormat(f)}>{FORMAT_LABEL[f]}</button>
            ))}
          </div>
        </fieldset>
        <fieldset className="field"><legend>Tipo de video</legend>
          <div className="segmented-inline">
            {(Object.keys(KIND_LABEL) as VideoKind[]).map((k) => (
              <button key={k} type="button" className={kind === k ? 'chip on' : 'chip'} onClick={() => setKind(k)}>{KIND_LABEL[k]}</button>
            ))}
          </div>
        </fieldset>
        <label className="field"><span>¿Qué video necesitas?</span>
          <textarea value={ask} onChange={(e) => setAsk(e.target.value)} maxLength={500} rows={3} placeholder={KIND_HINT[kind]} /></label>
        <fieldset className="field"><legend>Duración</legend>
          <div className="segmented-inline">
            {([15, 30, 45, 60] as const).map((d) => (
              <button key={d} type="button" className={duration === d ? 'chip on' : 'chip'} onClick={() => setDuration(d)}>{d} s</button>
            ))}
          </div>
        </fieldset>
        <button className="primary" onClick={() => create.mutate()} disabled={!seriesId || create.isPending}>
          {create.isPending ? 'DeepSeek dirige el video…' : 'Crear storyboard'}
        </button>
        {create.error && <p className="error small" role="alert">{errorText(create.error, 'No se pudo escribir el guion.')}</p>}
      </section>

      {videos.error && <p className="error">{errorText(videos.error, 'No pudimos cargar los videos.')}</p>}
      {current && <VideoEditor key={current.id} video={current} title={current.series_id ? titles[current.series_id] : undefined} onClose={() => setOpen(null)} />}
      <section className="marketing-videos">
        <h2 className="section-h">Tus videos</h2>
        {fetchMp4.error && <p className="error small" role="alert">{errorText(fetchMp4.error, 'No se pudo descargar.')}</p>}
        <ul className="marketing-list">
          {videos.data?.videos.map((v) => (
            <li key={v.id} className={v.id === open ? 'on' : undefined}>
              <div>
                <strong>{headline(v)}</strong>
                <span className="muted small">{v.template === 'storyboard' ? `${KIND_LABEL[v.script.kind]} · ${v.script.duration} s · ` : ''}{FORMAT_LABEL[v.format]} · {(v.series_id && titles[v.series_id]) || 'Tomo'} · {new Date(v.created_at).toLocaleDateString('es-MX', { day: 'numeric', month: 'short' })}</span>
              </div>
              <span className={v.has_mp4 ? 'pill ok' : 'pill idle'}>{v.has_mp4 ? 'MP4 listo' : 'Sin MP4'}</span>
              <span className="marketing-actions">
                {v.has_mp4 && <button type="button" className="primary small" onClick={() => fetchMp4.mutate(v.id)} disabled={fetchMp4.isPending}>Descargar MP4</button>}
                <button type="button" className="ghost small" onClick={() => setOpen(v.id)}>{v.id === open ? 'Abierto' : 'Abrir'}</button>
              </span>
            </li>
          ))}
        </ul>
        {videos.data?.videos.length === 0 && <p className="muted">Aún no hay videos. Elige un tomo y pide el primero.</p>}
      </section>
    </AppShell>
  )
}

function VideoEditor({ video, title, onClose }: { video: Video; title?: string; onClose: () => void }) {
  const qc = useQueryClient()
  const series = useSeries(video.series_id ?? '')
  const [script, setScript] = useState<VideoScript | Storyboard>(video.script)
  const [format, setFormat] = useState<Format>(video.format)
  const [progress, setProgress] = useState<number | null>(null)
  const [renderError, setRenderError] = useState<string | null>(null)
  const tome = useMemo(() => series.data ? videoTome(series.data) : null, [series.data])
  const [width, height] = SIZES[format]
  const board = video.template === 'storyboard' ? script as Storyboard : null
  const fixed = board ? null : script as VideoScript
  const frames = board ? boardFrames(board) : DURATION
  const dirty = JSON.stringify(script) !== JSON.stringify(video.script) || format !== video.format
  const save = useMutation({
    mutationFn: () => api.patch<{ video: Video }>(`/api/admin/marketing/videos/${video.id}`, { format, script }),
    onSuccess: async ({ video: saved }) => {
      setScript(saved.script)  // the server evens the scenes out to the length asked for
      await qc.invalidateQueries({ queryKey: ['marketing-videos'] })
    },
  })
  const remove = useMutation({
    mutationFn: () => api.delete(`/api/admin/marketing/videos/${video.id}`),
    onSuccess: async () => { onClose(); await qc.invalidateQueries({ queryKey: ['marketing-videos'] }) },
  })
  const voice = board ? board.scenes.map((sc) => sc.voice.trim()).filter(Boolean).join(' ') : fixed!.voiceover ?? spoken(fixed!)
  const screen = board ? boardScreen(board) : onScreen(fixed!)

  async function render() {
    if (!tome) return
    setRenderError(null)
    setProgress(0)
    try {  // drawn and encoded in this tab (WebCodecs), then kept in storage so it is downloaded again at once
      let current = script
      if (dirty) current = (await save.mutateAsync()).video.script  // the kept MP4 always matches the saved script
      disposable()
      const { renderMediaOnWeb } = await import('@remotion/web-renderer')
      await fontsReady()
      const result = video.template === 'storyboard'
        ? await renderMediaOnWeb({
          composition: { id: 'storyboard', component: StoryboardVideo, durationInFrames: boardFrames(current as Storyboard), fps: FPS, width, height,
            defaultProps: { board: current as Storyboard, tome } },
          inputProps: { board: current as Storyboard, tome }, onProgress: (p) => setProgress(p.progress) })
        : await renderMediaOnWeb({
          composition: { id: 'topic-to-book', component: TopicToBook, durationInFrames: DURATION, fps: FPS, width, height,
            defaultProps: { script: current as VideoScript, tome } },
          inputProps: { script: current as VideoScript, tome }, onProgress: (p) => setProgress(p.progress) })
      const blob = await result.getBlob()
      const url = URL.createObjectURL(blob)
      const a = Object.assign(document.createElement('a'), { href: url, download: `jelyx-${format.replace(':', 'x')}-${video.id.slice(0, 6)}.mp4` })
      a.click()
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
      setProgress(1)
      const { key, upload_url } = await api.post<{ key: string; upload_url: string }>(`/api/admin/marketing/videos/${video.id}/upload`)
      const put = await fetch(upload_url, { method: 'PUT', body: blob, headers: { 'Content-Type': 'video/mp4' } })
      if (!put.ok) throw new Error('El MP4 se descargó, pero no se pudo guardar en la sección.')
      await api.post(`/api/admin/marketing/videos/${video.id}/rendered`, { key })
      await qc.invalidateQueries({ queryKey: ['marketing-videos'] })
    } catch (e) {
      const why = e instanceof Error ? e.message : ''
      setRenderError(`No se pudo crear el video en este navegador${why ? ` (${why})` : ''}. Prueba en Chrome de escritorio.`)
    } finally {
      setProgress(null)
    }
  }

  return (
    <section className="panel marketing-editor">
      <div className="marketing-head">
        <span className="section-h">{title ?? 'Video'}{board ? ` · ${KIND_LABEL[board.kind]}` : ''}</span>
        <button type="button" className="ghost small" onClick={onClose}>Cerrar</button>
      </div>
      <div className="marketing-body">
        <div className="marketing-stage" style={{ aspectRatio: `${width} / ${height}` }}>
          {!tome ? <div className="page-preview-wait">{series.isError ? 'No se pudo cargar el tomo.' : 'Cargando el tomo…'}</div>
            : board ? (
              <Player component={StoryboardVideo} inputProps={{ board, tome }} durationInFrames={frames} fps={FPS}
                compositionWidth={width} compositionHeight={height} controls loop style={{ width: '100%', height: '100%' }} />
            ) : (
              <Player component={TopicToBook} inputProps={{ script: fixed!, tome }} durationInFrames={DURATION} fps={FPS}
                compositionWidth={width} compositionHeight={height} controls loop style={{ width: '100%', height: '100%' }} />
            )}
        </div>
        <div className="page-form">
          <fieldset className="field"><legend>Formato</legend>
            <div className="segmented-inline">
              {(Object.keys(SIZES) as Format[]).map((f) => (
                <button key={f} type="button" className={format === f ? 'chip on' : 'chip'} onClick={() => setFormat(f)}>{FORMAT_LABEL[f]}</button>
              ))}
            </div>
          </fieldset>
          {board ? <BoardFields board={board} onChange={setScript} /> : FIELDS.map(([key, label, max]) => (
            <label key={key} className="field"><span>{label}</span>
              {key === 'request'
                ? <textarea value={fixed![key]} onChange={(e) => setScript({ ...fixed!, [key]: e.target.value })} rows={2} maxLength={max} />
                : <input value={fixed![key]} onChange={(e) => setScript({ ...fixed!, [key]: e.target.value })} maxLength={max} />}
            </label>
          ))}
          <button className="primary" onClick={() => save.mutate()} disabled={!dirty || save.isPending}>{save.isPending ? 'Guardando…' : 'Guardar guion'}</button>
          {save.error && <p className="error small" role="alert">{errorText(save.error, 'No se pudo guardar.')}</p>}
          <hr />
          <button className="primary" onClick={render} disabled={!tome || progress !== null}>
            {progress === 1 ? 'Guardando el MP4…' : progress !== null ? `Creando el MP4… ${Math.round(progress * 100)} %`
              : video.has_mp4 && !dirty ? 'Crear el MP4 otra vez' : 'Crear MP4'}
          </button>
          <span className="muted small">El video se crea en este navegador (mejor en Chrome de escritorio); tarda unos minutos y la pestaña debe quedar abierta. Queda guardado en «Tus videos» para descargarlo cuando quieras.</span>
          {renderError && <p className="error small" role="alert">{renderError}</p>}
          <label className="field"><span>Guion para voz en off · {Math.round(frames / FPS)} s</span>
            {board ? <textarea value={voice} readOnly rows={6} />
              : <textarea value={voice} onChange={(e) => setScript({ ...fixed!, voiceover: e.target.value })} rows={6} maxLength={700} />}
            <span className="muted small">{words(voice)} palabras{board ? ' · se edita escena por escena, arriba' : ''} · pégalo en tu app de voz (ElevenLabs, CapCut…) y súmale el audio al MP4.</span>
            <CopyButton text={voice} label="Copiar guion de voz" />
          </label>
          <div className="field"><span>Textos en pantalla, por escena</span>
            <CopyButton text={screen} label="Copiar textos en pantalla" />
          </div>
          {script.post && (
            <label className="field"><span>Texto para publicar</span>
              <textarea value={script.post} onChange={(e) => setScript({ ...script, post: e.target.value })} rows={5} maxLength={700} />
              <CopyButton text={script.post} label="Copiar texto" />
            </label>
          )}
          <button type="button" className="ghost small" onClick={() => remove.mutate()} disabled={remove.isPending}>Borrar este video</button>
        </div>
      </div>
    </section>
  )
}

/** The storyboard, scene by scene: what it shows, how long, its line on screen and its voice; reordered or removed. */
function BoardFields({ board, onChange }: { board: Storyboard; onChange: (b: Storyboard) => void }) {
  const [adding, setAdding] = useState<SceneType>('editor_open')
  const set = (i: number, scene: Partial<Scene>) => onChange({ ...board, scenes: board.scenes.map((sc, j) => (j === i ? { ...sc, ...scene } : sc)) })
  const move = (i: number, by: number) => {
    const scenes = [...board.scenes]
    ;[scenes[i], scenes[i + by]] = [scenes[i + by], scenes[i]]
    onChange({ ...board, scenes })
  }
  const steps = timeline(board)
  return (
    <div className="field board">
      <label className="field"><span>Título del video</span>
        <input value={board.title} onChange={(e) => onChange({ ...board, title: e.target.value })} maxLength={80} /></label>
      <span>Escenas · {board.duration} s en total (al guardar se ajustan a esa duración)</span>
      <ol className="board-scenes">
        {board.scenes.map((sc, i) => (
          <li key={i}>
            <div className="board-head">
              <strong>{steps[i].step ? `Paso ${steps[i].step} · ` : ''}{SCENES[sc.type].label}</strong>
              <input type="number" min={1} max={15} step={0.5} value={sc.seconds} aria-label="Segundos"
                onChange={(e) => set(i, { seconds: Number(e.target.value) || 1 })} /><span className="muted small">s</span>
              <button type="button" className="ghost small" disabled={i === 0} onClick={() => move(i, -1)} aria-label="Subir">↑</button>
              <button type="button" className="ghost small" disabled={i === board.scenes.length - 1} onClick={() => move(i, 1)} aria-label="Bajar">↓</button>
              <button type="button" className="ghost small" disabled={board.scenes.length <= 2}
                onClick={() => onChange({ ...board, scenes: board.scenes.filter((_, j) => j !== i) })} aria-label="Quitar escena">✕</button>
            </div>
            <input value={sc.caption} onChange={(e) => set(i, { caption: e.target.value })} maxLength={70} placeholder="Texto en pantalla" />
            {SCENES[sc.type].types && <input value={sc.text} onChange={(e) => set(i, { text: e.target.value })} maxLength={140} placeholder={SCENES[sc.type].types} />}
            <textarea value={sc.voice} onChange={(e) => set(i, { voice: e.target.value })} maxLength={300} rows={2} placeholder="Voz en off de esta escena" />
          </li>
        ))}
      </ol>
      <div className="board-add">
        <select value={adding} onChange={(e) => setAdding(e.target.value as SceneType)}>
          {(Object.keys(SCENES) as SceneType[]).map((t) => <option key={t} value={t}>{SCENES[t].label}</option>)}
        </select>
        <button type="button" className="ghost small" disabled={board.scenes.length >= 16} onClick={() => onChange({ ...board,
          scenes: [...board.scenes.slice(0, -1), { type: adding, seconds: 4, caption: '', voice: '', text: '' }, ...board.scenes.slice(-1)] })}>
          + Añadir escena</button>
      </div>
    </div>
  )
}

/** Safari on iPhone (and other browsers without Symbol.dispose): the web renderer reads its objects' disposers under
 * Symbol.for('Symbol.dispose') but its own polyfill names the symbol Symbol.for('dispose'), so every render failed with
 * «Object not disposable». Defining the symbol first, under the key it reads, makes both agree. */
function disposable() {
  const symbols = Symbol as unknown as Record<string, unknown>
  for (const name of ['dispose', 'asyncDispose']) {
    if (typeof symbols[name] !== 'symbol') Object.defineProperty(Symbol, name, { value: Symbol.for(`Symbol.${name}`) })
  }
}

const clock = (frames: number) => `${Math.round(frames / FPS)} s`
const boardScreen = (b: Storyboard) => timeline(b).map(({ scene, from, frames, step }) =>
  `${clock(from)}–${clock(from + frames)} · ${step ? `Paso ${step} · ` : ''}${SCENES[scene.type].label}: ${scene.caption}${scene.text ? ` (${scene.text})` : ''}`).join('\n')

const words = (t: string) => t.split(/\s+/).filter(Boolean).length
// Scripts written before the voiceover existed: their screen lines, read in order.
const spoken = (s: VideoScript) => [s.hook, s.request, s.plan, s.cover, s.pages, s.pdf, `${s.cta}, en docs punto jelyx punto app.`]
  .map((l) => l.trim().replace(/[.!?¿¡]*$/, '')).filter(Boolean).join('. ')
const onScreen = (s: VideoScript) => [
  `0–3 s · Gancho: ${s.hook}`, `3–8 s · Pedido: ${s.request}`, `8–12 s · Plan: ${s.plan}`, `12–17 s · Portada: ${s.cover}`,
  `17–23 s · Páginas: ${s.pages}`, `23–27 s · PDF: ${s.pdf}`, `27–30 s · Cierre: ${s.cta} · docs.jelyx.app`].join('\n')

function CopyButton({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false)
  return (
    <button type="button" className="ghost small" onClick={async () => {
      await navigator.clipboard.writeText(text)
      setDone(true)
      setTimeout(() => setDone(false), 1800)
    }}>{done ? 'Copiado ✓' : label}</button>
  )
}
