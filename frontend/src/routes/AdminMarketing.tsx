import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { Player } from '@remotion/player'
import { useMemo, useRef, useState } from 'react'
import { Navigate } from 'react-router'
import { AppShell } from '../components/AppShell'
import { errorText } from '../components/ErrorNote'
import { api } from '../lib/apiClient'
import { GENRE_LABEL } from '../lib/labels'
import { useMe, useSeries } from '../lib/queries'
import type { Genre, Series } from '../lib/types'
import { StoryboardVideo } from '../video/Storyboard'
import { TopicToBook } from '../video/TopicToBook'
import { Voiced, type VoiceClip } from '../video/Voiced'
import { DURATION, FPS, LOOKS, SCENES, SIZES, TRANSITIONS, boardFrames, fontsReady, timeline, type Capture, type Look, type Scene, type SceneType,
  type ShelfBook, type Storyboard, type Transition, type VideoKind, type VideoScript, type VideoTome } from '../video/spec'
import { AdminTabs } from './AdminUsers'

type Format = keyof typeof SIZES
type Video = { id: string; series_id: string | null; format: Format; created_at: string; has_mp4: boolean; rendered_at: string | null }
  & ({ template: 'storyboard'; script: Storyboard } | { template: 'topic_to_book'; script: VideoScript })
type Tome = { id: string; title: string; genre: Genre | null; cover_url: string | null }
type Structure = { key: string; label: string; kinds: VideoKind[]; how: string }

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
    cast: (s.cast ?? []).filter((c) => c.sheet_url).map((c) => ({ name: c.name, sheet: c.sheet_url! })),
    plate: plate && { image: s.assets[plate.asset_id!], question: plate.question!, answer: plate.answer, notes: plate.notes ?? [], find: plate.find },
  }
}

/** The real cover as the PDF prints it, title painted, in a size for video; `forced`, with an option switched off. */
const coverShot = (id: string, forced = '') => ({ queryKey: ['cover-shot', id, forced], staleTime: Infinity, retry: 1,
  queryFn: () => api.get<{ image: string }>(`/api/series/${id}/cover/preview?hd=true${forced}`).then((r) => r.image) })

/** The tome with its real cover: the printed one (title, kicker, signature) and, for the editor's cover scene, the
 * same cover without the name line and then without the age badge. Null while they are being filmed. */
function useFilmedTome(seriesId: string) {
  const series = useSeries(seriesId)
  const [full, noName, bare] = useQueries({ queries: ['', '&name_line=false', '&name_line=false&age=false']
    .map((f) => ({ ...coverShot(seriesId, f), enabled: !!seriesId && !!series.data?.cover_url })) })
  const waiting = !!series.data?.cover_url && (full.isPending || noName.isPending || bare.isPending)
  const tome = useMemo(() => {
    if (!series.data || waiting) return null
    const t = videoTome(series.data)
    return full.data ? { ...t, art: t.cover, cover: full.data, covers: { full: full.data, noName: noName.data ?? full.data, bare: bare.data ?? noName.data ?? full.data } } : t
  }, [series.data, waiting, full.data, noName.data, bare.data])
  return { tome, isError: series.isError }
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
  const [structure, setStructure] = useState('auto')
  const [draft, setDraft] = useState<Storyboard | null>(null)  // proposed, seen and changed before the video exists
  const videos = useQuery({ queryKey: ['marketing-videos'], enabled: staff,
    queryFn: () => api.get<{ videos: Video[] }>('/api/admin/marketing/videos') })
  const tomes = useQuery({ queryKey: ['admin-series', 'ready-for-video'], enabled: staff,
    queryFn: () => api.get<{ series: Tome[] }>('/api/admin/series?status=ready&limit=96') })
  const structures = useQuery({ queryKey: ['marketing-structures'], enabled: staff, staleTime: Infinity,
    queryFn: () => api.get<{ structures: Structure[] }>('/api/admin/marketing/structures') })
  const captures = useCaptures(staff)
  const shelf = useShelf(tomes.data?.series ?? [])
  const ways = (structures.data?.structures ?? []).filter((st) => st.kinds.includes(kind))
  const asked = { series_id: seriesId, format, ask: ask.trim() || null, kind, duration }
  const propose = useMutation({
    mutationFn: () => api.post<{ script: Storyboard }>('/api/admin/marketing/storyboard', { ...asked, structure }),
    onSuccess: ({ script }) => { setDraft(script); setOpen(null) },
  })
  const create = useMutation({
    mutationFn: () => api.post<{ video: Video }>('/api/admin/marketing/videos', { ...asked, script: draft }),
    onSuccess: async ({ video }) => {
      await qc.invalidateQueries({ queryKey: ['marketing-videos'] })
      setOpen(video.id)
      setDraft(null)
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
              <button key={k} type="button" className={kind === k ? 'chip on' : 'chip'} onClick={() => { setKind(k); setStructure('auto') }}>{KIND_LABEL[k]}</button>
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
        <fieldset className="field"><legend>Estructura</legend>
          <div className="segmented-inline">
            <button type="button" className={structure === 'auto' ? 'chip on' : 'chip'} onClick={() => setStructure('auto')}>Automática</button>
            {ways.map((st) => (
              <button key={st.key} type="button" className={structure === st.key ? 'chip on' : 'chip'} title={st.how} onClick={() => setStructure(st.key)}>{st.label}</button>
            ))}
          </div>
          <span className="muted small">{structure === 'auto' ? 'DeepSeek elige una distinta a la del último video.' : ways.find((st) => st.key === structure)?.how}</span>
        </fieldset>
        <button className="primary" onClick={() => propose.mutate()} disabled={!seriesId || propose.isPending}>
          {propose.isPending ? 'DeepSeek dirige el video…' : draft ? 'Proponer otra estructura' : 'Ver la estructura'}
        </button>
        {propose.error && <p className="error small" role="alert">{errorText(propose.error, 'No se pudo escribir el guion.')}</p>}
      </section>

      {draft && <Draft board={draft} seriesId={seriesId} format={format} onChange={setDraft} onAgain={() => propose.mutate()} again={propose.isPending}
        onCreate={() => create.mutate()} creating={create.isPending} error={create.error} onDiscard={() => setDraft(null)}
        structure={structures.data?.structures.find((st) => st.key === draft.structure)?.label} captures={captures} shelf={shelf} />}

      {videos.error && <p className="error">{errorText(videos.error, 'No pudimos cargar los videos.')}</p>}
      {current && <VideoEditor key={current.id} captures={captures} shelf={shelf} video={current} title={current.series_id ? titles[current.series_id] : undefined} onClose={() => setOpen(null)} />}
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
      <CaptureLibrary captures={captures} />
    </AppShell>
  )
}

/** The proposed storyboard before it is a video: its structure at a glance, playing, and changed scene by scene. */
function Draft({ board, seriesId, format, structure, captures, shelf, onChange, onAgain, again, onCreate, creating, error, onDiscard }: {
  board: Storyboard; seriesId: string; format: Format; structure?: string; captures: Record<string, Capture>; shelf: ShelfBook[]; onChange: (b: Storyboard) => void
  onAgain: () => void; again: boolean; onCreate: () => void; creating: boolean; error: unknown; onDiscard: () => void
}) {
  const series = useFilmedTome(seriesId)
  const tome = series.tome
  const [width, height] = SIZES[format]
  const [editing, setEditing] = useState(false)
  return (
    <section className="panel marketing-editor">
      <div className="marketing-head">
        <span className="section-h">Propuesta · {board.title}</span>
        <button type="button" className="ghost small" onClick={onDiscard}>Descartar</button>
      </div>
      <div className="marketing-body">
        <div className="marketing-stage" style={{ aspectRatio: `${width} / ${height}` }}>
          {tome ? <Player component={StoryboardVideo} inputProps={{ board, tome, captures, shelf }} durationInFrames={boardFrames(board)} fps={FPS}
            compositionWidth={width} compositionHeight={height} controls loop style={{ width: '100%', height: '100%' }} />
            : <div className="page-preview-wait">Cargando el tomo…</div>}
        </div>
        <div className="page-form">
          <p className="muted small">{KIND_LABEL[board.kind]} · {board.duration} s{structure ? ` · ${structure}` : ''} · {board.scenes.length} escenas. Aún no se guarda: revísala, cámbiala o pide otra.</p>
          <ol className="board-outline">
            {timeline(board).map(({ scene, from, frames, step }, i) => (
              <li key={i}>
                <span className="muted small">{clock(from)}–{clock(from + frames)}</span>
                <strong>{step ? `Paso ${step} · ` : ''}{SCENES[scene.type].label}</strong>
                {scene.type === 'screen' && <span className="muted small">{(scene.capture && captures[scene.capture]?.name) || 'sin captura'}</span>}
                {scene.caption && <span>«{scene.caption}»</span>}
                {scene.text && <span className="muted small">{scene.text}</span>}
              </li>
            ))}
          </ol>
          <Styling board={board} onChange={onChange} />
          <button className="primary" onClick={onCreate} disabled={creating}>{creating ? 'Guardando…' : 'Crear este video'}</button>
          {error ? <p className="error small" role="alert">{errorText(error, 'No se pudo crear el video.')}</p> : null}
          <button type="button" className="ghost small" onClick={onAgain} disabled={again}>{again ? 'DeepSeek dirige otra…' : 'Otra estructura'}</button>
          <button type="button" className="ghost small" onClick={() => setEditing(!editing)}>{editing ? 'Ocultar escenas' : 'Editar escenas'}</button>
          {editing && <BoardFields board={board} onChange={onChange} captures={captures} />}
        </div>
      </div>
    </section>
  )
}

function VideoEditor({ video, title, captures, shelf, onClose }: { video: Video; title?: string; captures: Record<string, Capture>; shelf: ShelfBook[]; onClose: () => void }) {
  const qc = useQueryClient()
  const series = useFilmedTome(video.series_id ?? '')
  const [script, setScript] = useState<VideoScript | Storyboard>(video.script)
  const [format, setFormat] = useState<Format>(video.format)
  const [progress, setProgress] = useState<number | null>(null)
  const [renderError, setRenderError] = useState<string | null>(null)
  const [withVoice, setWithVoice] = useState(true)
  const tome = series.tome
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
    let lock: { release: () => Promise<void> } | null = null
    try {  // drawn and encoded in this tab (WebCodecs), then kept in storage so it is downloaded again at once
      let current = script
      if (dirty) current = (await save.mutateAsync()).video.script  // the kept MP4 always matches the saved script
      disposable()
      const web = await import('@remotion/web-renderer')
      await fontsReady()
      const plans = await renderPlans(web.canRenderMediaOnWeb, width, height)
      // The voiceover, read by Gemini (OpenRouter) scene by scene; the lines that did not change come back from storage.
      const clips = withVoice ? (await api.post<{ clips: VoiceClip[] }>(`/api/admin/marketing/videos/${video.id}/voice`)).clips : []
      const inner = video.template === 'storyboard'
        ? { Video: StoryboardVideo as React.ComponentType<object>, props: { board: current as Storyboard, tome, captures, shelf },
          board: current as Storyboard, frames: boardFrames(current as Storyboard) }
        : { Video: TopicToBook as React.ComponentType<object>, props: { script: current as VideoScript, tome }, board: null, frames: DURATION }
      const composition = { id: 'video', component: Voiced, durationInFrames: inner.frames, fps: FPS, width, height,
        defaultProps: { Video: inner.Video, props: inner.props, board: inner.board, clips } }
      lock = await awake()
      let result: Awaited<ReturnType<typeof web.renderMediaOnWeb>> | null = null
      let failure: unknown = null
      for (const plan of plans) {  // a phone that cannot encode 1080p H.264 still gets the video, smaller or in another codec
        try {
          setProgress(0)
          // With the voice, AAC (the renderer brings its own encoder where the phone lacks one); without it, no audio track.
          result = await web.renderMediaOnWeb({ composition: composition as never, inputProps: composition.defaultProps as never, muted: !clips.length,
            container: 'mp4', videoCodec: plan.codec, scale: plan.scale, outputTarget: 'arraybuffer', onProgress: (p) => setProgress(p.progress) })
          break
        } catch (e) {
          failure = e
        }
      }
      if (!result) throw failure instanceof Error ? failure : new Error(String(failure ?? 'sin detalle'))
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
      setRenderError(`No se pudo crear el video en este navegador${why ? ` (${why})` : ''}. Deja la pantalla encendida y esta pestaña al frente, o prueba en Chrome de escritorio.`)
    } finally {
      await lock?.release().catch(() => {})
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
            : progress !== null ? <div className="page-preview-wait">Creando el video… la vista previa vuelve al terminar.</div>
            : board ? (
              <Player component={StoryboardVideo} inputProps={{ board, tome, captures, shelf }} durationInFrames={frames} fps={FPS}
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
          {board && <Styling board={board} onChange={setScript} />}
          {board ? <BoardFields board={board} onChange={setScript} captures={captures} /> : FIELDS.map(([key, label, max]) => (
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
          <label className="check"><input type="checkbox" checked={withVoice} onChange={(e) => setWithVoice(e.target.checked)} />
            <span>Con voz en off (Gemini lee la voz de cada escena)</span></label>
          <span className="muted small">El video se crea en este navegador, también en el móvil; tarda unos minutos: deja la pantalla encendida y esta pestaña al frente. Queda guardado en «Tus videos» para descargarlo cuando quieras.</span>
          {renderError && <p className="error small" role="alert">{renderError}</p>}
          <label className="field"><span>Guion para voz en off · {Math.round(frames / FPS)} s</span>
            {board ? <textarea value={voice} readOnly rows={6} />
              : <textarea value={voice} onChange={(e) => setScript({ ...fixed!, voiceover: e.target.value })} rows={6} maxLength={700} />}
            <span className="muted small">{words(voice)} palabras{board ? ' · se edita escena por escena, arriba' : ''} · el MP4 ya lo lleva leído por Gemini; cópialo si prefieres otra voz.</span>
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
function BoardFields({ board, onChange, captures }: { board: Storyboard; onChange: (b: Storyboard) => void; captures: Record<string, Capture> }) {
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
            {sc.type === 'screen' && (
              <div className="board-head">
                <select value={sc.capture ?? ''} onChange={(e) => set(i, { capture: e.target.value, focus: 0 })} aria-label="Captura">
                  <option value="">Elige una captura…</option>
                  {Object.values(captures).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
                {sc.capture && (captures[sc.capture]?.focus.length ?? 0) > 1 && (
                  <select value={sc.focus ?? 0} onChange={(e) => set(i, { focus: Number(e.target.value) })} aria-label="Punto del zoom">
                    {captures[sc.capture].focus.map((f, j) => <option key={j} value={j}>Zoom: {f.label || `punto ${j + 1}`}</option>)}
                  </select>
                )}
              </div>
            )}
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

/** One finished tome per kind of book, its cover first, for the formats scene. */
/** One real tome per kind of book, each with its printed cover (title painted), or its art while that is filmed. */
function useShelf(tomes: Tome[]): ShelfBook[] {
  const picks = Object.keys(GENRE_LABEL).map((genre) => {
    const mine = tomes.filter((t) => t.genre === genre)
    return { genre, tome: mine.find((t) => t.cover_url) ?? mine[0] }
  })
  const shots = useQueries({ queries: picks.map(({ tome }) => ({ ...coverShot(tome?.id ?? ''), enabled: !!tome?.cover_url })) })
  const images = shots.map((q) => q.data ?? null).join('|')
  return useMemo(() => picks.map(({ genre, tome }, i) => ({ genre, label: GENRE_LABEL[genre], cover: shots[i].data ?? tome?.cover_url ?? null })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [tomes, images])
}

function useCaptures(enabled: boolean) {
  const { data } = useQuery({ queryKey: ['marketing-captures'], enabled, staleTime: 60 * 60_000,
    queryFn: () => api.get<{ captures: Capture[] }>('/api/admin/marketing/captures') })
  return useMemo(() => Object.fromEntries((data?.captures ?? []).map((c) => [c.id, c])), [data])
}

/** The text scenes' colours and how one scene gives way to the next. */
function Styling({ board, onChange }: { board: Storyboard; onChange: (b: Storyboard) => void }) {
  return (
    <>
      <fieldset className="field"><legend>Colores de los textos</legend>
        <div className="segmented-inline">
          {(Object.keys(LOOKS) as Look[]).map((l) => (
            <button key={l} type="button" className={(board.look ?? 'claro') === l ? 'chip on' : 'chip'} onClick={() => onChange({ ...board, look: l })}>{LOOKS[l].label}</button>
          ))}
        </div>
      </fieldset>
      <fieldset className="field"><legend>Transiciones</legend>
        <div className="segmented-inline">
          {(Object.keys(TRANSITIONS) as Transition[]).map((t) => (
            <button key={t} type="button" className={(board.transition ?? 'mixta') === t ? 'chip on' : 'chip'} onClick={() => onChange({ ...board, transition: t })}>{TRANSITIONS[t]}</button>
          ))}
        </div>
      </fieldset>
    </>
  )
}

/** Real screenshots of the app, uploaded once: each with a name the director reads and the points the camera zooms to. */
function CaptureLibrary({ captures }: { captures: Record<string, Capture> }) {
  const qc = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [open, setOpen] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const list = Object.values(captures)
  async function upload(files: FileList | null) {
    if (!files?.length) return
    setBusy(true)
    setError(null)
    try {
      for (const file of Array.from(files)) {
        const ext = file.type === 'image/jpeg' ? 'jpg' : file.type === 'image/webp' ? 'webp' : 'png'
        const { width, height } = await createImageBitmap(file)
        const { key, upload_url } = await api.post<{ key: string; upload_url: string }>(`/api/admin/marketing/captures/upload?ext=${ext}`)
        const put = await fetch(upload_url, { method: 'PUT', body: file, headers: { 'Content-Type': file.type || 'image/png' } })
        if (!put.ok) throw new Error(`No se pudo subir ${file.name}.`)
        const name = file.name.replace(/\.[^.]+$/, '').replace(/[-_]+/g, ' ').slice(0, 80) || 'Captura'
        await api.post('/api/admin/marketing/captures', { key, name, width, height })
      }
      await qc.invalidateQueries({ queryKey: ['marketing-captures'] })
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
    }
  }
  const current = open ? captures[open] : null
  return (
    <section className="marketing-videos">
      <h2 className="section-h">Capturas de la app</h2>
      <p className="muted small">Sube capturas reales de la app (de la computadora o del teléfono) y marca dónde debe acercarse la cámara. El director las usa en la escena «Pantalla real», dentro de un teléfono o una laptop.</p>
      <input ref={input} type="file" accept="image/png,image/jpeg,image/webp" multiple hidden onChange={(e) => upload(e.target.files)} />
      <button type="button" className="primary small" onClick={() => input.current?.click()} disabled={busy}>{busy ? 'Subiendo…' : '+ Subir capturas'}</button>
      {error ? <p className="error small" role="alert">{error instanceof Error && !(error as { code?: string }).code ? error.message : errorText(error, 'No se pudo subir la captura.')}</p> : null}
      <ul className="capture-grid">
        {list.map((c) => (
          <li key={c.id} className={c.id === open ? 'on' : undefined}>
            <button type="button" onClick={() => setOpen(c.id === open ? null : c.id)}>
              {c.url && <img src={c.url} alt="" loading="lazy" />}
              <span className="small">{c.name}</span>
              <span className={c.focus.length ? 'muted small' : 'error small'}>{c.focus.length ? `${c.focus.length} punto${c.focus.length > 1 ? 's' : ''} de zoom` : 'Sin puntos de zoom'}</span>
            </button>
          </li>
        ))}
      </ul>
      {current && <CaptureEditor key={current.id} capture={current} onClose={() => setOpen(null)} />}
    </section>
  )
}

function CaptureEditor({ capture, onClose }: { capture: Capture; onClose: () => void }) {
  const qc = useQueryClient()
  const [name, setName] = useState(capture.name)
  const [description, setDescription] = useState(capture.description)
  const [focus, setFocus] = useState(capture.focus)
  const save = useMutation({
    mutationFn: () => api.patch(`/api/admin/marketing/captures/${capture.id}`, { name, description, focus }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['marketing-captures'] }),
  })
  const remove = useMutation({
    mutationFn: () => api.delete(`/api/admin/marketing/captures/${capture.id}`),
    onSuccess: async () => { onClose(); await qc.invalidateQueries({ queryKey: ['marketing-captures'] }) },
  })
  const mark = (e: React.MouseEvent<HTMLDivElement>) => {
    if (focus.length >= 12) return
    const r = e.currentTarget.getBoundingClientRect()
    const x = Math.round(((e.clientX - r.left) / r.width) * 1000) / 1000
    const y = Math.round(((e.clientY - r.top) / r.height) * 1000) / 1000
    setFocus([...focus, { x, y, label: '' }])
  }
  return (
    <div className="panel capture-editor">
      <div className="capture-shot" onClick={mark} style={{ aspectRatio: `${capture.width} / ${capture.height}` }}>
        {capture.url && <img src={capture.url} alt="" draggable={false} />}
        {focus.map((f, i) => <span key={i} className="capture-dot" style={{ left: `${f.x * 100}%`, top: `${f.y * 100}%` }}>{i + 1}</span>)}
      </div>
      <div className="page-form">
        <label className="field"><span>Nombre</span><input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} /></label>
        <label className="field"><span>Qué muestra (lo lee el director)</span>
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} maxLength={300} rows={2} placeholder="Ej.: el Editor de páginas con la tira de miniaturas y el formulario" /></label>
        <div className="field"><span>Puntos de zoom · toca la captura para marcar uno</span>
          <ol className="board-outline">
            {focus.map((f, i) => (
              <li key={i}>
                <input value={f.label} maxLength={60} placeholder="Qué hay ahí, p. ej. «Añadir dato»"
                  onChange={(e) => setFocus(focus.map((g, j) => (j === i ? { ...g, label: e.target.value } : g)))} />
                <button type="button" className="ghost small" onClick={() => setFocus(focus.filter((_, j) => j !== i))} aria-label="Quitar punto">✕</button>
              </li>
            ))}
          </ol>
        </div>
        <button className="primary" onClick={() => save.mutate()} disabled={save.isPending}>{save.isPending ? 'Guardando…' : save.isSuccess ? 'Guardado ✓' : 'Guardar captura'}</button>
        {save.error && <p className="error small" role="alert">{errorText(save.error, 'No se pudo guardar.')}</p>}
        <button type="button" className="ghost small" onClick={onClose}>Cerrar</button>
        <button type="button" className="ghost small" onClick={() => remove.mutate()} disabled={remove.isPending}>Borrar captura</button>
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

type CanRender = typeof import('@remotion/web-renderer').canRenderMediaOnWeb
type Codec = 'h264' | 'h265' | 'vp9' | 'av1'
/** The encodings to try, best first: those the browser says it can make (full size in H.264, then smaller, as a phone's
 * hardware encoder often stops below 1080×1920, then the other codecs an MP4 holds), then plain H.264 anyway. The
 * check only orders the tries, never stops one: browsers answer it «no» (WebGL in an OffscreenCanvas, a cautious
 * encoder probe) where the render itself works, and a video that rendered before must render now. */
async function renderPlans(can: CanRender, width: number, height: number) {
  const tries: { codec: Codec; scale: number }[] = [{ codec: 'h264', scale: 1 }, { codec: 'h264', scale: 2 / 3 }, { codec: 'h264', scale: 0.5 },
    { codec: 'vp9', scale: 2 / 3 }, { codec: 'av1', scale: 2 / 3 }, { codec: 'h265', scale: 2 / 3 }]
  const ok = await Promise.all(tries.map(async ({ codec, scale }) => {
    const r = await can({ container: 'mp4', videoCodec: codec, width, height, scale, muted: true, outputTarget: 'arraybuffer' }).catch(() => null)
    return !!r && r.issues.every((i) => i.severity !== 'error' || i.type === 'webgl-unsupported')  // no 3D transforms here
  }))
  const passing = tries.filter((_, i) => ok[i])
  const fallback = tries.filter((t, i) => !ok[i] && t.codec === 'h264')
  return [...passing, ...fallback].slice(0, 4)
}

/** Keeps a phone's screen on while it renders: locked, the tab is frozen and the render dies. */
async function awake() {
  try {
    const nav = navigator as Navigator & { wakeLock?: { request: (t: 'screen') => Promise<{ release: () => Promise<void> }> } }
    return await nav.wakeLock?.request('screen') ?? null
  } catch {
    return null
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
